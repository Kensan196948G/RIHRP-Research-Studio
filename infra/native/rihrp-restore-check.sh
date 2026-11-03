#!/usr/bin/env bash
# 最新バックアップからの復元訓練（systemd timer から週次実行）。
# 専用の復元 DB を作り直し、業務テーブルの件数を比較する。成功時は復元 DB を削除する。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
ENV_FILE="${RIHRP_ENV_FILE:-$HOME/.config/rihrp/rihrp.conf}"
[[ -f "$ENV_FILE" ]] || {
  printf 'BLOCKED: %s がありません\n' "$ENV_FILE" >&2
  exit 1
}
# shellcheck disable=SC1090
set -a
source "$ENV_FILE"
set +a
: "${RIHRP_DATABASE_URL:?RIHRP_DATABASE_URL が必要です}"

url="${RIHRP_DATABASE_URL%%\?*}"
db="${url##*/}"
[[ "$db" == rihrp* ]] || {
  printf 'BLOCKED: DB 名が想定外です（%s）\n' "$db" >&2
  exit 2
}

BACKUP_DIR="${RIHRP_BACKUP_DIR:-$HOME/.local/state/rihrp/backups}"
DUMP="$(ls -1t "$BACKUP_DIR"/*.dump 2>/dev/null | head -n 1 || true)"
[[ -n "$DUMP" ]] || {
  printf 'NG: %s にバックアップがありません\n' "$BACKUP_DIR" >&2
  exit 1
}

STATE_DIR="${RIHRP_STATE_DIR:-$HOME/.local/state/rihrp}"
mkdir -p "$STATE_DIR"
LOG="$STATE_DIR/last-restore-check.log"

printf '%s restore check start dump=%s source=%s\n' "$(date -Is)" "$(basename "$DUMP")" "$db"
if RIHRP_SOURCE_DB="$db" "$ROOT/infra/db/restore_check.sh" "$DUMP" rihrp_restore_check >"$LOG" 2>&1; then
  cat "$LOG"
  if [[ "${RIHRP_RESTORE_KEEP_DB:-0}" != "1" ]]; then
    dropdb --if-exists rihrp_restore_check
  fi
  printf '%s restore check OK\n' "$(date -Is)"
else
  status=$?
  cat "$LOG" >&2
  printf '%s restore check FAILED（復元 DB を調査用に残します）\n' "$(date -Is)" >&2
  exit "$status"
fi
