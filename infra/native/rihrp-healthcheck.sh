#!/usr/bin/env bash
# 5 分間隔の外形チェック（同一ホスト）。失敗時は alert.sh で通知し、非 0 で終了する。
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
ENV_FILE="${RIHRP_ENV_FILE:-$HOME/.config/rihrp/rihrp.conf}"
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a
  source "$ENV_FILE"
  set +a
fi

if "$ROOT/infra/native/health_check.sh"; then
  printf '%s healthcheck OK\n' "$(date -Is)"
  exit 0
fi

"$ROOT/infra/native/alert.sh" "healthcheck" "healthz/readyz のチェックに失敗しました"
exit 1
