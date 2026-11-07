"""019_notice_multi_targeting

Expands official township notices to support multi-tower and multi-flat targeting:
1. notices: Adds JSON array columns target_tower_ids and target_flat_ids.
2. notice_targets: Normalized table for multi-tower and multi-flat indexing and query predicates.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "019_notice_multi_targeting"
down_revision: str | None = "018_official_township_notices"
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

    # 1. Add target_tower_ids and target_flat_ids JSON columns to notices
    op.add_column(
        "notices",
        sa.Column("target_tower_ids", sa.JSON(), nullable=True, server_default="[]"),
    )
    op.add_column(
        "notices",
        sa.Column("target_flat_ids", sa.JSON(), nullable=True, server_default="[]"),
    )

    # 2. Create notice_targets normalized mapping table
    op.create_table(
        "notice_targets",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "notice_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("notices.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.Uuid(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "notice_id", "target_type", "target_id", name="uq_notice_targets_unique"
        ),
    )
    op.create_index("ix_notice_targets_lookup", "notice_targets", ["target_type", "target_id"])

    if is_postgres:
        _enable_rls("notice_targets")


def downgrade() -> None:
    op.drop_index("ix_notice_targets_lookup", table_name="notice_targets")
    op.drop_table("notice_targets")
    op.drop_column("notices", "target_flat_ids")
    op.drop_column("notices", "target_tower_ids")
