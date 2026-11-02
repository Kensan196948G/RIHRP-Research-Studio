"""主要業務フローとデータ整合性の結合テスト。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text

from rihrp.db import engine
from tests.conftest import login

SOURCE_TEXT = (
    "海洋再生可能エネルギー導入調査\n"
    "導入可能量は 1,240 MW と試算された。2026年度の実証事業は 3 件である。"
)


def create_project(client: TestClient, title: str = "テストテーマ") -> dict:
    response = client.post("/api/projects", json={"title": title, "summary": "テスト"})
    assert response.status_code == 201, response.text
    return response.json()["project"]


def create_source(client: TestClient, project_id: str, content: str = SOURCE_TEXT) -> dict:
    response = client.post(
        f"/api/projects/{project_id}/sources",
        json={
            "title": "出典A",
            "kind": "url",
            "origin": "https://example.org/a",
            "content": content,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["source"]


def create_claim(client: TestClient, project_id: str, claim_text: str) -> dict:
    response = client.post(f"/api/projects/{project_id}/claims", json={"text": claim_text})
    assert response.status_code == 201, response.text
    return response.json()["claim"]


def build_verified_claim(client: TestClient) -> tuple[dict, dict, dict]:
    project = create_project(client)
    source = create_source(client, project["id"])
    claim = create_claim(client, project["id"], "導入可能量は 1,240 MW と試算された。")
    response = client.post(
        f"/api/claims/{claim['id']}/evidence",
        json={"source_id": source["id"], "quote": "導入可能量は 1,240 MW", "note": ""},
    )
    assert response.status_code == 201, response.text
    result = client.post(f"/api/claims/{claim['id']}/verify")
    assert result.status_code == 200
    assert result.json()["result"]["verdict"] == "verified"
    return project, source, claim


def create_report_with_claim(
    client: TestClient, project: dict, claim: dict, title: str = "レポート"
) -> dict:
    response = client.post(f"/api/projects/{project['id']}/reports", json={"title": title})
    assert response.status_code == 201, response.text
    report = response.json()["report"]
    content = {
        "sections": [
            {
                "heading": "1. 導入可能量",
                "paragraphs": [
                    {
                        "id": "p1",
                        "text": "導入可能量は 1,240 MW と試算された。",
                        "claimIds": [claim["id"]],
                    }
                ],
            }
        ]
    }
    saved = client.put(f"/api/reports/{report['id']}", json={"content": content})
    assert saved.status_code == 200, saved.text
    return saved.json()["report"]


def test_main_flow_end_to_end(
    editor_client: TestClient, reviewer_client: TestClient, users: dict[str, str]
) -> None:
    project, source, claim = build_verified_claim(editor_client)

    report = create_report_with_claim(editor_client, project, claim)
    assert report["version"] == 2

    verified = editor_client.post(f"/api/reports/{report['id']}/verify")
    assert verified.status_code == 200
    assert verified.json()["summary"]["verified"] == 1
    assert verified.json()["summary"]["contradicted"] == 0

    submitted = editor_client.post(f"/api/reports/{report['id']}/submit")
    assert submitted.status_code == 200
    assert submitted.json()["report"]["status"] == "in_review"

    approved = reviewer_client.post(
        f"/api/reports/{report['id']}/review",
        json={"decision": "approved", "comment": "問題ありません。"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["report"]["status"] == "approved"

    export = reviewer_client.get(f"/api/reports/{report['id']}/export")
    assert export.status_code == 200
    body = export.text
    assert "[検証済]" in body
    assert "1,240 MW" in body
    assert source["content_sha256"][:12] in body

    versions = editor_client.get(f"/api/reports/{report['id']}/versions")
    assert versions.status_code == 200
    assert versions.json()["current"] == 2
    assert len(versions.json()["versions"]) == 2

    audit = reviewer_client.get("/api/audit?limit=100").json()["events"]
    actions = {event["action"] for event in audit}
    assert {
        "project.created",
        "source.created",
        "claim.created",
        "claim.verified",
        "report.submitted",
        "report.reviewed",
    } <= actions


def test_duplicate_source_rejected(editor_client: TestClient, users: dict[str, str]) -> None:
    project = create_project(editor_client)
    create_source(editor_client, project["id"])
    response = editor_client.post(
        f"/api/projects/{project['id']}/sources",
        json={"title": "同じ本文", "kind": "text", "origin": "", "content": SOURCE_TEXT},
    )
    assert response.status_code == 409


def test_quote_must_exist(editor_client: TestClient, users: dict[str, str]) -> None:
    project = create_project(editor_client)
    source = create_source(editor_client, project["id"])
    claim = create_claim(editor_client, project["id"], "導入可能量は 1,240 MW である。")
    response = editor_client.post(
        f"/api/claims/{claim['id']}/evidence",
        json={"source_id": source["id"], "quote": "存在しない引用", "note": ""},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "quote_not_found"


def test_tampered_snapshot_blocks_approval(
    editor_client: TestClient, reviewer_client: TestClient, users: dict[str, str]
) -> None:
    project, source, claim = build_verified_claim(editor_client)
    report = create_report_with_claim(editor_client, project, claim)
    assert editor_client.post(f"/api/reports/{report['id']}/submit").status_code == 200

    with engine.begin() as connection:
        connection.execute(
            text("UPDATE sources SET content = content || '（改竄）' WHERE id = :id"),
            {"id": source["id"]},
        )

    verify = editor_client.post(f"/api/claims/{claim['id']}/verify")
    assert verify.json()["result"]["verdict"] == "contradicted"
    assert verify.json()["result"]["reasons"] == ["evidence_tampered"]

    blocked = reviewer_client.post(
        f"/api/reports/{report['id']}/review",
        json={"decision": "approved", "comment": ""},
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "approval_blocked"
    assert blocked.json()["error"]["details"]["contradicted"] == 1


def test_source_in_use_cannot_be_deleted(editor_client: TestClient, users: dict[str, str]) -> None:
    _, source, _ = build_verified_claim(editor_client)
    response = editor_client.delete(f"/api/sources/{source['id']}")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "source_in_use"


def test_claim_in_report_cannot_be_deleted(
    editor_client: TestClient, users: dict[str, str]
) -> None:
    project, _, claim = build_verified_claim(editor_client)
    create_report_with_claim(editor_client, project, claim)
    response = editor_client.delete(f"/api/claims/{claim['id']}")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "claim_in_use"


def test_submitted_report_is_locked(editor_client: TestClient, users: dict[str, str]) -> None:
    project, _, claim = build_verified_claim(editor_client)
    report = create_report_with_claim(editor_client, project, claim)
    editor_client.post(f"/api/reports/{report['id']}/submit")
    response = editor_client.put(f"/api/reports/{report['id']}", json={"title": "変更"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "report_locked"


def test_self_approval_forbidden(editor_client: TestClient, users: dict[str, str]) -> None:
    project, _, claim = build_verified_claim(editor_client)
    report = create_report_with_claim(editor_client, project, claim)
    editor_client.post(f"/api/reports/{report['id']}/submit")
    # admin は editor と reviewer の両方の権限を持つ。提出者本人の承認は 403。
    admin = TestClient(editor_client.app)
    login(admin, "admin")
    # admin が提出したレポートを作るため、まず admin で提出する
    admin_report = create_report_with_claim(admin, project, claim, title="admin 提出")
    assert admin.post(f"/api/reports/{admin_report['id']}/submit").status_code == 200
    blocked = admin.post(
        f"/api/reports/{admin_report['id']}/review",
        json={"decision": "approved", "comment": ""},
    )
    assert blocked.status_code == 403


def test_review_requires_comment_for_changes(
    editor_client: TestClient, reviewer_client: TestClient, users: dict[str, str]
) -> None:
    project, _, claim = build_verified_claim(editor_client)
    report = create_report_with_claim(editor_client, project, claim)
    editor_client.post(f"/api/reports/{report['id']}/submit")
    short = reviewer_client.post(
        f"/api/reports/{report['id']}/review",
        json={"decision": "changes_requested", "comment": "短い"},
    )
    assert short.status_code == 422
    ok = reviewer_client.post(
        f"/api/reports/{report['id']}/review",
        json={"decision": "changes_requested", "comment": "根拠の追加が必要です。"},
    )
    assert ok.status_code == 200
    assert ok.json()["report"]["status"] == "changes_requested"


def test_health_and_ready(client: TestClient, users: dict[str, str]) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}
    ready = client.get("/readyz")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"


def test_approved_report_flags_post_approval_tamper(
    editor_client: TestClient, reviewer_client: TestClient, users: dict[str, str]
) -> None:
    project, source, claim = build_verified_claim(editor_client)
    report = create_report_with_claim(editor_client, project, claim)
    assert editor_client.post(f"/api/reports/{report['id']}/submit").status_code == 200
    assert (
        reviewer_client.post(
            f"/api/reports/{report['id']}/review",
            json={"decision": "approved", "comment": ""},
        ).status_code
        == 200
    )

    with engine.begin() as connection:
        connection.execute(
            text("UPDATE sources SET content = content || '（改竄）' WHERE id = :id"),
            {"id": source["id"]},
        )
    assert (
        editor_client.post(f"/api/claims/{claim['id']}/verify").json()["result"]["verdict"]
        == "contradicted"
    )

    fetched = editor_client.get(f"/api/reports/{report['id']}").json()["report"]
    assert fetched["status"] == "approved"
    assert fetched["integrity"]["contradicted"] == 1
    assert fetched["integrity"]["needs_reapproval"] is True


def test_blocked_approval_persists_verification(
    editor_client: TestClient, reviewer_client: TestClient, users: dict[str, str]
) -> None:
    project, source, claim = build_verified_claim(editor_client)
    report = create_report_with_claim(editor_client, project, claim)
    assert editor_client.post(f"/api/reports/{report['id']}/submit").status_code == 200

    with engine.begin() as connection:
        connection.execute(
            text("UPDATE sources SET content = content || '（改竄）' WHERE id = :id"),
            {"id": source["id"]},
        )

    blocked = reviewer_client.post(
        f"/api/reports/{report['id']}/review",
        json={"decision": "approved", "comment": ""},
    )
    assert blocked.status_code == 409

    # 拒否後も検証結果と監査は残る（ロールバックで消えない）
    fetched_claim = editor_client.get(f"/api/claims/{claim['id']}").json()["claim"]
    assert fetched_claim["last_verdict"] == "contradicted"
    audit = reviewer_client.get("/api/audit?limit=100").json()["events"]
    assert any(event["action"] == "report.verified" for event in audit)
    report_after = editor_client.get(f"/api/reports/{report['id']}").json()["report"]
    assert report_after["status"] == "in_review"
