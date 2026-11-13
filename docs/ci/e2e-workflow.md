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
    timeout-minutes: 90
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
- 直列実行（`workers: 1`、1 テスト最大 180 秒 × 26 件 = 78 分）にセットアップ・
  依存導入・ビルドの時間を見込み、`timeout-minutes: 90` とする。

## 人間が行う手順

1. `.github/workflows/e2e.yml` を上記内容で追加（またはブランチへコミット）。
2. 追加後に GitHub Actions の「E2E (manual)」を **手動実行（workflow_dispatch）** し、
   緑になることを確認する。`pull_request` 起動ではないため、PR の CI では検証されない。
3. 必要なら PR ごとの自動実行へ変更（`pull_request` を追加し、ブランチ保護の
   required checks に `Playwright (studio)` を追加）。実行時間と課金を確認のうえ判断する。

## AI 討論 E2E のための LLM スタブ配線（提案・要人間適用）

AI は `.github/workflows/**` を変更できない（self-evolution ポリシーで DEPLOY 扱い）。
以下は **人間が適用する差分**の提案であり、未適用の間は討論 E2E が CI で skip される。

### 背景

- 討論 E2E（`apps/web/e2e/ai-debate.spec.ts`）は `RIHRP_E2E_LLM_BASE_URL` が未設定だと
  `test.skip` で飛ばされる（`configured = Boolean(process.env.RIHRP_E2E_LLM_BASE_URL)`）。
- ローカルでは `tests/e2e/llm_stub.py`（127.0.0.1:18130）を手動起動して
  スタブ経由で **44 passed / 1 skipped** を確認済み
  （証跡: `docs/verification/2026-11-13-ai-debate-poc/e2e-full.txt`）。
- CI ではスタブ起動ステップと env 設定がないため、討論 E2E は毎回 skip される。

### 適用する差分

`Install Playwright Chromium` の後に追加:

```yaml
      - name: Start LLM stub
        run: |
          nohup .venv/bin/python tests/e2e/llm_stub.py > /tmp/llm-stub.log 2>&1 &
          for _ in $(seq 1 30); do
            if curl -s -o /dev/null http://127.0.0.1:18130/; then
              echo "LLM stub is ready"
              exit 0
            fi
            sleep 1
          done
          echo "LLM stub did not become ready"
          cat /tmp/llm-stub.log
          exit 1
```

`Run E2E` に env を追加:

```yaml
      - name: Run E2E
        working-directory: apps/web
        env:
          RIHRP_E2E_LLM_BASE_URL: http://127.0.0.1:18130/v1
          RIHRP_E2E_LLM_KEY: stub-key
        run: npx playwright test
```

### 適用後の期待結果と注意

- 期待: `45 tests` 中 **44 passed / 1 skipped**（skip は「AI 下書きは未設定時に案内する」）。
  スタブを配線すると未設定経路の E2E は skip に変わるが、未設定時の 503 契約は
  API テスト（`test_ai_debate.py` / `test_ai_drafting.py`）で担保済み。
- スタブは本番キーを使わない。`RIHRP_E2E_LLM_KEY` はダミー。
- 適用後は `workflow_dispatch` で 1 回実行し、run id と結果を検証記録に追記して
  `docs/verification/2026-11-13-test-report-review-ai-debate.md` の条件 C3 を閉じる。

## 同一テスト DB の同時実行禁止（pytest と E2E）

- pytest（`tests/conftest.py`）と E2E（`tests/e2e/prepare_e2e.py`）は、既定でどちらも
  `rihrp_test` を使う。E2E 実行中に pytest が走ると、pytest の初期化が利用者・セッションを
  消し、E2E が **401（セッション失効）やログイン失敗**を起こす。
- 2026-11-13 の全 E2E 初回実行で実際に発生した（討論 E2E を追加した PR #50 の検証中、
  E2E 実行中に `pytest tests/integration/test_ai_debate.py` を同時実行）。
  原因はセッションログの時刻（09:36:20 / 09:36:47）と失敗時刻の一致で特定した。
- 再発防止として `tests/conftest.py` は、E2E の webServer（既定 127.0.0.1:18112、
  `RIHRP_E2E_PORT` で変更可）が起動中の場合は DB に触る前に `RuntimeError` で停止する。
- E2E 側から pytest を検知する仕組みはない。**E2E 実行中に pytest を起動しない**こと。
