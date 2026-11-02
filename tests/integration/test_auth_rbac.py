"""認証・認可・CSRF の結合テスト。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import ROLES, TEST_PASSWORD, login


def test_login_and_me(client: TestClient, users: dict[str, str]) -> None:
    user = login(client, "editor")
    assert user["email"] == ROLES["editor"]
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["role"] == "editor"


def test_login_rejects_wrong_password(client: TestClient, users: dict[str, str]) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": ROLES["editor"], "password": "wrong-password-123"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_me_requires_session(client: TestClient, users: dict[str, str]) -> None:
    assert client.get("/api/auth/me").status_code == 401


def test_csrf_required_for_writes(client: TestClient, users: dict[str, str]) -> None:
    login(client, "editor")
    client.headers.pop("X-CSRF-Token")
    response = client.post("/api/projects", json={"title": "CSRF", "summary": ""})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"


def test_logout_revokes_session(client: TestClient, users: dict[str, str]) -> None:
    login(client, "editor")
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_viewer_cannot_write(viewer_client: TestClient, users: dict[str, str]) -> None:
    response = viewer_client.post("/api/projects", json={"title": "denied", "summary": ""})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    assert viewer_client.get("/api/projects").status_code == 200


def test_viewer_cannot_read_audit(viewer_client: TestClient, users: dict[str, str]) -> None:
    assert viewer_client.get("/api/audit").status_code == 403


def test_audit_is_not_mutable(reviewer_client: TestClient, users: dict[str, str]) -> None:
    assert reviewer_client.put("/api/audit").status_code in (404, 405)
    assert reviewer_client.delete("/api/audit").status_code in (404, 405)


def test_admin_can_list_users(client: TestClient, users: dict[str, str]) -> None:
    login(client, "admin")
    response = client.get("/api/users")
    assert response.status_code == 200
    assert len(response.json()["users"]) == 4


def test_login_rate_limit(client: TestClient, users: dict[str, str], monkeypatch) -> None:
    import time

    from rihrp.auth import _login_attempts, reset_login_rate
    from rihrp.config import get_settings

    monkeypatch.setattr(get_settings(), "login_rate_limit", 5)
    reset_login_rate()
    now = time.monotonic()
    _login_attempts["testclient"].extend([now - i for i in range(5)])
    response = client.post(
        "/api/auth/login",
        json={"email": ROLES["editor"], "password": TEST_PASSWORD},
    )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
