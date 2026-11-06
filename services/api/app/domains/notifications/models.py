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
from typing import Any

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
