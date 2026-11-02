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
| Access | アプリ「RIHRP Research Studio」（self_hosted）、policy `rihrp-allow`（allow: `kensan1969@gmail.com` / `mirai-const.co.jp` / `takamatsu-cg.co.jp`） |

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

## 2. 配備

```bash
infra/native/deploy.sh
```

内部で `pip install -e .` → `alembic upgrade head` → `npm ci && npm run build` → unit 再起動 → health check を行う。
失敗時はユニットが起動しない / health check が非 0 で止まる。

## 3. データベース

```bash
# バックアップ（既定 14 世代）
infra/db/backup.sh rihrp

# 復元検証（別 DB に復元して行数を確認）
infra/db/restore_check.sh ~/.local/state/rihrp/backups/rihrp-<stamp>.dump

# pg_dump / pg_restore は同一 major を使う（既定: /usr/lib/postgresql/16/bin）。
# PATH の pg_dump が 17、pg_restore が 16 だと「バージョン(1.16)はサポートされていません」で失敗する。
# 必要なら RIHRP_PG_BIN=/usr/lib/postgresql/16/bin を指定する。

# migration 状態
(cd infra/migrations && alembic current && alembic heads)
```

**禁止（承認が必要）**: `DROP DATABASE` / `DROP TABLE` / `TRUNCATE` / 大量 DELETE / 不可逆 migration / 本番データへの重大変更。

## 4. 定期メンテナンス（手動 or cron）

- 期限切れセッションの削除:

```sql
DELETE FROM sessions WHERE expires_at < now() - interval '7 days';
```

- 監査ログの保持: 既定 365 日（`RIHRP_AUDIT_RETENTION_DAYS`）。削除ジョブは未実装（方針決定後に追加）。

## 5. 障害対応

| 症状 | 確認 | 対応 |
|---|---|---|
| `/readyz` が 503 `database_unreachable` | `pg_isready`、PostgreSQL のログ | PostgreSQL 起動、接続情報の確認 |
| `/readyz` が 503 `migration_pending` | `alembic current` | `alembic upgrade head` 後に再起動 |
| 承認が 409 `approval_blocked` | レポートの検証サマリ、矛盾クレーム | 根拠の修正（引用の修正 or 出典の再登録）後に再検証 |
| 出典が `tampered: true` | `sources.content` と `content_sha256` | 正しい本文で再登録（上書き API は無い）。監査ログを確認 |
| ログインできない（429） | ログイン試行の集中 | 待機、必要ならプロセス再起動でインメモリ制限をリセット |

## 6. ロールバック

- アプリ: 直前のコミットを checkout して `infra/native/deploy.sh`。
- DB: additive migration のみを原則とする。破壊的 migration は Approval PR で扱う。
- データ: `infra/db/restore_check.sh` で検証したバックアップからの復元（別 DB で確認後、切替）。

## 7. 監視（未実装）

- systemd の `Restart=on-failure` のみ。
- 外部合成監視（5 分ごとの `/readyz`）とアラートは未実装。公開 URL は稼働中だが、外形監視は未追加。

## 4.1 セッションの定期削除

```bash
set -a; source "$HOME/.config/rihrp/rihrp.conf"; set +a
.venv/bin/python -m rihrp.maintenance purge-sessions --days 7
```

期限切れから 7 日経過したセッションを削除する（既定）。cron / systemd timer で日次実行する場合は、`EnvironmentFile=~/.config/rihrp/rihrp.conf` を指定した oneshot ユニットにする。
