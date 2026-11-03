#!/usr/bin/env bash
# 指定 DB のバックアップ世代を保持数まで削る（他の DB・不完全な組には触れない）。
# 使い方: infra/db/prune_backups.sh <db> [keep]
#   - 保持対象は「dump + .sha256 + manifest（db が一致）」の完全な組だけ。
#   - 1 日以上経過した不完全な組・孤児 sidecar・.part/.tmp は掃除する。
#   - すべての削除対象は DB 名の厳密な境界（<db>-<日時>[-<pid>]）で照合する。
#   - RIHRP_BACKUP_DIR で保存先を変更できる（既定 ~/.local/state/rihrp/backups）。
set -euo pipefail
umask 077

DB_NAME="${1:?DB 名を指定してください}"
KEEP="${2:-${RIHRP_BACKUP_KEEP:-14}}"
OUT_DIR="${RIHRP_BACKUP_DIR:-$HOME/.local/state/rihrp/backups}"

[[ "$DB_NAME" =~ ^[A-Za-z_][A-Za-z0-9_-]*$ ]] || {
  printf 'BLOCKED: DB 名が不正です（%s）\n' "$DB_NAME" >&2
  exit 2
}
[[ "$KEEP" =~ ^[1-9][0-9]*$ ]] || {
  printf 'BLOCKED: 保持数は 1 以上の整数にしてください（%s）\n' "$KEEP" >&2
  exit 2
}
[[ -d "$OUT_DIR" ]] || exit 0

NAME_RE="^${DB_NAME}-[0-9]{8}T[0-9]+(-[0-9]+)?\\.dump$"
SIDECAR_RE="^${DB_NAME}-[0-9]{8}T[0-9]+(-[0-9]+)?\\.dump\\.(sha256|manifest\\.json)$"
RESIDUAL_RE="^${DB_NAME}-[0-9]{8}T[0-9]+(-[0-9]+)?\\.dump\\.(part|part\\.tmp|sha256\\.tmp|manifest\\.json\\.tmp)$"
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

# 孤児 sidecar（dump が無い）は、対象 DB の厳密な名前のものだけを削除する。
for sidecar in "$OUT_DIR"/*.sha256 "$OUT_DIR"/*.manifest.json; do
  [[ -f "$sidecar" ]] || continue
  base="$(basename "$sidecar")"
  [[ "$base" =~ $SIDECAR_RE ]] || continue
  dump="${sidecar%.sha256}"
  dump="${dump%.manifest.json}"
  [[ -f "$dump" ]] || rm -f -- "$sidecar"
done

# 不完全な組（sidecar 欠け）は 1 日経過後に削除する。
for path in "${all_dumps[@]}"; do
  [[ -f "$path" ]] || continue
  if [[ -f "${path}.manifest.json" && -f "${path}.sha256" ]]; then
    continue
  fi
  if [[ "$(find "$path" -maxdepth 0 -mtime +0 -print -quit)" ]]; then
    rm -f -- "$path" "${path}.sha256" "${path}.manifest.json"
  fi
done

# 失敗したバックアップの残骸（.part / .tmp）も、厳密な名前のものだけを 1 日後に削除する。
for path in "$OUT_DIR"/*; do
  [[ -f "$path" ]] || continue
  base="$(basename "$path")"
  [[ "$base" =~ $RESIDUAL_RE ]] || continue
  find "$path" -maxdepth 0 -mtime +0 -delete
done

printf 'pruned: %s（完全な組 %s 世代を保持）\n' "$DB_NAME" "$kept"
