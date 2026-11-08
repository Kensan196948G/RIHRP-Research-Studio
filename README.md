<div align="center">

# RIHRP Research Studio

**根拠付きリサーチスタジオ — 主張と根拠を、たどれる形で残す。**

出典をスナップショットと SHA-256 で固定し、主張を引用と数値で決定論的に検証する。
承認は「矛盾ゼロ」を条件に、未検証の残数も隠さない。

![status](https://img.shields.io/badge/status-production%20%2F%20CI%20green-0f766e) ![python](https://img.shields.io/badge/python-3.12-0f2436) ![node](https://img.shields.io/badge/node-22-0f2436) ![db](https://img.shields.io/badge/PostgreSQL-16-0f2436)

</div>

> [!IMPORTANT]
> **現在の状態（2026-11-03）:** 実装・テスト・CI・main マージ・本番公開まで完了。
> PR [#1](https://github.com/Kensan196948G/RIHRP-Research-Studio/pull/1) は **main へマージ済み**（merge commit `5e3f410`）。独立レビュー（pr-verifier）は **6 巡で合格**（critical 0 / high 0）。
> **CI（GitHub Actions）有効**: API (ruff / pytest) / Web (tsc / vitest / build) / Secret scan (gitleaks) の 3 ジョブ。
> **本番公開済み**: [research.mirai-dx-platform.com](https://research.mirai-dx-platform.com)（Cloudflare Tunnel + Access。未認証は 302）。
> **WebUI:** ルート直下の `RIHRP_Offline_Research_Studio.html`（6 ステップの研究ワークフロー）に整合させ、研究状態はサーバー（`research_documents`）へ保存。
> **本番更新（2026-11-03 22:24 JST）:** コミット別リリース **`82e6648`** へ切替済み。runtime SHA・manifest・静的asset・DB0004・認証境界を実測。local全量 **333 passed / 1 skipped**（後続追加回帰はCIで成功）/ Vitest **10** / 新release隔離E2E **29 passed** / main CI success3/3。詳細は[本番受入証跡](docs/verification/2026-11-03-production-acceptance.md)。旧checkout上配備方式は使わず、[新配備手順](docs/runbooks/immutable-release.md)に従う。認証後の本番通し実操作と実機確認は残条件。

## 01. これは何か

AI を使って調査レポートを作る場面では、次の 3 つが壊れやすい。

1. 出典と主張の紐付けが、文章の編集で失われる。
2. 「それらしいが根拠が無い」記述が通る。
3. 承認が「読んだ」の意味しか持たず、品質保証にならない。

RIHRP Research Studio は、**根拠スナップショット（内容アドレス固定）**・**決定論的検証**・**矛盾ゼロを条件とする承認**でこれを解く。

| 入力 | 出力 |
|---|---|
| 出典（URL / DOI / テキスト）、主張、引用 | 検証済みレポート（Markdown、検証マーカーと根拠付録付き） |

### 画面

| ログイン | ダッシュボード（`/dashboard`） |
|---|---|
| ![login](docs/assets/screenshots/01-login.png) | ![dashboard](docs/assets/screenshots/02-dashboard.png) |

| 主張と検証 | レポートエディタ |
|---|---|
| ![claims](docs/assets/screenshots/04-claims.png) | ![editor](docs/assets/screenshots/05-report-editor.png) |

## 02. 検証の規則（決定論）

主張の検証は LLM を使わず、次の規則だけで判定する（[ADR-0002](docs/adr/0002-deterministic-verification.md)）。

| 条件 | 判定 |
|---|---|
| 根拠が 0 件 | `insufficient` |
| スナップショットの SHA-256 が一致しない | `contradicted` |
| 引用がスナップショットに実在しない | `contradicted` |
| 主張内の数値が根拠本文に見つからない | `unverified` |
| 引用が実在し、数値もすべて実在する | `verified` |
| 引用も数値も無い | `insufficient` |

承認（`approved`）は **`contradicted = 0`** が条件。承認時に検証を再実行する。
未検証・根拠不足は承認を止めないが、件数を UI とエクスポートに残す（[ADR-0003](docs/adr/0003-approval-rule.md)）。

## 03. 構成

| 場所 | 内容 |
|---|---|
| `apps/api/rihrp/` | FastAPI（Python 3.12 / SQLAlchemy 2 / psycopg） |
| `apps/web/` | React 18 + TypeScript + Vite（ビルド成果物を API が同一オリジンで配信） |
| `infra/migrations/` | Alembic |
| `infra/db/` | DB bootstrap / backup / restore 検証 / OpenAPI 出力 |
| `infra/native/` | systemd user unit、deploy、health check |
| `tests/` | 実 PostgreSQL を使う結合テスト（`rihrp_test*` のみ） |
| `docs/` | 企画・要件・アーキテクチャ・ADR・WebUI 設計・Runbook・OpenAPI |

アーキテクチャの詳細は [docs/architecture/01-architecture.md](docs/architecture/01-architecture.md)。

## 04. 起動（ローカル）

前提: Python 3.12、Node 22、ローカル PostgreSQL 16。

```bash
# 1) DB（初回のみ）
RIHRP_DB_PASSWORD='<ローカル用パスワード>' infra/db/bootstrap.sh rihrp rihrp_app

# 2) ランタイム設定（リポジトリ外に置く。コミットしない）
mkdir -p ~/.config/rihrp
cat > ~/.config/rihrp/rihrp.conf <<'EOF'
RIHRP_ENV=development
RIHRP_DATABASE_URL=postgresql+psycopg://rihrp_app:<パスワード>@127.0.0.1:5432/rihrp
RIHRP_SEED_DEMO=true
RIHRP_COOKIE_SECURE=false
EOF

# 3) 本番配備は下記runbookのGo/No-Goを先に確認する。
# 旧deploy.shは稼働ツリーを更新するため次回コード配備には使わない。
# docs/runbooks/release.md / docs/verification/2026-11-03-production-batch1.md
```

手元で動かすだけなら:

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
(cd infra/migrations && alembic upgrade head)
(cd apps/web && npm ci && npm run build)
RIHRP_DATABASE_URL=postgresql+psycopg://rihrp_app:<パスワード>@127.0.0.1:5432/rihrp \
  .venv/bin/uvicorn rihrp.main:app --app-dir apps/api --host 127.0.0.1 --port 18110
```

- 画面: `http://127.0.0.1:18110`
- API 仕様: `docs/api/openapi.yaml`（`python infra/db/export_openapi.py` で再生成）
- ヘルス: `curl -fsS http://127.0.0.1:18110/healthz` / `readyz`

### 開発用アカウント（`RIHRP_SEED_DEMO=true` のときのみ）

| メール | 役割 |
|---|---|
| `editor@rihrp.local` | リサーチャー |
| `reviewer@rihrp.local` | レビュアー |
| `admin@rihrp.local` | 管理者 |
| `viewer@rihrp.local` | 閲覧者 |

初期パスワードは環境変数 `RIHRP_SEED_PASSWORD` で設定する（未設定ならデモ利用者は投入されない）。本番では seed を無効にする。

## 05. テスト

```bash
# テスト DB を用意（初回のみ）
createdb -O rihrp_app rihrp_test   # 接続先は RIHRP_TEST_DATABASE_URL で指定可

.venv/bin/pytest -q            # 148 passed / 1 skipped
(cd apps/web && npx vitest run) # 10 passed
.venv/bin/ruff check apps/api tests
.venv/bin/ruff format --check apps/api tests
tools/ci.sh --no-install       # CI 相当を一括実行

# 配備済み環境のスモーク（開発・プレビュー向け。秘密は環境変数）
RIHRP_BASE_URL=http://127.0.0.1:18110 \
RIHRP_SMOKE_EMAIL=... RIHRP_SMOKE_PASSWORD=... \
.venv/bin/python tests/e2e/preview_smoke.py
```

> **注意:** このスモークは Access を経由しない環境（`RIHRP_COOKIE_SECURE=false`）専用。
> 本番設定（`RIHRP_ENV=production` / `RIHRP_COOKIE_SECURE=true`）では Cookie に `Secure` が付くため `http://` では送られず 401 になる。
> また Cloudflare Access 配下の URL は `/healthz` を含めて未認証では 302 になり、スクリプトは Access の資格情報を持たないため**本番では実行できない**。
> 本番の確認は Access 認証後にブラウザで行う（自動 E2E は未対応）。

E2E（実装済み UI の通し検証。テスト DB を初期化して実行）:

```bash
cd apps/web
npm run build
npx playwright test          # 26 passed（Chromium）
```

主なテスト観点:

- 検証エンジン（引用一致 / 数値不一致 / 引用不在 / 改竄 / 根拠なし / アンカーなし）
- 主要フロー（テーマ → 出典 → 主張 → 根拠 → 検証 → レポート → 提出 → 承認 → エクスポート）
- 改竄時に承認が 409 で止まること
- CSRF 必須、viewer の書き込み拒否、提出者本人の承認拒否、差し戻しコメント必須
- 監査ログが業務操作と同時に記録され、更新・削除 API が無いこと

## 06. セキュリティ

- パスワード: Argon2id。セッションはサーバー側（DB）に保存し、Cookie は HttpOnly / SameSite=Lax / production では Secure。
- 状態変更 API は CSRF トークン（Cookie + `X-CSRF-Token`）必須。
- ログイン試行のレート制限。認証失敗の理由は統一（ユーザー存在を推測させない）。
- セキュリティヘッダー（CSP / X-Frame-Options / nosniff / Referrer-Policy）。
- 秘密情報は環境変数（リポジトリ外の設定ファイル）。`.env*` はコミットしない。
- 監査ログは append-only（更新・削除 API なし）。
- 本番は Cloudflare Access を前段に置く（`research.mirai-dx-platform.com` で稼働中）。
- **Cloudflare Access の自動ログイン**: `RIHRP_TRUST_CF_ACCESS=true` のとき、`/api/auth/access` が
  `Cf-Access-Jwt-Assertion` を RS256 署名・iss・aud・有効期限まで検証し、許可 email の利用者にアプリのセッションを発行する。
  平文の `Cf-Access-Authenticated-User-Email` は信頼しない。email allowlist・未設定時は全拒否（fail closed）。
  ループバック限定は任意の追加防御（uvicorn の proxy headers 設定に依存）。

## 07. 配備

旧 `infra/native/deploy.sh` は稼働checkoutを更新するため次回コード配備には使わない。
コミット別build/起動整合性/切替・切戻しは[新配備手順](docs/runbooks/immutable-release.md)を参照。
本番切替は同手順の隔離受入が完了してから実施する。
本番公開は Cloudflare Tunnel（`rihrp-cloudflared.service`）と Cloudflare Access で構成済み。公開 URL は `https://research.mirai-dx-platform.com`。
定期ジョブ（日次バックアップ・週次復元訓練・日次セッション削除・5 分間隔の外形チェック）は
`infra/native/install_ops_units.sh` で導入する（systemd user timer）。
手順と禁止事項は [docs/runbooks/operations.md](docs/runbooks/operations.md)、
リリース判定は [docs/runbooks/release.md](docs/runbooks/release.md) を参照。

## 08. 実装状況

| 機能 | 状態 | 根拠 |
|---|---|---|
| 認証・セッション・CSRF・RBAC | 実装済み | pytest（149 件中 148 passed / 1 skipped）、UI 実測 |
| テーマ / 出典（SHA-256）/ 主張 / 根拠 / 検証 | 実装済み | pytest、API 実測、UI 実測 |
| レポート / 版 / 検証 / 提出 / 承認 / 差し戻し | 実装済み | pytest、UI 実測（提出→承認） |
| 承認後の整合性警告（根拠変更で矛盾になった場合） | 実装済み | pytest（`test_approved_report_flags_post_approval_tamper`）、画面確認 |
| モバイル表示（カード / 表スクロール / レール非表示） | 実装済み | Playwright 実測（390px、横スクロール 0） |
| キーボード（Esc / フォーカスリング / スキップリンク） | 実装済み | Playwright 実測（2px ティール） |
| 描画エラー時のフォールバック | 実装済み | `ErrorBoundary.test.tsx` |
| 主張・テーマの編集 UI | 実装済み | UI 実測、pytest |
| レポート同時編集の競合検知（expected_version） | 実装済み | `test_report_save_rejects_stale_version` |
| 版履歴 UI | 実装済み | UI 実測 |
| 期限切れセッションの保守コマンド | 実装済み | `test_purge_sessions_removes_only_expired` |
| 設定画面（パスワード変更） | 実装済み | UI 実測、`test_change_password` |
| 管理者のロール変更・テーマ削除 | 実装済み | UI 実測、`test_admin_cannot_demote_self` |
| テーマ検索 / CLM 番号 / 最近の活動 | 実装済み | UI 実測（検索 1 件、該当なし、CLM-xxxx、reviewer/admin のみ活動表示） |
| パスワード変更時の他セッション失効 | 実装済み | `test_password_change_revokes_other_sessions` |
| 主張一覧の根拠数集約（N+1 解消） | 実装済み | `test_claim_list_reports_evidence_count` |
| 監査ログの DB レベル append-only | 実装済み | migration `0002_audit_immutable`、`test_audit_events_reject_update_and_delete` |
| 監査ログの TRUNCATE 保護（DB トリガー） | 実装済み | migration `0003_audit_truncate`、`test_audit_events_reject_update_and_delete`（TRUNCATE を含む）、`test_app_role_cannot_disable_audit_trigger`（所有者ロールでは skip） |
| 承認・主張変更の直列化（行ロック） | 実装済み | `services.py`（`SELECT … FOR UPDATE`）、`test_locking.py`（ロック後の最新行参照） |
| 主張の判定・本文フィルタ | 実装済み | UI 実測（矛盾 0 件 / 根拠不足 1 件 / 検索 1 件） |
| モーダルのフォーカストラップ | 実装済み | Playwright 実測（Tab 25 回で外に出ない） |
| エクスポートは参照主張のみ | 実装済み | `test_export_includes_only_referenced_claims` |
| 利用者無効化時のセッション失効 | 実装済み | `test_deactivated_user_sessions_are_revoked` |
| リクエスト相関 ID（監査・ヘッダー） | 実装済み | `test_audit_records_request_id_and_header` |
| レポートプレビュー（インライン CLM 表示） | 実装済み | UI 実測 |
| 依存関係の脆弱性監査 | 0 件（開発依存含む） | `npm audit`（full） / `pip-audit` / Dependabot |
| OpenDesign 設計参照との比較 | 実施済み | `docs/design/01-webui-design.md` 第 8 章 |
| Markdown エクスポート | 実装済み | pytest、API 実測 |
| 監査ログ（append-only） | 実装済み | pytest |
| ダッシュボード（`/dashboard`） / 検証結果 / 監査 / 利用者管理 | 実装済み | UI 実測（スクリーンショット）。ログイン後の既定画面は `/studio` |
| systemd 配備 / health check | 実装済み | 実測（第 10 章） |
| GitHub Actions CI | 実装済み | run `41513750337` success（API / Web / Secret scan） |
| 依存脆弱性の自動監査（週次 / PR paths / 手動） | 実装済み | `.github/workflows/dependency-audit.yml`（PR #16）。run `42374269050` success（Python / Node）。`docs/verification/2026-11-07-dependency-audit.md` |
| Cloudflare Tunnel / Access | 実装済み | `research.mirai-dx-platform.com`（未認証 302）。`docs/verification/2026-11-03.md` |
| WebUI（Offline Research Studio・6 ステップ） | 実装済み | `apps/web/src/studio/`、E2E `apps/web/e2e/studio.spec.ts`（26 件） |
| Cloudflare Access 自動ログイン（JWT 検証） | 実装済み | `tests/unit/test_cf_access.py`（25 件）、`tests/integration/test_access_login.py`（12 件）、`apps/web/src/auth.test.tsx`（4 件）、`apps/web/src/pages/Login.test.tsx`（1 件）、`docs/verification/2026-11-03-cf-access-autologin.md` |
| Dependabot アラート（脆弱性検知） | 有効 | open の critical / high = 0（dev 依存の 4 件は PR #3 で修正、再スキャン後に実測） |
| PDF / Office 取り込み、外部 URL 自動取得 | 未実装 | 将来（要件 §5 の対象外） |

## 09. 既知の問題・制約

1. **Cloudflare Access の認証後画面は人間の確認が必要**: 未認証 302 と Access 設定（アプリ・policy・DNS）は実測済みだが、OTP/SSO を通した画面確認は AI では実施できない（`docs/verification/2026-11-03.md` 第 6 章）。
2. **OpenDesign Studio の run は `failed` 表示**: 再実行で成果物（8 画面のプロトタイプ）は生成されたが、run の状態は `failed`（`od_next_next_run_claim_failed`、daemon journal に `SQLITE_BUSY_SNAPSHOT`）。成果物は `docs/design/opendesign/` に保存し、実装との差異を [docs/design/01-webui-design.md](docs/design/01-webui-design.md) 第 8 章に記載した。
3. **CI の依存脆弱性監査を追加（週次 schedule は初回発火待ち）**: `.github/workflows/dependency-audit.yml` を 2026-11-07 に追加（PR #16、main `f868ec7`）。`workflow_dispatch` の初回実行（run `42374269050`）で Python / Node 両ジョブの緑を確認した。週次 `schedule`（月曜 09:00 JST）は設定済みだが**初回発火は未確認**（次回 2026-11-09 見込み）。**未設定**: `.github/dependabot.yml`（依存更新 PR の自動化）、失敗時の通知先、required checks への追加。`.github/workflows/**` は self-evolution ポリシーで DEPLOY（critical）扱いのため AI は書き込めず、適用は人間が行った（2026-11-07 実測）。詳細は [docs/ci/dependency-audit.md](docs/ci/dependency-audit.md) と [検証記録](docs/verification/2026-11-07-dependency-audit.md)。
4. **マージ方法**: PR #1 は人間の操作で **merge commit**（`5e3f410`）としてマージされた。以後の通常 PR は `claude-automerge merge`（`--auto --squash`）を使う。`feat/mvp` リモートブランチは残存（AI は `git push --delete` 不可）。
5. **外部 URL の自動取得なし**: URL は識別子として保存し、本文は貼付を正とする（改竄検出の単純化）。
6. **モバイル実機・スクリーンリーダーの検証未実施**（CSS / ARIA の実装のみ）。
7. **SSO は未実装**: 認証基盤が提供されていないため（要件 §5 の対象外）。
8. **外部合成監視と通知先は未設定**: 同一ホストの 5 分間隔チェック（`rihrp-healthcheck.timer`）と失敗記録は実装済み。別ホストからの外形監視とアラート配信先（`RIHRP_ALERT_WEBHOOK`）は未設定。
9. **監査ログ保持365日・削除タイマー有効**: [ADR-0006](docs/adr/0006-audit-retention.md)の方針に基づき既存承認後に有効化済み（2026-11-03再確認）。インストーラは既定で無効、CLIはdry-run既定。現在の運用は[本番準備記録](docs/verification/2026-11-03-production-batch1.md)を参照。
10. **旧方式で配備しない**: checkout上ビルド方式の混在リスクを避け、別リリース構築・整合性検証・切替/切戻し方式へ移行済み。[リリース判定](docs/runbooks/release.md)と[受入証跡](docs/verification/2026-11-03-production-acceptance.md)の残条件を確認する。

## 10. 検証記録

### 2026-11-07 依存脆弱性監査ワークフロー（最新）

- `.github/workflows/dependency-audit.yml` を追加（PR #16、squash `f868ec7`）。
  週次 `schedule`（月曜 09:00 JST）+ `workflow_dispatch` + `pull_request`（依存ファイルの paths 限定）。
- 実 CI 検証: PR 上 run `42373686405`、main 初回 run `42374269050` がいずれも success。
  CI ログで Python 本番 34 パッケージの監査を確認（dev extras 46 パッケージは同一 lockfile に対する
  ローカル実測）、Node 本番・全依存とも 0 vulnerabilities。
- 適用理由・設計判断は [docs/ci/dependency-audit.md](docs/ci/dependency-audit.md)、
  証跡は [docs/verification/2026-11-07-dependency-audit.md](docs/verification/2026-11-07-dependency-audit.md)。

### 2026-11-03 本番準備 第1組

- 本番health/readiness正常、migration0004、許可2名、5timer enabled/active。新規バックアップを隔離DBへ復元し11表件数・SHA一致を確認。
- 事前検査CLIを追加（SHA/clean/バックアップ完全性）。CI成功・runtime SHA・配備許可そのものの証明ではない。
- 全量180 passed/1 skipped、Vitest10、E2E29。PRレビュー後の追加回帰を含むpreflight単体33 passed。
- 詳細と次の10項目: [本番準備記録](docs/verification/2026-11-03-production-batch1.md)。過去の配備記録は以下に履歴として保持する。

### 2026-11-03 初期リリース・準備の履歴

- 独立レビュー（pr-verifier）: **6 巡で合格**（critical 0 / high 0 / medium 0 / low 0）。各巡の件数は [`2026-11-03-reviews.json`](docs/verification/2026-11-03-reviews.json)。主な対応は、監査ログの TRUNCATE 保護と DB ロール分離、承認と主張変更の直列化（`SELECT … FOR UPDATE`）、ロック後の identity map 更新、project 削除と子作成の直列化、数値境界判定。
- CI（GitHub Actions）: run `41513750337`（head `6446935`）と main push の run `41533037024`（`5e3f410`）がいずれも **success 3/3**（API (ruff / pytest) / Web (tsc / vitest / build) / Secret scan (gitleaks)）。
- `pytest`: **148 passed / 1 skipped**（skip は所有者ロールのため対象外、`test_audit_immutable.py:40`）、`vitest`: 10 passed、E2E: 26 passed。
- main マージ: PR #1 → merge commit **`5e3f410`**（2026-11-03 06:57 JST）。マージゲートは 18/20（高リスク 2 件はユーザーの明示 Y のうえ GitHub UI で人間がマージ）。
- 配備（2026-11-03 07:00 JST 時点）: `infra/native/deploy.sh` → 稼働 commit **`5e3f410`**、`/healthz` 200・`/readyz` 200（`0003_audit_truncate`）。
- 本番公開: `research.mirai-dx-platform.com`（Cloudflare Tunnel `35974e49…` + Access アプリ／policy `rihrp-allow`）。未認証は 302。
- Dependabot アラート: 有効化。開発依存の critical 3 / high 1（vite / tinypool / vitest）は PR #3 で修正し、open の critical / high = **0 件**（再スキャン後に実測）。
- Cloudflare Access 自動ログイン（PR #4）: `pytest` **96 passed / 1 skipped**、`vitest` **10 passed**（Access 関連 37 件 + UI 5 件を追加）。
- リリース準備（2026-11-03）: 日次バックアップ・週次復元訓練・日次セッション削除・5 分間隔の外形チェックを systemd timer で導入し、各ジョブの実走と復元の件数一致を確認。NFR-16 の同時承認テストと行ロックの排他性テスト、監査ログ削除の dry-run/commit テストを追加（`pytest` **148 passed / 1 skipped**）。詳細: [docs/verification/2026-11-03-release-readiness.md](docs/verification/2026-11-03-release-readiness.md)。
- 詳細: [docs/verification/2026-11-03.md](docs/verification/2026-11-03.md)

### 2026-11-02

- `pytest`: **28 passed**（実 PostgreSQL `rihrp_test`）
- `vitest`: **5 passed**
- `ruff check` / `ruff format --check`: pass
- `tsc -b` / `vite build`: pass（227 kB / gzip 71 kB）
- `alembic upgrade head`: 適用済み（`2dee6c390541`）
- Health Check: `/healthz` 200、`/readyz` 200（migration 一致）
- 主要フロー実測: editor ログイン → 検証（2 verified / 1 unverified）→ 提出 → reviewer 承認 → Markdown エクスポート
- セキュリティ: セキュリティヘッダー、Cookie 属性（HttpOnly / SameSite）、2 MiB 超の本文 413、無効化時のセッション失効を自動テスト
- UI 実測（Round 3）: ログイン後の戻り先復元、主張編集（判定リセット）、テーマ編集、版履歴モーダル、設定画面、ロール変更、テーマ削除（管理者のみ）
- 改竄試験: 出典本文を変更 → `contradicted`（`evidence_tampered`）→ 承認 API が **409 approval_blocked**
- 監査: 上記操作が `audit_events` に記録されていることを確認
- 最終通し E2E（2026-11-03）: テーマ作成 → 出典（SHA-256 一致）→ 主張/根拠 → 検証 `verified` → レポート v2 → 提出 → 承認 → エクスポート（マーカー / SHA）→ 整合性 `needs_reapproval=false` → 管理者が削除
- 依存関係: `npm audit --omit=dev` 0 件、`pip-audit` 0 件
- OpenDesign: design direction（`tech-utility`）取得、Studio で 8 画面のプロトタイプ生成（run は failed 表示）、実装との差異を文書化
- systemd 配備: `rihrp.service` 起動、`/healthz` 200 / `/readyz` 200（migration `0002_audit_immutable`）
- UI: ダッシュボード要対応レール、エディタのセクション一覧レール、独立した検証結果画面、モバイル 390px（横スクロール 0、カード表示）、モーダル Esc、フォーカスリング 2px を実測
- 性能（小規模、n=100）: `/api/projects` p95 17.6ms / claims p95 24.8ms / sources p95 14.9ms（NFR-2 の 300ms 以内）
- 性能（スケール: 200 出典 / 1,000 主張 / 200 参照）: claims p95 180ms / export p95 42ms / projects p95 17ms（NFR-2 の 300ms 以内）
- 依存関係: `npm audit --omit=dev` 0 件、`pip-audit` 0 件（pytest 9.0.3 へ更新）
- プレビュースモーク: `tests/e2e/preview_smoke.py` が PASS（health / ready / login / CSRF / 主要データ / export）
- Backup / Restore: `infra/db/backup.sh` で dump 作成、`infra/db/restore_check.sh` で別 DB に復元（users=4 / projects=1 / claims=4 / reports=1）
- Migration rollback: `rihrp_test` で `alembic downgrade base` → `upgrade head` を実測（最終 `2dee6c390541 (head)`）

## 11. ドキュメント

- 企画: [docs/concept/01-concept.md](docs/concept/01-concept.md)
- 要件: [docs/requirements/01-requirements.md](docs/requirements/01-requirements.md)
- 設計: [docs/architecture/01-architecture.md](docs/architecture/01-architecture.md)
- WebUI 設計: [docs/design/01-webui-design.md](docs/design/01-webui-design.md)
- ADR: [0001](docs/adr/0001-web-stack.md) / [0002](docs/adr/0002-deterministic-verification.md) / [0003](docs/adr/0003-approval-rule.md) / [0004](docs/adr/0004-auth-session.md) / [0005](docs/adr/0005-audit-append-only.md) / [0006](docs/adr/0006-audit-retention.md)
- API: [docs/api/openapi.yaml](docs/api/openapi.yaml)
- 運用手順: [docs/runbooks/operations.md](docs/runbooks/operations.md)
- リリース手順: [docs/runbooks/release.md](docs/runbooks/release.md)
- 変更履歴: [CHANGELOG.md](CHANGELOG.md) / リリースノート: [docs/releases/2026-11-03-v0.1.0.md](docs/releases/2026-11-03-v0.1.0.md)
- CI ワークフロー: [E2E](docs/ci/e2e-workflow.md)（提案） / [依存監査](docs/ci/dependency-audit.md)（適用済み）
- 要件トレーサビリティ: [docs/requirements/traceability.md](docs/requirements/traceability.md)
- 検証記録: [2026-11-07 依存監査](docs/verification/2026-11-07-dependency-audit.md) / [2026-11-03](docs/verification/2026-11-03.md) / [2026-11-02](docs/verification/2026-11-02.md)
- 独立レビュー記録: [docs/verification/2026-11-03-reviews.json](docs/verification/2026-11-03-reviews.json)
- CI 相当の一括検証: `tools/ci.sh`

## 12. ライセンス

MIT
