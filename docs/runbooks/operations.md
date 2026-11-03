# RIHRP Research Studio — 運用手順

## 1. サービス

| 項目 | 値 |
|---|---|
| unit | `rihrp.service`（systemd --user） |
| バインド | `127.0.0.1:18110` |
| 設定 | `~/.config/rihrp/rihrp.conf`（リポジトリ外。`chmod 600`） |
| ログ | `journalctl --user -u rihrp.service -f` |
| ヘルス | `infra/native/health_check.sh` または `curl -fsS http://127.0.0.1:18110/readyz` |

```bash
systemctl --user status rihrp.service
systemctl --user restart rihrp.service
journalctl --user -u rihrp.service --since "30 min ago"
```

## 1.1 本番公開（Cloudflare Tunnel / Access）

| 項目 | 値 |
|---|---|
| 公開 URL | `https://research.mirai-dx-platform.com`（Cloudflare Access 保護） |
| Tunnel unit | `rihrp-cloudflared.service`（systemd --user、`~/.cloudflared/rihrp-config.yml`） |
| Tunnel ID | `35974e49-9cad-423b-86cd-ab77ff0a2021` |
| DNS | `research.mirai-dx-platform.com` CNAME → `<tunnel-id>.cfargotunnel.com`（proxied） |
| Access | アプリ「RIHRP Research Studio」（self_hosted）、policy `rihrp-allow`（allow: **個別email 2件**、domain/everyone許可なし） |

> 2026-11-03 20:12 JSTにCloudflare APIでemailルール2件、実プロセスの
> `RIHRP_CF_ACCESS_ALLOWED_EMAILS` も2件であることを再確認。ユーザーはadmin/editor各1名。
> ここでは件数・方式の確認であり、値を文書に載せない。
> 利用者を増やす場合は Access ポリシーとアプリ設定の**両方**を更新する（高リスク変更）。

```bash
systemctl --user status rihrp-cloudflared.service
journalctl --user -u rihrp-cloudflared.service --since "30 min ago"
curl -sS -o /dev/null -w '%{http_code}\n' https://research.mirai-dx-platform.com/   # 未認証は 302
```

- Access の認証後画面（OTP/SSO）の確認は人間が行う。AI は未認証 302 までを検証できる。
- 本番設定は `RIHRP_ENV=production` / `RIHRP_COOKIE_SECURE=true` / `RIHRP_SEED_DEMO=false`。
  この構成では `tests/e2e/preview_smoke.py` は `http://127.0.0.1` では Cookie が Secure のため 401、Access 配下の `https://` では未認証 302 となり、**どちらも実行できない**（スクリプトは Access の資格情報を持たない）。
  本番の確認は Access 認証後のブラウザで行い、スモークは開発・プレビュー環境（`RIHRP_COOKIE_SECURE=false`）でのみ使う。
- 公開 DNS・custom domain・Access の変更は組織方針の高リスク変更（Approval PR + ユーザーの明示 Y/N）。

### 1.1.1 Access 自動ログイン（JWT 検証）

アプリの `/api/auth/access` が `Cf-Access-Jwt-Assertion` を検証し、Access で認証済みの利用者にアプリのセッションを発行する。
設定は `~/.config/rihrp/rihrp.conf`（リポジトリ外）に置く。

```bash
RIHRP_TRUST_CF_ACCESS=true
RIHRP_CF_ACCESS_TEAM_DOMAIN=winter-lake-f4c9.cloudflareaccess.com
RIHRP_CF_ACCESS_AUD=<Access アプリの AUD タグ>
RIHRP_CF_ACCESS_ALLOWED_EMAILS=<許可する email（カンマ区切り）>
RIHRP_CF_ACCESS_LOOPBACK_ONLY=false
RIHRP_CF_ACCESS_PROVISION=false
```

- AUD は Cloudflare API（`/accounts/<id>/access/apps/<app id>`）の `aud`、team domain は Access のログイン URL から確認できる。
- 確認: `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18110/api/auth/access` は **401**（Assertion 無し）を返す。
  未設定なら **404**。`LOOPBACK_ONLY=true` のときはループバック外からの接続が **403** になるが、
  uvicorn は proxy headers を既定で信頼するため Tunnel 経由では client host が実 IP になり、通常は false のまま使う。
- 自動ログインを止める（切り戻し）: `RIHRP_TRUST_CF_ACCESS=false` にして `systemctl --user restart rihrp.service`。
  パスワードログイン（`/api/auth/login`）はそのまま使える。
- 注意: 許可 email が空のときは全拒否（fail closed）。ユーザーは `users.email` と Access の email を一致させる。
  未登録ユーザーを自動作成する場合は `RIHRP_CF_ACCESS_PROVISION=true`（既定ロール `viewer`）を明示する。

## 2. 配備

現行 `infra/native/deploy.sh` は同じ稼働ツリーで `pip install -e ".[dev]"` → migration →
Webビルド → unit再起動を行う旧方式。`set -e`で停止しても、変更済み依存・DB・distを元に戻さない。
ビルド途中で旧プロセスと新成果物が混在し得るため、**次回コード配備には使用しない**。
SHA固定・clean/CIゲート・排他・コミット別成果物・切戻しを整備し、隔離検証後に移行する。

事前の読み取り専用検査（CI承認やruntime SHAの証明ではない）:

```bash
python3 tools/release_preflight.py --expect-sha <対象の40桁SHA> \
  --backup-dir "$HOME/.local/state/rihrp/backups"
```

事前に `git fetch origin` を実行し、その観測時刻と対象SHAのリモートCI成功を別途確認する。
このCLIはネットワークに接続せず、**ローカルremote-tracking ref**のorigin/mainとの完全一致、
cleanな作業ツリー、新鮮で完全な本番バックアップを検査する。リモートrefの鮮度は保証しない。
origin/mainと異なるコミットや編集中のツリーでは意図どおり失敗する。ブランチ名だけは検査しない。
正常な結果だけで配備許可にはならない。

## 3. データベース

```bash
# 本番 DB のバックアップ（DB 名は設定の RIHRP_DATABASE_URL から導出。既定 14 世代）
infra/native/rihrp-backup.sh

# 復元訓練（最新バックアップを専用 DB に復元して件数を比較し、成功後に復元 DB を削除）
infra/native/rihrp-restore-check.sh

# pg_dump / pg_restore は同一 major を使う（既定: /usr/lib/postgresql/16/bin）。
# PATH の pg_dump が 17、pg_restore が 16 だと「バージョン(1.16)はサポートされていません」で失敗する。
# 必要なら RIHRP_PG_BIN=/usr/lib/postgresql/16/bin を指定する。

# migration 状態
(cd infra/migrations && alembic current && alembic heads)
```

- バックアップの保存先: `~/.local/state/rihrp/backups/`（`RIHRP_BACKUP_DIR` で変更可）。
- 1 回のバックアップは `.dump`・`.sha256`・`.manifest.json`（バックアップ時点の件数（11 テーブル）と migration）を 1 組で保存する。
  公開順序は dump → checksum → **manifest（最後＝完成の目印）**。途中で失敗した場合は `.part`/`.tmp` のまま残り、
  manifest が無い組は復元訓練の対象にならない。
- バックアップはロックファイルで直列化し、ファイル名は `<db>-<UTC日時>-<PID>.dump`（同名衝突を避ける）。
- 復元訓練は **manifest の件数**と比較する。現在の本番件数と比較すると、バックアップ後の通常更新で
  誤検知するため（以前の方式の欠陥）。SHA-256 と migration も検証する。
- **前提**: 実行する OS ユーザーが対象 DB にローカル接続できること（本番は peer 認証）。接続できない場合は
  バックアップが fail closed で停止する。`pg_dump` に接続情報は引き継がない（URL は DB 名の導出にのみ使う）。
- 復元訓練のログ: `~/.local/state/rihrp/last-restore-check.log`。
- 復元 DB を調査用に残す: `RIHRP_RESTORE_KEEP_DB=1 infra/native/rihrp-restore-check.sh`。
- 旧形式（manifest なし）の dump は
  `RIHRP_SOURCE_DB=rihrp_production infra/db/restore_check.sh <dump> [restore_db]` で手動検証できる
  （現在の本番件数との比較になる点に注意）。
- `infra/db/backup.sh` は dump と checksum だけを作る（世代管理なし、ロックと一意名あり）。世代管理は
  `infra/db/prune_backups.sh <db> [keep]`。保持対象は **dump + sha256 + manifest（db 一致）の完全な組**だけで、
  対象 DB 以外（例: rihrp と rihrp-other）には触れない。孤児の sidecar・1 日超の不完全な組・残骸は掃除する。
- 日次バックアップは **REPEATABLE READ のスナップショット**（`pg_export_snapshot`）で
  dump と manifest を取得するため、バックアップ中の書き込みで件数がずれない。

**禁止（承認が必要）**: `DROP DATABASE` / `DROP TABLE` / `TRUNCATE` / 大量 DELETE / 不可逆 migration / 本番データへの重大変更。

## 4. 定期ジョブ（systemd timer）

`infra/native/install_ops_units.sh` で導入する（`--dry-run` あり）。導入済みのユニットは次の5組（audit-purgeを含む）。

| timer | 実行 | 内容 | 手動実行 |
|---|---|---|---|
| `rihrp-backup.timer` | 毎日 03:30（JST） | 本番 DB のバックアップ（dump + sha256 + manifest、14 世代保持） | `systemctl --user start rihrp-backup.service` |
| `rihrp-maintenance.timer` | 毎日 04:00 | 期限切れ 7 日超のセッション削除 | `systemctl --user start rihrp-maintenance.service` |
| `rihrp-restore-check.timer` | 毎週日曜 04:30 | 最新の `<db>-*.dump` を復元し、SHA-256・migration・manifest の件数を検証 | `systemctl --user start rihrp-restore-check.service` |
| `rihrp-healthcheck.timer` | 起動 2 分後、以降 5 分間隔 | `/healthz` と `/readyz` のチェック。失敗で非 0 | `systemctl --user start rihrp-healthcheck.service` |

`rihrp-audit-purge.timer`（毎日05:00・監査ログ削除）は**インストーラでは既定で無効**。
この本番では所有者の既存承認により有効化済みで、2026-11-03 20:10 JSTにもenabled/activeを確認した。
再導入時の無条件有効化はしない。

```bash
systemctl --user list-timers 'rihrp-*' --all
systemctl --user status rihrp-backup.timer rihrp-healthcheck.timer
journalctl --user -u rihrp-backup.service -n 50 --no-pager
journalctl --user -u rihrp-restore-check.service -n 50 --no-pager
```

- **バックアップの失敗は黙って進まない**: ユニットが failed になるため `systemctl --user --failed` で確認できる。
- **外形チェックの失敗通知**: `rihrp-healthcheck.sh` は失敗時に `alert.sh` を呼び、journal（`rihrp-alert`）と
  `~/.local/state/rihrp/alerts.log` に残す。`RIHRP_ALERT_WEBHOOK` を設定すると JSON を POST する（Slack 等の
  incoming webhook を想定）。未設定でも記録は残るが、**人間への即時通知には通知先の設定が必要**。

## 5. 障害対応

| 症状 | 確認 | 対応 |
|---|---|---|
| `/readyz` が 503 `database_unreachable` | `pg_isready`、PostgreSQL のログ | PostgreSQL 起動、接続情報の確認 |
| `/readyz` が 503 `migration_pending` | `alembic current` | `alembic upgrade head` 後に再起動 |
| 承認が 409 `approval_blocked` | レポートの検証サマリ、矛盾クレーム | 根拠の修正（引用の修正 or 出典の再登録）後に再検証 |
| 出典が `tampered: true` | `sources.content` と `content_sha256` | 正しい本文で再登録（上書き API は無い）。監査ログを確認 |
| ログインできない（429） | ログイン試行の集中 | 待機、必要ならプロセス再起動でインメモリ制限をリセット |
| 外形チェック failed | `systemctl --user --failed`、`alerts.log` | サービス状態と DB を確認し、復旧後に `systemctl --user start rihrp-healthcheck.service` で再確認 |

## 6. ロールバック

- アプリ: 現行のcheckout＋再ビルド方式は即時切戻しを保証しない。次回配備の前に保持した現行/直前リリースへ切り替える方式を検証する（[リリース判定](release.md)）。
- DB: additive migration のみを原則とする。破壊的 migration は Approval PR で扱う。
- データ: `infra/native/rihrp-restore-check.sh` で検証したバックアップからの復元（別 DB で確認後、切替）。

## 7. 監視・アラート

| 項目 | 状態 |
|---|---|
| プロセスの自動再起動 | 実装済み（`Restart=on-failure`、`RestartSec=3`） |
| 同一ホストからの 5 分間隔チェック | 実装済み（`rihrp-healthcheck.timer`） |
| 失敗時の記録（journal / alerts.log） | 実装済み（`alert.sh`） |
| 外部合成監視（別ホスト・外形サービス） | **未実装**（別ホストからの監視と通知先の選定が必要） |
| ダッシュボード / アラート配信 | **未設定**（`RIHRP_ALERT_WEBHOOK` を設定すると webhook 通知） |

## 8. 監査ログの保持（365 日・削除は承認制）

- 方針: **365 日**（2026-11-03 決定、[ADR-0006](../adr/0006-audit-retention.md)）。
- 既定では削除しない。件数の確認:

```bash
set -a; source "$HOME/.config/rihrp/rihrp.conf"; set +a
.venv/bin/python -m rihrp.maintenance audit-stats
# audit events: total=... older_than_retention=... retention_days=365
```

- **dry-run（削除しない）**:

```bash
.venv/bin/python -m rihrp.maintenance purge-audit --days 365
```

- **実際の削除（承認時のみ）**: `RIHRP_ALLOW_AUDIT_PURGE=1` と `--commit` の両方が必要
  （関数内でも強制）。所有者ロールで 1 トランザクション内にトリガーを一時無効化し、
  削除後に再有効化する。ロック待ち 5 秒・statement 120 秒で打ち切り、対象 0 件なら
  ロックを取らずに終了する。

```bash
RIHRP_ALLOW_AUDIT_PURGE=1 .venv/bin/python -m rihrp.maintenance purge-audit --days 365 --commit
```

- 自動実行は `rihrp-audit-purge.timer`（毎日 05:00）。**インストーラは有効化しない**。
  承認後に `systemctl --user enable --now rihrp-audit-purge.timer` を実行する。
- 実行前に `infra/native/rihrp-backup.sh` でバックアップを取得する。削除は不可逆で、
  実行中は `audit_events` に短時間の ACCESS EXCLUSIVE ロックがかかる。

## 9. リリース

正式リリースの Go/No-Go 判定と手順は [release.md](release.md) を参照。
