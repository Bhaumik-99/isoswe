"""Empirical Adversarial Test Suite for Milestone 1: Visitor Domain Schema & Decoupled State Machines

Targeted Challenges:
- Challenge 1: Invalid state transitions. Attempt check-in on visitor whose approval_status == 'PENDING'.
               Must raise ValidationError with code 'VISITOR_APPROVAL_PENDING'.
- Challenge 2: Attempt check-in on rejected visitor (approval_status == 'REJECTED').
               Must raise ValidationError with code 'VISITOR_REJECTED'.
- Challenge 3: Attempt check-out on visitor who has not checked in (entry_status == 'EXPECTED').
               Must raise ValidationError with code 'INVALID_STATE_TRANSITION'.
- Challenge 4: Attempt duplicate check-in on an already checked-in visitor.
               Must raise ValidationError with code 'VISITOR_ALREADY_CHECKED_IN'.
- Challenge 5: Attempt to register visitor for flat belonging to a different society.
               Must reject with tenant isolation error ('FLAT_NOT_FOUND').

Extended Adversarial Scenarios:
- Challenge 6: Attempt check-in on checked-out visitor. Must raise 'INVALID_STATE_TRANSITION'.
- Challenge 7: Attempt duplicate check-out on already checked-out visitor. Must raise 'INVALID_STATE_TRANSITION'.
- Challenge 8: Unassigned gate guard access violation during check-in. Must raise 'GATE_ACCESS_DENIED'.
- Challenge 9: Guard outside shift window during check-in. Must raise 'GATE_ACCESS_DENIED'.
- Challenge 10: Cross-flat unauthorized approval attempt. Must raise 'FLAT_ACCESS_DENIED'.
- Challenge 11: Expired lease tenant approval attempt. Must raise 'FLAT_ACCESS_DENIED'.
- Challenge 12: Resident attempts to approve previously rejected visitor. Must raise 'INVALID_STATE_TRANSITION'.
- Challenge 13: Resident attempts to reject already checked-in visitor. Must raise 'INVALID_STATE_TRANSITION'.
- Challenge 14: Non-existent gate ID during check-in. Must raise 'GATE_NOT_FOUND'.
- Challenge 15: Cross-society gate access violation. Must raise 'GATE_NOT_FOUND' / 'GATE_ACCESS_DENIED'.
- Challenge 16: Database level integrity check constraints:
    - Inverted assignment dates (assigned_until < assigned_from)
    - Inverted visitor transit times (exit_time < entry_time)
    - Overflowing guest pass usage (used_count > max_uses)
    - Inverted pass validity dates (valid_until < valid_from)
- Challenge 17: PII leakage check: Raw phone number never leaked unmasked in AuditEvent metadata.
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
from app.domains.reliability.models import AuditEvent
from app.domains.visitors.models import (
    ApprovalStatus,
    EntryStatus,
    GateStaffAssignment,
    GuestPass,
    PassStatus,
    PassType,
    VisitorPurpose,
    VisitorRecord,
)
from app.domains.visitors.service import VisitorService

SOCIETY_PUNE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
GATE_1_ID = uuid.UUID("aaaaaaaa-1111-0000-0000-000000000001")
GATE_2_ID = uuid.UUID("aaaaaaaa-2222-0000-0000-000000000002")
FLAT_1203_ID = uuid.UUID("33333333-3333-3333-3333-333333331203")
FLAT_0408_ID = uuid.UUID("33333333-3333-3333-3333-333333330408")
USER_NEERAJ_ID = uuid.UUID("44444444-4444-4444-4444-444444440001")
USER_SWATI_ID = uuid.UUID("44444444-4444-4444-4444-444444440002")
USER_HELPDESK_ID = uuid.UUID("44444444-4444-4444-4444-444444440004")


def test_adversarial_challenge_1_checkin_pending_rejected(db_session: Session) -> None:
    """Challenge 1: Attempt check-in on a visitor whose approval_status == 'PENDING'.
    Must raise ValidationError with code 'VISITOR_APPROVAL_PENDING'.
    """
    service = VisitorService(db_session)
    visitor = service.register_visitor(
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        guard_user_id=USER_HELPDESK_ID,
        visitor_name="Pending Guest",
        phone_number="+919876543220",
        purpose=VisitorPurpose.GUEST,
        destination_flat_id=FLAT_1203_ID,
    )
    db_session.flush()

    assert visitor.approval_status == ApprovalStatus.PENDING
    assert visitor.entry_status == EntryStatus.EXPECTED

    with pytest.raises(ValidationError) as exc_info:
        service.check_in_visitor(
            visitor_id=visitor.id,
            gate_id=GATE_1_ID,
            guard_user_id=USER_HELPDESK_ID,
        )
    assert exc_info.value.code == "VISITOR_APPROVAL_PENDING"
    assert "explicit resident approval" in str(exc_info.value.message)


def test_adversarial_challenge_2_checkin_rejected_visitor(db_session: Session) -> None:
    """Challenge 2: Attempt check-in on a rejected visitor (approval_status == 'REJECTED').
    Must raise ValidationError with code 'VISITOR_REJECTED'.
    """
    service = VisitorService(db_session)
    visitor = service.register_visitor(
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        guard_user_id=USER_HELPDESK_ID,
        visitor_name="Rejected Delivery",
        phone_number="+919876543221",
        purpose=VisitorPurpose.DELIVERY,
        destination_flat_id=FLAT_1203_ID,
    )
    db_session.flush()

    # Reject visitor
    service.handle_resident_action(
        visitor_id=visitor.id,
        action="REJECT",
        resident_user_id=USER_NEERAJ_ID,
        reason="Suspicious delivery",
    )
    db_session.flush()

    assert visitor.approval_status == ApprovalStatus.REJECTED

    with pytest.raises(ValidationError) as exc_info:
        service.check_in_visitor(
            visitor_id=visitor.id,
            gate_id=GATE_1_ID,
            guard_user_id=USER_HELPDESK_ID,
        )
    assert exc_info.value.code == "VISITOR_REJECTED"
    assert "rejected by resident" in str(exc_info.value.message)


def test_adversarial_challenge_3_checkout_without_checkin(db_session: Session) -> None:
    """Challenge 3: Attempt check-out on a visitor who has not checked in (entry_status == 'EXPECTED').
    Must raise ValidationError with code 'INVALID_STATE_TRANSITION'.
    """
    service = VisitorService(db_session)
    visitor = service.register_visitor(
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        guard_user_id=USER_HELPDESK_ID,
        visitor_name="Expected Guest",
        phone_number="+919876543222",
        purpose=VisitorPurpose.GUEST,
        destination_flat_id=FLAT_1203_ID,
    )
    db_session.flush()

    # Even if approved, entry_status is EXPECTED
    service.handle_resident_action(visitor.id, "APPROVE", USER_NEERAJ_ID)
    db_session.flush()
    assert visitor.entry_status == EntryStatus.EXPECTED

    with pytest.raises(ValidationError) as exc_info:
        service.check_out_visitor(
            visitor_id=visitor.id,
            gate_id=GATE_1_ID,
            guard_user_id=USER_HELPDESK_ID,
        )
    assert exc_info.value.code == "INVALID_STATE_TRANSITION"
    assert "Must be CHECKED_IN" in str(exc_info.value.message)


def test_adversarial_challenge_4_duplicate_checkin(db_session: Session) -> None:
    """Challenge 4: Attempt duplicate check-in on an already checked-in visitor.
    Must raise ValidationError with code 'VISITOR_ALREADY_CHECKED_IN'.
    """
    service = VisitorService(db_session)
    visitor = service.register_visitor(
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        guard_user_id=USER_HELPDESK_ID,
        visitor_name="Checked In Guest",
        phone_number="+919876543223",
        purpose=VisitorPurpose.CAB,
        destination_flat_id=FLAT_1203_ID,
    )
    service.handle_resident_action(visitor.id, "APPROVE", USER_NEERAJ_ID)
    service.check_in_visitor(visitor.id, GATE_1_ID, USER_HELPDESK_ID)
    db_session.flush()

    assert visitor.entry_status == EntryStatus.CHECKED_IN

    with pytest.raises(ValidationError) as exc_info:
        service.check_in_visitor(
            visitor_id=visitor.id,
            gate_id=GATE_1_ID,
            guard_user_id=USER_HELPDESK_ID,
        )
    assert exc_info.value.code == "VISITOR_ALREADY_CHECKED_IN"


def test_adversarial_challenge_5_cross_society_flat_registration(db_session: Session) -> None:
    """Challenge 5: Attempt to register visitor for flat belonging to a different society.
    Must reject with tenant isolation error ('FLAT_NOT_FOUND').
    """
    service = VisitorService(db_session)
    now = datetime.now(UTC)

    # Create a secondary society and flat
    foreign_society_id = uuid.uuid4()
    foreign_society = Society(
        id=foreign_society_id,
        name="Foreign Township",
        status=SocietyStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    foreign_tower = Tower(
        id=uuid.uuid4(),
        society_id=foreign_society_id,
        tower_number="T1",
        name="Tower 1",
        created_at=now,
    )
    foreign_flat = Flat(
        id=uuid.uuid4(),
        society_id=foreign_society_id,
        tower_id=foreign_tower.id,
        flat_number="F-101",
        area_sqft=1100,
        status=FlatStatus.OCCUPIED,
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([foreign_society, foreign_tower, foreign_flat])
    db_session.flush()

    # Attempt to register in SOCIETY_PUNE_ID targeting foreign_flat.id: rejected
    with pytest.raises(ResourceNotFoundError) as exc_info:
        service.register_visitor(
            society_id=SOCIETY_PUNE_ID,
            gate_id=GATE_1_ID,
            guard_user_id=USER_HELPDESK_ID,
            visitor_name="Cross Society Intruder",
            phone_number="+919876543224",
            purpose=VisitorPurpose.GUEST,
            destination_flat_id=foreign_flat.id,
        )
    assert exc_info.value.code == "FLAT_NOT_FOUND"
    assert "not found in society" in str(exc_info.value.message)


def test_adversarial_challenge_6_checkin_checked_out_visitor(db_session: Session) -> None:
    """Challenge 6: Attempt check-in on a visitor who has already checked out.
    Must raise ValidationError with code 'INVALID_STATE_TRANSITION'.
    """
    service = VisitorService(db_session)
    visitor = service.register_visitor(
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        guard_user_id=USER_HELPDESK_ID,
        visitor_name="Checked Out Visitor",
        phone_number="+919876543225",
        purpose=VisitorPurpose.SERVICE_MAINTENANCE,
        destination_flat_id=FLAT_1203_ID,
    )
    service.handle_resident_action(visitor.id, "APPROVE", USER_NEERAJ_ID)
    service.check_in_visitor(visitor.id, GATE_1_ID, USER_HELPDESK_ID)
    service.check_out_visitor(visitor.id, GATE_1_ID, USER_HELPDESK_ID)
    db_session.flush()

    assert visitor.entry_status == EntryStatus.CHECKED_OUT

    with pytest.raises(ValidationError) as exc_info:
        service.check_in_visitor(
            visitor_id=visitor.id,
            gate_id=GATE_1_ID,
            guard_user_id=USER_HELPDESK_ID,
        )
    assert exc_info.value.code == "INVALID_STATE_TRANSITION"
    assert "already checked out" in str(exc_info.value.message)


def test_adversarial_challenge_7_duplicate_checkout(db_session: Session) -> None:
    """Challenge 7: Attempt duplicate check-out on an already checked-out visitor.
    Must raise ValidationError with code 'INVALID_STATE_TRANSITION'.
    """
    service = VisitorService(db_session)
    visitor = service.register_visitor(
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        guard_user_id=USER_HELPDESK_ID,
        visitor_name="Duplicate Checkout Guest",
        phone_number="+919876543226",
        purpose=VisitorPurpose.GUEST,
        destination_flat_id=FLAT_1203_ID,
    )
    service.handle_resident_action(visitor.id, "APPROVE", USER_NEERAJ_ID)
    service.check_in_visitor(visitor.id, GATE_1_ID, USER_HELPDESK_ID)
    service.check_out_visitor(visitor.id, GATE_1_ID, USER_HELPDESK_ID)
    db_session.flush()

    with pytest.raises(ValidationError) as exc_info:
        service.check_out_visitor(
            visitor_id=visitor.id,
            gate_id=GATE_1_ID,
            guard_user_id=USER_HELPDESK_ID,
        )
    assert exc_info.value.code == "INVALID_STATE_TRANSITION"


def test_adversarial_challenge_8_unassigned_gate_checkin(db_session: Session) -> None:
    """Challenge 8: Guard assigned to Gate 1 attempts to check in visitor at Gate 2 without assignment.
    Must raise AuthorizationError with code 'GATE_ACCESS_DENIED'.
    """
    service = VisitorService(db_session)
    visitor = service.register_visitor(
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        guard_user_id=USER_HELPDESK_ID,
        visitor_name="Gate 1 Guest",
        phone_number="+919876543227",
        purpose=VisitorPurpose.GUEST,
        destination_flat_id=FLAT_1203_ID,
    )
    service.handle_resident_action(visitor.id, "APPROVE", USER_NEERAJ_ID)
    db_session.flush()

    # USER_HELPDESK is assigned to GATE_1_ID only; attempt check-in at GATE_2_ID: denied
    with pytest.raises(AuthorizationError) as exc_info:
        service.check_in_visitor(
            visitor_id=visitor.id,
            gate_id=GATE_2_ID,
            guard_user_id=USER_HELPDESK_ID,
        )
    assert exc_info.value.code == "GATE_ACCESS_DENIED"


def test_adversarial_challenge_9_expired_guard_shift(db_session: Session) -> None:
    """Challenge 9: Guard with expired shift assignment attempts check-in.
    Must raise AuthorizationError with code 'GATE_ACCESS_DENIED'.
    """
    service = VisitorService(db_session)
    now = datetime.now(UTC)

    expired_guard = User(
        id=uuid.uuid4(),
        supabase_uid=uuid.uuid4(),
        email="shift.expired@example.com",
        phone="+91-98765-88888",
        full_name="Shift Expired Guard",
        status=UserStatus.ACTIVE,
    )
    db_session.add(expired_guard)
    db_session.add(
        GateStaffAssignment(
            id=uuid.uuid4(),
            society_id=SOCIETY_PUNE_ID,
            gate_id=GATE_1_ID,
            user_id=expired_guard.id,
            assigned_from=now - timedelta(hours=8),
            assigned_until=now - timedelta(minutes=1),  # shift ended 1 min ago
            is_active=True,
        )
    )
    db_session.flush()

    visitor = service.register_visitor(
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        guard_user_id=USER_HELPDESK_ID,
        visitor_name="Shift Test Guest",
        phone_number="+919876543228",
        purpose=VisitorPurpose.GUEST,
        destination_flat_id=FLAT_1203_ID,
    )
    service.handle_resident_action(visitor.id, "APPROVE", USER_NEERAJ_ID)
    db_session.flush()

    with pytest.raises(AuthorizationError) as exc_info:
        service.check_in_visitor(
            visitor_id=visitor.id,
            gate_id=GATE_1_ID,
            guard_user_id=expired_guard.id,
        )
    assert exc_info.value.code == "GATE_ACCESS_DENIED"


def test_adversarial_challenge_10_cross_flat_unauthorized_approval(db_session: Session) -> None:
    """Challenge 10: Resident of Flat A attempts to approve visitor bound for Flat B.
    Must raise AuthorizationError with code 'FLAT_ACCESS_DENIED'.
    """
    service = VisitorService(db_session)
    visitor = service.register_visitor(
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        guard_user_id=USER_HELPDESK_ID,
        visitor_name="Swati's Private Guest",
        phone_number="+919876543229",
        purpose=VisitorPurpose.GUEST,
        destination_flat_id=FLAT_0408_ID,  # Swati's flat
    )
    db_session.flush()

    # Neeraj (resident of 1203) attempts approval: denied
    with pytest.raises(AuthorizationError) as exc_info:
        service.handle_resident_action(
            visitor_id=visitor.id,
            action="APPROVE",
            resident_user_id=USER_NEERAJ_ID,
        )
    assert exc_info.value.code == "FLAT_ACCESS_DENIED"


def test_adversarial_challenge_11_expired_lease_resident_approval(db_session: Session) -> None:
    """Challenge 11: Resident with expired lease attempts to approve visitor.
    Must raise AuthorizationError with code 'FLAT_ACCESS_DENIED'.
    """
    service = VisitorService(db_session)
    now = datetime.now(UTC)

    expired_tenant = User(
        id=uuid.uuid4(),
        supabase_uid=uuid.uuid4(),
        email="past.tenant.approval@example.com",
        phone="+91-98765-77777",
        full_name="Past Tenant Approver",
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
    db_session.add(
        FlatMembership(
            id=uuid.uuid4(),
            society_id=SOCIETY_PUNE_ID,
            user_id=expired_tenant.id,
            flat_id=FLAT_1203_ID,
            membership_type=MembershipType.TENANT,
            valid_from=now - timedelta(days=200),
            valid_until=now - timedelta(days=5),  # expired 5 days ago
            status=MembershipStatus.APPROVED,
        )
    )
    db_session.flush()

    visitor = service.register_visitor(
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        guard_user_id=USER_HELPDESK_ID,
        visitor_name="Lease Test Guest",
        phone_number="+919876543230",
        purpose=VisitorPurpose.GUEST,
        destination_flat_id=FLAT_1203_ID,
    )
    db_session.flush()

    with pytest.raises(AuthorizationError) as exc_info:
        service.handle_resident_action(
            visitor_id=visitor.id,
            action="APPROVE",
            resident_user_id=expired_tenant.id,
        )
    assert exc_info.value.code == "FLAT_ACCESS_DENIED"


def test_adversarial_challenge_12_reapproval_of_rejected_visitor_prohibited(
    db_session: Session,
) -> None:
    """Challenge 12: Resident attempts to approve a visitor that was previously rejected.
    Must raise ValidationError with code 'INVALID_STATE_TRANSITION'.
    """
    service = VisitorService(db_session)
    visitor = service.register_visitor(
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        guard_user_id=USER_HELPDESK_ID,
        visitor_name="Rejected Then Approved",
        phone_number="+919876543231",
        purpose=VisitorPurpose.DELIVERY,
        destination_flat_id=FLAT_1203_ID,
    )
    service.handle_resident_action(
        visitor_id=visitor.id,
        action="REJECT",
        resident_user_id=USER_NEERAJ_ID,
        reason="Initial rejection",
    )
    db_session.flush()

    with pytest.raises(ValidationError) as exc_info:
        service.handle_resident_action(
            visitor_id=visitor.id,
            action="APPROVE",
            resident_user_id=USER_NEERAJ_ID,
        )
    assert exc_info.value.code == "INVALID_STATE_TRANSITION"
    assert "Cannot approve a previously rejected" in str(exc_info.value.message)


def test_adversarial_challenge_13_rejection_of_checkedin_visitor_prohibited(
    db_session: Session,
) -> None:
    """Challenge 13: Resident attempts to reject a visitor who is already physically checked in.
    Must raise ValidationError with code 'INVALID_STATE_TRANSITION'.
    """
    service = VisitorService(db_session)
    visitor = service.register_visitor(
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        guard_user_id=USER_HELPDESK_ID,
        visitor_name="Checked In Rejection Test",
        phone_number="+919876543232",
        purpose=VisitorPurpose.GUEST,
        destination_flat_id=FLAT_1203_ID,
    )
    service.handle_resident_action(visitor.id, "APPROVE", USER_NEERAJ_ID)
    service.check_in_visitor(visitor.id, GATE_1_ID, USER_HELPDESK_ID)
    db_session.flush()

    with pytest.raises(ValidationError) as exc_info:
        service.handle_resident_action(
            visitor_id=visitor.id,
            action="REJECT",
            resident_user_id=USER_NEERAJ_ID,
        )
    assert exc_info.value.code == "INVALID_STATE_TRANSITION"
    assert "already checked in" in str(exc_info.value.message)


def test_adversarial_challenge_14_nonexistent_gate(db_session: Session) -> None:
    """Challenge 14: Non-existent gate ID during check-in.
    Must raise ResourceNotFoundError with code 'GATE_NOT_FOUND'.
    """
    service = VisitorService(db_session)
    visitor = service.register_visitor(
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        guard_user_id=USER_HELPDESK_ID,
        visitor_name="Nonexistent Gate Test",
        phone_number="+919876543233",
        purpose=VisitorPurpose.GUEST,
        destination_flat_id=FLAT_1203_ID,
    )
    service.handle_resident_action(visitor.id, "APPROVE", USER_NEERAJ_ID)
    db_session.flush()

    random_gate_id = uuid.uuid4()
    with pytest.raises(ResourceNotFoundError) as exc_info:
        service.check_in_visitor(
            visitor_id=visitor.id,
            gate_id=random_gate_id,
            guard_user_id=USER_HELPDESK_ID,
        )
    assert exc_info.value.code == "GATE_NOT_FOUND"


def test_adversarial_challenge_15_database_check_constraints(db_session: Session) -> None:
    """Challenge 15: Verifies database check constraints reject corrupt and inverted records.
    - Assigned shift inverted: assigned_until < assigned_from
    - Visitor transit inverted: exit_time < entry_time
    - Guest pass overflow: used_count > max_uses
    - Guest pass inverted validity: valid_until < valid_from
    """
    now = datetime.now(UTC)

    # 1. Inverted gate assignment shift
    bad_assignment = GateStaffAssignment(
        id=uuid.uuid4(),
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        user_id=USER_HELPDESK_ID,
        assigned_from=now + timedelta(hours=5),
        assigned_until=now + timedelta(hours=1),  # until < from
        is_active=True,
    )
    db_session.add(bad_assignment)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

    # 2. Inverted visitor transit times
    bad_visitor = VisitorRecord(
        id=uuid.uuid4(),
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        destination_flat_id=FLAT_1203_ID,
        visitor_name="Time Traveler",
        phone_number="+919876543234",
        purpose=VisitorPurpose.GUEST,
        entry_time=now + timedelta(hours=2),
        exit_time=now,  # exit before entry
        created_at=now,
        updated_at=now,
    )
    db_session.add(bad_visitor)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

    # 3. Guest pass used_count overflow
    bad_pass = GuestPass(
        id=uuid.uuid4(),
        society_id=SOCIETY_PUNE_ID,
        destination_flat_id=FLAT_1203_ID,
        created_by_user_id=USER_NEERAJ_ID,
        guest_name="Overflow Guest",
        purpose="Party",
        pass_type=PassType.SINGLE_USE,
        pass_code_hash="unique_hash_9999",
        status=PassStatus.ACTIVE,
        max_uses=1,
        used_count=2,  # used_count > max_uses
        valid_from=now,
        valid_until=now + timedelta(hours=2),
    )
    db_session.add(bad_pass)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

    # 4. Inverted guest pass validity
    bad_validity_pass = GuestPass(
        id=uuid.uuid4(),
        society_id=SOCIETY_PUNE_ID,
        destination_flat_id=FLAT_1203_ID,
        created_by_user_id=USER_NEERAJ_ID,
        guest_name="Inverted Validity Guest",
        purpose="Party",
        pass_type=PassType.SINGLE_USE,
        pass_code_hash="unique_hash_8888",
        status=PassStatus.ACTIVE,
        max_uses=1,
        used_count=0,
        valid_from=now + timedelta(days=2),
        valid_until=now + timedelta(days=1),  # until < from
    )
    db_session.add(bad_validity_pass)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_adversarial_challenge_16_pii_sanitization_in_audit(db_session: Session) -> None:
    """Challenge 16: Raw visitor phone number (+919876543299) must NOT appear unmasked in AuditEvent metadata."""
    service = VisitorService(db_session)
    raw_phone = "+919876543299"

    visitor = service.register_visitor(
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        guard_user_id=USER_HELPDESK_ID,
        visitor_name="Secret VIP",
        phone_number=raw_phone,
        purpose=VisitorPurpose.GUEST,
        destination_flat_id=FLAT_1203_ID,
    )
    db_session.commit()

    audit = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.resource_id == str(visitor.id),
            AuditEvent.action == "VISITOR_REGISTERED",
        )
    )
    assert audit is not None
    assert audit.event_metadata["phone_masked"] == "+91-XXXXX-XX299"
    # Verify raw number never appears anywhere in the serialized audit event metadata
    assert "9876543299" not in str(audit.event_metadata)
    assert raw_phone not in str(audit.event_metadata)
