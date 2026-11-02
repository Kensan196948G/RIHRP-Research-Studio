"""認証 API。"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select, update
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
from ..cf_access import allowed_emails, verify_assertion
from ..config import get_settings
from ..db import get_db
from ..errors import ApiError
from ..models import Session as SessionRow
from ..models import User
from ..schemas import LoginIn, PasswordChangeIn
from ..security import (
    DUMMY_PASSWORD_HASH,
    hash_password,
    hash_token,
    new_csrf_token,
    new_opaque_token,
    verify_password,
)
from ..services import user_to_dict

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_cookies(response: Response, raw_token: str, csrf_token: str, ttl_minutes: int) -> None:
    settings = get_settings()
    secure = settings.cookie_secure or settings.is_production
    max_age = ttl_minutes * 60
    response.set_cookie(
        SESSION_COOKIE,
        raw_token,
        httponly=True,
        samesite="lax",
        secure=secure,
        max_age=max_age,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        httponly=False,
        samesite="lax",
        secure=secure,
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
    if user is None:
        # 利用者の存在を応答時間から推測されないよう、ダミーハッシュも検証する。
        verify_password(payload.password, DUMMY_PASSWORD_HASH)
        raise ApiError(401, "invalid_credentials", "メールアドレスまたはパスワードが一致しません。")
    if not user.is_active:
        verify_password(payload.password, user.password_hash)
        raise ApiError(401, "invalid_credentials", "メールアドレスまたはパスワードが一致しません。")
    if not verify_password(payload.password, user.password_hash):
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


def _access_denied(db: OrmSession, request: Request, reason: str, **details: object) -> None:
    """Access 自動ログインの拒否を監査に残す。

    検証前のクレームは信頼できないため、email は検証後に確定した場合だけ渡す。
    """
    source = request.client.host if request.client else ""
    write_audit(
        db,
        actor_id=None,
        action="auth.access_denied",
        entity_type="user",
        details={"reason": reason, "source": source, **details},
    )
    db.commit()


@router.get("/access")
def access_login(
    request: Request,
    response: Response,
    db: OrmSession = Depends(get_db),
) -> dict:
    """Cloudflare Access の ID でアプリのセッションを発行する（パスワード入力なし）。

    Access が付与する ``Cf-Access-Jwt-Assertion`` を署名・iss・aud・期限まで検証し、
    allowlist に載る email の利用者にだけセッションを渡す。失敗時は自動ログインせず、
    パスワードログイン（/api/auth/login）は別経路として残す。
    """
    settings = get_settings()
    if not settings.trust_cf_access:
        raise ApiError(404, "access_login_disabled", "Cloudflare Access ログインは無効です。")

    host = request.client.host if request.client else ""
    if settings.cf_access_loopback_only and host not in {"127.0.0.1", "::1"}:
        _access_denied(db, request, "origin_rejected", source=host)
        raise ApiError(
            403, "access_origin_rejected", "Cloudflare Access 経由の接続ではありません。"
        )

    token = request.headers.get("Cf-Access-Jwt-Assertion", "").strip()
    if not token:
        _access_denied(db, request, "assertion_missing")
        raise ApiError(
            401, "access_assertion_missing", "Cloudflare Access の認証情報がありません。"
        )

    try:
        claims = verify_assertion(token, settings)
    except ApiError as exc:
        _access_denied(db, request, exc.code)
        raise
    email = str(claims.get("email") or "").strip().lower()
    if not email:
        _access_denied(db, request, "email_missing")
        raise ApiError(
            401, "access_assertion_invalid", "Cloudflare Access のトークンに email がありません。"
        )

    if email not in allowed_emails(settings):
        _access_denied(db, request, "email_not_allowed", email=email)
        raise ApiError(403, "access_email_not_allowed", "このアカウントには利用権限がありません。")

    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None and settings.cf_access_provision:
        user = User(
            email=email,
            name=str(claims.get("name") or email.split("@")[0])[:120],
            role=settings.cf_access_default_role,
            password_hash=hash_password(new_opaque_token()),
        )
        db.add(user)
        db.flush()
    if user is None:
        _access_denied(db, request, "user_not_found", email=email)
        raise ApiError(403, "access_user_not_found", "このアカウントは登録されていません。")
    if not user.is_active:
        _access_denied(db, request, "user_inactive", email=email, user_id=user.id)
        raise ApiError(403, "access_user_inactive", "このアカウントは無効化されています。")

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
        details={"role": user.role, "via": "cloudflare_access"},
    )
    db.commit()
    _set_cookies(response, raw_token, csrf_token, settings.session_ttl_minutes)
    # 自動ログインの応答はキャッシュさせない（prefetch 等で古い応答を再利用させない）。
    response.headers["Cache-Control"] = "no-store"
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
    # パスワード変更時は、現在のセッション以外を失効させる（盗まれたセッションの継続を防ぐ）。
    revoked = db.execute(
        update(SessionRow)
        .where(
            SessionRow.user_id == user.id,
            SessionRow.id != principal.session_id,
            SessionRow.revoked_at.is_(None),
        )
        .values(revoked_at=utcnow())
    ).rowcount
    write_audit(
        db,
        actor_id=principal.user_id,
        action="user.password_changed",
        entity_type="user",
        entity_id=principal.user_id,
        details={"other_sessions_revoked": int(revoked or 0)},
    )
    db.commit()
    return {"ok": True}
