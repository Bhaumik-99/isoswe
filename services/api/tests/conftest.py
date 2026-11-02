"""Test Configuration and Fixtures

Provides:
- In-memory SQLite test database with identical schema and constraints
- FastAPI TestClient with overridden get_db dependency
- Pre-populated test seeds for Neeraj, Swati, Aamir, Helpdesk, Finance, Committee, Admin
"""

import os
import sys
import uuid

# Ensure root services/api and workspace root are on sys.path
services_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
repo_root = os.path.abspath(os.path.join(services_dir, "..", ".."))
sys.path.insert(0, repo_root)
sys.path.insert(0, services_dir)
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Force test environment configuration
os.environ["ENVIRONMENT"] = "development"
os.environ["ENABLE_LOCAL_AUTH_BYPASS"] = "true"
os.environ["MESSAGING_PROVIDER"] = "local"

from app.core.database import Base, get_db
from app.domains.identity.models import (
    Flat,
    FlatMembership,
    FlatStatus,
    MembershipStatus,
    MembershipType,
    RoleType,
    Society,
    SocietyStatus,
    Tower,
    User,
    UserRole,
    UserStatus,
)
from app.main import app

# Test in-memory database with static single-connection pool
TEST_SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """Provides a fresh database with all tables created and populated with test seeds."""
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()

    # Seed baseline society, towers, flats, and users
    society_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    other_society_id = uuid.UUID("99999999-9999-9999-9999-999999999999")

    soc1 = Society(id=society_id, name="Marvel Greenfield Residences", status=SocietyStatus.ACTIVE)
    soc2 = Society(id=other_society_id, name="Other Society", status=SocietyStatus.ACTIVE)
    session.add_all([soc1, soc2])

    tow1 = Tower(
        id=uuid.UUID("22222222-2222-2222-2222-222222222207"),
        society_id=society_id,
        tower_number="T07",
        name="Tower 7",
    )
    tow2 = Tower(
        id=uuid.UUID("22222222-2222-2222-2222-222222222212"),
        society_id=society_id,
        tower_number="T12",
        name="Tower 12",
    )
    session.add_all([tow1, tow2])

    flat_1203 = Flat(
        id=uuid.UUID("33333333-3333-3333-3333-333333331203"),
        society_id=society_id,
        tower_id=tow1.id,
        flat_number="1203",
        area_sqft=1150,
        status=FlatStatus.OCCUPIED,
    )
    flat_0408 = Flat(
        id=uuid.UUID("33333333-3333-3333-3333-333333330408"),
        society_id=society_id,
        tower_id=tow2.id,
        flat_number="0408",
        area_sqft=980,
        status=FlatStatus.OCCUPIED,
    )
    flat_other = Flat(
        id=uuid.UUID("33333333-3333-3333-3333-333333339999"),
        society_id=other_society_id,
        tower_id=tow1.id,
        flat_number="9999",
        area_sqft=1000,
        status=FlatStatus.OCCUPIED,
    )
    session.add_all([flat_1203, flat_0408, flat_other])

    # Users
    user_neeraj = User(
        id=uuid.UUID("44444444-4444-4444-4444-444444440001"),
        cognito_sub="mock-sub-neeraj-kulkarni",
        email="neeraj.kulkarni@example.com",
        full_name="Neeraj Kulkarni",
        status=UserStatus.ACTIVE,
    )
    user_swati = User(
        id=uuid.UUID("44444444-4444-4444-4444-444444440002"),
        cognito_sub="mock-sub-swati-joshi",
        email="swati.joshi@example.com",
        full_name="Swati Joshi",
        status=UserStatus.ACTIVE,
    )
    user_helpdesk = User(
        id=uuid.UUID("44444444-4444-4444-4444-444444440004"),
        cognito_sub="mock-sub-helpdesk-shinde",
        email="helpdesk@example.com",
        full_name="Rajesh Shinde",
        status=UserStatus.ACTIVE,
    )
    user_finance = User(
        id=uuid.UUID("44444444-4444-4444-4444-444444440005"),
        cognito_sub="mock-sub-finance-deshmukh",
        email="finance@example.com",
        full_name="Priya Deshmukh",
        status=UserStatus.ACTIVE,
    )
    user_committee = User(
        id=uuid.UUID("44444444-4444-4444-4444-444444440006"),
        cognito_sub="mock-sub-committee-patwardhan",
        email="committee@example.com",
        full_name="Aniket Patwardhan",
        status=UserStatus.ACTIVE,
    )
    user_admin = User(
        id=uuid.UUID("44444444-4444-4444-4444-444444440007"),
        cognito_sub="mock-sub-admin-joshi",
        email="admin@example.com",
        full_name="Vikram Joshi",
        status=UserStatus.ACTIVE,
    )
    session.add_all(
        [user_neeraj, user_swati, user_helpdesk, user_finance, user_committee, user_admin]
    )

    # Roles
    session.add_all(
        [
            UserRole(user_id=user_neeraj.id, society_id=society_id, role=RoleType.RESIDENT),
            UserRole(user_id=user_swati.id, society_id=society_id, role=RoleType.RESIDENT),
            UserRole(user_id=user_helpdesk.id, society_id=society_id, role=RoleType.HELPDESK),
            UserRole(user_id=user_finance.id, society_id=society_id, role=RoleType.FINANCE),
            UserRole(
                user_id=user_committee.id, society_id=society_id, role=RoleType.COMMITTEE_VIEWER
            ),
            UserRole(user_id=user_admin.id, society_id=society_id, role=RoleType.PLATFORM_ADMIN),
        ]
    )

    now = datetime.now(UTC)
    # Neeraj: Owner of 1203
    session.add(
        FlatMembership(
            id=uuid.UUID("55555555-5555-5555-5555-555555550001"),
            society_id=society_id,
            user_id=user_neeraj.id,
            flat_id=flat_1203.id,
            membership_type=MembershipType.OWNER,
            valid_from=now - timedelta(days=100),
            valid_until=None,
            is_primary=True,
            status=MembershipStatus.APPROVED,
        )
    )

    # Swati: Tenant of 0408 (Active)
    session.add(
        FlatMembership(
            id=uuid.UUID("55555555-5555-5555-5555-555555550002"),
            society_id=society_id,
            user_id=user_swati.id,
            flat_id=flat_0408.id,
            membership_type=MembershipType.TENANT,
            valid_from=now - timedelta(days=30),
            valid_until=now + timedelta(days=330),
            is_primary=True,
            status=MembershipStatus.APPROVED,
        )
    )

    session.commit()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Test client overriding the get_db dependency with test database session."""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
