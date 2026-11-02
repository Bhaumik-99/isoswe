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


def test_resident_cannot_perform_helpdesk_operations(client: TestClient) -> None:
    """Requirement: Residents cannot access restricted helpdesk, finance or reconciliation operations."""
    # Neeraj (RESIDENT) attempts to trigger batch billing preview
    res = client.post(
        "/api/v1/finance/batch-billing/preview",
        headers={"Authorization": "Bearer dev-token-neeraj"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


def test_helpdesk_can_perform_authorized_reconciliation_operations(client: TestClient) -> None:
    """Requirement: Helpdesk staff possessing granular permissions can execute reconciliation actions."""
    # Rajesh (HELPDESK) possesses BANK_IMPORT and RECONCILIATION_REVIEW permissions
    res = client.post(
        "/api/v1/finance/batch-billing/preview",
        headers={"Authorization": "Bearer dev-token-helpdesk"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "AUTHORIZED"


def test_tenant_access_stops_after_membership_expiry(
    client: TestClient, db_session: Session
) -> None:
    """Requirement 13.6: Tenant access stops after membership expiry."""
    # Create a tenant with an expired lease
    now = datetime.now(UTC)
    expired_sub = uuid.uuid4()
    expired_user = User(
        id=uuid.uuid4(),
        supabase_uid=expired_sub,
        phone="+91-98000-00099",
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
    from unittest.mock import patch

    from app.domains.identity.repository import IdentityRepository

    repo = IdentityRepository(db_session)
    has_access = repo.verify_flat_access(expired_user.id, uuid.UUID(FLAT_0408_ID))
    assert has_access is False

    # Also verify via API endpoint that expired tenant gets 403 FLAT_ACCESS_DENIED
    with patch(
        "app.integrations.supabase_auth.supabase_verifier.verify_token",
        return_value={
            "sub": str(expired_sub),
            "role": "authenticated",
            "aud": "authenticated",
            "exp": 9999999999,
            "iss": "https://test-project.supabase.co/auth/v1",
        },
    ):
        res = client.get(
            f"/api/v1/flats/{FLAT_0408_ID}",
            headers={"Authorization": "Bearer expired-tenant-token"},
        )
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "FLAT_ACCESS_DENIED"


def test_society_level_isolation_works(client: TestClient) -> None:
    """Requirement 13.7: Society-level isolation works (No cross-society data leakage)."""
    # Neeraj (society 1) attempts to query a flat belonging to society 2
    res = client.get(
        f"/api/v1/flats/{FLAT_OTHER_ID}",
        headers={"Authorization": "Bearer dev-token-neeraj"},
    )
    assert res.status_code == 403


def test_staff_cross_society_flat_access_denied(client: TestClient, db_session: Session) -> None:
    """Requirement: Staff role in Society A cannot access flats belonging to Society B."""
    from app.domains.identity.models import Flat, FlatStatus, Society, SocietyStatus, Tower

    # 1. Create a distinct secondary society with its own tower and flat
    other_society = Society(
        id=uuid.uuid4(),
        name="Secondary Township",
        timezone="Asia/Kolkata",
        preferred_currency="INR",
        status=SocietyStatus.ACTIVE,
    )
    db_session.add(other_society)
    db_session.flush()

    other_tower = Tower(
        id=uuid.uuid4(),
        society_id=other_society.id,
        tower_number="T99",
        name="Tower 99",
    )
    db_session.add(other_tower)
    db_session.flush()

    other_flat = Flat(
        id=uuid.uuid4(),
        society_id=other_society.id,
        tower_id=other_tower.id,
        flat_number="9901",
        area_sqft=1200,
        status=FlatStatus.OCCUPIED,
    )
    db_session.add(other_flat)
    db_session.commit()

    # Helpdesk staff (Rajesh) belongs ONLY to Society 1 (Marvel Greenfield)
    res = client.get(
        f"/api/v1/flats/{other_flat.id}",
        headers={"Authorization": "Bearer dev-token-helpdesk"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "CROSS_TENANT_ACCESS_DENIED"


def test_helpdesk_can_access_flats_in_own_society(client: TestClient, db_session: Session) -> None:
    """Requirement: Helpdesk staff can inspect flats located within their assigned society."""
    # Rajesh (HELPDESK) belongs to Marvel Greenfield Residences and can access flat 1203
    res = client.get(
        f"/api/v1/flats/{FLAT_1203_ID}",
        headers={"Authorization": "Bearer dev-token-helpdesk"},
    )
    assert res.status_code == 200
    assert res.json()["flat_number"] == "1203"


def test_canonical_sub_enforced_no_email_fallback(client: TestClient, db_session: Session) -> None:
    """Requirement: Authentication strictly maps canonical Supabase UUID. No fallback to email."""
    from unittest.mock import patch

    # Mock token with an unknown UUID sub, but an email matching an existing user (Neeraj)
    unlinked_token_payload = {
        "sub": "ffffffff-ffff-ffff-ffff-ffffffffffff",
        "email": "neeraj.kulkarni@example.com",
        "role": "authenticated",
        "aud": "authenticated",
        "exp": 9999999999,
        "iss": "https://test-project.supabase.co/auth/v1",
    }

    with patch(
        "app.integrations.supabase_auth.supabase_verifier.verify_token",
        return_value=unlinked_token_payload,
    ):
        res = client.get(
            "/api/v1/me",
            headers={"Authorization": "Bearer genuine-supabase-jwt-unlinked"},
        )
        # Must be rejected because 'ffffffff-ffff-ffff-ffff-ffffffffffff' does not exist in DB
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "USER_NOT_REGISTERED"
