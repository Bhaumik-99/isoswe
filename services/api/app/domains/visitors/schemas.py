"""Visitor Domain Pydantic Schemas

Defines request and response schemas for Phase 6 gate tablet operations,
resident approvals, and guest passes.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domains.visitors.models import (
    ApprovalStatus,
    EntryStatus,
    GateStatus,
    PassStatus,
    PassType,
    VisitorPurpose,
)


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class GateSchema(BaseSchema):
    gate_id: UUID = Field(alias="id")
    gate_number: int
    gate_name: str
    status: GateStatus = GateStatus.ACTIVE
    description: str | None = None
    assigned_from: datetime | None = None
    assigned_until: datetime | None = None
    created_at: datetime | None = None


class GateStaffAssignmentSchema(BaseSchema):
    id: UUID
    society_id: UUID
    user_id: UUID
    gate_id: UUID
    assigned_from: datetime
    assigned_until: datetime | None = None
    is_active: bool
    created_at: datetime


class FlatSummarySchema(BaseSchema):
    flat_id: UUID
    flat_number: str
    tower_name: str | None = None


class VisitorRegisterRequest(BaseModel):
    visitor_name: str = Field(min_length=2, max_length=255)
    phone_number: str = Field(pattern=r"^\+91[0-9]{10}$")
    vehicle_number: str | None = Field(default=None, max_length=20)
    purpose: VisitorPurpose
    destination_flat_id: UUID
    gate_id: UUID | None = None
    privacy_notice_version: str = Field(default="v1.0-2026-pune")
    client_event_id: UUID | None = None
    photo_base64: str | None = None

    @field_validator("visitor_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        stripped = v.strip()
        if len(stripped) < 2:
            raise ValueError("Visitor name must be at least 2 characters.")
        if len(stripped) > 255:
            raise ValueError("Visitor name cannot exceed 255 characters.")
        return stripped


class ResidentVisitorActionRequest(BaseModel):
    action: str = Field(pattern="^(APPROVE|REJECT)$")
    reason: str | None = Field(default=None, max_length=255)


class VisitorResponse(BaseSchema):
    visitor_id: UUID
    society_id: UUID
    gate_id: UUID
    visitor_name: str
    phone_masked: str
    vehicle_number: str | None = None
    purpose: VisitorPurpose
    destination_flat_id: UUID
    destination_flat: dict[str, Any] | None = None
    approval_status: ApprovalStatus
    entry_status: EntryStatus
    photo_url: str | None = None
    photo_storage_key: str | None = None
    created_at: datetime
    entry_time: datetime | None = None
    exit_time: datetime | None = None
    approved_at: datetime | None = None
    approved_by_user_id: UUID | None = None


class GateSessionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    user_id: UUID
    full_name: str
    society_id: UUID
    assigned_gate: dict[str, Any] | None = None
    available_gates: list[dict[str, Any]] = Field(default_factory=list)


class GuestPassCreateRequest(BaseModel):
    destination_flat_id: UUID
    guest_name: str = Field(min_length=2, max_length=255)
    guest_phone: str | None = Field(default=None, max_length=32)
    purpose: str = Field(min_length=1, max_length=255)
    pass_type: PassType
    max_uses: int = Field(default=1)
    valid_from: datetime
    valid_until: datetime

    @field_validator("guest_name")
    @classmethod
    def validate_guest_name(cls, v: str) -> str:
        stripped = v.strip()
        if len(stripped) < 2:
            raise ValueError("Guest name must be at least 2 characters.")
        return stripped

    @model_validator(mode="after")
    def validate_dates_and_uses(self) -> "GuestPassCreateRequest":
        if self.valid_until < self.valid_from:
            raise ValueError("valid_until must be greater than or equal to valid_from.")
        if self.pass_type == PassType.SINGLE_USE and self.max_uses != 1:
            raise ValueError("max_uses must be 1 for SINGLE_USE pass.")
        if self.pass_type == PassType.MULTI_USE and (self.max_uses < 2 or self.max_uses > 10):
            raise ValueError("max_uses must be between 2 and 10 for MULTI_USE pass.")
        return self


class GuestPassResponse(BaseSchema):
    pass_id: UUID
    pass_code: str | None = None
    pass_type: PassType
    max_uses: int
    used_count: int
    valid_from: datetime
    valid_until: datetime
    status: PassStatus
    destination_flat_id: UUID
    guest_name: str
    purpose: str


class GuestPassVerifyRequest(BaseModel):
    pass_code: str
    gate_id: UUID


class GuestPassVerifyResponse(BaseModel):
    verified: bool
    pass_id: UUID
    visitor_id: UUID | None = None
    guest_name: str
    pass_type: PassType
    remaining_uses: int
    approval_status: str
    entry_status: str
    destination_flat: dict[str, Any] | None = None


class OfflineSyncEventPayload(BaseModel):
    visitor_name: str
    phone_number: str
    vehicle_number: str | None = None
    purpose: VisitorPurpose
    destination_flat_id: UUID
    photo_base64: str | None = None
    privacy_notice_version: str = "v1.0-2026-pune"


class OfflineSyncBatchItem(BaseModel):
    client_event_id: UUID
    timestamp: datetime
    payload: dict[str, Any]


class OfflineSyncBatchRequest(BaseModel):
    gate_id: UUID
    events: list[OfflineSyncBatchItem]


class OfflineSyncEventResult(BaseModel):
    client_event_id: UUID
    status: str
    visitor_id: UUID | None = None
    approval_status: str | None = None
    error_message: str | None = None


class OfflineSyncBatchResponse(BaseModel):
    gate_id: UUID
    processed_count: int
    results: list[OfflineSyncEventResult]


class PrivacyNoticeResponse(BaseModel):
    version: str
    language: str
    title: str
    content: str
    retention_days: int = 90
    grievance_contact: str = "helpdesk@marvelgreenfield.com"
