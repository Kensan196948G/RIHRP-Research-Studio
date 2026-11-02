#!/usr/bin/env bash
# ローカル PostgreSQL に役割と DB を作る（冪等）。
# 使い方: RIHRP_DB_PASSWORD='...' infra/db/bootstrap.sh [db_name] [role]
set -euo pipefail

DB_NAME="${1:-rihrp}"
DB_ROLE="${2:-rihrp_app}"
: "${RIHRP_DB_PASSWORD:?RIHRP_DB_PASSWORD を設定してください}"

# 識別子・リテラルは psql の format('%I','%L') で安全に組み立てる（SQL 注入防止）。
psql -d postgres -v ON_ERROR_STOP=1 -v role="$DB_ROLE" -v pwd="$RIHRP_DB_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'role', :'pwd')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'role') \gexec
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
