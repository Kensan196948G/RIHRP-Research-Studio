#!/usr/bin/env bash
# ローカル PostgreSQL に役割と DB を作る（冪等）。
# 使い方: RIHRP_DB_PASSWORD='...' infra/db/bootstrap.sh [db_name] [app_role]
#   RIHRP_DB_OWNER を指定すると所有者とアプリロールを分離する（RIHRP_DB_OWNER_PASSWORD 必須）。
#   migration は所有者ロールで実行し、アプリは DML のみとする。
set -euo pipefail

DB_NAME="${1:-rihrp}"
DB_ROLE="${2:-rihrp_app}"
DB_OWNER="${RIHRP_DB_OWNER:-$DB_ROLE}"
: "${RIHRP_DB_PASSWORD:?RIHRP_DB_PASSWORD を設定してください}"
if [[ "$DB_OWNER" != "$DB_ROLE" ]]; then
  : "${RIHRP_DB_OWNER_PASSWORD:?RIHRP_DB_OWNER を分離する場合は RIHRP_DB_OWNER_PASSWORD が必要です}"
fi
for name in "$DB_NAME" "$DB_ROLE" "$DB_OWNER"; do
  if [[ ! "$name" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
    printf 'BLOCKED: 識別子に使用できない文字が含まれています（%s）\n' "$name" >&2
    exit 2
  fi
done

create_role() {
  local role="$1" password="$2"
  psql -d postgres -v ON_ERROR_STOP=1 -v role="$role" -v pwd="$password" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'role', :'pwd')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'role') \gexec
SQL
}

create_role "$DB_OWNER" "${RIHRP_DB_OWNER_PASSWORD:-$RIHRP_DB_PASSWORD}"
if [[ "$DB_OWNER" != "$DB_ROLE" ]]; then
  create_role "$DB_ROLE" "$RIHRP_DB_PASSWORD"
fi

database_exists() {
  # 呼び出し前に ^[A-Za-z_][A-Za-z0-9_]*$ を検証済みのため、リテラル連結は安全。
  psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$1'" | grep -q 1
}

if ! database_exists "$DB_NAME"; then
  createdb -O "$DB_OWNER" "$DB_NAME"
fi
if [[ "$DB_NAME" != *_test && "$DB_NAME" != "rihrp_test" ]]; then
  if ! database_exists "${DB_NAME}_test"; then
    createdb -O "$DB_OWNER" "${DB_NAME}_test"
  fi
fi

if [[ "$DB_OWNER" != "$DB_ROLE" ]]; then
  dbs=("$DB_NAME")
  if [[ "$DB_NAME" != *_test && "$DB_NAME" != "rihrp_test" ]]; then
    dbs+=("${DB_NAME}_test")
  fi
  for db in "${dbs[@]}"; do
    if database_exists "$db"; then
      psql -d "$db" -v ON_ERROR_STOP=1 -v owner="$DB_OWNER" -v app="$DB_ROLE" <<'SQL'
GRANT USAGE ON SCHEMA public TO :"app";
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app";
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO :"app";
REVOKE CREATE ON SCHEMA public FROM :"app";
SQL
    fi
  done
fi
echo "bootstrap ok: db=${DB_NAME} owner=${DB_OWNER} app=${DB_ROLE}"
