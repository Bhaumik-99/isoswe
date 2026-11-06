"""Notification Domain Pydantic v2 Schemas"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domains.notifications.models import (
    DeliveryStatus,
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
