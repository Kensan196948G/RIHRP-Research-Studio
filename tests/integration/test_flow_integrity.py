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
    saved = client.put(
        f"/api/reports/{report['id']}",
        json={"content": content, "expected_version": report["version"]},
    )
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


def test_report_save_rejects_stale_version(
    editor_client: TestClient, users: dict[str, str]
) -> None:
    project, _, claim = build_verified_claim(editor_client)
    report = create_report_with_claim(editor_client, project, claim)  # version 2
    stale = editor_client.put(
        f"/api/reports/{report['id']}",
        json={"expected_version": 1, "content": {"sections": []}},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "version_conflict"
    assert stale.json()["error"]["details"]["current_version"] == 2

    ok = editor_client.put(
        f"/api/reports/{report['id']}",
        json={"expected_version": 2, "content": {"sections": []}},
    )
    assert ok.status_code == 200
    assert ok.json()["report"]["version"] == 3


def test_claim_update_resets_verdict(editor_client: TestClient, users: dict[str, str]) -> None:
    project, source, claim = build_verified_claim(editor_client)
    updated = editor_client.patch(
        f"/api/claims/{claim['id']}", json={"text": "導入可能量は 1,240 MW と試算された（改訂）。"}
    )
    assert updated.status_code == 200
    assert updated.json()["claim"]["last_verdict"] is None
    assert updated.json()["claim"]["last_verified_at"] is None
    again = editor_client.post(f"/api/claims/{claim['id']}/verify")
    assert again.json()["result"]["verdict"] == "verified"


def test_project_update_and_archive(editor_client: TestClient, users: dict[str, str]) -> None:
    project = create_project(editor_client)
    response = editor_client.patch(
        f"/api/projects/{project['id']}",
        json={"title": "更新後テーマ", "summary": "更新後概要", "status": "archived"},
    )
    assert response.status_code == 200
    updated = response.json()["project"]
    assert updated["title"] == "更新後テーマ"
    assert updated["summary"] == "更新後概要"
    assert updated["status"] == "archived"


def test_approved_report_flags_claim_edit(
    editor_client: TestClient, reviewer_client: TestClient, users: dict[str, str]
) -> None:
    project, _, claim = build_verified_claim(editor_client)
    report = create_report_with_claim(editor_client, project, claim)
    assert editor_client.post(f"/api/reports/{report['id']}/submit").status_code == 200
    assert (
        reviewer_client.post(
            f"/api/reports/{report['id']}/review",
            json={"decision": "approved", "comment": ""},
        ).status_code
        == 200
    )

    edited = editor_client.patch(
        f"/api/claims/{claim['id']}",
        json={"text": "導入可能量は 1,240 MW と試算された（改訂）。"},
    )
    assert edited.status_code == 200
    assert edited.json()["claim"]["last_verdict"] is None

    fetched = editor_client.get(f"/api/reports/{report['id']}").json()["report"]
    assert fetched["status"] == "approved"
    assert fetched["integrity"]["unchecked"] == 1
    assert fetched["integrity"]["needs_reapproval"] is True


def test_claim_list_reports_evidence_count(
    editor_client: TestClient, users: dict[str, str]
) -> None:
    project = create_project(editor_client)
    source = create_source(editor_client, project["id"])
    claim = create_claim(editor_client, project["id"], "導入可能量は 1,240 MW と試算された。")
    for quote in ["導入可能量は 1,240 MW", "2026年度の実証事業は 3 件"]:
        response = editor_client.post(
            f"/api/claims/{claim['id']}/evidence",
            json={"source_id": source["id"], "quote": quote, "note": ""},
        )
        assert response.status_code == 201, response.text
    listed = editor_client.get(f"/api/projects/{project['id']}/claims").json()["claims"]
    assert [c["evidence_count"] for c in listed if c["id"] == claim["id"]] == [2]


def test_export_includes_only_referenced_claims(
    editor_client: TestClient, users: dict[str, str]
) -> None:
    project, _, claim = build_verified_claim(editor_client)
    unreferenced = create_claim(editor_client, project["id"], "参照されない主張は 777 MW である。")
    report = create_report_with_claim(editor_client, project, claim)
    body = editor_client.get(f"/api/reports/{report['id']}/export").text
    assert "1,240 MW" in body
    assert "777 MW" not in body
    assert unreferenced["text"] not in body


def test_readyz_reports_migration_mismatch(client: TestClient, users: dict[str, str]) -> None:
    with engine.begin() as connection:
        original = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    try:
        with engine.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num = 'deadbeef'"))
        response = client.get("/readyz")
        assert response.status_code == 503
        assert response.json()["reason"] == "migration_pending"
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE alembic_version SET version_num = :version"),
                {"version": original},
            )


def test_audit_records_request_id_and_header(
    editor_client: TestClient, users: dict[str, str]
) -> None:
    response = editor_client.post("/api/projects", json={"title": "相関ID", "summary": ""})
    assert response.status_code == 201
    request_id = response.headers.get("X-Request-Id")
    assert request_id and len(request_id) == 32

    with engine.begin() as connection:
        stored = connection.execute(
            text(
                "SELECT request_id FROM audit_events "
                "WHERE action = 'project.created' "
                "ORDER BY created_at DESC LIMIT 1"
            )
        ).scalar_one()
    assert stored == request_id


def test_missing_claim_reference_blocks_approval(
    editor_client: TestClient, reviewer_client: TestClient, users: dict[str, str]
) -> None:
    project, _, claim = build_verified_claim(editor_client)
    report = create_report_with_claim(editor_client, project, claim)
    assert editor_client.post(f"/api/reports/{report['id']}/submit").status_code == 200

    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM claim_evidence WHERE claim_id = :id"), {"id": claim["id"]}
        )
        connection.execute(text("DELETE FROM claims WHERE id = :id"), {"id": claim["id"]})

    fetched = editor_client.get(f"/api/reports/{report['id']}").json()["report"]
    assert fetched["integrity"]["missing_claim_ids"] == [claim["id"]]
    assert fetched["integrity"]["needs_reapproval"] is True

    blocked = reviewer_client.post(
        f"/api/reports/{report['id']}/review",
        json={"decision": "approved", "comment": ""},
    )
    assert blocked.status_code == 409
    assert claim["id"] in blocked.json()["error"]["details"]["missing_claim_ids"]


def test_integrity_detects_tampered_source(
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

    fetched = editor_client.get(f"/api/reports/{report['id']}").json()["report"]
    assert fetched["integrity"]["tampered_sources"] == 1
    assert fetched["integrity"]["needs_reapproval"] is True

    exported = editor_client.get(f"/api/reports/{report['id']}/export").text
    assert "矛盾（スナップショット改竄）" in exported


def test_report_content_update_requires_expected_version(
    editor_client: TestClient, users: dict[str, str]
) -> None:
    project, _, _ = build_verified_claim(editor_client)
    report = editor_client.post(
        f"/api/projects/{project['id']}/reports", json={"title": "版必須"}
    ).json()["report"]
    response = editor_client.put(
        f"/api/reports/{report['id']}",
        json={"content": {"sections": []}},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_evidence_audit_has_entity_id(editor_client: TestClient, users: dict[str, str]) -> None:
    project = create_project(editor_client)
    source = create_source(editor_client, project["id"])
    claim = create_claim(editor_client, project["id"], "導入可能量は 1,240 MW と試算された。")
    editor_client.post(
        f"/api/claims/{claim['id']}/evidence",
        json={"source_id": source["id"], "quote": "導入可能量は 1,240 MW", "note": ""},
    )
    with engine.begin() as connection:
        entity_id = connection.execute(
            text(
                "SELECT entity_id FROM audit_events "
                "WHERE action = 'evidence.created' ORDER BY created_at DESC LIMIT 1"
            )
        ).scalar_one()
    assert entity_id


def test_whitespace_and_short_values_rejected(
    editor_client: TestClient, users: dict[str, str]
) -> None:
    project = editor_client.post("/api/projects", json={"title": "   ", "summary": ""})
    assert project.status_code == 422

    created = create_project(editor_client)
    claim = editor_client.post(
        f"/api/projects/{created['id']}/claims",
        json={"text": "          "},
    )
    assert claim.status_code == 422
