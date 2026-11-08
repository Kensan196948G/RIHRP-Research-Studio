/**
 * 品質ゲート補完: 既存 E2E が直接カバーしていない UI ケース。
 * 検索・絞り込み・loading/empty/error・複数タブ競合・900px を実測する。
 */
import { expect, test, type Page } from "@playwright/test";

const EMAIL = "admin@e2e.local";
const PASSWORD = "e2e-password-123";

async function login(page: Page, email = EMAIL, password = PASSWORD): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("メールアドレス").fill(email);
  await page.getByLabel("パスワード").fill(password);
  await page.getByRole("button", { name: "サインイン", exact: true }).click();
  await expect(page.locator(".topbar")).toBeVisible();
}

async function csrf(page: Page): Promise<string> {
  const value = (await page.context().cookies()).find((c) => c.name === "rihrp_csrf")?.value;
  if (!value) throw new Error("CSRF cookie がありません");
  return value;
}

async function api(page: Page, method: string, path: string, data?: unknown) {
  const headers: Record<string, string> = { "X-CSRF-Token": await csrf(page) };
  const response = await page.request.fetch(path, { method, headers, data });
  if (!response.ok()) throw new Error(`${method} ${path} -> ${response.status()}`);
  return response.json();
}

async function createProject(page: Page, title: string): Promise<string> {
  const body = await api(page, "POST", "/api/projects", { title, summary: "" });
  return body.project.id as string;
}

/** Studio の初回表示で自動作成されたテーマも含め、全テーマを削除して空状態を作る。 */
async function clearProjects(page: Page): Promise<void> {
  const body = (await (await page.request.get("/api/projects")).json()) as {
    projects: { id: string }[];
  };
  for (const project of body.projects) {
    await api(page, "DELETE", `/api/projects/${project.id}`);
  }
}

async function createClaim(
  page: Page,
  projectId: string,
  text: string,
  sourceId: string,
  quote = "",
): Promise<Record<string, unknown>> {
  const body = await api(page, "POST", `/api/projects/${projectId}/claims`, { text });
  const claim = body.claim as Record<string, unknown>;
  await api(page, "POST", `/api/claims/${claim.id}/evidence`, {
    source_id: sourceId,
    quote,
    note: "",
  });
  await api(page, "POST", `/api/claims/${claim.id}/verify`);
  return claim;
}

test.describe.configure({ mode: "serial" });

test("ダッシュボード復活: ナビから /dashboard に到達できる", async ({ page }) => {
  await login(page);
  // ログイン直後の既定画面は従来どおり Studio のまま
  await expect(page).toHaveURL(/\/studio$/);
  await page.goto("/settings");
  const dashboardLink = page.getByRole("link", { name: "ダッシュボード" });
  await expect(dashboardLink).toHaveAttribute("href", "/dashboard");
  await dashboardLink.click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { name: "ダッシュボード" })).toBeVisible();
});

test("tc_mw7pqh83 ダッシュボードの loading / empty / error と再試行", async ({ page }) => {
  await login(page);
  await clearProjects(page);
  await page.goto("/dashboard");
  await expect(page.getByText("テーマがまだありません")).toBeVisible();

  // loading（API を遅延）
  await page.route("**/api/projects", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 2500));
    await route.continue().catch(() => undefined);
  });
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByRole("status")).toContainText("テーマを読み込んでいます");
  await page.unroute("**/api/projects");
  await expect(page.getByText("テーマがまだありません")).toBeVisible();

  // error（API 500）→ 再試行で復帰
  await page.route("**/api/projects", (route) =>
    route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "internal_error", message: "サーバー内部エラー" } }),
    }),
  );
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByRole("alert")).toContainText("サーバー内部エラー");
  await page.unroute("**/api/projects");
  await page.getByRole("button", { name: "再試行" }).click();
  await expect(page.getByText("テーマがまだありません")).toBeVisible();
});

test("tc_mw7pmf4c テーマ検索（1 件 / 0 件 / クリア）", async ({ page }) => {
  await login(page);
  await clearProjects(page);
  await createProject(page, "Alpha 河川研究");
  await createProject(page, "Beta 海岸研究");
  await page.goto("/dashboard");
  const rows = page.locator(".dashboard-table tbody tr");
  await expect(rows).toHaveCount(2);

  const search = page.getByLabel("テーマを検索");
  await search.fill("Alpha");
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText("Alpha");

  await search.fill("存在しないテーマ");
  await expect(page.getByText("該当するテーマがありません")).toBeVisible();

  await search.fill("");
  await expect(rows).toHaveCount(2);
});

test("tc_mw7pmf52 最近の活動は reviewer / admin のみ表示され監査と一致する", async ({ page, browser }) => {
  await login(page);
  await api(page, "POST", "/api/users", {
    email: "reviewer-dash@e2e.local",
    name: "reviewer dash",
    role: "reviewer",
    password: "reviewer-password-123",
  });
  await api(page, "POST", "/api/users", {
    email: "editor-dash@e2e.local",
    name: "editor dash",
    role: "editor",
    password: "editor-password-123",
  });

  const reviewerContext = await browser.newContext();
  const reviewerPage = await reviewerContext.newPage();
  await login(reviewerPage, "reviewer-dash@e2e.local", "reviewer-password-123");
  await reviewerPage.goto("/dashboard");
  await expect(reviewerPage.getByRole("heading", { name: "最近の活動" })).toBeVisible();
  const events = (await (await reviewerPage.request.get("/api/audit?limit=6")).json()) as {
    events: unknown[];
  };
  const items = reviewerPage.locator(".card", { hasText: "最近の活動" }).locator("li");
  await expect(items).toHaveCount(Math.min(events.events.length, 6));
  await reviewerContext.close();

  const editorContext = await browser.newContext();
  const editorPage = await editorContext.newPage();
  await login(editorPage, "editor-dash@e2e.local", "editor-password-123");
  await editorPage.goto("/dashboard");
  await expect(editorPage.getByRole("heading", { name: "最近の活動" })).toHaveCount(0);
  await editorContext.close();
});

test("tc_mw7pmf4n 主張の判定フィルタと本文検索", async ({ page }) => {
  await login(page);
  const projectId = await createProject(page, "主張フィルタ検証");
  const source = await api(page, "POST", `/api/projects/${projectId}/sources`, {
    title: "出典",
    kind: "text",
    origin: "",
    content: "基準は 50 cm、50%、1,000 件、3.5 m である。",
  });
  const sourceId = (source.source as Record<string, unknown>).id as string;
  await createClaim(page, projectId, "しきい値は 50 cm を超える。", sourceId);
  await createClaim(page, projectId, "しきい値は 1000 件を超える。", sourceId);
  await createClaim(page, projectId, "根拠のない主張をここに置く。", sourceId, "");

  await page.goto(`/projects/${projectId}?tab=claims`);
  await expect(page.getByText("3 / 3 件")).toBeVisible();

  const filter = page.getByLabel("判定で絞り込み");
  await filter.selectOption("verified");
  await expect(page.getByText("1 / 3 件")).toBeVisible();
  await expect(page.locator(".claims-table")).toContainText("しきい値は 50 cm");

  await filter.selectOption("unverified");
  await expect(page.getByText("1 / 3 件")).toBeVisible();
  await expect(page.locator(".claims-table")).toContainText("1000 件");

  await filter.selectOption("all");
  const search = page.getByLabel("主張を検索");
  await search.fill("1000");
  await expect(page.getByText("1 / 3 件")).toBeVisible();
  await expect(page.locator(".claims-table")).toContainText("1000 件");
  await expect(page.locator(".claims-table")).not.toContainText("50 cm を超える");
});

test("tc_mw7pqh83（部分）テーマ詳細の loading / empty / error と再試行", async ({ page }) => {
  await login(page);
  const projectId = await createProject(page, "状態表示検証");
  const emptyProjectId = await createProject(page, "空テーマ");

  // loading
  const detail = new RegExp(`/api/projects/${projectId}$`);
  await page.route(detail, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    await route.continue().catch(() => undefined);
  });
  await page.goto(`/projects/${projectId}`, { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("status")).toContainText("テーマを読み込んでいます");
  await page.unroute(detail);
  await expect(page.locator(".tabs")).toBeVisible();

  // error → 再試行で復帰
  await page.route(detail, (route) =>
    route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "internal_error", message: "取得に失敗しました" } }),
    }),
  );
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByRole("alert")).toContainText("取得に失敗しました");
  await page.unroute(detail);
  await page.getByRole("button", { name: "再試行" }).click();
  await expect(page.locator(".tabs")).toBeVisible();

  // empty（主張 0 件のテーマ詳細）
  await page.goto(`/projects/${emptyProjectId}?tab=claims`);
  await expect(page.getByText("主張がまだありません")).toBeVisible();
});

test("tc_mw7pqh9k 複数タブ同時編集で 409 を検知し再読込で復帰", async ({ page, context }) => {
  await login(page);
  await clearProjects(page);
  await page.goto("/studio");
  await page.locator('input[data-bind="title"]').fill("マルチタブ検証");
  await page.locator('textarea[data-bind="hypothesis"]').fill("最初の仮説です。十分な長さがあります。");
  await expect
    .poll(async () => (await page.locator("#saveState").innerText()).trim(), { timeout: 10_000 })
    .toBe("サーバーに自動保存済み");

  const second = await context.newPage();
  await second.goto("/studio");
  await expect(second.locator('input[data-bind="title"]')).toHaveValue("マルチタブ検証");

  const projects = (await (await page.request.get("/api/projects")).json()) as {
    projects: { id: string; title: string }[];
  };
  const projectId = projects.projects.find((item) => item.title === "マルチタブ検証")?.id;
  if (!projectId) throw new Error("マルチタブ検証のプロジェクトが見つかりません");

  // タブ A が先に保存して version を進める（保存状態は既に「保存済み」なので version を直接確認）
  await page.locator('textarea[data-bind="hypothesis"]').fill("タブAが保存した仮説です。十分な長さがあります。");
  await expect
    .poll(async () => {
      const doc = (await (await page.request.get(`/api/projects/${projectId}/research`)).json()) as {
        version: number;
      };
      return doc.version;
    }, { timeout: 10_000 })
    .toBe(2);

  // タブ B は古い version のまま保存 → 409 → 再読込で最新（タブ A）の内容に復帰
  const conflict = second.waitForResponse(
    (response) =>
      response.url().includes(`/api/projects/${projectId}/research`) &&
      response.request().method() === "PUT" &&
      response.status() === 409,
    { timeout: 10_000 },
  );
  await second.locator('textarea[data-bind="hypothesis"]').fill("タブBが保存した仮説です。十分な長さがあります。");
  await conflict;
  await expect(second.locator('textarea[data-bind="hypothesis"]')).toHaveValue(
    "タブAが保存した仮説です。十分な長さがあります。",
    { timeout: 15_000 },
  );
  await second.close();
});

test("tc_mw7pjyc4（部分）900px で横スクロールなし・アイコンレール", async ({ page }) => {
  await login(page);
  const projectId = await createProject(page, "900px レイアウト検証");
  await page.setViewportSize({ width: 900, height: 900 });
  await page.goto(`/projects/${projectId}`);
  const layout = await page.locator(".app-shell").evaluate((element) => {
    const style = getComputedStyle(element);
    return { columns: style.gridTemplateColumns, scrollWidth: document.documentElement.scrollWidth };
  });
  const contentWidth = await page
    .locator(".content")
    .evaluate((element) => element.getBoundingClientRect().width);
  expect(layout.columns.split(" ").length).toBe(2);
  expect(layout.scrollWidth).toBeLessThanOrEqual(900);
  expect(contentWidth).toBeLessThanOrEqual(900);

  // 実装は 900px 以下でラベルを視覚的に隠したアイコンレールになる（ケースの「横スクロール」とは表示形式が異なる）。
  // ラベルは display: none ではなく visually hidden で DOM に残し、読み上げ名を維持する（DEF-2）。
  const navLabel = page.locator(".sidebar .nav-label").first();
  const labelBox = await navLabel.boundingBox();
  expect(labelBox?.width ?? 0).toBeLessThanOrEqual(1);
  expect(labelBox?.height ?? 0).toBeLessThanOrEqual(1);
  await expect(page.locator(".sidebar nav a.nav-link").first()).toHaveAccessibleName("ダッシュボード");
});
