"""Visitor Domain Service

Core domain service managing visitor operations, gate guard assignments,
resident approvals, decoupled state machine transitions, and structured audit logging.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import String, cast, or_, select
from sqlalchemy.orm import Session

from app.core.errors import (
    AuthorizationError,
    ResourceNotFoundError,
    ValidationError,
)
from app.domains.identity.models import Flat, FlatMembership, MembershipStatus
from app.domains.reliability.models import AuditEvent
from app.domains.visitors.models import (
    ApprovalStatus,
    EntryStatus,
    Gate,
    GateStaffAssignment,
    GateStatus,
    VisitorPurpose,
    VisitorRecord,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_utc(dt: datetime | None) -> datetime:
    if dt is None:
        return datetime.now(UTC)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def mask_phone_number(phone: str) -> str:
    """Sanitizes phone number for audit logging and display:
    E.164 +919876543210 -> +91-XXXXX-XX210
    """
    clean = phone.strip()
    if len(clean) >= 10:
        prefix = clean[:3]
        suffix = clean[-3:]
        return f"{prefix}-XXXXX-XX{suffix}"
    return "+91-XXXXX-XXXXX"


class VisitorService:
    """Domain service for Phase 6 Visitor and Gate operations."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def verify_gate_access(
        self,
        user_id: uuid.UUID,
        society_id: uuid.UUID,
        gate_id: uuid.UUID,
        current_time: datetime | None = None,
    ) -> GateStaffAssignment:
        """Verifies that user is actively assigned to the specified gate in the given society."""
        now = current_time or utc_now()

        # 1. Gate must exist, belong to society, and be active
        gate = self.db.get(Gate, gate_id)
        if not gate:
            gate = self.db.scalars(
                select(Gate).where(
                    or_(
                        cast(Gate.id, String) == str(gate_id),
                        cast(Gate.id, String) == gate_id.hex,
                    )
                )
            ).first()

        if not gate or (
            str(gate.society_id) != str(society_id) and gate.society_id.hex != society_id.hex
        ):
            raise ResourceNotFoundError(
                code="GATE_NOT_FOUND",
                message=f"Gate {gate_id} not found in society {society_id}",
            )
        if gate.status != GateStatus.ACTIVE:
            raise AuthorizationError(
                code="GATE_ACCESS_DENIED",
                message=f"Gate {gate.display_name} is inactive or under maintenance",
            )

        # 2. Query active assignment
        user_cond = or_(
            cast(GateStaffAssignment.user_id, String) == str(user_id),
            cast(GateStaffAssignment.user_id, String) == user_id.hex,
        )
        society_cond = or_(
            cast(GateStaffAssignment.society_id, String) == str(society_id),
            cast(GateStaffAssignment.society_id, String) == society_id.hex,
        )
        gate_cond = or_(
            cast(GateStaffAssignment.gate_id, String) == str(gate_id),
            cast(GateStaffAssignment.gate_id, String) == gate_id.hex,
        )
        stmt = select(GateStaffAssignment).where(
            society_cond,
            user_cond,
            gate_cond,
            GateStaffAssignment.is_active.is_(True),
        )
        assignments = list(self.db.scalars(stmt).all())
        valid_assignment: GateStaffAssignment | None = None
        for a in assignments:
            a_from = ensure_utc(a.assigned_from)
            if a_from > now:
                continue
            if a.assigned_until is not None and ensure_utc(a.assigned_until) < now:
                continue
            valid_assignment = a
            break

        if not valid_assignment:
            raise AuthorizationError(
                code="GATE_ACCESS_DENIED",
                message=f"Staff member is not actively assigned to Gate {gate.gate_number} ({gate.display_name}) for the current shift.",
            )
        return valid_assignment

    def verify_resident_flat_access(
        self,
        user_id: uuid.UUID,
        society_id: uuid.UUID,
        flat_id: uuid.UUID,
        current_time: datetime | None = None,
    ) -> FlatMembership:
        """Verifies that the resident has an active, non-expired, approved membership for flat_id."""
        now = current_time or utc_now()

        stmt = select(FlatMembership).where(
            FlatMembership.user_id == user_id,
            FlatMembership.society_id == society_id,
            FlatMembership.flat_id == flat_id,
            FlatMembership.status == MembershipStatus.APPROVED,
            FlatMembership.valid_from <= now,
            or_(
                FlatMembership.valid_until.is_(None),
                FlatMembership.valid_until >= now,
            ),
        )
        membership = self.db.scalars(stmt).first()
        if not membership:
            raise AuthorizationError(
                code="FLAT_ACCESS_DENIED",
                message=f"You do not hold an active, approved membership for flat {flat_id} in this society.",
            )
        return membership

    def get_visitor_by_id(self, visitor_id: uuid.UUID) -> VisitorRecord | None:
        v = self.db.get(VisitorRecord, visitor_id)
        if v:
            return v
        stmt = select(VisitorRecord).where(
            or_(
                cast(VisitorRecord.id, String) == str(visitor_id),
                cast(VisitorRecord.id, String) == visitor_id.hex,
            )
        )
        return self.db.scalars(stmt).first()

    def get_gate_by_id(self, gate_id: uuid.UUID) -> Gate | None:
        gate = self.db.get(Gate, gate_id)
        if gate:
            return gate
        stmt = select(Gate).where(
            or_(
                cast(Gate.id, String) == str(gate_id),
                cast(Gate.id, String) == gate_id.hex,
            )
        )
        return self.db.scalars(stmt).first()

    def register_visitor(
        self,
        society_id: uuid.UUID,
        gate_id: uuid.UUID,
        guard_user_id: uuid.UUID,
        visitor_name: str,
        phone_number: str,
        purpose: VisitorPurpose,
        destination_flat_id: uuid.UUID,
        vehicle_number: str | None = None,
        privacy_notice_version: str = "v1.0-2026-pune",
        client_event_id: uuid.UUID | None = None,
        photo_s3_key: str | None = None,
        is_offline_creation: bool = False,
        correlation_id: str | None = None,
    ) -> VisitorRecord:
        """Registers a walk-in visitor with decoupled state machines."""
        # Validate gate access for guard
        self.verify_gate_access(guard_user_id, society_id, gate_id)

        # Validate destination flat exists in society
        flat = self.db.get(Flat, destination_flat_id)
        if not flat or flat.society_id != society_id:
            raise ResourceNotFoundError(
                code="FLAT_NOT_FOUND",
                message=f"Destination flat {destination_flat_id} not found in society {society_id}",
            )

        now = utc_now()
        visitor = VisitorRecord(
            id=uuid.uuid4(),
            society_id=society_id,
            gate_id=gate_id,
            destination_flat_id=destination_flat_id,
            destination_tower_id=flat.tower_id,
            visitor_name=visitor_name.strip(),
            phone_number=phone_number.strip(),
            vehicle_number=vehicle_number.strip() if vehicle_number else None,
            purpose=purpose,
            approval_status=ApprovalStatus.PENDING,
            entry_status=EntryStatus.EXPECTED,
            photo_s3_key=photo_s3_key,
            photo_storage_key=photo_s3_key,
            photo_captured_at=now if photo_s3_key else None,
            privacy_notice_version=privacy_notice_version,
            client_event_id=client_event_id,
            is_offline_creation=is_offline_creation,
            created_at=now,
            updated_at=now,
        )
        self.db.add(visitor)
        self.db.flush()

        # Audit event
        audit = AuditEvent(
            id=uuid.uuid4(),
            society_id=society_id,
            actor_id=guard_user_id,
            action="VISITOR_REGISTERED",
            resource_type="visitor_record",
            resource_id=str(visitor.id),
            correlation_id=correlation_id or str(uuid.uuid4()),
            event_metadata={
                "gate_id": str(gate_id),
                "destination_flat_id": str(destination_flat_id),
                "visitor_name": visitor.visitor_name,
                "phone_masked": mask_phone_number(visitor.phone_number),
                "purpose": visitor.purpose.value,
                "vehicle_number": visitor.vehicle_number,
                "privacy_notice_version": visitor.privacy_notice_version,
                "approval_status": ApprovalStatus.PENDING.value,
                "entry_status": EntryStatus.EXPECTED.value,
            },
        )
        self.db.add(audit)
        self.db.flush()
        return visitor

    def handle_resident_action(
        self,
        visitor_id: uuid.UUID,
        action: str,
        resident_user_id: uuid.UUID,
        reason: str | None = None,
        correlation_id: str | None = None,
    ) -> VisitorRecord:
        """Processes resident approval or rejection with strict state guards and idempotency."""
        visitor = self.get_visitor_by_id(visitor_id)
        if not visitor:
            raise ResourceNotFoundError(
                code="VISITOR_NOT_FOUND",
                message=f"Visitor record {visitor_id} not found",
            )

        # Enforce resident active flat membership
        self.verify_resident_flat_access(
            user_id=resident_user_id,
            society_id=visitor.society_id,
            flat_id=visitor.destination_flat_id,
        )

        norm_action = action.upper().strip()
        if norm_action not in ("APPROVE", "REJECT"):
            raise ValidationError(
                code="INVALID_ACTION",
                message=f"Invalid action '{action}'. Must be 'APPROVE' or 'REJECT'.",
            )

        # Check physical presence invariants
        if visitor.entry_status == EntryStatus.CHECKED_IN and norm_action == "REJECT":
            raise ValidationError(
                code="INVALID_STATE_TRANSITION",
                message="Cannot reject a visitor who has already checked in to the premises",
            )
        if visitor.entry_status == EntryStatus.CHECKED_OUT:
            raise ValidationError(
                code="INVALID_STATE_TRANSITION",
                message="Cannot mutate approval status of a checked-out visitor",
            )

        # Check approval status invariants
        if visitor.approval_status == ApprovalStatus.REJECTED and norm_action == "APPROVE":
            raise ValidationError(
                code="INVALID_STATE_TRANSITION",
                message="Cannot approve a previously rejected visitor registration",
            )
        if visitor.approval_status == ApprovalStatus.AUTO_APPROVED and norm_action == "REJECT":
            raise ValidationError(
                code="INVALID_STATE_TRANSITION",
                message="Cannot reject a pre-approved guest pass redemption",
            )

        # Idempotency check: no-op if status already matches requested action
        if visitor.approval_status == ApprovalStatus.APPROVED and norm_action == "APPROVE":
            return visitor
        if visitor.approval_status == ApprovalStatus.REJECTED and norm_action == "REJECT":
            return visitor

        now = utc_now()
        if norm_action == "APPROVE":
            visitor.approval_status = ApprovalStatus.APPROVED
            visitor.approved_by_user_id = resident_user_id
            visitor.approval_action_at = now
            visitor.updated_at = now
            audit_action = "VISITOR_APPROVED"
            audit_metadata: dict[str, Any] = {
                "destination_flat_id": str(visitor.destination_flat_id),
                "previous_approval_status": ApprovalStatus.PENDING.value,
                "new_approval_status": ApprovalStatus.APPROVED.value,
                "approved_at": now.isoformat(),
            }
        else:
            visitor.approval_status = ApprovalStatus.REJECTED
            visitor.approved_by_user_id = resident_user_id
            visitor.approval_action_at = now
            visitor.approval_rejection_reason = reason
            visitor.updated_at = now
            audit_action = "VISITOR_REJECTED"
            audit_metadata = {
                "destination_flat_id": str(visitor.destination_flat_id),
                "previous_approval_status": ApprovalStatus.PENDING.value,
                "new_approval_status": ApprovalStatus.REJECTED.value,
                "reason": reason or "No reason provided",
                "rejected_at": now.isoformat(),
            }

        audit = AuditEvent(
            id=uuid.uuid4(),
            society_id=visitor.society_id,
            actor_id=resident_user_id,
            action=audit_action,
            resource_type="visitor_record",
            resource_id=str(visitor.id),
            correlation_id=correlation_id or str(uuid.uuid4()),
            event_metadata=audit_metadata,
        )
        self.db.add(audit)
        self.db.flush()
        return visitor

    def check_in_visitor(
        self,
        visitor_id: uuid.UUID,
        gate_id: uuid.UUID,
        guard_user_id: uuid.UUID,
        correlation_id: str | None = None,
    ) -> VisitorRecord:
        """Physical check-in at gate. Precondition: APPROVED or AUTO_APPROVED and EXPECTED."""
        visitor = self.get_visitor_by_id(visitor_id)
        if not visitor:
            raise ResourceNotFoundError(
                code="VISITOR_NOT_FOUND",
                message=f"Visitor record {visitor_id} not found",
            )

        # Validate gate operator assignment
        self.verify_gate_access(guard_user_id, visitor.society_id, gate_id)

        # Precondition checks
        if visitor.entry_status == EntryStatus.CHECKED_IN:
            raise ValidationError(
                code="VISITOR_ALREADY_CHECKED_IN",
                message="Visitor is already checked in to the premises",
            )
        if visitor.entry_status == EntryStatus.CHECKED_OUT:
            raise ValidationError(
                code="INVALID_STATE_TRANSITION",
                message="Cannot check in a visitor who has already checked out",
            )
        if visitor.approval_status == ApprovalStatus.PENDING:
            raise ValidationError(
                code="VISITOR_APPROVAL_PENDING",
                message="Visitor entry requires explicit resident approval before check-in",
            )
        if visitor.approval_status == ApprovalStatus.REJECTED:
            raise ValidationError(
                code="VISITOR_REJECTED",
                message="Visitor entry was rejected by resident and cannot be admitted",
            )

        now = utc_now()
        visitor.entry_status = EntryStatus.CHECKED_IN
        visitor.entry_gate_id = gate_id
        visitor.entry_guard_user_id = guard_user_id
        visitor.entry_time = now
        visitor.updated_at = now

        audit = AuditEvent(
            id=uuid.uuid4(),
            society_id=visitor.society_id,
            actor_id=guard_user_id,
            action="VISITOR_CHECKED_IN",
            resource_type="visitor_record",
            resource_id=str(visitor.id),
            correlation_id=correlation_id or str(uuid.uuid4()),
            event_metadata={
                "entry_gate_id": str(gate_id),
                "entry_time": now.isoformat(),
                "approval_status": visitor.approval_status.value,
                "guest_pass_id": str(visitor.guest_pass_id) if visitor.guest_pass_id else None,
            },
        )
        self.db.add(audit)
        self.db.flush()
        return visitor

    def check_out_visitor(
        self,
        visitor_id: uuid.UUID,
        gate_id: uuid.UUID,
        guard_user_id: uuid.UUID,
        correlation_id: str | None = None,
    ) -> VisitorRecord:
        """Physical check-out at gate. Precondition: CHECKED_IN."""
        visitor = self.get_visitor_by_id(visitor_id)
        if not visitor:
            raise ResourceNotFoundError(
                code="VISITOR_NOT_FOUND",
                message=f"Visitor record {visitor_id} not found",
            )

        # Validate gate operator assignment
        self.verify_gate_access(guard_user_id, visitor.society_id, gate_id)

        # Precondition checks
        if visitor.entry_status != EntryStatus.CHECKED_IN:
            raise ValidationError(
                code="INVALID_STATE_TRANSITION",
                message=f"Cannot check out visitor with entry status '{visitor.entry_status.value}'. Must be CHECKED_IN.",
            )

        now = utc_now()
        visitor.entry_status = EntryStatus.CHECKED_OUT
        visitor.exit_gate_id = gate_id
        visitor.exit_guard_user_id = guard_user_id
        visitor.exit_time = now
        visitor.updated_at = now

        duration_mins: float | None = None
        if visitor.entry_time:
            duration_mins = round((now - ensure_utc(visitor.entry_time)).total_seconds() / 60.0, 1)

        audit = AuditEvent(
            id=uuid.uuid4(),
            society_id=visitor.society_id,
            actor_id=guard_user_id,
            action="VISITOR_CHECKED_OUT",
            resource_type="visitor_record",
            resource_id=str(visitor.id),
            correlation_id=correlation_id or str(uuid.uuid4()),
            event_metadata={
                "entry_gate_id": str(visitor.entry_gate_id) if visitor.entry_gate_id else None,
                "exit_gate_id": str(gate_id),
                "entry_time": visitor.entry_time.isoformat() if visitor.entry_time else None,
                "exit_time": now.isoformat(),
                "duration_minutes": duration_mins,
            },
        )
        self.db.add(audit)
        self.db.flush()
        return visitor
