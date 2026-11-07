"""API Version 1 Notifications & Resident Communication Endpoints

Provides REST endpoints for:
- Resident & Staff in-app notification inbox (newest-first, paginated, unread filtering)
- Real-time unread badge counts
- Mark single notification or all notifications as read
- User communication channel preferences (Email, SMS, In-App)
- Staff delivery overview and failure tracking
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AuthorizationError
from app.core.security import get_current_user, require_permissions, require_roles
from app.domains.identity.models import Permission, RoleType
from app.domains.identity.schemas import CurrentUserClaims
from app.domains.notifications.models import (
    NoticeCategory,
    NoticeStatus,
    NoticeTargetType,
)
from app.domains.notifications.notice_service import NoticeService
from app.domains.notifications.schemas import (
    CreateNoticeRequest,
    FlatOptionSchema,
    MarkAllNoticesReadResponse,
    MarkAllReadResponse,
    MarkNoticeReadResponse,
    MarkReadResponse,
    NoticeOverviewStatsResponse,
    NoticeResponseSchema,
    NoticeTargetingOptionsResponse,
    NotificationPreferenceSchema,
    PaginatedNoticesResponse,
    PaginatedNotificationsResponse,
    PublishNoticeRequest,
    StaffNotificationOverviewResponse,
    TowerOptionSchema,
    UnreadCountResponse,
    UpdateNoticeRequest,
    UpdateNotificationPreferenceRequest,
)
from app.domains.notifications.service import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications & Resident Communication"])


def _resolve_society_id(claims: CurrentUserClaims, query_society_id: UUID | None = None) -> UUID:
    if query_society_id:
        if query_society_id not in claims.society_ids:
            raise AuthorizationError(
                f"Access denied: User does not belong to society {query_society_id}"
            )
        return query_society_id
    if claims.society_ids:
        return claims.society_ids[0]
    raise AuthorizationError("No authorized society found for current user")


# =============================================================================
# In-App Notification Inbox Endpoints (Resident & Staff)
# =============================================================================


@router.get(
    "/me",
    response_model=PaginatedNotificationsResponse,
    summary="Get paginated notifications inbox for current user",
)
def get_my_notifications(
    claims: Annotated[CurrentUserClaims, Depends(get_current_user)],
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    unread_only: bool = Query(False, description="Filter for unread notifications only"),
    society_id: UUID | None = Query(None, description="Optional society filter"),
    db: Session = Depends(get_db),
) -> PaginatedNotificationsResponse:
    target_society = _resolve_society_id(claims, society_id)
    service = NotificationService(db)
    return service.get_user_notifications(
        society_id=target_society,
        user_id=claims.user_id,
        page=page,
        page_size=page_size,
        unread_only=unread_only,
    )


@router.get(
    "/me/unread-count",
    response_model=UnreadCountResponse,
    summary="Get unread notifications count for badge display",
)
def get_my_unread_count(
    claims: Annotated[CurrentUserClaims, Depends(get_current_user)],
    society_id: UUID | None = Query(None, description="Optional society filter"),
    db: Session = Depends(get_db),
) -> UnreadCountResponse:
    target_society = _resolve_society_id(claims, society_id)
    service = NotificationService(db)
    count = service.get_unread_count(society_id=target_society, user_id=claims.user_id)
    return UnreadCountResponse(unread_count=count)


@router.patch(
    "/me/{notification_id}/read",
    response_model=MarkReadResponse,
    summary="Mark a specific notification as read",
)
def mark_notification_as_read(
    notification_id: UUID,
    claims: Annotated[CurrentUserClaims, Depends(get_current_user)],
    society_id: UUID | None = Query(None, description="Optional society filter"),
    db: Session = Depends(get_db),
) -> MarkReadResponse:
    target_society = _resolve_society_id(claims, society_id)
    service = NotificationService(db)
    notif = service.mark_notification_as_read(
        society_id=target_society,
        user_id=claims.user_id,
        notification_id=notification_id,
    )
    return MarkReadResponse(
        notification_id=notif.id,
        read_at=notif.read_at,  # type: ignore[arg-type]
        status="success",
    )


@router.patch(
    "/me/read-all",
    response_model=MarkAllReadResponse,
    summary="Mark all unread notifications as read for current user",
)
def mark_all_notifications_as_read(
    claims: Annotated[CurrentUserClaims, Depends(get_current_user)],
    society_id: UUID | None = Query(None, description="Optional society filter"),
    db: Session = Depends(get_db),
) -> MarkAllReadResponse:
    target_society = _resolve_society_id(claims, society_id)
    service = NotificationService(db)
    marked_count = service.mark_all_notifications_as_read(
        society_id=target_society,
        user_id=claims.user_id,
    )
    return MarkAllReadResponse(
        marked_count=marked_count,
        status="success",
    )


# =============================================================================
# Communication Channel Preferences
# =============================================================================


@router.get(
    "/me/preferences",
    response_model=NotificationPreferenceSchema,
    summary="Get user communication channel preferences",
)
def get_notification_preferences(
    claims: Annotated[CurrentUserClaims, Depends(get_current_user)],
    society_id: UUID | None = Query(None, description="Optional society filter"),
    db: Session = Depends(get_db),
) -> NotificationPreferenceSchema:
    target_society = _resolve_society_id(claims, society_id)
    service = NotificationService(db)
    return service.get_user_preferences_schema(
        society_id=target_society,
        user_id=claims.user_id,
    )


@router.put(
    "/me/preferences",
    response_model=NotificationPreferenceSchema,
    summary="Update user communication channel preferences",
)
def update_notification_preferences(
    payload: UpdateNotificationPreferenceRequest,
    claims: Annotated[CurrentUserClaims, Depends(get_current_user)],
    society_id: UUID | None = Query(None, description="Optional society filter"),
    db: Session = Depends(get_db),
) -> NotificationPreferenceSchema:
    target_society = _resolve_society_id(claims, society_id)
    service = NotificationService(db)
    return service.update_user_preferences(
        society_id=target_society,
        user_id=claims.user_id,
        req=payload,
    )


# =============================================================================
# Staff Operational Overview Endpoints
# =============================================================================


@router.get(
    "/staff/overview",
    response_model=StaffNotificationOverviewResponse,
    summary="Operational notification deliveries overview and failure statistics for facility staff",
)
def get_staff_notification_overview(
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.HELPDESK))],
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    society_id: UUID | None = Query(None, description="Optional society filter"),
    db: Session = Depends(get_db),
) -> StaffNotificationOverviewResponse:
    target_society = _resolve_society_id(claims, society_id)
    service = NotificationService(db)
    return service.get_staff_overview(
        society_id=target_society,
        page=page,
        page_size=page_size,
    )


# =============================================================================
# Resident Official Notices Feed & Read Tracking Endpoints
# =============================================================================


@router.get(
    "/resident/notices",
    response_model=PaginatedNoticesResponse,
    summary="Get targeted official township notices feed for resident",
)
def get_resident_notices(
    claims: Annotated[CurrentUserClaims, Depends(get_current_user)],
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    category: NoticeCategory | None = Query(None, description="Optional category filter"),
    unread_only: bool = Query(False, description="Filter for unread notices only"),
    society_id: UUID | None = Query(None, description="Optional society filter"),
    db: Session = Depends(get_db),
) -> PaginatedNoticesResponse:
    target_society = _resolve_society_id(claims, society_id)
    service = NoticeService(db)
    return service.list_resident_notices(
        society_id=target_society,
        user_id=claims.user_id,
        page=page,
        page_size=page_size,
        category=category,
        unread_only=unread_only,
    )


@router.get(
    "/resident/notices/unread-count",
    response_model=UnreadCountResponse,
    summary="Get unread official notice count for the current resident",
)
def get_resident_notices_unread_count(
    claims: Annotated[CurrentUserClaims, Depends(get_current_user)],
    society_id: UUID | None = Query(None, description="Optional society filter"),
    db: Session = Depends(get_db),
) -> UnreadCountResponse:
    target_society = _resolve_society_id(claims, society_id)
    service = NoticeService(db)
    count = service.get_resident_unread_count(
        society_id=target_society,
        user_id=claims.user_id,
    )
    return UnreadCountResponse(unread_count=count)


@router.get(
    "/resident/notices/{notice_id}",
    response_model=NoticeResponseSchema,
    summary="Get single official notice details for resident",
)
def get_resident_notice_detail(
    notice_id: UUID,
    claims: Annotated[CurrentUserClaims, Depends(get_current_user)],
    society_id: UUID | None = Query(None, description="Optional society filter"),
    db: Session = Depends(get_db),
) -> NoticeResponseSchema:
    target_society = _resolve_society_id(claims, society_id)
    service = NoticeService(db)
    return service.get_resident_notice(
        society_id=target_society,
        user_id=claims.user_id,
        notice_id=notice_id,
    )


@router.patch(
    "/resident/notices/{notice_id}/read",
    response_model=MarkNoticeReadResponse,
    summary="Mark single official notice as read for current resident",
)
def mark_resident_notice_read(
    notice_id: UUID,
    claims: Annotated[CurrentUserClaims, Depends(get_current_user)],
    society_id: UUID | None = Query(None, description="Optional society filter"),
    db: Session = Depends(get_db),
) -> MarkNoticeReadResponse:
    target_society = _resolve_society_id(claims, society_id)
    service = NoticeService(db)
    return service.mark_notice_read(
        society_id=target_society,
        user_id=claims.user_id,
        notice_id=notice_id,
    )


@router.patch(
    "/resident/notices/read-all",
    response_model=MarkAllNoticesReadResponse,
    summary="Mark all visible unread notices as read for current resident",
)
def mark_all_resident_notices_read(
    claims: Annotated[CurrentUserClaims, Depends(get_current_user)],
    society_id: UUID | None = Query(None, description="Optional society filter"),
    db: Session = Depends(get_db),
) -> MarkAllNoticesReadResponse:
    target_society = _resolve_society_id(claims, society_id)
    service = NoticeService(db)
    return service.mark_all_notices_read(
        society_id=target_society,
        user_id=claims.user_id,
    )


# =============================================================================
# Staff Official Notice Management Endpoints
# =============================================================================


@router.get(
    "/staff/targeting-options",
    response_model=NoticeTargetingOptionsResponse,
    summary="Load towers and flats dynamically for notice composer",
)
def get_notice_targeting_options(
    claims: Annotated[
        CurrentUserClaims, Depends(require_permissions(Permission.COMMUNICATIONS_MANAGE))
    ],
    society_id: UUID | None = Query(None, description="Optional society filter"),
    db: Session = Depends(get_db),
) -> NoticeTargetingOptionsResponse:
    target_society = _resolve_society_id(claims, society_id)
    service = NoticeService(db)
    return service.get_targeting_options(target_society)


@router.get(
    "/staff/towers",
    response_model=list[TowerOptionSchema],
    summary="List all towers in society dynamically for notice targeting",
)
def list_society_towers(
    claims: Annotated[
        CurrentUserClaims, Depends(require_permissions(Permission.COMMUNICATIONS_MANAGE))
    ],
    society_id: UUID | None = Query(None, description="Optional society filter"),
    db: Session = Depends(get_db),
) -> list[TowerOptionSchema]:
    target_society = _resolve_society_id(claims, society_id)
    service = NoticeService(db)
    return service.list_society_towers(target_society)


@router.get(
    "/staff/flats",
    response_model=list[FlatOptionSchema],
    summary="List flats in society dynamically for notice targeting",
)
def list_society_flats(
    claims: Annotated[
        CurrentUserClaims, Depends(require_permissions(Permission.COMMUNICATIONS_MANAGE))
    ],
    society_id: UUID | None = Query(None, description="Optional society filter"),
    tower_id: UUID | None = Query(None, description="Optional tower filter"),
    search: str | None = Query(None, description="Optional flat number search"),
    limit: int = Query(200, ge=1, le=500, description="Max flats to return"),
    db: Session = Depends(get_db),
) -> list[FlatOptionSchema]:
    target_society = _resolve_society_id(claims, society_id)
    service = NoticeService(db)
    return service.list_society_flats(
        society_id=target_society,
        tower_id=tower_id,
        search=search,
        limit=limit,
    )


@router.get(
    "/staff/notices",
    response_model=PaginatedNoticesResponse,
    summary="List all official notices with management filters for staff",
)
def list_staff_notices(
    claims: Annotated[
        CurrentUserClaims, Depends(require_permissions(Permission.COMMUNICATIONS_MANAGE))
    ],
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status: NoticeStatus | None = Query(None, description="Filter by notice status"),
    category: NoticeCategory | None = Query(None, description="Filter by category"),
    target_type: NoticeTargetType | None = Query(None, description="Filter by target type"),
    search: str | None = Query(None, description="Search in title or body"),
    society_id: UUID | None = Query(None, description="Optional society filter"),
    db: Session = Depends(get_db),
) -> PaginatedNoticesResponse:
    target_society = _resolve_society_id(claims, society_id)
    service = NoticeService(db)
    return service.list_staff_notices(
        society_id=target_society,
        page=page,
        page_size=page_size,
        status=status,
        category=category,
        target_type=target_type,
        search=search,
    )


@router.post(
    "/staff/notices",
    response_model=NoticeResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create official township notice (draft, published, or scheduled)",
)
def create_staff_notice(
    payload: CreateNoticeRequest,
    claims: Annotated[
        CurrentUserClaims, Depends(require_permissions(Permission.COMMUNICATIONS_MANAGE))
    ],
    society_id: UUID | None = Query(None, description="Optional society filter"),
    db: Session = Depends(get_db),
) -> NoticeResponseSchema:
    target_society = _resolve_society_id(claims, society_id)
    service = NoticeService(db)
    return service.create_notice(
        society_id=target_society,
        author_id=claims.user_id,
        req=payload,
    )


@router.get(
    "/staff/notices/overview",
    response_model=NoticeOverviewStatsResponse,
    summary="Overview counts across official notice statuses and emergency announcements",
)
def get_staff_notices_overview(
    claims: Annotated[
        CurrentUserClaims, Depends(require_permissions(Permission.COMMUNICATIONS_MANAGE))
    ],
    society_id: UUID | None = Query(None, description="Optional society filter"),
    db: Session = Depends(get_db),
) -> NoticeOverviewStatsResponse:
    target_society = _resolve_society_id(claims, society_id)
    service = NoticeService(db)
    return service.get_staff_notices_overview(target_society)


@router.get(
    "/staff/notices/{notice_id}",
    response_model=NoticeResponseSchema,
    summary="Get single official notice details for staff",
)
def get_staff_notice_detail(
    notice_id: UUID,
    claims: Annotated[
        CurrentUserClaims, Depends(require_permissions(Permission.COMMUNICATIONS_MANAGE))
    ],
    society_id: UUID | None = Query(None, description="Optional society filter"),
    db: Session = Depends(get_db),
) -> NoticeResponseSchema:
    target_society = _resolve_society_id(claims, society_id)
    service = NoticeService(db)
    return service.get_notice(
        society_id=target_society,
        notice_id=notice_id,
    )


@router.put(
    "/staff/notices/{notice_id}",
    response_model=NoticeResponseSchema,
    summary="Edit and update an official township notice",
)
def update_staff_notice(
    notice_id: UUID,
    payload: UpdateNoticeRequest,
    claims: Annotated[
        CurrentUserClaims, Depends(require_permissions(Permission.COMMUNICATIONS_MANAGE))
    ],
    society_id: UUID | None = Query(None, description="Optional society filter"),
    db: Session = Depends(get_db),
) -> NoticeResponseSchema:
    target_society = _resolve_society_id(claims, society_id)
    service = NoticeService(db)
    return service.update_notice(
        society_id=target_society,
        actor_id=claims.user_id,
        notice_id=notice_id,
        req=payload,
    )


@router.post(
    "/staff/notices/{notice_id}/publish",
    response_model=NoticeResponseSchema,
    summary="Publish draft notice to active status",
)
def publish_staff_notice(
    notice_id: UUID,
    claims: Annotated[
        CurrentUserClaims, Depends(require_permissions(Permission.COMMUNICATIONS_MANAGE))
    ],
    payload: PublishNoticeRequest | None = None,
    society_id: UUID | None = Query(None, description="Optional society filter"),
    db: Session = Depends(get_db),
) -> NoticeResponseSchema:
    target_society = _resolve_society_id(claims, society_id)
    service = NoticeService(db)
    return service.publish_notice(
        society_id=target_society,
        actor_id=claims.user_id,
        notice_id=notice_id,
        req=payload,
    )


@router.post(
    "/staff/notices/{notice_id}/archive",
    response_model=NoticeResponseSchema,
    summary="Archive published notice",
)
def archive_staff_notice(
    notice_id: UUID,
    claims: Annotated[
        CurrentUserClaims, Depends(require_permissions(Permission.COMMUNICATIONS_MANAGE))
    ],
    society_id: UUID | None = Query(None, description="Optional society filter"),
    db: Session = Depends(get_db),
) -> NoticeResponseSchema:
    target_society = _resolve_society_id(claims, society_id)
    service = NoticeService(db)
    return service.archive_notice(
        society_id=target_society,
        actor_id=claims.user_id,
        notice_id=notice_id,
    )


@router.post(
    "/staff/notices/publish-scheduled",
    response_model=list[NoticeResponseSchema],
    summary="Trigger immediate publication of all due scheduled notices",
)
def trigger_publish_due_scheduled_notices(
    claims: Annotated[
        CurrentUserClaims, Depends(require_permissions(Permission.COMMUNICATIONS_MANAGE))
    ],
    society_id: UUID | None = Query(None, description="Optional society filter"),
    db: Session = Depends(get_db),
) -> list[NoticeResponseSchema]:
    target_society = _resolve_society_id(claims, society_id)
    service = NoticeService(db)
    return service.publish_due_scheduled_notices(society_id=target_society)
