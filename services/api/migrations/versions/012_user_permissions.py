"""012_user_permissions

Phase 5 Hardening: Granular User Permissions Table.
Supports explicitly assigned operational and reporting permissions (e.g. COMMITTEE_REPORT_READ)
for selected staff while maintaining strictly two application roles (RESIDENT and HELPDESK).

Revision ID: 012_user_permissions
Revises: 011_phase5_core_governance
Create Date: 2026-11-06 14:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "012_user_permissions"
down_revision: str | None = "011_phase5_core_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 1. Create user_permissions table
    op.create_table(
        "user_permissions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "society_id",
            sa.Uuid(),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("permission", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id", "society_id", "permission", name="uq_user_society_permission"
        ),
    )
    op.create_index("ix_user_permissions_lookup", "user_permissions", ["user_id", "permission"])

    if is_postgres:
        op.execute("ALTER TABLE user_permissions ENABLE ROW LEVEL SECURITY;")
        op.execute("ALTER TABLE user_permissions FORCE ROW LEVEL SECURITY;")
        op.execute("GRANT SELECT ON user_permissions TO authenticated;")
        op.execute("GRANT ALL ON user_permissions TO service_role;")

        # Authenticated user can read own permissions
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'user_permissions' AND policyname = 'user_permissions_read_own') THEN
                    CREATE POLICY user_permissions_read_own ON user_permissions
                    FOR SELECT TO authenticated
                    USING (user_id IN (SELECT id FROM users WHERE supabase_uid = auth.uid()));
                END IF;
            END $$;
            """
        )

        # Helpdesk can read permissions in their assigned society
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'user_permissions' AND policyname = 'user_permissions_helpdesk_read') THEN
                    CREATE POLICY user_permissions_helpdesk_read ON user_permissions
                    FOR SELECT TO authenticated
                    USING (public.is_helpdesk_for_society(society_id));
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("DROP POLICY IF EXISTS user_permissions_read_own ON user_permissions;")
        op.execute("DROP POLICY IF EXISTS user_permissions_helpdesk_read ON user_permissions;")

    op.drop_table("user_permissions")
