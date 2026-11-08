/**
 * DEF-2 回帰: モバイル幅（900px 以下）のサイドバーはアイコンレールになるが、
 * ナビリンクのアクセシブル名は失わない。
 *
 * 900px 以下で `.nav-label` を display: none にするとアクセシビリティツリーから
 * ラベルが消え、リンクが無名になる（DEF-2）。ここでは visually hidden に
 * なっていることを、ロール・名前での取得と accessible name の一致で確認する。
 */
import { expect, test, type Page } from "@playwright/test";

const EMAIL = "admin@e2e.local";
const PASSWORD = "e2e-password-123";
const NAV_LABELS = ["ダッシュボード", "設定", "監査ログ", "利用者"];

async function login(page: Page): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("メールアドレス").fill(EMAIL);
  await page.getByLabel("パスワード").fill(PASSWORD);
  await page.getByRole("button", { name: "サインイン", exact: true }).click();
  await expect(page.locator(".topbar")).toBeVisible();
}

function mainNav(page: Page) {
  return page.getByRole("navigation", { name: "メインナビゲーション" });
}

test.describe("モバイル幅のナビゲーション（DEF-2）", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("390px / 393px でナビリンク 4 件がアクセシブル名を持つ", async ({ page }) => {
    await login(page);
    await page.goto("/dashboard");

    for (const width of [390, 393]) {
      await page.setViewportSize({ width, height: 844 });
      const nav = mainNav(page);
      const links = nav.getByRole("link");

      await expect(links).toHaveCount(NAV_LABELS.length);
      for (const [index, label] of NAV_LABELS.entries()) {
        // ロール + 名前で取得できる = アクセシブル名が空でない
        await expect(links.nth(index)).toHaveAccessibleName(label);
        await expect(nav.getByRole("link", { name: label, exact: true })).toBeVisible();
      }
    }
  });

  test("900px 以下ではラベルが視覚的に隠れる（アイコンレールのまま）", async ({ page }) => {
    await login(page);
    await page.goto("/dashboard");

    const firstLabel = page.locator("nav .nav-label").first();
    await expect(firstLabel).toBeAttached();

    // visually hidden（1x1 に切り抜き）で、レイアウトには寄与しない
    const box = await firstLabel.boundingBox();
    expect(box?.width ?? 0).toBeLessThanOrEqual(1);
    expect(box?.height ?? 0).toBeLessThanOrEqual(1);

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });

  test("デスクトップ幅ではラベルが表示される", async ({ page }) => {
    await login(page);
    await page.goto("/dashboard");
    await page.setViewportSize({ width: 1280, height: 900 });

    for (const label of NAV_LABELS) {
      await expect(page.locator("nav .nav-label", { hasText: label })).toBeVisible();
    }
  });
});
