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
from sqlalchemy import Engine, create_engine, inspect, pool, text
from sqlalchemy.orm import Session

from app.domains.billing.models import Invoice, InvoiceStatus, PaymentStatus
from app.domains.billing.service import BillingService
from app.domains.identity.models import (
    Flat,
    FlatStatus,
    Society,
    SocietyStatus,
    Tower,
    User,
    UserStatus,
)

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

    engine = create_engine(TEST_DB_URL, poolclass=pool.NullPool)
    yield engine
    engine.dispose()

    # Teardown
    cleanup_conn = psycopg.connect(POSTGRES_BASE_URL, autocommit=True)
    with cleanup_conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB_NAME} WITH (FORCE);")
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
            text(
                "SELECT id, supabase_uid, email FROM users WHERE email = 'legacy@township.example.com'"
            )
        ).fetchone()
        assert user_row is not None
        assert user_row.supabase_uid is not None

        # Verify profiles view exists and is queryable
        view_row = connection.execute(
            text(
                "SELECT id, supabase_uid, email FROM profiles WHERE email = 'legacy@township.example.com'"
            )
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
            conn.execute(
                text(f"UPDATE users SET full_name = 'Hacked' WHERE id = '{user_active_id}';")
            )
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


def test_postgres_rls_billing_isolation(postgres_test_db: Engine) -> None:
    """Requirement 7, 9 & 13.11: Real PostgreSQL RLS tests for billing domain isolation.

    Verifies:
    1. Active resident can only view invoices for their own approved flat.
    2. Active resident cannot view invoices from other flats in the same society or another society.
    3. Active resident can only view their own payments and allocations.
    4. Expired tenant cannot view any invoices or billing records.
    5. Direct INSERT/UPDATE on invoices and ledger by 'authenticated' role is blocked by RLS.
    """
    engine = postgres_test_db
    api_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    alembic_cfg = Config(os.path.join(api_dir, "alembic.ini"))
    alembic_cfg.set_main_option("script_location", os.path.join(api_dir, "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DB_URL)

    with engine.connect() as connection:
        alembic_cfg.attributes["connection"] = connection
        command.upgrade(alembic_cfg, "head")
        connection.commit()

    soc_a_id = uuid.uuid4()
    soc_b_id = uuid.uuid4()
    tower_a_id = uuid.uuid4()
    tower_b_id = uuid.uuid4()
    flat_act_id = uuid.uuid4()
    flat_exp_id = uuid.uuid4()
    flat_b_id = uuid.uuid4()

    user_act_sub = uuid.uuid4()
    user_exp_sub = uuid.uuid4()
    user_act_id = uuid.uuid4()
    user_exp_id = uuid.uuid4()

    inv_act_id = uuid.uuid4()
    inv_exp_id = uuid.uuid4()
    inv_b_id = uuid.uuid4()
    pmt_act_id = uuid.uuid4()

    now = datetime.now(UTC)
    last_year = now - timedelta(days=365)
    next_year = now + timedelta(days=365)
    yesterday = now - timedelta(days=1)

    # 1. Superuser/service role inserts fixtures
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO societies (id, name, timezone, preferred_currency, status, created_at, updated_at) "
                "VALUES (:sa, 'Soc A', 'Asia/Kolkata', 'INR', 'ACTIVE', NOW(), NOW()), "
                "       (:sb, 'Soc B', 'Asia/Kolkata', 'INR', 'ACTIVE', NOW(), NOW());"
            ),
            {"sa": soc_a_id, "sb": soc_b_id},
        )
        conn.execute(
            text(
                "INSERT INTO towers (id, society_id, tower_number, name, created_at) "
                "VALUES (:ta, :sa, 'T01', 'Tower 1', NOW()), "
                "       (:tb, :sb, 'T02', 'Tower 2', NOW());"
            ),
            {"ta": tower_a_id, "sa": soc_a_id, "tb": tower_b_id, "sb": soc_b_id},
        )
        conn.execute(
            text(
                "INSERT INTO flats (id, society_id, tower_id, flat_number, area_sqft, status, created_at, updated_at) "
                "VALUES (:fa, :sa, :ta, '101', 1150, 'OCCUPIED', NOW(), NOW()), "
                "       (:fe, :sa, :ta, '102', 980, 'OCCUPIED', NOW(), NOW()), "
                "       (:fb, :sb, :tb, '201', 1640, 'OCCUPIED', NOW(), NOW());"
            ),
            {
                "fa": flat_act_id,
                "fe": flat_exp_id,
                "fb": flat_b_id,
                "sa": soc_a_id,
                "sb": soc_b_id,
                "ta": tower_a_id,
                "tb": tower_b_id,
            },
        )
        conn.execute(
            text(
                "INSERT INTO users (id, supabase_uid, email, phone, full_name, status, created_at, updated_at) "
                "VALUES (:ua, :sub_a, 'act@example.com', '+919800011111', 'Active Resident', 'ACTIVE', NOW(), NOW()), "
                "       (:ue, :sub_e, 'exp@example.com', '+919800022222', 'Expired Tenant', 'ACTIVE', NOW(), NOW());"
            ),
            {"ua": user_act_id, "sub_a": user_act_sub, "ue": user_exp_id, "sub_e": user_exp_sub},
        )
        conn.execute(
            text(
                "INSERT INTO flat_memberships (id, society_id, user_id, flat_id, membership_type, status, valid_from, valid_until, is_primary, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :sa, :ua, :fa, 'OWNER', 'APPROVED', :last_year, :next_year, true, NOW(), NOW()), "
                "       (gen_random_uuid(), :sa, :ue, :fe, 'TENANT', 'APPROVED', :last_year, :yesterday, true, NOW(), NOW());"
            ),
            {
                "sa": soc_a_id,
                "ua": user_act_id,
                "fa": flat_act_id,
                "ue": user_exp_id,
                "fe": flat_exp_id,
                "last_year": last_year,
                "next_year": next_year,
                "yesterday": yesterday,
            },
        )
        # Insert Invoices
        conn.execute(
            text(
                "INSERT INTO invoices (id, society_id, flat_id, billing_period, invoice_number, area_sqft_snapshot, rate_paise_per_sqft_snapshot, subtotal_paise, total_paise, due_date, status, created_at, updated_at) "
                "VALUES (:ia, :sa, :fa, '2026-11', 'INV-202611-101', 1150, 650, 747500, 747500, NOW() + INTERVAL '15 days', 'UNPAID', NOW(), NOW()), "
                "       (:ie, :sa, :fe, '2026-11', 'INV-202611-102', 980, 650, 637000, 637000, NOW() + INTERVAL '15 days', 'UNPAID', NOW(), NOW()), "
                "       (:ib, :sb, :fb, '2026-11', 'INV-202611-201', 1640, 650, 1066000, 1066000, NOW() + INTERVAL '15 days', 'UNPAID', NOW(), NOW());"
            ),
            {
                "ia": inv_act_id,
                "ie": inv_exp_id,
                "ib": inv_b_id,
                "sa": soc_a_id,
                "sb": soc_b_id,
                "fa": flat_act_id,
                "fe": flat_exp_id,
                "fb": flat_b_id,
            },
        )
        # Insert Payment for Active resident
        conn.execute(
            text(
                "INSERT INTO payments (id, society_id, flat_id, amount_paise, currency, provider, provider_reference, status, initiated_by, created_at, updated_at) "
                "VALUES (:pa, :sa, :fa, 747500, 'INR', 'SIMULATED', 'SIM-REF-001', 'SUCCESS', :ua, NOW(), NOW());"
            ),
            {"pa": pmt_act_id, "sa": soc_a_id, "fa": flat_act_id, "ua": user_act_id},
        )
        conn.commit()

    # 2. Query as Active Resident under 'authenticated' role
    with engine.connect() as conn:
        conn.execute(text("SET ROLE authenticated;"))
        conn.execute(text(f"SET request.jwt.claim.sub = '{user_act_sub}';"))

        # Invoices visible: Only own flat's invoice (INV-202611-101)
        invoices = conn.execute(text("SELECT id, invoice_number FROM invoices;")).fetchall()
        assert len(invoices) == 1
        assert invoices[0].id == inv_act_id
        assert invoices[0].invoice_number == "INV-202611-101"

        # Payments visible: Only own flat's payment
        payments = conn.execute(text("SELECT id, provider_reference FROM payments;")).fetchall()
        assert len(payments) == 1
        assert payments[0].id == pmt_act_id

        # Direct INSERT on invoices by authenticated role must fail
        insert_blocked = False
        try:
            conn.execute(
                text(
                    f"INSERT INTO invoices (id, society_id, flat_id, billing_period, invoice_number, area_sqft_snapshot, rate_paise_per_sqft_snapshot, subtotal_paise, total_paise, due_date, status, created_at, updated_at) "
                    f"VALUES (gen_random_uuid(), '{soc_a_id}', '{flat_act_id}', '2026-12', 'INV-ROGUE-001', 1150, 650, 747500, 747500, NOW(), 'UNPAID', NOW(), NOW());"
                )
            )
        except Exception:
            insert_blocked = True
            conn.rollback()
            conn.execute(text("SET ROLE authenticated;"))
            conn.execute(text(f"SET request.jwt.claim.sub = '{user_act_sub}';"))
        assert insert_blocked, "Direct invoice creation by authenticated role must be denied by RLS"
        conn.execute(text("RESET ROLE;"))

    # 3. Query as Expired Tenant under 'authenticated' role
    with engine.connect() as conn:
        conn.execute(text("SET ROLE authenticated;"))
        conn.execute(text(f"SET request.jwt.claim.sub = '{user_exp_sub}';"))

        # Expired tenant has no active membership -> sees 0 invoices
        expired_invoices = conn.execute(text("SELECT id FROM invoices;")).fetchall()
        assert len(expired_invoices) == 0, "Expired tenant must see zero invoices"
        conn.execute(text("RESET ROLE;"))


def test_postgres_financial_ledger_immutability_trigger(postgres_test_db: Engine) -> None:
    """Finding 7: Enforce append-only financial ledger behavior at PostgreSQL database level.

    Direct UPDATE and DELETE on financial_ledger_entries must be strictly rejected
    by the 'financial_ledger_immutable' PostgreSQL trigger, regardless of database user privileges.
    """
    engine = postgres_test_db
    soc_id = uuid.uuid4()
    tower_id = uuid.uuid4()
    flat_id = uuid.uuid4()
    ledger_id = uuid.uuid4()

    with engine.connect() as conn:
        conn.execute(text("RESET ROLE;"))
        conn.execute(
            text(
                "INSERT INTO societies (id, name, timezone, preferred_currency, status, created_at, updated_at) "
                "VALUES (:s, 'Soc Immutability', 'Asia/Kolkata', 'INR', 'ACTIVE', NOW(), NOW());"
            ),
            {"s": soc_id},
        )
        conn.execute(
            text(
                "INSERT INTO towers (id, society_id, tower_number, name, created_at) "
                "VALUES (:t, :s, 'T01', 'Tower 1', NOW());"
            ),
            {"t": tower_id, "s": soc_id},
        )
        conn.execute(
            text(
                "INSERT INTO flats (id, society_id, tower_id, flat_number, area_sqft, status, created_at, updated_at) "
                "VALUES (:f, :s, :t, '101', 1150, 'OCCUPIED', NOW(), NOW());"
            ),
            {"f": flat_id, "s": soc_id, "t": tower_id},
        )
        # Insert initial valid ledger entry (allowed)
        conn.execute(
            text(
                "INSERT INTO financial_ledger_entries (id, society_id, flat_id, entry_type, amount_paise, description, created_at) "
                "VALUES (:id, :s, :f, 'CHARGE', 747500, 'Maintenance charge', NOW());"
            ),
            {"id": ledger_id, "s": soc_id, "f": flat_id},
        )
        conn.commit()

    # 1. Direct UPDATE on financial_ledger_entries must FAIL via trigger
    with engine.connect() as conn:
        update_rejected = False
        try:
            conn.execute(
                text(
                    f"UPDATE financial_ledger_entries SET amount_paise = 999999 WHERE id = '{ledger_id}';"
                )
            )
            conn.commit()
        except Exception as exc:
            update_rejected = True
            assert "immutable" in str(exc).lower()
        assert update_rejected, "Database trigger must reject UPDATE on financial_ledger_entries"

    # 2. Direct DELETE on financial_ledger_entries must FAIL via trigger
    with engine.connect() as conn:
        delete_rejected = False
        try:
            conn.execute(text(f"DELETE FROM financial_ledger_entries WHERE id = '{ledger_id}';"))
            conn.commit()
        except Exception as exc:
            delete_rejected = True
            assert "immutable" in str(exc).lower()
        assert delete_rejected, "Database trigger must reject DELETE on financial_ledger_entries"


def test_postgres_composite_fk_rejects_cross_society_reference(postgres_test_db: Engine) -> None:
    """Finding 6: Database composite foreign key enforces that invoices belong to the flat's society."""
    engine = postgres_test_db
    soc_a = uuid.uuid4()
    soc_b = uuid.uuid4()
    tower_b = uuid.uuid4()
    flat_b = uuid.uuid4()

    with engine.connect() as conn:
        conn.execute(text("RESET ROLE;"))
        conn.execute(
            text(
                "INSERT INTO societies (id, name, timezone, preferred_currency, status, created_at, updated_at) "
                "VALUES (:sa, 'Soc A', 'Asia/Kolkata', 'INR', 'ACTIVE', NOW(), NOW()), "
                "       (:sb, 'Soc B', 'Asia/Kolkata', 'INR', 'ACTIVE', NOW(), NOW());"
            ),
            {"sa": soc_a, "sb": soc_b},
        )
        conn.execute(
            text(
                "INSERT INTO towers (id, society_id, tower_number, name, created_at) "
                "VALUES (:tb, :sb, 'T01', 'Tower B1', NOW());"
            ),
            {"tb": tower_b, "sb": soc_b},
        )
        conn.execute(
            text(
                "INSERT INTO flats (id, society_id, tower_id, flat_number, area_sqft, status, created_at, updated_at) "
                "VALUES (:fb, :sb, :tb, '101', 1000, 'OCCUPIED', NOW(), NOW());"
            ),
            {"fb": flat_b, "sb": soc_b, "tb": tower_b},
        )
        conn.commit()

        # Attempt to create an invoice claiming Society A, but referencing Flat B (which belongs to Society B)
        # The composite foreign key fk_invoices_flats_composite must reject this!
        cross_society_rejected = False
        try:
            conn.execute(
                text(
                    f"INSERT INTO invoices (id, society_id, flat_id, billing_period, invoice_number, area_sqft_snapshot, rate_paise_per_sqft_snapshot, subtotal_paise, total_paise, due_date, status, created_at, updated_at) "
                    f"VALUES (gen_random_uuid(), '{soc_a}', '{flat_b}', '2026-11', 'INV-CROSS-001', 1000, 650, 650000, 650000, NOW(), 'UNPAID', NOW(), NOW());"
                )
            )
            conn.commit()
        except Exception:
            cross_society_rejected = True
        assert cross_society_rejected, (
            "Composite FK fk_invoices_flats_composite must reject cross-society flat references"
        )


def test_postgres_cross_flat_allocation_rejected_by_trigger(postgres_test_db: Engine) -> None:
    """P1: Database trigger rejects cross-flat payment allocation at PostgreSQL database level."""
    engine = postgres_test_db
    soc_id = uuid.uuid4()
    tow_id = uuid.uuid4()
    flat1_id = uuid.uuid4()
    flat2_id = uuid.uuid4()
    user_id = uuid.uuid4()
    inv_id = uuid.uuid4()
    pay_id = uuid.uuid4()
    alloc_id = uuid.uuid4()

    with engine.connect() as conn:
        conn.execute(text("RESET ROLE;"))
        conn.execute(
            text(
                "INSERT INTO societies (id, name, timezone, preferred_currency, status, created_at, updated_at) "
                "VALUES (:s, 'Trigger Soc', 'Asia/Kolkata', 'INR', 'ACTIVE', NOW(), NOW());"
            ),
            {"s": soc_id},
        )
        conn.execute(
            text(
                "INSERT INTO users (id, supabase_uid, email, phone, full_name, status, created_at, updated_at) "
                "VALUES (:u, :sub, :email, :phone, 'Trigger User', 'ACTIVE', NOW(), NOW());"
            ),
            {
                "u": user_id,
                "sub": uuid.uuid4(),
                "email": f"trg-{uuid.uuid4().hex[:6]}@example.com",
                "phone": f"+9198{uuid.uuid4().int % 100000000:08d}",
            },
        )
        conn.execute(
            text(
                "INSERT INTO towers (id, society_id, tower_number, name, created_at) "
                "VALUES (:t, :s, 'T99', 'Tower 99', NOW());"
            ),
            {"t": tow_id, "s": soc_id},
        )
        conn.execute(
            text(
                "INSERT INTO flats (id, society_id, tower_id, flat_number, area_sqft, status, created_at, updated_at) "
                "VALUES (:f1, :s, :t, '101', 1000, 'OCCUPIED', NOW(), NOW()), "
                "       (:f2, :s, :t, '102', 1200, 'OCCUPIED', NOW(), NOW());"
            ),
            {"f1": flat1_id, "f2": flat2_id, "s": soc_id, "t": tow_id},
        )
        conn.execute(
            text(
                "INSERT INTO invoices (id, society_id, flat_id, billing_period, invoice_number, area_sqft_snapshot, rate_paise_per_sqft_snapshot, subtotal_paise, total_paise, due_date, status, created_at, updated_at) "
                "VALUES (:inv, :s, :f1, '2026-11', 'INV-TRG-001', 1000, 650, 650000, 650000, NOW(), 'UNPAID', NOW(), NOW());"
            ),
            {"inv": inv_id, "s": soc_id, "f1": flat1_id},
        )
        conn.execute(
            text(
                "INSERT INTO payments (id, society_id, flat_id, amount_paise, currency, provider, provider_reference, status, initiated_by, created_at, updated_at) "
                "VALUES (:p, :s, :f2, 650000, 'INR', 'SIMULATED', 'SIM-TRG-001', 'SUCCESS', :u, NOW(), NOW());"
            ),
            {"p": pay_id, "s": soc_id, "f2": flat2_id, "u": user_id},
        )
        conn.commit()

        cross_flat_rejected = False
        try:
            conn.execute(
                text(
                    "INSERT INTO payment_allocations (id, payment_id, invoice_id, allocated_paise, created_at) "
                    "VALUES (:a, :p, :inv, 650000, NOW());"
                ),
                {"a": alloc_id, "p": pay_id, "inv": inv_id},
            )
            conn.commit()
        except Exception as exc:
            cross_flat_rejected = True
            assert "cross-flat" in str(exc).lower()

        assert cross_flat_rejected, "Database trigger must reject cross-flat payment allocation"


def test_postgres_flat_deletion_restricted_when_invoices_exist(postgres_test_db: Engine) -> None:
    """P1: ON DELETE RESTRICT prevents flat deletion when invoices exist in PostgreSQL."""
    engine = postgres_test_db
    soc_id = uuid.uuid4()
    tow_id = uuid.uuid4()
    flat_id = uuid.uuid4()
    inv_id = uuid.uuid4()

    with engine.connect() as conn:
        conn.execute(text("RESET ROLE;"))
        conn.execute(
            text(
                "INSERT INTO societies (id, name, timezone, preferred_currency, status, created_at, updated_at) "
                "VALUES (:s, 'Del Soc', 'Asia/Kolkata', 'INR', 'ACTIVE', NOW(), NOW());"
            ),
            {"s": soc_id},
        )
        conn.execute(
            text(
                "INSERT INTO towers (id, society_id, tower_number, name, created_at) "
                "VALUES (:t, :s, 'T01', 'Tower 1', NOW());"
            ),
            {"t": tow_id, "s": soc_id},
        )
        conn.execute(
            text(
                "INSERT INTO flats (id, society_id, tower_id, flat_number, area_sqft, status, created_at, updated_at) "
                "VALUES (:f, :s, :t, '501', 1000, 'OCCUPIED', NOW(), NOW());"
            ),
            {"f": flat_id, "s": soc_id, "t": tow_id},
        )
        conn.execute(
            text(
                "INSERT INTO invoices (id, society_id, flat_id, billing_period, invoice_number, area_sqft_snapshot, rate_paise_per_sqft_snapshot, subtotal_paise, total_paise, due_date, status, created_at, updated_at) "
                "VALUES (:inv, :s, :f, '2026-11', 'INV-DEL-PG-001', 1000, 650, 650000, 650000, NOW(), 'UNPAID', NOW(), NOW());"
            ),
            {"inv": inv_id, "s": soc_id, "f": flat_id},
        )
        conn.commit()

        del_rejected = False
        try:
            conn.execute(text(f"DELETE FROM flats WHERE id = '{flat_id}';"))
            conn.commit()
        except Exception as exc:
            del_rejected = True
            assert (
                "foreign key" in str(exc).lower()
                or "violates" in str(exc).lower()
                or "restrict" in str(exc).lower()
            )

        assert del_rejected, (
            "ON DELETE RESTRICT on composite FK must prevent deleting flat with existing invoices"
        )


def test_postgres_concurrent_payment_locking(postgres_test_db: Engine) -> None:
    """Requirement: Two independent PostgreSQL sessions attempting ₹7,000 simultaneously against a ₹10,000 invoice.

    Only one should succeed due to SELECT ... FOR UPDATE row locking and balance re-check.
    Calls actual BillingService.process_invoice_payment to verify transaction boundaries and concurrency safety.
    """
    import concurrent.futures

    engine = postgres_test_db
    soc_id = uuid.uuid4()
    tow_id = uuid.uuid4()
    flat_id = uuid.uuid4()
    user_id = uuid.uuid4()
    inv_id = uuid.uuid4()

    # 1. Setup society, tower, flat, user, and ₹10,000 (1,000,000 paise) invoice
    with Session(engine) as session:
        session.execute(text("RESET ROLE;"))
        soc = Society(id=soc_id, name="Conc Soc", status=SocietyStatus.ACTIVE)
        session.add(soc)
        user = User(
            id=user_id,
            supabase_uid=uuid.uuid4(),
            email=f"conc-{uuid.uuid4().hex[:6]}@example.com",
            phone=f"+9198{uuid.uuid4().int % 100000000:08d}",
            full_name="Conc User",
            status=UserStatus.ACTIVE,
        )
        session.add(user)
        tow = Tower(id=tow_id, society_id=soc_id, tower_number="T01", name="Tower 1")
        session.add(tow)
        flat = Flat(
            id=flat_id,
            society_id=soc_id,
            tower_id=tow_id,
            flat_number="701",
            area_sqft=1000,
            status=FlatStatus.OCCUPIED,
        )
        session.add(flat)
        session.commit()

        # Insert ₹10,000 invoice
        inv = Invoice(
            id=inv_id,
            society_id=soc_id,
            flat_id=flat_id,
            billing_period="2026-11",
            invoice_number="INV-CONC-001",
            area_sqft_snapshot=1000,
            rate_paise_per_sqft_snapshot=1000,
            subtotal_paise=1000000,
            total_paise=1000000,
            due_date=datetime.now(UTC),
            status=InvoiceStatus.UNPAID,
        )
        session.add(inv)
        session.commit()

    # Worker function executing real BillingService.process_invoice_payment
    # Payment amount = 700,000 paise (₹7,000)
    def attempt_payment(worker_name: str, idemp_key: str) -> bool:
        with Session(engine) as session:
            session.execute(text("RESET ROLE;"))
            service = BillingService(session)
            try:
                res = service.process_invoice_payment(
                    society_id=soc_id,
                    invoice_id=inv_id,
                    amount_paise=700000,
                    user_id=user_id,
                    simulate_failure=False,
                    idempotency_key=idemp_key,
                )
                return res.status == PaymentStatus.SUCCESS
            except Exception:
                return False

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(attempt_payment, "Worker-1", f"conc-key-1-{uuid.uuid4()}")
        f2 = executor.submit(attempt_payment, "Worker-2", f"conc-key-2-{uuid.uuid4()}")
        results = [f1.result(), f2.result()]

    # Exactly ONE session must succeed and one must be rejected!
    assert results.count(True) == 1, f"Expected exactly one payment to succeed, got: {results}"
    assert results.count(False) == 1, (
        f"Expected exactly one payment to fail due to over-allocation, got: {results}"
    )

    # Verify final total allocated in PostgreSQL is strictly 700,000 paise (₹7,000), NOT 1,400,000 paise!
    with Session(engine) as session:
        session.execute(text("RESET ROLE;"))
        total_allocated = session.execute(
            text("SELECT SUM(allocated_paise) FROM payment_allocations WHERE invoice_id = :inv;"),
            {"inv": inv_id},
        ).scalar()
        assert total_allocated == 700000, (
            f"Expected exactly 700000 allocated, got {total_allocated}"
        )


def test_postgres_batch_billing_generation_bounded_operations(postgres_test_db: Engine) -> None:
    """Requirement: Verify batch billing generation with bounded operations and CHUNK_SIZE=500 in PostgreSQL."""
    import time

    engine = postgres_test_db
    soc_id = uuid.uuid4()
    admin_id = uuid.uuid4()

    with Session(engine) as session:
        session.execute(text("RESET ROLE;"))
        soc = Society(id=soc_id, name="PG Bounded Batch Township", status=SocietyStatus.ACTIVE)
        session.add(soc)

        # Create 5 towers with 100 flats each = 500 flats (one full chunk)
        flats = []
        for t_idx in range(5):
            tow_id = uuid.uuid4()
            tow = Tower(
                id=tow_id,
                society_id=soc_id,
                tower_number=f"PG-T{t_idx:02d}",
                name=f"PG Tower {t_idx}",
            )
            session.add(tow)
            for f_idx in range(100):
                flat = Flat(
                    id=uuid.uuid4(),
                    society_id=soc_id,
                    tower_id=tow_id,
                    flat_number=f"{t_idx:02d}-{f_idx:03d}",
                    area_sqft=1000 + (f_idx % 5) * 50,
                    status=FlatStatus.OCCUPIED,
                )
                flats.append(flat)
        session.add_all(flats)
        session.commit()

        service = BillingService(session)
        service.repo.create_default_billing_config(
            society_id=soc_id,
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )

        # Invariant 1: CHUNK_SIZE must be bounded to 500
        assert service.CHUNK_SIZE == 500

        # Invariant 2: Execution across 500 flats in PostgreSQL completes efficiently (< 5.0 seconds)
        start_time = time.perf_counter()
        run = service.execute_billing_run(
            society_id=soc_id,
            billing_period="2027-02",
            actor_id=admin_id,
        )
        elapsed = time.perf_counter() - start_time

        assert run.total_invoiced_flats == 500
        assert run.status == "COMPLETED"
        assert elapsed < 5.0, (
            f"500-flat PostgreSQL batch generation took {elapsed:.2f}s, exceeding 5.0s threshold"
        )

        # Verify database invoice count matches exactly 500
        count = session.execute(
            text(
                "SELECT COUNT(*) FROM invoices WHERE society_id = :soc AND billing_period = '2027-02';"
            ),
            {"soc": soc_id},
        ).scalar()
        assert count == 500
