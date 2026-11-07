"""Notification Domain SQLAlchemy Models

Defines models for:
- In-app resident & staff notifications
- External channel delivery tracking (Email, SMS, In-App)
- Auditable delivery attempts and provider reference tracking
- User communication channel preferences
"""

import enum
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.domains.identity.models import Flat, Tower, User

from sqlalchemy import (
    Boolean,
    DateTime,
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class NotificationChannel(str, enum.Enum):
    IN_APP = "IN_APP"
    EMAIL = "EMAIL"
    SMS = "SMS"


class NotificationPriority(str, enum.Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


class DeliveryStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    RETRYING = "RETRYING"
    FAILED = "FAILED"
    SUPPRESSED = "SUPPRESSED"


class Notification(Base):
    """Core in-app notification entity supporting the resident & staff inbox."""

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[NotificationChannel] = mapped_column(
        SAEnum(NotificationChannel, native_enum=False),
        nullable=False,
        default=NotificationChannel.IN_APP,
    )
    priority: Mapped[NotificationPriority] = mapped_column(
        SAEnum(NotificationPriority, native_enum=False),
        nullable=False,
        default=NotificationPriority.NORMAL,
    )
    aggregate_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    aggregate_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    action_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    # Relationships
    deliveries: Mapped[list["NotificationDelivery"]] = relationship(
        "NotificationDelivery", back_populates="notification", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_notifications_recipient_unread", "recipient_user_id", "read_at"),
        Index("ix_notifications_recipient_created", "recipient_user_id", "created_at"),
        Index("ix_notifications_society_created", "society_id", "created_at"),
        Index("ix_notifications_aggregate", "aggregate_type", "aggregate_id"),
    )


class NotificationDelivery(Base):
    """Tracks asynchronous multi-channel delivery lifecycles, retries, and idempotency."""

    __tablename__ = "notification_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    notification_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("notifications.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        SAEnum(NotificationChannel, native_enum=False), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[DeliveryStatus] = mapped_column(
        SAEnum(DeliveryStatus, native_enum=False),
        nullable=False,
        default=DeliveryStatus.PENDING,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    # Relationships
    notification: Mapped[Notification | None] = relationship(
        "Notification", back_populates="deliveries"
    )
    attempts: Mapped[list["NotificationDeliveryAttempt"]] = relationship(
        "NotificationDeliveryAttempt", back_populates="delivery", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_deliveries_status_next_attempt", "status", "next_attempt_at"),
        Index("ix_deliveries_society_recipient", "society_id", "recipient_user_id"),
    )


class NotificationDeliveryAttempt(Base):
    """Auditable log of individual delivery dispatches to providers."""

    __tablename__ = "notification_delivery_attempts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    delivery_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("notification_deliveries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[DeliveryStatus] = mapped_column(
        SAEnum(DeliveryStatus, native_enum=False), nullable=False
    )
    provider_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships
    delivery: Mapped[NotificationDelivery] = relationship(
        "NotificationDelivery", back_populates="attempts"
    )


class NotificationPreference(Base):
    """User-configured communication preferences per society.

    Note: Mandatory emergency/security notifications bypass ordinary preference opt-outs.
    """

    __tablename__ = "notification_preferences"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sms_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    in_app_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    billing_email: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    billing_sms: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    complaints_email: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    complaints_sms: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    visitor_sms: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("society_id", "user_id", name="uq_notification_preference_user_society"),
    )


# =============================================================================
# Official Township Notices & Circulars
# =============================================================================


class NoticeCategory(str, enum.Enum):
    CIRCULAR = "CIRCULAR"
    MAINTENANCE = "MAINTENANCE"
    EMERGENCY = "EMERGENCY"
    EVENT = "EVENT"
    GENERAL = "GENERAL"
    WATER = "WATER"
    ELECTRICITY = "ELECTRICITY"
    SECURITY = "SECURITY"


class NoticePriority(str, enum.Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


class NoticeStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class NoticeTargetType(str, enum.Enum):
    SOCIETY = "SOCIETY"
    TOWER = "TOWER"
    FLAT = "FLAT"


class Notice(Base):
    """Official society notices, circulars, advisories and emergency announcements."""

    __tablename__ = "notices"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[NoticeCategory] = mapped_column(
        SAEnum(NoticeCategory, native_enum=False),
        nullable=False,
        default=NoticeCategory.GENERAL,
    )
    priority: Mapped[NoticePriority] = mapped_column(
        SAEnum(NoticePriority, native_enum=False),
        nullable=False,
        default=NoticePriority.NORMAL,
    )
    status: Mapped[NoticeStatus] = mapped_column(
        SAEnum(NoticeStatus, native_enum=False),
        nullable=False,
        default=NoticeStatus.DRAFT,
    )
    target_type: Mapped[NoticeTargetType] = mapped_column(
        SAEnum(NoticeTargetType, native_enum=False),
        nullable=False,
        default=NoticeTargetType.SOCIETY,
    )
    target_tower_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("towers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    target_flat_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("flats.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    target_tower_ids: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
    )
    target_flat_ids: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
    )
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    author_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    # Relationships
    author: Mapped["User"] = relationship("User", foreign_keys=[author_id])
    target_tower: Mapped["Tower | None"] = relationship("Tower", foreign_keys=[target_tower_id])
    target_flat: Mapped["Flat | None"] = relationship("Flat", foreign_keys=[target_flat_id])
    reads: Mapped[list["NoticeRead"]] = relationship(
        "NoticeRead", back_populates="notice", cascade="all, delete-orphan"
    )
    targets: Mapped[list["NoticeTarget"]] = relationship(
        "NoticeTarget", back_populates="notice", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_notices_society_status", "society_id", "status"),
        Index("ix_notices_society_published", "society_id", "published_at"),
        Index(
            "ix_notices_society_target",
            "society_id",
            "target_type",
            "target_tower_id",
            "target_flat_id",
        ),
        Index("ix_notices_pinned_published", "society_id", "is_pinned", "published_at"),
        Index("ix_notices_status_published_at", "status", "published_at"),
    )


class NoticeRead(Base):
    """Tracks read status of official notices per user."""

    __tablename__ = "notice_reads"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    notice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("notices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    notice: Mapped["Notice"] = relationship("Notice", back_populates="reads")

    __table_args__ = (
        UniqueConstraint("notice_id", "user_id", name="uq_notice_reads_notice_user"),
        Index("ix_notice_reads_user_notice", "user_id", "notice_id"),
    )


class NoticeTarget(Base):
    """Normalized targets for official society notices (supports multi-tower & multi-flat broadcasting)."""

    __tablename__ = "notice_targets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    notice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("notices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_type: Mapped[NoticeTargetType] = mapped_column(
        SAEnum(NoticeTargetType, native_enum=False),
        nullable=False,
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    notice: Mapped["Notice"] = relationship("Notice", back_populates="targets")

    __table_args__ = (
        UniqueConstraint("notice_id", "target_type", "target_id", name="uq_notice_targets_unique"),
        Index("ix_notice_targets_lookup", "target_type", "target_id"),
    )
