#!/usr/bin/env bash
# 指定 DB のバックアップ世代を保持数まで削る（他の DB・不完全な組には触れない）。
# 使い方: infra/db/prune_backups.sh <db> [keep]
#   - 保持対象は「dump + .sha256 + manifest（db が一致）」の完全な組だけ。
#   - 1 日以上経過した不完全な組・孤児 sidecar・.part/.tmp は掃除する。
#   - RIHRP_BACKUP_DIR で保存先を変更できる（既定 ~/.local/state/rihrp/backups）。
set -euo pipefail
umask 077

DB_NAME="${1:?DB 名を指定してください}"
KEEP="${2:-${RIHRP_BACKUP_KEEP:-14}}"
OUT_DIR="${RIHRP_BACKUP_DIR:-$HOME/.local/state/rihrp/backups}"

[[ "$DB_NAME" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || {
  printf 'BLOCKED: DB 名が不正です（%s）\n' "$DB_NAME" >&2
  exit 2
}
[[ "$KEEP" =~ ^[1-9][0-9]*$ ]] || {
  printf 'BLOCKED: 保持数は 1 以上の整数にしてください（%s）\n' "$KEEP" >&2
  exit 2
}
[[ -d "$OUT_DIR" ]] || exit 0

# ファイル名は「<db>-<日時>[-<pid>].dump」。前方一致ではなく日時部分まで検証する。
NAME_RE="^${DB_NAME}-[0-9]{8}T[0-9]+(-[0-9]+)?\\.dump$"
manifest_db() {
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("db",""))' "$1"
}

complete=()
all_dumps=()
for path in "$OUT_DIR"/*.dump; do
  [[ -f "$path" ]] || continue
  base="$(basename "$path")"
  [[ "$base" =~ $NAME_RE ]] || continue
  all_dumps+=("$path")
  [[ -f "${path}.sha256" && -f "${path}.manifest.json" ]] || continue
  [[ "$(manifest_db "${path}.manifest.json")" == "$DB_NAME" ]] || continue
  complete+=("$path")
done

# 新しい順に並べ、KEEP を超えた完全な組だけを削除する。
sorted=()
if ((${#complete[@]})); then
  mapfile -t sorted < <(printf '%s\n' "${complete[@]}" | sort -r)
fi
for ((i = KEEP; i < ${#sorted[@]}; i++)); do
  rm -f -- "${sorted[$i]}" "${sorted[$i]}.sha256" "${sorted[$i]}.manifest.json"
done
kept=${#sorted[@]}
((kept > KEEP)) && kept=$KEEP

# 孤児（dump が無い sidecar）は即時、不完全な組・残骸は 1 日経過後に削除する。
for sidecar in "$OUT_DIR"/*.sha256 "$OUT_DIR"/*.manifest.json; do
  [[ -f "$sidecar" ]] || continue
  dump="${sidecar%.sha256}"
  dump="${dump%.manifest.json}"
  [[ -f "$dump" ]] || rm -f -- "$sidecar"
done
for path in "${all_dumps[@]}"; do
  [[ -f "${path}.manifest.json" && -f "${path}.sha256" ]] && continue
  if [[ -f "$path" ]] && [[ "$(find "$path" -maxdepth 0 -mtime +0 -print -quit)" ]]; then
    rm -f -- "$path"
  fi
  find "${path}.sha256" "${path}.manifest.json" -maxdepth 0 -mtime +0 -delete 2>/dev/null || true
done
find "$OUT_DIR" -maxdepth 1 -type f \
  \( -name "${DB_NAME}-*.dump.part" -o -name "${DB_NAME}-*.dump.part.tmp" \
     -o -name "${DB_NAME}-*.sha256.tmp" -o -name "${DB_NAME}-*.manifest.json.tmp" \) \
  -mtime +0 -delete

printf 'pruned: %s（完全な組 %s 世代を保持）\n' "$DB_NAME" "$kept"
