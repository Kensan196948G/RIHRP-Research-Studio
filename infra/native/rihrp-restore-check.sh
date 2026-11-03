#!/usr/bin/env bash
# 最新バックアップからの復元訓練（systemd timer から週次実行）。
# 対象 DB の最新 dump と manifest を選び、チェックサム・migration・
# 「バックアップ時点の件数」を検証する。成功時は復元 DB を削除する。
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

BACKUP_DIR="${RIHRP_BACKUP_DIR:-$HOME/.local/state/rihrp/backups}"
DUMP="$(
  find "$BACKUP_DIR" -maxdepth 1 -type f -name "${db}-*.dump" -printf '%T@ %p\n' 2>/dev/null |
    sort -rn | head -n 1 | cut -d' ' -f2-
)"
[[ -n "$DUMP" ]] || {
  printf 'NG: %s に %s のバックアップがありません\n' "$BACKUP_DIR" "$db" >&2
  exit 1
}
MANIFEST="${DUMP}.manifest.json"
[[ -f "$MANIFEST" ]] || {
  printf 'NG: manifest がありません（%s）。先にバックアップを実行してください。\n' "$MANIFEST" >&2
  exit 1
}

STATE_DIR="${RIHRP_STATE_DIR:-$HOME/.local/state/rihrp}"
mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR"
LOG="$STATE_DIR/last-restore-check.log"

printf '%s restore check start dump=%s source=%s\n' "$(date -Is)" "$(basename "$DUMP")" "$db"
if RIHRP_SOURCE_DB="$db" "$ROOT/infra/db/restore_check.sh" "$DUMP" rihrp_restore_check "$MANIFEST" >"$LOG" 2>&1; then
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
