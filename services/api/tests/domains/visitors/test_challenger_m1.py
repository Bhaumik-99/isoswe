"""Adversarial Empirical Verification Suite for Milestone 1 (Phase 6)

Challenges tested:
1. Challenge 1: Gate-only staff privilege escalation
   - User with RoleType.HELPDESK and Permission.GATE_OPERATIONS (no billing/recon/complaint permissions).
   - Verify cannot resolve or access operational permissions (BILLING_MANAGE, RECONCILIATION_REVIEW, COMPLAINT_MANAGE, BANK_IMPORT).
   - Verify 403 Forbidden on financial/operational endpoints.
2. Challenge 2: Unassigned gate operations
   - Guard assigned strictly to Gate 1 attempts operations targeting Gate 2.
   - Verify verify_gate_access, register_visitor, check_in_visitor, check_out_visitor are rejected with GATE_ACCESS_DENIED.
3. Challenge 3: Cross-society gate assignment bypass
   - Guard attempts operation on a gate belonging to another society or cross-society ID mismatch.
   - Verify rejection with GATE_NOT_FOUND or GATE_ACCESS_DENIED.
4. Challenge 4: Expired tenancy membership
   - Resident whose flat lease has expired attempts flat access validation.
   - Verify return 403 / AuthorizationError with code FLAT_ACCESS_DENIED.
5. Challenge 5: Full baseline regression verification.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.errors import (
    AuthorizationError,
    ResourceNotFoundError,
)
from app.core.security import CurrentUserClaims, get_current_user, require_flat_access
from app.domains.identity.models import (
    Flat,
    FlatMembership,
    MembershipStatus,
    MembershipType,
    Permission,
    RoleType,
    Society,
    SocietyStatus,
    Tower,
    User,
    UserPermission,
    UserRole,
    UserStatus,
)
from app.domains.identity.service import IdentityService
from app.domains.visitors.models import (
    ApprovalStatus,
    EntryStatus,
    Gate,
    GateStaffAssignment,
    GateStatus,
    VisitorPurpose,
)
from app.domains.visitors.service import VisitorService
from app.main import app

SOCIETY_PUNE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
GATE_1_ID = uuid.UUID("aaaaaaaa-1111-0000-0000-000000000001")
GATE_2_ID = uuid.UUID("aaaaaaaa-2222-0000-0000-000000000002")
GATE_3_ID = uuid.UUID("aaaaaaaa-3333-0000-0000-000000000003")
GATE_4_ID = uuid.UUID("aaaaaaaa-4444-0000-0000-000000000004")

FLAT_1203_ID = uuid.UUID("33333333-3333-3333-3333-333333331203")
FLAT_0408_ID = uuid.UUID("33333333-3333-3333-3333-333333330408")


# ==============================================================================
# CHALLENGE 1: Gate-Only Staff Privilege Escalation
# ==============================================================================
def test_challenge_1_gate_staff_privilege_escalation(
    db_session: Session, client: TestClient
) -> None:
    """Challenge 1: Gate-only staff privilege escalation.

    Create a user with RoleType.HELPDESK and Permission.GATE_OPERATIONS (no billing/recon/complaint permissions).
    Verify they cannot resolve or access operational permissions (BILLING_MANAGE, RECONCILIATION_REVIEW, COMPLAINT_MANAGE).
    """
    identity_svc = IdentityService(db_session)
    user_id = uuid.uuid4()
    supabase_uid = uuid.uuid4()

    # Create gate security guard with only GATE_OPERATIONS
    guard_user = User(
        id=user_id,
        supabase_uid=supabase_uid,
        email="adversarial.guard@example.com",
        phone="+91-98765-99901",
        full_name="Adversarial Guard Ramesh",
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
    db_session.add_all([guard_user, role, perm])
    db_session.flush()

    # 1. Empirically verify permission resolution from identity service
    profile = identity_svc.get_me_profile(user_id)
    assert [r.role for r in profile.roles] == [RoleType.HELPDESK]
    assert profile.permissions == [Permission.GATE_OPERATIONS]

    # Explicitly check operational permissions are NOT present
    assert Permission.BILLING_MANAGE not in profile.permissions
    assert Permission.RECONCILIATION_REVIEW not in profile.permissions
    assert Permission.COMPLAINT_MANAGE not in profile.permissions
    assert Permission.BANK_IMPORT not in profile.permissions
    assert Permission.COMMITTEE_REPORT_READ not in profile.permissions

    # 2. Empirically verify permission checker dependencies reject operational permissions
    from app.core.security import require_permissions

    claims = CurrentUserClaims(
        user_id=user_id,
        supabase_uid=supabase_uid,
        email="adversarial.guard@example.com",
        phone="+91-98765-99901",
        full_name="Adversarial Guard Ramesh",
        roles=[RoleType.HELPDESK],
        permissions=[Permission.GATE_OPERATIONS],
        society_ids=[SOCIETY_PUNE_ID],
        active_flat_ids=[],
        is_mock=True,
    )

    for forbidden_perm in [
        Permission.BILLING_MANAGE,
        Permission.RECONCILIATION_REVIEW,
        Permission.COMPLAINT_MANAGE,
        Permission.BANK_IMPORT,
        Permission.COMMITTEE_REPORT_READ,
    ]:
        checker = require_permissions(forbidden_perm)
        with pytest.raises(AuthorizationError) as exc_info:
            checker(claims)
        assert exc_info.value.code == "INSUFFICIENT_PERMISSIONS"
        assert forbidden_perm.value in exc_info.value.message

    # 3. Empirically challenge HTTP endpoints via TestClient
    app.dependency_overrides[get_current_user] = lambda: claims
    try:
        # Billing & reconciliation protected endpoint attempt: /api/v1/finance/batch-billing/preview
        billing_resp = client.post("/api/v1/finance/batch-billing/preview")
        assert billing_resp.status_code == 403, f"Expected 403, got {billing_resp.status_code}"
        assert billing_resp.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"

        # Committee report endpoint attempt
        committee_resp = client.get(f"/api/v1/committee/overview?society_id={SOCIETY_PUNE_ID}")
        assert committee_resp.status_code == 403, f"Expected 403, got {committee_resp.status_code}"
        assert committee_resp.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ==============================================================================
# CHALLENGE 2: Unassigned Gate Operations
# ==============================================================================
def test_challenge_2_unassigned_gate_operations(db_session: Session) -> None:
    """Challenge 2: Unassigned gate operations.

    Guard assigned strictly to Gate 1 attempts to perform operations targeting Gate 2.
    Must be rejected with GATE_ACCESS_DENIED.
    """
    now = datetime.now(UTC)
    visitor_svc = VisitorService(db_session)

    # Create Guard strictly assigned to Gate 1
    guard_id = uuid.uuid4()
    guard = User(
        id=guard_id,
        supabase_uid=uuid.uuid4(),
        email="gate1.exclusive@example.com",
        phone="+91-98765-99902",
        full_name="Exclusive Gate 1 Guard",
        status=UserStatus.ACTIVE,
    )
    role = UserRole(
        id=uuid.uuid4(),
        user_id=guard_id,
        society_id=SOCIETY_PUNE_ID,
        role=RoleType.HELPDESK,
    )
    perm = UserPermission(
        id=uuid.uuid4(),
        user_id=guard_id,
        society_id=SOCIETY_PUNE_ID,
        permission=Permission.GATE_OPERATIONS,
    )
    assignment_g1 = GateStaffAssignment(
        id=uuid.uuid4(),
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        user_id=guard_id,
        assigned_from=now - timedelta(hours=2),
        assigned_until=now + timedelta(hours=6),
        is_active=True,
    )
    db_session.add_all([guard, role, perm, assignment_g1])
    db_session.flush()

    # 1. Guard attempts direct access verification on Gate 2 -> DENIED
    with pytest.raises(AuthorizationError) as exc_info:
        visitor_svc.verify_gate_access(guard_id, SOCIETY_PUNE_ID, GATE_2_ID)
    assert exc_info.value.code == "GATE_ACCESS_DENIED"
    assert "not actively assigned to Gate 2" in exc_info.value.message

    # 2. Guard attempts registration targeting Gate 2 -> DENIED
    with pytest.raises(AuthorizationError) as exc_info:
        visitor_svc.register_visitor(
            society_id=SOCIETY_PUNE_ID,
            gate_id=GATE_2_ID,
            guard_user_id=guard_id,
            visitor_name="Sneaky Visitor",
            phone_number="+919876543211",
            purpose=VisitorPurpose.GUEST,
            destination_flat_id=FLAT_1203_ID,
        )
    assert exc_info.value.code == "GATE_ACCESS_DENIED"

    # 3. Create a valid approved visitor, guard attempts check-in at Gate 2 -> DENIED
    valid_visitor = visitor_svc.register_visitor(
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,  # Registered at Gate 1
        guard_user_id=guard_id,
        visitor_name="Preapproved Guest",
        phone_number="+919876543212",
        purpose=VisitorPurpose.GUEST,
        destination_flat_id=FLAT_1203_ID,
    )
    # Manually approve for check-in test
    valid_visitor.approval_status = ApprovalStatus.APPROVED
    db_session.flush()

    with pytest.raises(AuthorizationError) as exc_info:
        visitor_svc.check_in_visitor(
            visitor_id=valid_visitor.id,
            gate_id=GATE_2_ID,
            guard_user_id=guard_id,
        )
    assert exc_info.value.code == "GATE_ACCESS_DENIED"

    # 4. Check in at Gate 1 (legitimate), guard attempts check-out at Gate 2 -> DENIED
    visitor_svc.check_in_visitor(
        visitor_id=valid_visitor.id,
        gate_id=GATE_1_ID,
        guard_user_id=guard_id,
    )
    assert valid_visitor.entry_status == EntryStatus.CHECKED_IN

    with pytest.raises(AuthorizationError) as exc_info:
        visitor_svc.check_out_visitor(
            visitor_id=valid_visitor.id,
            gate_id=GATE_2_ID,
            guard_user_id=guard_id,
        )
    assert exc_info.value.code == "GATE_ACCESS_DENIED"

    # 5. Temporal shift expiration: If assignment is in the past, Gate 1 access is also denied
    assignment_g1.assigned_until = now - timedelta(seconds=1)
    db_session.flush()

    with pytest.raises(AuthorizationError) as exc_info:
        visitor_svc.verify_gate_access(guard_id, SOCIETY_PUNE_ID, GATE_1_ID)
    assert exc_info.value.code == "GATE_ACCESS_DENIED"


# ==============================================================================
# CHALLENGE 3: Cross-Society Gate Assignment Bypass
# ==============================================================================
def test_challenge_3_cross_society_gate_assignment_bypass(db_session: Session) -> None:
    """Challenge 3: Cross-society gate assignment bypass.

    Guard attempts operation on a gate belonging to another society.
    Must be rejected with GATE_NOT_FOUND or GATE_ACCESS_DENIED.
    """
    now = datetime.now(UTC)
    visitor_svc = VisitorService(db_session)

    # Create Society 2 and Gate for Society 2
    society_2_id = uuid.uuid4()
    soc2 = Society(
        id=society_2_id,
        name="Society 2 Royal Palms",
        status=SocietyStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    db_session.add(soc2)

    gate_soc2_id = uuid.uuid4()
    gate_soc2 = Gate(
        id=gate_soc2_id,
        society_id=society_2_id,
        gate_number=1,
        gate_name="Society 2 Gate 1",
        status=GateStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    db_session.add(gate_soc2)

    # Tower & flat in Society 2
    tow2 = Tower(
        id=uuid.uuid4(),
        society_id=society_2_id,
        tower_number="T1",
        name="Tower 1",
    )
    db_session.add(tow2)
    flat_soc2 = Flat(
        id=uuid.uuid4(),
        society_id=society_2_id,
        tower_id=tow2.id,
        flat_number="101",
        area_sqft=1000,
    )
    db_session.add(flat_soc2)

    # Guard in Society Pune (Society 1) assigned to Gate 1
    guard_id = uuid.uuid4()
    guard = User(
        id=guard_id,
        supabase_uid=uuid.uuid4(),
        email="guard.soc1@example.com",
        phone="+91-98765-99903",
        full_name="Guard Society 1",
        status=UserStatus.ACTIVE,
    )
    role_soc1 = UserRole(
        id=uuid.uuid4(),
        user_id=guard_id,
        society_id=SOCIETY_PUNE_ID,
        role=RoleType.HELPDESK,
    )
    perm_soc1 = UserPermission(
        id=uuid.uuid4(),
        user_id=guard_id,
        society_id=SOCIETY_PUNE_ID,
        permission=Permission.GATE_OPERATIONS,
    )
    assign_soc1 = GateStaffAssignment(
        id=uuid.uuid4(),
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        user_id=guard_id,
        assigned_from=now - timedelta(hours=1),
        assigned_until=now + timedelta(hours=7),
        is_active=True,
    )
    db_session.add_all([guard, role_soc1, perm_soc1, assign_soc1])
    db_session.flush()

    # 1. Guard Soc1 attempts verify_gate_access with Society 1 ID but Society 2 Gate ID
    with pytest.raises(ResourceNotFoundError) as exc_info:
        visitor_svc.verify_gate_access(
            user_id=guard_id,
            society_id=SOCIETY_PUNE_ID,
            gate_id=gate_soc2_id,
        )
    assert exc_info.value.code == "GATE_NOT_FOUND"

    # 2. Guard Soc1 attempts verify_gate_access with Society 2 ID and Society 2 Gate ID
    with pytest.raises(AuthorizationError) as exc_info:
        visitor_svc.verify_gate_access(
            user_id=guard_id,
            society_id=society_2_id,
            gate_id=gate_soc2_id,
        )
    assert exc_info.value.code == "GATE_ACCESS_DENIED"

    # 3. Guard Soc1 attempts registration in Society 2
    with pytest.raises((AuthorizationError, ResourceNotFoundError)):
        visitor_svc.register_visitor(
            society_id=society_2_id,
            gate_id=gate_soc2_id,
            guard_user_id=guard_id,
            visitor_name="Cross Society Intruder",
            phone_number="+919876543213",
            purpose=VisitorPurpose.GUEST,
            destination_flat_id=flat_soc2.id,
        )

    # 4. Guard Soc1 attempts registration in Society 1 but pointing to destination flat in Society 2
    with pytest.raises(ResourceNotFoundError) as exc_info:
        visitor_svc.register_visitor(
            society_id=SOCIETY_PUNE_ID,
            gate_id=GATE_1_ID,
            guard_user_id=guard_id,
            visitor_name="Cross Flat Intruder",
            phone_number="+919876543214",
            purpose=VisitorPurpose.GUEST,
            destination_flat_id=flat_soc2.id,  # Flat belongs to society 2
        )
    assert exc_info.value.code == "FLAT_NOT_FOUND"


# ==============================================================================
# CHALLENGE 4: Expired Tenancy Membership
# ==============================================================================
def test_challenge_4_expired_tenancy_membership_access_denied(
    db_session: Session, client: TestClient
) -> None:
    """Challenge 4: Expired tenancy membership.

    Resident whose flat lease has expired attempts flat access validation.
    Must return 403 FLAT_ACCESS_DENIED.
    """
    now = datetime.now(UTC)
    visitor_svc = VisitorService(db_session)

    # Create tenant whose lease has expired
    expired_tenant_id = uuid.uuid4()
    expired_supabase_uid = uuid.uuid4()

    expired_tenant = User(
        id=expired_tenant_id,
        supabase_uid=expired_supabase_uid,
        email="expired.tenant@example.com",
        phone="+91-98765-99904",
        full_name="Expired Tenant Manoj",
        status=UserStatus.ACTIVE,
    )
    role = UserRole(
        id=uuid.uuid4(),
        user_id=expired_tenant_id,
        society_id=SOCIETY_PUNE_ID,
        role=RoleType.RESIDENT,
    )
    # Lease expired 2 days ago
    expired_membership = FlatMembership(
        id=uuid.uuid4(),
        society_id=SOCIETY_PUNE_ID,
        user_id=expired_tenant_id,
        flat_id=FLAT_0408_ID,
        membership_type=MembershipType.TENANT,
        valid_from=now - timedelta(days=365),
        valid_until=now - timedelta(days=2),
        is_primary=True,
        status=MembershipStatus.APPROVED,
    )
    db_session.add_all([expired_tenant, role, expired_membership])
    db_session.flush()

    # 1. Empirically verify verify_resident_flat_access raises AuthorizationError(code="FLAT_ACCESS_DENIED")
    with pytest.raises(AuthorizationError) as exc_info:
        visitor_svc.verify_resident_flat_access(
            user_id=expired_tenant_id,
            society_id=SOCIETY_PUNE_ID,
            flat_id=FLAT_0408_ID,
            current_time=now,
        )
    assert exc_info.value.code == "FLAT_ACCESS_DENIED"

    # 2. Expired tenant attempts to approve a visitor destined for FLAT_0408 -> DENIED
    guard_id = uuid.UUID("44444444-4444-4444-4444-444444440004")  # Seeded helpdesk guard
    visitor = visitor_svc.register_visitor(
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        guard_user_id=guard_id,
        visitor_name="Visitor for Expired Tenant",
        phone_number="+919876543215",
        purpose=VisitorPurpose.GUEST,
        destination_flat_id=FLAT_0408_ID,
    )
    assert visitor.approval_status == ApprovalStatus.PENDING

    with pytest.raises(AuthorizationError) as exc_info:
        visitor_svc.handle_resident_action(
            visitor_id=visitor.id,
            action="APPROVE",
            resident_user_id=expired_tenant_id,
        )
    assert exc_info.value.code == "FLAT_ACCESS_DENIED"

    # 3. Security dependency require_flat_access raises AuthorizationError(code="FLAT_ACCESS_DENIED")
    claims = CurrentUserClaims(
        user_id=expired_tenant_id,
        supabase_uid=expired_supabase_uid,
        email="expired.tenant@example.com",
        phone="+91-98765-99904",
        full_name="Expired Tenant Manoj",
        roles=[RoleType.RESIDENT],
        permissions=[],
        society_ids=[SOCIETY_PUNE_ID],
        active_flat_ids=[],  # No active flat IDs because lease is expired
        is_mock=True,
    )
    with pytest.raises(AuthorizationError) as exc_info:
        require_flat_access(flat_id=FLAT_0408_ID, db=db_session, claims=claims)
    assert exc_info.value.code == "FLAT_ACCESS_DENIED"

    # 4. HTTP endpoint check via TestClient with dependency override
    app.dependency_overrides[get_current_user] = lambda: claims
    try:
        # A flat-scoped endpoint (e.g. GET /api/v1/flats/{flat_id})
        flat_endpoint_resp = client.get(f"/api/v1/flats/{FLAT_0408_ID}")
        assert flat_endpoint_resp.status_code == 403
        assert flat_endpoint_resp.json()["error"]["code"] == "FLAT_ACCESS_DENIED"
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    # 5. Boundary edge test: valid_until is 1 second in the past
    expired_membership.valid_until = now - timedelta(seconds=1)
    db_session.flush()
    with pytest.raises(AuthorizationError) as exc_info:
        visitor_svc.verify_resident_flat_access(
            user_id=expired_tenant_id,
            society_id=SOCIETY_PUNE_ID,
            flat_id=FLAT_0408_ID,
            current_time=now,
        )
    assert exc_info.value.code == "FLAT_ACCESS_DENIED"

    # 6. Status edge test: Membership status is EXPIRED even if date is valid
    expired_membership.valid_until = now + timedelta(days=30)
    expired_membership.status = MembershipStatus.EXPIRED
    db_session.flush()
    with pytest.raises(AuthorizationError) as exc_info:
        visitor_svc.verify_resident_flat_access(
            user_id=expired_tenant_id,
            society_id=SOCIETY_PUNE_ID,
            flat_id=FLAT_0408_ID,
            current_time=now,
        )
    assert exc_info.value.code == "FLAT_ACCESS_DENIED"
