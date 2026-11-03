"""運用向け保守コマンド。秘密は環境変数から読む。

RIHRP_DATABASE_URL=... .venv/bin/python -m rihrp.maintenance purge-sessions --days 7
RIHRP_DATABASE_URL=... .venv/bin/python -m rihrp.maintenance audit-stats
"""

from __future__ import annotations

import argparse
from datetime import timedelta

from sqlalchemy import delete, func, select

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m rihrp.maintenance")
    sub = parser.add_subparsers(dest="command", required=True)
    purge = sub.add_parser("purge-sessions", help="期限切れセッションを削除する")
    purge.add_argument("--days", type=int, default=7, help="期限切れからの猶予日数（既定 7）")
    stats = sub.add_parser(
        "audit-stats", help="監査ログの総件数と保持期間超過件数を表示する（削除はしない）"
    )
    stats.add_argument("--retention-days", type=int, default=None, help="保持日数（既定は設定値）")
    args = parser.parse_args(argv)

    if args.command == "purge-sessions":
        count = purge_sessions(args.days)
        print(f"purged sessions: {count}")
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
