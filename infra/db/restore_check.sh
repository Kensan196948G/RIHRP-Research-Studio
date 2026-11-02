#!/usr/bin/env bash
# バックアップからの復元検証（別 DB に復元し、主要テーブルの行数を比較する）。
# 使い方: infra/db/restore_check.sh <backup.dump> [restore_db]
set -euo pipefail

DUMP="${1:?バックアップファイルを指定してください}"
RESTORE_DB="${2:-rihrp_restore_check}"

dropdb --if-exists "$RESTORE_DB"
createdb "$RESTORE_DB"
pg_restore --no-owner --dbname="$RESTORE_DB" "$DUMP"

echo "restored: $RESTORE_DB"
psql -d "$RESTORE_DB" -tAc "select 'users='||count(*) from users union all select 'projects='||count(*) from projects union all select 'claims='||count(*) from claims union all select 'reports='||count(*) from reports"
