"""Complaints Domain SQLAlchemy Models

Provides persistent entities for:
1. Complaint (Resident tickets with category, priority, status, SLA deadlines, AI triage, safety escalation)
2. ComplaintAttachment (Secure photo/file upload metadata with private storage keys)
3. ComplaintComment (Public conversation and internal helpdesk notes)
4. ComplaintActivity (Immutable audit timeline of state transitions, assignments, and SLA events)
"""

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class ComplaintStatus(str, enum.Enum):
    SUBMITTED = "SUBMITTED"
    TRIAGED = "TRIAGED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    AWAITING_RESIDENT = "AWAITING_RESIDENT"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    REOPENED = "REOPENED"
    CANCELLED = "CANCELLED"


class ComplaintPriority(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ComplaintCategory(str, enum.Enum):
    PLUMBING = "PLUMBING"
    ELECTRICAL = "ELECTRICAL"
    HOUSEKEEPING = "HOUSEKEEPING"
    LIFT = "LIFT"
    SECURITY = "SECURITY"
    WATER_SUPPLY = "WATER_SUPPLY"
    WASTE_MANAGEMENT = "WASTE_MANAGEMENT"
    COMMON_AREA = "COMMON_AREA"
    STRUCTURAL = "STRUCTURAL"
    OTHER = "OTHER"


class Complaint(Base):
    """Authoritative complaint entity."""

    __tablename__ = "complaints"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    flat_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("flats.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    complaint_number: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[ComplaintCategory] = mapped_column(
        SAEnum(ComplaintCategory, native_enum=False),
        nullable=False,
        default=ComplaintCategory.OTHER,
        index=True,
    )
    subcategory: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    priority: Mapped[ComplaintPriority] = mapped_column(
        SAEnum(ComplaintPriority, native_enum=False),
        nullable=False,
        default=ComplaintPriority.MEDIUM,
        index=True,
    )
    status: Mapped[ComplaintStatus] = mapped_column(
        SAEnum(ComplaintStatus, native_enum=False),
        nullable=False,
        default=ComplaintStatus.SUBMITTED,
        index=True,
    )

    # AI-assisted classification fields (stored separately from human decisions)
    ai_suggested_category: Mapped[ComplaintCategory | None] = mapped_column(
        SAEnum(ComplaintCategory, native_enum=False), nullable=True
    )
    ai_suggested_priority: Mapped[ComplaintPriority | None] = mapped_column(
        SAEnum(ComplaintPriority, native_enum=False), nullable=True
    )
    ai_confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ai_urgency_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Duplicate tracking
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("complaints.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Deterministic safety escalation (runs prior to AI and cannot be overridden by AI)
    safety_escalated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    safety_escalation_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # SLA targets and actual tracking (UTC)
    first_response_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolution_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_response_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reopened_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Resident satisfaction & feedback
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("society_id", "complaint_number", name="uq_complaint_society_number"),
        CheckConstraint(
            "rating IS NULL OR (rating >= 1 AND rating <= 5)", name="chk_complaint_rating_range"
        ),
        Index("ix_complaints_society_status", "society_id", "status"),
        Index("ix_complaints_society_priority", "society_id", "priority"),
        Index("ix_complaints_society_flat", "society_id", "flat_id"),
        Index("ix_complaints_society_assigned", "society_id", "assigned_to"),
        Index("ix_complaints_society_created", "society_id", "created_at"),
        Index("ix_complaints_resolution_deadline", "resolution_deadline"),
    )

    # Relationships
    attachments: Mapped[list["ComplaintAttachment"]] = relationship(
        "ComplaintAttachment",
        back_populates="complaint",
        cascade="all, delete-orphan",
        order_by="ComplaintAttachment.created_at",
    )
    comments: Mapped[list["ComplaintComment"]] = relationship(
        "ComplaintComment",
        back_populates="complaint",
        cascade="all, delete-orphan",
        order_by="ComplaintComment.created_at",
    )
    activities: Mapped[list["ComplaintActivity"]] = relationship(
        "ComplaintActivity",
        back_populates="complaint",
        cascade="all, delete-orphan",
        order_by="ComplaintActivity.created_at",
    )


class ComplaintAttachment(Base):
    """Metadata for uploaded complaint photo attachments."""

    __tablename__ = "complaint_attachments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    complaint_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("complaints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint("file_size_bytes > 0", name="chk_attachment_size_positive"),
        Index("ix_complaint_attachments_complaint", "complaint_id"),
    )

    complaint: Mapped["Complaint"] = relationship("Complaint", back_populates="attachments")


class ComplaintComment(Base):
    """Resident public comments and internal helpdesk notes."""

    __tablename__ = "complaint_comments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    complaint_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("complaints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (Index("ix_complaint_comments_complaint", "complaint_id", "created_at"),)

    complaint: Mapped["Complaint"] = relationship("Complaint", back_populates="comments")


class ComplaintActivity(Base):
    """Immutable audit trail of complaint lifecycle transitions and operational events."""

    __tablename__ = "complaint_activities"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    complaint_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("complaints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    activity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    old_value: Mapped[str | None] = mapped_column(String(128), nullable=True)
    new_value: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    activity_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (Index("ix_complaint_activities_complaint", "complaint_id", "created_at"),)

    complaint: Mapped["Complaint"] = relationship("Complaint", back_populates="activities")
