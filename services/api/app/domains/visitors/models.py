"""Visitor Domain SQLAlchemy Models

Defines persistent models for ISOSWE Phase 6 perimeter security and visitor operations:
- Gate: Physical gate entrance configuration (Gates 1–4)
- GateStaffAssignment: Guard staff-to-gate assignments with temporal shift validity
- GuestPass: Resident pre-approved visitor passes with salted SHA-256 hash storage
- VisitorRecord: Full walk-in and pre-approved visitor lifecycle tracking
- GuestPassRedemption: Immutable audit log for pass usage at gates
- OfflineSyncEvent: Idempotent synchronization registry for tablet offline operations
"""

import enum
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import expression

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class GateStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    MAINTENANCE = "MAINTENANCE"


class VisitorPurpose(str, enum.Enum):
    GUEST = "GUEST"
    DELIVERY = "DELIVERY"
    CAB = "CAB"
    SERVICE_MAINTENANCE = "SERVICE_MAINTENANCE"
    EMERGENCY = "EMERGENCY"
    OTHER = "OTHER"


class ApprovalStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    AUTO_APPROVED = "AUTO_APPROVED"


class EntryStatus(str, enum.Enum):
    EXPECTED = "EXPECTED"
    CHECKED_IN = "CHECKED_IN"
    CHECKED_OUT = "CHECKED_OUT"


class PassType(str, enum.Enum):
    SINGLE_USE = "SINGLE_USE"
    MULTI_USE = "MULTI_USE"


class PassStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    EXHAUSTED = "EXHAUSTED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class SyncStatus(str, enum.Enum):
    ACK = "ACK"
    CONFLICT = "CONFLICT"
    FAILED = "FAILED"


class Gate(Base):
    """Physical gate entity bound to a society."""

    __tablename__ = "gates"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    gate_number: Mapped[int] = mapped_column(Integer, nullable=False)
    gate_name: Mapped[str | None] = mapped_column(String(128), nullable=True, default="Main Gate")
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[GateStatus] = mapped_column(
        SAEnum(GateStatus, native_enum=False),
        nullable=False,
        default=GateStatus.ACTIVE,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("society_id", "gate_number", name="uq_gate_society_number"),
        CheckConstraint("gate_number >= 1", name="chk_gate_number_positive"),
        Index("ix_gates_society_status", "society_id", "status"),
    )

    # Relationships
    assignments: Mapped[list["GateStaffAssignment"]] = relationship(
        "GateStaffAssignment", back_populates="gate", cascade="all, delete-orphan"
    )
    visitor_records: Mapped[list["VisitorRecord"]] = relationship(
        "VisitorRecord", foreign_keys="VisitorRecord.gate_id", back_populates="gate"
    )

    @property
    def is_active(self) -> bool:
        return self.status == GateStatus.ACTIVE

    @property
    def display_name(self) -> str:
        return self.gate_name or self.name or f"Gate {self.gate_number}"


class GateStaffAssignment(Base):
    """Temporal assignment of a helpdesk staff guard to a specific gate."""

    __tablename__ = "gate_assignments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    gate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("gates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assigned_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    assigned_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "assigned_until IS NULL OR assigned_until >= assigned_from",
            name="chk_gate_assignment_dates",
        ),
        Index("ix_gate_assignments_user_active", "user_id", "is_active"),
        Index("ix_gate_assignments_gate_active", "gate_id", "is_active"),
        Index("ix_gate_assignments_society_gate", "society_id", "gate_id"),
        Index(
            "ix_gate_assignments_auth_lookup",
            "user_id",
            "society_id",
            "gate_id",
            "is_active",
        ),
    )

    # Relationships
    gate: Mapped["Gate"] = relationship("Gate", back_populates="assignments")


class GuestPass(Base):
    """Pre-approved visitor pass issued by a verified flat resident."""

    __tablename__ = "guest_passes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    destination_flat_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("flats.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    flat_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("flats.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    guest_name: Mapped[str] = mapped_column(String(255), nullable=False)
    guest_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    purpose: Mapped[str] = mapped_column(String(255), nullable=False)
    pass_type: Mapped[PassType] = mapped_column(SAEnum(PassType, native_enum=False), nullable=False)
    pass_code_prefix: Mapped[str | None] = mapped_column(String(16), nullable=True, default="GP-")
    pass_code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[PassStatus] = mapped_column(
        SAEnum(PassStatus, native_enum=False),
        nullable=False,
        default=PassStatus.ACTIVE,
    )
    max_uses: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    used_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    revocation_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("society_id", "pass_code_hash", name="uq_guest_pass_society_hash"),
        CheckConstraint("max_uses >= 1", name="chk_guest_pass_max_uses"),
        CheckConstraint(
            "used_count >= 0 AND used_count <= max_uses", name="chk_guest_pass_used_count"
        ),
        CheckConstraint("valid_until >= valid_from", name="chk_guest_pass_validity"),
        Index("ix_guest_passes_hash_lookup", "society_id", "pass_code_hash", "status"),
        Index("ix_guest_passes_flat_status", "destination_flat_id", "status", "valid_until"),
        Index("ix_guest_passes_creator_created", "created_by_user_id", "created_at"),
        Index("ix_guest_passes_society_created", "society_id", "created_at"),
    )

    # Relationships
    visitor_records: Mapped[list["VisitorRecord"]] = relationship(
        "VisitorRecord", back_populates="guest_pass"
    )
    redemptions: Mapped[list["GuestPassRedemption"]] = relationship(
        "GuestPassRedemption", back_populates="guest_pass", cascade="all, delete-orphan"
    )

    @property
    def target_flat_id(self) -> uuid.UUID:
        return self.destination_flat_id or self.flat_id  # type: ignore[return-value]

    @property
    def is_usable(self) -> bool:
        now = utc_now()
        vf = self.valid_from if self.valid_from.tzinfo else self.valid_from.replace(tzinfo=UTC)
        vu = self.valid_until if self.valid_until.tzinfo else self.valid_until.replace(tzinfo=UTC)
        return (
            self.status == PassStatus.ACTIVE and self.used_count < self.max_uses and vf <= now <= vu
        )


class VisitorRecord(Base):
    """Visitor log record tracking arrival, resident approval, entry, and exit."""

    __tablename__ = "visitors"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    gate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("gates.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    destination_flat_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("flats.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    destination_tower_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("towers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    visitor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(32), nullable=False)
    vehicle_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    purpose: Mapped[VisitorPurpose] = mapped_column(
        SAEnum(VisitorPurpose, native_enum=False), nullable=False
    )
    approval_status: Mapped[ApprovalStatus] = mapped_column(
        SAEnum(ApprovalStatus, native_enum=False),
        nullable=False,
        default=ApprovalStatus.PENDING,
    )
    entry_status: Mapped[EntryStatus] = mapped_column(
        SAEnum(EntryStatus, native_enum=False),
        nullable=False,
        default=EntryStatus.EXPECTED,
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approval_action_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_rejection_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    entry_gate_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("gates.id", ondelete="SET NULL"), nullable=True
    )
    entry_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entry_guard_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    exit_gate_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("gates.id", ondelete="SET NULL"), nullable=True
    )
    exit_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_guard_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    photo_s3_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    photo_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    photo_captured_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    photo_purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    photo_deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    privacy_notice_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default="v1.0-2026-pune", server_default="v1.0-2026-pune"
    )
    guest_pass_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("guest_passes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    client_event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    photo_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_offline_creation: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=expression.false(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "exit_time IS NULL OR entry_time IS NULL OR exit_time >= entry_time",
            name="chk_visitor_entry_exit_time",
        ),
        Index(
            "ix_visitor_records_society_flat_created",
            "society_id",
            "destination_flat_id",
            "created_at",
        ),
        Index(
            "ix_visitor_records_flat_pending",
            "destination_flat_id",
            "approval_status",
            "created_at",
        ),
        Index(
            "ix_visitor_records_society_checked_in",
            "society_id",
            "entry_status",
            "entry_time",
        ),
        Index("ix_visitor_records_gate_date", "gate_id", "created_at"),
        Index("ix_visitor_records_society_phone", "society_id", "phone_number"),
        Index("ix_visitor_records_society_vehicle", "society_id", "vehicle_number"),
        Index("ix_visitor_records_retention", "created_at", "photo_s3_key"),
        Index("ix_visitor_records_client_event", "client_event_id"),
    )

    # Relationships
    gate: Mapped["Gate"] = relationship(
        "Gate", foreign_keys=[gate_id], back_populates="visitor_records"
    )
    guest_pass: Mapped["GuestPass | None"] = relationship(
        "GuestPass", back_populates="visitor_records"
    )
    redemptions: Mapped[list["GuestPassRedemption"]] = relationship(
        "GuestPassRedemption",
        primaryjoin="VisitorRecord.id==GuestPassRedemption.visitor_record_id",
        back_populates="visitor_record",
    )
    sync_events: Mapped[list["OfflineSyncEvent"]] = relationship(
        "OfflineSyncEvent",
        primaryjoin="VisitorRecord.id==OfflineSyncEvent.visitor_record_id",
        back_populates="visitor_record",
    )

    @property
    def photo_key(self) -> str | None:
        return self.photo_storage_key or self.photo_s3_key

    @property
    def is_photo_expired(self) -> bool:
        """Returns True if record is > 90 days old or photo has already been purged."""
        if self.photo_purged_at is not None or self.photo_deleted_at is not None:
            return True
        if not self.photo_key:
            return True
        c_at = self.created_at if self.created_at.tzinfo else self.created_at.replace(tzinfo=UTC)
        return utc_now() - c_at > timedelta(days=90)

    @property
    def is_active_on_campus(self) -> bool:
        """Returns True if visitor is currently on campus."""
        return self.entry_status == EntryStatus.CHECKED_IN

    @property
    def is_approved_for_entry(self) -> bool:
        """Returns True if resident or system approved physical check-in."""
        return self.approval_status in (ApprovalStatus.APPROVED, ApprovalStatus.AUTO_APPROVED)

    @property
    def masked_phone(self) -> str:
        """Sanitized phone number for display (e.g., +91-XXXXX-XX210)."""
        raw = self.phone_number
        if len(raw) >= 10:
            return f"+91-XXXXX-XX{raw[-3:]}"
        return "+91-XXXXX-XXXXX"


class GuestPassRedemption(Base):
    """Immutable audit record for guest pass redemption at a gate."""

    __tablename__ = "guest_pass_redemptions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    guest_pass_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("guest_passes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    visitor_record_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("visitors.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    visitor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("visitors.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    gate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("gates.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    redeemed_by_guard_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    redeemed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    redemption_sequence: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    redeemed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        Index("ix_guest_pass_redemptions_pass", "guest_pass_id", "redemption_sequence"),
        Index(
            "ix_guest_pass_redemptions_society_gate",
            "society_id",
            "gate_id",
            "redeemed_at",
        ),
    )

    # Relationships
    guest_pass: Mapped["GuestPass"] = relationship("GuestPass", back_populates="redemptions")
    visitor_record: Mapped["VisitorRecord | None"] = relationship(
        "VisitorRecord",
        foreign_keys=[visitor_record_id],
        back_populates="redemptions",
    )


class OfflineSyncEvent(Base):
    """Audit and replay conflict detection registry for offline batch synchronization."""

    __tablename__ = "offline_sync_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    gate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("gates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_event_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(
        String(64),
        default="VISITOR_REGISTRATION",
        nullable=False,
    )
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    sync_status: Mapped[SyncStatus] = mapped_column(
        SAEnum(SyncStatus, native_enum=False), nullable=False
    )
    visitor_record_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("visitors.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    visitor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("visitors.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("society_id", "client_event_id", name="uq_offline_sync_client_event"),
        Index("ix_offline_sync_client_event", "society_id", "client_event_id"),
        Index("ix_offline_sync_gate_processed", "gate_id", "processed_at"),
    )

    # Relationships
    visitor_record: Mapped["VisitorRecord | None"] = relationship(
        "VisitorRecord",
        foreign_keys=[visitor_record_id],
        back_populates="sync_events",
    )


class GuestPassFailedAttempt(Base):
    """Durable record of failed guest-pass verification attempts.

    Backs the distributed brute-force limiter so that lockouts are enforced consistently across
    AWS Lambda instances (an in-process dictionary cannot coordinate between containers).
    """

    __tablename__ = "guest_pass_failed_attempts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    gate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("gates.id", ondelete="CASCADE"),
        nullable=False,
    )
    guard_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        Index("ix_pass_failed_gate_time", "gate_id", "attempted_at"),
        Index("ix_pass_failed_guard_time", "guard_user_id", "attempted_at"),
    )


# -----------------------------------------------------------------------------
# Compatibility column synchronisation
#
# GuestPass and GuestPassRedemption carry paired columns (destination_flat_id/flat_id,
# visitor_record_id/visitor_id, redeemed_by_guard_id/redeemed_by_user_id). Keep each pair
# consistent on insert so that writers may populate either side.
# -----------------------------------------------------------------------------


@event.listens_for(GuestPass, "before_insert")
def _sync_guest_pass_flat_columns(mapper: object, connection: object, target: GuestPass) -> None:
    if target.destination_flat_id is None and target.flat_id is not None:
        target.destination_flat_id = target.flat_id
    if target.flat_id is None and target.destination_flat_id is not None:
        target.flat_id = target.destination_flat_id
    if target.pass_code_prefix is None:
        target.pass_code_prefix = "GP-"


@event.listens_for(GuestPassRedemption, "before_insert")
def _sync_redemption_columns(
    mapper: object, connection: object, target: GuestPassRedemption
) -> None:
    if target.visitor_record_id is None and target.visitor_id is not None:
        target.visitor_record_id = target.visitor_id
    if target.visitor_id is None and target.visitor_record_id is not None:
        target.visitor_id = target.visitor_record_id
    if target.redeemed_by_guard_id is None and target.redeemed_by_user_id is not None:
        target.redeemed_by_guard_id = target.redeemed_by_user_id
    if target.redeemed_by_user_id is None and target.redeemed_by_guard_id is not None:
        target.redeemed_by_user_id = target.redeemed_by_guard_id


@event.listens_for(OfflineSyncEvent, "before_insert")
def _sync_offline_event_columns(
    mapper: object, connection: object, target: OfflineSyncEvent
) -> None:
    if target.visitor_record_id is None and target.visitor_id is not None:
        target.visitor_record_id = target.visitor_id
    if target.visitor_id is None and target.visitor_record_id is not None:
        target.visitor_id = target.visitor_record_id
