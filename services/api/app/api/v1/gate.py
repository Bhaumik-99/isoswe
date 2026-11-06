"""API Version 1 Gate Operator Endpoints

Provides REST endpoints for tablet perimeter operations:
- Session & Overview: Gate assignment and connection status
- Registration: Walk-in visitor capture with multipart and JSON base64 support
- Check-In & Check-Out: Decoupled physical entry and exit state transitions
- Campus Activity & Visitor History: Filterable, paginated query endpoints
- Pass Verification: CSPRNG code verification and automated redemption
- Offline Sync: Replay-protected batch synchronization
- Privacy Notice: Tri-lingual compliance notice
"""

import base64
import contextlib
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import String, cast, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import (
    AuthorizationError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.security import get_current_user, require_roles
from app.domains.identity.models import Flat, Permission, RoleType
from app.domains.identity.schemas import CurrentUserClaims
from app.domains.visitors.models import (
    ApprovalStatus,
    EntryStatus,
    Gate,
    GateStaffAssignment,
    VisitorRecord,
)
from app.domains.visitors.pass_service import GuestPassService
from app.domains.visitors.retention_service import PhotoRetentionService
from app.domains.visitors.schemas import (
    GateSessionResponse,
    GuestPassVerifyRequest,
    GuestPassVerifyResponse,
    OfflineSyncBatchRequest,
    OfflineSyncBatchResponse,
    PrivacyNoticeResponse,
    VisitorRegisterRequest,
)
from app.domains.visitors.service import VisitorService
from app.domains.visitors.sync_service import OfflineSyncService

router = APIRouter(prefix="/gate", tags=["Gate Operations"])


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_utc(dt: datetime | None) -> datetime:
    if dt is None:
        return datetime.now(UTC)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def get_gate_by_id(db: Session, gate_id: uuid.UUID) -> Gate | None:
    gate = db.get(Gate, gate_id)
    if gate:
        return gate
    stmt = select(Gate).where(
        or_(
            cast(Gate.id, String) == str(gate_id),
            cast(Gate.id, String) == gate_id.hex,
        )
    )
    return db.scalars(stmt).first()


def _get_guard_society_and_assignment(
    claims: CurrentUserClaims, db: Session, requested_gate_id: uuid.UUID | None = None
) -> tuple[uuid.UUID, GateStaffAssignment]:
    """Helper to verify that guard has HELPDESK role, GATE_OPERATIONS permission,
    and an active temporal assignment to the requested gate (or primary gate).
    """
    if RoleType.HELPDESK not in claims.roles:
        raise AuthorizationError(
            code="INSUFFICIENT_PERMISSIONS",
            message="Gate operations require HELPDESK staff role.",
        )

    # Check for GATE_OPERATIONS permission in claims or user_permissions table
    has_gate_perm = Permission.GATE_OPERATIONS in claims.permissions or any(
        getattr(p, "value", str(p)) == "GATE_OPERATIONS" for p in claims.permissions
    )
    if not has_gate_perm:
        from sqlalchemy import text

        uid_str = str(claims.user_id)
        uid_hex = claims.user_id.hex
        perm_row = db.execute(
            text(
                "SELECT id FROM user_permissions WHERE (user_id = :u1 OR user_id = :u2) AND permission = 'GATE_OPERATIONS'"
            ),
            {"u1": uid_str, "u2": uid_hex},
        ).fetchone()
        if perm_row:
            has_gate_perm = True

    if not has_gate_perm:
        raise AuthorizationError(
            code="INSUFFICIENT_PERMISSIONS",
            message="Gate operations require GATE_OPERATIONS permission.",
        )

    society_id = claims.society_ids[0] if claims.society_ids else None
    if not society_id:
        raise AuthorizationError(
            code="GATE_ACCESS_DENIED",
            message="No society associated with authenticated guard.",
        )

    now = utc_now()
    user_cond = or_(
        cast(GateStaffAssignment.user_id, String) == str(claims.user_id),
        cast(GateStaffAssignment.user_id, String) == claims.user_id.hex,
    )
    society_cond = or_(
        cast(GateStaffAssignment.society_id, String) == str(society_id),
        cast(GateStaffAssignment.society_id, String) == society_id.hex,
    )
    stmt = select(GateStaffAssignment).where(
        society_cond,
        user_cond,
        GateStaffAssignment.is_active.is_(True),
    )
    if requested_gate_id:
        gate_cond = or_(
            cast(GateStaffAssignment.gate_id, String) == str(requested_gate_id),
            cast(GateStaffAssignment.gate_id, String) == requested_gate_id.hex,
        )
        stmt = stmt.where(gate_cond)

    assignments = list(db.scalars(stmt).all())
    assignment: GateStaffAssignment | None = None
    for a in assignments:
        a_from = ensure_utc(a.assigned_from)
        if a_from > now:
            continue
        if a.assigned_until is not None and ensure_utc(a.assigned_until) < now:
            continue
        assignment = a
        break

    if not assignment:
        raise AuthorizationError(
            code="GATE_ACCESS_DENIED",
            message=f"Guard is not actively assigned to the requested gate in society {society_id}.",
        )
    return society_id, assignment


# =============================================================================
# 1. Gate Session & Overview Endpoints
# =============================================================================


@router.get("/session", response_model=GateSessionResponse)
def get_gate_session(
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> GateSessionResponse:
    """Authenticates gate operator tablet, identifies assigned gate and society, and returns available gates."""
    society_id, primary_assignment = _get_guard_society_and_assignment(claims, db)
    now = utc_now()

    # Query all active assignments for guard to show available gates
    user_cond = or_(
        cast(GateStaffAssignment.user_id, String) == str(claims.user_id),
        cast(GateStaffAssignment.user_id, String) == claims.user_id.hex,
    )
    society_cond = or_(
        cast(GateStaffAssignment.society_id, String) == str(society_id),
        cast(GateStaffAssignment.society_id, String) == society_id.hex,
    )
    stmt = select(GateStaffAssignment).where(
        society_cond,
        user_cond,
        GateStaffAssignment.is_active.is_(True),
    )
    assignments = list(db.scalars(stmt).all())

    available_gates: list[dict[str, Any]] = []
    seen_gate_ids = set()
    for a in assignments:
        a_from = ensure_utc(a.assigned_from)
        if a_from > now:
            continue
        if a.assigned_until is not None and ensure_utc(a.assigned_until) < now:
            continue
        gate_obj = get_gate_by_id(db, a.gate_id)
        if gate_obj and str(gate_obj.id) not in seen_gate_ids:
            seen_gate_ids.add(str(gate_obj.id))
            available_gates.append(
                {
                    "gate_id": gate_obj.id,
                    "gate_number": gate_obj.gate_number,
                    "gate_name": gate_obj.display_name,
                }
            )
    available_gates.sort(key=lambda g: str(g["gate_number"]))

    primary_gate = get_gate_by_id(db, primary_assignment.gate_id)
    assigned_gate_dict = (
        {
            "gate_id": primary_gate.id,
            "gate_number": primary_gate.gate_number,
            "gate_name": primary_gate.display_name,
            "assigned_from": primary_assignment.assigned_from,
            "assigned_until": primary_assignment.assigned_until,
        }
        if primary_gate
        else None
    )

    return GateSessionResponse(
        user_id=claims.user_id,
        full_name=claims.full_name or "Gate Guard",
        society_id=society_id,
        assigned_gate=assigned_gate_dict,
        available_gates=available_gates,
    )


@router.get("/overview")
def get_gate_overview(
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Provides high-contrast tablet overview banner metrics and connectivity badge status."""
    society_id, primary_assignment = _get_guard_society_and_assignment(claims, db)
    gate_obj = get_gate_by_id(db, primary_assignment.gate_id)

    # Calculate active checked in count
    active_count_stmt = select(VisitorRecord).where(
        VisitorRecord.society_id == society_id,
        VisitorRecord.entry_status == EntryStatus.CHECKED_IN,
    )
    active_count = len(list(db.scalars(active_count_stmt).all()))

    # Calculate pending count
    pending_count_stmt = select(VisitorRecord).where(
        VisitorRecord.society_id == society_id,
        VisitorRecord.approval_status == ApprovalStatus.PENDING,
    )
    pending_count = len(list(db.scalars(pending_count_stmt).all()))

    return {
        "user_id": str(claims.user_id),
        "full_name": claims.full_name,
        "society_id": str(society_id),
        "gate_id": str(gate_obj.id) if gate_obj else None,
        "gate_name": gate_obj.display_name if gate_obj else "Main Gate",
        "assigned_gate": {
            "gate_id": str(gate_obj.id) if gate_obj else None,
            "gate_number": gate_obj.gate_number if gate_obj else 1,
            "gate_name": gate_obj.display_name if gate_obj else "Main Gate",
        },
        "active_checked_in_count": active_count,
        "pending_approvals_count": pending_count,
        "offline_queue_supported": True,
    }


@router.get("/flats")
def list_gate_flats(
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=50),
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Lists destination flats within the gate operator's society for tablet selection."""
    society_id, _ = _get_guard_society_and_assignment(claims, db)
    stmt = select(Flat).where(Flat.society_id == society_id)
    if search and search.strip():
        q = f"%{search.strip()}%"
        stmt = stmt.where(Flat.flat_number.ilike(q))
    stmt = stmt.order_by(Flat.flat_number.asc()).limit(limit)
    flats = list(db.scalars(stmt).all())
    return [
        {
            "flat_id": str(f.id),
            "flat_number": f.flat_number,
            "tower_number": f.tower.tower_number if f.tower else "Tower",
            "tower_name": f.tower.name if f.tower else "Tower",
        }
        for f in flats
    ]


# =============================================================================
# 2. Visitor Registration & Lifecycle Endpoints
# =============================================================================


@router.post("/visitors/register", status_code=status.HTTP_201_CREATED)
async def register_visitor(
    request: Request,
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Walk-in visitor registration. Accepts multipart/form-data or application/json."""
    content_type_header = request.headers.get("content-type", "")

    raw_data: dict[str, Any] = {}
    photo_bytes: bytes | None = None

    if "multipart/form-data" in content_type_header:
        form = await request.form()
        for k, v in form.items():
            if k == "photo" and hasattr(v, "read"):
                photo_bytes = await v.read()
            else:
                raw_data[k] = v
    else:
        try:
            raw_data = await request.json()
        except Exception:
            raise ValidationError(
                code="INVALID_PAYLOAD", message="Malformed or missing request body."
            )

        photo_base64 = raw_data.get("photo_base64")
        if photo_base64:
            clean_b64 = photo_base64.split(",", 1)[1] if "," in photo_base64 else photo_base64
            try:
                photo_bytes = base64.b64decode(clean_b64)
            except Exception:
                raise ValidationError(
                    code="INVALID_PHOTO_BASE64",
                    message="Invalid base64 encoding for photo.",
                )

    # Validate inputs using Pydantic schema
    try:
        validated_data = VisitorRegisterRequest(**raw_data)
    except PydanticValidationError as e:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message=str(e),
        )

    # Gate validation
    requested_gate_id = validated_data.gate_id
    society_id, assignment = _get_guard_society_and_assignment(
        claims, db, requested_gate_id=requested_gate_id
    )
    actual_gate_id = assignment.gate_id

    # Validate destination flat exists and belongs to this society
    target_flat = db.get(Flat, validated_data.destination_flat_id)
    if not target_flat:
        target_flat = db.scalars(
            select(Flat).where(
                or_(
                    cast(Flat.id, String) == str(validated_data.destination_flat_id),
                    cast(Flat.id, String) == validated_data.destination_flat_id.hex,
                )
            )
        ).first()

    if not target_flat:
        raise ResourceNotFoundError(
            code="FLAT_NOT_FOUND",
            message=f"Destination flat {validated_data.destination_flat_id} not found",
        )
    if (
        str(target_flat.society_id) != str(society_id)
        and target_flat.society_id.hex != society_id.hex
    ):
        raise ValidationError(
            code="CROSS_SOCIETY_FLAT_FORBIDDEN",
            message=f"Destination flat {validated_data.destination_flat_id} belongs to a different society.",
        )

    # Handle Photo upload if present
    retention_service = PhotoRetentionService(db)
    photo_key: str | None = None
    visitor_id = uuid.uuid4()

    if photo_bytes:
        photo_key = retention_service.save_photo_bytes(
            society_id=society_id,
            visitor_id=visitor_id,
            photo_bytes=photo_bytes,
        )

    # Register visitor in domain service
    visitor_service = VisitorService(db)
    visitor = visitor_service.register_visitor(
        society_id=society_id,
        gate_id=actual_gate_id,
        guard_user_id=claims.user_id,
        visitor_name=validated_data.visitor_name,
        phone_number=validated_data.phone_number,
        purpose=validated_data.purpose,
        destination_flat_id=validated_data.destination_flat_id,
        vehicle_number=validated_data.vehicle_number,
        privacy_notice_version=validated_data.privacy_notice_version,
        client_event_id=validated_data.client_event_id,
        photo_s3_key=photo_key,
    )
    db.commit()

    # Destination flat details
    flat = db.get(Flat, visitor.destination_flat_id)
    dest_flat_dict = {
        "flat_id": str(flat.id) if flat else str(visitor.destination_flat_id),
        "flat_number": flat.flat_number if flat else "",
        "tower_name": flat.tower.name if flat and flat.tower else "",
    }

    photo_url: str | None = None
    if photo_key:
        photo_url = retention_service.storage_provider.generate_download_url(
            storage_key=photo_key,
            expires_in_seconds=900,
        )

    return {
        "visitor_id": str(visitor.id),
        "society_id": str(visitor.society_id),
        "gate_id": str(visitor.gate_id),
        "visitor_name": visitor.visitor_name,
        "phone_masked": visitor.masked_phone,
        "vehicle_number": visitor.vehicle_number,
        "purpose": visitor.purpose.value,
        "destination_flat_id": str(visitor.destination_flat_id),
        "destination_flat": dest_flat_dict,
        "approval_status": visitor.approval_status.value,
        "entry_status": visitor.entry_status.value,
        "photo_url": photo_url,
        "photo_storage_key": visitor.photo_key,
        "created_at": visitor.created_at.isoformat(),
    }


@router.post("/visitors/{visitor_id}/check-in")
def check_in_visitor(
    visitor_id: uuid.UUID,
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Physical check-in at gate. Requires visitor to be APPROVED or AUTO_APPROVED and EXPECTED."""
    society_id, assignment = _get_guard_society_and_assignment(claims, db)
    visitor_service = VisitorService(db)
    visitor = visitor_service.check_in_visitor(
        visitor_id=visitor_id,
        gate_id=assignment.gate_id,
        guard_user_id=claims.user_id,
    )
    db.commit()

    return {
        "visitor_id": str(visitor.id),
        "entry_status": visitor.entry_status.value,
        "entry_time": visitor.entry_time.isoformat() if visitor.entry_time else None,
        "entry_gate_id": str(visitor.entry_gate_id) if visitor.entry_gate_id else None,
    }


@router.post("/visitors/{visitor_id}/check-out")
async def check_out_visitor(
    visitor_id: uuid.UUID,
    request: Request,
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Physical check-out at exit gate. Requires visitor to be CHECKED_IN."""
    body: dict[str, Any] = {}
    with contextlib.suppress(Exception):
        body = await request.json()

    exit_gate_id_raw = body.get("exit_gate_id")
    requested_exit_gate: uuid.UUID | None = None
    if exit_gate_id_raw:
        try:
            requested_exit_gate = uuid.UUID(str(exit_gate_id_raw))
        except Exception:
            raise ValidationError(
                code="INVALID_GATE_ID", message="exit_gate_id must be a valid UUID."
            )

    society_id, assignment = _get_guard_society_and_assignment(claims, db, requested_gate_id=None)
    exit_gate_id = assignment.gate_id
    if requested_exit_gate:
        try:
            _, specific_assignment = _get_guard_society_and_assignment(
                claims, db, requested_gate_id=requested_exit_gate
            )
            exit_gate_id = specific_assignment.gate_id
        except AuthorizationError:
            pass

    visitor_service = VisitorService(db)
    visitor = visitor_service.check_out_visitor(
        visitor_id=visitor_id,
        gate_id=exit_gate_id,
        guard_user_id=claims.user_id,
    )
    db.commit()

    return {
        "visitor_id": str(visitor.id),
        "entry_status": visitor.entry_status.value,
        "exit_time": visitor.exit_time.isoformat() if visitor.exit_time else None,
        "exit_gate_id": str(visitor.exit_gate_id) if visitor.exit_gate_id else None,
    }


# =============================================================================
# 3. Campus Visitors Directory & History Endpoints
# =============================================================================


def _query_visitors(
    claims: CurrentUserClaims,
    db: Session,
    status: str | None = None,
    gate_id: uuid.UUID | None = None,
    search: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Paginated, searchable campus visitor registry scoped to operator's society."""
    if limit <= 0:
        raise ValidationError(code="INVALID_LIMIT", message="limit must be >= 1.")
    if limit > 50:
        limit = 50
    if offset < 0:
        raise ValidationError(code="INVALID_OFFSET", message="offset must be >= 0.")

    society_id, _ = _get_guard_society_and_assignment(claims, db)

    stmt = select(VisitorRecord).where(VisitorRecord.society_id == society_id)

    if status and isinstance(status, str):
        status_clean = status.upper().strip()
        if status_clean in EntryStatus._member_names_:
            stmt = stmt.where(VisitorRecord.entry_status == EntryStatus(status_clean))
        elif status_clean in ApprovalStatus._member_names_:
            stmt = stmt.where(VisitorRecord.approval_status == ApprovalStatus(status_clean))

    if gate_id and isinstance(gate_id, uuid.UUID):
        stmt = stmt.where(VisitorRecord.gate_id == gate_id)

    if search and isinstance(search, str):
        search_pattern = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                VisitorRecord.visitor_name.ilike(search_pattern),
                VisitorRecord.phone_number.ilike(search_pattern),
                VisitorRecord.vehicle_number.ilike(search_pattern),
            )
        )

    stmt = stmt.order_by(VisitorRecord.created_at.desc()).offset(offset).limit(limit)
    records = list(db.scalars(stmt).all())

    results = []
    for r in records:
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
                "approval_status": r.approval_status.value,
                "entry_status": r.entry_status.value,
                "photo_url": None,
                "created_at": r.created_at.isoformat(),
                "entry_time": r.entry_time.isoformat() if r.entry_time else None,
                "exit_time": r.exit_time.isoformat() if r.exit_time else None,
            }
        )
    return results


@router.get("/visitors")
def list_visitors(
    status: str | None = Query(default=None),
    gate_id: uuid.UUID | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=20),
    offset: int = Query(default=0),
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Paginated, searchable campus visitor registry scoped to operator's society."""
    return _query_visitors(
        claims=claims,
        db=db,
        status=status,
        gate_id=gate_id,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/visitors/active")
def get_active_visitors(
    limit: int = Query(default=50),
    offset: int = Query(default=0),
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Returns currently checked-in visitors on campus."""
    return _query_visitors(
        claims=claims,
        db=db,
        status="CHECKED_IN",
        limit=limit,
        offset=offset,
    )


@router.get("/visitors/history")
def get_visitor_history(
    limit: int = Query(default=20),
    offset: int = Query(default=0),
    search: str | None = Query(default=None),
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Returns historical visitor logs for the gate."""
    return _query_visitors(
        claims=claims,
        db=db,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/visitors/{visitor_id}")
def get_visitor_detail(
    visitor_id: uuid.UUID,
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Fetches details of a specific visitor record for tablet polling."""
    society_id, _ = _get_guard_society_and_assignment(claims, db)
    id_cond = or_(
        cast(VisitorRecord.id, String) == str(visitor_id),
        cast(VisitorRecord.id, String) == visitor_id.hex,
    )
    society_cond = or_(
        cast(VisitorRecord.society_id, String) == str(society_id),
        cast(VisitorRecord.society_id, String) == society_id.hex,
    )
    stmt = select(VisitorRecord).where(id_cond, society_cond)
    visitor = db.scalars(stmt).first()
    if not visitor:
        raise ResourceNotFoundError(
            code="VISITOR_NOT_FOUND", message=f"Visitor {visitor_id} not found."
        )

    flat = db.get(Flat, visitor.destination_flat_id)
    return {
        "visitor_id": str(visitor.id),
        "society_id": str(visitor.society_id),
        "gate_id": str(visitor.gate_id),
        "visitor_name": visitor.visitor_name,
        "phone_masked": visitor.masked_phone,
        "vehicle_number": visitor.vehicle_number,
        "purpose": visitor.purpose.value,
        "destination_flat_id": str(visitor.destination_flat_id),
        "destination_flat": {
            "flat_id": str(flat.id) if flat else str(visitor.destination_flat_id),
            "flat_number": flat.flat_number if flat else "",
            "tower_name": flat.tower.name if flat and flat.tower else "",
        }
        if flat
        else None,
        "approval_status": visitor.approval_status.value,
        "entry_status": visitor.entry_status.value,
        "privacy_notice_version": visitor.privacy_notice_version,
        "created_at": visitor.created_at.isoformat(),
        "entry_time": visitor.entry_time.isoformat() if visitor.entry_time else None,
        "exit_time": visitor.exit_time.isoformat() if visitor.exit_time else None,
    }


@router.get("/visitors/{visitor_id}/photo")
def get_visitor_photo_presigned_url(
    visitor_id: uuid.UUID,
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Generates a presigned URL (15-min expiration) with 90-day logical cutoff enforcement."""
    society_id, _ = _get_guard_society_and_assignment(claims, db)
    retention_service = PhotoRetentionService(db)
    return retention_service.get_visitor_photo_presigned_url(
        visitor_id=visitor_id,
        requester_user_id=claims.user_id,
        society_id=society_id,
        is_guard=True,
    )


# =============================================================================
# 4. Guest Pass Verification Endpoint
# =============================================================================


@router.post("/pass/verify", response_model=GuestPassVerifyResponse)
def verify_guest_pass(
    body: GuestPassVerifyRequest,
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> GuestPassVerifyResponse:
    """Verifies resident pre-approved guest pass code at gate with row-level concurrency lock."""
    society_id, _ = _get_guard_society_and_assignment(claims, db, requested_gate_id=None)
    pass_service = GuestPassService(db)
    result = pass_service.verify_and_redeem_pass(
        pass_code=body.pass_code,
        gate_id=body.gate_id,
        guard_user_id=claims.user_id,
        society_id=society_id,
    )
    return GuestPassVerifyResponse(**result)


# =============================================================================
# 5. Offline Batch Sync Endpoint
# =============================================================================


@router.post("/sync", response_model=OfflineSyncBatchResponse)
def sync_offline_batch(
    body: OfflineSyncBatchRequest,
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> OfflineSyncBatchResponse:
    """Reconnection batch sync for offline tablet events with replay conflict detection."""
    society_id, _ = _get_guard_society_and_assignment(claims, db, requested_gate_id=body.gate_id)
    sync_service = OfflineSyncService(db)
    raw_events = [e.model_dump() for e in body.events]
    result = sync_service.process_sync_batch(
        gate_id=body.gate_id,
        guard_user_id=claims.user_id,
        society_id=society_id,
        events=raw_events,
    )
    return OfflineSyncBatchResponse(**result)


# =============================================================================
# 6. Tri-Lingual Statutory Privacy Notice Endpoint
# =============================================================================


@router.get("/privacy-notice", response_model=PrivacyNoticeResponse)
def get_privacy_notice(
    lang: str = Query(default="en"),
    claims: CurrentUserClaims = Depends(get_current_user),
) -> PrivacyNoticeResponse:
    """Provides the tri-lingual statutory privacy notice in English, Hindi, and Marathi."""
    notices = {
        "en": {
            "title": "Township Gate Visitor Privacy Notice",
            "content": (
                "Under Pune municipal guidelines, visitor photography, name, and contact information "
                "are captured solely for perimeter security and resident verification. "
                "Photographs are retained in private storage for exactly 90 days and deleted automatically thereafter. "
                "For inquiries or grievance redressal, contact helpdesk@marvelgreenfield.com."
            ),
        },
        "hi": {
            "title": "गेट आगंतुक गोपनीयता सूचना",
            "content": (
                "पुणे नगर निगम दिशानिर्देशों के अनुसार, परिसर की सुरक्षा और निवासी सत्यापन के लिए "
                "आगंतुक का फोटो, नाम और संपर्क विवरण एकत्र किया जाता है। "
                "फोटो 90 दिनों के लिए सुरक्षित रूप से संग्रहीत की जाती है और उसके बाद स्वचालित रूप से हटा दी जाती है। "
                "शिकायत निवारण के लिए helpdesk@marvelgreenfield.com पर संपर्क करें।"
            ),
        },
        "mr": {
            "title": "गेट अभ्यागत गोपनीयता सूचना",
            "content": (
                "पुणे महानगरपालिका मार्गदर्शक तत्त्वांनुसार, सुरक्षा आणि रहिवासी पडताळणीसाठी "
                "अभ्यागताचे छायाचित्र, नाव आणि संपर्क माहिती गोळा केली जाते. "
                "छायाचित्रे ९० दिवस खाजगी साठवणुकीत ठेवली जातात आणि त्यानंतर स्वयंचलितपणे नष्ट केली जातात. "
                "तक्रार निवारणासाठी helpdesk@marvelgreenfield.com वर संपर्क साधा."
            ),
        },
    }
    selected = notices.get(lang.lower(), notices["en"])
    return PrivacyNoticeResponse(
        version="v1.0-2026-pune",
        language=lang.lower(),
        title=selected["title"],
        content=selected["content"],
        retention_days=90,
        grievance_contact="helpdesk@marvelgreenfield.com",
    )
