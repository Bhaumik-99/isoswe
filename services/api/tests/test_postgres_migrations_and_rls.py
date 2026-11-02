"""PostgreSQL Integration Tests: Migrations, Rollback, and Row-Level Security (RLS) Policies

Validates against live PostgreSQL database:
1. Migration from an empty PostgreSQL database (001 -> 002).
2. Upgrade with pre-existing user records (populating supabase_uid).
3. RLS policy execution using the 'authenticated' Supabase role.
4. Tenant isolation and cross-society access denial.
5. Expired tenant lease access denial (valid_until < CURRENT_TIMESTAMP).
6. Unauthorized user profile updates rejected (users_authenticated_update removed).
7. Profile view with security_invoker = true enforcement.
8. Full database rollback and migration downgrade to base.
"""

import os
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect, text

POSTGRES_BASE_URL = os.environ.get(
    "TEST_POSTGRES_URL",
    "postgresql://postgres:postgres@localhost:5432/postgres",
)
TEST_DB_NAME = "township_ops_rls_integration_test"
TEST_DB_URL = f"postgresql+psycopg://postgres:postgres@localhost:5432/{TEST_DB_NAME}"


def is_postgres_available() -> bool:
    try:
        conn = psycopg.connect(POSTGRES_BASE_URL, connect_timeout=3)
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not is_postgres_available(),
    reason="PostgreSQL container is not reachable on localhost:5432",
)


@pytest.fixture(scope="module")
def postgres_test_db() -> Generator[Engine, None, None]:
    """Sets up a dedicated PostgreSQL database for Alembic and RLS testing, and tears it down afterwards."""
    conn = psycopg.connect(POSTGRES_BASE_URL, autocommit=True)
    with conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB_NAME};")
        cur.execute(f"CREATE DATABASE {TEST_DB_NAME};")
    conn.close()

    # Configure auth schema and mock auth.uid() function in the test DB
    test_conn = psycopg.connect(
        f"postgresql://postgres:postgres@localhost:5432/{TEST_DB_NAME}",
        autocommit=True,
    )
    with test_conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS auth;")
        cur.execute(
            "CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid AS "
            "'SELECT NULLIF(current_setting(''request.jwt.claim.sub'', true), '''')::uuid;' "
            "LANGUAGE sql STABLE;"
        )
        cur.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                    CREATE ROLE authenticated;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
                    CREATE ROLE service_role;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                    CREATE ROLE anon;
                END IF;
            END $$;
            """
        )
        # Grant usage so authenticated role can query public schema
        cur.execute("GRANT USAGE ON SCHEMA public TO authenticated;")
        cur.execute("GRANT USAGE ON SCHEMA public TO service_role;")
        cur.execute("GRANT USAGE ON SCHEMA auth TO authenticated;")
        cur.execute("GRANT USAGE ON SCHEMA auth TO service_role;")
    test_conn.close()

    engine = create_engine(TEST_DB_URL)
    yield engine
    engine.dispose()

    # Teardown
    cleanup_conn = psycopg.connect(POSTGRES_BASE_URL, autocommit=True)
    with cleanup_conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB_NAME};")
    cleanup_conn.close()


def test_postgres_empty_migration_upgrade_and_downgrade(postgres_test_db: Engine) -> None:
    """Verifies Alembic migration from an empty PostgreSQL database, upgrade with existing records, and clean downgrade."""
    engine = postgres_test_db
    api_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    alembic_cfg = Config(os.path.join(api_dir, "alembic.ini"))
    alembic_cfg.set_main_option("script_location", os.path.join(api_dir, "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DB_URL)

    with engine.connect() as connection:
        alembic_cfg.attributes["connection"] = connection

        # 1. Migrate to initial schema (001)
        command.upgrade(alembic_cfg, "001_initial_schema")
        connection.commit()

        # 2. Insert a pre-existing user record with legacy cognito_sub
        legacy_uid = str(uuid.uuid4())
        connection.execute(
            text(
                """
                INSERT INTO societies (id, name, timezone, preferred_currency, status, created_at, updated_at)
                VALUES (:soc_id, 'Pre-Migration Society', 'Asia/Kolkata', 'INR', 'ACTIVE', NOW(), NOW());
                """
            ),
            {"soc_id": legacy_uid},
        )
        connection.execute(
            text(
                """
                INSERT INTO users (id, cognito_sub, email, phone, full_name, status, created_at, updated_at)
                VALUES (gen_random_uuid(), 'cognito-legacy-sub-1234', 'legacy@township.example.com', '+919999900001', 'Legacy User', 'ACTIVE', NOW(), NOW());
                """
            )
        )
        connection.commit()

        # 3. Upgrade to 002 (adds supabase_uid, sets RLS policies and profiles view)
        command.upgrade(alembic_cfg, "head")
        connection.commit()

        # Verify supabase_uid column exists and is populated for the pre-existing record
        user_row = connection.execute(
            text("SELECT id, supabase_uid, email FROM users WHERE email = 'legacy@township.example.com'")
        ).fetchone()
        assert user_row is not None
        assert user_row.supabase_uid is not None

        # Verify profiles view exists and is queryable
        view_row = connection.execute(
            text("SELECT id, supabase_uid, email FROM profiles WHERE email = 'legacy@township.example.com'")
        ).fetchone()
        assert view_row is not None

        # 4. Verify clean downgrade rollback
        command.downgrade(alembic_cfg, "base")
        connection.commit()

        inspector = inspect(connection)
        tables = inspector.get_table_names()
        assert "societies" not in tables
        assert "users" not in tables
        assert "profiles" not in inspector.get_view_names()

        # 5. Re-upgrade to head for RLS testing
        command.upgrade(alembic_cfg, "head")
        connection.commit()


def test_postgres_rls_tenant_isolation_and_expired_lease_denial(postgres_test_db: Engine) -> None:
    """Verifies PostgreSQL RLS enforcement:
    - User can only SELECT their own user row
    - Direct UPDATE by authenticated user is rejected
    - Authenticated user can only SELECT flats with APPROVED unexpired lease
    - Expired tenant is denied access to flat/tower/society
    - Cross-society resident cannot access foreign flats
    """
    engine = postgres_test_db

    # Grant SELECT on all tables to authenticated role so RLS controls visibility
    with engine.connect() as conn:
        conn.execute(text("GRANT SELECT ON ALL TABLES IN SCHEMA public TO authenticated;"))
        conn.commit()

    # Generate test UUIDs
    soc_a_id = uuid.uuid4()
    soc_b_id = uuid.uuid4()
    tower_a_id = uuid.uuid4()
    tower_b_id = uuid.uuid4()
    flat_active_id = uuid.uuid4()
    flat_expired_id = uuid.uuid4()
    flat_b_id = uuid.uuid4()

    user_active_uid = uuid.uuid4()
    user_expired_uid = uuid.uuid4()
    user_b_uid = uuid.uuid4()

    user_active_id = uuid.uuid4()
    user_expired_id = uuid.uuid4()
    user_b_id = uuid.uuid4()

    now = datetime.now(UTC)
    yesterday = now - timedelta(days=1)
    last_year = now - timedelta(days=365)
    next_year = now + timedelta(days=365)

    with engine.connect() as conn:
        # Insert Societies
        conn.execute(
            text(
                "INSERT INTO societies (id, name, timezone, preferred_currency, status, created_at, updated_at) "
                "VALUES (:id_a, 'Society Alpha', 'Asia/Kolkata', 'INR', 'ACTIVE', NOW(), NOW()), "
                "       (:id_b, 'Society Beta', 'Asia/Kolkata', 'INR', 'ACTIVE', NOW(), NOW());"
            ),
            {"id_a": soc_a_id, "id_b": soc_b_id},
        )

        # Insert Towers
        conn.execute(
            text(
                "INSERT INTO towers (id, society_id, tower_number, name, created_at) "
                "VALUES (:t_a, :soc_a, 'T01', 'Tower Alpha 1', NOW()), "
                "       (:t_b, :soc_b, 'T02', 'Tower Beta 1', NOW());"
            ),
            {"t_a": tower_a_id, "soc_a": soc_a_id, "t_b": tower_b_id, "soc_b": soc_b_id},
        )

        # Insert Flats
        conn.execute(
            text(
                "INSERT INTO flats (id, society_id, tower_id, flat_number, area_sqft, status, created_at, updated_at) "
                "VALUES (:f_act, :soc_a, :t_a, '101', 1150, 'OCCUPIED', NOW(), NOW()), "
                "       (:f_exp, :soc_a, :t_a, '102', 980, 'OCCUPIED', NOW(), NOW()), "
                "       (:f_b, :soc_b, :t_b, '201', 1640, 'OCCUPIED', NOW(), NOW());"
            ),
            {
                "f_act": flat_active_id,
                "f_exp": flat_expired_id,
                "f_b": flat_b_id,
                "soc_a": soc_a_id,
                "soc_b": soc_b_id,
                "t_a": tower_a_id,
                "t_b": tower_b_id,
            },
        )

        # Insert Users
        conn.execute(
            text(
                "INSERT INTO users (id, supabase_uid, email, phone, full_name, status, created_at, updated_at) "
                "VALUES (:u1, :sub1, 'active@example.com', '+919876500001', 'Active Resident', 'ACTIVE', NOW(), NOW()), "
                "       (:u2, :sub2, 'expired@example.com', '+919876500002', 'Expired Tenant', 'ACTIVE', NOW(), NOW()), "
                "       (:u3, :sub3, 'b@example.com', '+919876500003', 'Beta Resident', 'ACTIVE', NOW(), NOW());"
            ),
            {
                "u1": user_active_id,
                "sub1": user_active_uid,
                "u2": user_expired_id,
                "sub2": user_expired_uid,
                "u3": user_b_id,
                "sub3": user_b_uid,
            },
        )

        # Insert Flat Memberships:
        # User 1: Active approved membership (valid_until = next year)
        # User 2: Expired membership (valid_until = yesterday)
        # User 3: Active in Society B
        conn.execute(
            text(
                "INSERT INTO flat_memberships (id, society_id, user_id, flat_id, membership_type, status, valid_from, valid_until, is_primary, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :soc_a, :u1, :f_act, 'OWNER', 'APPROVED', :last_year, :next_year, true, NOW(), NOW()), "
                "       (gen_random_uuid(), :soc_a, :u2, :f_exp, 'TENANT', 'APPROVED', :last_year, :yesterday, true, NOW(), NOW()), "
                "       (gen_random_uuid(), :soc_b, :u3, :f_b, 'OWNER', 'APPROVED', :last_year, :next_year, true, NOW(), NOW());"
            ),
            {
                "soc_a": soc_a_id,
                "soc_b": soc_b_id,
                "u1": user_active_id,
                "f_act": flat_active_id,
                "u2": user_expired_id,
                "f_exp": flat_expired_id,
                "u3": user_b_id,
                "f_b": flat_b_id,
                "last_year": last_year,
                "yesterday": yesterday,
                "next_year": next_year,
            },
        )
        conn.commit()

    # -------------------------------------------------------------
    # Scenario 1: User 1 (Active Resident) queries under 'authenticated' role
    # -------------------------------------------------------------
    with engine.connect() as conn:
        conn.execute(text("SET ROLE authenticated;"))
        conn.execute(text(f"SET request.jwt.claim.sub = '{user_active_uid}';"))

        # 1a. User isolation: can only view own user row
        users_visible = conn.execute(text("SELECT id, email FROM users;")).fetchall()
        assert len(users_visible) == 1
        assert users_visible[0].id == user_active_id

        # 1b. Profiles view respects security_invoker = true
        profiles_visible = conn.execute(text("SELECT id, email FROM profiles;")).fetchall()
        assert len(profiles_visible) == 1
        assert profiles_visible[0].id == user_active_id

        # 1c. Direct UPDATE is blocked (users_authenticated_update was safely removed)
        update_failed = False
        try:
            conn.execute(text(f"UPDATE users SET full_name = 'Hacked' WHERE id = '{user_active_id}';"))
        except Exception:
            update_failed = True
            conn.rollback()
            conn.execute(text("SET ROLE authenticated;"))
            conn.execute(text(f"SET request.jwt.claim.sub = '{user_active_uid}';"))
        assert update_failed, "UPDATE on users by authenticated role must be rejected"

        # 1d. Can only view Flat 101 (own flat). Flat 102 (other flat) and 201 (other society) are excluded
        flats_visible = conn.execute(text("SELECT id, flat_number FROM flats;")).fetchall()
        assert len(flats_visible) == 1
        assert flats_visible[0].id == flat_active_id

        # 1e. Society isolation: can only view Society Alpha, not Society Beta
        societies_visible = conn.execute(text("SELECT id, name FROM societies;")).fetchall()
        assert len(societies_visible) == 1
        assert societies_visible[0].id == soc_a_id

    # -------------------------------------------------------------
    # Scenario 2: User 2 (Expired Tenant) queries under 'authenticated' role
    # -------------------------------------------------------------
    with engine.connect() as conn:
        conn.execute(text("SET ROLE authenticated;"))
        conn.execute(text(f"SET request.jwt.claim.sub = '{user_expired_uid}';"))

        # User row is visible to themselves
        users_visible = conn.execute(text("SELECT id FROM users;")).fetchall()
        assert len(users_visible) == 1
        assert users_visible[0].id == user_expired_id

        # BUT expired lease denies access to flats via RLS:
        flats_visible = conn.execute(text("SELECT id FROM flats;")).fetchall()
        assert len(flats_visible) == 0, "Expired tenant must not see any flat records"

        towers_visible = conn.execute(text("SELECT id FROM towers;")).fetchall()
        assert len(towers_visible) == 0, "Expired tenant must not see any tower records"

        societies_visible = conn.execute(text("SELECT id FROM societies;")).fetchall()
        assert len(societies_visible) == 0, "Expired tenant must not see any society records"

    # -------------------------------------------------------------
    # Scenario 3: User 3 (Society Beta) queries under 'authenticated' role
    # -------------------------------------------------------------
    with engine.connect() as conn:
        conn.execute(text("SET ROLE authenticated;"))
        conn.execute(text(f"SET request.jwt.claim.sub = '{user_b_uid}';"))

        flats_visible = conn.execute(text("SELECT id, flat_number FROM flats;")).fetchall()
        assert len(flats_visible) == 1
        assert flats_visible[0].id == flat_b_id

        societies_visible = conn.execute(text("SELECT id FROM societies;")).fetchall()
        assert len(societies_visible) == 1
        assert societies_visible[0].id == soc_b_id
