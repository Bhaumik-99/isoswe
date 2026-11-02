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
        # Enable RLS on all tables and grant full access to backend service_role
        for tbl in tables:
            op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;")
            op.execute(f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_policies WHERE tablename = '{tbl}' AND policyname = '{tbl}_service_role_policy'
                    ) THEN
                        CREATE POLICY {tbl}_service_role_policy ON {tbl}
                        FOR ALL
                        TO service_role
                        USING (true)
                        WITH CHECK (true);
                    END IF;
                END
                $$;
            """)

        # Tenant-scoped policies for authenticated users
        # 2a. Users: authenticated user can only view and update their own user record
        op.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'users' AND policyname = 'users_authenticated_select') THEN
                    CREATE POLICY users_authenticated_select ON users
                    FOR SELECT TO authenticated
                    USING (supabase_uid = auth.uid());
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'users' AND policyname = 'users_authenticated_update') THEN
                    CREATE POLICY users_authenticated_update ON users
                    FOR UPDATE TO authenticated
                    USING (supabase_uid = auth.uid())
                    WITH CHECK (supabase_uid = auth.uid());
                END IF;
            END $$;
        """)

        # 2b. Flat Memberships: authenticated user can only view their own memberships
        op.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'flat_memberships' AND policyname = 'flat_memberships_authenticated_select') THEN
                    CREATE POLICY flat_memberships_authenticated_select ON flat_memberships
                    FOR SELECT TO authenticated
                    USING (user_id IN (SELECT id FROM users WHERE supabase_uid = auth.uid()));
                END IF;
            END $$;
        """)

        # 2c. Flats: authenticated resident can only view flats where they have approved membership
        op.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'flats' AND policyname = 'flats_authenticated_select') THEN
                    CREATE POLICY flats_authenticated_select ON flats
                    FOR SELECT TO authenticated
                    USING (
                        id IN (
                            SELECT flat_id FROM flat_memberships
                            WHERE user_id IN (SELECT id FROM users WHERE supabase_uid = auth.uid())
                            AND status = 'APPROVED'
                        )
                    );
                END IF;
            END $$;
        """)

        # 2d. Towers: authenticated resident can only view towers containing their approved flats
        op.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'towers' AND policyname = 'towers_authenticated_select') THEN
                    CREATE POLICY towers_authenticated_select ON towers
                    FOR SELECT TO authenticated
                    USING (
                        id IN (
                            SELECT tower_id FROM flats
                            WHERE id IN (
                                SELECT flat_id FROM flat_memberships
                                WHERE user_id IN (SELECT id FROM users WHERE supabase_uid = auth.uid())
                                AND status = 'APPROVED'
                            )
                        )
                    );
                END IF;
            END $$;
        """)

        # 2e. Societies: authenticated resident can only view societies containing their approved flats
        op.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'societies' AND policyname = 'societies_authenticated_select') THEN
                    CREATE POLICY societies_authenticated_select ON societies
                    FOR SELECT TO authenticated
                    USING (
                        id IN (
                            SELECT society_id FROM flats
                            WHERE id IN (
                                SELECT flat_id FROM flat_memberships
                                WHERE user_id IN (SELECT id FROM users WHERE supabase_uid = auth.uid())
                                AND status = 'APPROVED'
                            )
                        )
                    );
                END IF;
            END $$;
        """)

        # 2f. Application profile view aliasing users for Supabase dashboard integration
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
        # Drop tenant-scoped authenticated policies
        op.execute("DROP POLICY IF EXISTS users_authenticated_select ON users;")
        op.execute("DROP POLICY IF EXISTS users_authenticated_update ON users;")
        op.execute(
            "DROP POLICY IF EXISTS flat_memberships_authenticated_select ON flat_memberships;"
        )
        op.execute("DROP POLICY IF EXISTS flats_authenticated_select ON flats;")
        op.execute("DROP POLICY IF EXISTS towers_authenticated_select ON towers;")
        op.execute("DROP POLICY IF EXISTS societies_authenticated_select ON societies;")

        for tbl in tables:
            op.execute(f"DROP POLICY IF EXISTS {tbl}_service_role_policy ON {tbl};")
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
