"""Authorization, RBAC, and Tenant Isolation Test Suite

Mandatory Tests:
3. Resident cannot access another resident's flat (403 Forbidden)
4. Help-desk user cannot perform restricted finance operations (403 Forbidden)
5. Committee viewer cannot modify records (403 Forbidden)
6. Tenant access stops after membership expiry (403 Forbidden)
7. Society-level isolation works (Cross-society access denied)
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.identity.models import (
    FlatMembership,
    MembershipStatus,
    MembershipType,
    RoleType,
    User,
    UserRole,
    UserStatus,
)

FLAT_1203_ID = "33333333-3333-3333-3333-333333331203"
FLAT_0408_ID = "33333333-3333-3333-3333-333333330408"
FLAT_OTHER_ID = "33333333-3333-3333-3333-333333339999"


def test_resident_can_access_own_flat(client: TestClient) -> None:
    """Verifies that an authorized resident (Neeraj) can access his own flat 1203."""
    res = client.get(
        f"/api/v1/flats/{FLAT_1203_ID}",
        headers={"Authorization": "Bearer dev-token-neeraj"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["flat_number"] == "1203"
    assert data["area_sqft"] == 1150


def test_resident_cannot_access_another_residents_flat(client: TestClient) -> None:
    """Requirement 13.3: Resident cannot access another resident's flat."""
    # Neeraj attempts to access Swati's flat 0408
    res = client.get(
        f"/api/v1/flats/{FLAT_0408_ID}",
        headers={"Authorization": "Bearer dev-token-neeraj"},
    )
    assert res.status_code == 403
    error = res.json()["error"]
    assert error["code"] == "FLAT_ACCESS_DENIED"
    assert "not authorised to access this flat" in error["message"]

    # Swati attempts to access Neeraj's flat 1203
    res2 = client.get(
        f"/api/v1/flats/{FLAT_1203_ID}",
        headers={"Authorization": "Bearer dev-token-swati"},
    )
    assert res2.status_code == 403


def test_helpdesk_cannot_perform_finance_operations(client: TestClient) -> None:
    """Requirement 13.4: Help-desk user cannot perform restricted finance operations."""
    # Rajesh (HELPDESK) attempts to trigger batch billing
    res = client.post(
        "/api/v1/finance/batch-billing/preview",
        headers={"Authorization": "Bearer dev-token-helpdesk"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"

    # Priya (FINANCE) can perform finance operations
    res_finance = client.post(
        "/api/v1/finance/batch-billing/preview",
        headers={"Authorization": "Bearer dev-token-finance"},
    )
    assert res_finance.status_code == 200
    assert res_finance.json()["status"] == "AUTHORIZED"


def test_committee_viewer_cannot_modify_records(client: TestClient) -> None:
    """Requirement 13.5: Committee viewer cannot modify records."""
    # Aniket (COMMITTEE_VIEWER) attempts restricted finance modification
    res = client.post(
        "/api/v1/finance/batch-billing/preview",
        headers={"Authorization": "Bearer dev-token-committee"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


def test_tenant_access_stops_after_membership_expiry(
    client: TestClient, db_session: Session
) -> None:
    """Requirement 13.6: Tenant access stops after membership expiry."""
    # Create a tenant with an expired lease
    now = datetime.now(UTC)
    expired_user = User(
        id=uuid.uuid4(),
        cognito_sub="mock-sub-expired-tenant",
        email="expired.tenant@example.com",
        full_name="Expired Tenant",
        status=UserStatus.ACTIVE,
    )
    db_session.add(expired_user)
    db_session.flush()

    db_session.add(
        UserRole(
            user_id=expired_user.id,
            society_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
            role=RoleType.RESIDENT,
        )
    )

    # Membership valid_until was 10 days ago
    expired_membership = FlatMembership(
        id=uuid.uuid4(),
        society_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        user_id=expired_user.id,
        flat_id=uuid.UUID(FLAT_0408_ID),
        membership_type=MembershipType.TENANT,
        valid_from=now - timedelta(days=365),
        valid_until=now - timedelta(days=10),
        is_primary=True,
        status=MembershipStatus.APPROVED,
    )
    db_session.add(expired_membership)
    db_session.commit()

    # Query IdentityRepository directly to assert lease validity boundary
    from app.domains.identity.repository import IdentityRepository

    repo = IdentityRepository(db_session)
    has_access = repo.verify_flat_access(expired_user.id, uuid.UUID(FLAT_0408_ID))
    assert has_access is False


def test_society_level_isolation_works(client: TestClient) -> None:
    """Requirement 13.7: Society-level isolation works (No cross-society data leakage)."""
    # Neeraj (society 1) attempts to query a flat belonging to society 2
    res = client.get(
        f"/api/v1/flats/{FLAT_OTHER_ID}",
        headers={"Authorization": "Bearer dev-token-neeraj"},
    )
    assert res.status_code == 403
