"""Cloudflare Access による自動ログイン（実 PostgreSQL）。"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt import PyJWKSet
from jwt.algorithms import RSAAlgorithm
from sqlalchemy import select

from rihrp import cf_access
from rihrp.config import get_settings
from rihrp.db import SessionLocal
from rihrp.models import AuditEvent, User

TEAM = "team.example.com"
AUD = "aud-123"
ISS = f"https://{TEAM}"


@pytest.fixture
def access_env(monkeypatch) -> Iterator[None]:
    monkeypatch.setenv("RIHRP_TRUST_CF_ACCESS", "true")
    monkeypatch.setenv("RIHRP_CF_ACCESS_TEAM_DOMAIN", TEAM)
    monkeypatch.setenv("RIHRP_CF_ACCESS_AUD", AUD)
    monkeypatch.setenv("RIHRP_CF_ACCESS_ALLOWED_EMAILS", "editor@test.local")
    monkeypatch.setenv("RIHRP_CF_ACCESS_LOOPBACK_ONLY", "false")
    monkeypatch.setenv("RIHRP_CF_ACCESS_PROVISION", "false")
    get_settings.cache_clear()
    cf_access._jwks_cache.clear()
    yield
    get_settings.cache_clear()
    cf_access._jwks_cache.clear()
    monkeypatch.undo()


@pytest.fixture
def signing_key(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({"kid": "kid-test", "alg": "RS256", "use": "sig"})
    jwks = PyJWKSet.from_dict({"keys": [jwk]})
    monkeypatch.setattr(cf_access, "_fetch_jwks", lambda _settings: jwks)
    return private_key


def make_token(
    private_key, *, email: str = "editor@test.local", aud: str = AUD, exp_delta: int = 300
) -> str:
    now = int(time.time())
    payload = {
        "aud": aud,
        "iss": ISS,
        "email": email,
        "sub": "user-1",
        "iat": now,
        "exp": now + exp_delta,
    }
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": "kid-test"})


def audit_actions() -> list[tuple[str, dict]]:
    with SessionLocal() as db:
        rows = db.execute(select(AuditEvent.action, AuditEvent.details)).all()
    return [(action, details or {}) for action, details in rows]


def has_audit(action: str, **expected: object) -> bool:
    """details の部分一致で監査イベントを探す（source 等の付加情報は無視する）。"""
    for recorded, details in audit_actions():
        if recorded != action:
            continue
        if all(details.get(key) == value for key, value in expected.items()):
            return True
    return False


def test_access_login_is_disabled_by_default(client: TestClient, users: dict[str, str]) -> None:
    response = client.get("/api/auth/access")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "access_login_disabled"


def test_access_login_requires_assertion(
    client: TestClient, users: dict[str, str], access_env: None, signing_key
) -> None:
    response = client.get("/api/auth/access")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "access_assertion_missing"
    assert has_audit("auth.access_denied", reason="assertion_missing")


def test_access_login_rejects_forged_token(
    client: TestClient, users: dict[str, str], access_env: None, signing_key
) -> None:
    forged_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    response = client.get(
        "/api/auth/access",
        headers={"Cf-Access-Jwt-Assertion": make_token(forged_key)},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "access_assertion_invalid"
    assert has_audit("auth.access_denied", reason="access_assertion_invalid")


def test_access_login_creates_session(
    client: TestClient, users: dict[str, str], access_env: None, signing_key
) -> None:
    response = client.get(
        "/api/auth/access",
        headers={"Cf-Access-Jwt-Assertion": make_token(signing_key)},
    )
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    body = response.json()
    assert body["user"]["email"] == "editor@test.local"
    assert body["user"]["role"] == "editor"
    assert body["csrf_token"]

    client.headers["X-CSRF-Token"] = body["csrf_token"]
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "editor@test.local"

    assert has_audit("auth.login", role="editor", via="cloudflare_access")


def test_access_login_rejects_email_outside_allowlist(
    client: TestClient, users: dict[str, str], access_env: None, signing_key
) -> None:
    response = client.get(
        "/api/auth/access",
        headers={"Cf-Access-Jwt-Assertion": make_token(signing_key, email="reviewer@test.local")},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "access_email_not_allowed"
    assert has_audit("auth.access_denied", email="reviewer@test.local", reason="email_not_allowed")


def test_access_login_rejects_unknown_user(
    client: TestClient, users: dict[str, str], access_env: None, signing_key
) -> None:
    get_settings.cache_clear()
    import os

    os.environ["RIHRP_CF_ACCESS_ALLOWED_EMAILS"] = "nobody@test.local"
    get_settings.cache_clear()
    try:
        response = client.get(
            "/api/auth/access",
            headers={"Cf-Access-Jwt-Assertion": make_token(signing_key, email="nobody@test.local")},
        )
    finally:
        os.environ["RIHRP_CF_ACCESS_ALLOWED_EMAILS"] = "editor@test.local"
        get_settings.cache_clear()

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "access_user_not_found"
    assert has_audit("auth.access_denied", email="nobody@test.local", reason="user_not_found")


def test_access_login_provisions_when_enabled(
    client: TestClient, users: dict[str, str], access_env: None, signing_key, monkeypatch
) -> None:
    monkeypatch.setenv("RIHRP_CF_ACCESS_ALLOWED_EMAILS", "new-user@test.local")
    monkeypatch.setenv("RIHRP_CF_ACCESS_PROVISION", "true")
    get_settings.cache_clear()

    response = client.get(
        "/api/auth/access",
        headers={"Cf-Access-Jwt-Assertion": make_token(signing_key, email="new-user@test.local")},
    )

    assert response.status_code == 200, response.text
    assert response.json()["user"]["role"] == "viewer"
    with SessionLocal() as db:
        created = db.execute(
            select(User).where(User.email == "new-user@test.local")
        ).scalar_one_or_none()
    assert created is not None


def test_access_login_requires_loopback_when_configured(
    client: TestClient, users: dict[str, str], access_env: None, signing_key, monkeypatch
) -> None:
    monkeypatch.setenv("RIHRP_CF_ACCESS_LOOPBACK_ONLY", "true")
    get_settings.cache_clear()

    response = client.get(
        "/api/auth/access",
        headers={"Cf-Access-Jwt-Assertion": make_token(signing_key)},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "access_origin_rejected"


def test_access_login_denies_all_when_allowlist_is_empty(
    client: TestClient, users: dict[str, str], access_env: None, signing_key, monkeypatch
) -> None:
    monkeypatch.setenv("RIHRP_CF_ACCESS_ALLOWED_EMAILS", "")
    get_settings.cache_clear()

    response = client.get(
        "/api/auth/access",
        headers={"Cf-Access-Jwt-Assertion": make_token(signing_key)},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "access_email_not_allowed"
    assert has_audit("auth.access_denied", reason="email_not_allowed")


def test_access_login_audits_origin_rejection(
    client: TestClient, users: dict[str, str], access_env: None, signing_key, monkeypatch
) -> None:
    monkeypatch.setenv("RIHRP_CF_ACCESS_LOOPBACK_ONLY", "true")
    get_settings.cache_clear()

    response = client.get(
        "/api/auth/access",
        headers={"Cf-Access-Jwt-Assertion": make_token(signing_key)},
    )

    assert response.status_code == 403
    assert has_audit("auth.access_denied", reason="origin_rejected")
