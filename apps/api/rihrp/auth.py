"""セッション認証・CSRF・RBAC。"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .errors import ApiError
from .models import Session as SessionRow
from .models import User
from .security import hash_token, tokens_equal

SESSION_COOKIE = "rihrp_session"
CSRF_COOKIE = "rihrp_csrf"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

_login_attempts: dict[str, deque[float]] = defaultdict(deque)


@dataclass(frozen=True)
class Principal:
    user_id: str
    email: str
    name: str
    role: str
    session_id: str
    csrf_token: str


def utcnow() -> datetime:
    return datetime.now(UTC)


def check_login_rate(ip: str) -> None:
    settings = get_settings()
    limit = max(settings.login_rate_limit, 1)
    now = time.monotonic()
    window = _login_attempts[ip]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= limit:
        raise ApiError(
            429, "rate_limited", "試行回数が多すぎます。しばらく待って再試行してください。"
        )
    window.append(now)


def reset_login_rate() -> None:
    _login_attempts.clear()


def _extract_session_token(request: Request) -> str | None:
    return request.cookies.get(SESSION_COOKIE)


def get_principal(request: Request, db: Session = Depends(get_db)) -> Principal:
    token = _extract_session_token(request)
    if not token:
        raise ApiError(401, "unauthorized", "ログインが必要です。")

    row = db.execute(
        select(SessionRow, User)
        .join(User, User.id == SessionRow.user_id)
        .where(SessionRow.token_hash == hash_token(token))
    ).first()
    if row is None:
        raise ApiError(401, "unauthorized", "セッションが無効です。再ログインしてください。")

    session_row, user = row
    now = utcnow()
    expires_at = session_row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if session_row.revoked_at is not None or expires_at <= now or not user.is_active:
        raise ApiError(
            401, "unauthorized", "セッションの有効期限が切れました。再ログインしてください。"
        )

    if request.method.upper() not in SAFE_METHODS:
        header = request.headers.get("X-CSRF-Token", "")
        cookie = request.cookies.get(CSRF_COOKIE, "")
        if (
            not header
            or not cookie
            or not tokens_equal(header, cookie)
            or not tokens_equal(header, session_row.csrf_token)
        ):
            raise ApiError(403, "csrf_failed", "CSRF トークンが一致しません。")

    return Principal(
        user_id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        session_id=session_row.id,
        csrf_token=session_row.csrf_token,
    )


def require_roles(*roles: str):
    def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.role not in roles:
            raise ApiError(403, "forbidden", "この操作を行う権限がありません。")
        return principal

    return dependency


require_admin = require_roles("admin")
require_editor = require_roles("editor", "admin")
require_reviewer = require_roles("reviewer", "admin")
require_verifier = require_roles("editor", "reviewer", "admin")
