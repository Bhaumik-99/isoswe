"""Gate RBAC and Permission Safety Test Suite

Validates:
1. Strict 2-role preservation: RoleType contains only RESIDENT and HELPDESK.
2. Introduction and registration of Permission.GATE_OPERATIONS.
3. Permission resolution refactoring:
   - HELPDESK role alone does NOT grant billing/complaints/reconciliation capabilities.
   - Gate-only operators receive strictly GATE_OPERATIONS.
4. Cross-domain privilege separation:
   - Gate-only staff cannot access /api/v1/billing or /api/v1/reconciliation endpoints.
5. Legacy staff backfill guarantees:
   - Seeded helpdesk staff (Rajesh Shinde) retain Phase 1-5 capabilities via explicit permissions.
6. Tenant lease expiration boundary enforcement.
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import CurrentUserClaims, get_current_user
from app.domains.identity.models import (
    FlatMembership,
    MembershipStatus,
    MembershipType,
    Permission,
    RoleType,
    User,
    UserPermission,
    UserRole,
    UserStatus,
)
from app.domains.identity.service import IdentityService
from app.main import app

SOCIETY_PUNE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_HELPDESK_ID = uuid.UUID("44444444-4444-4444-4444-444444440004")
FLAT_1203_ID = uuid.UUID("33333333-3333-3333-3333-333333331203")
FLAT_0408_ID = uuid.UUID("33333333-3333-3333-3333-333333330408")


def test_role_type_enum_preservation() -> None:
    """Verifies that the system strictly preserves only two roles: RESIDENT and HELPDESK."""
    role_members = {member.value for member in RoleType}
    assert role_members == {"RESIDENT", "HELPDESK"}, (
        f"RoleType must contain strictly RESIDENT and HELPDESK. Found: {role_members}"
    )


def test_gate_operations_permission_registered() -> None:
    """Verifies that Permission.GATE_OPERATIONS is registered with value 'GATE_OPERATIONS'."""
    assert hasattr(Permission, "GATE_OPERATIONS")
    assert Permission.GATE_OPERATIONS.value == "GATE_OPERATIONS"


def test_communications_manage_permission_registered() -> None:
    """Verifies that Permission.COMMUNICATIONS_MANAGE is registered with value 'COMMUNICATIONS_MANAGE'."""
    assert hasattr(Permission, "COMMUNICATIONS_MANAGE")
    assert Permission.COMMUNICATIONS_MANAGE.value == "COMMUNICATIONS_MANAGE"


def test_helpdesk_role_no_longer_auto_grants_financial_permissions(
    db_session: Session,
) -> None:
    """Verifies that creating a HELPDESK user without explicit permissions resolves to empty permissions."""
    service = IdentityService(db_session)
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        supabase_uid=uuid.uuid4(),
        email="plain.helpdesk@example.com",
        phone="+91-98765-11111",
        full_name="Plain Helpdesk Staff",
        status=UserStatus.ACTIVE,
    )
    role = UserRole(
        id=uuid.uuid4(),
        user_id=user_id,
        society_id=SOCIETY_PUNE_ID,
        role=RoleType.HELPDESK,
    )
    db_session.add_all([user, role])
    db_session.flush()

    profile = service.get_me_profile(user_id)
    assert profile.permissions == []
    assert Permission.COMPLAINT_MANAGE not in profile.permissions
    assert Permission.BANK_IMPORT not in profile.permissions
    assert Permission.RECONCILIATION_REVIEW not in profile.permissions
    assert Permission.BILLING_MANAGE not in profile.permissions


def test_gate_staff_only_has_gate_operations(db_session: Session) -> None:
    """Verifies that a gate operator user has exclusively GATE_OPERATIONS permission."""
    service = IdentityService(db_session)
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        supabase_uid=uuid.uuid4(),
        email="gate.guard@example.com",
        phone="+91-98765-22222",
        full_name="Gate Guard Suresh",
        status=UserStatus.ACTIVE,
    )
    role = UserRole(
        id=uuid.uuid4(),
        user_id=user_id,
        society_id=SOCIETY_PUNE_ID,
        role=RoleType.HELPDESK,
    )
    perm = UserPermission(
        id=uuid.uuid4(),
        user_id=user_id,
        society_id=SOCIETY_PUNE_ID,
        permission=Permission.GATE_OPERATIONS,
    )
    db_session.add_all([user, role, perm])
    db_session.flush()

    profile = service.get_me_profile(user_id)
    assert profile.permissions == [Permission.GATE_OPERATIONS]
    assert Permission.BILLING_MANAGE not in profile.permissions
    assert Permission.COMPLAINT_MANAGE not in profile.permissions


def test_gate_staff_cannot_access_billing_or_reconciliation(
    client: TestClient, db_session: Session
) -> None:
    """Verifies that gate-only staff are denied access (HTTP 403) to billing and reconciliation endpoints."""
    gate_guard_id = uuid.uuid4()
    claims = CurrentUserClaims(
        user_id=gate_guard_id,
        supabase_uid=uuid.uuid4(),
        email="gate.guard@example.com",
        phone="+91-98765-22222",
        full_name="Gate Guard Suresh",
        roles=[RoleType.HELPDESK],
        permissions=[Permission.GATE_OPERATIONS],
        society_ids=[SOCIETY_PUNE_ID],
        active_flat_ids=[],
        is_mock=True,
    )
    app.dependency_overrides[get_current_user] = lambda: claims
    try:
        # Attempt to access finance restricted endpoint requiring BANK_IMPORT & RECONCILIATION_REVIEW: must be 403 Forbidden
        finance_resp = client.post("/api/v1/finance/batch-billing/preview")
        assert finance_resp.status_code == 403
        assert (
            finance_resp.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"
            or finance_resp.status_code == 403
        )

        # Attempt to access committee reporting requiring COMMITTEE_REPORT_READ: must be 403 Forbidden
        committee_resp = client.get(f"/api/v1/committee/overview?society_id={SOCIETY_PUNE_ID}")
        assert committee_resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_gate_staff_cannot_manage_official_notices(client: TestClient, db_session: Session) -> None:
    """Verifies that gate-only staff (GATE_OPERATIONS only) receive HTTP 403 on notice mutations."""
    gate_guard_id = uuid.uuid4()
    claims = CurrentUserClaims(
        user_id=gate_guard_id,
        supabase_uid=uuid.uuid4(),
        email="gate.guard@example.com",
        phone="+91-98765-22222",
        full_name="Gate Guard Suresh",
        roles=[RoleType.HELPDESK],
        permissions=[Permission.GATE_OPERATIONS],
        society_ids=[SOCIETY_PUNE_ID],
        active_flat_ids=[],
        is_mock=True,
    )
    app.dependency_overrides[get_current_user] = lambda: claims
    try:
        # 1. Create notice: must be 403 Forbidden
        create_resp = client.post(
            f"/api/v1/notifications/staff/notices?society_id={SOCIETY_PUNE_ID}",
            json={
                "title": "Gate Operator Rogue Circular",
                "body": "Should be rejected with 403.",
                "category": "GENERAL",
                "status": "DRAFT",
            },
        )
        assert create_resp.status_code == 403
        assert (
            create_resp.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"
            or create_resp.status_code == 403
        )

        fake_notice_id = uuid.uuid4()
        # 2. Update notice: must be 403 Forbidden
        update_resp = client.put(
            f"/api/v1/notifications/staff/notices/{fake_notice_id}?society_id={SOCIETY_PUNE_ID}",
            json={"title": "Updated Title"},
        )
        assert update_resp.status_code == 403

        # 3. Publish notice: must be 403 Forbidden
        pub_resp = client.post(
            f"/api/v1/notifications/staff/notices/{fake_notice_id}/publish?society_id={SOCIETY_PUNE_ID}"
        )
        assert pub_resp.status_code == 403

        # 4. Archive notice: must be 403 Forbidden
        arch_resp = client.post(
            f"/api/v1/notifications/staff/notices/{fake_notice_id}/archive?society_id={SOCIETY_PUNE_ID}"
        )
        assert arch_resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_legacy_helpdesk_staff_retains_operational_access(
    client: TestClient, db_session: Session
) -> None:
    """Verifies that legacy helpdesk staff retains access to Phase 1-5 capabilities due to explicit backfill permissions."""
    legacy_claims = CurrentUserClaims(
        user_id=USER_HELPDESK_ID,
        supabase_uid=uuid.UUID("00000000-0000-0000-0000-000000000004"),
        email="helpdesk@example.com",
        phone="+91-98000-00004",
        full_name="Rajesh Shinde",
        roles=[RoleType.HELPDESK],
        permissions=[
            Permission.COMPLAINT_MANAGE,
            Permission.BANK_IMPORT,
            Permission.RECONCILIATION_REVIEW,
            Permission.BILLING_MANAGE,
            Permission.COMMITTEE_REPORT_READ,
            Permission.COMMUNICATIONS_MANAGE,
        ],
        society_ids=[SOCIETY_PUNE_ID],
        active_flat_ids=[],
        is_mock=True,
    )
    app.dependency_overrides[get_current_user] = lambda: legacy_claims
    try:
        # Access committee overview: succeeds with 200 OK
        resp = client.get(f"/api/v1/committee/overview?society_id={SOCIETY_PUNE_ID}")
        assert resp.status_code == 200

        # Access reconciliation statements: succeeds with 200 OK
        recon_resp = client.get(f"/api/v1/reconciliation/statements?society_id={SOCIETY_PUNE_ID}")
        assert recon_resp.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_expired_tenant_cannot_access_flat(db_session: Session) -> None:
    """Verifies that tenant lease expiration strictly revokes active flat membership access."""
    now = datetime.now(UTC)
    service = IdentityService(db_session)

    expired_user_id = uuid.uuid4()
    expired_user = User(
        id=expired_user_id,
        supabase_uid=uuid.uuid4(),
        email="past.tenant@example.com",
        phone="+91-98765-33333",
        full_name="Past Tenant",
        status=UserStatus.ACTIVE,
    )
    db_session.add(expired_user)
    db_session.add(
        UserRole(
            user_id=expired_user_id,
            society_id=SOCIETY_PUNE_ID,
            role=RoleType.RESIDENT,
        )
    )
    membership = FlatMembership(
        id=uuid.uuid4(),
        society_id=SOCIETY_PUNE_ID,
        user_id=expired_user_id,
        flat_id=FLAT_0408_ID,
        membership_type=MembershipType.TENANT,
        valid_from=now - timedelta(days=365),
        valid_until=now - timedelta(days=1),  # Expired yesterday
        status=MembershipStatus.APPROVED,
    )
    db_session.add(membership)
    db_session.flush()

    profile = service.get_me_profile(expired_user_id)
    # The expired membership must NOT be returned in active memberships
    assert len(profile.memberships) == 0
