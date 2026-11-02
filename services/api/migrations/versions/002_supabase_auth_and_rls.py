"""002_supabase_auth_and_rls

Migrates authentication identity to Supabase Auth UUID (supabase_uid),
relaxes email uniqueness/nullability for Phone OTP auth,
and applies Row-Level Security (RLS) policies for Supabase PostgreSQL.

Revision ID: 002_supabase_auth_and_rls
Revises: 001_initial_schema
Create Date: 2026-11-03 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002_supabase_auth_and_rls"
down_revision: str | None = "001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Update users table: replace cognito_sub with supabase_uid UUID and make email nullable
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("supabase_uid", sa.Uuid(), nullable=True))
        batch_op.alter_column("email", existing_type=sa.String(length=255), nullable=True)

    # Populate dummy UUID for any existing rows if present
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("UPDATE users SET supabase_uid = gen_random_uuid() WHERE supabase_uid IS NULL;")
    else:
        op.execute(
            "UPDATE users SET supabase_uid = '00000000-0000-0000-0000-000000000000' WHERE supabase_uid IS NULL;"
        )

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column("supabase_uid", nullable=False)
        batch_op.create_unique_constraint("uq_users_supabase_uid", ["supabase_uid"])
        batch_op.create_index("ix_users_supabase_uid", ["supabase_uid"])
        # Drop legacy cognito_sub index and column
        batch_op.drop_index("ix_users_cognito_sub")
        batch_op.drop_column("cognito_sub")

    # 2. Supabase PostgreSQL Row Level Security (RLS) & Profile View
    if bind.dialect.name == "postgresql":
        tables = [
            "societies",
            "towers",
            "flats",
            "users",
            "flat_memberships",
            "user_roles",
            "audit_events",
            "outbox_events",
            "idempotency_keys",
            "processed_events",
        ]
        for tbl in tables:
            op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;")
            op.execute(f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_policies WHERE tablename = '{tbl}' AND policyname = '{tbl}_service_policy'
                    ) THEN
                        CREATE POLICY {tbl}_service_policy ON {tbl}
                        FOR ALL
                        TO authenticated, service_role
                        USING (true)
                        WITH CHECK (true);
                    END IF;
                END
                $$;
            """)

        # Application profile view aliasing users for Supabase dashboard integration
        op.execute("""
            CREATE OR REPLACE VIEW profiles AS
            SELECT id, supabase_uid, email, phone, full_name, status, created_at, updated_at
            FROM users;
        """)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP VIEW IF EXISTS profiles;")
        tables = [
            "societies",
            "towers",
            "flats",
            "users",
            "flat_memberships",
            "user_roles",
            "audit_events",
            "outbox_events",
            "idempotency_keys",
            "processed_events",
        ]
        for tbl in tables:
            op.execute(f"DROP POLICY IF EXISTS {tbl}_service_policy ON {tbl};")
            op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY;")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("cognito_sub", sa.String(length=128), nullable=True))

    op.execute("UPDATE users SET cognito_sub = 'legacy-cognito-sub' WHERE cognito_sub IS NULL;")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column("cognito_sub", nullable=False)
        batch_op.create_unique_constraint("uq_users_cognito_sub", ["cognito_sub"])
        batch_op.create_index("ix_users_cognito_sub", ["cognito_sub"])
        batch_op.drop_index("ix_users_supabase_uid")
        batch_op.drop_column("supabase_uid")
