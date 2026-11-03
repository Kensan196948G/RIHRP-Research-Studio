# 検証記録 — 2026-11-03 リリース準備（AI 対応可能タスク）

正式リリースに向けて AI が実施できる項目を実装し、実測した記録。

## 1. 実装したもの

| 項目 | 実装 | 実測 |
|---|---|---|
| 日次バックアップ | `infra/native/rihrp-backup.sh` + `backup_manifest.py` + `rihrp-backup.timer`（03:30） | **REPEATABLE READ + `pg_export_snapshot`** で dump と manifest（件数・migration・sha256）を同一スナップショットから取得。`Result=success`、dump/sha256/manifest の 3 点セットを生成 |
| 週次復元訓練 | `infra/native/rihrp-restore-check.sh` + `rihrp-restore-check.timer`（日曜 04:30） | manifest 付きの最新 `<db>-*.dump` を選び、SHA-256・manifest と dump の対応（名前・ハッシュ）・migration・**バックアップ時点の件数**を検証。users 1/1・projects 4/4・audit_events 18/18 で `restore check: OK`。成功後に復元 DB を削除 |
| セッション定期削除 | `rihrp-maintenance.service/.timer`（04:00） | `purged sessions: 0`（成功） |
| 外形チェック | `infra/native/rihrp-healthcheck.sh` + `rihrp-healthcheck.timer`（5 分間隔） | `/healthz` 200・`/readyz` 200、失敗時は `alert.sh` が journal と `~/.local/state/rihrp/alerts.log` に記録 |
| 通知経路 | `infra/native/alert.sh`（`RIHRP_ALERT_WEBHOOK` 対応、未設定でも記録） | 自己テストで `alerts.log` への記録を確認。**通知先の設定は人間** |
| 監査統計 | `python -m rihrp.maintenance audit-stats` | 本番: `total=18 older_than_retention=0 retention_days=365` |
| 運用手順 | `docs/runbooks/operations.md` 全面更新 | Access policy の実測値を反映（単一 email） |
| リリース手順 | `docs/runbooks/release.md` | Go/No-Go 12 項目と手順 |
| 変更履歴 | `CHANGELOG.md` / 本リリースノート | v0.1.0 |
| NFR-16 並行更新 | `tests/integration/test_locking.py::test_concurrent_approval_is_serialized` / `test_report_row_lock_is_exclusive` | 2 本同時承認で `[200, 409 invalid_state]`、`reviews=1`、`audit report.reviewed=1`。別セッションの `FOR UPDATE NOWAIT` が `OperationalError` になることで行ロックの取得自体を拘束 |
| CI 依存監査 | 提案 `docs/ci/dependency-audit.md`（workflow 変更は人間） | YAML をパース検証 |

ユニット定義は `systemd-analyze --user verify` が exit 0、`infra/native/install_ops_units.sh` で導入。
導入後の `systemctl --user list-timers 'rihrp-*' --all` は 4 timer を表示（次回 11-04 03:30 / 04:00、11-08 04:34）。

## 2. テスト

| 項目 | 結果 |
|---|---|
| pytest | 148 collected / **147 passed / 1 skipped**（78.9s） |
| 追加テスト | 同時承認の直列化（NFR-16）、行ロックの排他性、監査統計の保持超過件数 |
| vitest | 10 passed |
| Playwright E2E | 26 passed |
| ruff check / format | pass |
| shellcheck / ruff | シェルは警告なし（SC1090/SC2012 も解消）。`backup_manifest.py` は `ruff check` / `format` pass |

## 2.1 負の対照（実測）

- manifest から 1 テーブルを欠落させた場合: `NG: manifest の件数を読み取れません` で exit 1（「0 件検査で成功」にしない）。
- manifest が無いバックアップだけを置いた場合: `NG: ... manifest 付きの ... バックアップがありません` で exit 1。
- 前方一致が衝突する DB 名（`rihrp` と `rihrp-other`）を混在させた `prune_backups.sh rihrp 1`: `rihrp-other` の dump は残り、`rihrp` の古い世代だけが削除された（manifest の `db` も検証）。
- 同時実行: `backup_manifest.py` を 2 本同時に起動し、片方は成功・片方は `BACKUP FAILED: 別のバックアップが実行中です`（exit 3）でロックが機能した。
- `systemd-analyze --user verify` exit 0、shellcheck は対象スクリプトで警告なし。

## 3. 本番の実測（2026-11-03）

- `/healthz` 200、`/readyz` 200（migration `0004_research_documents`）、`/`・`/studio`・`/login` 200、`/api/auth/me` 401。
- 配信 asset はビルド成果物と一致。`rihrp.service` は active、起動後エラー 0。
- DB: users 1 / projects 4 / audit_events 18 / sessions 7。
- 公開 URL は 302（Cloudflare Access）。Access policy は `kensan1969@gmail.com` のみ（Cloudflare API で実測）。

## 4. 未実施（人間が必要）

- Access の OTP/SSO を通した実ブラウザ確認（ログイン → 6 ステップ → 保存 → 再読込）。
- リリース対象者の確定（現状は単一 email）と告知。
- アラート通知先（`RIHRP_ALERT_WEBHOOK`）の選定・設定。外部合成監視を別ホストに置くかの判断。
- 監査ログの保持方針（365 日でよいか）と削除ジョブの追加可否。
- `.github/workflows/**` の適用（E2E・依存監査の提案ドキュメント）。workflow_dispatch での手動実行確認。
- モバイル実機・スクリーンリーダーでの確認。
