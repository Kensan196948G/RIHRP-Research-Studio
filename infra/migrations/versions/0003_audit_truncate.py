"""audit_events の TRUNCATE も拒否する

Revision ID: 0003_audit_truncate
Revises: 0002_audit_immutable
Create Date: 2026-11-03
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_audit_truncate"
down_revision: str | None = "0002_audit_immutable"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TRIGGER trg_audit_no_truncate
        BEFORE TRUNCATE ON audit_events
        FOR EACH STATEMENT EXECUTE FUNCTION rihrp_audit_immutable();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_no_truncate ON audit_events;")
