#!/usr/bin/env bash
# ローカル PostgreSQL に役割と DB を作る（冪等）。
# 使い方: RIHRP_DB_PASSWORD='...' infra/db/bootstrap.sh [db_name] [role]
set -euo pipefail

DB_NAME="${1:-rihrp}"
DB_ROLE="${2:-rihrp_app}"
: "${RIHRP_DB_PASSWORD:?RIHRP_DB_PASSWORD を設定してください}"

psql -d postgres -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${DB_ROLE}') THEN
    CREATE ROLE ${DB_ROLE} LOGIN PASSWORD '${RIHRP_DB_PASSWORD}';
  END IF;
END
\$\$;
SQL

if ! psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1; then
  createdb -O "${DB_ROLE}" "${DB_NAME}"
fi
if [[ "${DB_NAME}" != *_test && "${DB_NAME}" != "rihrp_test" ]]; then
  if ! psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}_test'" | grep -q 1; then
    createdb -O "${DB_ROLE}" "${DB_NAME}_test"
  fi
fi
echo "bootstrap ok: role=${DB_ROLE} db=${DB_NAME}"
