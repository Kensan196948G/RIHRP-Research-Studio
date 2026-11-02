"""行ロック後に identity map が古い値のままにならないことを確認する。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from rihrp.db import SessionLocal
from rihrp.models import Claim, Report
from rihrp.services import get_report_for_update, lock_project
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
        refreshed = stale.execute(
            select(Claim)
            .where(Claim.id == claim["id"])
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one()
        assert refreshed.text == "別のセッションで更新した主張テキスト。"
