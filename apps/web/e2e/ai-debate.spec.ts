/**
 * AI 討論（Phase 3 B PoC）のブラウザ E2E。実キーは使わず RIHRP_E2E_LLM_BASE_URL のスタブを使う。
 */
import { expect, test, type Page } from "@playwright/test";

const EMAIL = "admin@e2e.local";
const PASSWORD = "e2e-password-123";
const HYPOTHESIS =
  "河道湾曲部の外岸側で根固め工の重量を従来比1.5倍にすると、計画高水時の護岸基礎部の洗掘深は30%以上低減する。";
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

test("AI 討論を生成し、プレビューから採用できる（採用時のみ保存）", async ({ page }) => {
  test.skip(!configured, "LLM スタブ未設定のため AI 討論 E2E は対象外");
  await login(page);

  const title = `AI討論E2E-${Date.now()}`;
  const created = await api(page, "POST", "/api/projects", { title, summary: "" });
  const projectId = created.project.id as string;
  const payload = {
    title,
    hypothesis: HYPOTHESIS,
    evidence: [
      {
        id: "ev-1",
        title: "護岸基礎の洗掘に関する現地観測",
        stance: "support",
        reliability: 78,
        summary: "重量を増した区間で洗掘深が低減した。",
      },
    ],
    critiques: [],
  };
  await api(page, "PUT", `/api/projects/${projectId}/research`, {
    expected_version: 0,
    payload,
  });
  const before = (await api(page, "GET", `/api/projects/${projectId}/research`)) as {
    version: number;
  };

  await page.goto("/");
  await expect(page.locator("#projSel")).toBeVisible();
  await page.selectOption("#projSel", { label: title });
  await expect(page.locator('textarea[data-bind="hypothesis"]')).toHaveValue(HYPOTHESIS);

  await page.locator('#nav .navitem[data-v="debate"]').click();
  await page.locator('button[data-act="aiDebate"]').click();

  const main = page.locator("#main");
  await expect(main).toContainText("AI生成の討論（試行）");
  await expect(main).toContainText("E2E スタブの根拠発言");

  // 採用前は保存されない
  const during = (await api(page, "GET", `/api/projects/${projectId}/research`)) as {
    version: number;
    payload: { debateAi?: unknown };
  };
  expect(during.version).toBe(before.version);
  expect(during.payload.debateAi).toBeUndefined();

  // 破棄では保存されず、プレビューも消える
  await page.locator('button[data-act="aiDebateDiscard"]').click();
  await expect(main).not.toContainText("AI生成の討論（試行）");
  const discarded = (await api(page, "GET", `/api/projects/${projectId}/research`)) as {
    version: number;
    payload: { debateAi?: unknown };
  };
  expect(discarded.version).toBe(before.version);
  expect(discarded.payload.debateAi).toBeUndefined();

  // 再生成して採用する
  await page.locator('button[data-act="aiDebate"]').click();
  await expect(main).toContainText("AI生成の討論（試行）");

  await page.locator('button[data-act="aiDebateAdopt"]').click();
  await expect(main).toContainText("この討論は AI 生成");
  await expect(page.locator("#chat")).toContainText("E2E スタブの根拠発言");

  // 採用時のみ保存される（provenance 付き）
  await expect
    .poll(
      async () => {
        const doc = (await api(page, "GET", `/api/projects/${projectId}/research`)) as {
          payload: { debateAi?: { model?: string }; debate?: unknown[] };
        };
        return `${doc.payload.debateAi ? "ai" : "none"}:${doc.payload.debate?.length ?? 0}`;
      },
      { timeout: 10_000 },
    )
    .toBe("ai:3");
});
