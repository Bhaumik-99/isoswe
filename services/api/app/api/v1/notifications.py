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

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AuthorizationError
from app.core.security import get_current_user, require_roles
from app.domains.identity.models import RoleType
from app.domains.identity.schemas import CurrentUserClaims
from app.domains.notifications.schemas import (
    MarkAllReadResponse,
    MarkReadResponse,
    NotificationPreferenceSchema,
    PaginatedNotificationsResponse,
    StaffNotificationOverviewResponse,
    UnreadCountResponse,
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
