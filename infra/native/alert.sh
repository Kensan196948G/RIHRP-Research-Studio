#!/usr/bin/env bash
# 異常検知時の通知。通知先（RIHRP_ALERT_WEBHOOK）が未設定でも journal とローカルログに残す。
set -uo pipefail
umask 077

SOURCE="${1:-unknown}"
MESSAGE="${2:-RIHRP で異常を検知しました}"
STAMP="$(date -Is)"
STATE_DIR="${RIHRP_STATE_DIR:-$HOME/.local/state/rihrp}"
mkdir -p "$STATE_DIR" || exit 1

logger -t rihrp-alert -p user.err "[$SOURCE] $MESSAGE"
if ! printf '[%s] [%s] %s\n' "$STAMP" "$SOURCE" "$MESSAGE" >>"$STATE_DIR/alerts.log"; then
  logger -t rihrp-alert -p user.err "alerts.log への記録に失敗しました"
  exit 1
fi

if [[ -n "${RIHRP_ALERT_WEBHOOK:-}" ]]; then
  payload="$(
    python3 -c 'import json,sys; print(json.dumps({"text": f"[RIHRP] {sys.argv[1]}: {sys.argv[2]} ({sys.argv[3]})"}))' \
      "$SOURCE" "$MESSAGE" "$STAMP"
  )" || {
    logger -t rihrp-alert -p user.err "通知 JSON の生成に失敗しました"
    exit 1
  }
  if ! curl -fsS -m 5 -H 'Content-Type: application/json' -d "$payload" "$RIHRP_ALERT_WEBHOOK" >/dev/null; then
    logger -t rihrp-alert -p user.err "webhook への通知に失敗しました"
    exit 1
  fi
else
  logger -t rihrp-alert -p user.warning \
    'RIHRP_ALERT_WEBHOOK 未設定のため通知先は journal と alerts.log のみです'
fi
exit 0
