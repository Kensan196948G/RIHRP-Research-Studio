"""品質ゲート P0（20 件）の実測実行。

各テストは QA ワークベンチの testcase id に対応する。隔離 DB `rihrp_test*` のみを
使い、ケースに書かれた手順と期待結果をそのまま確認する。
"""

from __future__ import annotations

import hashlib
import time
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from rihrp.config import get_settings
from rihrp.db import SessionLocal, engine
from rihrp.models import AuditEvent, ReportVerification
from tests.gate.conftest import DEMO_PASSWORD, login_as, new_client
from tests.gate.harness import Case

SOURCE_TEXT = "海岸護岸の洗掘深さは 50 cm を超える。導入可能量は 1,240 MW と試算された。"


# ---------------------------------------------------------------- helpers
def create_project(client: TestClient, title: str = "検証テーマ") -> dict:
    response = client.post("/api/projects", json={"title": title, "summary": "テスト"})
    assert response.status_code == 201, response.text
    return response.json()["project"]


def create_source(
    client: TestClient,
    project_id: str,
    *,
    title: str = "出典A",
    kind: str = "url",
    origin: str = "https://example.test/a",
    content: str = SOURCE_TEXT,
) -> dict:
    response = client.post(
        f"/api/projects/{project_id}/sources",
        json={"title": title, "kind": kind, "origin": origin, "content": content},
    )
    assert response.status_code == 201, response.text
    return response.json()["source"]


def create_claim(client: TestClient, project_id: str, claim_text: str) -> dict:
    response = client.post(f"/api/projects/{project_id}/claims", json={"text": claim_text})
    assert response.status_code == 201, response.text
    return response.json()["claim"]


def add_evidence(client: TestClient, claim_id: str, source_id: str, quote: str):
    return client.post(
        f"/api/claims/{claim_id}/evidence",
        json={"source_id": source_id, "quote": quote, "note": ""},
    )


def build_verified_claim(
    client: TestClient, project_id: str, claim_text: str, quote: str
) -> tuple[dict, dict, dict]:
    source = create_source(client, project_id)
    claim = create_claim(client, project_id, claim_text)
    response = add_evidence(client, claim["id"], source["id"], quote)
    assert response.status_code == 201, response.text
    result = client.post(f"/api/claims/{claim['id']}/verify")
    assert result.status_code == 200, result.text
    assert result.json()["result"]["verdict"] == "verified", result.text
    return source, claim, result.json()


def create_report_with_claim(
    client: TestClient, project_id: str, claim_id: str, paragraph: str, title: str = "レポート"
) -> dict:
    response = client.post(f"/api/projects/{project_id}/reports", json={"title": title})
    assert response.status_code == 201, response.text
    report = response.json()["report"]
    content = {
        "sections": [
            {
                "heading": "1. 検証",
                "paragraphs": [{"id": "p1", "text": paragraph, "claimIds": [claim_id]}],
            }
        ]
    }
    saved = client.put(
        f"/api/reports/{report['id']}",
        json={"content": content, "expected_version": report["version"]},
    )
    assert saved.status_code == 200, saved.text
    return saved.json()["report"]


def tamper_source(source_id: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE sources SET content = content || 'x' WHERE id = :id"),
            {"id": source_id},
        )


def insert_evidence(claim_id: str, source_id: str, quote: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO claim_evidence (id, claim_id, source_id, quote, note, created_at) "
                "VALUES (:id, :claim_id, :source_id, :quote, '', now())"
            ),
            {
                "id": str(uuid.uuid4()),
                "claim_id": claim_id,
                "source_id": source_id,
                "quote": quote,
            },
        )


def audit_actions() -> list[str]:
    with SessionLocal() as db:
        return list(db.execute(select(AuditEvent.action)).scalars())


# ---------------------------------------------------------------- 1
def test_tc_mw7phjyd_login_and_me(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7phjyd_64fa0a44", "ログイン成功と /me")
    editor = demo_users["editor"]
    body = login_as(client, editor["email"], DEMO_PASSWORD)
    case.step("login", status=200, user=body["user"])
    case.expect("rihrp_session" in client.cookies, "rihrp_session Cookie がない")
    case.expect("rihrp_csrf" in client.cookies, "rihrp_csrf Cookie がない")

    me = client.get("/api/auth/me")
    case.step("me", status=me.status_code, body=me.json())
    case.expect(me.status_code == 200, f"/me が {me.status_code}")
    case.expect(me.json()["user"]["email"] == editor["email"], "email が一致しない")
    case.expect(me.json()["user"]["role"] == "editor", "role が editor でない")
    case.finish()


# ---------------------------------------------------------------- 2
def test_tc_mw7phjyq_login_failure_is_identical(
    client: TestClient, demo_users: dict[str, dict]
) -> None:
    case = Case("tc_mw7phjyq_9b6cafbe", "ログイン失敗理由の統一")
    editor = demo_users["editor"]
    client.headers.pop("X-CSRF-Token", None)

    started = time.perf_counter()
    unknown = client.post(
        "/api/auth/login",
        json={"email": "nobody@rihrp.local", "password": "wrong-password-1"},
    )
    unknown_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    wrong = client.post(
        "/api/auth/login",
        json={"email": editor["email"], "password": "wrong-password-1"},
    )
    wrong_ms = (time.perf_counter() - started) * 1000

    case.step(
        "attempts",
        unknown={
            "status": unknown.status_code,
            "error": unknown.json().get("error"),
            "ms": round(unknown_ms, 1),
        },
        existing={
            "status": wrong.status_code,
            "error": wrong.json().get("error"),
            "ms": round(wrong_ms, 1),
        },
    )
    case.expect(unknown.status_code == 401, f"存在しない email が {unknown.status_code}")
    case.expect(wrong.status_code == 401, f"誤パスワードが {wrong.status_code}")
    case.expect(
        unknown.json().get("error", {}).get("code") == wrong.json().get("error", {}).get("code"),
        "error.code が一致しない",
    )
    case.expect(
        unknown.json().get("error", {}).get("message")
        == wrong.json().get("error", {}).get("message"),
        "error.message が一致しない",
    )
    case.expect(abs(unknown_ms - wrong_ms) < 300, "応答時間に 300ms 以上の差がある")
    case.finish()


# ---------------------------------------------------------------- 3
def test_tc_mw7phjzg_cookie_attributes(
    client: TestClient, demo_users: dict[str, dict], monkeypatch
) -> None:
    case = Case("tc_mw7phjzg_91e23d52", "セッション Cookie の属性")
    editor = demo_users["editor"]

    dev = client.post("/api/auth/login", json={"email": editor["email"], "password": DEMO_PASSWORD})
    dev_cookies = dev.headers.get_list("set-cookie")
    session_cookie = next(c for c in dev_cookies if c.startswith("rihrp_session="))
    csrf_cookie = next(c for c in dev_cookies if c.startswith("rihrp_csrf="))
    case.step("development", session=session_cookie, csrf=csrf_cookie)
    case.expect("HttpOnly" in session_cookie, "session に HttpOnly がない")
    case.expect("samesite=lax" in session_cookie.lower(), "session に SameSite=Lax がない")
    case.expect("Path=/" in session_cookie, "session に Path=/ がない")
    case.expect("Secure" not in session_cookie, "development で Secure が付いている")
    case.expect("HttpOnly" not in csrf_cookie, "csrf が HttpOnly になっている")

    monkeypatch.setattr(get_settings(), "env", "production")
    with new_client() as prod:
        prod_response = prod.post(
            "/api/auth/login", json={"email": editor["email"], "password": DEMO_PASSWORD}
        )
        prod_session = next(
            c
            for c in prod_response.headers.get_list("set-cookie")
            if c.startswith("rihrp_session=")
        )
    case.step("production", session=prod_session)
    case.expect("Secure" in prod_session, "production で Secure が付かない")
    case.finish()


# ---------------------------------------------------------------- 4
def test_tc_mw7phjzs_csrf_required(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7phjzs_4572064f", "CSRF 欠落・不一致 403")
    editor = demo_users["editor"]
    body = login_as(client, editor["email"], DEMO_PASSWORD, set_csrf=False)
    csrf = body["csrf_token"]

    missing = client.post("/api/projects", json={"title": "CSRF欠落"})
    mismatched = client.post(
        "/api/projects", json={"title": "CSRF不一致"}, headers={"X-CSRF-Token": "not-the-token"}
    )
    matched = client.post(
        "/api/projects", json={"title": "CSRF一致"}, headers={"X-CSRF-Token": csrf}
    )
    listed = client.get("/api/projects")

    case.step(
        "responses",
        missing={"status": missing.status_code, "error": missing.json().get("error")},
        mismatched={"status": mismatched.status_code, "error": mismatched.json().get("error")},
        matched={"status": matched.status_code},
        get_without_token={"status": listed.status_code, "count": len(listed.json()["projects"])},
    )
    case.expect(missing.status_code == 403, f"欠落が {missing.status_code}")
    case.expect(mismatched.status_code == 403, f"不一致が {mismatched.status_code}")
    case.expect(matched.status_code == 201, f"一致時が {matched.status_code}")
    case.expect(listed.status_code == 200, f"GET が {listed.status_code}")
    case.finish()


# ---------------------------------------------------------------- 5
def test_tc_mw7phk0f_password_change_boundary(
    client: TestClient, demo_users: dict[str, dict]
) -> None:
    case = Case("tc_mw7phk0f_bc14b2e0", "パスワード 12 文字境界・失効")
    editor = demo_users["editor"]
    login_as(client, editor["email"], DEMO_PASSWORD)
    with new_client() as session_b:
        login_as(session_b, editor["email"], DEMO_PASSWORD)

        wrong_current = client.post(
            "/api/auth/change-password",
            json={"current_password": "definitely-wrong", "new_password": "abcdefghijkl"},
        )
        too_short = client.post(
            "/api/auth/change-password",
            json={"current_password": DEMO_PASSWORD, "new_password": "abcdefghijk"},
        )
        success = client.post(
            "/api/auth/change-password",
            json={"current_password": DEMO_PASSWORD, "new_password": "abcdefghijkl"},
        )
        other = session_b.get("/api/auth/me")
        current = client.get("/api/auth/me")

    case.step(
        "responses",
        wrong_current={
            "status": wrong_current.status_code,
            "error": wrong_current.json().get("error"),
        },
        too_short={"status": too_short.status_code, "error": too_short.json().get("error")},
        success={"status": success.status_code},
        other_session={"status": other.status_code},
        current_session={"status": current.status_code},
    )
    case.expect(wrong_current.status_code in (400, 401, 422), "誤った現在パスワードが拒否されない")
    case.expect(too_short.status_code == 422, f"11 文字が {too_short.status_code}")
    case.expect(success.status_code == 200, f"12 文字が {success.status_code}")
    case.expect(other.status_code == 401, f"他セッションが {other.status_code}")
    case.expect(current.status_code == 200, f"現在セッションが {current.status_code}")
    case.finish()


# ---------------------------------------------------------------- 6
def test_tc_mw7phk0t_access_jwt(
    client: TestClient, users: dict[str, str], access_env, signing_key
) -> None:
    from tests.integration.test_access_login import make_token

    case = Case("tc_mw7phk0t_01e5685d", "Access JWT の成功・拒否")
    valid = client.get(
        "/api/auth/access", headers={"Cf-Access-Jwt-Assertion": make_token(signing_key)}
    )
    valid_cookie = any(c.startswith("rihrp_session=") for c in valid.headers.get_list("set-cookie"))

    with new_client() as other:
        tampered_token = make_token(signing_key)[:-4] + "aaaa"
        tampered = other.get(
            "/api/auth/access", headers={"Cf-Access-Jwt-Assertion": tampered_token}
        )
    with new_client() as other:
        expired = other.get(
            "/api/auth/access",
            headers={"Cf-Access-Jwt-Assertion": make_token(signing_key, exp_delta=-10)},
        )
    with new_client() as other:
        plain = other.get(
            "/api/auth/access",
            headers={"Cf-Access-Authenticated-User-Email": "editor@test.local"},
        )
    with new_client() as other:
        outside = other.get(
            "/api/auth/access",
            headers={"Cf-Access-Jwt-Assertion": make_token(signing_key, email="other@test.local")},
        )

    with SessionLocal() as db:
        denied = list(
            db.execute(
                select(AuditEvent.details).where(AuditEvent.action == "auth.access_denied")
            ).scalars()
        )
    reasons = [entry.get("reason") for entry in denied]

    case.step(
        "responses",
        valid={"status": valid.status_code, "cookie": valid_cookie},
        tampered={"status": tampered.status_code},
        expired={"status": expired.status_code},
        plain_header={"status": plain.status_code},
        outside_allowlist={"status": outside.status_code},
        denied_reasons=reasons,
    )
    case.expect(valid.status_code == 200, f"有効 JWT が {valid.status_code}")
    case.expect(valid_cookie, "有効 JWT でセッション Cookie が出ない")
    case.expect(tampered.status_code >= 400, "改竄 JWT が拒否されない")
    case.expect(expired.status_code >= 400, "期限切れ JWT が拒否されない")
    case.expect(plain.status_code >= 400, "平文ヘッダーが拒否されない")
    case.expect(outside.status_code >= 400, "allowlist 外が拒否されない")
    case.expect("auth.access_denied" in audit_actions(), "拒否監査がない")
    case.expect(bool(reasons), "拒否理由が監査に残っていない")
    case.finish()


# ---------------------------------------------------------------- 7
def test_tc_mw7pi009_project_rbac(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7pi009_3012ef11", "テーマ作成・更新の権限")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    created = client.post("/api/projects", json={"title": "検証テーマ"})
    project_id = created.json()["project"]["id"]
    updated = client.patch(f"/api/projects/{project_id}", json={"title": "更新後"})
    listed = client.get("/api/projects")

    with new_client() as viewer:
        login_as(viewer, demo_users["viewer"]["email"], DEMO_PASSWORD)
        viewer_post = viewer.post("/api/projects", json={"title": "viewer"})
    with new_client() as reviewer:
        login_as(reviewer, demo_users["reviewer"]["email"], DEMO_PASSWORD)
        reviewer_post = reviewer.post("/api/projects", json={"title": "reviewer"})

    too_long = client.post("/api/projects", json={"title": "x" * 201})

    case.step(
        "responses",
        create={"status": created.status_code},
        update={
            "status": updated.status_code,
            "title": updated.json().get("project", {}).get("title"),
        },
        list_contains=any(
            p["id"] == project_id and p["title"] == "更新後" for p in listed.json()["projects"]
        ),
        viewer={"status": viewer_post.status_code},
        reviewer={"status": reviewer_post.status_code},
        title_201={"status": too_long.status_code, "error": too_long.json().get("error")},
    )
    case.expect(created.status_code == 201, f"作成が {created.status_code}")
    case.expect(updated.status_code == 200, f"更新が {updated.status_code}")
    case.expect(updated.json()["project"]["title"] == "更新後", "更新が反映されない")
    case.expect(
        any(p["id"] == project_id and p["title"] == "更新後" for p in listed.json()["projects"]),
        "一覧に更新が反映されない",
    )
    case.expect(viewer_post.status_code == 403, f"viewer が {viewer_post.status_code}")
    case.expect(reviewer_post.status_code == 403, f"reviewer が {reviewer_post.status_code}")
    case.expect(too_long.status_code == 422, f"201 文字が {too_long.status_code}")
    case.finish()


# ---------------------------------------------------------------- 8
def test_tc_mw7pi015_source_kinds_and_sha(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7pi015_ee8a1fd6", "出典 3 種と SHA-256")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    project = create_project(client)
    bodies = {
        "url": "URL 出典の本文 1,240 MW",
        "doi": "DOI 出典の本文 480 MW",
        "text": "自由文の出典本文 120 MW",
    }
    origins = {"url": "https://example.test/a", "doi": "10.0000/example", "text": ""}
    created = {}
    for kind, body in bodies.items():
        response = client.post(
            f"/api/projects/{project['id']}/sources",
            json={
                "title": f"{kind} 出典",
                "kind": kind,
                "origin": origins[kind],
                "content": body,
            },
        )
        created[kind] = response

    details = {}
    for kind, response in created.items():
        fetched = client.get(f"/api/sources/{response.json()['source']['id']}")
        expected = hashlib.sha256(bodies[kind].encode("utf-8")).hexdigest()
        details[kind] = {
            "create_status": response.status_code,
            "get_status": fetched.status_code,
            "kind": fetched.json()["source"]["kind"],
            "origin": fetched.json()["source"]["origin"],
            "sha_matches": fetched.json()["source"]["content_sha256"] == expected,
            "sha64": len(fetched.json()["source"]["content_sha256"]) == 64,
            "tampered": fetched.json()["source"]["tampered"],
        }
    case.step("sources", **details)
    for kind, item in details.items():
        case.expect(item["create_status"] == 201, f"{kind} の登録が {item['create_status']}")
        case.expect(item["get_status"] == 200, f"{kind} の取得が {item['get_status']}")
        case.expect(item["kind"] == kind, f"{kind} の kind が違う")
        case.expect(item["origin"] == origins[kind], f"{kind} の origin が違う")
        case.expect(item["sha_matches"], f"{kind} の SHA-256 が本文と一致しない")
        case.expect(item["sha64"], f"{kind} の SHA-256 が 64 桁でない")
        case.expect(item["tampered"] is False, f"{kind} が tampered=true")
    case.finish()


# ---------------------------------------------------------------- 9
def test_tc_mw7pi021_tamper_detection(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7pi021_defecae4", "改竄検知（tampered）")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    project = create_project(client)
    source, claim, _ = build_verified_claim(
        client, project["id"], "導入可能量は 1,240 MW と試算された。", "導入可能量は 1,240 MW"
    )
    before = client.get(f"/api/sources/{source['id']}")
    tamper_source(source["id"])
    after = client.get(f"/api/sources/{source['id']}")
    verified = client.post(f"/api/claims/{claim['id']}/verify")

    delete_unused = create_source(
        client,
        project["id"],
        title="未使用",
        origin="https://example.test/unused",
        content="未使用の本文",
    )
    delete_unused_response = client.delete(f"/api/sources/{delete_unused['id']}")
    delete_in_use = client.delete(f"/api/sources/{source['id']}")

    case.step(
        "responses",
        before=before.json()["source"]["tampered"],
        after=after.json()["source"]["tampered"],
        verify={"status": verified.status_code, "result": verified.json().get("result")},
        delete_unused={"status": delete_unused_response.status_code},
        delete_in_use={
            "status": delete_in_use.status_code,
            "error": delete_in_use.json().get("error"),
        },
    )
    case.expect(before.json()["source"]["tampered"] is False, "改竄前が tampered=true")
    case.expect(after.json()["source"]["tampered"] is True, "改竄後が tampered=false")
    case.expect(
        verified.json()["result"]["verdict"] == "contradicted", "改竄後の判定が contradicted でない"
    )
    case.expect(
        "evidence_tampered" in verified.json()["result"]["reasons"],
        "理由に evidence_tampered がない",
    )
    case.deviation(
        "ケース手順 5 の『出典の削除 API が存在しない（404/405）』は現実装と不一致。"
        f"DELETE /api/sources/{{id}} は存在し、未使用は {delete_unused_response.status_code}、"
        f"使用中は {delete_in_use.status_code}（source_in_use）で保護される。"
    )
    case.finish()


# ---------------------------------------------------------------- 10
def test_tc_mw7pigi8_quote_existence(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7pigi8_2068fe0f", "引用の実在確認")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    project = create_project(client)
    source = create_source(client, project["id"], content="海岸護岸の洗掘深さは 50 cm を超える。")
    claim = create_claim(client, project["id"], "洗掘深さは 50 cm を超えるという調査結果がある。")

    found = add_evidence(client, claim["id"], source["id"], "洗掘深さは 50 cm")
    missing = add_evidence(client, claim["id"], source["id"], "存在しない引用文")
    spaced = add_evidence(client, claim["id"], source["id"], "洗掘深さは　50 cm")
    empty = add_evidence(client, claim["id"], source["id"], "")
    too_long = add_evidence(client, claim["id"], source["id"], "x" * 501)

    case.step(
        "responses",
        found={"status": found.status_code},
        missing={"status": missing.status_code, "error": missing.json().get("error")},
        spaced={"status": spaced.status_code},
        empty={"status": empty.status_code},
        too_long={"status": too_long.status_code, "error": too_long.json().get("error")},
    )
    case.expect(found.status_code == 201, f"実在引用が {found.status_code}")
    case.expect(missing.status_code == 422, f"不在引用が {missing.status_code}")
    case.expect(
        missing.json().get("error", {}).get("code") == "quote_not_found",
        "不在引用の code が quote_not_found でない",
    )
    case.expect(spaced.status_code == 201, f"空白差が {spaced.status_code}")
    case.expect(empty.status_code == 201, f"空引用が {empty.status_code}")
    case.expect(too_long.status_code == 422, f"501 文字が {too_long.status_code}")
    case.finish()


# ---------------------------------------------------------------- 11
def test_tc_mw7pigiz_verification_rules(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7pigiz_3960de50", "検証 6 規則（draft）")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    project = create_project(client)
    source = create_source(client, project["id"], content="海岸護岸の洗掘深さは 50 cm を超える。")

    no_evidence_claim = create_claim(client, project["id"], "根拠のない主張をここに置く。")
    r1 = client.post(f"/api/claims/{no_evidence_claim['id']}/verify")

    missing_quote_claim = create_claim(client, project["id"], "引用が本文に無い主張をここに置く。")
    insert_evidence(missing_quote_claim["id"], source["id"], "本文に存在しない引用")
    r2 = client.post(f"/api/claims/{missing_quote_claim['id']}/verify")

    unverified_claim = create_claim(client, project["id"], "洗掘深さは 80 cm を超える。")
    add_evidence(client, unverified_claim["id"], source["id"], "洗掘深さは 50 cm")
    r3 = client.post(f"/api/claims/{unverified_claim['id']}/verify")

    verified_claim = create_claim(client, project["id"], "洗掘深さは 50 cm を超える。")
    add_evidence(client, verified_claim["id"], source["id"], "洗掘深さは 50 cm")
    r4 = client.post(f"/api/claims/{verified_claim['id']}/verify")

    insufficient_claim = create_claim(client, project["id"], "数値も引用も無い主張をここに置く。")
    add_evidence(client, insufficient_claim["id"], source["id"], "")
    r5 = client.post(f"/api/claims/{insufficient_claim['id']}/verify")

    number_claim = create_claim(client, project["id"], "洗掘深さは 50 cm である。")
    add_evidence(client, number_claim["id"], source["id"], "")
    r6 = client.post(f"/api/claims/{number_claim['id']}/verify")

    results = {
        "no_evidence": r1.json()["result"],
        "quote_missing": r2.json()["result"],
        "number_missing": r3.json()["result"],
        "verified": r4.json()["result"],
        "no_anchor": r5.json()["result"],
        "number_only": r6.json()["result"],
    }
    case.step("verdicts", **results)
    case.expect(r1.json()["result"]["verdict"] == "insufficient", "規則1 insufficient でない")
    case.expect(r2.json()["result"]["verdict"] == "contradicted", "規則2 contradicted でない")
    case.expect(r3.json()["result"]["verdict"] == "unverified", "規則3 unverified でない")
    case.expect(r4.json()["result"]["verdict"] == "verified", "規則4 verified でない")
    case.expect(r5.json()["result"]["verdict"] == "insufficient", "規則5 insufficient でない")
    case.expect(r5.json()["result"]["reasons"] == ["no_anchor"], "規則5 の理由が no_anchor でない")
    case.expect(r6.json()["result"]["verdict"] == "verified", "規則6 verified でない")
    case.expect(
        r6.json()["result"]["reasons"] == ["number_verified"],
        "規則6 の理由が number_verified でない",
    )
    case.finish()


# ---------------------------------------------------------------- 12
def test_tc_mw7pigjb_details_breakdown(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7pigjb_d4f0c1a9", "検証 details の内訳")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    project = create_project(client)
    source = create_source(client, project["id"], content="導入可能量は 1,240 MW と試算された。")
    claim = create_claim(client, project["id"], "導入可能量は 1,240 MW と試算された。")
    add_evidence(client, claim["id"], source["id"], "導入可能量は 1,240 MW")

    first = client.post(f"/api/claims/{claim['id']}/verify").json()["result"]
    client.patch(
        f"/api/claims/{claim['id']}", json={"text": "導入可能量は 9,999 MW と試算された。"}
    )
    second = client.post(f"/api/claims/{claim['id']}/verify").json()["result"]
    tamper_source(source["id"])
    third = client.post(f"/api/claims/{claim['id']}/verify").json()["result"]

    case.step("details", first=first["details"], second=second["details"], third=third["details"])
    case.expect(first["verdict"] == "verified", "1 回目が verified でない")
    case.expect(
        first["details"]["evidence"][0]["quote_found"] is True, "quote_found が true でない"
    )
    case.expect(first["details"]["evidence"][0]["digest_ok"] is True, "digest_ok が true でない")
    case.expect(all(n["found"] for n in first["details"]["numbers"]), "数値が found=false")
    case.expect(second["verdict"] == "unverified", "2 回目が unverified でない")
    case.expect(any(n["found"] is False for n in second["details"]["numbers"]), "未発見数値がない")
    case.expect(third["verdict"] == "contradicted", "3 回目が contradicted でない")
    case.expect(third["details"]["evidence"][0]["digest_ok"] is False, "digest_ok が false でない")
    case.expect("evidence_tampered" in third["reasons"], "evidence_tampered がない")
    case.finish()


# ---------------------------------------------------------------- 13
def test_tc_mw7piylz_approve_and_residual_counts(
    client: TestClient, demo_users: dict[str, dict]
) -> None:
    case = Case("tc_mw7piylz_19e85845", "承認成功＋残数表示")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    project = create_project(client)
    _, claim, _ = build_verified_claim(
        client, project["id"], "導入可能量は 1,240 MW と試算された。", "導入可能量は 1,240 MW"
    )
    report = create_report_with_claim(
        client, project["id"], claim["id"], "導入可能量は 1,240 MW と試算された。"
    )
    submitted = client.post(f"/api/reports/{report['id']}/submit")
    assert submitted.status_code == 200, submitted.text

    with new_client() as reviewer:
        login_as(reviewer, demo_users["reviewer"]["email"], DEMO_PASSWORD)
        reviewer.post(f"/api/reports/{report['id']}/verify")
        approved = reviewer.post(
            f"/api/reports/{report['id']}/review",
            json={"decision": "approved", "comment": "確認しました。"},
        )
        fetched = reviewer.get(f"/api/reports/{report['id']}")

    summary = fetched.json()["report"]["latest_verification"]["summary"]
    case.step(
        "approved",
        status=approved.status_code,
        report_status=fetched.json()["report"]["status"],
        summary_keys=sorted(summary.keys()),
    )
    case.expect(approved.status_code == 200, f"承認が {approved.status_code}")
    case.expect(fetched.json()["report"]["status"] == "approved", "status が approved でない")
    case.expect("unverified" in summary, "unverified が省略されている")
    case.expect("insufficient" in summary, "insufficient が省略されている")
    case.expect(summary["unverified"] == 0, "unverified が 0 でない")
    case.expect(summary["insufficient"] == 0, "insufficient が 0 でない")

    # 未検証（根拠なし＝insufficient）を含むレポートも承認でき、残数が残ることを確認する
    claim2 = create_claim(client, project["id"], "根拠のない主張は残数として扱われる。")
    report2 = create_report_with_claim(
        client, project["id"], claim2["id"], "根拠のない主張は残数として扱われる。", "残数レポート"
    )
    client.post(f"/api/reports/{report2['id']}/submit")
    with new_client() as reviewer2:
        login_as(reviewer2, demo_users["reviewer"]["email"], DEMO_PASSWORD)
        approved2 = reviewer2.post(
            f"/api/reports/{report2['id']}/review",
            json={"decision": "approved", "comment": "残数を確認しました。"},
        )
        fetched2 = reviewer2.get(f"/api/reports/{report2['id']}")
    summary2 = fetched2.json()["report"]["latest_verification"]["summary"]
    case.step("residual", status=approved2.status_code, summary=summary2)
    case.expect(approved2.status_code == 200, "残数あり承認が拒否された")
    case.expect(summary2["insufficient"] == 1, "insufficient 残数が 1 でない")
    case.finish()


# ---------------------------------------------------------------- 14
def test_tc_mw7piymc_approval_blocked(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7piymc_5f7507c0", "承認 409＋検証結果保存")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    project = create_project(client)
    source, claim, _ = build_verified_claim(
        client, project["id"], "導入可能量は 1,240 MW と試算された。", "導入可能量は 1,240 MW"
    )
    report = create_report_with_claim(
        client, project["id"], claim["id"], "導入可能量は 1,240 MW と試算された。"
    )
    client.post(f"/api/reports/{report['id']}/submit")
    tamper_source(source["id"])

    with new_client() as reviewer:
        login_as(reviewer, demo_users["reviewer"]["email"], DEMO_PASSWORD)
        blocked = reviewer.post(
            f"/api/reports/{report['id']}/review",
            json={"decision": "approved", "comment": "確認しました。"},
        )
        fetched = reviewer.get(f"/api/reports/{report['id']}")

    with SessionLocal() as db:
        rows = list(
            db.execute(
                select(ReportVerification).where(ReportVerification.report_id == report["id"])
            ).scalars()
        )
    case.step(
        "blocked",
        status=blocked.status_code,
        error=blocked.json().get("error"),
        report_status=fetched.json()["report"]["status"],
        verification_rows=len(rows),
        latest_summary=rows[-1].summary if rows else None,
    )
    case.expect(blocked.status_code == 409, f"承認が {blocked.status_code}")
    case.expect(
        blocked.json().get("error", {}).get("code") == "approval_blocked",
        "code が approval_blocked でない",
    )
    case.expect(fetched.json()["report"]["status"] == "in_review", "status が in_review でない")
    case.expect(bool(rows), "拒否時の検証行が残っていない")
    case.expect(rows[-1].summary["contradicted"] >= 1, "contradicted 件数が残っていない")
    case.finish()


# ---------------------------------------------------------------- 15
def test_tc_mw7piymy_self_approval_forbidden(
    client: TestClient, demo_users: dict[str, dict]
) -> None:
    case = Case("tc_mw7piymy_f572f756", "自己承認 403")
    with new_client() as admin:
        login_as(admin, demo_users["admin"]["email"], DEMO_PASSWORD)
        project = create_project(admin)
        _, claim, _ = build_verified_claim(
            admin, project["id"], "導入可能量は 1,240 MW と試算された。", "導入可能量は 1,240 MW"
        )
        report = create_report_with_claim(
            admin, project["id"], claim["id"], "導入可能量は 1,240 MW と試算された。"
        )
        admin.post(f"/api/reports/{report['id']}/submit")
        self_approval = admin.post(
            f"/api/reports/{report['id']}/review",
            json={"decision": "approved", "comment": "自分で承認します。"},
        )
        status_after = admin.get(f"/api/reports/{report['id']}").json()["report"]["status"]

    with new_client() as reviewer:
        login_as(reviewer, demo_users["reviewer"]["email"], DEMO_PASSWORD)
        approved = reviewer.post(
            f"/api/reports/{report['id']}/review",
            json={"decision": "approved", "comment": "職務分離を確認しました。"},
        )

    case.step(
        "responses",
        self_approval={
            "status": self_approval.status_code,
            "error": self_approval.json().get("error"),
        },
        status_after=status_after,
        reviewer_approval={"status": approved.status_code},
    )
    case.expect(self_approval.status_code == 403, f"自己承認が {self_approval.status_code}")
    case.expect(status_after == "in_review", f"自己承認後の status が {status_after}")
    case.expect(approved.status_code == 200, f"別 reviewer の承認が {approved.status_code}")
    case.expect(
        approved.json()["report"]["status"] == "approved", "別 reviewer で approved にならない"
    )
    case.finish()


# ---------------------------------------------------------------- 16
def test_tc_mw7piynz_post_approval_tamper(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7piynz_b5ff1258", "承認後の改竄検知")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    project = create_project(client)
    source, claim, _ = build_verified_claim(
        client, project["id"], "導入可能量は 1,240 MW と試算された。", "導入可能量は 1,240 MW"
    )
    report = create_report_with_claim(
        client, project["id"], claim["id"], "導入可能量は 1,240 MW と試算された。"
    )
    client.post(f"/api/reports/{report['id']}/submit")

    with new_client() as reviewer:
        login_as(reviewer, demo_users["reviewer"]["email"], DEMO_PASSWORD)
        reviewer.post(f"/api/reports/{report['id']}/verify")
        approved = reviewer.post(
            f"/api/reports/{report['id']}/review",
            json={"decision": "approved", "comment": "確認しました。"},
        )
        assert approved.status_code == 200, approved.text
        before = reviewer.get(f"/api/reports/{report['id']}").json()["report"]["integrity"]
        tamper_source(source["id"])
        after = reviewer.get(f"/api/reports/{report['id']}").json()["report"]["integrity"]
        reverified = reviewer.post(f"/api/reports/{report['id']}/verify")

    case.step(
        "integrity",
        before=before,
        after=after,
        reverify_status=reverified.status_code,
        reverify_summary=reverified.json().get("summary"),
    )
    case.expect(before["needs_reapproval"] is False, "承認直後に needs_reapproval=true")
    case.expect(after["tampered_sources"] >= 1, "改竄が tampered_sources に出ない")
    case.expect(after["needs_reapproval"] is True, "改竄後に needs_reapproval=false")
    case.expect(
        reverified.json()["summary"]["contradicted"] >= 1, "再検証で contradicted にならない"
    )
    case.finish()


# ---------------------------------------------------------------- 17
def test_tc_mw7ppxy9_acceptance_full_flow(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7ppxy9_e62e0b90", "受入 #1 通しフロー")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    project = create_project(client, "受入テスト")
    source = create_source(client, project["id"], content=SOURCE_TEXT)
    expected_sha = hashlib.sha256(SOURCE_TEXT.encode("utf-8")).hexdigest()
    claim = create_claim(client, project["id"], "導入可能量は 1,240 MW と試算された。")
    evidence = add_evidence(client, claim["id"], source["id"], "導入可能量は 1,240 MW")
    verified = client.post(f"/api/claims/{claim['id']}/verify")
    report = create_report_with_claim(
        client, project["id"], claim["id"], "導入可能量は 1,240 MW と試算された。"
    )
    submitted = client.post(f"/api/reports/{report['id']}/submit")

    with new_client() as reviewer:
        login_as(reviewer, demo_users["reviewer"]["email"], DEMO_PASSWORD)
        report_verified = reviewer.post(f"/api/reports/{report['id']}/verify")
        approved = reviewer.post(
            f"/api/reports/{report['id']}/review",
            json={"decision": "approved", "comment": "受入確認しました。"},
        )
        exported = reviewer.get(f"/api/reports/{report['id']}/export")
        audit = reviewer.get("/api/audit", params={"project_id": project["id"]})

    actions = [event["action"] for event in audit.json()["events"]]
    case.step(
        "flow",
        project=project["id"],
        source_sha_ok=source["content_sha256"] == expected_sha,
        evidence_status=evidence.status_code,
        claim_verdict=verified.json()["result"]["verdict"],
        report_version=report["version"],
        submit_status=submitted.status_code,
        submit_state=submitted.json()["report"]["status"],
        report_verify=report_verified.json().get("summary"),
        approve_status=approved.status_code,
        approved_state=approved.json()["report"]["status"],
        export_status=exported.status_code,
        export_has_marker="[検証済]" in exported.text,
        export_has_sha=expected_sha[:12] in exported.text,
        audit_actions=sorted(set(actions)),
    )
    case.expect(source["content_sha256"] == expected_sha, "SHA-256 が一致しない")
    case.expect(evidence.status_code == 201, "根拠登録が失敗")
    case.expect(verified.json()["result"]["verdict"] == "verified", "検証が verified でない")
    case.expect(submitted.status_code == 200, "提出が失敗")
    case.expect(submitted.json()["report"]["status"] == "in_review", "提出後 in_review でない")
    case.expect(
        report_verified.json()["summary"]["contradicted"] == 0, "提出後検証で contradicted がある"
    )
    case.expect(approved.status_code == 200, f"承認が {approved.status_code}")
    case.expect(approved.json()["report"]["status"] == "approved", "承認後 approved でない")
    case.expect(exported.status_code == 200, "エクスポートが失敗")
    case.expect("[検証済]" in exported.text, "エクスポートに検証マーカーがない")
    case.expect(expected_sha[:12] in exported.text, "エクスポートに根拠 SHA がない")
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
    case.finish()


# ---------------------------------------------------------------- 18
def test_tc_mw7ppxyq_acceptance_tamper_flow(
    client: TestClient, demo_users: dict[str, dict]
) -> None:
    case = Case("tc_mw7ppxyq_e103c419", "受入 #2 改竄→409")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    project = create_project(client, "受入テスト2")
    source, claim, _ = build_verified_claim(
        client, project["id"], "導入可能量は 1,240 MW と試算された。", "導入可能量は 1,240 MW"
    )
    report = create_report_with_claim(
        client, project["id"], claim["id"], "導入可能量は 1,240 MW と試算された。"
    )
    client.post(f"/api/reports/{report['id']}/submit")
    tamper_source(source["id"])
    reverified = client.post(f"/api/claims/{claim['id']}/verify")

    with new_client() as reviewer:
        login_as(reviewer, demo_users["reviewer"]["email"], DEMO_PASSWORD)
        report_verified = reviewer.post(f"/api/reports/{report['id']}/verify")
        approved = reviewer.post(
            f"/api/reports/{report['id']}/review",
            json={"decision": "approved", "comment": "確認しました。"},
        )
        source_after = reviewer.get(f"/api/sources/{source['id']}")

    with SessionLocal() as db:
        rows = list(
            db.execute(
                select(ReportVerification).where(ReportVerification.report_id == report["id"])
            ).scalars()
        )
    case.step(
        "flow",
        reverify=reverified.json()["result"],
        report_summary=report_verified.json().get("summary"),
        approve_status=approved.status_code,
        approve_error=approved.json().get("error"),
        verification_rows=len(rows),
        source_tampered=source_after.json()["source"]["tampered"],
    )
    case.expect(
        reverified.json()["result"]["verdict"] == "contradicted", "再検証が contradicted でない"
    )
    case.expect(
        "evidence_tampered" in reverified.json()["result"]["reasons"], "evidence_tampered がない"
    )
    case.expect(
        report_verified.json()["summary"]["contradicted"] >= 1, "レポート検証で contradicted が 0"
    )
    case.expect(approved.status_code == 409, f"承認が {approved.status_code}")
    case.expect(
        approved.json().get("error", {}).get("code") == "approval_blocked",
        "code が approval_blocked でない",
    )
    case.expect(bool(rows), "拒否時の検証履歴が残っていない")
    case.expect(source_after.json()["source"]["tampered"] is True, "出典が tampered=true でない")
    case.finish()


# ---------------------------------------------------------------- 19
def test_tc_mw7pjgw4_audit_immutable(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7pjgw4_71f966b3", "監査の不変・TRUNCATE 拒否")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    client.post("/api/projects", json={"title": "監査テスト"})

    with new_client() as reviewer:
        login_as(reviewer, demo_users["reviewer"]["email"], DEMO_PASSWORD)
        reviewer_audit = reviewer.get("/api/audit")
        put_audit = reviewer.put("/api/audit", json={"action": "x"})
        delete_audit = reviewer.delete("/api/audit")
    with new_client() as viewer:
        login_as(viewer, demo_users["viewer"]["email"], DEMO_PASSWORD)
        viewer_audit = viewer.get("/api/audit")

    errors = {}
    for name, statement in {
        "update": "UPDATE audit_events SET action = 'tampered'",
        "delete": "DELETE FROM audit_events",
        "truncate": "TRUNCATE audit_events",
    }.items():
        try:
            with engine.begin() as connection:
                connection.execute(text(statement))
        except DBAPIError as exc:
            errors[name] = type(exc.orig).__name__
        else:
            errors[name] = "NO_ERROR"

    with engine.begin() as connection:
        app_role = connection.execute(text("SELECT current_user")).scalar_one()
        table_owner = connection.execute(
            text("SELECT pg_get_userbyid(relowner) FROM pg_class WHERE relname = 'audit_events'")
        ).scalar_one()

    case.step(
        "responses",
        reviewer_audit=reviewer_audit.status_code,
        viewer_audit=viewer_audit.status_code,
        put_audit=put_audit.status_code,
        delete_audit=delete_audit.status_code,
        db_errors=errors,
        app_role=app_role,
        table_owner=table_owner,
    )
    case.expect(
        reviewer_audit.status_code == 200, f"reviewer の監査閲覧が {reviewer_audit.status_code}"
    )
    case.expect(viewer_audit.status_code == 403, f"viewer の監査閲覧が {viewer_audit.status_code}")
    case.expect(put_audit.status_code in (404, 405), f"PUT が {put_audit.status_code}")
    case.expect(delete_audit.status_code in (404, 405), f"DELETE が {delete_audit.status_code}")
    case.expect(errors["update"] != "NO_ERROR", "UPDATE が拒否されない")
    case.expect(errors["delete"] != "NO_ERROR", "DELETE が拒否されない")
    case.expect(errors["truncate"] != "NO_ERROR", "TRUNCATE が拒否されない")
    if app_role == table_owner:
        case.skip("アプリロールがテーブル所有者のため DISABLE TRIGGER の拒否は対象外")
    else:
        try:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE audit_events DISABLE TRIGGER ALL"))
        except DBAPIError:
            pass
        else:
            case.expect(False, "DISABLE TRIGGER が拒否されない")
    case.finish()


# ---------------------------------------------------------------- 20
def test_tc_mw7pjybt_research_document(client: TestClient, demo_users: dict[str, dict]) -> None:
    case = Case("tc_mw7pjybt_baa79565", "研究文書の永続化・409（draft）")
    login_as(client, demo_users["editor"]["email"], DEMO_PASSWORD)
    project = create_project(client)
    payload = {"title": "研究", "hypothesis": "仮説", "revision": 1}

    saved = client.put(
        f"/api/projects/{project['id']}/research",
        json={"expected_version": 0, "payload": payload},
    )
    loaded = client.get(f"/api/projects/{project['id']}/research")
    conflict = client.put(
        f"/api/projects/{project['id']}/research",
        json={"expected_version": 0, "payload": payload},
    )
    too_large = client.put(
        f"/api/projects/{project['id']}/research",
        json={"expected_version": 1, "payload": {"big": "x" * (1024 * 1024 + 10)}},
    )
    with new_client() as viewer:
        login_as(viewer, demo_users["viewer"]["email"], DEMO_PASSWORD)
        viewer_put = viewer.put(
            f"/api/projects/{project['id']}/research",
            json={"expected_version": 1, "payload": payload},
        )
    with new_client() as anonymous:
        anonymous_get = anonymous.get(f"/api/projects/{project['id']}/research")
        anonymous_put = anonymous.put(
            f"/api/projects/{project['id']}/research",
            json={"expected_version": 1, "payload": payload},
        )

    deleted = client.delete(f"/api/projects/{project['id']}")
    after_delete = client.get(f"/api/projects/{project['id']}/research")

    case.step(
        "responses",
        saved={"status": saved.status_code, "version": saved.json().get("version")},
        loaded={"status": loaded.status_code, "payload": loaded.json().get("payload")},
        conflict={"status": conflict.status_code, "error": conflict.json().get("error")},
        too_large={"status": too_large.status_code, "error": too_large.json().get("error")},
        viewer_put=viewer_put.status_code,
        anonymous_get=anonymous_get.status_code,
        anonymous_put=anonymous_put.status_code,
        delete=deleted.status_code,
        after_delete=after_delete.status_code,
    )
    case.expect(saved.status_code == 200, f"保存が {saved.status_code}")
    case.expect(saved.json()["version"] == 1, "初回保存の version が 1 でない")
    case.expect(loaded.json()["payload"] == payload, "再読込で内容が復元されない")
    case.expect(conflict.status_code == 409, f"旧 version 保存が {conflict.status_code}")
    case.expect(
        conflict.json().get("error", {}).get("code") == "version_conflict",
        "code が version_conflict でない",
    )
    case.expect(too_large.status_code == 413, f"1 MiB 超が {too_large.status_code}")
    case.expect(
        too_large.json().get("error", {}).get("code") == "payload_too_large",
        "code が payload_too_large でない",
    )
    case.expect(viewer_put.status_code == 403, f"viewer が {viewer_put.status_code}")
    case.expect(anonymous_get.status_code == 401, f"未認証 GET が {anonymous_get.status_code}")
    case.expect(anonymous_put.status_code == 401, f"未認証 PUT が {anonymous_put.status_code}")
    case.expect(deleted.status_code == 200, f"テーマ削除が {deleted.status_code}")
    case.expect(after_delete.status_code == 404, f"削除後の研究文書が {after_delete.status_code}")
    case.skip("UI の 500ms デバウンス・2 ブラウザ同時編集は API 実行の範囲外（UI 実行で別途確認）")
    case.finish()
