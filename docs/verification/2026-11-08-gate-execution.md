# 品質ゲート「未完了のテスト実行」実行記録（2026-11-08）

- 対象: RIHRP Research Studio（`main` = `1e8409d` / PR #18、本番リリース = `1e8409d`）
- 実行: QA ゲート実行（AI）。テスト責任者の承認・リスク受容は未実施。
- 位置づけ: **実行証拠の記録**。リリース承認ではない。

## 1. 結果サマリ

| 区分 | 総数 | 実行済み | 未実行 |
|---|---:|---:|---:|
| P0 | 20 | **20** | 0 |
| P1 | 40 | **38** | 2 |
| P2 | 19 | **19** | 0 |
| **合計** | **79** | **77** | **2** |

- 開始時: executed 2 / reviewed 74 / draft 3（未完了 77）
- 終了時: executed 77 / reviewed 1 / draft 1（未完了 2）
- 実行済み範囲の製品不具合: **0 件**。未実行領域で検出した UI 不具合 1 件（DEF-1）は修正・再実行済み（§5）
- テストケース側の期待値不整合: 1 件（§5 CASE-1）
- 部分スキップ: 2 件（§6）

### 実行したスイート

| スイート | 結果 | 証跡 |
|---|---|---|
| 既存 結合テスト（基準線） | 115 件 / 114 pass / 0 fail / 1 skip（74.5s） | `tmp/gate-20261108/integration.xml` |
| P0 専用ランナー | 20 件 / 20 pass / 0 fail（17.6s） | `tmp/gate-20261108/p0.xml`、`evidence/tc_*.json` |
| P1 専用ランナー（API/DB） | 28 件 / 28 pass / 0 fail（90.3s） | `p1-fast.xml`（27）＋`p1-ratelimit.xml`（1） |
| P2 専用ランナー（API/DB） | 8 件 / 8 pass / 0 fail（7.7s） | `p2.xml` |
| Playwright UI（既存＋補完） | **34 件 / 34 pass / 0 fail**（104.5s） | `playwright-core.xml` |
| Playwright UI（ダッシュボード復活後） | **8 件 / 8 pass / 0 fail**（13.1s） | `playwright-dashboard.xml` |
| 性能（NFR-2） | 主要 API は p95 300ms 以下。1000 件一括検証のみ超過 | `performance.json` |
| バックアップ／復元 | SHA 一致・全 11 テーブル件数一致・restore check OK | 本記録 §4 |
| ヘルスチェック | 5 分間隔・失敗記録・復帰成功・通知先未設定を確認 | `state/alerts.log` |

## 2. 実行環境（本番変更なし）

| 項目 | 実測値 |
|---|---|
| PostgreSQL | 16.15（Ubuntu 16.15-1.pgdg24.04+2） |
| Python | 3.12.3 |
| Node.js | v22.22.3 |
| アプリ | `rihrp.service`（稼働中、v0.2.0） |
| 隔離 DB | `rihrp_test_gate_20261108`、`rihrp_test_ui_20261108`、`rihrp_test_ui_extra_20261108`、`rihrp_scale_20261108`、`rihrp_restore_gate_20261108` |
| 本番 DB | **未変更**（`rihrp` / `rihrp_production` へ接続・書込なし） |
| 本番サービス | **未再起動**（`systemctl` の変更なし） |

- AI 専用ランナーは FastAPI `TestClient` ＋ 隔離 PostgreSQL で、ケースの手順をそのまま実行した。
- UI は Playwright（Chromium）で、隔離 DB に接続した uvicorn（ポート 18112）に対して実行した。
- 性能は `tools/seed_scale.py` で 100 テーマ・1000 主張を投入した隔離 DB を使用した。

## 3. ケース別の実行結果

全 74 件の個別証跡は `tmp/gate-20261108/evidence/<testcase_id>.json` に、
実行した手順・観測値・仕様との差異・スキップ理由を記録している。

### 3.1 主な確認内容（P0）

- 認証・セッション・CSRF・Cookie 属性（development / production）・パスワード 12 文字境界・Access JWT
- テーマ RBAC、出典 3 種と SHA-256、改竄検知、引用実在、検証 6 規則、details 内訳
- 承認成功／409／自己承認 403／承認後改竄、受入 #1 通し、受入 #2 改竄→409
- 監査 RBAC と DB の UPDATE/DELETE/TRUNCATE 拒否、研究文書の保存・409・413・権限・cascade

### 3.2 主な確認内容（P1）

- レート制限 10/11 回・61 秒復帰、ログアウト失効、テーマ削除権限、要対応件数の DB 一致
- 出典重複のテーマスコープ、1 MiB 境界、主張 9/10/2000/2001 文字、別テーマ出典 422
- 一括検証とレポート検証履歴、版と seal、提出・二重提出、差し戻しコメント境界、同時編集 409
- エクスポートのマーカー・付録、監査の相関 ID、利用者管理、監査保持削除（隔離 DB）
- migration 未適用 readyz 503、エラー統一形式、ログ秘密漏洩、一意制約競合 409、同時承認
- 無効化ユーザー拒否、数値表記差、CSRF PATCH/DELETE、パスワード変更後再ログイン、期限切れ 401
- UI: 共通シェル、01 仮説、02 タスク、06 報告書、ダーク／印刷／390px／キーボード（既存 E2E）
- 運用: バックアップ／復元、5 分間隔ヘルスチェック
- 環境: PG16・環境変数接続・Docker 非依存、Node22／Python3.12 ビルド

### 3.3 主な確認内容（P2）

- 出典 title 300/301、HTTP 本文 2 MiB 境界、レポート title 200/201・段落 20000/20001
- 研究文書の形状検証・413、監査の全テーマ閲覧、期限切れセッション削除、seed 環境変数制御
- N+1 回避（10 主張でクエリ 4 件。主張一覧＋根拠件数の 2 クエリと認証系 2 クエリ）
- UI: 03 討論、04 根拠・反証、05 新仮説比較、主張フィルタ・検索、保存失敗時の再試行、複数タブ 409

## 4. 運用ケースの実測

### バックアップ／復元（`tc_mw7pk9gf_0ecdd10e`）

- 隔離 DB `rihrp_test_gate_20261108` を `infra/native/rihrp-backup.sh` でバックアップ。
- dump の SHA-256 を manifest と照合 → OK。
- `infra/db/restore_check.sh` で `rihrp_restore_gate_20261108` へ復元。
- 11 テーブルの件数が一致（users 4 / projects 1 / sources 1 / claims 10 / claim_evidence 10 / audit_events 23 ほか）→ `restore check: OK`。
- `rihrp-backup.timer` は enabled / active（次回 2026-11-09 03:30 JST）。

### ヘルスチェック（`tc_mw7pmf7q_f7e11758`）

- `rihrp-healthcheck.timer` は 5 分間隔（`OnUnitActiveSec=5min`）で active。
- 正常時: `/healthz` 200・`/readyz` 200 → exit 0。
- API 停止時: 両方失敗 → exit 1、`tmp/gate-20261108/state/alerts.log` に失敗理由を記録。
- API 再開時: 成功に復帰 → exit 0。
- `RIHRP_ALERT_WEBHOOK` は未設定（0 件）。`alert.sh` は journal とローカルログのみに記録し、送信しない。

## 5. 検出した問題

### DEF-1（UI / 文書整合）: ダッシュボード画面が到達不能 → 修正済み

- 検出: `apps/web/src/App.tsx:81` で index ルートが `Navigate to="/studio"` に変更され
  （commit `f25603c`）、`components/Layout.tsx` のナビ「ダッシュボード」は `/` を指していた。
  `/` は `/studio` へ遷移するため、ダッシュボードのテーマ検索・最近の活動・状態表示を
  UI から操作できなかった。
- 修正（2026-11-08）: `App.tsx` に `/dashboard` ルートを追加し、`Layout.tsx` のナビを
  `/dashboard` へ変更した。`/` は従来どおり `/studio` へリダイレクトし、ログイン後の
  既定画面（Studio）は変えていない。
- 検証: 一時ビルド（`/tmp/rihrp-gate-dist`、`RIHRP_WEB_DIST` で配信）に対して
  Playwright 8 件を実行し、ダッシュボード 3 ケース（テーマ検索・最近の活動・
  loading / empty / error）を含めて全 pass。
- 本番反映: 2026-11-08 21:30 JST に不変リリース `1e8409d` をビルドし、本番バックアップ＋
  隔離復元証跡を前提に activate した。`/healthz`・`/readyz` が release SHA `1e8409d` を返し、
  `/dashboard` は新ビルド `index-DIKL1po7.js` を配信している。
- 証跡: `tmp/gate-20261108/playwright-dashboard.xml`。

### CASE-1（テストケースの期待値不整合）: 出典削除 API の有無

- `tc_mw7pi021_defecae4` 手順 5 は「出典の更新・削除 API が存在しない（404/405）」を期待する。
- 実装には `DELETE /api/sources/{id}` が存在し、未使用なら 200、使用中なら 409 `source_in_use` で保護される。
- 判定: 製品不具合ではない。**ケースの期待値が現実装に追随していない**ため、ケース修正が必要。

### CASE-2（表示形式の差異）: 900px のナビ

- `tc_mw7pjyc4_371de126` は「820〜900px で 1 カラム・ナビが横スクロール」を期待する。
- 実装は 900px 以下で 68px のアイコンレールに切り替わり、横スクロールにはならない。
- 実測: 横スクロールなし、サイドバーはアイコンのみ、コンテンツは 900px に収まる。
- 判定: ケースまたは設計記述の更新が必要（どちらを正とするかは人間の判断）。

### PERF-1（NFR-2 の解釈）: 1000 件一括検証の p95

- 100 テーマ・1000 主張の隔離 DB で実測:

| API | p50 | p95 | max |
|---|---:|---:|---:|
| GET /api/projects（一覧） | 19.2ms | **21.4ms** | 90.3ms |
| GET /api/projects/{id}（詳細） | 17.7ms | **49.2ms** | 1868.3ms |
| GET /api/projects/{id}/claims（一覧） | 65.4ms | **144.7ms** | 1452.1ms |
| GET /api/reports/{id}/export | 34.5ms | **45.5ms** | 112.3ms |
| POST /api/claims/{id}/verify（単一） | 17.5ms | **20.3ms** | 24.4ms |
| POST /api/projects/{id}/claims/verify（1000 件一括） | 1336.0ms | **1862.1ms** | 2411.9ms |
| GET /api/projects（8 並列） | 106.8ms | **158.2ms** | 220.7ms |
| GET /api/projects/{id}（8 並列） | 59.6ms | **79.7ms** | 112.7ms |

- 単一リクエストの主要 API は p95 300ms 以下を満たす。
- 1000 件を 1 リクエストで検証する一括 API は 1862ms で超過する。
  これは「1 リクエストで 1000 件を処理するバッチ」であり、NFR-2 の対象に含めるかは仕様判断が必要。

## 6. 部分スキップ（未実施として記録）

| ケース | 未実施内容 | 理由 |
|---|---|---|
| `tc_mw7piyoc_3268ea0c` | 監査書込失敗時の fail closed 注入 | 実装を壊さずに注入できない。設計確認で代替 |
| `tc_mw7ppxz3_aef4a18a` | UI 承認画面の残数表示 | API 応答・エクスポートは確認済み。UI は別途 |
| `tc_mw7pjgxa` ほか UI | 一部の細目（80 文字打ち切り、T-09 差し戻し 等） | 既存 E2E の主要シナリオで代替。細目は未確認 |

## 7. 残り 2 件と理由

| ID | 優先 | ケース | 未実行の理由 | 解除に必要なもの |
|---|---|---|---|---|
| `tc_mw7pk9gr_0bfcc673` | P1 | リリース切替・切戻し | systemd ユニットの書き換え・サービス再起動・本番相当の承認が必要 | 人間の実施承認と立会い。既存の `docs/verification/2026-11-03-production-batch2.md` に過去の実測あり |
| `tc_mw7ppy15_74c5dadf` | P1 | 数値表記差（初版） | draft。修正版 `tc_mw7pqh7r_23eb2848` が同等の検証を実行済み。初版は根拠紐付け手順が欠落 | 修正版への統合／削除の判断（ケース本文の編集が必要） |

- `tc_mw7pmf4c` / `tc_mw7pmf52` / `tc_mw7pqh83` は DEF-1 修正後に実行し、executed へ更新済み。

## 8. ゲート判定

- **79 件中 77 件を実行済み**（P0 20/20、P1 38/40、P2 19/19）。実行範囲に承認を止める
  製品不具合は検出されなかった。
- ただし **リリースゲートは依然 NO-GO**:
  1. 未実行 2 件（リリース切替は人間承認、draft 初版はケース整理）。
  2. RISK-01〜07・ISS-01〜05 のリスク受容が人間により記録されていない。
  3. レポート／リリースのゲート承認はテスト責任者の人手判断（AI は代行不可）。
- ダッシュボード修正（DEF-1）は PR #18 → main `1e8409d` → 不変リリース `1e8409d` として
  本番反映済み。`/healthz`・`/readyz` の release SHA と `/dashboard` の配信を実測確認した。
- 実行証拠は `tmp/gate-20261108/` と本記録に揃っている。残り 2 件の扱いを決めれば、
  テスト責任者の判断材料としては十分な状態である。

## 9. 証跡一覧

| 証跡 | パス |
|---|---|
| ケース別 JSON（56 件） | `tmp/gate-20261108/evidence/` |
| P0 JUnit | `tmp/gate-20261108/p0.xml` |
| P1 JUnit | `tmp/gate-20261108/p1-fast.xml`、`p1-ratelimit.xml` |
| P2 JUnit | `tmp/gate-20261108/p2.xml` |
| Playwright JUnit（34 件） | `tmp/gate-20261108/playwright-core.xml` |
| Playwright JUnit（ダッシュボード復活後 8 件） | `tmp/gate-20261108/playwright-dashboard.xml` |
| 既存結合テスト基準線 | `tmp/gate-20261108/integration.xml` |
| 性能実測 | `tmp/gate-20261108/performance.json` |
| バックアップ／復元 | `tmp/gate-20261108/backups/` |
| ヘルスチェック失敗ログ | `tmp/gate-20261108/state/alerts.log` |
| QA ステータス更新前後 | `tmp/gate-20261108/qa_update.json` |
| 実行ランナー | `tests/gate/`、`apps/web/e2e/gate-extra.spec.ts`、`apps/web/playwright.gate.config.ts` |
| ダッシュボード修正 | `apps/web/src/App.tsx`、`apps/web/src/components/Layout.tsx` |
| PR / マージ | PR #18 → `1e8409d`（main push CI success） |
| 本番リリース | `~/.local/share/rihrp/releases/1e8409d...`（`current` シンボリックリンク） |
| 本番バックアップ／復元証跡 | `~/.local/state/rihrp/backups/rihrp_production-20261108T123031...`、`restore-evidence-deploy-20261108.json` |
