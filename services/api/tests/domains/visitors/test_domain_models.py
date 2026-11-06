"""Visitor Domain Models and State Machine Unit Tests

Validates:
1. 4-Gate entity configuration and unique gate numbers per society.
2. Gate staff assignment temporal validity and multi-gate flexibility.
3. Decoupled state transitions:
   - Physical entry/exit: EXPECTED -> CHECKED_IN -> CHECKED_OUT.
   - Resident approval: PENDING -> APPROVED / REJECTED.
4. Transition guards preventing unauthorized or invalid state shifts:
   - Check-in denied when approval is PENDING or REJECTED.
   - Double check-in denied.
   - Checkout denied if not CHECKED_IN.
   - Rejection prohibited once visitor is CHECKED_IN.
5. Resident active flat membership verification and lease expiry rejection.
6. Structured audit event generation with phone masking.
7. Guest pass usability invariants and photo retention properties.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import (
    AuthorizationError,
    ResourceNotFoundError,
    ValidationError,
)
from app.domains.identity.models import (
    FlatMembership,
    MembershipStatus,
    MembershipType,
    RoleType,
    Society,
    SocietyStatus,
    User,
    UserRole,
    UserStatus,
)
from app.domains.reliability.models import AuditEvent
from app.domains.visitors.models import (
    ApprovalStatus,
    EntryStatus,
    Gate,
    GateStaffAssignment,
    GateStatus,
    GuestPass,
    PassStatus,
    PassType,
    VisitorPurpose,
    VisitorRecord,
)
from app.domains.visitors.service import VisitorService

# Test Society & Flat Constants from conftest
SOCIETY_PUNE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
GATE_1_ID = uuid.UUID("aaaaaaaa-1111-0000-0000-000000000001")
GATE_2_ID = uuid.UUID("aaaaaaaa-2222-0000-0000-000000000002")
GATE_3_ID = uuid.UUID("aaaaaaaa-3333-0000-0000-000000000003")
GATE_4_ID = uuid.UUID("aaaaaaaa-4444-0000-0000-000000000004")

FLAT_1203_ID = uuid.UUID("33333333-3333-3333-3333-333333331203")
FLAT_0408_ID = uuid.UUID("33333333-3333-3333-3333-333333330408")
USER_NEERAJ_ID = uuid.UUID("44444444-4444-4444-4444-444444440001")
USER_SWATI_ID = uuid.UUID("44444444-4444-4444-4444-444444440002")
USER_HELPDESK_ID = uuid.UUID("44444444-4444-4444-4444-444444440004")


def test_four_gate_configuration_crud(db_session: Session) -> None:
    """Verifies that 4 entrance gates exist with proper names, numbers, and uniqueness constraints."""
    gates = db_session.scalars(
        select(Gate).where(Gate.society_id == SOCIETY_PUNE_ID).order_by(Gate.gate_number)
    ).all()
    assert len(gates) == 4
    gate_numbers = [g.gate_number for g in gates]
    assert gate_numbers == [1, 2, 3, 4]

    gate_names = [g.gate_name for g in gates]
    assert "Gate 1 - North Main" in gate_names[0]
    assert "Gate 2 - South Entry" in gate_names[1]
    assert "Gate 3 - East Service" in gate_names[2]
    assert "Gate 4 - West Resident" in gate_names[3]

    for g in gates:
        assert g.status == GateStatus.ACTIVE
        assert g.is_active is True

    # Unique constraint test: Duplicate gate_number 1 in same society must fail
    now = datetime.now(UTC)
    dup_gate = Gate(
        id=uuid.uuid4(),
        society_id=SOCIETY_PUNE_ID,
        gate_number=1,
        gate_name="Duplicate North Main",
        status=GateStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    db_session.add(dup_gate)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

    # Same gate number in a different society is permitted
    other_society_id = uuid.uuid4()
    other_society = Society(
        id=other_society_id,
        name="Second Society",
        status=SocietyStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    db_session.add(other_society)
    other_gate_1 = Gate(
        id=uuid.uuid4(),
        society_id=other_society_id,
        gate_number=1,
        gate_name="Gate 1 - Other Society",
        status=GateStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    db_session.add(other_gate_1)
    db_session.flush()
    assert other_gate_1.gate_number == 1


def test_gate_staff_assignment_temporal_validity(db_session: Session) -> None:
    """Verifies temporal validity of gate staff assignments (past, active, future, inactive)."""
    service = VisitorService(db_session)
    now = datetime.now(UTC)

    # 1. Active assignment succeeds (seeded in conftest: helpdesk -> Gate 1)
    assignment = service.verify_gate_access(
        user_id=USER_HELPDESK_ID,
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        current_time=now,
    )
    assert assignment is not None
    assert assignment.gate_id == GATE_1_ID

    # 2. Future assignment raises GATE_ACCESS_DENIED
    future_guard = User(
        id=uuid.uuid4(),
        supabase_uid=uuid.uuid4(),
        email="future.guard@example.com",
        phone="+91-98765-00001",
        full_name="Future Guard",
        status=UserStatus.ACTIVE,
    )
    db_session.add(future_guard)
    future_assignment = GateStaffAssignment(
        id=uuid.uuid4(),
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_2_ID,
        user_id=future_guard.id,
        assigned_from=now + timedelta(hours=2),
        assigned_until=now + timedelta(hours=10),
        is_active=True,
    )
    db_session.add(future_assignment)
    db_session.flush()

    with pytest.raises(AuthorizationError) as exc_info:
        service.verify_gate_access(
            user_id=future_guard.id,
            society_id=SOCIETY_PUNE_ID,
            gate_id=GATE_2_ID,
            current_time=now,
        )
    assert exc_info.value.code == "GATE_ACCESS_DENIED"

    # 3. Expired assignment raises GATE_ACCESS_DENIED
    expired_guard = User(
        id=uuid.uuid4(),
        supabase_uid=uuid.uuid4(),
        email="expired.guard@example.com",
        phone="+91-98765-00002",
        full_name="Expired Guard",
        status=UserStatus.ACTIVE,
    )
    db_session.add(expired_guard)
    expired_assignment = GateStaffAssignment(
        id=uuid.uuid4(),
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_2_ID,
        user_id=expired_guard.id,
        assigned_from=now - timedelta(hours=10),
        assigned_until=now - timedelta(hours=2),
        is_active=True,
    )
    db_session.add(expired_assignment)
    db_session.flush()

    with pytest.raises(AuthorizationError) as exc_info:
        service.verify_gate_access(
            user_id=expired_guard.id,
            society_id=SOCIETY_PUNE_ID,
            gate_id=GATE_2_ID,
            current_time=now,
        )
    assert exc_info.value.code == "GATE_ACCESS_DENIED"

    # 4. Deactivated assignment raises GATE_ACCESS_DENIED
    deactivated_assignment = GateStaffAssignment(
        id=uuid.uuid4(),
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_3_ID,
        user_id=future_guard.id,
        assigned_from=now - timedelta(hours=1),
        assigned_until=now + timedelta(hours=8),
        is_active=False,
    )
    db_session.add(deactivated_assignment)
    db_session.flush()

    with pytest.raises(AuthorizationError) as exc_info:
        service.verify_gate_access(
            user_id=future_guard.id,
            society_id=SOCIETY_PUNE_ID,
            gate_id=GATE_3_ID,
            current_time=now,
        )
    assert exc_info.value.code == "GATE_ACCESS_DENIED"


def test_multi_gate_staff_assignments(db_session: Session) -> None:
    """Verifies that roving staff assigned to multiple gates can operate both, but not unassigned gates."""
    service = VisitorService(db_session)
    now = datetime.now(UTC)

    roving_guard = User(
        id=uuid.uuid4(),
        supabase_uid=uuid.uuid4(),
        email="roving.guard@example.com",
        phone="+91-98765-00003",
        full_name="Roving Guard Ramesh",
        status=UserStatus.ACTIVE,
    )
    db_session.add(roving_guard)

    # Assign to Gate 1 and Gate 2
    a1 = GateStaffAssignment(
        id=uuid.uuid4(),
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        user_id=roving_guard.id,
        assigned_from=now - timedelta(hours=2),
        assigned_until=now + timedelta(hours=6),
        is_active=True,
    )
    a2 = GateStaffAssignment(
        id=uuid.uuid4(),
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_2_ID,
        user_id=roving_guard.id,
        assigned_from=now - timedelta(hours=2),
        assigned_until=now + timedelta(hours=6),
        is_active=True,
    )
    db_session.add_all([a1, a2])
    db_session.flush()

    # Access Gate 1: Success
    res1 = service.verify_gate_access(roving_guard.id, SOCIETY_PUNE_ID, GATE_1_ID, now)
    assert res1.gate_id == GATE_1_ID

    # Access Gate 2: Success
    res2 = service.verify_gate_access(roving_guard.id, SOCIETY_PUNE_ID, GATE_2_ID, now)
    assert res2.gate_id == GATE_2_ID

    # Access Gate 3: Denied
    with pytest.raises(AuthorizationError) as exc_info:
        service.verify_gate_access(roving_guard.id, SOCIETY_PUNE_ID, GATE_3_ID, now)
    assert exc_info.value.code == "GATE_ACCESS_DENIED"


def test_cross_society_gate_access_denied(db_session: Session) -> None:
    """Verifies that gate staff cannot access gates belonging to another society."""
    service = VisitorService(db_session)
    other_society_id = uuid.uuid4()
    other_gate_id = uuid.uuid4()

    with pytest.raises((AuthorizationError, ResourceNotFoundError)):
        service.verify_gate_access(
            user_id=USER_HELPDESK_ID,
            society_id=other_society_id,
            gate_id=other_gate_id,
        )


def test_visitor_registration_and_initial_decoupled_state(db_session: Session) -> None:
    """Verifies visitor registration, initial decoupled state (EXPECTED, PENDING), and audit logging."""
    service = VisitorService(db_session)

    visitor = service.register_visitor(
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        guard_user_id=USER_HELPDESK_ID,
        visitor_name="Vikram Malhotra",
        phone_number="+919876543210",
        purpose=VisitorPurpose.GUEST,
        destination_flat_id=FLAT_1203_ID,
        vehicle_number="MH12AB1234",
        privacy_notice_version="v1.0-2026-pune",
    )
    db_session.commit()

    assert visitor.id is not None
    assert visitor.visitor_name == "Vikram Malhotra"
    assert visitor.entry_status == EntryStatus.EXPECTED
    assert visitor.approval_status == ApprovalStatus.PENDING
    assert visitor.is_approved_for_entry is False
    assert visitor.is_active_on_campus is False
    assert visitor.masked_phone == "+91-XXXXX-XX210"

    # Verify AuditEvent
    audit = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.resource_id == str(visitor.id),
            AuditEvent.action == "VISITOR_REGISTERED",
        )
    )
    assert audit is not None
    assert audit.actor_id == USER_HELPDESK_ID
    assert audit.event_metadata["phone_masked"] == "+91-XXXXX-XX210"
    assert "9876543210" not in str(audit.event_metadata)


def test_visitor_check_in_blocked_when_pending_or_rejected(db_session: Session) -> None:
    """Verifies that guards cannot check in a visitor whose approval status is PENDING or REJECTED."""
    service = VisitorService(db_session)

    visitor = service.register_visitor(
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        guard_user_id=USER_HELPDESK_ID,
        visitor_name="Pending Visitor",
        phone_number="+919876543211",
        purpose=VisitorPurpose.DELIVERY,
        destination_flat_id=FLAT_1203_ID,
    )
    db_session.flush()

    # Attempt check-in while PENDING: blocked
    with pytest.raises(ValidationError) as exc_info:
        service.check_in_visitor(
            visitor_id=visitor.id,
            gate_id=GATE_1_ID,
            guard_user_id=USER_HELPDESK_ID,
        )
    assert exc_info.value.code == "VISITOR_APPROVAL_PENDING"

    # Reject visitor
    service.handle_resident_action(
        visitor_id=visitor.id,
        action="REJECT",
        resident_user_id=USER_NEERAJ_ID,
        reason="Unknown delivery person",
    )
    db_session.flush()

    # Attempt check-in while REJECTED: blocked
    with pytest.raises(ValidationError) as exc_info:
        service.check_in_visitor(
            visitor_id=visitor.id,
            gate_id=GATE_1_ID,
            guard_user_id=USER_HELPDESK_ID,
        )
    assert exc_info.value.code == "VISITOR_REJECTED"


def test_visitor_check_in_success_and_entry_mutation(db_session: Session) -> None:
    """Verifies that an approved visitor can be checked in and physical entry state is updated."""
    service = VisitorService(db_session)

    visitor = service.register_visitor(
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        guard_user_id=USER_HELPDESK_ID,
        visitor_name="Approved Guest",
        phone_number="+919876543212",
        purpose=VisitorPurpose.GUEST,
        destination_flat_id=FLAT_1203_ID,
    )
    db_session.flush()

    # Resident approves
    service.handle_resident_action(
        visitor_id=visitor.id,
        action="APPROVE",
        resident_user_id=USER_NEERAJ_ID,
    )
    db_session.flush()

    assert visitor.approval_status == ApprovalStatus.APPROVED
    assert visitor.entry_status == EntryStatus.EXPECTED
    assert visitor.is_approved_for_entry is True

    # Guard checks in visitor
    checked_in = service.check_in_visitor(
        visitor_id=visitor.id,
        gate_id=GATE_1_ID,
        guard_user_id=USER_HELPDESK_ID,
    )
    db_session.flush()

    assert checked_in.entry_status == EntryStatus.CHECKED_IN
    assert checked_in.approval_status == ApprovalStatus.APPROVED
    assert checked_in.entry_time is not None
    assert checked_in.entry_gate_id == GATE_1_ID
    assert checked_in.is_active_on_campus is True

    # Audit event verification
    audit = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.resource_id == str(visitor.id),
            AuditEvent.action == "VISITOR_CHECKED_IN",
        )
    )
    assert audit is not None
    assert audit.event_metadata["approval_status"] == ApprovalStatus.APPROVED.value


def test_visitor_double_check_in_prohibited(db_session: Session) -> None:
    """Verifies that an already checked-in visitor cannot be checked in a second time."""
    service = VisitorService(db_session)

    visitor = service.register_visitor(
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        guard_user_id=USER_HELPDESK_ID,
        visitor_name="Double Checkin Test",
        phone_number="+919876543213",
        purpose=VisitorPurpose.CAB,
        destination_flat_id=FLAT_1203_ID,
    )
    service.handle_resident_action(
        visitor_id=visitor.id,
        action="APPROVE",
        resident_user_id=USER_NEERAJ_ID,
    )
    service.check_in_visitor(
        visitor_id=visitor.id,
        gate_id=GATE_1_ID,
        guard_user_id=USER_HELPDESK_ID,
    )
    db_session.flush()

    with pytest.raises(ValidationError) as exc_info:
        service.check_in_visitor(
            visitor_id=visitor.id,
            gate_id=GATE_1_ID,
            guard_user_id=USER_HELPDESK_ID,
        )
    assert exc_info.value.code == "VISITOR_ALREADY_CHECKED_IN"


def test_visitor_check_out_success_and_duration_calculation(db_session: Session) -> None:
    """Verifies checkout from CHECKED_IN to CHECKED_OUT, exit timestamp, gate assignment, and duration."""
    service = VisitorService(db_session)

    visitor = service.register_visitor(
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        guard_user_id=USER_HELPDESK_ID,
        visitor_name="Checkout Test",
        phone_number="+919876543214",
        purpose=VisitorPurpose.SERVICE_MAINTENANCE,
        destination_flat_id=FLAT_1203_ID,
    )
    service.handle_resident_action(
        visitor_id=visitor.id,
        action="APPROVE",
        resident_user_id=USER_NEERAJ_ID,
    )
    service.check_in_visitor(
        visitor_id=visitor.id,
        gate_id=GATE_1_ID,
        guard_user_id=USER_HELPDESK_ID,
    )
    # Simulate time elapsed
    visitor.entry_time = datetime.now(UTC) - timedelta(minutes=45)
    db_session.flush()

    checked_out = service.check_out_visitor(
        visitor_id=visitor.id,
        gate_id=GATE_1_ID,
        guard_user_id=USER_HELPDESK_ID,
    )
    db_session.flush()

    assert checked_out.entry_status == EntryStatus.CHECKED_OUT
    assert checked_out.approval_status == ApprovalStatus.APPROVED
    assert checked_out.exit_time is not None
    assert checked_out.exit_gate_id == GATE_1_ID
    assert checked_out.is_active_on_campus is False

    # Audit event verification
    audit = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.resource_id == str(visitor.id),
            AuditEvent.action == "VISITOR_CHECKED_OUT",
        )
    )
    assert audit is not None
    assert audit.event_metadata["duration_minutes"] is not None
    assert audit.event_metadata["duration_minutes"] >= 44.0


def test_visitor_check_out_invalid_transitions(db_session: Session) -> None:
    """Verifies that checkout is rejected when visitor is EXPECTED or already CHECKED_OUT."""
    service = VisitorService(db_session)

    visitor = service.register_visitor(
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        guard_user_id=USER_HELPDESK_ID,
        visitor_name="Invalid Checkout",
        phone_number="+919876543215",
        purpose=VisitorPurpose.GUEST,
        destination_flat_id=FLAT_1203_ID,
    )
    db_session.flush()

    # Attempt checkout on EXPECTED: blocked
    with pytest.raises(ValidationError) as exc_info:
        service.check_out_visitor(
            visitor_id=visitor.id,
            gate_id=GATE_1_ID,
            guard_user_id=USER_HELPDESK_ID,
        )
    assert exc_info.value.code == "INVALID_STATE_TRANSITION"

    # Progress to CHECKED_OUT
    service.handle_resident_action(visitor.id, "APPROVE", USER_NEERAJ_ID)
    service.check_in_visitor(visitor.id, GATE_1_ID, USER_HELPDESK_ID)
    service.check_out_visitor(visitor.id, GATE_1_ID, USER_HELPDESK_ID)
    db_session.flush()

    # Attempt second checkout: blocked
    with pytest.raises(ValidationError) as exc_info:
        service.check_out_visitor(
            visitor_id=visitor.id,
            gate_id=GATE_1_ID,
            guard_user_id=USER_HELPDESK_ID,
        )
    assert exc_info.value.code == "INVALID_STATE_TRANSITION"


def test_resident_approval_idempotency_and_rejection_rules(db_session: Session) -> None:
    """Verifies resident action idempotency, reversal prohibitions, and rejection rules."""
    service = VisitorService(db_session)

    visitor = service.register_visitor(
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        guard_user_id=USER_HELPDESK_ID,
        visitor_name="Idempotency Test",
        phone_number="+919876543216",
        purpose=VisitorPurpose.GUEST,
        destination_flat_id=FLAT_1203_ID,
    )
    db_session.flush()

    # First APPROVE
    v1 = service.handle_resident_action(visitor.id, "APPROVE", USER_NEERAJ_ID)
    assert v1.approval_status == ApprovalStatus.APPROVED

    # Idempotent second APPROVE produces no error
    v2 = service.handle_resident_action(visitor.id, "APPROVE", USER_NEERAJ_ID)
    assert v2.approval_status == ApprovalStatus.APPROVED

    # Check in visitor
    service.check_in_visitor(visitor.id, GATE_1_ID, USER_HELPDESK_ID)
    db_session.flush()

    # Attempt to REJECT while already CHECKED_IN: blocked
    with pytest.raises(ValidationError) as exc_info:
        service.handle_resident_action(visitor.id, "REJECT", USER_NEERAJ_ID)
    assert exc_info.value.code == "INVALID_STATE_TRANSITION"


def test_resident_flat_membership_guard(db_session: Session) -> None:
    """Verifies that residents can only approve visitors for their own active flat memberships."""
    service = VisitorService(db_session)
    now = datetime.now(UTC)

    # Visitor destination is Flat 0408 (Swati's flat)
    visitor_swati = service.register_visitor(
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        guard_user_id=USER_HELPDESK_ID,
        visitor_name="Swati's Friend",
        phone_number="+919876543217",
        purpose=VisitorPurpose.GUEST,
        destination_flat_id=FLAT_0408_ID,
    )
    db_session.flush()

    # Neeraj (Flat 1203) attempts to approve visitor for Flat 0408: blocked
    with pytest.raises(AuthorizationError) as exc_info:
        service.handle_resident_action(
            visitor_id=visitor_swati.id,
            action="APPROVE",
            resident_user_id=USER_NEERAJ_ID,
        )
    assert exc_info.value.code == "FLAT_ACCESS_DENIED"

    # Swati (Flat 0408) approves: succeeds
    res = service.handle_resident_action(
        visitor_id=visitor_swati.id,
        action="APPROVE",
        resident_user_id=USER_SWATI_ID,
    )
    assert res.approval_status == ApprovalStatus.APPROVED

    # Expired tenant lease access denial
    expired_tenant = User(
        id=uuid.uuid4(),
        supabase_uid=uuid.uuid4(),
        email="expired.tenant@example.com",
        phone="+91-98765-00099",
        full_name="Expired Tenant",
        status=UserStatus.ACTIVE,
    )
    db_session.add(expired_tenant)
    db_session.add(
        UserRole(
            user_id=expired_tenant.id,
            society_id=SOCIETY_PUNE_ID,
            role=RoleType.RESIDENT,
        )
    )
    expired_membership = FlatMembership(
        id=uuid.uuid4(),
        society_id=SOCIETY_PUNE_ID,
        user_id=expired_tenant.id,
        flat_id=FLAT_0408_ID,
        membership_type=MembershipType.TENANT,
        valid_from=now - timedelta(days=400),
        valid_until=now - timedelta(days=35),  # expired 35 days ago
        status=MembershipStatus.APPROVED,
    )
    db_session.add(expired_membership)
    db_session.flush()

    with pytest.raises(AuthorizationError) as exc_info:
        service.verify_resident_flat_access(
            user_id=expired_tenant.id,
            society_id=SOCIETY_PUNE_ID,
            flat_id=FLAT_0408_ID,
            current_time=now,
        )
    assert exc_info.value.code == "FLAT_ACCESS_DENIED"


def test_guest_pass_properties_and_model_constraints(db_session: Session) -> None:
    """Verifies GuestPass model helper properties (is_usable) across status and validity boundaries."""
    now = datetime.now(UTC)

    # 1. Usable single-use pass
    pass_active = GuestPass(
        id=uuid.uuid4(),
        society_id=SOCIETY_PUNE_ID,
        destination_flat_id=FLAT_1203_ID,
        created_by_user_id=USER_NEERAJ_ID,
        guest_name="Guest Alpha",
        purpose="Dinner",
        pass_type=PassType.SINGLE_USE,
        pass_code_hash="dummyhash123",
        status=PassStatus.ACTIVE,
        max_uses=1,
        used_count=0,
        valid_from=now - timedelta(hours=1),
        valid_until=now + timedelta(hours=5),
    )
    assert pass_active.is_usable is True

    # 2. Exhausted pass
    pass_exhausted = GuestPass(
        id=uuid.uuid4(),
        society_id=SOCIETY_PUNE_ID,
        destination_flat_id=FLAT_1203_ID,
        created_by_user_id=USER_NEERAJ_ID,
        guest_name="Guest Beta",
        purpose="Dinner",
        pass_type=PassType.SINGLE_USE,
        pass_code_hash="dummyhash456",
        status=PassStatus.EXHAUSTED,
        max_uses=1,
        used_count=1,
        valid_from=now - timedelta(hours=2),
        valid_until=now + timedelta(hours=4),
    )
    assert pass_exhausted.is_usable is False

    # 3. Expired pass
    pass_expired = GuestPass(
        id=uuid.uuid4(),
        society_id=SOCIETY_PUNE_ID,
        destination_flat_id=FLAT_1203_ID,
        created_by_user_id=USER_NEERAJ_ID,
        guest_name="Guest Gamma",
        purpose="Dinner",
        pass_type=PassType.MULTI_USE,
        pass_code_hash="dummyhash789",
        status=PassStatus.ACTIVE,
        max_uses=3,
        used_count=1,
        valid_from=now - timedelta(days=3),
        valid_until=now - timedelta(days=1),
    )
    assert pass_expired.is_usable is False


def test_visitor_photo_retention_properties(db_session: Session) -> None:
    """Verifies 90-day logical expiry calculation and purged flag behaviour."""
    now = datetime.now(UTC)

    # Fresh record (< 90 days)
    fresh_record = VisitorRecord(
        id=uuid.uuid4(),
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        destination_flat_id=FLAT_1203_ID,
        visitor_name="Fresh Visitor",
        phone_number="+919876543290",
        purpose=VisitorPurpose.GUEST,
        photo_s3_key="visitor-photos/1111/photo.jpg",
        created_at=now - timedelta(days=30),
    )
    assert fresh_record.is_photo_expired is False

    # Record > 90 days old
    old_record = VisitorRecord(
        id=uuid.uuid4(),
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        destination_flat_id=FLAT_1203_ID,
        visitor_name="Old Visitor",
        phone_number="+919876543291",
        purpose=VisitorPurpose.GUEST,
        photo_s3_key="visitor-photos/1111/photo_old.jpg",
        created_at=now - timedelta(days=91),
    )
    assert old_record.is_photo_expired is True

    # Purged record
    purged_record = VisitorRecord(
        id=uuid.uuid4(),
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        destination_flat_id=FLAT_1203_ID,
        visitor_name="Purged Visitor",
        phone_number="+919876543292",
        purpose=VisitorPurpose.GUEST,
        photo_s3_key=None,
        photo_purged_at=now,
        created_at=now - timedelta(days=20),
    )
    assert purged_record.is_photo_expired is True
