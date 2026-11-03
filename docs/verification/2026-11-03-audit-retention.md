# 検証記録 — 2026-11-03 監査ログ保持（365 日）と削除ジョブ

決定: 保持期間 **365 日**（ADR-0006）。削除ジョブは実装するが**既定は無効**とし、
人間の承認後に有効化する。

## 1. 実装

- `python -m rihrp.maintenance purge-audit --days 365`（**dry-run**、件数のみ）
- `... purge-audit --days 365 --commit`（削除。`RIHRP_ALLOW_AUDIT_PURGE=1` が必要）
- 所有者ロール（`RIHRP_MIGRATION_DATABASE_URL`）で 1 トランザクション内に
  `ALTER TABLE audit_events DISABLE TRIGGER trg_audit_immutable` → バッチ削除 →
  `ENABLE TRIGGER` を実行。失敗時はロールバックでトリガーが戻る。
- systemd: `rihrp-audit-purge.service/.timer` を追加。インストーラは配置するが
  **timer を有効化しない**（承認後に手動で `enable --now`）。

## 2. テスト（pytest）

`tests/integration/test_maintenance.py::test_purge_audit_dry_run_then_commit`

- 400 日前と現在の監査イベントを用意。
- dry-run: `eligible=1` / `deleted=0`、行数は 2 のまま。
- commit: `deleted=1` / `remaining=1`、残るのは新しいイベントのみ。
- 削除後に `DELETE FROM audit_events` を試すと **append-only トリガーで失敗**する
  （トリガーが再有効化されていることの確認）。

実測: 上記テストが pass（`pytest -k purge_audit`）。全体は 149 collected / 148 passed / 1 skipped。

## 3. 本番の dry-run（読み取りのみ）

```
$ .venv/bin/python -m rihrp.maintenance purge-audit --days 365
audit purge: retention_days=365 total=19 eligible=0 deleted=0
```

現時点で保持期間を超えるイベントは 0 件のため、有効化しても削除は発生しない。

## 4. 有効化の条件（人間）

1. 保持方針 365 日を承認する。
2. 実行前のバックアップを取得する（`infra/native/rihrp-backup.sh`）。
3. `systemctl --user enable --now rihrp-audit-purge.timer` を実行する。
4. 初回実行後に `journalctl --user -u rihrp-audit-purge.service` と
   `audit-stats` の件数を確認する。
