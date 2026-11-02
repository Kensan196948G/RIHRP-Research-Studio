"""実 PostgreSQL（rihrp_test*）に対する結合テストの共通設定。"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TEST_DB_URL = os.environ.get(
    "RIHRP_TEST_DATABASE_URL",
    "postgresql+psycopg://rihrp_app:rihrp_dev_password@127.0.0.1:5432/rihrp_test",
)
if not TEST_DB_URL.rsplit("/", 1)[-1].startswith("rihrp_test"):
    raise RuntimeError("テストは rihrp_test* の DB でのみ実行できます")
# ローカルでは app が所有者でもよい。CI/本番では owner ロールで migration と後始末を行う。
MIGRATION_DB_URL = os.environ.get("RIHRP_MIGRATION_DATABASE_URL", TEST_DB_URL)

os.environ.update(
    RIHRP_ENV="test",
    RIHRP_DATABASE_URL=TEST_DB_URL,
    RIHRP_MIGRATION_DATABASE_URL=MIGRATION_DB_URL,
    RIHRP_SEED_DEMO="false",
    RIHRP_LOGIN_RATE_LIMIT="1000",
    RIHRP_COOKIE_SECURE="false",
)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from rihrp.auth import reset_login_rate  # noqa: E402
from rihrp.db import SessionLocal  # noqa: E402
from rihrp.main import app  # noqa: E402
from rihrp.models import User  # noqa: E402
from rihrp.security import hash_password  # noqa: E402

owner_engine = create_engine(MIGRATION_DB_URL, pool_pre_ping=True)
TEST_PASSWORD = "test-password-123"  # noqa: S105
ROLES = {
    "admin": "admin@test.local",
    "editor": "editor@test.local",
    "reviewer": "reviewer@test.local",
    "viewer": "viewer@test.local",
}


def alembic(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["RIHRP_DATABASE_URL"] = MIGRATION_DB_URL
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *args],
        cwd=REPO / "infra/migrations",
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.fixture(scope="session", autouse=True)
def migrated() -> None:
    alembic("upgrade", "head")


@pytest.fixture(autouse=True)
def clean_db() -> Iterator[None]:
    reset_login_rate()
    # 監査テーブルは TRUNCATE トリガーで保護されているため、テスト後始末だけ一時的に外す。
    with owner_engine.begin() as connection:
        connection.execute(text("ALTER TABLE audit_events DISABLE TRIGGER trg_audit_no_truncate"))
        try:
            connection.execute(
                text(
                    "TRUNCATE audit_events, reviews, report_verifications, report_versions, "
                    "reports, claim_evidence, claims, sources, projects, sessions, users "
                    "RESTART IDENTITY CASCADE"
                )
            )
        finally:
            connection.execute(
                text("ALTER TABLE audit_events ENABLE TRIGGER trg_audit_no_truncate")
            )
    yield


@pytest.fixture
def users() -> dict[str, str]:
    created: dict[str, str] = {}
    with SessionLocal() as db:
        for role, email in ROLES.items():
            user = User(
                email=email,
                name=f"{role} user",
                role=role,
                password_hash=hash_password(TEST_PASSWORD),
            )
            db.add(user)
            db.flush()
            created[role] = user.id
        db.commit()
    return created


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def login(client: TestClient, role: str = "editor") -> dict:
    response = client.post(
        "/api/auth/login",
        json={"email": ROLES[role], "password": TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    client.headers["X-CSRF-Token"] = body["csrf_token"]
    return body["user"]


@pytest.fixture
def editor_client(client: TestClient, users: dict[str, str]) -> TestClient:
    login(client, "editor")
    return client


@pytest.fixture
def reviewer_client(users: dict[str, str]) -> Iterator[TestClient]:
    with TestClient(app) as other:
        login(other, "reviewer")
        yield other


@pytest.fixture
def viewer_client(users: dict[str, str]) -> Iterator[TestClient]:
    with TestClient(app) as other:
        login(other, "viewer")
        yield other
