"""セッション保守コマンドの結合テスト。"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError

from rihrp.auth import utcnow
from rihrp.db import SessionLocal
from rihrp.maintenance import audit_stats, purge_audit, purge_sessions
from rihrp.models import AuditEvent
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


def test_audit_stats_counts_retention_backlog(users: dict[str, str]) -> None:
    with SessionLocal() as db:
        db.add(
            AuditEvent(
                actor_id=users["admin"],
                action="test.old",
                entity_type="test",
                created_at=utcnow() - timedelta(days=400),
            )
        )
        db.add(
            AuditEvent(
                actor_id=users["admin"],
                action="test.new",
                entity_type="test",
            )
        )
        db.commit()

    stats = audit_stats(365)
    assert stats == {"total": 2, "older_than_retention": 1, "retention_days": 365}

    assert audit_stats(0)["older_than_retention"] == 2


def test_purge_audit_dry_run_then_commit(users: dict[str, str]) -> None:
    with SessionLocal() as db:
        db.add(
            AuditEvent(
                actor_id=users["admin"],
                action="test.old",
                entity_type="test",
                created_at=utcnow() - timedelta(days=400),
            )
        )
        db.add(AuditEvent(actor_id=users["admin"], action="test.new", entity_type="test"))
        db.commit()

    dry = purge_audit(365)
    assert dry["eligible"] == 1
    assert dry["deleted"] == 0
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == 2

    result = purge_audit(365, commit=True)
    assert result["deleted"] == 1
    assert result["remaining"] == 1
    with SessionLocal() as db:
        remaining = db.query(AuditEvent).all()
    assert [row.action for row in remaining] == ["test.new"]

    # 削除後も append-only トリガーが有効に戻っている。
    with pytest.raises(SQLAlchemyError), SessionLocal() as db:
        db.execute(delete(AuditEvent))
        db.commit()
