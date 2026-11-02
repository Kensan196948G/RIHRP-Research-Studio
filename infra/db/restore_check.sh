#!/usr/bin/env bash
# バックアップからの復元検証（破壊的: 専用の復元DBのみを作り直す）。
# 使い方: infra/db/restore_check.sh <backup.dump> [restore_db]
#   restore_db は rihrp_restore_ で始まる名前だけ許可する。
#   比較元は RIHRP_SOURCE_DB（既定 rihrp）。
set -euo pipefail

DUMP="${1:?バックアップファイルを指定してください}"
RESTORE_DB="${2:-rihrp_restore_check}"
SOURCE_DB="${RIHRP_SOURCE_DB:-rihrp}"
PG_BIN="${RIHRP_PG_BIN:-/usr/lib/postgresql/16/bin}"
PG_RESTORE="$PG_BIN/pg_restore"
[[ -x "$PG_RESTORE" ]] || PG_RESTORE="pg_restore"

if [[ "$RESTORE_DB" != rihrp_restore_* || "$RESTORE_DB" == "$SOURCE_DB" ]]; then
  printf 'BLOCKED: 復元先は rihrp_restore_ で始まる専用DBに限ります（指定: %s）\n' "$RESTORE_DB" >&2
  exit 2
fi

printf '== restore %s -> %s\n' "$DUMP" "$RESTORE_DB"
dropdb --if-exists "$RESTORE_DB"
createdb "$RESTORE_DB"
"$PG_RESTORE" --no-owner --dbname="$RESTORE_DB" "$DUMP"

fail=0
printf '%-14s %10s %10s\n' "table" "source" "restored"
for table in users projects sources claims reports audit_events; do
  source_count="$(psql -d "$SOURCE_DB" -tAc "SELECT count(*) FROM $table")"
  restored_count="$(psql -d "$RESTORE_DB" -tAc "SELECT count(*) FROM $table")"
  printf '%-14s %10s %10s\n' "$table" "$source_count" "$restored_count"
  if [[ "$source_count" != "$restored_count" ]]; then
    fail=1
  fi
done

if [[ "$fail" -ne 0 ]]; then
  printf 'NG: 復元後の件数が元DBと一致しません\n' >&2
  exit 1
fi
printf 'restore check: OK\n'
