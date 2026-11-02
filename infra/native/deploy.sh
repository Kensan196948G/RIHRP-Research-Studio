#!/usr/bin/env bash
# ローカル配備: 依存同期 → migration → Web ビルド → systemd user unit 再起動 → health check。
# 使い方: infra/native/deploy.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
ENV_FILE="${RIHRP_ENV_FILE:-$HOME/.config/rihrp/rihrp.conf}"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

[[ -f "$ENV_FILE" ]] || {
  printf 'BLOCKED: %s がありません（RIHRP_DATABASE_URL 等を設定してください）\n' "$ENV_FILE" >&2
  exit 1
}
# shellcheck disable=SC1090
set -a
source "$ENV_FILE"
set +a
: "${RIHRP_DATABASE_URL:?RIHRP_DATABASE_URL が必要です}"

cd "$ROOT"
printf '== 依存（Python）\n'
.venv/bin/pip install -q -e ".[dev]"

printf '== migration\n'
(
  cd infra/migrations
  RIHRP_DATABASE_URL="$RIHRP_DATABASE_URL" ../../.venv/bin/alembic upgrade head
)

printf '== Web ビルド\n'
(
  cd apps/web
  npm ci --no-audit --no-fund >/dev/null
  npm run build >/dev/null
)

printf '== systemd user unit\n'
mkdir -p "$UNIT_DIR"
install -m 0644 infra/native/rihrp.service "$UNIT_DIR/rihrp.service"
systemctl --user daemon-reload
systemctl --user enable rihrp.service >/dev/null
systemctl --user restart rihrp.service
for i in $(seq 1 20); do
  if infra/native/health_check.sh >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

printf '== health check\n'
infra/native/health_check.sh
printf 'deployed: %s\n' "$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo 'no-git')"
