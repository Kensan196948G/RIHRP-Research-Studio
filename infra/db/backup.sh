#!/usr/bin/env bash
# PostgreSQL の論理バックアップ（pg_dump -Fc）。保持は RUNS 世代。
# 途中で失敗した場合は .part のまま残し、完成した .dump だけを公開する。
set -euo pipefail
umask 077

DB_NAME="${1:-rihrp}"
OUT_DIR="${RIHRP_BACKUP_DIR:-$HOME/.local/state/rihrp/backups}"
KEEP="${RIHRP_BACKUP_KEEP:-14}"
PG_BIN="${RIHRP_PG_BIN:-/usr/lib/postgresql/16/bin}"
PG_DUMP="$PG_BIN/pg_dump"
[[ -x "$PG_DUMP" ]] || PG_DUMP="pg_dump"

if [[ ! "$KEEP" =~ ^[1-9][0-9]*$ ]]; then
  printf 'BLOCKED: RIHRP_BACKUP_KEEP は 1 以上の整数にしてください（%s）\n' "$KEEP" >&2
  exit 2
fi

STAMP="$(date +%Y%m%dT%H%M%S)"
mkdir -p "$OUT_DIR"
chmod 700 "$OUT_DIR"
FILE="$OUT_DIR/${DB_NAME}-${STAMP}.dump"
PART="${FILE}.part"

"$PG_DUMP" -Fc --dbname="$DB_NAME" --file="$PART"
mv "$PART" "$FILE"
sha256sum "$FILE" > "${FILE}.sha256"
chmod 600 "$FILE" "${FILE}.sha256"

# 古い世代を削除する（.dump と .sha256 を同時に消す）。
mapfile -t dumps < <(
  find "$OUT_DIR" -maxdepth 1 -type f -name '*.dump' -printf '%T@ %p\n' |
    sort -rn | cut -d' ' -f2-
)
for ((i = KEEP; i < ${#dumps[@]}; i++)); do
  rm -f -- "${dumps[$i]}" "${dumps[$i]}.sha256"
done

echo "backup: $FILE"
