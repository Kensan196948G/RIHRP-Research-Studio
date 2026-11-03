"""行ロック後に identity map が古い値のままにならないことを確認する。"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from rihrp.db import SessionLocal
from rihrp.main import app
from rihrp.models import AuditEvent, Claim, Report, Review
from rihrp.services import get_claim_for_update, get_report_for_update, lock_project
from tests.conftest import login
from tests.integration.test_flow_integrity import build_verified_claim, create_report_with_claim


def test_report_lock_refreshes_stale_identity_map(
    editor_client: TestClient, users: dict[str, str]
) -> None:
    project, _, claim = build_verified_claim(editor_client)
    report = create_report_with_claim(editor_client, project, claim)

    with SessionLocal() as stale:
        loaded = stale.get(Report, report["id"])
        assert loaded is not None and loaded.version == 2

        with SessionLocal() as other:
            row = other.execute(select(Report).where(Report.id == report["id"])).scalar_one()
            row.version = 3
            other.commit()

        locked = get_report_for_update(stale, report["id"])
        assert locked.version == 3


def test_project_lock_refreshes_stale_identity_map(
    editor_client: TestClient, users: dict[str, str]
) -> None:
    project, _, _ = build_verified_claim(editor_client)
    from rihrp.models import Project

    with SessionLocal() as stale:
        loaded = stale.get(Project, project["id"])
        assert loaded is not None
        with SessionLocal() as other:
            row = other.execute(select(Project).where(Project.id == project["id"])).scalar_one()
            row.summary = "更新済み"
            other.commit()
        locked = lock_project(stale, project["id"])
        assert locked.summary == "更新済み"


def test_claim_lock_refreshes_stale_identity_map(
    editor_client: TestClient, users: dict[str, str]
) -> None:
    project, _, claim = build_verified_claim(editor_client)
    with SessionLocal() as stale:
        loaded = stale.get(Claim, claim["id"])
        assert loaded is not None
        with SessionLocal() as other:
            row = other.execute(select(Claim).where(Claim.id == claim["id"])).scalar_one()
            row.text = "別のセッションで更新した主張テキスト。"
            other.commit()
        lock_project(stale, project["id"])
        refreshed = get_claim_for_update(stale, claim["id"])
        assert refreshed.text == "別のセッションで更新した主張テキスト。"


def test_concurrent_approval_is_serialized(
    editor_client: TestClient, users: dict[str, str]
) -> None:
    """同じレポートへの同時承認は行ロックで直列化され、成功は 1 回だけになる（NFR-16）。"""
    project, _, claim = build_verified_claim(editor_client)
    report = create_report_with_claim(editor_client, project, claim)
    submitted = editor_client.post(f"/api/reports/{report['id']}/submit")
    assert submitted.status_code == 200, submitted.text

    barrier = threading.Barrier(2)

    def approve(_: int) -> tuple[int, str]:
        with TestClient(app) as reviewer:
            login(reviewer, "reviewer")
            barrier.wait(timeout=10)
            response = reviewer.post(
                f"/api/reports/{report['id']}/review",
                json={"decision": "approved", "comment": "同時承認の直列化テスト。"},
            )
            body = response.json()
            return response.status_code, (body.get("error") or {}).get("code", "")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(approve, range(2)))

    # 1 本目が approved にした後、2 本目は最新行を見て 409 invalid_state になる。
    assert [status for status, _ in results] == [200, 409]
    assert [code for status, code in results if status == 409] == ["invalid_state"]

    with SessionLocal() as db:
        stored = db.get(Report, report["id"])
        assert stored is not None and stored.status == "approved"
        assert db.scalar(select(func.count()).select_from(Review)) == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "report.reviewed")
            )
            == 1
        )


def test_report_row_lock_is_exclusive(editor_client: TestClient, users: dict[str, str]) -> None:
    """get_report_for_update が実際に行ロックを取る（他セッションは NOWAIT で失敗する）。"""
    project, _, claim = build_verified_claim(editor_client)
    report = create_report_with_claim(editor_client, project, claim)

    with SessionLocal() as holder:
        assert get_report_for_update(holder, report["id"]) is not None
        with SessionLocal() as other, pytest.raises(OperationalError):
            other.execute(
                select(Report).where(Report.id == report["id"]).with_for_update(nowait=True)
            ).scalar_one()
