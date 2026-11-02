"""セッション保守コマンドの結合テスト。"""

from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from rihrp.auth import utcnow
from rihrp.db import SessionLocal
from rihrp.maintenance import purge_sessions
from rihrp.models import Session as SessionRow
from rihrp.security import hash_token, new_csrf_token, new_opaque_token


def _session(user_id: str, *, expired: bool) -> str:
    raw = new_opaque_token()
    with SessionLocal() as db:
        db.add(
            SessionRow(
                user_id=user_id,
                token_hash=hash_token(raw),
                csrf_token=new_csrf_token(),
                expires_at=utcnow() - timedelta(days=1)
                if expired
                else utcnow() + timedelta(hours=1),
            )
        )
        db.commit()
    return raw


def test_purge_sessions_removes_only_expired(client: TestClient, users: dict[str, str]) -> None:
    _session(users["editor"], expired=True)
    _session(users["editor"], expired=False)

    purged = purge_sessions(0)
    assert purged == 1

    with SessionLocal() as db:
        remaining = db.query(SessionRow).all()
    assert len(remaining) == 1
