"""006_attachment_lifecycle_and_ai_metadata

Phase 3 Remediation:
1. Adds status column to complaint_attachments (PENDING, UPLOADED, FAILED)
2. Adds ai_status, ai_reasoning, ai_provider, ai_model, ai_processed_at to complaints

Revision ID: 006_attachment_lifecycle
Revises: 005_complaints_domain
Create Date: 2026-11-04 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "006_attachment_lifecycle"
down_revision: str | None = "005_complaints_domain"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add status column to complaint_attachments
    op.add_column(
        "complaint_attachments",
        sa.Column("status", sa.String(length=32), server_default="UPLOADED", nullable=False),
    )

    # 2. Add AI metadata columns to complaints
    op.add_column(
        "complaints",
        sa.Column("ai_status", sa.String(length=32), server_default="PENDING", nullable=False),
    )
    op.add_column(
        "complaints",
        sa.Column("ai_reasoning", sa.Text(), nullable=True),
    )
    op.add_column(
        "complaints",
        sa.Column("ai_provider", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "complaints",
        sa.Column("ai_model", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "complaints",
        sa.Column("ai_processed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("complaints", "ai_processed_at")
    op.drop_column("complaints", "ai_model")
    op.drop_column("complaints", "ai_provider")
    op.drop_column("complaints", "ai_reasoning")
    op.drop_column("complaints", "ai_status")
    op.drop_column("complaint_attachments", "status")
