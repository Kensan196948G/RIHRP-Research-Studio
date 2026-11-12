"""レポートに AI 支援の自己申告フラグを追加する。

Revision ID: 0005_reports_ai_assisted
Revises: 0004_research_documents
Create Date: 2026-11-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_reports_ai_assisted"
down_revision: str | None = "0004_research_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "reports",
        sa.Column(
            "ai_assisted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("reports", "ai_assisted")
