"""Complaints Domain Pydantic v2 Schemas

Strict typed contracts for:
- Complaint creation, updates, and assignments
- Attachments & presigned upload/download URLs
- Public comments & internal helpdesk notes
- Timeline activities & SLA countdowns
- Staff operational dashboard & metric aggregates
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domains.complaints.models import (
    AttachmentStatus,
    ComplaintAIStatus,
    ComplaintCategory,
    ComplaintPriority,
    ComplaintStatus,
)


class CreateComplaintRequest(BaseModel):
    flat_id: UUID = Field(..., description="ID of the resident's flat")
    title: str = Field(..., min_length=3, max_length=255, description="Short summary of the issue")
    description: str = Field(
        ..., min_length=5, max_length=5000, description="Detailed description of the complaint"
    )
    category: ComplaintCategory = Field(
        default=ComplaintCategory.OTHER, description="Primary issue category"
    )
    subcategory: str | None = Field(default=None, max_length=64)


class UpdateComplaintStatusRequest(BaseModel):
    status: ComplaintStatus = Field(..., description="Target lifecycle status")
    notes: str | None = Field(
        default=None, max_length=1000, description="Optional transition or resolution notes"
    )


class AssignComplaintRequest(BaseModel):
    assigned_to: UUID = Field(..., description="User ID of the helpdesk staff to assign")
    notes: str | None = Field(default=None, max_length=500)


class UpdateComplaintPriorityRequest(BaseModel):
    priority: ComplaintPriority = Field(..., description="Target operational priority")
    reason: str | None = Field(default=None, max_length=500)


class CreateCommentRequest(BaseModel):
    comment: str = Field(..., min_length=1, max_length=5000)
    is_internal: bool = Field(
        default=False, description="Set true for internal helpdesk notes invisible to residents"
    )


class RateComplaintRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="Satisfaction score between 1 and 5")
    feedback: str | None = Field(
        default=None, max_length=1000, description="Optional qualitative feedback"
    )


class ReopenComplaintRequest(BaseModel):
    reason: str = Field(
        ...,
        min_length=5,
        max_length=1000,
        description="Explanation of why issue remains unresolved",
    )


class InitiateAttachmentUploadRequest(BaseModel):
    file_name: str = Field(..., min_length=1, max_length=255)
    file_size_bytes: int = Field(
        ..., gt=0, le=5 * 1024 * 1024, description="Max 5MB file size limit"
    )
    content_type: str = Field(
        ..., pattern=r"^image\/(jpeg|png|webp)$", description="Only JPEG, PNG, or WebP allowed"
    )


class PresignedUploadResponse(BaseModel):
    attachment_id: UUID
    upload_url: str
    storage_key: str
    expires_in_seconds: int = 3600


class AttachmentResponse(BaseModel):
    id: UUID
    complaint_id: UUID
    file_name: str
    file_size_bytes: int
    content_type: str
    status: AttachmentStatus = AttachmentStatus.UPLOADED
    download_url: str
    uploaded_by: UUID
    uploader_name: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CommentResponse(BaseModel):
    id: UUID
    complaint_id: UUID
    user_id: UUID
    user_name: str | None = None
    user_role: str | None = None
    comment: str
    is_internal: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ActivityResponse(BaseModel):
    id: UUID
    complaint_id: UUID
    actor_id: UUID | None = None
    actor_name: str | None = None
    activity_type: str
    old_value: str | None = None
    new_value: str | None = None
    notes: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ComplaintResponse(BaseModel):
    id: UUID
    society_id: UUID
    flat_id: UUID
    tower_number: str | None = None
    flat_number: str | None = None
    created_by: UUID
    creator_name: str | None = None
    assigned_to: UUID | None = None
    assignee_name: str | None = None
    complaint_number: str
    category: ComplaintCategory
    subcategory: str | None = None
    title: str
    description: str
    priority: ComplaintPriority
    status: ComplaintStatus

    # AI Suggestions
    ai_status: ComplaintAIStatus = ComplaintAIStatus.PENDING
    ai_suggested_category: ComplaintCategory | None = None
    ai_suggested_priority: ComplaintPriority | None = None
    ai_confidence_score: float | None = None
    ai_summary: str | None = None
    ai_urgency_reason: str | None = None
    ai_reasoning: str | None = None
    ai_provider: str | None = None
    ai_model: str | None = None
    ai_processed_at: datetime | None = None

    # Safety Escalation
    safety_escalated: bool = False
    safety_escalation_reason: str | None = None

    # Duplicate tracking
    duplicate_of_id: UUID | None = None
    duplicate_candidates: list[UUID] = Field(default_factory=list)

    # SLA Tracking
    first_response_deadline: datetime | None = None
    resolution_deadline: datetime | None = None
    first_response_at: datetime | None = None
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    reopened_at: datetime | None = None
    reopened_count: int = 0
    is_sla_breached: bool = False

    # Rating & Feedback
    rating: int | None = None
    feedback: str | None = None

    # Child collections
    attachments: list[AttachmentResponse] = Field(default_factory=list)
    comments: list[CommentResponse] = Field(default_factory=list)
    activities: list[ActivityResponse] = Field(default_factory=list)

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HelpdeskDashboardMetricsResponse(BaseModel):
    total_complaints: int
    unassigned_count: int
    in_progress_count: int
    critical_count: int
    overdue_count: int
    resolved_count: int
    average_first_response_minutes: float
    average_resolution_minutes: float
    resolution_rate_percentage: float


class CompleteAttachmentUploadResponse(BaseModel):
    attachment: AttachmentResponse
    message: str = "Attachment upload completed successfully"
