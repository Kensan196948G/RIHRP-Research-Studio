#!/usr/bin/env bash
# 異常検知時の通知。通知先（RIHRP_ALERT_WEBHOOK）が未設定でも journal とローカルログに残す。
set -uo pipefail

SOURCE="${1:-unknown}"
MESSAGE="${2:-RIHRP で異常を検知しました}"
STAMP="$(date -Is)"
STATE_DIR="${RIHRP_STATE_DIR:-$HOME/.local/state/rihrp}"
mkdir -p "$STATE_DIR"

logger -t rihrp-alert -p user.err "[$SOURCE] $MESSAGE"
printf '[%s] [%s] %s\n' "$STAMP" "$SOURCE" "$MESSAGE" >>"$STATE_DIR/alerts.log"

if [[ -n "${RIHRP_ALERT_WEBHOOK:-}" ]]; then
  payload="$(printf '{"text":"[RIHRP] %s: %s (%s)"}' "$SOURCE" "$MESSAGE" "$STAMP")"
  if ! curl -fsS -m 5 -H 'Content-Type: application/json' -d "$payload" "$RIHRP_ALERT_WEBHOOK" >/dev/null; then
    logger -t rihrp-alert -p user.err "webhook への通知に失敗しました"
  fi
else
  logger -t rihrp-alert -p user.warning \
    'RIHRP_ALERT_WEBHOOK 未設定のため通知先は journal と alerts.log のみです'
fi
exit 0
