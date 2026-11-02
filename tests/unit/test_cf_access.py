"""Cloudflare Access JWT の検証（DB 不要の単体テスト）。"""

from __future__ import annotations

import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import PyJWKSet
from jwt.algorithms import RSAAlgorithm

from rihrp import cf_access
from rihrp.config import Settings
from rihrp.errors import ApiError

TEAM = "team.example.com"
AUD = "aud-123"
ISS = f"https://{TEAM}"


def make_key(kid: str = "kid-1"):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
    return private_key, PyJWKSet.from_dict({"keys": [jwk]})


def make_settings(**overrides) -> Settings:
    values = {
        "trust_cf_access": True,
        "cf_access_team_domain": TEAM,
        "cf_access_aud": AUD,
        "cf_access_allowed_emails": "editor@example.com",
        "cf_access_loopback_only": False,
    }
    values.update(overrides)
    return Settings(**values)


def make_token(private_key, *, kid: str = "kid-1", email: str = "editor@example.com", **claims):
    now = int(time.time())
    payload = {
        "aud": AUD,
        "iss": ISS,
        "email": email,
        "sub": "user-1",
        "iat": now,
        "exp": now + 300,
    }
    payload.update(claims)
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": kid})


@pytest.fixture(autouse=True)
def clear_cache():
    cf_access._jwks_cache.clear()
    yield
    cf_access._jwks_cache.clear()


def test_verify_assertion_accepts_valid_token(monkeypatch):
    private_key, jwks = make_key()
    monkeypatch.setattr(cf_access, "_fetch_jwks", lambda _settings: jwks)

    claims = cf_access.verify_assertion(make_token(private_key), make_settings())

    assert claims["email"] == "editor@example.com"
    assert claims["aud"] == AUD


def test_verify_assertion_rejects_wrong_audience(monkeypatch):
    private_key, jwks = make_key()
    monkeypatch.setattr(cf_access, "_fetch_jwks", lambda _settings: jwks)

    with pytest.raises(ApiError) as excinfo:
        cf_access.verify_assertion(make_token(private_key, aud="other-aud"), make_settings())

    assert excinfo.value.status_code == 401
    assert excinfo.value.code == "access_assertion_invalid"


def test_verify_assertion_rejects_wrong_issuer(monkeypatch):
    private_key, jwks = make_key()
    monkeypatch.setattr(cf_access, "_fetch_jwks", lambda _settings: jwks)

    with pytest.raises(ApiError):
        cf_access.verify_assertion(
            make_token(private_key, iss="https://evil.example.com"), make_settings()
        )


def test_verify_assertion_rejects_expired_token(monkeypatch):
    private_key, jwks = make_key()
    monkeypatch.setattr(cf_access, "_fetch_jwks", lambda _settings: jwks)

    with pytest.raises(ApiError):
        cf_access.verify_assertion(
            make_token(private_key, exp=int(time.time()) - 60), make_settings()
        )


def test_verify_assertion_rejects_forged_signature(monkeypatch):
    _, jwks = make_key()
    other_key, _ = make_key()
    monkeypatch.setattr(cf_access, "_fetch_jwks", lambda _settings: jwks)

    with pytest.raises(ApiError):
        cf_access.verify_assertion(make_token(other_key), make_settings())


def test_verify_assertion_rejects_unknown_kid(monkeypatch):
    private_key, jwks = make_key()
    monkeypatch.setattr(cf_access, "_fetch_jwks", lambda _settings: jwks)

    with pytest.raises(ApiError):
        cf_access.verify_assertion(make_token(private_key, kid="unknown"), make_settings())


def test_verify_assertion_requires_configuration():
    with pytest.raises(ApiError) as excinfo:
        cf_access.verify_assertion("token", make_settings(cf_access_aud=""))
    assert excinfo.value.status_code == 503


def test_allowed_emails_parsing():
    settings = make_settings(cf_access_allowed_emails=" A@example.com, b@example.com ,, ")
    assert cf_access.allowed_emails(settings) == {"a@example.com", "b@example.com"}
