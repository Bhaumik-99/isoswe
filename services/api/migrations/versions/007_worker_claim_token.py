"""007_worker_claim_token

Phase 3 Reliability Hardening:
Adds ai_claim_token to complaints for worker lease ownership fencing.
Each Phase-1 claim writes a unique UUID token; Phase-3 only commits
its result when the stored token still matches, preventing stale workers
from overwriting a successful result written by a faster competing worker.

Revision ID: 007_worker_claim_token
Revises: 006_attachment_lifecycle
Create Date: 2026-11-05 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "007_worker_claim_token"
down_revision: str | None = "006_attachment_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "complaints",
        sa.Column("ai_claim_token", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("complaints", "ai_claim_token")
