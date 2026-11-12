"""AI 支援レポートの承認条件（ADR-0003 改訂）の結合テスト。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.integration.test_flow_integrity import (
    build_verified_claim,
    create_claim,
    create_project,
    create_report_with_claim,
)


def _insufficient_claim(client: TestClient, project: dict) -> dict:
    # 根拠を紐付けないので verify は insufficient になる。
    return create_claim(client, project["id"], "根拠のない主張は 42 という数値を持つ。")


def test_ai_assisted_report_with_insufficient_claim_is_blocked(
    editor_client: TestClient, reviewer_client: TestClient
) -> None:
    project = create_project(editor_client, "AI支援レポート")
    claim = _insufficient_claim(editor_client, project)
    report = create_report_with_claim(editor_client, project, claim)

    submitted = editor_client.post(
        f"/api/reports/{report['id']}/submit", json={"ai_assisted": True}
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["report"]["ai_assisted"] is True

    approved = reviewer_client.post(
        f"/api/reports/{report['id']}/review",
        json={"decision": "approved", "comment": ""},
    )
    assert approved.status_code == 409, approved.text
    error = approved.json()["error"]
    assert error["code"] == "approval_blocked"
    assert error["details"]["ai_assisted"] is True
    assert error["details"]["insufficient"] == 1


def test_non_ai_report_with_insufficient_claim_keeps_current_rule(
    editor_client: TestClient, reviewer_client: TestClient
) -> None:
    project = create_project(editor_client, "通常レポート")
    claim = _insufficient_claim(editor_client, project)
    report = create_report_with_claim(editor_client, project, claim)

    submitted = editor_client.post(f"/api/reports/{report['id']}/submit")
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["report"]["ai_assisted"] is False

    approved = reviewer_client.post(
        f"/api/reports/{report['id']}/review",
        json={"decision": "approved", "comment": ""},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["report"]["status"] == "approved"


def test_ai_assisted_report_with_all_verified_claims_is_approved(
    editor_client: TestClient, reviewer_client: TestClient
) -> None:
    project, _source, claim = build_verified_claim(editor_client)
    report = create_report_with_claim(editor_client, project, claim)

    submitted = editor_client.post(
        f"/api/reports/{report['id']}/submit", json={"ai_assisted": True}
    )
    assert submitted.status_code == 200, submitted.text

    approved = reviewer_client.post(
        f"/api/reports/{report['id']}/review",
        json={"decision": "approved", "comment": ""},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["report"]["status"] == "approved"


def test_ai_assisted_flag_cannot_be_withdrawn_on_resubmit(
    editor_client: TestClient, reviewer_client: TestClient
) -> None:
    project = create_project(editor_client, "申告の固定")
    claim = _insufficient_claim(editor_client, project)
    report = create_report_with_claim(editor_client, project, claim)

    first = editor_client.post(f"/api/reports/{report['id']}/submit", json={"ai_assisted": True})
    assert first.status_code == 200, first.text

    returned = reviewer_client.post(
        f"/api/reports/{report['id']}/review",
        json={"decision": "changes_requested", "comment": "根拠を追加してください。"},
    )
    assert returned.status_code == 200, returned.text

    second = editor_client.post(f"/api/reports/{report['id']}/submit", json={"ai_assisted": False})
    assert second.status_code == 200, second.text
    assert second.json()["report"]["ai_assisted"] is True

    blocked = reviewer_client.post(
        f"/api/reports/{report['id']}/review",
        json={"decision": "approved", "comment": ""},
    )
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["error"]["details"]["ai_assisted"] is True
