"""監査ログの append-only を DB レベルで検証する。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from rihrp.db import engine
from tests.conftest import login


def test_audit_events_reject_update_and_delete(client: TestClient, users: dict[str, str]) -> None:
    login(client, "editor")
    created = client.post("/api/projects", json={"title": "監査テスト", "summary": ""})
    assert created.status_code == 201

    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(text("UPDATE audit_events SET action = 'tampered'"))

    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(text("DELETE FROM audit_events"))

    with engine.begin() as connection:
        count = connection.execute(text("SELECT count(*) FROM audit_events")).scalar_one()
    assert count >= 1
