#!/usr/bin/env bash
# 本番 DB の日次バックアップ（systemd timer から実行）。
# DB 名は ~/.config/rihrp/rihrp.conf の RIHRP_DATABASE_URL から導出する。
# dump と manifest は同一スナップショットで取得し（backup_manifest.py）、
# 完全な組が揃ってから世代削除を行う。
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
ENV_FILE="${RIHRP_ENV_FILE:-$HOME/.config/rihrp/rihrp.conf}"
[[ -f "$ENV_FILE" ]] || {
  printf 'BLOCKED: %s がありません\n' "$ENV_FILE" >&2
  exit 1
}
set -a
# shellcheck source=/dev/null
source "$ENV_FILE"
set +a
: "${RIHRP_DATABASE_URL:?RIHRP_DATABASE_URL が必要です}"

url="${RIHRP_DATABASE_URL%%\?*}"
db="${url##*/}"
[[ "$db" == rihrp* ]] || {
  printf 'BLOCKED: DB 名が想定外です（%s）\n' "$db" >&2
  exit 2
}

# 前提: このユニットを実行する OS ユーザーが対象 DB に接続できること
# （本番ホストではローカル peer 認証。詳細は docs/runbooks/operations.md）。
if ! psql -d "$db" -tAc 'SELECT 1' >/dev/null 2>&1; then
  printf 'BLOCKED: OS ユーザーから %s に接続できません\n' "$db" >&2
  exit 3
fi

BACKUP_DIR="${RIHRP_BACKUP_DIR:-$HOME/.local/state/rihrp/backups}"
PG_BIN="${RIHRP_PG_BIN:-/usr/lib/postgresql/16/bin}"

printf '%s backup start db=%s\n' "$(date -Is)" "$db"
"$ROOT/.venv/bin/python" "$ROOT/infra/native/backup_manifest.py" \
  --db "$db" \
  --out-dir "$BACKUP_DIR" \
  --pg-dump "$PG_BIN/pg_dump"

# manifest まで揃った組だけを残して世代を削る。
"$ROOT/infra/db/prune_backups.sh" "$db" "${RIHRP_BACKUP_KEEP:-14}"
printf '%s backup done\n' "$(date -Is)"
