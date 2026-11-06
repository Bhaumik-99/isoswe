"""Amenity & Clubhouse Booking Domain SQLAlchemy Models

Provides persistent primitives for:
1. Amenity: Facilities (clubhouse, courts, gym, swimming pool, community hall)
2. AmenityBooking: Slot reservations, payment tracking, cancellation and refund status
"""

import enum
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
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


class AmenityType(str, enum.Enum):
    CLUBHOUSE = "CLUBHOUSE"
    BADMINTON_COURT = "BADMINTON_COURT"
    TENNIS_COURT = "TENNIS_COURT"
    SWIMMING_POOL = "SWIMMING_POOL"
    GYM = "GYM"
    COMMUNITY_HALL = "COMMUNITY_HALL"
    GUEST_ROOM = "GUEST_ROOM"
    OTHER = "OTHER"


class BookingStatus(str, enum.Enum):
    PENDING_PAYMENT = "PENDING_PAYMENT"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    PAYMENT_FAILED = "PAYMENT_FAILED"


class BookingPaymentStatus(str, enum.Enum):
    FREE = "FREE"
    PAID = "PAID"
    PENDING = "PENDING"
    REFUNDED = "REFUNDED"
    FAILED = "FAILED"


class RefundStatus(str, enum.Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PENDING_REFUND = "PENDING_REFUND"
    REFUNDED = "REFUNDED"
    CANCELLED_NO_REFUND = "CANCELLED_NO_REFUND"


class Amenity(Base):
    """Amenity or facility resource available for booking."""

    __tablename__ = "amenities"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    amenity_type: Mapped[AmenityType] = mapped_column(
        SAEnum(AmenityType, native_enum=False), nullable=False
    )
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tower_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("towers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    slot_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    opening_time: Mapped[str] = mapped_column(String(8), nullable=False, default="06:00")
    closing_time: Mapped[str] = mapped_column(String(8), nullable=False, default="22:00")
    booking_fee_paise: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), nullable=False, default=0
    )
    advance_booking_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    min_advance_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_slots_per_day_per_resident: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    cancellation_deadline_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    refund_percentage: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    allowed_membership_types: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=lambda: ["OWNER", "TENANT", "FAMILY_MEMBER"],
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    rules_and_guidelines: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    # Relationships
    society: Mapped["Society"] = relationship("Society")  # type: ignore[name-defined] # noqa: F821
    tower: Mapped["Tower | None"] = relationship("Tower")  # type: ignore[name-defined] # noqa: F821
    bookings: Mapped[list["AmenityBooking"]] = relationship(
        "AmenityBooking", back_populates="amenity", cascade="all, delete-orphan"
    )
    blocks: Mapped[list["AmenityBlock"]] = relationship(
        "AmenityBlock", back_populates="amenity", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("capacity > 0", name="chk_amenity_capacity_positive"),
        CheckConstraint("slot_duration_minutes > 0", name="chk_amenity_slot_duration_positive"),
        CheckConstraint("booking_fee_paise >= 0", name="chk_amenity_fee_non_negative"),
        CheckConstraint("advance_booking_days >= 0", name="chk_amenity_advance_days_non_negative"),
        CheckConstraint(
            "refund_percentage >= 0 AND refund_percentage <= 100",
            name="chk_amenity_refund_pct_range",
        ),
        Index("ix_amenities_society_active", "society_id", "is_active"),
    )


class AmenityBooking(Base):
    """Reservation record for an amenity slot."""

    __tablename__ = "amenity_bookings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amenity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("amenities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    flat_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("flats.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    booking_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[str] = mapped_column(String(8), nullable=False)
    end_time: Mapped[str] = mapped_column(String(8), nullable=False)
    booked_units: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[BookingStatus] = mapped_column(
        SAEnum(BookingStatus, native_enum=False),
        nullable=False,
        default=BookingStatus.CONFIRMED,
    )
    booking_fee_paise: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), nullable=False, default=0
    )
    payment_status: Mapped[BookingPaymentStatus] = mapped_column(
        SAEnum(BookingPaymentStatus, native_enum=False),
        nullable=False,
        default=BookingPaymentStatus.FREE,
    )
    payment_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "payments.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_amenity_bookings_payment_id",
        ),
        nullable=True,
        index=True,
    )
    payment_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    refund_status: Mapped[RefundStatus] = mapped_column(
        SAEnum(RefundStatus, native_enum=False),
        nullable=False,
        default=RefundStatus.NOT_APPLICABLE,
    )
    refund_amount_paise: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), nullable=False, default=0
    )
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    booking_metadata: Mapped[dict[str, Any]] = mapped_column(
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
    amenity: Mapped[Amenity] = relationship("Amenity", back_populates="bookings")
    society: Mapped["Society"] = relationship("Society")  # type: ignore[name-defined] # noqa: F821
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])  # type: ignore[name-defined] # noqa: F821
    cancelled_by: Mapped["User | None"] = relationship(  # type: ignore[name-defined] # noqa: F821
        "User", foreign_keys=[cancelled_by_user_id]
    )
    flat: Mapped["Flat"] = relationship("Flat")  # type: ignore[name-defined] # noqa: F821
    payment: Mapped["Payment | None"] = relationship(  # type: ignore[name-defined] # noqa: F821
        "Payment", foreign_keys=[payment_id]
    )

    __table_args__ = (
        CheckConstraint("booked_units > 0", name="chk_booking_units_positive"),
        CheckConstraint("booking_fee_paise >= 0", name="chk_booking_fee_non_negative"),
        CheckConstraint("refund_amount_paise >= 0", name="chk_booking_refund_non_negative"),
        CheckConstraint("end_time > start_time", name="chk_booking_time_order"),
        Index("ix_amenity_bookings_amenity_date", "amenity_id", "booking_date", "status"),
        Index("ix_amenity_bookings_user_date", "user_id", "booking_date"),
        Index("ix_amenity_bookings_society_created", "society_id", "created_at"),
        Index("ix_amenity_bookings_flat", "flat_id"),
    )


class AmenityBlock(Base):
    """Temporary maintenance or administrative block of an amenity for a date or slot."""

    __tablename__ = "amenity_blocks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amenity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("amenities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    block_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[str | None] = mapped_column(String(8), nullable=True)
    end_time: Mapped[str | None] = mapped_column(String(8), nullable=True)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    blocked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    # Relationships
    amenity: Mapped["Amenity"] = relationship("Amenity", back_populates="blocks")
    society: Mapped["Society"] = relationship("Society")  # type: ignore[name-defined] # noqa: F821
    blocked_by: Mapped["User | None"] = relationship("User")  # type: ignore[name-defined] # noqa: F821

    __table_args__ = (
        Index("ix_amenity_blocks_society_amenity_date", "society_id", "amenity_id", "block_date"),
    )

