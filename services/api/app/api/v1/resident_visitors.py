"""API Version 1 Resident Visitor & Pass Endpoints

Provides REST endpoints for resident portal visitor workflows:
- Pending Visitor Inbox: Review and act on visitor arrivals within 2 taps
- Idempotent Action: Transactional approve / reject with audit logging
- Today's & Historical Feeds: Visitor logs filtered to resident's active flats
- Photo Inspection: Secure presigned download URL with IDOR access prevention
- Pre-Approved Guest Passes: Create, list, and revoke single-use and multi-use passes
"""

import contextlib
import uuid
from datetime import UTC, datetime, time
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AuthorizationError
from app.core.security import require_roles
from app.domains.identity.models import Flat, RoleType
from app.domains.identity.schemas import CurrentUserClaims
from app.domains.visitors.models import (
    ApprovalStatus,
    GuestPass,
    VisitorRecord,
)
from app.domains.visitors.pass_service import GuestPassService
from app.domains.visitors.retention_service import PhotoRetentionService
from app.domains.visitors.schemas import (
    GuestPassCreateRequest,
    ResidentVisitorActionRequest,
)
from app.domains.visitors.service import VisitorService

router = APIRouter(prefix="/resident", tags=["Resident Visitors & Passes"])


def utc_now() -> datetime:
    return datetime.now(UTC)


def _get_resident_context(claims: CurrentUserClaims) -> tuple[uuid.UUID, list[uuid.UUID]]:
    """Helper to verify that resident has RESIDENT role and active flat memberships."""
    if RoleType.RESIDENT not in claims.roles:
        raise AuthorizationError(
            code="INSUFFICIENT_PERMISSIONS",
            message="Endpoint requires RESIDENT role.",
        )
    society_id = claims.society_ids[0] if claims.society_ids else None
    if not society_id:
        raise AuthorizationError(
            code="TENANT_ISOLATION_ERROR",
            message="No society associated with authenticated resident.",
        )
    return society_id, claims.active_flat_ids


# =============================================================================
# 1. Visitor Approvals & Feeds Endpoints
# =============================================================================


@router.get("/visitors/pending", response_model=list[dict[str, Any]])
def get_pending_visitors(
    claims: CurrentUserClaims = Depends(require_roles(RoleType.RESIDENT)),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Resident pending approvals inbox accessible within two taps."""
    society_id, active_flats = _get_resident_context(claims)
    if not active_flats:
        return []

    stmt = (
        select(VisitorRecord)
        .where(
            VisitorRecord.society_id == society_id,
            VisitorRecord.destination_flat_id.in_(active_flats),
            VisitorRecord.approval_status == ApprovalStatus.PENDING,
        )
        .order_by(VisitorRecord.created_at.desc())
    )
    records = list(db.scalars(stmt).all())
    retention_service = PhotoRetentionService(db)

    results = []
    for r in records:
        photo_url = None
        if r.photo_key and not r.is_photo_expired:
            with contextlib.suppress(Exception):
                photo_url = retention_service.storage_provider.generate_download_url(
                    r.photo_key, expires_in_seconds=900
                )

        flat = db.get(Flat, r.destination_flat_id)
        results.append(
            {
                "visitor_id": str(r.id),
                "society_id": str(r.society_id),
                "gate_id": str(r.gate_id),
                "visitor_name": r.visitor_name,
                "phone_masked": r.masked_phone,
                "vehicle_number": r.vehicle_number,
                "purpose": r.purpose.value,
                "destination_flat_id": str(r.destination_flat_id),
                "destination_flat": {
                    "flat_id": str(flat.id) if flat else str(r.destination_flat_id),
                    "flat_number": flat.flat_number if flat else "",
                    "tower_name": flat.tower.name if flat and flat.tower else "",
                }
                if flat
                else None,
                "approval_status": r.approval_status.value,
                "entry_status": r.entry_status.value,
                "photo_url": photo_url,
                "photo_storage_key": r.photo_key,
                "created_at": r.created_at.isoformat(),
            }
        )
    return results


@router.post("/visitors/{visitor_id}/action")
def handle_visitor_approval_action(
    visitor_id: uuid.UUID,
    body: ResidentVisitorActionRequest,
    claims: CurrentUserClaims = Depends(require_roles(RoleType.RESIDENT)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """In-app resident approval or rejection with idempotency and flat membership checks."""
    _get_resident_context(claims)
    service = VisitorService(db)
    visitor = service.handle_resident_action(
        visitor_id=visitor_id,
        action=body.action,
        resident_user_id=claims.user_id,
        reason=body.reason,
    )
    db.commit()

    return {
        "visitor_id": str(visitor.id),
        "approval_status": visitor.approval_status.value,
        "approved_at": visitor.approval_action_at.isoformat()
        if visitor.approval_action_at
        else None,
        "action_by_user_id": str(claims.user_id),
    }


@router.get("/visitors/today")
def get_today_visitors(
    claims: CurrentUserClaims = Depends(require_roles(RoleType.RESIDENT)),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Returns today's visitors and expected arrivals for resident's active flats."""
    society_id, active_flats = _get_resident_context(claims)
    if not active_flats:
        return []

    now = utc_now()
    start_of_today = datetime.combine(now.date(), time.min, tzinfo=UTC)

    stmt = (
        select(VisitorRecord)
        .where(
            VisitorRecord.society_id == society_id,
            VisitorRecord.destination_flat_id.in_(active_flats),
            VisitorRecord.created_at >= start_of_today,
        )
        .order_by(VisitorRecord.created_at.desc())
    )
    records = list(db.scalars(stmt).all())

    results = []
    for r in records:
        results.append(
            {
                "visitor_id": str(r.id),
                "visitor_name": r.visitor_name,
                "phone_masked": r.masked_phone,
                "purpose": r.purpose.value,
                "destination_flat_id": str(r.destination_flat_id),
                "approval_status": r.approval_status.value,
                "entry_status": r.entry_status.value,
                "created_at": r.created_at.isoformat(),
                "entry_time": r.entry_time.isoformat() if r.entry_time else None,
                "exit_time": r.exit_time.isoformat() if r.exit_time else None,
            }
        )
    return results


@router.get("/visitors/history")
def get_resident_visitor_history(
    limit: int = Query(default=20),
    offset: int = Query(default=0),
    claims: CurrentUserClaims = Depends(require_roles(RoleType.RESIDENT)),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Historical visitor logs for resident's active flats."""
    society_id, active_flats = _get_resident_context(claims)
    if not active_flats:
        return []

    stmt = (
        select(VisitorRecord)
        .where(
            VisitorRecord.society_id == society_id,
            VisitorRecord.destination_flat_id.in_(active_flats),
        )
        .order_by(VisitorRecord.created_at.desc())
        .offset(offset)
        .limit(min(limit, 50))
    )
    records = list(db.scalars(stmt).all())

    results = []
    for r in records:
        results.append(
            {
                "visitor_id": str(r.id),
                "visitor_name": r.visitor_name,
                "phone_masked": r.masked_phone,
                "purpose": r.purpose.value,
                "destination_flat_id": str(r.destination_flat_id),
                "approval_status": r.approval_status.value,
                "entry_status": r.entry_status.value,
                "created_at": r.created_at.isoformat(),
                "entry_time": r.entry_time.isoformat() if r.entry_time else None,
                "exit_time": r.exit_time.isoformat() if r.exit_time else None,
            }
        )
    return results


@router.get("/visitors/{visitor_id}/photo")
def get_resident_visitor_photo(
    visitor_id: uuid.UUID,
    claims: CurrentUserClaims = Depends(require_roles(RoleType.RESIDENT)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Resident visitor photo download URL with IDOR protection (CHAL-17) and 90-day cutoff."""
    society_id, active_flats = _get_resident_context(claims)
    retention_service = PhotoRetentionService(db)
    return retention_service.get_visitor_photo_presigned_url(
        visitor_id=visitor_id,
        requester_user_id=claims.user_id,
        society_id=society_id,
        is_guard=False,
        active_flat_ids=active_flats,
    )


# =============================================================================
# 2. Pre-Approved Guest Pass Endpoints
# =============================================================================


@router.post("/passes", status_code=status.HTTP_201_CREATED)
def create_guest_pass(
    body: GuestPassCreateRequest,
    claims: CurrentUserClaims = Depends(require_roles(RoleType.RESIDENT)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Resident issues a pre-approved guest pass (CSPRNG code + salted SHA-256 hash)."""
    society_id, active_flats = _get_resident_context(claims)
    service = GuestPassService(db)
    result = service.create_guest_pass(
        society_id=society_id,
        resident_user_id=claims.user_id,
        destination_flat_id=body.destination_flat_id,
        guest_name=body.guest_name,
        purpose=body.purpose,
        pass_type=body.pass_type,
        valid_from=body.valid_from,
        valid_until=body.valid_until,
        max_uses=body.max_uses,
        guest_phone=body.guest_phone,
        active_flat_ids=active_flats,
    )
    return result


@router.get("/passes")
def list_resident_passes(
    claims: CurrentUserClaims = Depends(require_roles(RoleType.RESIDENT)),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Lists pre-approved guest passes for resident's active flats. Passcode is NEVER exposed."""
    society_id, active_flats = _get_resident_context(claims)
    if not active_flats:
        return []

    stmt = (
        select(GuestPass)
        .where(
            GuestPass.society_id == society_id,
            GuestPass.destination_flat_id.in_(active_flats),
        )
        .order_by(GuestPass.created_at.desc())
    )
    passes = list(db.scalars(stmt).all())

    results = []
    for p in passes:
        results.append(
            {
                "pass_id": str(p.id),
                "pass_code": None,  # Plaintext passcode is never returned!
                "pass_type": p.pass_type.value,
                "max_uses": p.max_uses,
                "used_count": p.used_count,
                "valid_from": p.valid_from.isoformat(),
                "valid_until": p.valid_until.isoformat(),
                "status": p.status.value,
                "destination_flat_id": str(p.destination_flat_id),
                "guest_name": p.guest_name,
                "purpose": p.purpose,
            }
        )
    return results


@router.post("/passes/{pass_id}/revoke")
async def revoke_guest_pass(
    pass_id: uuid.UUID,
    request: Request,
    claims: CurrentUserClaims = Depends(require_roles(RoleType.RESIDENT)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Resident revokes an unexhausted guest pass."""
    society_id, active_flats = _get_resident_context(claims)
    reason: str | None = None
    try:
        body = await request.json()
        reason = body.get("reason")
    except Exception:
        pass

    service = GuestPassService(db)
    result = service.revoke_guest_pass(
        pass_id=pass_id,
        resident_user_id=claims.user_id,
        reason=reason,
        active_flat_ids=active_flats,
    )
    return result
