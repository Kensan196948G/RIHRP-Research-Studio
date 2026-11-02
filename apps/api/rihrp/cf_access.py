"""Cloudflare Access の ID をアプリのセッションへ引き継ぐ（自動ログイン）。

境界の考え方:

- アプリは 127.0.0.1:18110 でのみ待ち受け、外部からは Cloudflare Tunnel + Access 経由でのみ
  到達できる。
- Access は認証済みリクエストに ``Cf-Access-Jwt-Assertion``（RS256 の JWT）を付与する。
- このモジュールは **署名・iss・aud・有効期限を検証**したうえで email クレームだけを取り出す。
  ヘッダーをそのまま信頼しない（ローカルプロセスからの詐称に備える）。
- 検証に失敗した場合は自動ログインを行わない（fail closed）。パスワードログインは別経路として残る。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

import jwt
from jwt import PyJWKSet

from .config import Settings
from .errors import ApiError

JWKS_TTL_SECONDS = 300.0
# 鍵取得に失敗したとき、この秒数までは直前の鍵を使う（それ以上古い鍵では 503 で停止する）。
JWKS_STALE_MAX_SECONDS = 3600.0
HTTP_TIMEOUT_SECONDS = 5.0

# team domain -> (取得時刻, JWKS)
_jwks_cache: dict[str, tuple[float, PyJWKSet]] = {}


def issuer(settings: Settings) -> str:
    return f"https://{settings.cf_access_team_domain}"


def certs_url(settings: Settings) -> str:
    return f"{issuer(settings)}/cdn-cgi/access/certs"


def _fetch_jwks(settings: Settings) -> PyJWKSet:
    """Access の公開鍵を取得する（テストでは monkeypatch する）。"""
    request = urllib.request.Request(  # noqa: S310 - URL は自前の設定から組み立てた https
        certs_url(settings), headers={"Accept": "application/json"}
    )
    with urllib.request.urlopen(  # noqa: S310
        request, timeout=HTTP_TIMEOUT_SECONDS
    ) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return PyJWKSet.from_dict(payload)


def load_jwks(settings: Settings, *, force: bool = False) -> PyJWKSet:
    domain = settings.cf_access_team_domain
    now = time.monotonic()
    cached = _jwks_cache.get(domain)
    if cached and not force and now - cached[0] < JWKS_TTL_SECONDS:
        return cached[1]
    try:
        jwks = _fetch_jwks(settings)
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError, jwt.PyJWKSetError) as exc:
        # 一時的な取得失敗では、許容時間内に限り直前の鍵を使う（鍵の失効・ローテーションに配慮）。
        if cached and now - cached[0] <= JWKS_STALE_MAX_SECONDS:
            return cached[1]
        raise ApiError(
            503,
            "access_verification_unavailable",
            "Cloudflare Access の公開鍵を取得できません。",
        ) from exc
    _jwks_cache[domain] = (now, jwks)
    return jwks


def _find_key(settings: Settings, kid: str | None) -> Any:
    if not kid:
        raise ApiError(401, "access_assertion_invalid", "Cloudflare Access のトークンが不正です。")
    for force in (False, True):
        jwks = load_jwks(settings, force=force)
        for key in jwks.keys:
            if key.key_id == kid:
                return key.key
    raise ApiError(401, "access_assertion_invalid", "Cloudflare Access の署名鍵が見つかりません。")


def verify_assertion(token: str, settings: Settings) -> dict[str, Any]:
    """``Cf-Access-Jwt-Assertion`` を検証してクレームを返す。失敗は ApiError（401/503）。"""
    if not settings.cf_access_team_domain or not settings.cf_access_aud:
        raise ApiError(503, "access_not_configured", "Cloudflare Access の設定が不足しています。")
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise ApiError(
            401, "access_assertion_invalid", "Cloudflare Access のトークンを解釈できません。"
        ) from exc
    if header.get("alg") != "RS256":
        raise ApiError(401, "access_assertion_invalid", "Cloudflare Access の署名方式が不正です。")
    key = _find_key(settings, header.get("kid"))
    try:
        return jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.cf_access_aud,
            issuer=issuer(settings),
            leeway=10,
            options={"require": ["exp", "iat", "aud", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise ApiError(
            401, "access_assertion_invalid", "Cloudflare Access のトークンが無効です。"
        ) from exc


def allowed_emails(settings: Settings) -> set[str]:
    return {
        item.strip().lower()
        for item in settings.cf_access_allowed_emails.split(",")
        if item.strip()
    }
