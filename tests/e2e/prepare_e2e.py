#!/usr/bin/env python3
"""E2E（Playwright）用のテスト DB 準備。

- テスト DB（rihrp_test*）に migration を適用する
- 業務テーブルを初期化し、E2E 用の管理者ユーザーを作る

秘密は環境変数で渡す（既定はローカル開発用の既知値）。本番 DB では実行しない。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEST_DB_URL = os.environ.get(
    "RIHRP_TEST_DATABASE_URL",
    "postgresql+psycopg://rihrp_app:rihrp_dev_password@127.0.0.1:5432/rihrp_test",
)
if not TEST_DB_URL.rsplit("/", 1)[-1].startswith("rihrp_test"):
    raise SystemExit("E2E は rihrp_test* の DB でのみ実行できます")

E2E_EMAIL = os.environ.get("RIHRP_E2E_EMAIL", "admin@e2e.local")
E2E_PASSWORD = os.environ.get("RIHRP_E2E_PASSWORD", "e2e-password-123")

os.environ.update(
    RIHRP_ENV="test",
    RIHRP_DATABASE_URL=TEST_DB_URL,
    RIHRP_MIGRATION_DATABASE_URL=TEST_DB_URL,
    RIHRP_SEED_DEMO="false",
    RIHRP_COOKIE_SECURE="false",
    RIHRP_TRUST_CF_ACCESS="false",
)
sys.path.insert(0, str(REPO / "apps/api"))

from sqlalchemy import create_engine, select, text  # noqa: E402

from rihrp.db import SessionLocal  # noqa: E402
from rihrp.models import User  # noqa: E402
from rihrp.security import hash_password  # noqa: E402


def migrate() -> None:
    env = os.environ.copy()
    env["RIHRP_DATABASE_URL"] = TEST_DB_URL
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=REPO / "infra/migrations",
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )


def reset() -> None:
    engine = create_engine(TEST_DB_URL, pool_pre_ping=True)
    with engine.begin() as connection:
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
    engine.dispose()


def seed_user() -> None:
    with SessionLocal() as db:
        existing = db.execute(select(User).where(User.email == E2E_EMAIL)).scalar_one_or_none()
        if existing is not None:
            existing.password_hash = hash_password(E2E_PASSWORD)
            existing.role = "admin"
            existing.is_active = True
        else:
            db.add(
                User(
                    email=E2E_EMAIL,
                    name="E2E Admin",
                    role="admin",
                    password_hash=hash_password(E2E_PASSWORD),
                )
            )
        db.commit()


def main() -> None:
    migrate()
    reset()
    seed_user()
    print(f"e2e db ready: {E2E_EMAIL}")


if __name__ == "__main__":
    main()
