#!/usr/bin/env bash
# 運用用の systemd user unit（バックアップ・復元訓練・セッション削除・外形チェック）を導入する。
# 使い方: infra/native/install_ops_units.sh [--dry-run]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNITS=(
  rihrp-backup.service
  rihrp-backup.timer
  rihrp-restore-check.service
  rihrp-restore-check.timer
  rihrp-maintenance.service
  rihrp-maintenance.timer
  rihrp-healthcheck.service
  rihrp-healthcheck.timer
)
TIMERS=(rihrp-backup.timer rihrp-restore-check.timer rihrp-maintenance.timer rihrp-healthcheck.timer)

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  for unit in "${UNITS[@]}"; do
    printf 'would install: %s -> %s\n' "$ROOT/infra/native/$unit" "$UNIT_DIR/$unit"
  done
  printf 'would run: systemctl --user daemon-reload\n'
  printf 'would run: systemctl --user enable --now %s\n' "${TIMERS[*]}"
  exit 0
fi

mkdir -p "$UNIT_DIR"
for unit in "${UNITS[@]}"; do
  install -m 0644 "$ROOT/infra/native/$unit" "$UNIT_DIR/$unit"
done

systemctl --user daemon-reload
for timer in "${TIMERS[@]}"; do
  systemctl --user enable --now "$timer"
done

systemctl --user list-timers 'rihrp-*' --all --no-pager
