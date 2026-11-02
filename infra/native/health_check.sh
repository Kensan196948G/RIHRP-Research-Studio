#!/usr/bin/env bash
# Health Check: プロセス生存と DB/migration の readiness を確認する。
set -euo pipefail

BASE="${RIHRP_BASE_URL:-http://127.0.0.1:18110}"
fail=0

health="$(curl -fsS -m 5 "$BASE/healthz" 2>/dev/null || true)"
if [[ "$health" != *'"status": "ok"'* && "$health" != *'"status":"ok"'* ]]; then
  printf 'NG /healthz: %s\n' "${health:-no response}" >&2
  fail=1
else
  printf 'OK /healthz: %s\n' "$health"
fi

ready="$(curl -fsS -m 5 "$BASE/readyz" 2>/dev/null || true)"
if [[ "$ready" != *'"status": "ready"'* && "$ready" != *'"status":"ready"'* ]]; then
  printf 'NG /readyz: %s\n' "${ready:-no response}" >&2
  fail=1
else
  printf 'OK /readyz: %s\n' "$ready"
fi

exit "$fail"
