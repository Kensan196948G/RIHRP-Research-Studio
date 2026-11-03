# CI への E2E ジョブ追加（提案・要人間適用）

AI は `.github/workflows/**` を変更できない（self-evolution ポリシーで DEPLOY 扱い）。
以下を人間が `.github/workflows/e2e.yml` として追加し、PR でレビューしてください。

- 起動条件は `workflow_dispatch` のみ（通常の PR / push では走らない）
- 既存 CI の必須チェックには含めない（ブランチ保護は変更しない）
- PostgreSQL 16 サービス + ロール分離 + `.venv` 作成 + `npm ci` / `npm run build` + Chromium

```yaml
name: E2E (manual)

on:
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: e2e-${{ github.ref }}
  cancel-in-progress: true

jobs:
  e2e:
    name: Playwright (studio)
    runs-on: ubuntu-latest
    timeout-minutes: 30
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: ci-postgres
          POSTGRES_DB: postgres
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U postgres"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
    env:
      RIHRP_ENV: development
      RIHRP_DATABASE_URL: postgresql+psycopg://rihrp_app:ci-password@127.0.0.1:5432/rihrp_test
      RIHRP_TEST_DATABASE_URL: postgresql+psycopg://rihrp_app:ci-password@127.0.0.1:5432/rihrp_test
      RIHRP_MIGRATION_DATABASE_URL: postgresql+psycopg://rihrp_owner:ci-owner@127.0.0.1:5432/rihrp_test
      RIHRP_COOKIE_SECURE: "false"
      RIHRP_TRUST_CF_ACCESS: "false"
      RIHRP_SEED_DEMO: "false"
      PGPASSWORD: ci-postgres
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: npm
          cache-dependency-path: apps/web/package-lock.json
      - name: Create roles and test database (owner/app separation)
        run: |
          psql -h 127.0.0.1 -U postgres -d postgres <<'SQL'
          CREATE ROLE rihrp_owner LOGIN PASSWORD 'ci-owner';
          CREATE ROLE rihrp_app LOGIN PASSWORD 'ci-password';
          CREATE DATABASE rihrp_test OWNER rihrp_owner;
          SQL
          psql -h 127.0.0.1 -U postgres -d rihrp_test <<'SQL'
          GRANT USAGE ON SCHEMA public TO rihrp_app;
          ALTER DEFAULT PRIVILEGES FOR ROLE rihrp_owner IN SCHEMA public
            GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO rihrp_app;
          ALTER DEFAULT PRIVILEGES FOR ROLE rihrp_owner IN SCHEMA public
            GRANT USAGE, SELECT ON SEQUENCES TO rihrp_app;
          SQL
      - name: Install Python dependencies
        run: |
          python -m venv .venv
          .venv/bin/pip install -q -e ".[dev]"
      - name: Install web dependencies and build
        working-directory: apps/web
        run: |
          npm ci
          npm run build
      - name: Install Playwright Chromium
        working-directory: apps/web
        run: npx playwright install --with-deps chromium
      - name: Run E2E
        working-directory: apps/web
        run: npx playwright test
      - name: Upload Playwright report
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report
          path: apps/web/test-results
          retention-days: 7
```

## 人間が行う手順

1. `.github/workflows/e2e.yml` を上記内容で追加（またはブランチへコミット）。
2. PR を作成し、CI が緑になることを確認。
3. 必要なら PR ごとの自動実行へ変更（`pull_request` を追加し、ブランチ保護の
   required checks に `Playwright (studio)` を追加）。実行時間と課金を確認のうえ判断する。
