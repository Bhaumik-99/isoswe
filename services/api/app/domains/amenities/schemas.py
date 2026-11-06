"""Pydantic schemas for the Amenity and Clubhouse Booking domain."""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domains.amenities.models import (
    AmenityType,
    BookingPaymentStatus,
    BookingStatus,
    RefundStatus,
)


class AmenityBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    amenity_type: AmenityType
    location: str | None = Field(default=None, max_length=255)
    tower_id: uuid.UUID | None = None
    capacity: int = Field(default=1, ge=1, le=1000)
    slot_duration_minutes: int = Field(default=60, ge=15, le=480)
    opening_time: str = Field(default="06:00", pattern=r"^\d{2}:\d{2}$")
    closing_time: str = Field(default="22:00", pattern=r"^\d{2}:\d{2}$")
    booking_fee_paise: int = Field(default=0, ge=0)
    advance_booking_days: int = Field(default=7, ge=0, le=365)
    min_advance_hours: int = Field(default=0, ge=0, le=168)
    max_slots_per_day_per_resident: int = Field(default=2, ge=1, le=24)
    cancellation_deadline_hours: int = Field(default=2, ge=0, le=168)
    refund_percentage: int = Field(default=100, ge=0, le=100)
    allowed_membership_types: list[str] = Field(
        default_factory=lambda: ["OWNER", "TENANT", "FAMILY_MEMBER"]
    )
    is_active: bool = True
    rules_and_guidelines: str | None = Field(default=None, max_length=5000)

    @field_validator("closing_time")
    @classmethod
    def validate_times(cls, v: str, info: Any) -> str:
        opening = info.data.get("opening_time")
        if opening and v <= opening:
            raise ValueError("closing_time must be later than opening_time")
        return v


class AmenityCreateRequest(AmenityBase):
    pass


class AmenityUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    amenity_type: AmenityType | None = None
    location: str | None = Field(default=None, max_length=255)
    tower_id: uuid.UUID | None = None
    capacity: int | None = Field(default=None, ge=1, le=1000)
    slot_duration_minutes: int | None = Field(default=None, ge=15, le=480)
    opening_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    closing_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    booking_fee_paise: int | None = Field(default=None, ge=0)
    advance_booking_days: int | None = Field(default=None, ge=0, le=365)
    min_advance_hours: int | None = Field(default=None, ge=0, le=168)
    max_slots_per_day_per_resident: int | None = Field(default=None, ge=1, le=24)
    cancellation_deadline_hours: int | None = Field(default=None, ge=0, le=168)
    refund_percentage: int | None = Field(default=None, ge=0, le=100)
    allowed_membership_types: list[str] | None = None
    is_active: bool | None = None
    rules_and_guidelines: str | None = Field(default=None, max_length=5000)


class AmenityStatusRequest(BaseModel):
    is_active: bool


class AmenityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    society_id: uuid.UUID
    name: str
    description: str | None = None
    amenity_type: AmenityType
    location: str | None = None
    tower_id: uuid.UUID | None = None
    capacity: int
    slot_duration_minutes: int
    opening_time: str
    closing_time: str
    booking_fee_paise: int
    advance_booking_days: int
    min_advance_hours: int
    max_slots_per_day_per_resident: int
    cancellation_deadline_hours: int
    refund_percentage: int
    allowed_membership_types: list[str]
    is_active: bool
    rules_and_guidelines: str | None = None
    created_at: datetime
    updated_at: datetime


class AmenityListResponse(BaseModel):
    items: list[AmenityResponse]
    total: int


class TimeSlotAvailability(BaseModel):
    start_time: str
    end_time: str
    total_capacity: int
    booked_units: int
    remaining_capacity: int
    is_available: bool
    is_past: bool
    user_booked: bool = False


class AmenitySlotsResponse(BaseModel):
    amenity_id: uuid.UUID
    booking_date: date
    slots: list[TimeSlotAvailability]


class CreateBookingRequest(BaseModel):
    flat_id: uuid.UUID
    booking_date: date
    start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    booked_units: int = Field(default=1, ge=1, le=50)
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("end_time")
    @classmethod
    def validate_time_order(cls, v: str, info: Any) -> str:
        start = info.data.get("start_time")
        if start and v <= start:
            raise ValueError("end_time must be later than start_time")
        return v


class CancelBookingRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class StaffCancelBookingRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


class BookingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    society_id: uuid.UUID
    amenity_id: uuid.UUID
    amenity_name: str | None = None
    amenity_type: AmenityType | None = None
    user_id: uuid.UUID
    flat_id: uuid.UUID
    flat_number: str | None = None
    booking_date: date
    start_time: str
    end_time: str
    booked_units: int
    status: BookingStatus
    booking_fee_paise: int
    payment_status: BookingPaymentStatus
    payment_reference: str | None = None
    refund_status: RefundStatus
    refund_amount_paise: int
    cancellation_reason: str | None = None
    cancelled_at: datetime | None = None
    cancelled_by_user_id: uuid.UUID | None = None
    notes: str | None = None
    booking_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class PaginatedBookingsResponse(BaseModel):
    items: list[BookingResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
