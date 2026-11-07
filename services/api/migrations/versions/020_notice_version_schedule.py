"""020_notice_version_schedule

Expands official township notices schema:
1. notices.version: Monotonically increasing revision number for publication and audit versioning.
2. notices.deliver_emergency: Flag indicating whether notice is designated for multi-channel emergency broadcast.
3. Index ix_notices_status_published_at: Optimizes background worker queries for scheduled notice publication.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "020_notice_version_schedule"
down_revision: str | None = "019_notice_multi_targeting"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add version column to notices
    op.add_column(
        "notices",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )

    # 2. Add deliver_emergency column to notices
    op.add_column(
        "notices",
        sa.Column("deliver_emergency", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # 3. Add compound index on status and published_at for worker polling efficiency
    op.create_index(
        "ix_notices_status_published_at",
        "notices",
        ["status", "published_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notices_status_published_at", table_name="notices")
    op.drop_column("notices", "deliver_emergency")
    op.drop_column("notices", "version")
