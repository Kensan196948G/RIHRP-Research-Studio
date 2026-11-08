"""品質ゲート P1（API/DB ケース）の実測実行。

UI・運用・性能に依存する P1 ケースは別途扱う（このファイルでは API/DB のみ）。
"""

from __future__ import annotations

import concurrent.futures
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select, text

from rihrp.auth import reset_login_rate
from rihrp.config import get_settings
from rihrp.db import SessionLocal, engine
from rihrp.maintenance import purge_audit
from rihrp.models import AuditEvent, ReportVerification, Review
from rihrp.models import Session as SessionRow
from tests.gate.conftest import DEMO_PASSWORD, login_as, new_client
from tests.gate.harness import Case

SOURCE_TEXT = "海岸護岸の洗掘深さは 50 cm を超える。導入可能量は 1,240 MW と試算された。"


def create_project(client: TestClient, title: str = "P1テーマ") -> dict:
    response = client.post("/api/projects", json={"title": title, "summary": ""})
    assert response.status_code == 201, response.text
    return response.json()["project"]


def create_source(
    client: TestClient,
    project_id: str,
    *,
    content: str = SOURCE_TEXT,
    title: str = "出典",
    origin: str = "https://example.test/p1",
) -> dict:
    response = client.post(
        f"/api/projects/{project_id}/sources",
        json={"title": title, "kind": "url", "origin": origin, "content": content},
    )
    assert response.status_code == 201, response.text
    return response.json()["source"]


def create_claim(client: TestClient, project_id: str, value: str) -> dict:
    response = client.post(f"/api/projects/{project_id}/claims", json={"text": value})
    assert response.status_code == 201, response.text
    return response.json()["claim"]


def add_evidence(client: TestClient, claim_id: str, source_id: str, quote: str = ""):
    return client.post(
        f"/api/claims/{claim_id}/evidence",
        json={"source_id": source_id, "quote": quote, "note": ""},
    )


def create_report(client: TestClient, project_id: str, title: str = "P1レポート") -> dict:
    response = client.post(f"/api/projects/{project_id}/reports", json={"title": title})
    assert response.status_code == 201, response.text
    return response.json()["report"]


def save_report(client: TestClient, report: dict, claim_ids: list[str], body: str) -> dict:
    content = {
        "sections": [
            {
                "id": "s1",
                "heading": "1. 検証",
                "paragraphs": [{"id": "p1", "text": body, "claimIds": claim_ids}],
            }
        ]
    }
    response = client.put(
        f"/api/reports/{report['id']}",
        json={"content": content, "expected_version": report["version"]},
    )
    assert response.status_code == 200, response.text
    return response.json()["report"]


def create_user_as_admin(admin: TestClient, email: str, role: str = "editor") -> dict:
    response = admin.post(
        "/api/users",
        json={
            "email": email,
            "name": email.split("@")[0],
            "role": role,
            "password": "user-password-123",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["user"]


# ---------------------------------------------------------------- 1 rate limit
def test_tc_mw7phjz4_login_rate_limit(
    client: TestClient, demo_users: dict[str, dict], monkeypatch
) -> None:
    import time

    case = Case("tc_mw7phjz4_758bbf96", "レート制限 10/11 回・60 秒")
    monkeypatch.setattr(get_settings(), "login_rate_limit", 10)
    reset_login_rate()
    client.headers.pop("X-CSRF-Token", None)
    editor = demo_users["editor"]
    statuses = []
    for _ in range(10):
        statuses.append(
            client.post(
                "/api/auth/login", json={"email": editor["email"], "password": "wrong-password"}
            ).status_code
        )
    eleventh = client.post(
        "/api/auth/login", json={"email": editor["email"], "password": "wrong-password"}
    )
    time.sleep(61)
    after_wait = client.post(
        "/api/auth/login", json={"email": editor["email"], "password": "wrong-password"}
    )
    case.step(
        "attempts",
        first_ten=statuses,
        eleventh={"status": eleventh.status_code, "error": eleventh.json().get("error")},
        after_61s={"status": after_wait.status_code, "error": after_wait.json().get("error")},
    )
    case.expect(all(status == 401 for status in statuses), "1〜10 回目に 401 以外がある")
    case.expect(eleventh.status_code == 429, f"11 回目が {eleventh.status_code}")
    case.expect(
        eleventh.json().get("error", {}).get("code") == "rate_limited",
        "code が rate_limited でない",
    )
    case.expect(after_wait.status_code != 429, "61 秒後も 429 のまま")
    reset_login_rate()
    case.finish()


# ---------------------------------------------------------------- 2 logout
def test_tc_mw7phk04_logout_revokes(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7phk04_657736d9", "ログアウト失効")
    editor = demo_users["editor"]
    login_as(client, editor["email"], DEMO_PASSWORD)
    logout = client.post("/api/auth/logout")
    me = client.get("/api/auth/me")
    with SessionLocal() as db:
        revoked = [
            row.isoformat() if row is not None else None
            for row in db.execute(
                select(SessionRow.revoked_at).where(SessionRow.user_id == editor["id"])
            ).scalars()
        ]
    case.step("logout", status=logout.status_code, me=me.status_code, revoked=revoked)
    case.expect(logout.status_code == 200, f"ログアウトが {logout.status_code}")
    case.expect(me.status_code == 401, f"ログアウト後 /me が {me.status_code}")
    case.expect(any(value is not None for value in revoked), "revoked_at が NULL のまま")
    case.finish()


# ---------------------------------------------------------------- 3 project delete RBAC
def test_tc_mw7pi00l_project_delete_permissions(
    client: TestClient, demo_users: dict[str, dict]
) -> None:
    case = Case("tc_mw7pi00l_343c398e", "テーマ削除の権限")
    with new_client() as admin:
        login_as(admin, demo_users["admin"]["email"], DEMO_PASSWORD)
        editor2 = create_user_as_admin(admin, "editor2@rihrp.local")
        login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
        p1 = create_project(client, "editor1 のテーマ")
        p2 = create_project(client, "admin 削除用")

        with new_client() as other_editor:
            login_as(other_editor, editor2["email"], "user-password-123")
            foreign = other_editor.delete(f"/api/projects/{p1['id']}")
        own = client.delete(f"/api/projects/{p1['id']}")
        admin_delete = admin.delete(f"/api/projects/{p2['id']}")

        p3 = create_project(client, "viewer 削除用")
        with new_client() as viewer:
            login_as(viewer, demo_users["viewer"]["email"], DEMO_PASSWORD)
            viewer_delete = viewer.delete(f"/api/projects/{p3['id']}")
        listed = [item["id"] for item in client.get("/api/projects").json()["projects"]]

    case.step(
        "responses",
        foreign=foreign.status_code,
        own=own.status_code,
        admin=admin_delete.status_code,
        viewer=viewer_delete.status_code,
        listed=listed,
    )
    case.expect(foreign.status_code == 403, f"他人のテーマ削除が {foreign.status_code}")
    case.expect(own.status_code == 200, f"所有者削除が {own.status_code}")
    case.expect(admin_delete.status_code == 200, f"admin 削除が {admin_delete.status_code}")
    case.expect(viewer_delete.status_code == 403, f"viewer 削除が {viewer_delete.status_code}")
    case.expect(p1["id"] not in listed, "削除済みテーマが一覧に残る")
    case.expect(p2["id"] not in listed, "admin 削除済みテーマが一覧に残る")
    case.finish()


# ---------------------------------------------------------------- 4 list stats & empty
def test_tc_mw7pi00v_list_stats_and_empty(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7pi00v_350062bb", "要対応件数・空詳細")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    project = create_project(client, "集計テーマ")
    source = create_source(client, project["id"])
    verified = create_claim(client, project["id"], "導入可能量は 1,240 MW と試算された。")
    add_evidence(client, verified["id"], source["id"], "導入可能量は 1,240 MW")
    client.post(f"/api/claims/{verified['id']}/verify")
    insufficient = create_claim(client, project["id"], "根拠のない主張をここに置く。")
    client.post(f"/api/claims/{insufficient['id']}/verify")
    report = create_report(client, project["id"])
    save_report(client, report, [verified["id"], insufficient["id"]], "本文")
    client.post(f"/api/reports/{report['id']}/submit")

    empty = create_project(client, "空テーマ")
    listed = {p["id"]: p for p in client.get("/api/projects").json()["projects"]}
    stats = listed[project["id"]]["stats"]
    expected = {
        "sources": 1,
        "claims": 2,
        "verified": 1,
        "insufficient": 1,
        "unchecked": 0,
        "review_pending": 1,
        "changes_requested": 0,
    }
    empty_sources = client.get(f"/api/projects/{empty['id']}/sources")
    empty_claims = client.get(f"/api/projects/{empty['id']}/claims")
    empty_reports = client.get(f"/api/projects/{empty['id']}/reports")
    missing = client.get("/api/projects/does-not-exist")
    case.step(
        "stats",
        actual=stats,
        expected=expected,
        empty=listed[empty["id"]]["stats"],
        empty_sources=empty_sources.json(),
        empty_claims=empty_claims.json(),
        empty_reports=empty_reports.json(),
        missing={"status": missing.status_code, "error": missing.json().get("error")},
    )
    for key, value in expected.items():
        case.expect(stats[key] == value, f"{key} が {stats[key]}（期待 {value}）")
    case.expect(
        empty_sources.status_code == 200 and empty_sources.json()["sources"] == [],
        "空出典が空配列でない",
    )
    case.expect(
        empty_claims.status_code == 200 and empty_claims.json()["claims"] == [],
        "空主張が空配列でない",
    )
    case.expect(
        empty_reports.status_code == 200 and empty_reports.json()["reports"] == [],
        "空レポートが空配列でない",
    )
    case.expect(missing.status_code == 404, f"存在しない ID が {missing.status_code}")
    case.expect(
        missing.json().get("error", {}).get("code") == "not_found",
        "404 の code が not_found でない",
    )
    case.finish()


# ---------------------------------------------------------------- 5 duplicate source scope
def test_tc_mw7pi01f_duplicate_source_scope(
    client: TestClient, demo_users: dict[str, dict]
) -> None:
    case = Case("tc_mw7pi01f_49094299", "同一内容出典の 409")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    a = create_project(client, "テーマA")
    b = create_project(client, "テーマB")
    body = "同一内容の出典本文"
    first = client.post(
        f"/api/projects/{a['id']}/sources",
        json={"title": "A1", "kind": "text", "origin": "", "content": body},
    )
    duplicate = client.post(
        f"/api/projects/{a['id']}/sources",
        json={"title": "A2", "kind": "text", "origin": "", "content": body},
    )
    other_theme = client.post(
        f"/api/projects/{b['id']}/sources",
        json={"title": "B1", "kind": "text", "origin": "", "content": body},
    )
    changed = client.post(
        f"/api/projects/{a['id']}/sources",
        json={"title": "A3", "kind": "text", "origin": "", "content": body + "!"},
    )
    case.step(
        "responses",
        first=first.status_code,
        duplicate={"status": duplicate.status_code, "error": duplicate.json().get("error")},
        other_theme=other_theme.status_code,
        changed=changed.status_code,
    )
    case.expect(first.status_code == 201, f"初回が {first.status_code}")
    case.expect(duplicate.status_code == 409, f"重複が {duplicate.status_code}")
    case.expect(other_theme.status_code == 201, f"別テーマが {other_theme.status_code}")
    case.expect(changed.status_code == 201, f"1 文字差が {changed.status_code}")
    case.finish()


# ---------------------------------------------------------------- 6 source size boundary
def test_tc_mw7pi01p_source_size_boundary(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7pi01p_d9a187eb", "出典 1 MiB 境界")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    project = create_project(client)
    exactly = "a" * (1024 * 1024)
    over = "b" * (1024 * 1024 + 1)
    ok = client.post(
        f"/api/projects/{project['id']}/sources",
        json={"title": "1MiB", "kind": "text", "origin": "", "content": exactly},
    )
    rejected = client.post(
        f"/api/projects/{project['id']}/sources",
        json={"title": "over", "kind": "text", "origin": "", "content": over},
    )
    sources = client.get(f"/api/projects/{project['id']}/sources").json()["sources"]
    case.step(
        "responses",
        exact={"status": ok.status_code, "bytes": len(exactly.encode())},
        over={"status": rejected.status_code, "error": rejected.json().get("error")},
        count=len(sources),
    )
    case.expect(ok.status_code == 201, f"1 MiB ちょうどが {ok.status_code}")
    case.expect(rejected.status_code == 422, f"1 MiB+1 が {rejected.status_code}")
    case.expect(len(sources) == 1, f"一覧件数が {len(sources)}")
    case.finish()


# ---------------------------------------------------------------- 7 claim boundary
def test_tc_mw7pighq_claim_boundary_and_reset(
    client: TestClient, demo_users: dict[str, dict]
) -> None:
    case = Case("tc_mw7pighq_b3b6bf72", "主張 9/10/2000/2001 文字")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    project = create_project(client)
    nine = client.post(f"/api/projects/{project['id']}/claims", json={"text": "123456789"})
    ten = client.post(f"/api/projects/{project['id']}/claims", json={"text": "1234567890"})
    two_thousand = client.post(f"/api/projects/{project['id']}/claims", json={"text": "あ" * 2000})
    two_thousand_one = client.post(
        f"/api/projects/{project['id']}/claims", json={"text": "あ" * 2001}
    )
    source = create_source(client, project["id"], content="洗掘深さは 50 cm を超える。")
    claim = create_claim(client, project["id"], "洗掘深さは 50 cm を超える。")
    add_evidence(client, claim["id"], source["id"], "洗掘深さは 50 cm")
    verified = client.post(f"/api/claims/{claim['id']}/verify").json()["claim"]
    patched = client.patch(
        f"/api/claims/{claim['id']}", json={"text": "洗掘深さは 60 cm を超える。"}
    )
    case.step(
        "responses",
        nine=nine.status_code,
        ten=ten.status_code,
        two_thousand=two_thousand.status_code,
        two_thousand_one=two_thousand_one.status_code,
        verified={"verdict": verified["last_verdict"], "at": verified["last_verified_at"]},
        patched={
            "status": patched.status_code,
            "last_verdict": patched.json()["claim"]["last_verdict"],
            "last_verified_at": patched.json()["claim"]["last_verified_at"],
        },
    )
    case.expect(nine.status_code == 422, f"9 文字が {nine.status_code}")
    case.expect(ten.status_code == 201, f"10 文字が {ten.status_code}")
    case.expect(two_thousand.status_code == 201, f"2000 文字が {two_thousand.status_code}")
    case.expect(two_thousand_one.status_code == 422, f"2001 文字が {two_thousand_one.status_code}")
    case.expect(verified["last_verdict"] == "verified", "検証済みにならない")
    case.expect(patched.json()["claim"]["last_verdict"] is None, "編集後 last_verdict が残る")
    case.expect(
        patched.json()["claim"]["last_verified_at"] is None, "編集後 last_verified_at が残る"
    )
    case.finish()


# ------------------------------------------------ 8 cross theme / duplicate evidence
def test_tc_mw7pigim_cross_theme_and_duplicate(
    client: TestClient, demo_users: dict[str, dict]
) -> None:
    case = Case("tc_mw7pigim_a37f571e", "別テーマ出典 422・重複根拠 409")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    a = create_project(client, "テーマA")
    b = create_project(client, "テーマB")
    source_b = create_source(client, b["id"], content="テーマBの出典本文")
    source_a = create_source(client, a["id"], content="テーマAの出典本文 50 cm")
    claim = create_claim(client, a["id"], "テーマAの主張として 50 cm を確認する。")
    cross = add_evidence(client, claim["id"], source_b["id"], "")
    first = add_evidence(client, claim["id"], source_a["id"], "50 cm")
    duplicate = add_evidence(client, claim["id"], source_a["id"], "50 cm")
    other_quote = add_evidence(client, claim["id"], source_a["id"], "出典本文")
    case.step(
        "responses",
        cross={"status": cross.status_code, "error": cross.json().get("error")},
        first=first.status_code,
        duplicate={"status": duplicate.status_code, "error": duplicate.json().get("error")},
        other_quote=other_quote.status_code,
    )
    case.expect(cross.status_code == 422, f"別テーマが {cross.status_code}")
    case.expect(first.status_code == 201, f"初回が {first.status_code}")
    case.expect(duplicate.status_code == 409, f"重複が {duplicate.status_code}")
    case.expect(other_quote.status_code == 201, f"引用違いが {other_quote.status_code}")
    case.finish()


# ---------------------------------------------------------------- 9 bulk verify & history
def test_tc_mw7pigjq_bulk_verify_and_history(
    client: TestClient, demo_users: dict[str, dict]
) -> None:
    case = Case("tc_mw7pigjq_8f541311", "一括検証・レポート検証履歴")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    project = create_project(client)
    source = create_source(client, project["id"])
    verified = create_claim(client, project["id"], "導入可能量は 1,240 MW と試算された。")
    add_evidence(client, verified["id"], source["id"], "導入可能量は 1,240 MW")
    insufficient = create_claim(client, project["id"], "根拠のない主張をここに置く。")
    bulk = client.post(f"/api/projects/{project['id']}/claims/verify")
    claims = {
        item["id"]: item
        for item in client.get(f"/api/projects/{project['id']}/claims").json()["claims"]
    }

    report = create_report(client, project["id"])
    save_report(client, report, [verified["id"]], "導入可能量は 1,240 MW と試算された。")
    first_verify = client.post(f"/api/reports/{report['id']}/verify")
    second_verify = client.post(f"/api/reports/{report['id']}/verify")
    with SessionLocal() as db:
        rows = list(
            db.execute(
                select(ReportVerification).where(ReportVerification.report_id == report["id"])
            ).scalars()
        )
    empty_report = create_report(client, project["id"], "空レポート")
    empty_verify = client.post(f"/api/reports/{empty_report['id']}/verify")
    case.step(
        "bulk",
        status=bulk.status_code,
        verified_count=bulk.json().get("verified"),
        results=bulk.json().get("results"),
        last_verdicts={cid: item["last_verdict"] for cid, item in claims.items()},
        first_summary=first_verify.json().get("summary"),
        second_summary=second_verify.json().get("summary"),
        history_rows=len(rows),
        empty_summary=empty_verify.json().get("summary"),
    )
    case.expect(bulk.status_code == 200, f"一括検証が {bulk.status_code}")
    case.expect(bulk.json()["verified"] == 2, "一括検証の件数が 2 でない")
    case.expect(claims[verified["id"]]["last_verdict"] == "verified", "検証済みが一致しない")
    case.expect(
        claims[insufficient["id"]]["last_verdict"] == "insufficient", "根拠不足が一致しない"
    )
    case.expect(first_verify.status_code == 200, "レポート検証が失敗")
    case.expect(len(rows) == 2, f"検証履歴が {len(rows)} 件")
    case.expect(empty_verify.status_code == 200, "空レポート検証が失敗")
    case.expect(empty_verify.json()["summary"]["total_claims"] == 0, "空レポートの集計が 0 でない")
    case.finish()


# ---------------------------------------------------------------- 10 versions & seal
def test_tc_mw7pigk2_versions_and_seal(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7pigk2_f8a679a9", "版と seal_sha256")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    project = create_project(client)
    source = create_source(client, project["id"])
    claim = create_claim(client, project["id"], "導入可能量は 1,240 MW と試算された。")
    add_evidence(client, claim["id"], source["id"], "導入可能量は 1,240 MW")
    client.post(f"/api/claims/{claim['id']}/verify")
    report = create_report(client, project["id"])
    v2 = save_report(client, report, [claim["id"]], "本文A")
    v3 = save_report(client, v2, [claim["id"]], "本文A")
    v4 = save_report(client, v3, [claim["id"]], "本文B")
    versions = client.get(f"/api/reports/{report['id']}/versions").json()
    by_version = {item["version"]: item for item in versions["versions"]}
    case.step(
        "versions",
        current=versions["current"],
        items=versions["versions"],
    )
    case.expect(v2["version"] == 2, "2 回目保存で version 2 にならない")
    case.expect(v3["version"] == 3, "同一内容保存で version 3 にならない")
    case.expect(v4["version"] == 4, "変更保存で version 4 にならない")
    case.expect(versions["current"] == 4, "current が 4 でない")
    case.expect(len(versions["versions"]) == 4, "版数が 4 でない")
    case.expect(len(by_version[1]["seal_sha256"]) == 64, "seal が 64 桁でない")
    case.expect(
        by_version[2]["seal_sha256"] == by_version[3]["seal_sha256"],
        "同一内容の版 2・3 の seal が一致しない",
    )
    case.expect(
        by_version[2]["seal_sha256"] != by_version[4]["seal_sha256"],
        "変更後の seal が変わらない",
    )
    case.expect(all(item.get("created_at") for item in versions["versions"]), "作成日時がない")
    case.finish()


# ---------------------------------------------------------------- 11 submit states
def test_tc_mw7pigke_submit_states(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7pigke_ccb82988", "提出・二重提出 409")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    project = create_project(client)
    report = create_report(client, project["id"])
    save_report(client, report, [], "本文")
    first = client.post(f"/api/reports/{report['id']}/submit")
    double = client.post(f"/api/reports/{report['id']}/submit")
    second_draft = create_report(client, project["id"], "別レポート")
    save_report(client, second_draft, [], "本文2")

    with new_client() as reviewer:
        login_as(reviewer, demo_users["reviewer"]["email"], DEMO_PASSWORD)
        reviewer_submit = reviewer.post(f"/api/reports/{second_draft['id']}/submit")
    with new_client() as viewer:
        login_as(viewer, demo_users["viewer"]["email"], DEMO_PASSWORD)
        viewer_submit = viewer.post(f"/api/reports/{second_draft['id']}/submit")

    case.step(
        "responses",
        first=first.status_code,
        first_state=first.json()["report"]["status"],
        double={"status": double.status_code, "error": double.json().get("error")},
        reviewer=reviewer_submit.status_code,
        viewer=viewer_submit.status_code,
    )
    case.expect(first.status_code == 200, f"提出が {first.status_code}")
    case.expect(first.json()["report"]["status"] == "in_review", "in_review でない")
    case.expect(double.status_code == 409, f"二重提出が {double.status_code}")
    case.expect(
        reviewer_submit.status_code == 403, f"reviewer 提出が {reviewer_submit.status_code}"
    )
    case.expect(viewer_submit.status_code == 403, f"viewer 提出が {viewer_submit.status_code}")
    case.finish()


# ---------------------------------------------------------------- 12 changes comment boundary
def test_tc_mw7piymn_changes_comment_boundary(
    client: TestClient, demo_users: dict[str, dict]
) -> None:
    case = Case("tc_mw7piymn_36df17df", "差し戻しコメント 9/10 文字")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    project = create_project(client)
    report = create_report(client, project["id"])
    save_report(client, report, [], "本文")
    client.post(f"/api/reports/{report['id']}/submit")

    with new_client() as reviewer:
        login_as(reviewer, demo_users["reviewer"]["email"], DEMO_PASSWORD)
        too_short = reviewer.post(
            f"/api/reports/{report['id']}/review",
            json={"decision": "changes_requested", "comment": "123456789"},
        )
        ok = reviewer.post(
            f"/api/reports/{report['id']}/review",
            json={"decision": "changes_requested", "comment": "1234567890"},
        )
        fetched = reviewer.get(f"/api/reports/{report['id']}")
    resubmit = client.post(f"/api/reports/{report['id']}/submit")
    case.step(
        "responses",
        too_short={"status": too_short.status_code, "error": too_short.json().get("error")},
        ok=ok.status_code,
        state=fetched.json()["report"]["status"],
        comments=[item["comment"] for item in fetched.json()["report"]["reviews"]],
        resubmit={
            "status": resubmit.status_code,
            "state": resubmit.json().get("report", {}).get("status"),
        },
    )
    case.expect(too_short.status_code == 422, f"9 文字が {too_short.status_code}")
    case.expect(ok.status_code == 200, f"10 文字が {ok.status_code}")
    case.expect(
        fetched.json()["report"]["status"] == "changes_requested", "changes_requested でない"
    )
    case.expect(
        "1234567890" in [item["comment"] for item in fetched.json()["report"]["reviews"]],
        "コメントが保存されない",
    )
    case.expect(resubmit.status_code == 200, f"再提出が {resubmit.status_code}")
    case.expect(resubmit.json()["report"]["status"] == "in_review", "再提出で in_review でない")
    case.finish()


# ---------------------------------------------------------------- 13 stale version
def test_tc_mw7piyna_stale_version(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7piyna_f032662a", "同時編集 409")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    project = create_project(client)
    report = create_report(client, project["id"])
    saved = save_report(client, report, [], "クライアントA")
    stale = client.put(
        f"/api/reports/{report['id']}",
        json={
            "content": {"sections": [{"heading": "B", "paragraphs": [{"text": "クライアントB"}]}]},
            "expected_version": 1,
        },
    )
    fetched = client.get(f"/api/reports/{report['id']}")
    retried = client.put(
        f"/api/reports/{report['id']}",
        json={
            "content": {"sections": [{"heading": "B", "paragraphs": [{"text": "クライアントB"}]}]},
            "expected_version": 2,
        },
    )
    case.step(
        "responses",
        saved={"status": saved["version"]},
        stale={"status": stale.status_code, "error": stale.json().get("error")},
        content=fetched.json()["report"]["content"],
        retried={"status": retried.status_code, "version": retried.json()["report"]["version"]},
    )
    case.expect(saved["version"] == 2, "A の保存で version 2 にならない")
    case.expect(stale.status_code == 409, f"古い版が {stale.status_code}")
    case.expect(
        stale.json().get("error", {}).get("code") == "version_conflict",
        "code が version_conflict でない",
    )
    text_values = [
        p["text"] for s in fetched.json()["report"]["content"]["sections"] for p in s["paragraphs"]
    ]
    case.expect("クライアントB" not in text_values, "B の内容が反映されている")
    case.expect(retried.status_code == 200, f"版 2 の再保存が {retried.status_code}")
    case.finish()


# ---------------------------------------------------------------- 14 export markers
def test_tc_mw7piynl_export_markers(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7piynl_89a4886b", "エクスポート（マーカー・付録）")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    project = create_project(client)
    source = create_source(client, project["id"])
    verified = create_claim(client, project["id"], "導入可能量は 1,240 MW と試算された。")
    add_evidence(client, verified["id"], source["id"], "導入可能量は 1,240 MW")
    client.post(f"/api/claims/{verified['id']}/verify")
    unverified = create_claim(client, project["id"], "導入可能量は 9,999 MW と試算された。")
    add_evidence(client, unverified["id"], source["id"], "導入可能量は 1,240 MW")
    client.post(f"/api/claims/{unverified['id']}/verify")
    insufficient = create_claim(client, project["id"], "根拠のない主張をここに置く。")
    client.post(f"/api/claims/{insufficient['id']}/verify")
    unreferenced = create_claim(client, project["id"], "未参照の主張本文はここにある。")

    report = create_report(client, project["id"])
    save_report(
        client,
        report,
        [verified["id"], unverified["id"], insufficient["id"]],
        "本文",
    )
    exported = client.get(f"/api/reports/{report['id']}/export")
    body = exported.text
    case.step(
        "export",
        status=exported.status_code,
        has_verified="[検証済]" in body,
        has_unverified="[未検証]" in body,
        has_insufficient="[根拠不足]" in body,
        has_appendix="根拠付録" in body,
        has_quote="導入可能量は 1,240 MW" in body,
        has_sha=source["content_sha256"] in body,
        has_unreferenced=unreferenced["text"] in body,
    )
    case.expect(exported.status_code == 200, f"エクスポートが {exported.status_code}")
    case.expect("[検証済]" in body, "検証済マーカーがない")
    case.expect("[未検証]" in body, "未検証マーカーがない")
    case.expect("[根拠不足]" in body, "根拠不足マーカーがない")
    case.expect("根拠付録" in body, "根拠付録がない")
    case.expect("導入可能量は 1,240 MW" in body, "引用が付録にない")
    case.expect(source["content_sha256"] in body, "SHA が付録にない")
    case.expect(unreferenced["text"] not in body, "未参照主張が含まれる")
    case.finish()


# ---------------------------------------------------------------- 15 audit correlation
def test_tc_mw7piyoc_audit_correlation(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7piyoc_3268ea0c", "監査記録＋相関 ID")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    project = create_project(client)
    source = create_source(client, project["id"])
    claim = create_claim(client, project["id"], "導入可能量は 1,240 MW と試算された。")
    add_evidence(client, claim["id"], source["id"], "導入可能量は 1,240 MW")
    client.post(f"/api/claims/{claim['id']}/verify")
    report = create_report(client, project["id"])
    save_report(client, report, [claim["id"]], "本文")
    submitted = client.post(f"/api/reports/{report['id']}/submit")
    request_id = submitted.headers.get("X-Request-Id", "")

    with new_client() as reviewer:
        login_as(reviewer, demo_users["reviewer"]["email"], DEMO_PASSWORD)
        reviewer.post(
            f"/api/reports/{report['id']}/review",
            json={"decision": "approved", "comment": "確認しました。"},
        )
    with SessionLocal() as db:
        events = list(
            db.execute(
                select(AuditEvent)
                .where(AuditEvent.project_id == project["id"])
                .order_by(AuditEvent.created_at)
            ).scalars()
        )
        same_request = [event for event in events if event.request_id == request_id]
    actions = {event.action for event in events}
    case.step(
        "audit",
        request_id=request_id,
        actions=sorted(actions),
        same_request=[event.action for event in same_request],
        actors=sorted({event.actor_id for event in events}),
    )
    case.expect(bool(request_id), "X-Request-Id がない")
    for action in (
        "project.created",
        "source.created",
        "claim.created",
        "evidence.created",
        "report.created",
        "report.submitted",
        "report.reviewed",
    ):
        case.expect(action in actions, f"監査に {action} がない")
    case.expect(all(event.actor_id for event in events), "actor_id がない監査行がある")
    case.expect(bool(same_request), "同じ相関 ID の監査行が特定できない")
    case.skip("監査書込失敗時の fail closed は実装を壊さずに注入できないため未実施")
    case.finish()


# ---------------------------------------------------------------- 16 user management
def test_tc_mw7pjgwf_user_management(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7pjgwf_c57f9084", "利用者管理・自己降格拒否")
    with new_client() as admin:
        login_as(admin, demo_users["admin"]["email"], DEMO_PASSWORD)
        listed = admin.get("/api/users")
        created = create_user_as_admin(admin, "managed@rihrp.local", "viewer")
        changed = admin.patch(f"/api/users/{created['id']}", json={"role": "editor"})
        self_demote = admin.patch(
            f"/api/users/{demo_users['admin']['id']}", json={"role": "viewer"}
        )
        with new_client() as editor:
            login_as(editor, demo_users["editor"]["email"], DEMO_PASSWORD)
            deactivated = admin.patch(
                f"/api/users/{demo_users['editor']['id']}", json={"is_active": False}
            )
            editor_me = editor.get("/api/auth/me")
    with new_client() as reviewer:
        login_as(reviewer, demo_users["reviewer"]["email"], DEMO_PASSWORD)
        reviewer_users = reviewer.get("/api/users")
    case.step(
        "responses",
        listed=listed.status_code,
        created=created.get("email"),
        changed=changed.json().get("user", {}).get("role"),
        self_demote={"status": self_demote.status_code, "error": self_demote.json().get("error")},
        deactivated=deactivated.status_code,
        editor_me=editor_me.status_code,
        reviewer_users=reviewer_users.status_code,
    )
    case.expect(listed.status_code == 200, f"一覧が {listed.status_code}")
    case.expect(created["email"] == "managed@rihrp.local", "作成が反映されない")
    case.expect(changed.json()["user"]["role"] == "editor", "ロール変更が反映されない")
    case.expect(self_demote.status_code in (400, 422), f"自己降格が {self_demote.status_code}")
    case.expect(deactivated.status_code == 200, f"無効化が {deactivated.status_code}")
    case.expect(editor_me.status_code == 401, f"無効化後 /me が {editor_me.status_code}")
    case.expect(reviewer_users.status_code == 403, f"reviewer 一覧が {reviewer_users.status_code}")
    case.finish()


# ---------------------------------------------------------------- 17 audit purge
def test_tc_mw7pjgx0_audit_purge(
    client: TestClient, demo_users: dict[str, dict], monkeypatch
) -> None:
    case = Case("tc_mw7pjgx0_8e0977cc", "監査保持 365 日削除（隔離 DB）")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    client.post("/api/projects", json={"title": "purge 用"})
    with engine.begin() as connection:
        old_id = str(uuid.uuid4())
        connection.execute(
            text(
                "INSERT INTO audit_events "
                "(id, actor_id, action, entity_type, entity_id, project_id, details, "
                "request_id, created_at) "
                "VALUES (:id, NULL, 'legacy.event', 'test', '', NULL, '{}'::jsonb, '', "
                "now() - interval '400 days')"
            ),
            {"id": old_id},
        )
    dry = purge_audit(365, commit=False)
    monkeypatch.delenv("RIHRP_ALLOW_AUDIT_PURGE", raising=False)
    try:
        purge_audit(365, commit=True)
    except RuntimeError as exc:
        refused = str(exc)
    else:
        refused = ""
    monkeypatch.setenv("RIHRP_ALLOW_AUDIT_PURGE", "1")
    committed = purge_audit(365, commit=True)
    with SessionLocal() as db:
        remaining_old = db.execute(
            select(AuditEvent).where(AuditEvent.id == old_id)
        ).scalar_one_or_none()
        total = db.execute(select(AuditEvent)).scalars().all()
        triggers = list(
            db.execute(
                text(
                    "SELECT tgname, tgenabled FROM pg_trigger "
                    "WHERE tgrelid = 'audit_events'::regclass AND NOT tgisinternal"
                )
            )
        )
    case.step(
        "purge",
        dry=dry,
        refused=refused,
        committed=committed,
        old_removed=remaining_old is None,
        remaining=len(total),
        triggers=[(row[0], row[1]) for row in triggers],
    )
    case.expect(dry["deleted"] == 0, "dry-run で削除された")
    case.expect(dry["eligible"] >= 1, "dry-run の対象件数が 0")
    case.expect(bool(refused), "承認なし commit が拒否されない")
    case.expect(committed["deleted"] >= 1, "承認あり commit で削除されない")
    case.expect(remaining_old is None, "365 日超の行が残っている")
    case.expect(bool(total), "365 日以内の行まで消えている")
    case.expect(
        all(enabled == "O" for _name, enabled in triggers), "トリガーが再有効化されていない"
    )
    case.finish()


# ---------------------------------------------------------------- 18 migration pending
def test_tc_mw7pjyck_migration_pending(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7pjyck_a24fdb08", "migration 未適用で readyz 503")
    with engine.begin() as connection:
        head = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM alembic_version"))
    pending = client.get("/readyz")
    health = client.get("/healthz")
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:head)"), {"head": head}
        )
    ready = client.get("/readyz")
    case.step(
        "readyz",
        health=health.status_code,
        pending={"status": pending.status_code, "body": pending.json()},
        ready={"status": ready.status_code, "body": ready.json()},
    )
    case.expect(health.status_code == 200, f"healthz が {health.status_code}")
    case.expect(pending.status_code == 503, f"未適用 readyz が {pending.status_code}")
    case.expect(
        pending.json().get("reason") == "migration_pending", "reason が migration_pending でない"
    )
    case.expect(ready.status_code == 200, f"適用後 readyz が {ready.status_code}")
    case.finish()


# ---------------------------------------------------------------- 19 unified errors
def test_tc_mw7pjydf_unified_errors(
    client: TestClient, demo_users: dict[str, dict], monkeypatch
) -> None:
    case = Case("tc_mw7pjydf_dbe2efe9", "エラー統一形式")
    client.headers.pop("X-CSRF-Token", None)
    unauthorized = client.get("/api/projects")
    with new_client() as viewer:
        login_as(viewer, demo_users["viewer"]["email"], DEMO_PASSWORD)
        forbidden = viewer.post("/api/projects", json={"title": "x"})
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    not_found = client.get("/api/projects/does-not-exist")
    validation = client.post("/api/projects", json={"title": ""})
    project = create_project(client)
    create_source(client, project["id"], content="重複本文")
    conflict = client.post(
        f"/api/projects/{project['id']}/sources",
        json={"title": "dup", "kind": "text", "origin": "", "content": "重複本文"},
    )
    monkeypatch.setattr(get_settings(), "login_rate_limit", 1)
    reset_login_rate()
    with new_client() as limited:
        limited.post("/api/auth/login", json={"email": "none@rihrp.local", "password": "x"})
        rate_limited = limited.post(
            "/api/auth/login", json={"email": "none@rihrp.local", "password": "x"}
        )
    reset_login_rate()
    responses = {
        "unauthorized": unauthorized,
        "forbidden": forbidden,
        "not_found": not_found,
        "validation": validation,
        "conflict": conflict,
        "rate_limited": rate_limited,
    }
    observed = {}
    for name, response in responses.items():
        body = response.json()
        observed[name] = {
            "status": response.status_code,
            "has_error": isinstance(body.get("error"), dict),
            "code": body.get("error", {}).get("code"),
            "message": bool(body.get("error", {}).get("message")),
        }
    case.step("errors", **observed)
    expected_codes = {
        "unauthorized": (401, "unauthorized"),
        "forbidden": (403, "forbidden"),
        "not_found": (404, "not_found"),
        "validation": (422, "validation_error"),
        "conflict": (409, "conflict"),
        "rate_limited": (429, "rate_limited"),
    }
    for name, (status, code) in expected_codes.items():
        case.expect(
            observed[name]["status"] == status, f"{name} の status が {observed[name]['status']}"
        )
        case.expect(observed[name]["has_error"], f"{name} が統一形式でない")
        case.expect(observed[name]["code"] == code, f"{name} の code が {observed[name]['code']}")
        case.expect(observed[name]["message"], f"{name} に message がない")
    case.finish()


# ---------------------------------------------------------------- 20 no secrets in logs
def test_tc_mw7pmf6f_no_secrets_in_logs(
    client: TestClient, demo_users: dict[str, dict], caplog
) -> None:
    case = Case("tc_mw7pmf6f_3a8f761c", "ログに秘密を出さない")
    secret = "super-secret-password-123"
    client.headers.pop("X-CSRF-Token", None)
    caplog.set_level("DEBUG")
    client.post(
        "/api/auth/login", json={"email": demo_users["editor"]["email"], "password": secret}
    )
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    client.post(
        "/api/auth/change-password",
        json={"current_password": DEMO_PASSWORD, "new_password": "brand-new-password-123"},
    )
    client.post("/api/projects", json={"title": ""})
    client.get("/api/projects/does-not-exist")
    logs = caplog.text
    with SessionLocal() as db:
        details = [str(detail) for detail in db.execute(select(AuditEvent.details)).scalars()]
    case.step(
        "scan",
        log_has_secret=secret in logs,
        log_has_password_field="password" in logs.lower(),
        audit_has_secret=any(secret in detail for detail in details),
        audit_has_new_password=any("brand-new-password-123" in detail for detail in details),
        log_sample=logs[-500:],
    )
    case.expect(secret not in logs, "ログに誤入力パスワードが平文で出ている")
    case.expect("brand-new-password-123" not in logs, "新パスワードがログに出ている")
    case.expect(
        not any(secret in detail for detail in details), "監査 details にパスワードが出ている"
    )
    case.finish()


# ---------------------------------------------------------------- 21 unique conflict concurrency
def test_tc_mw7pmf7e_unique_conflict_concurrency(
    client: TestClient, demo_users: dict[str, dict]
) -> None:
    case = Case("tc_mw7pmf7e_00bf9f5c", "一意制約競合の 409")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    project = create_project(client)
    source = create_source(client, project["id"], content="並行テストの出典本文")
    claim = create_claim(client, project["id"], "並行テストの主張をここに置く。")

    def post_source():
        with new_client() as worker:
            login_as(worker, demo_users["editor"]["email"], DEMO_PASSWORD)
            return worker.post(
                f"/api/projects/{project['id']}/sources",
                json={"title": "same", "kind": "text", "origin": "", "content": "同一本文"},
            ).status_code

    def post_evidence():
        with new_client() as worker:
            login_as(worker, demo_users["editor"]["email"], DEMO_PASSWORD)
            return worker.post(
                f"/api/claims/{claim['id']}/evidence",
                json={"source_id": source["id"], "quote": "", "note": ""},
            ).status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        source_statuses = list(pool.map(lambda _: post_source(), range(2)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        evidence_statuses = list(pool.map(lambda _: post_evidence(), range(2)))

    admin = new_client()
    try:
        login_as(admin, demo_users["admin"]["email"], DEMO_PASSWORD)
        email = f"race-{uuid.uuid4().hex[:8]}@rihrp.local"

        def post_user(_):
            with new_client() as worker:
                login_as(worker, demo_users["admin"]["email"], DEMO_PASSWORD)
                return worker.post(
                    "/api/users",
                    json={
                        "email": email,
                        "name": "race",
                        "role": "viewer",
                        "password": "user-password-123",
                    },
                ).status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            user_statuses = list(pool.map(post_user, range(2)))
    finally:
        admin.close()

    case.step(
        "concurrency",
        source=sorted(source_statuses),
        evidence=sorted(evidence_statuses),
        user=sorted(user_statuses),
    )
    for name, statuses in (
        ("出典", source_statuses),
        ("根拠", evidence_statuses),
        ("利用者", user_statuses),
    ):
        case.expect(sorted(statuses) == [201, 409], f"{name} が 201/409 にならない: {statuses}")
        case.expect(500 not in statuses, f"{name} で 500 が発生")
    case.finish()


# ---------------------------------------------------------------- 22 concurrent approval
def test_tc_mw7pk9g4_concurrent_approval(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7pk9g4_7f7079e2", "同時承認の直列化")
    with new_client() as admin:
        login_as(admin, demo_users["admin"]["email"], DEMO_PASSWORD)
        reviewer2 = create_user_as_admin(admin, "reviewer2@rihrp.local", "reviewer")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    project = create_project(client)
    source = create_source(client, project["id"])
    claim = create_claim(client, project["id"], "導入可能量は 1,240 MW と試算された。")
    add_evidence(client, claim["id"], source["id"], "導入可能量は 1,240 MW")
    client.post(f"/api/claims/{claim['id']}/verify")
    report = create_report(client, project["id"])
    save_report(client, report, [claim["id"]], "本文")
    client.post(f"/api/reports/{report['id']}/submit")

    def approve(email, password):
        with new_client() as worker:
            login_as(worker, email, password)
            response = worker.post(
                f"/api/reports/{report['id']}/review",
                json={"decision": "approved", "comment": "同時承認テストです。"},
            )
            return response.status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(approve, demo_users["reviewer"]["email"], DEMO_PASSWORD)
        second = pool.submit(approve, reviewer2["email"], "user-password-123")
        statuses = [first.result(), second.result()]
    state = client.get(f"/api/reports/{report['id']}").json()["report"]["status"]
    with SessionLocal() as db:
        reviews = list(db.execute(select(Review).where(Review.report_id == report["id"])).scalars())
    case.step("approval", statuses=sorted(statuses), state=state, review_rows=len(reviews))
    case.expect(sorted(statuses) == [200, 409], f"200/409 にならない: {statuses}")
    case.expect(state == "approved", f"status が {state}")
    case.expect(len(reviews) == 1, f"review 行が {len(reviews)} 件")
    case.finish()


# ---------------------------------------------------------------- 23 disabled login
def test_tc_mw7pqh8d_disabled_user_login(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7pqh8d_70033c15", "無効化ユーザーのログイン拒否")
    with new_client() as admin:
        login_as(admin, demo_users["admin"]["email"], DEMO_PASSWORD)
        admin.patch(f"/api/users/{demo_users['editor']['id']}", json={"is_active": False})
    client.headers.pop("X-CSRF-Token", None)
    disabled = client.post(
        "/api/auth/login",
        json={"email": demo_users["editor"]["email"], "password": DEMO_PASSWORD},
    )
    wrong = client.post(
        "/api/auth/login",
        json={"email": demo_users["editor"]["email"], "password": "wrong-password-1"},
    )
    with new_client() as admin:
        login_as(admin, demo_users["admin"]["email"], DEMO_PASSWORD)
        admin.patch(f"/api/users/{demo_users['editor']['id']}", json={"is_active": True})
    restored = client.post(
        "/api/auth/login",
        json={"email": demo_users["editor"]["email"], "password": DEMO_PASSWORD},
    )
    case.step(
        "responses",
        disabled={
            "status": disabled.status_code,
            "error": disabled.json().get("error"),
            "cookie": "rihrp_session" in disabled.cookies,
        },
        wrong={"status": wrong.status_code, "error": wrong.json().get("error")},
        restored={"status": restored.status_code},
    )
    case.expect(disabled.status_code == 401, f"無効化ユーザーが {disabled.status_code}")
    case.expect("rihrp_session" not in disabled.cookies, "無効化ユーザーに Cookie が出ている")
    case.expect(
        disabled.json()["error"]["code"] == wrong.json()["error"]["code"]
        and disabled.json()["error"]["message"] == wrong.json()["error"]["message"],
        "誤パスワード時と code/message が一致しない",
    )
    case.expect(restored.status_code == 200, f"有効化後が {restored.status_code}")
    case.finish()


# ---------------------------------------------------------------- 24 numeric notation
def test_tc_mw7pqh7r_numeric_notation(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7pqh7r_23eb2848", "数値表記差（修正版）")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    project = create_project(client)
    source = create_source(
        client, project["id"], content="基準は 50 cm、50%、1,000 件、3.5 m である。"
    )
    cases = {
        "50cm": ("しきい値は 50 cm を超える。", "verified"),
        "50pct": ("しきい値は 50% を超える。", "verified"),
        "comma": ("しきい値は 1,000 件を超える。", "verified"),
        "nocomma": ("しきい値は 1000 件を超える。", "unverified"),
        "decimal": ("しきい値は 3.5 m を超える。", "verified"),
        "trailing": ("しきい値は 3.50 m を超える。", "unverified"),
    }
    results = {}
    for name, (body, _expected) in cases.items():
        claim = create_claim(client, project["id"], body)
        add_evidence(client, claim["id"], source["id"], "")
        verified = client.post(f"/api/claims/{claim['id']}/verify")
        results[name] = verified.json()["result"]["verdict"]
    case.step("verdicts", **results)
    for name, (_body, expected) in cases.items():
        case.expect(results[name] == expected, f"{name} が {results[name]}（期待 {expected}）")
    case.expect(
        all(value != "contradicted" for value in results.values()), "contradicted が出ている"
    )
    case.finish()


# ---------------------------------------------------------------- 25 CSRF PATCH/DELETE
def test_tc_mw7ppy02_csrf_patch_delete(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7ppy02_ffa1cb2b", "CSRF（PATCH/DELETE）")
    editor = demo_users["editor"]
    body = login_as(client, editor["email"], DEMO_PASSWORD, set_csrf=False)
    csrf = body["csrf_token"]
    client.headers["X-CSRF-Token"] = csrf
    project = create_project(client)
    client.headers.pop("X-CSRF-Token", None)
    missing_patch = client.patch(f"/api/projects/{project['id']}", json={"title": "x"})
    mismatched_patch = client.patch(
        f"/api/projects/{project['id']}", json={"title": "x"}, headers={"X-CSRF-Token": "wrong"}
    )
    correct_patch = client.patch(
        f"/api/projects/{project['id']}", json={"title": "更新"}, headers={"X-CSRF-Token": csrf}
    )
    missing_delete = client.delete(f"/api/projects/{project['id']}")
    correct_delete = client.delete(f"/api/projects/{project['id']}", headers={"X-CSRF-Token": csrf})
    case.step(
        "responses",
        missing_patch=missing_patch.status_code,
        mismatched_patch=mismatched_patch.status_code,
        correct_patch=correct_patch.status_code,
        missing_delete=missing_delete.status_code,
        correct_delete=correct_delete.status_code,
    )
    case.expect(missing_patch.status_code == 403, f"PATCH 欠落が {missing_patch.status_code}")
    case.expect(
        mismatched_patch.status_code == 403, f"PATCH 不一致が {mismatched_patch.status_code}"
    )
    case.expect(correct_patch.status_code == 200, f"PATCH 一致が {correct_patch.status_code}")
    case.expect(missing_delete.status_code == 403, f"DELETE 欠落が {missing_delete.status_code}")
    case.expect(correct_delete.status_code == 200, f"DELETE 一致が {correct_delete.status_code}")
    case.finish()


# ---------------------------------------------------------------- 26 password change relogin
def test_tc_mw7ppy0j_password_change_relogin(
    client: TestClient, demo_users: dict[str, dict]
) -> None:
    case = Case("tc_mw7ppy0j_edbba5f9", "パスワード変更後の再ログイン")
    editor = demo_users["editor"]
    login_as(client, editor["email"], DEMO_PASSWORD)
    changed = client.post(
        "/api/auth/change-password",
        json={"current_password": DEMO_PASSWORD, "new_password": "new-password-123"},
    )
    client.post("/api/auth/logout")
    client.headers.pop("X-CSRF-Token", None)
    old = client.post("/api/auth/login", json={"email": editor["email"], "password": DEMO_PASSWORD})
    new = client.post(
        "/api/auth/login", json={"email": editor["email"], "password": "new-password-123"}
    )
    case.step(
        "responses",
        changed=changed.status_code,
        old={"status": old.status_code, "error": old.json().get("error")},
        new={"status": new.status_code, "cookie": "rihrp_session" in new.cookies},
    )
    case.expect(changed.status_code == 200, f"変更が {changed.status_code}")
    case.expect(old.status_code == 401, f"旧パスワードが {old.status_code}")
    case.expect(new.status_code == 200, f"新パスワードが {new.status_code}")
    case.expect("rihrp_session" in new.cookies, "新パスワードで Cookie が出ない")
    case.finish()


# ---------------------------------------------------------------- 27 expired session
def test_tc_mw7ppxzk_expired_session(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7ppxzk_211c31f2", "期限切れセッション 401")
    editor = demo_users["editor"]
    login_as(client, editor["email"], DEMO_PASSWORD)
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE sessions SET expires_at = now() - interval '1 hour' "
                "WHERE user_id = :user_id AND revoked_at IS NULL"
            ),
            {"user_id": editor["id"]},
        )
    me = client.get("/api/auth/me")
    write = client.post("/api/projects", json={"title": "期限切れ"})
    client.headers.pop("X-CSRF-Token", None)
    relogin = client.post(
        "/api/auth/login", json={"email": editor["email"], "password": DEMO_PASSWORD}
    )
    case.step(
        "responses",
        me={"status": me.status_code, "error": me.json().get("error")},
        write=write.status_code,
        relogin={"status": relogin.status_code},
    )
    case.expect(me.status_code == 401, f"期限切れ /me が {me.status_code}")
    case.expect(
        me.json().get("error", {}).get("code") == "unauthorized", "code が unauthorized でない"
    )
    case.expect(write.status_code == 401, f"期限切れ書込が {write.status_code}")
    case.expect(relogin.status_code == 200, f"再ログインが {relogin.status_code}")
    case.finish()


# ---------------------------------------------------------------- 28 residual approval
def test_tc_mw7ppxz3_residual_approval(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7ppxz3_aef4a18a", "未検証を含む承認可・残数")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    project = create_project(client)
    source = create_source(client, project["id"])
    unverified = create_claim(client, project["id"], "導入可能量は 9,999 MW と試算された。")
    add_evidence(client, unverified["id"], source["id"], "導入可能量は 1,240 MW")
    client.post(f"/api/claims/{unverified['id']}/verify")
    insufficient = create_claim(client, project["id"], "根拠のない主張をここに置く。")
    client.post(f"/api/claims/{insufficient['id']}/verify")
    report = create_report(client, project["id"])
    save_report(client, report, [unverified["id"], insufficient["id"]], "本文")
    client.post(f"/api/reports/{report['id']}/submit")

    with new_client() as reviewer:
        login_as(reviewer, demo_users["reviewer"]["email"], DEMO_PASSWORD)
        approved = reviewer.post(
            f"/api/reports/{report['id']}/review",
            json={"decision": "approved", "comment": "残数を含めて承認します。"},
        )
        fetched = reviewer.get(f"/api/reports/{report['id']}")
        exported = reviewer.get(f"/api/reports/{report['id']}/export")
    summary = fetched.json()["report"]["latest_verification"]["summary"]
    case.step(
        "approval",
        status=approved.status_code,
        state=fetched.json()["report"]["status"],
        summary=summary,
        export_unverified="[未検証]" in exported.text,
        export_insufficient="[根拠不足]" in exported.text,
    )
    case.expect(approved.status_code == 200, f"承認が {approved.status_code}")
    case.expect(fetched.json()["report"]["status"] == "approved", "approved でない")
    case.expect(summary["unverified"] == 1, "unverified 残数が 1 でない")
    case.expect(summary["insufficient"] == 1, "insufficient 残数が 1 でない")
    case.expect("[未検証]" in exported.text, "エクスポートに未検証マーカーがない")
    case.expect("[根拠不足]" in exported.text, "エクスポートに根拠不足マーカーがない")
    case.skip("UI の承認画面の残数表示は UI 実行で別途確認")
    case.finish()
