# RIHRP Research Studio — リリース手順（Go/No-Go）

本番は 2026-11-03 時点で稼働中（Cloudflare Access 保護）。ここでは「正式リリース判定」に必要な
確認項目と手順を示す。**人間の確認が必要な項目**を明示する。

## 1. Go/No-Go チェックリスト

| # | 判定項目 | 確認方法 | 状態（2026-11-03 実測） |
|---|---|---|---|
| 1 | main の CI が緑 | GitHub Actions（api / web / secret-scan） | ✅ success |
| 2 | 本番が起動している | `infra/native/health_check.sh` | ✅ `/healthz` 200・`/readyz` 200 |
| 3 | 本番 DB の migration が最新 | `alembic current` / `/readyz` の `migration` | ✅ `0004_research_documents` |
| 4 | 主要フローの自動検証 | `pytest` / `vitest` / `npx playwright test` | ✅ 後述の実測値 |
| 5 | 定期バックアップが動作 | `systemctl --user list-timers 'rihrp-*'` と backup の成功 | ✅ 日次 timer 稼働 |
| 6 | 復元訓練が成功 | `journalctl --user -u rihrp-restore-check.service` | ✅ 件数一致 |
| 7 | 外形チェックが動作 | `systemctl --user status rihrp-healthcheck.timer` | ✅ 5 分間隔 |
| 8 | Access 認証後の実ブラウザ確認 | OTP/SSO → ログイン → 6 ステップ操作 | ⚠️ **人間が実施** |
| 9 | 利用対象者の確定 | Access ポリシーとアプリ allowlist | ⚠️ **人間が判断**（現状は単一 email） |
| 10 | 監視の通知先 | `RIHRP_ALERT_WEBHOOK` の設定 | ⚠️ **未設定**（記録のみ） |
| 11 | リリースタグ | `git tag -l` / GitHub Releases | ⏳ 本 PR マージ後に `v0.1.0` を作成（手順は §2） |
| 12 | 監査ログ保持方針 | ADR-0006 / `audit-stats` / `purge-audit` dry-run | ✅ **365 日で決定**。削除ジョブ実装済み・タイマーは承認待ちで無効 |

## 2. リリース手順

1. `main` が最新で CI が緑であることを確認する。
2. `git tag -a v0.1.0 -m "RIHRP Research Studio v0.1.0"` を作成し、`git push origin v0.1.0`。
3. 本番へ配備する: `infra/native/deploy.sh`。
4. 配備後の実測:
   - `/healthz` 200、`/readyz` 200（migration が期待値）
   - `/`・`/studio`・`/login` 200、`/api/auth/me` 401
   - 配信 asset がビルド成果物と一致
   - 公開 URL が 302（Access）
   - `journalctl --user -u rihrp.service --since "10 min ago" -p err` にエラーがない
5. 定期ジョブの状態を確認する（`systemctl --user list-timers 'rihrp-*' --all`）。
6. 利用者へ告知する（対象者・URL・ログイン方法・問い合わせ先）。

## 3. リリース後の確認（初日）

- `rihrp-backup.service` が成功し、`~/.local/state/rihrp/backups/` に当日分が増えている。
- `rihrp-restore-check.service` の週次実行が成功している（翌週）。
- `rihrp-healthcheck.timer` が 5 分間隔で動き、`systemctl --user --failed` が空である。
- 監査ログの件数が想定どおり増えている（`audit-stats`）。

## 4. ロールバック

- アプリ: 直前のタグ/コミットを checkout して `infra/native/deploy.sh`。
- データ: `infra/native/rihrp-restore-check.sh` で検証済みのバックアップから復元する
  （別 DB で確認後、切替。`DROP DATABASE` を伴う操作は人間承認）。
- Access を含む公開設定の変更は組織の高リスク変更手順（Approval PR + 明示 Y/N）に従う。

## 5. 今回のリリースに含めない項目

- PDF / Office 取り込み、外部 URL 自動取得、SSO（要件の対象外）。
- 外部合成監視サービスとアラート配信先の選定（通知先が決まり次第 `RIHRP_ALERT_WEBHOOK` を設定）。
- 監査ログの保持期間を超えたレコードの削除（保持方針の決定後）。
