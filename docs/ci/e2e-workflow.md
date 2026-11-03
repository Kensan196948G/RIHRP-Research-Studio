# CI への E2E ジョブ追加（提案・要人間適用）

AI は `.github/workflows/**` を変更できない（self-evolution ポリシーで DEPLOY 扱い）。
以下を人間が `.github/workflows/e2e.yml` として追加し、PR でレビューしてください。

- 起動条件は `workflow_dispatch` のみ（通常の PR / push では走らない）
- 既存 CI の必須チェックには含めない（ブランチ保護は変更しない）
- PostgreSQL 16 サービス + E2E 用 DB（**所有者を app ロールに一致**）+ `.venv` 作成 + `npm ci` / `npm run build` + Chromium

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
    timeout-minutes: 60
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
      - name: Create the E2E database (owner = app role)
        run: |
          psql -h 127.0.0.1 -U postgres -d postgres <<'SQL'
          CREATE ROLE rihrp_app LOGIN PASSWORD 'ci-password';
          CREATE DATABASE rihrp_test OWNER rihrp_app;
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
      - name: Upload Playwright traces
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-traces
          path: apps/web/test-results
          if-no-files-found: ignore
          retention-days: 7
```

## 設計上の注意（ロールと migration）

- Playwright の `globalSetup` は `tests/e2e/prepare_e2e.py` を呼び、その `migrate()` は
  `RIHRP_DATABASE_URL`（app ロール）で `alembic upgrade head` を実行する。postgres:16 では
  schema `public` の CREATE 権限が所有者にしかないため、E2E 用 DB は **app ロール
  （`rihrp_app`）が所有者**である必要がある。ローカルの `createdb -O rihrp_app rihrp_test`
  と同一の構成にしてある。
- `reset()` は app 接続で `ALTER TABLE ... DISABLE TRIGGER` と `TRUNCATE` を行うため、
  これも app ロールがテーブル所有者であることが前提になる。
- pytest 側（`.github/workflows/ci.yml`）は `RIHRP_MIGRATION_DATABASE_URL` で owner ロールを
  分離しているが、E2E の `prepare_e2e.py` は app ロールのみを使う。そのためこの workflow に
  `RIHRP_MIGRATION_DATABASE_URL` は設定しない（設定しても読まれない）。
- `reporter` は `list` のみ（HTML レポートは未生成）のため、artifact は失敗時の
  trace / screenshot を回収する目的で `playwright-traces` とする。
- 直列実行（`workers: 1`、1 テスト最大 180 秒 × 26 件）の最悪ケースを考慮して
  `timeout-minutes: 60` とする。

## 人間が行う手順

1. `.github/workflows/e2e.yml` を上記内容で追加（またはブランチへコミット）。
2. PR を作成し、CI が緑になることを確認。
3. 必要なら PR ごとの自動実行へ変更（`pull_request` を追加し、ブランチ保護の
   required checks に `Playwright (studio)` を追加）。実行時間と課金を確認のうえ判断する。
