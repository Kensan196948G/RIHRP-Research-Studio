import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * E2E の前にテスト DB（rihrp_test*）を初期化し、E2E 用の管理者を作る。
 * 本番 DB では実行されない（prepare_e2e.py が DB 名を検査する）。
 */
export default async function globalSetup(): Promise<void> {
  const repoRoot = fileURLToPath(new URL("../../..", import.meta.url));
  execFileSync(path.join(repoRoot, ".venv/bin/python"), [path.join(repoRoot, "tests/e2e/prepare_e2e.py")], {
    cwd: repoRoot,
    stdio: "inherit",
    env: process.env,
  });
}
