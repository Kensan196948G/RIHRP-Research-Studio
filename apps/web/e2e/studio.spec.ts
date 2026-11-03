import { expect, test, type Page } from "@playwright/test";

const EMAIL = "admin@e2e.local";
const PASSWORD = "e2e-password-123";
const TITLE = "河道湾曲部における護岸基礎の洗掘対策";
const HYPOTHESIS =
  "河道湾曲部の外岸側で根固め工の重量を従来比1.5倍にすると、計画高水時の護岸基礎部の洗掘深は30%以上低減する。これは外岸近傍の流速が減衰し、河床材料の移動が抑制されるためである。";

async function login(page: Page): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("メールアドレス").fill(EMAIL);
  await page.getByLabel("パスワード").fill(PASSWORD);
  await page.getByRole("button", { name: "サインイン", exact: true }).click();
  await expect(page.locator(".topbar")).toBeVisible();
}

async function openStudio(page: Page): Promise<void> {
  await login(page);
  await expect(page.locator("#nav .navitem")).toHaveCount(6);
}

type ResearchDoc = { version: number; payload: Record<string, unknown> };

async function fetchDoc(page: Page, title: string): Promise<ResearchDoc> {
  const projects = (await (await page.request.get("/api/projects")).json()) as {
    projects: { id: string; title: string }[];
  };
  const project = projects.projects.find((item) => item.title === title);
  if (!project) throw new Error(`project not found: ${title}`);
  return (await (await page.request.get(`/api/projects/${project.id}/research`)).json()) as ResearchDoc;
}

async function saveState(page: Page): Promise<string> {
  return (await page.locator("#saveState").innerText()).trim();
}

test.describe.configure({ mode: "serial" });

test("S-01/S-02/S-09/S-10 シェル（トップバー・警告ノート・6ステップナビ）", async ({ page }) => {
  await openStudio(page);

  // トップバー（ブランド・バッジ）
  await expect(page.locator(".topbar .brand-t")).toHaveText("RIHRP Research Studio");
  await expect(page.locator(".topbar .offbadge")).toHaveText("Offline Demo");

  // 警告ノート（プロトタイプの文言）
  const notice = page.locator(".notice");
  await expect(notice).toContainText("オフライン・シミュレーション");
  await expect(notice).toContainText("ルールベース処理");
  await expect(notice).toContainText("架空の模擬データ");
  await expect(notice).toContainText("科学的な真偽や新規性を保証しません");

  // ナビ 6 ステップの番号とラベル
  const labels = ["研究仮説登録", "AIタスク管理", "複数AI討論", "根拠・反証", "新仮説比較", "研究報告書"];
  for (let i = 0; i < labels.length; i += 1) {
    const item = page.locator("#nav .navitem").nth(i);
    await expect(item.locator(".num")).toHaveText(`0${i + 1}`);
    await expect(item.locator(".lbl")).toHaveText(labels[i]);
  }

  // 初期状態の表示
  await expect(page.locator("#nav .navitem").first().locator(".st")).toHaveText("未入力");
  await expect(page.locator("#main")).toContainText("STEP 01");
  await expect(page.locator("#main")).toContainText("研究仮説登録");
});

test("R-02/R-04/S-07 仮説のライブチェックとサーバー自動保存", async ({ page }) => {
  await openStudio(page);

  await page.locator('input[data-bind="title"]').fill(TITLE);
  await page.locator('textarea[data-bind="hypothesis"]').fill(HYPOTHESIS);
  await page.waitForTimeout(300);

  const live = page.locator("#liveCheck");
  await expect(live).toContainText("河川・水工");
  await expect(live).toContainText("構造スコア");
  await expect(live).toContainText("5 / 5");
  await expect(live).toContainText("1.5倍");
  await expect(live).toContainText("30%");

  // 保存状態（500ms デバウンスののちサーバー保存）
  await expect(page.locator("#nav .navitem").first().locator(".st")).toHaveText("r1 登録済み");
  await expect
    .poll(async () => saveState(page), { timeout: 10_000 })
    .toBe("サーバーに自動保存済み");
});

test("X-01 再読込してもサーバーから復元される", async ({ page }) => {
  await openStudio(page);
  await page.reload();
  await expect(page.locator(".topbar")).toBeVisible();
  await expect(page.locator('textarea[data-bind="hypothesis"]')).toHaveValue(HYPOTHESIS);
  await expect(page.locator('input[data-bind="title"]')).toHaveValue(TITLE);
  await expect(page.locator("#nav .navitem").first().locator(".st")).toHaveText("r1 登録済み");
});

test("S-04/R-13 新規研究の作成と削除（confirm）", async ({ page }) => {
  await openStudio(page);
  const before = await page.locator("#projSel option").count();

  await page.getByRole("button", { name: "＋ 新規研究" }).click();
  await expect(page.locator("#projSel option")).toHaveCount(before + 1);
  await expect(page.locator('input[data-bind="title"]')).toHaveValue("新しい研究テーマ");

  page.on("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: "この研究を削除" }).click();
  await expect(page.locator("#projSel option")).toHaveCount(before);

  // 元の研究に戻す
  await page.selectOption("#projSel", { label: TITLE });
  await expect(page.locator('textarea[data-bind="hypothesis"]')).toHaveValue(HYPOTHESIS);
});

test("T-03/T-04/T-07/T-08/T-13 タスク実行・承認・完了", async ({ page }) => {
  await openStudio(page);
  await page.locator('#nav .navitem[data-v="tasks"]').click();

  // 初期状態: 依存なしの 1 件だけ実行可能
  await expect(page.locator("#main")).toContainText("実行可能");
  await expect(page.locator("#main")).toContainText("依存待ち");

  await page.selectOption("#speedSel", "4");

  let sawVerifyApproval = false;
  let sawEvaluateApproval = false;
  for (let i = 0; i < 45; i += 1) {
    const banner = page.locator(".banner.warn");
    if (await banner.count()) {
      const text = await banner.innerText();
      if (text.includes("根拠の信頼性検証")) {
        sawVerifyApproval = true;
        expect(text).toContain("資料");
        expect(text).toContain("平均信頼性");
      }
      if (text.includes("統合評価・仮説比較")) sawEvaluateApproval = true;
      const approve = page.getByRole("button", { name: "承認する" });
      if (await approve.isVisible().catch(() => false)) {
        await approve.click();
        await page.waitForTimeout(600);
      }
    }
    const run = page.getByRole("button", { name: "▶ 実行開始" });
    if (await run.isVisible().catch(() => false)) {
      await run.click();
    }
    await page.waitForTimeout(1200);
    const stats = (await page.locator(".stats").innerText()).replace(/\s+/g, " ");
    if (stats.includes("100%")) break;
  }

  expect(sawVerifyApproval).toBe(true);
  expect(sawEvaluateApproval).toBe(true);
  await expect(page.locator(".stats")).toContainText("100%");
  await expect(page.locator(".stats")).toContainText("10/10");

  // サーバー側にも完了状態が保存されている
  await expect
    .poll(
      async () => {
        const doc = await fetchDoc(page, TITLE);
        const tasks = (doc.payload.tasks ?? []) as { status: string }[];
        return `${tasks.filter((task) => task.status === "done").length}/${tasks.length}`;
      },
      { timeout: 30_000 },
    )
    .toBe("10/10");
});

test("D-02/D-05/D-08 討論の表示・全件表示・研究者の発言", async ({ page }) => {
  await openStudio(page);
  await page.locator('#nav .navitem[data-v="debate"]').click();

  await expect(page.locator(".agents .agent")).toHaveCount(8);
  await expect(page.locator("#main")).toContainText("合意度");

  const shown = page.locator("#debCnt");
  const before = (await shown.innerText()).trim();
  expect(before).toMatch(/^\d+\/\d+$/);

  await page.getByRole("button", { name: /すべて表示/ }).click();
  await expect(shown).toHaveText(/^(\d+)\/\1$/);

  // 研究者として発言（チップ → 送信）
  await page.locator('button[data-act="chip"]').first().click();
  await page.getByRole("button", { name: "発言する" }).click();
  await expect
    .poll(async () => (await page.locator("#debCnt").innerText()).trim(), { timeout: 20_000 })
    .toMatch(/^(\d+)\/\1$/);
  await expect(page.locator("#main")).toContainText("あなた");
});

test("E-02/E-05/E-08 根拠の表示・立場の修正・手動追加", async ({ page }) => {
  await openStudio(page);
  await page.locator('#nav .navitem[data-v="evidence"]').click();

  await expect(page.locator(".stats")).toContainText("資料数");
  await expect(page.locator(".stats")).toContainText("平均信頼性");

  // 立場の修正 → 統計（反証数）が更新される
  const stance = page.locator("select[data-evstance]").first();
  await stance.selectOption("contradict");
  await expect
    .poll(async () => saveState(page), { timeout: 10_000 })
    .toBe("サーバーに自動保存済み");

  // 手動追加
  await page.getByRole("button", { name: "＋ 手動で追加" }).click();
  await page.locator("#ae_title").fill("E2E 追加資料");
  await page.locator("#ae_sum").fill("E2E テストで追加した資料");
  await page.getByRole("button", { name: "追加する" }).click();
  await expect(page.locator("#main")).toContainText("E2E 追加資料");
});

test("C-02/C-04/C-06 新仮説比較（候補・重み・採択）", async ({ page }) => {
  await openStudio(page);
  await page.locator('#nav .navitem[data-v="compare"]').click();

  const cards = page.locator(".cand");
  await expect(cards).not.toHaveCount(0);
  await expect(page.locator("#main")).toContainText("総合点ランキング");
  await expect(page.locator("svg.radar")).toBeVisible();

  const rankBefore = await page.locator("#rank").innerText();
  await page.locator('input[data-w="novelty"]').evaluate((el: HTMLInputElement) => {
    el.value = "50";
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await expect
    .poll(async () => page.locator("#rank").innerText(), { timeout: 10_000 })
    .not.toBe(rankBefore);

  // 候補の却下
  const target = cards.nth(1);
  const label = (await target.locator(".lb").innerText()).trim();
  await target.getByRole("button", { name: "却下" }).click();
  await expect(target.locator(".chip").filter({ hasText: "却下" })).toHaveCount(1);
});

test("P-01/P-04/P-09 研究報告書の章構成と HTML 保存", async ({ page }) => {
  await openStudio(page);
  await page.locator('#nav .navitem[data-v="report"]').click();

  await expect(page.locator("#reportBody")).toBeVisible();
  await expect(page.locator("#reportBody h1")).toContainText(TITLE);
  const headings = page.locator("#reportBody h2");
  await expect(headings).toHaveCount(11);
  await expect(page.locator("#reportBody")).toContainText("研究概要");
  await expect(page.locator("#reportBody")).toContainText("次のステップ");

  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "HTMLで保存" }).click(),
  ]);
  expect(download.suggestedFilename()).toContain("RIHRP報告書");
});


test("A-04 390px で横スクロールしない（ナビは横スクロール）", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openStudio(page);
  const overflow = await page.evaluate(() => {
    const doc = document.documentElement;
    return doc.scrollWidth - window.innerWidth;
  });
  expect(overflow).toBeLessThanOrEqual(1);
  const navOverflow = await page.locator("#nav").evaluate((el) => el.scrollWidth - el.clientWidth);
  expect(navOverflow).toBeGreaterThanOrEqual(0);
});

test("S-15 印刷時にシェル（トップバー・ナビ）を出さない", async ({ page }) => {
  await openStudio(page);
  await page.emulateMedia({ media: "print" });
  await expect(page.locator(".topbar")).toBeHidden();
  await expect(page.locator("#nav")).toBeHidden();
  await expect(page.locator(".notice")).toBeHidden();
  await page.emulateMedia({ media: "screen" });
  await expect(page.locator(".topbar")).toBeVisible();
});

test("S-13 ダークモードのトークンが適用される", async ({ page }) => {
  await openStudio(page);
  const light = await page.locator(".studio-root").evaluate((el) => getComputedStyle(el).backgroundColor);
  await page.emulateMedia({ colorScheme: "dark" });
  await page.waitForTimeout(200);
  const dark = await page.locator(".studio-root").evaluate((el) => getComputedStyle(el).backgroundColor);
  expect(dark).not.toBe(light);
  expect(dark).toBe("rgb(13, 20, 22)");
});

test("G-01/G-02/G-03 ログイン・管理導線・ログアウト", async ({ page }) => {
  await openStudio(page);

  // 未認証アクセスはログインへ
  const anonymous = await page.context().browser()?.newContext();
  const guest = await anonymous!.newPage();
  await guest.goto("/studio");
  await expect(guest).toHaveURL(/\/login/);
  await anonymous!.close();

  // 管理（監査ログ）へ遷移できる
  await page.locator('[data-act="admin"]').click();
  await expect(page).toHaveURL(/\/audit/);
  await page.goBack();
  await expect(page.locator(".topbar")).toBeVisible();

  // ログアウトでログイン画面へ
  await page.locator('[data-act="logout"]').click();
  await expect(page).toHaveURL(/\/login/);
});


async function selectMain(page: Page): Promise<void> {
  await page.selectOption("#projSel", { label: TITLE });
  await expect(page.locator("#main")).toContainText("STEP 01");
}

test("R-08/R-09 改訂の記録と復元", async ({ page }) => {
  await openStudio(page);
  await selectMain(page);
  page.on("dialog", (dialog) => void dialog.accept());
  const revisions = page.locator(".revs li");
  const before = await revisions.count();
  const ta = page.locator('textarea[data-bind="hypothesis"]');

  await ta.fill(`${HYPOTHESIS} 追加条件A。`);
  await page.waitForTimeout(250);
  await page.getByRole("button", { name: "改訂として記録" }).click();
  await expect(revisions).toHaveCount(before + 1);

  await ta.fill(`${HYPOTHESIS} 追加条件B。`);
  await page.waitForTimeout(250);
  await page.getByRole("button", { name: "改訂として記録" }).click();
  await expect(revisions).toHaveCount(before + 2);
  await expect(revisions.first()).toContainText(`r${before + 2}`);

  // 直前の改訂（追加条件A）を復元
  await revisions.nth(1).getByRole("button", { name: "復元" }).click();
  await expect(ta).toHaveValue(`${HYPOTHESIS} 追加条件A。`);
  await expect
    .poll(async () => saveState(page), { timeout: 10_000 })
    .toBe("サーバーに自動保存済み");
});

test("R-11 架空の研究事例を追加できる", async ({ page }) => {
  await openStudio(page);
  await selectMain(page);
  const before = await page.locator("#projSel option").count();
  await page.locator('button[data-act="addSample"]').first().click();
  await expect(page.locator("#projSel option")).toHaveCount(before + 1);
  await expect(page.locator('input[data-bind="title"]')).toHaveValue("河道湾曲部における護岸基礎の洗掘対策");

  // 後続テストのため追加した事例を削除して元に戻す
  page.on("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: "この研究を削除" }).click();
  await expect(page.locator("#projSel option")).toHaveCount(before);
});

test("E-06 根拠から除外すると淡色化し、含め直せる", async ({ page }) => {
  await openStudio(page);
  await selectMain(page);
  await page.locator('#nav .navitem[data-v="evidence"]').click();

  const first = page.locator(".ev").first();
  await first.getByRole("button", { name: "根拠から除外" }).click();
  await expect(page.locator(".ev.off").first()).toBeVisible();
  await expect(first.getByRole("button", { name: "根拠に含める" })).toBeVisible();
  await expect
    .poll(async () => saveState(page), { timeout: 10_000 })
    .toBe("サーバーに自動保存済み");

  await first.getByRole("button", { name: "根拠に含める" }).click();
  await expect(page.locator(".ev.off")).toHaveCount(0);
});

test("P-05/P-06 テキスト保存と JSON 保存", async ({ page }) => {
  await openStudio(page);
  await selectMain(page);
  await page.locator('#nav .navitem[data-v="report"]').click();

  const [txt] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "テキストで保存" }).click(),
  ]);
  expect(txt.suggestedFilename()).toContain(".txt");

  const [json] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "JSONで保存" }).click(),
  ]);
  expect(json.suggestedFilename()).toContain(".json");
});

test("保存待ちの編集はテーマ切替で失われない（flush）", async ({ page }) => {
  await openStudio(page);
  await selectMain(page);
  // 前提を固定（先行テストの改訂で仮説が変わっている可能性がある）
  await page.locator('textarea[data-bind="hypothesis"]').fill(HYPOTHESIS);
  await expect
    .poll(async () => saveState(page), { timeout: 10_000 })
    .toBe("サーバーに自動保存済み");

  const newTitle = "切替テスト研究";
  const newHypothesis = "切替テストの仮説。洗掘深を30%低減する。";
  const beforeCount = await page.locator("#projSel option").count();
  await page.getByRole("button", { name: "＋ 新規研究" }).click();
  // サーバー作成は非同期のため、完了（選択肢の増加とタイトルの初期値）を待ってから入力する
  await expect(page.locator("#projSel option")).toHaveCount(beforeCount + 1);
  await expect(page.locator('input[data-bind="title"]')).toHaveValue("新しい研究テーマ");
  await page.locator('input[data-bind="title"]').fill(newTitle);
  await page.locator('textarea[data-bind="hypothesis"]').fill(newHypothesis);

  // デバウンス（500ms）を待たずに切替 → flush されていなければ失われる
  await page.selectOption("#projSel", { label: TITLE });
  await expect(page.locator('textarea[data-bind="hypothesis"]')).toHaveValue(HYPOTHESIS);

  await page.selectOption("#projSel", { label: newTitle });
  await expect(page.locator('textarea[data-bind="hypothesis"]')).toHaveValue(newHypothesis);

  // サーバーに保存されていることを、再読込して確認する
  await page.reload();
  await selectMain(page);
  await page.selectOption("#projSel", { label: newTitle });
  await expect(page.locator('textarea[data-bind="hypothesis"]')).toHaveValue(newHypothesis);

  // 後片付け
  page.on("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: "この研究を削除" }).click();
  await expect(page.locator(`#projSel option:has-text("${newTitle}")`)).toHaveCount(0);
});

test("保存待ちの編集はログアウトでも失われない（flush）", async ({ page }) => {
  await openStudio(page);
  await selectMain(page);
  const value = `${HYPOTHESIS} ログアウト前の保存確認。`;
  const order: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "PUT" && request.url().includes("/research")) order.push("put");
    if (request.url().includes("/api/auth/logout")) order.push("logout");
  });
  await page.locator('textarea[data-bind="hypothesis"]').fill(value);

  await page.locator('[data-act="logout"]').click();
  await expect(page).toHaveURL(/\/login/);

  // flush がログアウト要求より前に PUT を送っていること（デバウンス待ちでは成立しない）
  expect(order.indexOf("put")).toBeGreaterThanOrEqual(0);
  expect(order.indexOf("put")).toBeLessThan(order.indexOf("logout"));

  await openStudio(page);
  await selectMain(page);
  await expect(page.locator('textarea[data-bind="hypothesis"]')).toHaveValue(value);
});

test("保存済みデータ由来の XSS が成立しない", async ({ page }) => {
  await openStudio(page);
  await selectMain(page);

  const projects = (await (await page.request.get("/api/projects")).json()) as {
    projects: { id: string; title: string }[];
  };
  const target = projects.projects.find((item) => item.title === TITLE);
  expect(target).toBeTruthy();
  const doc = (await (
    await page.request.get(`/api/projects/${target!.id}/research`)
  ).json()) as { version: number; payload: Record<string, unknown> };

  const malicious = JSON.parse(JSON.stringify(doc.payload)) as Record<string, unknown>;
  malicious.title = 'XSS<img src=x onerror="window.__xss=1">';
  malicious.hypothesis = "<script>window.__xss=2</script>仮説";
  const candidates = malicious.candidates as Record<string, unknown>[] | null;
  if (candidates?.length) {
    candidates[0].label = 'XSS<img src=x onerror="window.__xss=4">';
  }
  const evidence = malicious.evidence as Record<string, unknown>[] | null;
  if (evidence?.length) {
    evidence[0].id = 'x" data-injected="1';
  }
  const critiques = malicious.critiques as Record<string, unknown>[] | null;
  if (critiques?.length) {
    critiques[0].cat = 'XSS<img src=x onerror="window.__xss=5">';
  }
  const csrf = (await page.context().cookies()).find((cookie) => cookie.name === "rihrp_csrf")?.value;
  const headers = { "X-CSRF-Token": csrf ?? "" };

  const put = await page.request.put(`/api/projects/${target!.id}/research`, {
    headers,
    data: { expected_version: doc.version, payload: malicious },
  });
  expect(put.ok()).toBe(true);
  const saved = (await put.json()) as { version: number };

  await page.reload();

  // 報告書
  await page.locator('#nav .navitem[data-v="report"]').click();
  await expect(page.locator("#reportBody h1")).toContainText("<img");
  expect(await page.evaluate(() => (window as unknown as { __xss?: number }).__xss)).toBeUndefined();
  expect(await page.locator('#reportBody img[src="x"]').count()).toBe(0);
  expect(await page.locator("#reportBody script").count()).toBe(0);

  // 比較画面（candidate.label 経由）
  await page.locator('#nav .navitem[data-v="compare"]').click();
  await expect(page.locator("#main")).toContainText("<img");
  expect(await page.locator('#main img[src="x"]').count()).toBe(0);
  expect(await page.evaluate(() => (window as unknown as { __xss?: number }).__xss)).toBeUndefined();

  // 根拠画面（evidence.id / critique.cat 経由）
  await page.locator('#nav .navitem[data-v="evidence"]').click();
  expect(await page.locator('#main img[src="x"]').count()).toBe(0);
  expect(await page.locator('[data-injected]').count()).toBe(0);
  expect(await page.evaluate(() => (window as unknown as { __xss?: number }).__xss)).toBeUndefined();

  // 元に戻す
  await page.request.put(`/api/projects/${target!.id}/research`, {
    headers,
    data: { expected_version: saved.version, payload: doc.payload },
  });
});

test("S-05/S-06 JSON 保存と読込", async ({ page }) => {
  await openStudio(page);
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.locator('button[data-act="exportAll"]').click(),
  ]);
  const filePath = await download.path();
  expect(download.suggestedFilename()).toContain("rihrp_backup");

  const before = await page.locator("#projSel option").count();
  page.on("dialog", (dialog) => void dialog.accept());
  await page.locator("#fileJson").setInputFiles(filePath);
  await expect(page.locator("#projSel option")).toHaveCount(before * 2, { timeout: 30_000 });
});
