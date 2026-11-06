"""API Version 1 Complaints & Helpdesk Operations Endpoints

Provides REST endpoints for:
- Resident complaints: raising tickets, tracking status, uploading photos, commenting, rating, reopening.
- Helpdesk operations: triage queue, workload reassignment, lifecycle transitions, internal notes, KPI dashboard.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_permissions, require_roles
from app.domains.complaints.models import ComplaintCategory, ComplaintPriority, ComplaintStatus
from app.domains.complaints.schemas import (
    AcknowledgeSafetyAlertRequest,
    AssignComplaintRequest,
    AttachmentResponse,
    CommentResponse,
    ComplaintResponse,
    CreateCommentRequest,
    CreateComplaintRequest,
    HelpdeskDashboardMetricsResponse,
    InitiateAttachmentUploadRequest,
    LinkDuplicateComplaintRequest,
    PresignedUploadResponse,
    RateComplaintRequest,
    ReopenComplaintRequest,
    SafetyAlertResponse,
    UpdateComplaintCategoryRequest,
    UpdateComplaintPriorityRequest,
    UpdateComplaintStatusRequest,
)
from app.domains.complaints.service import ComplaintService
from app.domains.identity.models import Permission, RoleType
from app.domains.identity.schemas import CurrentUserClaims

router = APIRouter(prefix="/complaints", tags=["Complaints & Helpdesk"])


# =============================================================================
# Resident Endpoints
# =============================================================================


@router.post(
    "",
    response_model=ComplaintResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Raise a new resident complaint",
)
def create_complaint(
    payload: CreateComplaintRequest,
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.RESIDENT))],
    db: Session = Depends(get_db),
) -> ComplaintResponse:
    """Resident submits a complaint with title, description, category, and flat ID.

    Executes deterministic multilingual safety escalation, AI-assisted advisory triage,
    and automatic workload-based assignment to active helpdesk staff.
    """
    service = ComplaintService(db)
    return service.create_complaint(claims, payload)


@router.get(
    "/me",
    response_model=list[ComplaintResponse],
    summary="List complaints raised by or belonging to current resident",
)
def list_resident_complaints(
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.RESIDENT))],
    complaint_status: ComplaintStatus | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[ComplaintResponse]:
    """Returns complaints for flats where the resident has approved memberships."""
    service = ComplaintService(db)
    return service.list_resident_complaints(
        claims, status=complaint_status, limit=limit, offset=offset
    )


@router.get(
    "/me/{complaint_id}",
    response_model=ComplaintResponse,
    summary="Get resident complaint detail",
)
def get_resident_complaint(
    complaint_id: UUID,
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.RESIDENT))],
    db: Session = Depends(get_db),
) -> ComplaintResponse:
    """Returns complaint details, attachments, public comments, and status for a resident's ticket."""
    service = ComplaintService(db)
    return service.get_resident_complaint(claims, complaint_id)


@router.post(
    "/me/{complaint_id}/attachments",
    response_model=PresignedUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate photo/file attachment upload for resident",
)
def initiate_resident_attachment(
    complaint_id: UUID,
    payload: InitiateAttachmentUploadRequest,
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.RESIDENT))],
    db: Session = Depends(get_db),
) -> PresignedUploadResponse:
    service = ComplaintService(db)
    return service.initiate_attachment_upload(claims, complaint_id, payload, is_staff=False)


@router.post(
    "/me/{complaint_id}/attachments/{attachment_id}/complete",
    response_model=AttachmentResponse,
    summary="Complete and verify resident attachment upload",
)
def complete_resident_attachment(
    complaint_id: UUID,
    attachment_id: UUID,
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.RESIDENT))],
    db: Session = Depends(get_db),
) -> AttachmentResponse:
    service = ComplaintService(db)
    return service.complete_attachment_upload(claims, complaint_id, attachment_id, is_staff=False)


@router.post(
    "/me/{complaint_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add public comment to complaint",
)
def add_resident_comment(
    complaint_id: UUID,
    payload: CreateCommentRequest,
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.RESIDENT))],
    db: Session = Depends(get_db),
) -> CommentResponse:
    service = ComplaintService(db)
    return service.add_comment(claims, complaint_id, payload, is_staff=False)


@router.post(
    "/me/{complaint_id}/reopen",
    response_model=ComplaintResponse,
    summary="Reopen resolved complaint within 7-day window",
)
def reopen_resident_complaint(
    complaint_id: UUID,
    payload: ReopenComplaintRequest,
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.RESIDENT))],
    db: Session = Depends(get_db),
) -> ComplaintResponse:
    service = ComplaintService(db)
    return service.reopen_complaint(claims, complaint_id, payload)


@router.post(
    "/me/{complaint_id}/rating",
    response_model=ComplaintResponse,
    summary="Submit satisfaction rating and feedback for resolved complaint",
)
def rate_resident_complaint(
    complaint_id: UUID,
    payload: RateComplaintRequest,
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.RESIDENT))],
    db: Session = Depends(get_db),
) -> ComplaintResponse:
    service = ComplaintService(db)
    return service.rate_complaint(claims, complaint_id, payload)


# =============================================================================
# Safety Alerts Endpoints
# =============================================================================


@router.get(
    "/safety-alerts",
    response_model=list[SafetyAlertResponse],
    summary="List persistent safety alerts for duty manager emergency queue",
)
def list_safety_alerts(
    claims: Annotated[CurrentUserClaims, Depends(require_permissions(Permission.COMPLAINT_MANAGE))],
    society_id: UUID | None = Query(None),
    unacknowledged_only: bool = Query(True),
    unread_only: bool | None = Query(None),
    db: Session = Depends(get_db),
) -> list[SafetyAlertResponse]:
    service = ComplaintService(db)
    filter_unack = unread_only if unread_only is not None else unacknowledged_only
    return service.list_safety_alerts(
        claims, society_id=society_id, unacknowledged_only=filter_unack
    )


@router.post(
    "/safety-alerts/{alert_id}/ack",
    response_model=SafetyAlertResponse,
    summary="Acknowledge persistent safety alert",
)
def acknowledge_safety_alert(
    alert_id: UUID,
    payload: AcknowledgeSafetyAlertRequest,
    claims: Annotated[CurrentUserClaims, Depends(require_permissions(Permission.COMPLAINT_MANAGE))],
    db: Session = Depends(get_db),
) -> SafetyAlertResponse:
    service = ComplaintService(db)
    return service.acknowledge_safety_alert(claims, alert_id, payload)


# =============================================================================
# Helpdesk Staff Operations Endpoints
# =============================================================================


@router.get(
    "/helpdesk/dashboard",
    response_model=HelpdeskDashboardMetricsResponse,
    summary="Get helpdesk operational KPI metrics",
)
@router.get(
    "/dashboard",
    response_model=HelpdeskDashboardMetricsResponse,
    include_in_schema=False,
)
def get_helpdesk_dashboard_metrics(
    claims: Annotated[CurrentUserClaims, Depends(require_permissions(Permission.COMPLAINT_MANAGE))],
    society_id: UUID | None = Query(None),
    db: Session = Depends(get_db),
) -> HelpdeskDashboardMetricsResponse:
    """Returns ticket counts, SLA breach metrics, and resolution turnaround times."""
    service = ComplaintService(db)
    return service.get_dashboard_metrics(claims, society_id=society_id)


@router.get(
    "/helpdesk",
    response_model=list[ComplaintResponse],
    summary="List society complaints for helpdesk operations",
)
def list_helpdesk_complaints(
    claims: Annotated[CurrentUserClaims, Depends(require_permissions(Permission.COMPLAINT_MANAGE))],
    response: Response,
    society_id: UUID | None = Query(None),
    assigned_to: UUID | None = Query(None),
    unassigned_only: bool = Query(False),
    complaint_status: list[ComplaintStatus] | None = Query(None, alias="status"),
    priority: ComplaintPriority | None = Query(None),
    category: ComplaintCategory | None = Query(None),
    tower_id: UUID | None = Query(None),
    search: str | None = Query(None),
    is_sla_breached: bool = Query(False),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[ComplaintResponse]:
    """Staff query endpoint with multi-filter capability and SLA breach detection."""
    service = ComplaintService(db)
    complaints, total = service.list_helpdesk_complaints(
        claims,
        society_id=society_id,
        assigned_to=assigned_to,
        unassigned_only=unassigned_only,
        statuses=complaint_status,
        priority=priority,
        category=category,
        tower_id=tower_id,
        search=search,
        is_sla_breached_only=is_sla_breached,
        offset=offset,
        limit=limit,
    )
    response.headers["X-Total-Count"] = str(total)
    return complaints


@router.get(
    "/helpdesk/{complaint_id}",
    response_model=ComplaintResponse,
    summary="Get full helpdesk complaint detail with duplicate candidates and internal notes",
)
def get_helpdesk_complaint(
    complaint_id: UUID,
    claims: Annotated[CurrentUserClaims, Depends(require_permissions(Permission.COMPLAINT_MANAGE))],
    db: Session = Depends(get_db),
) -> ComplaintResponse:
    service = ComplaintService(db)
    return service.get_helpdesk_complaint(claims, complaint_id)


@router.patch(
    "/helpdesk/{complaint_id}/status",
    response_model=ComplaintResponse,
    summary="Transition complaint lifecycle status",
)
def update_helpdesk_complaint_status(
    complaint_id: UUID,
    payload: UpdateComplaintStatusRequest,
    claims: Annotated[CurrentUserClaims, Depends(require_permissions(Permission.COMPLAINT_MANAGE))],
    db: Session = Depends(get_db),
) -> ComplaintResponse:
    service = ComplaintService(db)
    return service.update_status(claims, complaint_id, payload)


@router.patch(
    "/helpdesk/{complaint_id}/assign",
    response_model=ComplaintResponse,
    summary="Assign or reassign complaint to staff member",
)
def assign_helpdesk_complaint(
    complaint_id: UUID,
    payload: AssignComplaintRequest,
    claims: Annotated[CurrentUserClaims, Depends(require_permissions(Permission.COMPLAINT_MANAGE))],
    db: Session = Depends(get_db),
) -> ComplaintResponse:
    service = ComplaintService(db)
    return service.assign_complaint(claims, complaint_id, payload)


@router.patch(
    "/helpdesk/{complaint_id}/priority",
    response_model=ComplaintResponse,
    summary="Update complaint priority and recalculate SLA",
)
def update_helpdesk_complaint_priority(
    complaint_id: UUID,
    payload: UpdateComplaintPriorityRequest,
    claims: Annotated[CurrentUserClaims, Depends(require_permissions(Permission.COMPLAINT_MANAGE))],
    db: Session = Depends(get_db),
) -> ComplaintResponse:
    service = ComplaintService(db)
    return service.update_priority(claims, complaint_id, payload)


@router.patch(
    "/{complaint_id}/category",
    response_model=ComplaintResponse,
    summary="Correct AI or resident assigned category in 1 action",
)
@router.patch(
    "/helpdesk/{complaint_id}/category",
    response_model=ComplaintResponse,
    include_in_schema=False,
)
def correct_complaint_category(
    complaint_id: UUID,
    payload: UpdateComplaintCategoryRequest,
    claims: Annotated[CurrentUserClaims, Depends(require_permissions(Permission.COMPLAINT_MANAGE))],
    db: Session = Depends(get_db),
) -> ComplaintResponse:
    service = ComplaintService(db)
    return service.correct_category(claims, complaint_id, payload)


@router.post(
    "/{complaint_id}/link-duplicate",
    response_model=ComplaintResponse,
    summary="Link complaint as duplicate without auto-closing",
)
@router.post(
    "/helpdesk/{complaint_id}/link-duplicate",
    response_model=ComplaintResponse,
    include_in_schema=False,
)
def link_duplicate_complaint(
    complaint_id: UUID,
    payload: LinkDuplicateComplaintRequest,
    claims: Annotated[CurrentUserClaims, Depends(require_permissions(Permission.COMPLAINT_MANAGE))],
    db: Session = Depends(get_db),
) -> ComplaintResponse:
    service = ComplaintService(db)
    return service.link_duplicate(claims, complaint_id, payload)


@router.post(
    "/{complaint_id}/unlink-duplicate",
    response_model=ComplaintResponse,
    summary="Unlink duplicate complaint relationship",
)
@router.post(
    "/helpdesk/{complaint_id}/unlink-duplicate",
    response_model=ComplaintResponse,
    include_in_schema=False,
)
def unlink_duplicate_complaint(
    complaint_id: UUID,
    claims: Annotated[CurrentUserClaims, Depends(require_permissions(Permission.COMPLAINT_MANAGE))],
    db: Session = Depends(get_db),
) -> ComplaintResponse:
    service = ComplaintService(db)
    return service.unlink_duplicate(claims, complaint_id)


@router.get(
    "/{complaint_id}/linked-duplicates",
    response_model=list[ComplaintResponse],
    summary="List complaints linked as duplicates of this complaint",
)
@router.get(
    "/helpdesk/{complaint_id}/linked-duplicates",
    response_model=list[ComplaintResponse],
    include_in_schema=False,
)
def list_linked_duplicates(
    complaint_id: UUID,
    claims: Annotated[CurrentUserClaims, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> list[ComplaintResponse]:
    service = ComplaintService(db)
    return service.list_linked_duplicates(claims, complaint_id)


@router.post(
    "/helpdesk/{complaint_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add public comment or internal helpdesk note",
)
def add_helpdesk_comment(
    complaint_id: UUID,
    payload: CreateCommentRequest,
    claims: Annotated[CurrentUserClaims, Depends(require_permissions(Permission.COMPLAINT_MANAGE))],
    db: Session = Depends(get_db),
) -> CommentResponse:
    service = ComplaintService(db)
    return service.add_comment(claims, complaint_id, payload, is_staff=True)


@router.post(
    "/helpdesk/{complaint_id}/attachments",
    response_model=PresignedUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate photo/file attachment upload for helpdesk",
)
def initiate_helpdesk_attachment(
    complaint_id: UUID,
    payload: InitiateAttachmentUploadRequest,
    claims: Annotated[CurrentUserClaims, Depends(require_permissions(Permission.COMPLAINT_MANAGE))],
    db: Session = Depends(get_db),
) -> PresignedUploadResponse:
    service = ComplaintService(db)
    return service.initiate_attachment_upload(claims, complaint_id, payload, is_staff=True)


@router.post(
    "/helpdesk/{complaint_id}/attachments/{attachment_id}/complete",
    response_model=AttachmentResponse,
    summary="Complete and verify helpdesk attachment upload",
)
def complete_helpdesk_attachment(
    complaint_id: UUID,
    attachment_id: UUID,
    claims: Annotated[CurrentUserClaims, Depends(require_permissions(Permission.COMPLAINT_MANAGE))],
    db: Session = Depends(get_db),
) -> AttachmentResponse:
    service = ComplaintService(db)
    return service.complete_attachment_upload(claims, complaint_id, attachment_id, is_staff=True)


# =============================================================================
# Direct Convenience Endpoints
# =============================================================================


@router.get(
    "/{complaint_id}",
    response_model=ComplaintResponse,
    summary="Get complaint details (role-aware)",
)
def get_complaint_by_id(
    complaint_id: UUID,
    claims: Annotated[CurrentUserClaims, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> ComplaintResponse:
    service = ComplaintService(db)
    if RoleType.HELPDESK in claims.roles:
        return service.get_helpdesk_complaint(claims, complaint_id)
    return service.get_resident_complaint(claims, complaint_id)


@router.post(
    "/{complaint_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add comment to complaint (role-aware)",
)
def add_comment_direct(
    complaint_id: UUID,
    payload: CreateCommentRequest,
    claims: Annotated[CurrentUserClaims, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> CommentResponse:
    service = ComplaintService(db)
    is_staff = RoleType.HELPDESK in claims.roles
    return service.add_comment(claims, complaint_id, payload, is_staff=is_staff)


@router.post(
    "/{complaint_id}/attachments",
    response_model=PresignedUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate attachment upload (role-aware)",
)
def initiate_attachment_direct(
    complaint_id: UUID,
    payload: InitiateAttachmentUploadRequest,
    claims: Annotated[CurrentUserClaims, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> PresignedUploadResponse:
    service = ComplaintService(db)
    is_staff = RoleType.HELPDESK in claims.roles
    return service.initiate_attachment_upload(claims, complaint_id, payload, is_staff=is_staff)


@router.post(
    "/{complaint_id}/attachments/{attachment_id}/complete",
    response_model=AttachmentResponse,
    summary="Complete and verify attachment upload (role-aware)",
)
def complete_attachment_direct(
    complaint_id: UUID,
    attachment_id: UUID,
    claims: Annotated[CurrentUserClaims, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> AttachmentResponse:
    service = ComplaintService(db)
    is_staff = RoleType.HELPDESK in claims.roles
    return service.complete_attachment_upload(
        claims, complaint_id, attachment_id, is_staff=is_staff
    )


@router.post(
    "/{complaint_id}/reopen",
    response_model=ComplaintResponse,
    summary="Reopen resolved complaint",
)
def reopen_complaint_direct(
    complaint_id: UUID,
    payload: ReopenComplaintRequest,
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.RESIDENT))],
    db: Session = Depends(get_db),
) -> ComplaintResponse:
    service = ComplaintService(db)
    return service.reopen_complaint(claims, complaint_id, payload)


@router.post(
    "/{complaint_id}/rating",
    response_model=ComplaintResponse,
    summary="Rate resolved complaint",
)
def rate_complaint_direct(
    complaint_id: UUID,
    payload: RateComplaintRequest,
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.RESIDENT))],
    db: Session = Depends(get_db),
) -> ComplaintResponse:
    service = ComplaintService(db)
    return service.rate_complaint(claims, complaint_id, payload)
