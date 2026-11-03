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
| 8 | Access 認証後の実ブラウザ確認 | OTP → 自動ログイン → 6 ステップ操作 | 利用者のOTPログイン成功は確認済み。認証後6ステップ全体の本番実操作は別途確認 |
| 9 | 利用対象者の確定 | Access ポリシーとアプリ allowlist | ✅ 許可2件、アプリadmin/editor各1名（20:12 JST再確認） |
| 10 | 監視の通知先 | `RIHRP_ALERT_WEBHOOK` の設定 | 設定しない既存決定を維持。journal/alerts.logのみ。外部監視なし |
| 11 | リリースタグ | `git tag -l` | ✅ `v0.1.0` 作成済み。最新mainと同義ではない |
| 12 | 監査ログ保持方針 | ADR-0006 / `audit-stats` / timer状態 | ✅ **365日**。削除タイマーenabled/active（有効化済み） |

## 2. リリース手順

> **次回コード配備は現時点NO-GO**。現行 `deploy.sh` は稼働ツリー上で依存更新・ビルドを行い、
> SHA固定・排他・失敗時のアプリ切戻しを強制しない。正常稼働中の本番を止めずに、
> コミット別の配備先・切替・ロールバックを別変更で整備・検証してから使う。
> 詳細と実測は [本番準備 第1組](../verification/2026-11-03-production-batch1.md)。

1. `main` が最新で、配備対象の40桁SHAにCIと独立レビューが対応することを確認する。
2. `v0.1.0` は作成済みなので再作成・付け替えしない。次の版は対象SHAとリリース内容を確定して採番する。
3. 新しい配備方式の受入後に、固定SHAから配備する。以下は配備後の必須検査。
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

- アプリ: 旧方式の「稼働ツリーをcheckoutして再ビルド」は依存・成果物を保持せず、即時切戻しを保証しない。次回配備前に現行/直前リリースを別ディレクトリに保持する切戻し方式を検証する。現行サービスのために安易にcheckout/再起動しない。
- データ: `infra/native/rihrp-restore-check.sh` で検証済みのバックアップから復元する
  （別 DB で確認後、切替。`DROP DATABASE` を伴う操作は人間承認）。
- Access を含む公開設定の変更は組織の高リスク変更手順（Approval PR + 明示 Y/N）に従う。

## 5. 今回のリリースに含めない項目

- PDF / Office 取り込み、外部 URL 自動取得、SSO（要件の対象外）。
- 外部合成監視サービスとアラート配信先（現時点は導入しない既存決定。再検討は人間の判断）。
- 実機・スクリーンリーダー確認（後日保留）。監査保持365日と削除ジョブは導入済み。
