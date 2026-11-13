/**
 * AI 批判・候補提案（Phase 3 C）のブラウザ E2E。実キーは使わず RIHRP_E2E_LLM_BASE_URL のスタブを使う。
 */
import { expect, test, type Page } from "@playwright/test";

const EMAIL = "admin@e2e.local";
const PASSWORD = "e2e-password-123";
const HYPOTHESIS =
  "河道湾曲部の外岸側で根固め工の重量を従来比1.5倍にすると、計画高水時の護岸基礎部の洗掘深は30%以上低減する。";
const VARS = ["根固め工の重量", "洗掘深", "流速"];
const configured = Boolean(process.env.RIHRP_E2E_LLM_BASE_URL);

async function login(page: Page): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("メールアドレス").fill(EMAIL);
  await page.getByLabel("パスワード").fill(PASSWORD);
  await page.getByRole("button", { name: "サインイン", exact: true }).click();
  await expect(page.locator(".topbar")).toBeVisible();
}

async function csrf(page: Page): Promise<string> {
  const value = (await page.context().cookies()).find((cookie) => cookie.name === "rihrp_csrf")?.value;
  if (!value) throw new Error("CSRF cookie がありません");
  return value;
}

async function api(page: Page, method: string, path: string, data?: unknown) {
  const response = await page.request.fetch(path, {
    method,
    headers: { "X-CSRF-Token": await csrf(page) },
    data,
  });
  if (!response.ok()) throw new Error(`${method} ${path} -> ${response.status()}`);
  return response.json();
}

async function seed(page: Page, title: string, payload: Record<string, unknown>) {
  const created = await api(page, "POST", "/api/projects", { title, summary: "" });
  const projectId = created.project.id as string;
  await api(page, "PUT", `/api/projects/${projectId}/research`, {
    expected_version: 0,
    payload: { title, hypothesis: HYPOTHESIS, evidence: [], critiques: [], ...payload },
  });
  const before = (await api(page, "GET", `/api/projects/${projectId}/research`)) as {
    version: number;
  };
  return { projectId, before };
}

test("AI 批判をプレビューし、採用時のみ保存する", async ({ page }) => {
  test.skip(!configured, "LLM スタブ未設定のため AI 批判 E2E は対象外");
  await login(page);
  const title = `AI批判E2E-${Date.now()}`;
  const { projectId, before } = await seed(page, title, {
    evidence: [
      {
        id: "ev-1",
        title: "護岸基礎の洗掘に関する現地観測",
        stance: "support",
        reliability: 78,
        summary: "重量を増した区間で洗掘深が低減した。",
      },
    ],
  });

  await page.goto("/");
  await expect(page.locator("#projSel")).toBeVisible();
  await page.selectOption("#projSel", { label: title });
  await page.locator('#nav .navitem[data-v="evidence"]').click();
  await page.locator('button[data-act="aiCritique"]').click();

  const main = page.locator("#main");
  await expect(main).toContainText("AI生成の批判（試行）");
  await expect(main).toContainText("E2E スタブの批判です");

  // 採用前は保存されない
  const during = (await api(page, "GET", `/api/projects/${projectId}/research`)) as {
    version: number;
    payload: { critiques?: unknown };
  };
  expect(during.version).toBe(before.version);
  expect(during.payload.critiques ?? []).toEqual([]);

  // 破棄では保存されない
  await page.locator('button[data-act="aiCritiqueDiscard"]').click();
  await expect(main).not.toContainText("AI生成の批判（試行）");
  const discarded = (await api(page, "GET", `/api/projects/${projectId}/research`)) as {
    version: number;
    payload: { critiques?: unknown[] };
  };
  expect(discarded.version).toBe(before.version);
  expect(discarded.payload.critiques ?? []).toEqual([]);

  // 再生成して採用
  await page.locator('button[data-act="aiCritique"]').click();
  await expect(main).toContainText("AI生成の批判（試行）");
  await page.locator('button[data-act="aiCritiqueAdopt"]').click();
  await expect(main).toContainText("E2E スタブの批判です");

  await expect
    .poll(
      async () => {
        const doc = (await api(page, "GET", `/api/projects/${projectId}/research`)) as {
          payload: {
            critiques?: { sev: string; status: string; origin: string }[];
            aiAssist?: { critiques?: { promptVersion?: string } };
          };
        };
        return `${doc.payload.critiques?.length ?? 0}:${doc.payload.critiques?.[0]?.sev}:${
          doc.payload.aiAssist?.critiques?.promptVersion ? "ai" : "none"
        }`;
      },
      { timeout: 10_000 },
    )
    .toBe("2:低:ai");
});

test("AI 候補をプレビューし、採用後に既存ロジックで採点する", async ({ page }) => {
  test.skip(!configured, "LLM スタブ未設定のため AI 候補 E2E は対象外");
  await login(page);
  const title = `AI候補E2E-${Date.now()}`;
  const { projectId } = await seed(page, title, {
    analysis: {
      field: "river",
      vars: VARS,
      inferred: [],
      nums: [],
      vague: [],
      iv: VARS[0],
      dv: VARS[1],
      dir: "増やすと低減する",
      quality: 3,
      hasNum: true,
      hasMech: true,
      hasCond: true,
      hasComp: false,
    },
    evidence: [
      {
        id: "ev-1",
        title: "護岸基礎の洗掘に関する現地観測",
        stance: "support",
        reliability: 78,
        summary: "重量を増した区間で洗掘深が低減した。",
        tags: VARS,
      },
    ],
  });

  await page.goto("/");
  await expect(page.locator("#projSel")).toBeVisible();
  await page.selectOption("#projSel", { label: title });
  await page.locator('#nav .navitem[data-v="compare"]').click();
  await page.locator('button[data-act="aiCandidate"]').click();

  const main = page.locator("#main");
  await expect(main).toContainText("AI生成の候補（試行）");
  await expect(main).toContainText("E2E スタブの候補です");

  const during = (await api(page, "GET", `/api/projects/${projectId}/research`)) as {
    payload: { candidates?: unknown };
  };
  expect(during.payload.candidates ?? null).toBeNull();

  await page.locator('button[data-act="aiCandidateAdopt"]').click();
  await expect(main).toContainText("E2E スタブの候補です");

  await expect
    .poll(
      async () => {
        const doc = (await api(page, "GET", `/api/projects/${projectId}/research`)) as {
          payload: {
            candidates?: { origin: string; scores?: { evidence?: number }; total?: number }[];
            aiAssist?: { candidates?: { promptVersion?: string } };
          };
        };
        const items = doc.payload.candidates ?? [];
        const ai = items.find((item) => item.origin === "AI提案");
        const scored = ai && typeof ai.scores?.evidence === "number" && typeof ai.total === "number";
        return `${items.length}:${ai ? "ai" : "none"}:${scored ? "scored" : "unscored"}:${
          doc.payload.aiAssist?.candidates?.promptVersion ? "meta" : "nometa"
        }`;
      },
      { timeout: 10_000 },
    )
    .toBe("2:ai:scored:meta");
});
