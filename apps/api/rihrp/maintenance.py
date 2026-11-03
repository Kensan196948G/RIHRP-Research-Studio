"""運用向け保守コマンド。秘密は環境変数から読む。

RIHRP_DATABASE_URL=... .venv/bin/python -m rihrp.maintenance purge-sessions --days 7
RIHRP_DATABASE_URL=... .venv/bin/python -m rihrp.maintenance audit-stats
RIHRP_DATABASE_URL=... RIHRP_MIGRATION_DATABASE_URL=... \
  .venv/bin/python -m rihrp.maintenance purge-audit --days 365          # dry-run
RIHRP_ALLOW_AUDIT_PURGE=1 RIHRP_DATABASE_URL=... RIHRP_MIGRATION_DATABASE_URL=... \
  .venv/bin/python -m rihrp.maintenance purge-audit --days 365 --commit # 削除（承認時のみ）
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import timedelta

from sqlalchemy import create_engine, delete, func, select, text

from .auth import utcnow
from .config import get_settings
from .db import SessionLocal
from .models import AuditEvent
from .models import Session as SessionRow


def purge_sessions(days: int = 7) -> int:
    """期限切れから days 日以上経過したセッションを削除し、件数を返す。"""
    if days < 0:
        raise ValueError("days は 0 以上にしてください")
    cutoff = utcnow() - timedelta(days=days)
    with SessionLocal() as db:
        result = db.execute(delete(SessionRow).where(SessionRow.expires_at < cutoff))
        db.commit()
        return int(result.rowcount or 0)


def audit_stats(retention_days: int | None = None) -> dict[str, int]:
    """監査ログの総件数と保持期間を超えた件数を返す（削除はしない）。

    保持期間の削除ジョブは方針決定後に追加する。ここでは判断材料の件数だけを示す。
    """
    days = get_settings().audit_retention_days if retention_days is None else retention_days
    if days < 0:
        raise ValueError("retention_days は 0 以上にしてください")
    cutoff = utcnow() - timedelta(days=days)
    with SessionLocal() as db:
        total = db.scalar(select(func.count()).select_from(AuditEvent)) or 0
        older = (
            db.scalar(
                select(func.count()).select_from(AuditEvent).where(AuditEvent.created_at < cutoff)
            )
            or 0
        )
    return {
        "total": int(total),
        "older_than_retention": int(older),
        "retention_days": days,
    }


def purge_audit(
    retention_days: int | None = None, *, commit: bool = False, batch_size: int = 1000
) -> dict[str, int]:
    """保持期間を超えた監査ログを削除する（既定は dry-run）。

    audit_events は append-only トリガーで保護されているため、削除には所有者ロールで
    トリガーを一時的に無効化する。実行トランザクション内で無効化・削除・再有効化を行い、
    失敗時はロールバックでトリガーが戻る。実際の削除は `commit=True` かつ CLI では
    `RIHRP_ALLOW_AUDIT_PURGE=1` が揃った場合だけ行う。
    """
    days = get_settings().audit_retention_days if retention_days is None else retention_days
    if days < 0:
        raise ValueError("retention_days は 0 以上にしてください")
    if batch_size < 1:
        raise ValueError("batch_size は 1 以上にしてください")
    cutoff = utcnow() - timedelta(days=days)

    if not commit:
        with SessionLocal() as db:
            total = db.scalar(select(func.count()).select_from(AuditEvent)) or 0
            eligible = (
                db.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(AuditEvent.created_at < cutoff)
                )
                or 0
            )
        return {
            "retention_days": days,
            "total": int(total),
            "eligible": int(eligible),
            "deleted": 0,
        }

    # 関数レベルでも承認を要求する（CLI 以外の呼び出しで迂回させない）。
    if os.environ.get("RIHRP_ALLOW_AUDIT_PURGE") != "1":
        raise RuntimeError("監査ログの削除には RIHRP_ALLOW_AUDIT_PURGE=1 が必要です")
    owner_url = os.environ.get("RIHRP_MIGRATION_DATABASE_URL") or os.environ.get(
        "RIHRP_DATABASE_URL"
    )
    if not owner_url:
        raise RuntimeError("削除には RIHRP_MIGRATION_DATABASE_URL（所有者）が必要です")
    # ロックを取る前に削除対象が無ければ、早期に何もしない（書き込みを止めない）。
    with SessionLocal() as db:
        total_pre = int(db.scalar(select(func.count()).select_from(AuditEvent)) or 0)
        eligible_pre = int(
            db.scalar(
                select(func.count()).select_from(AuditEvent).where(AuditEvent.created_at < cutoff)
            )
            or 0
        )
    if eligible_pre == 0:
        return {
            "retention_days": days,
            "total": total_pre,
            "eligible": 0,
            "deleted": 0,
            "remaining": total_pre,
        }

    engine = create_engine(owner_url, pool_pre_ping=True)
    deleted = 0
    try:
        with engine.begin() as conn:
            # ロック待ちと長時間実行に上限を設ける（失敗時はロールバック）。
            conn.execute(text("SET LOCAL lock_timeout = '5s'"))
            conn.execute(text("SET LOCAL statement_timeout = '120s'"))
            total = int(conn.scalar(text("SELECT count(*) FROM audit_events")) or 0)
            eligible = int(
                conn.scalar(
                    text("SELECT count(*) FROM audit_events WHERE created_at < :cutoff"),
                    {"cutoff": cutoff},
                )
                or 0
            )
            conn.execute(text("ALTER TABLE audit_events DISABLE TRIGGER trg_audit_immutable"))
            while True:
                result = conn.execute(
                    text(
                        "DELETE FROM audit_events WHERE id IN ("
                        " SELECT id FROM audit_events WHERE created_at < :cutoff LIMIT :limit)"
                    ),
                    {"cutoff": cutoff, "limit": batch_size},
                )
                count = int(result.rowcount or 0)
                deleted += count
                if count == 0:
                    break
            conn.execute(text("ALTER TABLE audit_events ENABLE TRIGGER trg_audit_immutable"))
            remaining = int(conn.scalar(text("SELECT count(*) FROM audit_events")) or 0)
    finally:
        engine.dispose()
    return {
        "retention_days": days,
        "total": total,
        "eligible": eligible,
        "deleted": deleted,
        "remaining": remaining,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m rihrp.maintenance")
    sub = parser.add_subparsers(dest="command", required=True)
    purge = sub.add_parser("purge-sessions", help="期限切れセッションを削除する")
    purge.add_argument("--days", type=int, default=7, help="期限切れからの猶予日数（既定 7）")
    stats = sub.add_parser(
        "audit-stats", help="監査ログの総件数と保持期間超過件数を表示する（削除はしない）"
    )
    stats.add_argument("--retention-days", type=int, default=None, help="保持日数（既定は設定値）")
    purge_audit_parser = sub.add_parser(
        "purge-audit", help="保持期間を超えた監査ログを削除する（既定は dry-run）"
    )
    purge_audit_parser.add_argument(
        "--days", type=int, default=None, help="保持日数（既定は設定値）"
    )
    purge_audit_parser.add_argument(
        "--commit", action="store_true", help="実際に削除する（RIHRP_ALLOW_AUDIT_PURGE=1 が必要）"
    )
    purge_audit_parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args(argv)

    if args.command == "purge-sessions":
        # 破壊的なため、接続先が明示されていない場合は既定 DB へ推測で接続しない。
        if not os.environ.get("RIHRP_DATABASE_URL"):
            print("BLOCKED: RIHRP_DATABASE_URL が未設定のため purge を中止します", file=sys.stderr)
            return 2
        count = purge_sessions(args.days)
        print(f"purged sessions: {count}")
    elif args.command == "purge-audit":
        if not os.environ.get("RIHRP_DATABASE_URL"):
            print("BLOCKED: RIHRP_DATABASE_URL が未設定のため中止します", file=sys.stderr)
            return 2
        if args.commit and os.environ.get("RIHRP_ALLOW_AUDIT_PURGE") != "1":
            print(
                "BLOCKED: 削除には RIHRP_ALLOW_AUDIT_PURGE=1 が必要です（承認後に設定）",
                file=sys.stderr,
            )
            return 3
        result = purge_audit(args.days, commit=args.commit, batch_size=args.batch_size)
        print(
            "audit purge: "
            f"retention_days={result['retention_days']} "
            f"total={result['total']} eligible={result['eligible']} "
            f"deleted={result['deleted']}"
            + (f" remaining={result['remaining']}" if "remaining" in result else "")
        )
    elif args.command == "audit-stats":
        result = audit_stats(args.retention_days)
        print(
            "audit events: "
            f"total={result['total']} "
            f"older_than_retention={result['older_than_retention']} "
            f"retention_days={result['retention_days']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
