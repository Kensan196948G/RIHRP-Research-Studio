"""品質ゲート P2（API/DB ケース）の実測実行。"""

from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import event, select

from rihrp.auth import utcnow
from rihrp.config import get_settings
from rihrp.db import SessionLocal, engine
from rihrp.maintenance import purge_sessions
from rihrp.models import Session as SessionRow
from rihrp.seed import seed_users
from tests.gate.conftest import DEMO_PASSWORD, login_as, new_client
from tests.gate.harness import Case


def create_project(client: TestClient, title: str = "P2テーマ") -> dict:
    response = client.post("/api/projects", json={"title": title, "summary": ""})
    assert response.status_code == 201, response.text
    return response.json()["project"]


def create_source(client: TestClient, project_id: str, **overrides):
    payload = {"title": "出典", "kind": "text", "origin": "", "content": "本文"}
    payload.update(overrides)
    return client.post(f"/api/projects/{project_id}/sources", json=payload)


# ---------------------------------------------------------------- 1 source title/kind boundary
def test_tc_mw7pi02b_source_title_boundary(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7pi02b_977c69f9", "出典の空・300/301 文字")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    project = create_project(client)
    empty_title = create_source(client, project["id"], title="")
    exactly = create_source(client, project["id"], title="あ" * 300, content="300")
    over = create_source(client, project["id"], title="あ" * 301, content="301")
    empty_content = create_source(client, project["id"], content="")
    bad_kind = create_source(client, project["id"], kind="pdf", content="kind")
    case.step(
        "responses",
        empty_title=empty_title.status_code,
        exactly=exactly.status_code,
        over=over.status_code,
        empty_content=empty_content.status_code,
        bad_kind=bad_kind.status_code,
    )
    case.expect(empty_title.status_code == 422, f"空 title が {empty_title.status_code}")
    case.expect(exactly.status_code == 201, f"300 文字が {exactly.status_code}")
    case.expect(over.status_code == 422, f"301 文字が {over.status_code}")
    case.expect(empty_content.status_code == 422, f"空本文が {empty_content.status_code}")
    case.expect(bad_kind.status_code == 422, f"不正 kind が {bad_kind.status_code}")
    case.finish()


# ---------------------------------------------------------------- 2 HTTP 2 MiB boundary
def test_tc_mw7pjycx_http_body_boundary(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7pjycx_0f6c61e2", "HTTP 本文 2 MiB 境界")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    limit = 2 * 1024 * 1024
    over_payload = '{"title":"' + "a" * (limit + 1) + '"}'
    under_payload = '{"title":"' + "a" * (limit - 200) + '"}'
    over = client.post(
        "/api/projects", content=over_payload, headers={"Content-Type": "application/json"}
    )
    under = client.post(
        "/api/projects", content=under_payload, headers={"Content-Type": "application/json"}
    )
    case.step(
        "responses",
        over={"status": over.status_code, "error": over.json().get("error")},
        under={"status": under.status_code, "error": under.json().get("error")},
    )
    case.expect(over.status_code == 413, f"2 MiB 超が {over.status_code}")
    case.expect(
        over.json().get("error", {}).get("code") == "payload_too_large",
        "code が payload_too_large でない",
    )
    case.expect(under.status_code != 413, f"2 MiB 以下が {under.status_code}")
    case.finish()


# ---------------------------------------------------------------- 3 report length boundary
def test_tc_mw7pqh8n_report_length_boundary(
    client: TestClient, demo_users: dict[str, dict]
) -> None:
    case = Case("tc_mw7pqh8n_f73d2880", "レポート長境界")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    project = create_project(client)
    title_200 = client.post(f"/api/projects/{project['id']}/reports", json={"title": "あ" * 200})
    title_201 = client.post(f"/api/projects/{project['id']}/reports", json={"title": "あ" * 201})
    report = title_200.json()["report"]

    def put_paragraph(value: str):
        return client.put(
            f"/api/reports/{report['id']}",
            json={
                "content": {
                    "sections": [
                        {
                            "id": "s1",
                            "heading": "h",
                            "paragraphs": [{"id": "p1", "text": value, "claimIds": []}],
                        }
                    ]
                },
                "expected_version": report["version"],
            },
        )

    para_20000 = put_paragraph("あ" * 20000)
    report2 = client.post(f"/api/projects/{project['id']}/reports", json={"title": "境界2"}).json()[
        "report"
    ]
    para_20001 = client.put(
        f"/api/reports/{report2['id']}",
        json={
            "content": {
                "sections": [
                    {
                        "id": "s1",
                        "heading": "h",
                        "paragraphs": [{"id": "p1", "text": "あ" * 20001, "claimIds": []}],
                    }
                ]
            },
            "expected_version": report2["version"],
        },
    )
    case.step(
        "responses",
        title_200=title_200.status_code,
        title_201=title_201.status_code,
        para_20000=para_20000.status_code,
        para_20001=para_20001.status_code,
    )
    case.expect(title_200.status_code == 201, f"title 200 が {title_200.status_code}")
    case.expect(title_201.status_code == 422, f"title 201 が {title_201.status_code}")
    case.expect(para_20000.status_code == 200, f"段落 20000 が {para_20000.status_code}")
    case.expect(para_20001.status_code == 422, f"段落 20001 が {para_20001.status_code}")
    case.finish()


# ---------------------------------------------------------------- 4 research doc shape
def test_tc_mw7pqh90_research_shape(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7pqh90_5ad8f33a", "研究文書の形状・413")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    project = create_project(client)
    base = f"/api/projects/{project['id']}/research"

    ok = client.put(base, json={"expected_version": 0, "payload": {"revision": 1}})
    negative_revision = client.put(base, json={"expected_version": 1, "payload": {"revision": -1}})
    bad_field = client.put(base, json={"expected_version": 1, "payload": {"field": "unknown"}})
    bad_task_status = client.put(
        base,
        json={"expected_version": 1, "payload": {"tasks": [{"status": "bogus"}]}},
    )
    bad_version_type = client.put(base, json={"expected_version": "abc", "payload": {}})
    too_large = client.put(
        base,
        json={"expected_version": 1, "payload": {"big": "x" * (1024 * 1024 + 10)}},
    )
    wrong_version = client.put(base, json={"expected_version": 99, "payload": {"revision": 2}})
    case.step(
        "responses",
        ok=ok.status_code,
        negative_revision=negative_revision.status_code,
        bad_field=bad_field.status_code,
        bad_task_status=bad_task_status.status_code,
        bad_version_type=bad_version_type.status_code,
        too_large=too_large.status_code,
        wrong_version=wrong_version.status_code,
    )
    case.expect(ok.status_code == 200, f"正常保存が {ok.status_code}")
    case.expect(
        negative_revision.status_code == 422, f"revision -1 が {negative_revision.status_code}"
    )
    case.expect(bad_field.status_code == 422, f"不正 enum が {bad_field.status_code}")
    case.expect(
        bad_task_status.status_code == 422, f"不正 task status が {bad_task_status.status_code}"
    )
    case.expect(
        bad_version_type.status_code == 422,
        f"expected_version 型違いが {bad_version_type.status_code}",
    )
    case.expect(too_large.status_code == 413, f"1 MiB 超が {too_large.status_code}")
    case.expect(wrong_version.status_code == 409, f"版不一致が {wrong_version.status_code}")
    case.finish()


# ---------------------------------------------------------------- 5 audit across themes
def test_tc_mw7pqh9v_audit_all_themes(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7pqh9v_ec0baca7", "監査の全テーマ閲覧")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    a = create_project(client, "監査テーマA")
    b = create_project(client, "監査テーマB")
    create_source(client, a["id"], content="A")
    create_source(client, b["id"], content="B")
    with new_client() as reviewer:
        login_as(reviewer, demo_users["reviewer"]["email"], DEMO_PASSWORD)
        all_events = reviewer.get("/api/audit", params={"limit": 500})
        only_a = reviewer.get("/api/audit", params={"project_id": a["id"], "limit": 500})
    actions_all = [event["action"] for event in all_events.json()["events"]]
    project_ids = {event.get("project_id") for event in only_a.json()["events"]}
    case.step(
        "audit",
        all_status=all_events.status_code,
        filtered_status=only_a.status_code,
        actions=sorted(set(actions_all)),
        filtered_projects=sorted(project_ids),
    )
    case.expect(all_events.status_code == 200, f"全件が {all_events.status_code}")
    case.expect(only_a.status_code == 200, f"絞り込みが {only_a.status_code}")
    case.expect("source.created" in actions_all, "source.created が全件にない")
    case.expect(project_ids == {a["id"]}, f"project_id 絞り込みが {project_ids}")
    case.finish()


# ---------------------------------------------------------------- 6 expired session purge
def test_tc_mw7pjgwr_session_purge(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7pjgwr_373e87f3", "期限切れセッション削除")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    with SessionLocal() as db:
        expired = SessionRow(
            user_id=demo_users["editor"]["id"],
            token_hash="expired-token-hash",
            csrf_token="csrf",
            expires_at=utcnow() - timedelta(days=10),
        )
        valid = SessionRow(
            user_id=demo_users["editor"]["id"],
            token_hash="valid-token-hash",
            csrf_token="csrf",
            expires_at=utcnow() + timedelta(days=1),
        )
        db.add_all([expired, valid])
        db.commit()
        expired_id, valid_id = expired.id, valid.id
    deleted = purge_sessions(days=7)
    with SessionLocal() as db:
        remaining = {
            row.id
            for row in db.execute(
                select(SessionRow).where(SessionRow.id.in_([expired_id, valid_id]))
            ).scalars()
        }
    case.step("purge", deleted=deleted, remaining=sorted(remaining))
    case.expect(expired_id not in remaining, "期限切れセッションが残っている")
    case.expect(valid_id in remaining, "有効セッションが削除された")
    case.finish()


# ---------------------------------------------------------------- 7 seed env control
def test_tc_mw7pmf5e_seed_env_control(
    client: TestClient, demo_users: dict[str, dict], monkeypatch
) -> None:
    case = Case("tc_mw7pmf5e_a1810570", "seed の環境変数制御")
    monkeypatch.delenv("RIHRP_SEED_PASSWORD", raising=False)
    with SessionLocal() as db:
        without_password = seed_users(db)
    monkeypatch.setenv("RIHRP_SEED_PASSWORD", "seed-password-123")
    with SessionLocal() as db:
        with_password = seed_users(db)
    settings = get_settings()
    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.setattr(settings, "seed_demo", True)
    production_gate = settings.seed_demo and not settings.is_production
    case.step(
        "seed",
        without_password=len(without_password),
        with_password=sorted(with_password),
        production_gate=production_gate,
    )
    case.expect(without_password == {}, "パスワード未設定でも投入された")
    case.expect(
        set(with_password) == {"admin", "editor", "reviewer", "viewer"}, "4 ロールが投入されない"
    )
    case.expect(production_gate is False, "production で seed が許可されている")
    case.finish()


# ---------------------------------------------------------------- 8 N+1 avoidance
def test_tc_mw7pmf73_no_n_plus_one(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7pmf73_a3b93813", "N+1 回避（クエリ数）")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    project = create_project(client)
    source = client.post(
        f"/api/projects/{project['id']}/sources",
        json={"title": "出典", "kind": "text", "origin": "", "content": "N+1 本文"},
    ).json()["source"]
    for index in range(10):
        claim = client.post(
            f"/api/projects/{project['id']}/claims",
            json={"text": f"主張 {index:02d} は十分な長さを持っています。"},
        ).json()["claim"]
        client.post(
            f"/api/claims/{claim['id']}/evidence",
            json={"source_id": source["id"], "quote": "", "note": ""},
        )

    statements: list[str] = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        response = client.get(f"/api/projects/{project['id']}/claims")
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)
    count = len(statements)
    case.step(
        "queries", status=response.status_code, count=count, claims=len(response.json()["claims"])
    )
    case.expect(response.status_code == 200, f"一覧が {response.status_code}")
    case.expect(len(response.json()["claims"]) == 10, "主張が 10 件でない")
    case.expect(count <= 5, f"クエリ数が {count}（N+1 の疑い）")
    case.finish()
