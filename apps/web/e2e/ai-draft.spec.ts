/**
 * AI 下書き（生成経路）のブラウザ E2E。ADR-0006。
 * 実キーは使わず、RIHRP_E2E_LLM_BASE_URL でローカルスタブを指す。
 */
import { expect, test, type Page } from "@playwright/test";

const EMAIL = "admin@e2e.local";
const PASSWORD = "e2e-password-123";
const SOURCE_TEXT =
  "海洋再生可能エネルギー導入調査\n導入可能量は 1,240 MW と試算された。2026年度の実証事業は 3 件である。";
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

async function seed(page: Page): Promise<string> {
  const title = `AI下書きE2E-${Date.now()}`;
  const created = await api(page, "POST", "/api/projects", { title, summary: "" });
  const projectId = created.project.id as string;
  await api(page, "POST", `/api/projects/${projectId}/sources`, {
    title: "出典A",
    kind: "text",
    origin: "",
    content: SOURCE_TEXT,
  });
  return projectId;
}

test("AI 下書きは未設定時に案内する", async ({ page }) => {
  test.skip(configured, "スタブ設定済みのため未設定経路は対象外");
  await login(page);
  const projectId = await seed(page);
  await page.goto(`/projects/${projectId}?tab=claims`);
  await page.getByRole("button", { name: "AI で下書き" }).click();
  await page.getByLabel("下書きの対象出典").selectOption({ label: "出典A" });
  await page.getByRole("button", { name: "生成", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("AI 下書きは未設定です");
});

test("AI 下書きの候補を生成し、採用したものだけ登録する", async ({ page }) => {
  test.skip(!configured, "スタブ未設定のため生成経路は対象外");
  await login(page);
  const projectId = await seed(page);
  await page.goto(`/projects/${projectId}?tab=claims`);
  await page.getByRole("button", { name: "AI で下書き" }).click();
  await page.getByLabel("下書きの対象出典").selectOption({ label: "出典A" });
  await page.getByRole("button", { name: "生成", exact: true }).click();

  await expect(page.getByText("導入可能量は 1,240 MW と試算された。")).toBeVisible();
  await expect(page.getByText("引用が見つかりません")).toBeVisible();
  await expect(page.getByRole("button", { name: "採用して主張に追加" }).nth(1)).toBeDisabled();

  await page.getByRole("button", { name: "採用して主張に追加" }).first().click();
  await expect(page.getByText("主張を追加しました（根拠付き）。")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByText("導入可能量は 1,240 MW と試算された。").first()).toBeVisible();
});
