"""監査ログと利用者管理 API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from ..audit import write_audit
from ..auth import Principal, require_admin, require_reviewer
from ..db import get_db
from ..errors import ApiError
from ..models import AuditEvent, User
from ..schemas import UserIn, UserPatch
from ..security import hash_password
from ..services import audit_to_dict, user_to_dict

router = APIRouter(prefix="/api", tags=["admin"])


@router.get("/audit")
def list_audit(
    limit: int = Query(default=100, ge=1, le=500),
    project_id: str | None = Query(default=None),
    principal: Principal = Depends(require_reviewer),
    db: OrmSession = Depends(get_db),
) -> dict:
    stmt = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
    if project_id:
        stmt = stmt.where(AuditEvent.project_id == project_id)
    events = list(db.execute(stmt).scalars())
    actor_ids = {e.actor_id for e in events if e.actor_id}
    actors = (
        {
            user.id: user.name
            for user in db.execute(select(User).where(User.id.in_(actor_ids))).scalars()
        }
        if actor_ids
        else {}
    )
    return {"events": [audit_to_dict(e, actors.get(e.actor_id or "")) for e in events]}


@router.get("/users")
def list_users(
    principal: Principal = Depends(require_admin),
    db: OrmSession = Depends(get_db),
) -> dict:
    users = list(db.execute(select(User).order_by(User.created_at)).scalars())
    return {"users": [user_to_dict(u) for u in users]}


@router.post("/users", status_code=201)
def create_user(
    payload: UserIn,
    principal: Principal = Depends(require_admin),
    db: OrmSession = Depends(get_db),
) -> dict:
    email = payload.email.strip().lower()
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing is not None:
        raise ApiError(409, "conflict", "同じメールアドレスの利用者が存在します。")
    if len(payload.password) < 12:
        raise ApiError(422, "validation_error", "パスワードは 12 文字以上にしてください。")
    user = User(
        email=email,
        name=payload.name.strip(),
        role=payload.role,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.flush()
    write_audit(
        db,
        actor_id=principal.user_id,
        action="user.created",
        entity_type="user",
        entity_id=user.id,
        details={"role": user.role},
    )
    db.commit()
    return {"user": user_to_dict(user)}


@router.patch("/users/{user_id}")
def update_user(
    user_id: str,
    payload: UserPatch,
    principal: Principal = Depends(require_admin),
    db: OrmSession = Depends(get_db),
) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise ApiError(404, "not_found", "利用者が見つかりません。")
    if user.id == principal.user_id and payload.is_active is False:
        raise ApiError(422, "validation_error", "自分自身を無効化できません。")
    changes: dict = {}
    if payload.name is not None:
        user.name = payload.name.strip()
        changes["name"] = user.name
    if payload.role is not None:
        user.role = payload.role
        changes["role"] = user.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
        changes["is_active"] = payload.is_active
    write_audit(
        db,
        actor_id=principal.user_id,
        action="user.updated",
        entity_type="user",
        entity_id=user.id,
        details=changes,
    )
    db.commit()
    return {"user": user_to_dict(user)}
