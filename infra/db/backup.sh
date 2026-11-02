#!/usr/bin/env bash
# PostgreSQL の論理バックアップ（pg_dump -Fc）。保持は RUNS 世代。
set -euo pipefail

DB_NAME="${1:-rihrp}"
OUT_DIR="${RIHRP_BACKUP_DIR:-$HOME/.local/state/rihrp/backups}"
STAMP="$(date +%Y%m%dT%H%M%S)"
mkdir -p "$OUT_DIR"
FILE="$OUT_DIR/${DB_NAME}-${STAMP}.dump"
pg_dump -Fc --dbname="$DB_NAME" --file="$FILE"
sha256sum "$FILE" > "$FILE.sha256"
echo "backup: $FILE"
ls -1t "$OUT_DIR"/*.dump | tail -n +"$((${RIHRP_BACKUP_KEEP:-14} + 1))" | xargs -r rm -f
