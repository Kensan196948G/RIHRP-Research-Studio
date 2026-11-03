#!/usr/bin/env bash
# 本番 DB の日次バックアップ（systemd timer から実行）。
# DB 名は ~/.config/rihrp/rihrp.conf の RIHRP_DATABASE_URL から導出する。
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

printf '%s backup start db=%s\n' "$(date -Is)" "$db"
"$ROOT/infra/db/backup.sh" "$db"
printf '%s backup done\n' "$(date -Is)"
