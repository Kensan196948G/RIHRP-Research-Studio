"""運用向け保守コマンド。秘密は環境変数から読む。

RIHRP_DATABASE_URL=... .venv/bin/python -m rihrp.maintenance purge-sessions --days 7
"""

from __future__ import annotations

import argparse
from datetime import timedelta

from sqlalchemy import delete

from .auth import utcnow
from .db import SessionLocal
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m rihrp.maintenance")
    sub = parser.add_subparsers(dest="command", required=True)
    purge = sub.add_parser("purge-sessions", help="期限切れセッションを削除する")
    purge.add_argument("--days", type=int, default=7, help="期限切れからの猶予日数（既定 7）")
    args = parser.parse_args(argv)

    if args.command == "purge-sessions":
        count = purge_sessions(args.days)
        print(f"purged sessions: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
