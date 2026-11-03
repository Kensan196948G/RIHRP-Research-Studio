#!/usr/bin/env bash
# 本番 DB の日次バックアップ（systemd timer から実行）。
# DB 名は ~/.config/rihrp/rihrp.conf の RIHRP_DATABASE_URL から導出する。
# バックアップ時点の件数を manifest に残し、復元訓練はこの値と比較する
# （現在の本番件数と比較すると、バックアップ後の通常更新で誤検知するため）。
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
ENV_FILE="${RIHRP_ENV_FILE:-$HOME/.config/rihrp/rihrp.conf}"
[[ -f "$ENV_FILE" ]] || {
  printf 'BLOCKED: %s がありません\n' "$ENV_FILE" >&2
  exit 1
}
set -a
# shellcheck source=/dev/null
source "$ENV_FILE"
set +a
: "${RIHRP_DATABASE_URL:?RIHRP_DATABASE_URL が必要です}"

url="${RIHRP_DATABASE_URL%%\?*}"
db="${url##*/}"
[[ "$db" == rihrp* ]] || {
  printf 'BLOCKED: DB 名が想定外です（%s）\n' "$db" >&2
  exit 2
}

# 前提: このユニットを実行する OS ユーザーが対象 DB に接続できること
# （本番ホストではローカル peer 認証。詳細は docs/runbooks/operations.md）。
if ! psql -d "$db" -tAc 'SELECT 1' >/dev/null 2>&1; then
  printf 'BLOCKED: OS ユーザーから %s に接続できません\n' "$db" >&2
  exit 3
fi

printf '%s backup start db=%s\n' "$(date -Is)" "$db"
output="$("$ROOT/infra/db/backup.sh" "$db")"
printf '%s\n' "$output"
dump="${output##*backup: }"
[[ -f "$dump" ]] || {
  printf 'BLOCKED: バックアップファイルを特定できません（%s）\n' "$dump" >&2
  exit 4
}

counts="$(psql -d "$db" -tAc "
  SELECT json_build_object(
    'users', (SELECT count(*) FROM users),
    'projects', (SELECT count(*) FROM projects),
    'sources', (SELECT count(*) FROM sources),
    'claims', (SELECT count(*) FROM claims),
    'reports', (SELECT count(*) FROM reports),
    'audit_events', (SELECT count(*) FROM audit_events)
  )::text")"
migration="$(psql -d "$db" -tAc 'SELECT version_num FROM alembic_version')"
sha256="$(cut -d' ' -f1 "${dump}.sha256")"

python3 - "$dump" "$db" "$migration" "$sha256" "$counts" <<'PY'
import json
import sys
from datetime import datetime, timezone

dump, db, migration, sha256, counts = sys.argv[1:6]
manifest = {
    "db": db,
    "dump": dump.rsplit("/", 1)[-1],
    "sha256": sha256,
    "migration": migration,
    "created_at": datetime.now(timezone.utc).isoformat(),
    "counts": json.loads(counts),
}
path = f"{dump}.manifest.json"
with open(path, "w", encoding="utf-8") as fh:
    json.dump(manifest, fh, ensure_ascii=False, indent=2, sort_keys=True)
print(f"manifest: {path}")
PY

printf '%s backup done\n' "$(date -Is)"
