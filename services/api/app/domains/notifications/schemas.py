"""Notification Domain Pydantic v2 Schemas"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domains.notifications.models import (
    DeliveryStatus,
    NoticeCategory,
    NoticePriority,
    NoticeStatus,
    NoticeTargetType,
    NotificationChannel,
    NotificationPriority,
)


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class NotificationResponseSchema(BaseSchema):
    id: UUID
    society_id: UUID
    recipient_user_id: UUID
    event_type: str
    title: str
    body: str
    channel: NotificationChannel
    priority: NotificationPriority
    aggregate_type: str | None = None
    aggregate_id: str | None = None
    action_url: str | None = None
    read_at: datetime | None = None
    is_read: bool = False
    created_at: datetime


class PaginatedNotificationsResponse(BaseModel):
    items: list[NotificationResponseSchema]
    total: int
    page: int
    page_size: int
    total_pages: int
    unread_count: int


class UnreadCountResponse(BaseModel):
    unread_count: int


class MarkReadResponse(BaseModel):
    notification_id: UUID
    read_at: datetime
    status: str = "success"


class MarkAllReadResponse(BaseModel):
    marked_count: int
    status: str = "success"


class NotificationPreferenceSchema(BaseSchema):
    society_id: UUID
    user_id: UUID
    email_enabled: bool = True
    sms_enabled: bool = True
    in_app_enabled: bool = True
    billing_email: bool = True
    billing_sms: bool = True
    complaints_email: bool = True
    complaints_sms: bool = True
    visitor_sms: bool = True
    emergency_alerts_mandatory: bool = Field(
        default=True,
        description="Emergency safety alerts cannot be disabled by user preference.",
    )


class UpdateNotificationPreferenceRequest(BaseModel):
    email_enabled: bool | None = None
    sms_enabled: bool | None = None
    in_app_enabled: bool | None = None
    billing_email: bool | None = None
    billing_sms: bool | None = None
    complaints_email: bool | None = None
    complaints_sms: bool | None = None
    visitor_sms: bool | None = None


class StaffDeliveryOverviewItem(BaseSchema):
    id: UUID
    notification_id: UUID | None = None
    society_id: UUID
    recipient_user_id: UUID
    channel: NotificationChannel
    provider: str
    status: DeliveryStatus
    attempt_count: int
    next_attempt_at: datetime | None = None
    last_error_code: str | None = None
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    created_at: datetime


class StaffNotificationOverviewResponse(BaseModel):
    items: list[StaffDeliveryOverviewItem]
    total: int
    page: int
    page_size: int
    total_pages: int
    pending_count: int
    failed_count: int
    sent_count: int
    delivered_count: int
    suppressed_count: int


# =============================================================================
# Official Notices & Circulars Schemas
# =============================================================================


class CreateNoticeRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    body: str = Field(..., min_length=1)
    category: NoticeCategory = NoticeCategory.GENERAL
    priority: NoticePriority = NoticePriority.NORMAL
    status: NoticeStatus = NoticeStatus.DRAFT
    target_type: NoticeTargetType = NoticeTargetType.SOCIETY
    target_tower_id: UUID | None = None
    target_tower_ids: list[UUID] = Field(default_factory=list)
    target_flat_id: UUID | None = None
    target_flat_ids: list[UUID] = Field(default_factory=list)
    is_pinned: bool = False
    published_at: datetime | None = None
    expires_at: datetime | None = None
    deliver_emergency: bool = False


class UpdateNoticeRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    body: str | None = Field(None, min_length=1)
    category: NoticeCategory | None = None
    priority: NoticePriority | None = None
    status: NoticeStatus | None = None
    target_type: NoticeTargetType | None = None
    target_tower_id: UUID | None = None
    target_tower_ids: list[UUID] | None = None
    target_flat_id: UUID | None = None
    target_flat_ids: list[UUID] | None = None
    is_pinned: bool | None = None
    published_at: datetime | None = None
    expires_at: datetime | None = None
    deliver_emergency: bool | None = None


class NoticeResponseSchema(BaseSchema):
    id: UUID
    society_id: UUID
    title: str
    body: str
    category: NoticeCategory
    priority: NoticePriority
    status: NoticeStatus
    target_type: NoticeTargetType
    target_tower_id: UUID | None = None
    target_tower_name: str | None = None
    target_tower_ids: list[UUID] = Field(default_factory=list)
    target_tower_names: list[str] = Field(default_factory=list)
    target_flat_id: UUID | None = None
    target_flat_number: str | None = None
    target_flat_ids: list[UUID] = Field(default_factory=list)
    target_flat_numbers: list[str] = Field(default_factory=list)
    is_pinned: bool = False
    published_at: datetime | None = None
    expires_at: datetime | None = None
    author_id: UUID
    author_name: str | None = None
    is_read: bool = False
    read_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PaginatedNoticesResponse(BaseModel):
    items: list[NoticeResponseSchema]
    total: int
    page: int
    page_size: int
    total_pages: int
    unread_count: int = 0


class MarkNoticeReadResponse(BaseModel):
    notice_id: UUID
    read_at: datetime
    status: str = "success"


class MarkAllNoticesReadResponse(BaseModel):
    marked_count: int
    status: str = "success"


class TowerOptionSchema(BaseModel):
    id: UUID
    tower_number: str
    name: str


class FlatOptionSchema(BaseModel):
    id: UUID
    flat_number: str
    tower_id: UUID
    tower_number: str
    tower_name: str


class NoticeTargetingOptionsResponse(BaseModel):
    towers: list[TowerOptionSchema]
    flats: list[FlatOptionSchema]
