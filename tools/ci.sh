#!/usr/bin/env bash
# CI 相当のローカル検証（GitHub Actions が使えない環境向け）。
# 使い方: tools/ci.sh [--no-install]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT"
INSTALL=1
[[ "${1:-}" == "--no-install" ]] && INSTALL=0

printf '== ruff check\n'
.venv/bin/ruff check apps/api tests infra/native/backup_manifest.py
printf '== ruff format --check\n'
.venv/bin/ruff format --check apps/api tests infra/native/backup_manifest.py
printf '== openapi drift\n'
.venv/bin/python infra/db/export_openapi.py --check
printf '== pytest（実 PostgreSQL rihrp_test）\n'
.venv/bin/python -m pytest

printf '== web\n'
cd apps/web
if [[ "$INSTALL" == "1" ]]; then
  npm ci --no-audit --no-fund >/dev/null
fi
npx tsc -b
npx vitest run
npm run build
printf 'CI-equivalent checks: OK\n'
