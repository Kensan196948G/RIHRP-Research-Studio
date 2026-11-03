"""研究ワークスペース文書 API（実 PostgreSQL）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from rihrp.db import SessionLocal
from rihrp.models import AuditEvent, ResearchDocument
from rihrp.schemas import TASK_KEYS
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


@pytest.mark.parametrize(
    "payload",
    [
        {"revisions": "not-a-list"},
        {"tasks": [{"key": "struct", "status": "bogus"}]},
        {"evidence": [{"stance": "bogus"}]},
        {"critiques": [{"sev": "超高"}]},
        {"candidates": [{"status": "unknown"}]},
        {"weights": {"evidence": "high"}},
        {"revision": "1"},
        {"title": ["配列は不可"]},
    ],
)
def test_invalid_payload_rejected(client: TestClient, users: dict[str, str], payload: dict) -> None:
    login(client)
    project_id = create_project(client)

    response = client.put(
        f"/api/projects/{project_id}/research",
        json={"expected_version": 0, "payload": payload},
    )

    assert response.status_code == 422


def test_valid_nested_payload_accepted(client: TestClient, users: dict[str, str]) -> None:
    login(client)
    project_id = create_project(client)
    payload = {
        "title": "検証",
        "revision": 2,
        "tasks": _valid_tasks(),
        "evidence": [{"title": "資料", "stance": "support", "relevance": 50}],
        "critiques": [{"sev": "高", "status": "未対応"}],
        "candidates": [{"label": "H1", "status": "採択", "scores": {"evidence": 10}}],
        "weights": {"evidence": 25},
        "analysis": {
            "field": "river",
            "iv": "流量",
            "dv": None,
            "dir": "低減",
            "vars": ["流量"],
            "inferred": [],
            "nums": ["10%"],
            "hasNum": True,
            "hasMech": False,
            "hasCond": False,
            "hasComp": True,
            "vague": [],
            "quality": 3,
        },
    }

    response = client.put(
        f"/api/projects/{project_id}/research",
        json={"expected_version": 0, "payload": payload},
    )

    assert response.status_code == 200, response.text
    assert response.json()["payload"]["tasks"][0]["status"] == "done"


def _valid_tasks() -> list[dict]:
    return [{"key": key, "status": "done", "progress": 100, "runs": 1} for key in sorted(TASK_KEYS)]


@pytest.mark.parametrize(
    "payload",
    [
        {"field": "bogus"},
        {"constraints": []},
        {"constraints": {"budget": "無限"}},
        {"tasks": [{"key": "struct", "status": "done"}]},
        {
            "tasks": [dict(item) for item in _valid_tasks()][:-1]
            + [{"key": "struct", "status": "done"}]
        },
        {
            "tasks": [dict(item) for item in _valid_tasks()][:-1]
            + [{"key": "bogus", "status": "done"}]
        },
        {
            "tasks": [dict(item) for item in _valid_tasks()][:-1]
            + [{"key": "report", "status": "done", "progress": 101}]
        },
        {"candidates": [{"label": ["配列は不可"]}]},
        {"candidates": [{"label": "x" * 51}]},
        {"candidates": [{"scores": {"evidence": 101}}]},
        {"plan": {"methods": [{"n": "x", "cost": 9, "time": 3, "val": 3}]}},
        {"plan": {"measures": [{"n": "x", "role": "謎の役割"}]}},
        {"weights": {"evidence": 60}},
        {"weights": {"unknown": 10}},
        {"evidence": [{"relevance": 101}]},
        {"evidence": [{"tags": "not-a-list"}]},
        {"analysis": {"field": "bogus"}},
        {"analysis": {"field": "river", "vars": "not-a-list"}},
        {"analysis": {"field": "river", "quality": 9}},
        {"field": ["river"]},
        {"constraints": {"budget": []}},
        {"tasks": [dict(item) for item in _valid_tasks()][:-1] + [{"key": "struct", "status": []}]},
        {"evidence": [{"stance": {}}]},
        {"critiques": [{"sev": []}]},
        {"candidates": [{"status": []}]},
        {"plan": {"measures": [{"n": "x", "role": []}]}},
        {"revision": -1},
    ],
)
def test_invalid_payload_variants_rejected(
    client: TestClient, users: dict[str, str], payload: dict
) -> None:
    login(client)
    project_id = create_project(client)

    response = client.put(
        f"/api/projects/{project_id}/research",
        json={"expected_version": 0, "payload": payload},
    )

    assert response.status_code == 422
