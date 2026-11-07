"""018_official_township_notices

Provisions official township notices & circulars:
1. notices: Official federation circulars, power/water maintenance advisories, and emergency announcements.
2. notice_reads: Per-resident read/unread state tracking.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "018_official_township_notices"
down_revision: str | None = "017_amenity_blocks_and_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
    op.execute(f"GRANT SELECT ON {table} TO authenticated;")
    op.execute(f"GRANT ALL ON {table} TO service_role;")
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE tablename = '{table}' AND policyname = '{table}_service_role_policy'
            ) THEN
                CREATE POLICY {table}_service_role_policy ON {table}
                FOR ALL TO service_role
                USING (true) WITH CHECK (true);
            END IF;
        END $$;
        """
    )


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 1. notices table
    op.create_table(
        "notices",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False, server_default="GENERAL"),
        sa.Column("priority", sa.String(length=32), nullable=False, server_default="NORMAL"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("target_type", sa.String(length=32), nullable=False, server_default="SOCIETY"),
        sa.Column(
            "target_tower_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("towers.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "target_flat_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("flats.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "author_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_notices_society_status", "notices", ["society_id", "status"])
    op.create_index("ix_notices_society_published", "notices", ["society_id", "published_at"])
    op.create_index(
        "ix_notices_society_target",
        "notices",
        ["society_id", "target_type", "target_tower_id", "target_flat_id"],
    )
    op.create_index(
        "ix_notices_pinned_published",
        "notices",
        ["society_id", "is_pinned", "published_at"],
    )

    # 2. notice_reads table
    op.create_table(
        "notice_reads",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "notice_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("notices.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "read_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("notice_id", "user_id", name="uq_notice_reads_notice_user"),
    )
    op.create_index("ix_notice_reads_user_notice", "notice_reads", ["user_id", "notice_id"])

    if is_postgres:
        _enable_rls("notices")
        _enable_rls("notice_reads")


def downgrade() -> None:
    op.drop_table("notice_reads")
    op.drop_table("notices")
