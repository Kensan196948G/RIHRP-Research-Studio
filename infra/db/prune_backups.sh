#!/usr/bin/env bash
# 指定 DB のバックアップ世代を保持数まで削る（他の DB の dump には触れない）。
# 使い方: infra/db/prune_backups.sh <db> [keep]
#   RIHRP_BACKUP_DIR で保存先を変更できる（既定 ~/.local/state/rihrp/backups）。
set -euo pipefail

DB_NAME="${1:?DB 名を指定してください}"
KEEP="${2:-${RIHRP_BACKUP_KEEP:-14}}"
OUT_DIR="${RIHRP_BACKUP_DIR:-$HOME/.local/state/rihrp/backups}"

[[ "$KEEP" =~ ^[1-9][0-9]*$ ]] || {
  printf 'BLOCKED: 保持数は 1 以上の整数にしてください（%s）\n' "$KEEP" >&2
  exit 2
}
[[ -d "$OUT_DIR" ]] || exit 0

mapfile -t dumps < <(
  find "$OUT_DIR" -maxdepth 1 -type f -name "${DB_NAME}-*.dump" -printf '%T@ %p\n' |
    sort -rn | cut -d' ' -f2-
)
for ((i = KEEP; i < ${#dumps[@]}; i++)); do
  rm -f -- "${dumps[$i]}" "${dumps[$i]}.sha256" "${dumps[$i]}.manifest.json"
done

# 失敗したバックアップの残骸（.part / .tmp）を 1 日以上経過したものに限って掃除する。
find "$OUT_DIR" -maxdepth 1 -type f \
  \( -name "${DB_NAME}-*.dump.part" -o -name "${DB_NAME}-*.dump.part.tmp" -o -name "${DB_NAME}-*.manifest.json.tmp" \) \
  -mtime +0 -delete

printf 'pruned: %s（保持 %s 世代）\n' "$DB_NAME" "$KEEP"
