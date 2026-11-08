import { defineConfig, devices } from "@playwright/test";

/**
 * ダッシュボード復活後の UI ケースを、既存 dist ではなく
 * 一時ビルド（RIHRP_WEB_DIST）に対して実行するための設定。
 * webServer は外部で起動済みの 18114 を再利用する。
 */
export default defineConfig({
  testDir: "./e2e",
  testMatch: /gate-extra\.spec\.ts/,
  timeout: 180_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  globalSetup: "./e2e/global-setup.ts",
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:18114",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    locale: "ja-JP",
    timezoneId: "Asia/Tokyo",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
