import { fileURLToPath } from "node:url";
import { defineConfig, devices } from "@playwright/test";

const repoRoot = fileURLToPath(new URL("../..", import.meta.url));
const PORT = Number(process.env.RIHRP_E2E_PORT ?? 18112);
const TEST_DB_URL =
  process.env.RIHRP_TEST_DATABASE_URL ??
  "postgresql+psycopg://rihrp_app:rihrp_dev_password@127.0.0.1:5432/rihrp_test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  globalSetup: "./e2e/global-setup.ts",
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    locale: "ja-JP",
    timezoneId: "Asia/Tokyo",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command:
      `RIHRP_ENV=development RIHRP_DATABASE_URL='${TEST_DB_URL}' RIHRP_SEED_DEMO=false ` +
      `RIHRP_COOKIE_SECURE=false RIHRP_TRUST_CF_ACCESS=false RIHRP_LOGIN_RATE_LIMIT=1000 ` +
      `.venv/bin/uvicorn rihrp.main:app --app-dir apps/api --host 127.0.0.1 --port ${PORT}`,
    url: `http://127.0.0.1:${PORT}/healthz`,
    cwd: repoRoot,
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
