"""研究ワークスペース文書 API（実 PostgreSQL）。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from rihrp.db import SessionLocal
from rihrp.models import AuditEvent, ResearchDocument
from tests.conftest import login


def create_project(client: TestClient, title: str = "テスト研究") -> str:
    response = client.post("/api/projects", json={"title": title, "summary": ""})
    assert response.status_code == 201, response.text
    return response.json()["project"]["id"]


def test_get_returns_empty_document_before_save(client: TestClient, users: dict[str, str]) -> None:
    login(client)
    project_id = create_project(client)

    response = client.get(f"/api/projects/{project_id}/research")

    assert response.status_code == 200
    assert response.json() == {
        "version": 0,
        "payload": {},
        "updated_at": None,
        "updated_by": None,
    }


def test_put_creates_document_and_audits(client: TestClient, users: dict[str, str]) -> None:
    login(client)
    project_id = create_project(client)

    response = client.put(
        f"/api/projects/{project_id}/research",
        json={"expected_version": 0, "payload": {"hypothesis": "護岸の洗掘を30%低減する。"}},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version"] == 1
    assert body["payload"]["hypothesis"] == "護岸の洗掘を30%低減する。"

    with SessionLocal() as db:
        doc = db.get(ResearchDocument, project_id)
        assert doc is not None and doc.version == 1
        events = (
            db.execute(select(AuditEvent.action).where(AuditEvent.project_id == project_id))
            .scalars()
            .all()
        )
    assert "research.created" in events


def test_put_is_optimistically_locked(client: TestClient, users: dict[str, str]) -> None:
    login(client)
    project_id = create_project(client)
    first = client.put(
        f"/api/projects/{project_id}/research",
        json={"expected_version": 0, "payload": {"revision": 1}},
    )
    assert first.status_code == 200

    stale = client.put(
        f"/api/projects/{project_id}/research",
        json={"expected_version": 0, "payload": {"revision": 2}},
    )

    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "version_conflict"
    assert stale.json()["error"]["details"]["current_version"] == 1


def test_put_increments_version(client: TestClient, users: dict[str, str]) -> None:
    login(client)
    project_id = create_project(client)
    client.put(
        f"/api/projects/{project_id}/research",
        json={"expected_version": 0, "payload": {"n": 1}},
    )
    second = client.put(
        f"/api/projects/{project_id}/research",
        json={"expected_version": 1, "payload": {"n": 2}},
    )

    assert second.status_code == 200
    assert second.json()["version"] == 2
    fetched = client.get(f"/api/projects/{project_id}/research").json()
    assert fetched["version"] == 2
    assert fetched["payload"] == {"n": 2}


def test_viewer_cannot_write(client: TestClient, users: dict[str, str]) -> None:
    login(client)
    project_id = create_project(client)
    login(client, "viewer")

    response = client.put(
        f"/api/projects/{project_id}/research",
        json={"expected_version": 0, "payload": {"x": 1}},
    )

    assert response.status_code == 403


def test_unauthenticated_get_rejected(client: TestClient, users: dict[str, str]) -> None:
    login(client)
    project_id = create_project(client)

    with TestClient(client.app) as anonymous:
        response = anonymous.get(f"/api/projects/{project_id}/research")

    assert response.status_code == 401


def test_unknown_project_returns_404(client: TestClient, users: dict[str, str]) -> None:
    login(client)
    response = client.get("/api/projects/does-not-exist/research")
    assert response.status_code == 404


def test_oversized_document_rejected(client: TestClient, users: dict[str, str]) -> None:
    login(client)
    project_id = create_project(client)
    big = "x" * (1024 * 1024 + 10)

    response = client.put(
        f"/api/projects/{project_id}/research",
        json={"expected_version": 0, "payload": {"big": big}},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


def test_meta_endpoint(client: TestClient, users: dict[str, str]) -> None:
    login(client)
    project_id = create_project(client)
    assert client.get(f"/api/projects/{project_id}/research/meta").json() == {"version": 0}
    client.put(
        f"/api/projects/{project_id}/research",
        json={"expected_version": 0, "payload": {"a": 1}},
    )
    assert client.get(f"/api/projects/{project_id}/research/meta").json() == {"version": 1}


def test_project_delete_cascades_document(client: TestClient, users: dict[str, str]) -> None:
    login(client)
    project_id = create_project(client)
    client.put(
        f"/api/projects/{project_id}/research",
        json={"expected_version": 0, "payload": {"a": 1}},
    )
    with SessionLocal() as db:
        assert db.get(ResearchDocument, project_id) is not None

    login(client, "admin")
    response = client.delete(f"/api/projects/{project_id}")
    assert response.status_code == 200

    with SessionLocal() as db:
        assert db.get(ResearchDocument, project_id) is None
