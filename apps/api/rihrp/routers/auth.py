"""認証 API。"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from ..audit import write_audit
from ..auth import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    Principal,
    check_login_rate,
    get_principal,
    utcnow,
)
from ..config import get_settings
from ..db import get_db
from ..errors import ApiError
from ..models import Session as SessionRow
from ..models import User
from ..schemas import LoginIn, PasswordChangeIn
from ..security import hash_password, hash_token, new_csrf_token, new_opaque_token, verify_password
from ..services import user_to_dict

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_cookies(response: Response, raw_token: str, csrf_token: str, ttl_minutes: int) -> None:
    settings = get_settings()
    max_age = ttl_minutes * 60
    response.set_cookie(
        SESSION_COOKIE,
        raw_token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=max_age,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        httponly=False,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=max_age,
        path="/",
    )


@router.post("/login")
def login(
    payload: LoginIn,
    request: Request,
    response: Response,
    db: OrmSession = Depends(get_db),
) -> dict:
    ip = request.client.host if request.client else "unknown"
    check_login_rate(ip)
    email = payload.email.strip().lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.password_hash)
    ):
        raise ApiError(401, "invalid_credentials", "メールアドレスまたはパスワードが一致しません。")

    settings = get_settings()
    raw_token = new_opaque_token()
    csrf_token = new_csrf_token()
    session_row = SessionRow(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        csrf_token=csrf_token,
        expires_at=utcnow() + timedelta(minutes=settings.session_ttl_minutes),
    )
    db.add(session_row)
    db.flush()
    write_audit(
        db,
        actor_id=user.id,
        action="auth.login",
        entity_type="session",
        entity_id=session_row.id,
        details={"role": user.role},
    )
    db.commit()
    _set_cookies(response, raw_token, csrf_token, settings.session_ttl_minutes)
    return {"user": user_to_dict(user), "csrf_token": csrf_token}


@router.post("/logout")
def logout(
    response: Response,
    principal: Principal = Depends(get_principal),
    db: OrmSession = Depends(get_db),
) -> dict:
    session_row = db.get(SessionRow, principal.session_id)
    if session_row is not None and session_row.revoked_at is None:
        session_row.revoked_at = utcnow()
    write_audit(
        db,
        actor_id=principal.user_id,
        action="auth.logout",
        entity_type="session",
        entity_id=principal.session_id,
    )
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(
    principal: Principal = Depends(get_principal),
    db: OrmSession = Depends(get_db),
) -> dict:
    user = db.get(User, principal.user_id)
    if user is None:
        raise ApiError(401, "unauthorized", "利用者が見つかりません。")
    return {"user": user_to_dict(user), "csrf_token": principal.csrf_token}


@router.post("/change-password")
def change_password(
    payload: PasswordChangeIn,
    principal: Principal = Depends(get_principal),
    db: OrmSession = Depends(get_db),
) -> dict:
    user = db.get(User, principal.user_id)
    if user is None or not verify_password(payload.current_password, user.password_hash):
        raise ApiError(401, "invalid_credentials", "現在のパスワードが一致しません。")
    user.password_hash = hash_password(payload.new_password)
    write_audit(
        db,
        actor_id=principal.user_id,
        action="user.password_changed",
        entity_type="user",
        entity_id=principal.user_id,
    )
    db.commit()
    return {"ok": True}
