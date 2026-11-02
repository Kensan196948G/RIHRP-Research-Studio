"""パスワード・トークン・CSRF。秘密はログに出さない。"""

from __future__ import annotations

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()

# 存在しない利用者でも同じコストで検証するための固定ハッシュ（秘密ではない）。
DUMMY_PASSWORD_HASH = (  # noqa: S105 - ダミー検証用の固定ハッシュ（秘密ではない）
    "$argon2id$v=19$m=65536,t=3,p=4$G2B/HUUvA3vH+VxvuXyQig$"  # noqa: S105
    "xmr/E7Gs26hPFj1di6RdkZhxWHE+ComAXbLpWrVRSEo"
)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def new_opaque_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_csrf_token() -> str:
    return secrets.token_urlsafe(24)


def tokens_equal(left: str, right: str) -> bool:
    return secrets.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
