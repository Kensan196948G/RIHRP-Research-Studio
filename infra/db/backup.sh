#!/usr/bin/env bash
# 単体の論理バックアップ（pg_dump -Fc）。世代管理は行わない（prune_backups.sh を使う）。
# 途中で失敗した場合は .part のまま残し、完成した .dump だけを公開する。
set -euo pipefail
umask 077

DB_NAME="${1:-rihrp}"
OUT_DIR="${RIHRP_BACKUP_DIR:-$HOME/.local/state/rihrp/backups}"
PG_BIN="${RIHRP_PG_BIN:-/usr/lib/postgresql/16/bin}"
PG_DUMP="$PG_BIN/pg_dump"
[[ -x "$PG_DUMP" ]] || PG_DUMP="pg_dump"

STAMP="$(date +%Y%m%dT%H%M%S)"
mkdir -p "$OUT_DIR"
chmod 700 "$OUT_DIR"
FILE="$OUT_DIR/${DB_NAME}-${STAMP}.dump"
PART="${FILE}.part"

"$PG_DUMP" -Fc --dbname="$DB_NAME" --file="$PART"
mv "$PART" "$FILE"
# チェックサムは basename で記録し、ディレクトリ移動後も検証できるようにする。
(cd "$OUT_DIR" && sha256sum "$(basename "$FILE")" > "$(basename "$FILE").sha256")
chmod 600 "$FILE" "${FILE}.sha256"

echo "backup: $FILE"
