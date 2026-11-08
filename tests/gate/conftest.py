"""品質ゲート実行用の共通フィクスチャ（隔離 DB `rihrp_test*` 専用）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from rihrp.db import SessionLocal
from rihrp.main import app
from rihrp.seed import seed_users

DEMO_PASSWORD = "gate-test-password-123"  # noqa: S105 - テスト専用の固定値


@pytest.fixture
def demo_users(clean_db, monkeypatch) -> dict[str, dict]:
    """ケース記述と同じ `*@rihrp.local` の利用者を隔離 DB に作る。"""
    monkeypatch.setenv("RIHRP_SEED_PASSWORD", DEMO_PASSWORD)
    with SessionLocal() as db:
        created = seed_users(db)
    assert created, "デモ利用者の投入に失敗しました"
    return {
        role: {"email": user.email, "id": user.id, "password": DEMO_PASSWORD}
        for role, user in created.items()
    }


def login_as(client: TestClient, email: str, password: str, *, set_csrf: bool = True) -> dict:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    body = response.json()
    if set_csrf:
        client.headers["X-CSRF-Token"] = body["csrf_token"]
    return body


def new_client() -> TestClient:
    return TestClient(app)


# Access JWT ケース用のフィクスチャを tests/integration から再利用する。
from tests.integration.test_access_login import access_env, signing_key  # noqa: E402, F401
