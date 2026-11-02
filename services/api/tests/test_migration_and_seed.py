"""Database Schema and Idempotent Seed Test Suite

Mandatory Tests:
12. Database migration works from an empty database
13. Seed script is idempotent
"""

from scripts.seed import (
    FLAT_0408_ID,
    FLAT_1203_ID,
    FLAT_1601_ID,
    seed_database,
)
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.domains.identity.models import (
    Flat,
    FlatMembership,
    Society,
    Tower,
    User,
    UserRole,
)


def test_database_migration_works_from_empty_database() -> None:
    """Requirement 13.12: Database migration works from an empty database."""
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    # Create all schema tables from metadata
    Base.metadata.create_all(bind=engine)

    # Assert that all 10 core tables exist in the metadata
    table_names = Base.metadata.tables.keys()
    required_tables = [
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
    for tbl in required_tables:
        assert tbl in table_names, f"Table {tbl} must be created during initial migration"

    Base.metadata.drop_all(bind=engine)


def test_seed_script_is_idempotent(monkeypatch) -> None:
    """Requirement 13.13: Seed script is idempotent. Re-running it must not duplicate records."""
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)

    # Monkeypatch SessionLocal in scripts.seed to point to our test engine
    import scripts.seed

    monkeypatch.setattr(scripts.seed, "SessionLocal", TestSession)

    # Pass 1: Run seed
    seed_database()

    with TestSession() as session:
        society_count_1 = session.scalar(select(func.count(Society.id)))
        tower_count_1 = session.scalar(select(func.count(Tower.id)))
        flat_count_1 = session.scalar(select(func.count(Flat.id)))
        user_count_1 = session.scalar(select(func.count(User.id)))
        membership_count_1 = session.scalar(select(func.count(FlatMembership.id)))
        role_count_1 = session.scalar(select(func.count(UserRole.id)))

        assert society_count_1 == 1
        assert tower_count_1 == 3
        assert flat_count_1 == 3
        assert user_count_1 == 7

        # Verify the 3 required sample flats exist with correct details
        f1 = session.get(Flat, FLAT_1203_ID)
        assert f1.flat_number == "1203"
        assert f1.area_sqft == 1150

        f2 = session.get(Flat, FLAT_0408_ID)
        assert f2.flat_number == "0408"
        assert f2.area_sqft == 980

        f3 = session.get(Flat, FLAT_1601_ID)
        assert f3.flat_number == "1601"
        assert f3.area_sqft == 1640

    # Pass 2: Re-run seed immediately (must not fail or duplicate)
    seed_database()

    with TestSession() as session:
        society_count_2 = session.scalar(select(func.count(Society.id)))
        tower_count_2 = session.scalar(select(func.count(Tower.id)))
        flat_count_2 = session.scalar(select(func.count(Flat.id)))
        user_count_2 = session.scalar(select(func.count(User.id)))
        membership_count_2 = session.scalar(select(func.count(FlatMembership.id)))
        role_count_2 = session.scalar(select(func.count(UserRole.id)))

        # Counts must remain strictly identical
        assert society_count_2 == society_count_1
        assert tower_count_2 == tower_count_1
        assert flat_count_2 == flat_count_1
        assert user_count_2 == user_count_1
        assert membership_count_2 == membership_count_1
        assert role_count_2 == role_count_1

    Base.metadata.drop_all(bind=engine)
