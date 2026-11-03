#!/usr/bin/env bash
# バックアップからの復元検証（破壊的: 専用の復元DBのみを作り直す）。
# 使い方: infra/db/restore_check.sh <backup.dump> [restore_db] [manifest.json]
#   restore_db は rihrp_restore_ で始まる名前だけ許可する。
#   manifest を指定した場合: SHA-256 と「バックアップ時点」の件数・migration を検証する。
#   manifest 省略時: 現在の RIHRP_SOURCE_DB と件数を比較する（バックアップ後の更新で
#   差分が出るため、直後に検証する場合に限る）。
set -euo pipefail
umask 077

DUMP="${1:?バックアップファイルを指定してください}"
RESTORE_DB="${2:-rihrp_restore_check}"
MANIFEST="${3:-}"
SOURCE_DB="${RIHRP_SOURCE_DB:-rihrp}"
PG_BIN="${RIHRP_PG_BIN:-/usr/lib/postgresql/16/bin}"
PG_RESTORE="$PG_BIN/pg_restore"
[[ -x "$PG_RESTORE" ]] || PG_RESTORE="pg_restore"

if [[ "$RESTORE_DB" != rihrp_restore_* || "$RESTORE_DB" == "$SOURCE_DB" ]]; then
  printf 'BLOCKED: 復元先は rihrp_restore_ で始まる専用DBに限ります（指定: %s）\n' "$RESTORE_DB" >&2
  exit 2
fi
if [[ -n "$MANIFEST" && ! -f "$MANIFEST" ]]; then
  printf 'BLOCKED: manifest がありません（%s）\n' "$MANIFEST" >&2
  exit 2
fi

if [[ -n "$MANIFEST" ]]; then
  printf '== verify checksum %s\n' "$(basename "$DUMP")"
  (cd "$(dirname "$DUMP")" && sha256sum -c "$(basename "$DUMP").sha256")
fi

printf '== restore %s -> %s\n' "$DUMP" "$RESTORE_DB"
dropdb --if-exists "$RESTORE_DB"
createdb "$RESTORE_DB"
"$PG_RESTORE" --no-owner --dbname="$RESTORE_DB" "$DUMP"

fail=0
if [[ -n "$MANIFEST" ]]; then
  expected_migration="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["migration"])' "$MANIFEST")"
  restored_migration="$(psql -d "$RESTORE_DB" -tAc 'SELECT version_num FROM alembic_version')"
  printf '%-14s %10s %10s\n' "table" "expected" "restored"
  if [[ "$expected_migration" != "$restored_migration" ]]; then
    printf '%-14s %10s %10s\n' "migration" "$expected_migration" "$restored_migration"
    fail=1
  fi
  while IFS=' ' read -r table expected; do
    restored_count="$(psql -d "$RESTORE_DB" -tAc "SELECT count(*) FROM $table")"
    printf '%-14s %10s %10s\n' "$table" "$expected" "$restored_count"
    if [[ "$expected" != "$restored_count" ]]; then
      fail=1
    fi
  done < <(
    python3 - "$MANIFEST" <<'PY'
import json
import sys

counts = json.load(open(sys.argv[1], encoding="utf-8"))["counts"]
for table in ("users", "projects", "sources", "claims", "reports", "audit_events"):
    print(table, counts[table])
PY
  )
else
  printf '%-14s %10s %10s\n' "table" "source" "restored"
  for table in users projects sources claims reports audit_events; do
    source_count="$(psql -d "$SOURCE_DB" -tAc "SELECT count(*) FROM $table")"
    restored_count="$(psql -d "$RESTORE_DB" -tAc "SELECT count(*) FROM $table")"
    printf '%-14s %10s %10s\n' "$table" "$source_count" "$restored_count"
    if [[ "$source_count" != "$restored_count" ]]; then
      fail=1
    fi
  done
fi

if [[ "$fail" -ne 0 ]]; then
  printf 'NG: 復元後の件数が期待値と一致しません\n' >&2
  exit 1
fi
printf 'restore check: OK\n'
