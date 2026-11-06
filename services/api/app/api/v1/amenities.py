"""API Version 1 Amenities & Clubhouse Booking Endpoints

Provides REST endpoints for:
- Resident:
  - List available amenities
  - View amenity details and operating rules
  - View available slots for any date within advance booking window
  - Reserve / book amenity slots (concurrency-safe with row locking)
  - View own bookings (upcoming, past, filtered by status)
  - Cancel eligible bookings with automated refund calculation
- Staff:
  - Create, update, activate/deactivate amenities
  - View all community bookings with filters
  - Administrative cancellation with mandatory audit reason
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AuthorizationError
from app.core.security import require_roles
from app.domains.amenities.models import AmenityType, BookingPaymentStatus, BookingStatus
from app.domains.amenities.schemas import (
    AmenityBlockResponse,
    AmenityCreateRequest,
    AmenityListResponse,
    AmenityResponse,
    AmenitySlotsResponse,
    AmenityStatusRequest,
    AmenityUpdateRequest,
    BookingResponse,
    CancelBookingRequest,
    CreateAmenityBlockRequest,
    CreateBookingRequest,
    PaginatedBookingsResponse,
    PayBookingRequest,
    StaffCancelBookingRequest,
)
from app.domains.amenities.service import AmenityService
from app.domains.identity.models import RoleType
from app.domains.identity.schemas import CurrentUserClaims

router = APIRouter(prefix="/amenities", tags=["Amenities & Clubhouse Bookings"])


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
# Staff Amenity Management Endpoints (Requires RoleType.HELPDESK)
# =============================================================================


@router.post(
    "/staff",
    response_model=AmenityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new amenity (Staff only)",
)
def create_amenity(
    req: AmenityCreateRequest,
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.HELPDESK))],
    society_id: UUID | None = Query(None, description="Society ID"),
    db: Session = Depends(get_db),
) -> AmenityResponse:
    soc_id = _resolve_society_id(claims, society_id)
    svc = AmenityService(db)
    amenity = svc.create_amenity_by_staff(
        society_id=soc_id,
        staff_user_id=claims.user_id,
        req=req,
    )
    db.commit()
    return AmenityResponse.model_validate(amenity)


@router.patch(
    "/staff/{amenity_id}",
    response_model=AmenityResponse,
    summary="Update amenity configuration (Staff only)",
)
def update_amenity(
    amenity_id: UUID,
    req: AmenityUpdateRequest,
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.HELPDESK))],
    society_id: UUID | None = Query(None, description="Society ID"),
    db: Session = Depends(get_db),
) -> AmenityResponse:
    soc_id = _resolve_society_id(claims, society_id)
    svc = AmenityService(db)
    amenity = svc.update_amenity_by_staff(
        society_id=soc_id,
        staff_user_id=claims.user_id,
        amenity_id=amenity_id,
        req=req,
    )
    db.commit()
    return AmenityResponse.model_validate(amenity)


@router.post(
    "/staff/{amenity_id}/status",
    response_model=AmenityResponse,
    summary="Activate or deactivate amenity (Staff only)",
)
def set_amenity_status(
    amenity_id: UUID,
    req: AmenityStatusRequest,
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.HELPDESK))],
    society_id: UUID | None = Query(None, description="Society ID"),
    db: Session = Depends(get_db),
) -> AmenityResponse:
    soc_id = _resolve_society_id(claims, society_id)
    svc = AmenityService(db)
    amenity = svc.set_amenity_status_by_staff(
        society_id=soc_id,
        staff_user_id=claims.user_id,
        amenity_id=amenity_id,
        is_active=req.is_active,
    )
    db.commit()
    return AmenityResponse.model_validate(amenity)


@router.post(
    "/staff/{amenity_id}/blocks",
    response_model=AmenityBlockResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Temporarily block dates or slots for an amenity (Staff only)",
)
def create_amenity_block(
    amenity_id: UUID,
    req: CreateAmenityBlockRequest,
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.HELPDESK))],
    society_id: UUID | None = Query(None, description="Society ID"),
    db: Session = Depends(get_db),
) -> AmenityBlockResponse:
    soc_id = _resolve_society_id(claims, society_id)
    svc = AmenityService(db)
    block = svc.create_amenity_block(
        society_id=soc_id,
        staff_user_id=claims.user_id,
        amenity_id=amenity_id,
        req=req,
    )
    db.commit()
    return AmenityBlockResponse.model_validate(block)


@router.get(
    "/staff/{amenity_id}/blocks",
    response_model=list[AmenityBlockResponse],
    summary="List active temporary blocks for an amenity (Staff only)",
)
def list_amenity_blocks(
    amenity_id: UUID,
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.HELPDESK))],
    block_date: date | None = Query(None, description="Filter by date"),
    society_id: UUID | None = Query(None, description="Society ID"),
    db: Session = Depends(get_db),
) -> list[AmenityBlockResponse]:
    soc_id = _resolve_society_id(claims, society_id)
    svc = AmenityService(db)
    blocks = svc.list_amenity_blocks(
        society_id=soc_id,
        amenity_id=amenity_id,
        block_date=block_date,
    )
    return [AmenityBlockResponse.model_validate(b) for b in blocks]


@router.delete(
    "/staff/blocks/{block_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a temporary amenity block (Staff only)",
)
def delete_amenity_block(
    block_id: UUID,
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.HELPDESK))],
    society_id: UUID | None = Query(None, description="Society ID"),
    db: Session = Depends(get_db),
) -> None:
    soc_id = _resolve_society_id(claims, society_id)
    svc = AmenityService(db)
    svc.delete_amenity_block(
        society_id=soc_id,
        staff_user_id=claims.user_id,
        block_id=block_id,
    )
    db.commit()


@router.get(
    "/staff/bookings",
    response_model=PaginatedBookingsResponse,
    summary="List all community bookings across amenities (Staff only)",
)
def list_staff_bookings(
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.HELPDESK))],
    amenity_id: UUID | None = Query(None, description="Filter by amenity ID"),
    booking_date: date | None = Query(None, description="Filter by booking date"),
    booking_status: BookingStatus | None = Query(
        None, alias="status", description="Filter by status"
    ),
    flat_id: UUID | None = Query(None, description="Filter by flat ID"),
    payment_status: BookingPaymentStatus | None = Query(
        None, description="Filter by payment status"
    ),
    search: str | None = Query(None, description="Search resident name, flat number, or reference"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    society_id: UUID | None = Query(None, description="Society ID"),
    db: Session = Depends(get_db),
) -> PaginatedBookingsResponse:
    soc_id = _resolve_society_id(claims, society_id)
    svc = AmenityService(db)
    return svc.list_staff_bookings(
        society_id=soc_id,
        page=page,
        page_size=page_size,
        amenity_id=amenity_id,
        booking_date=booking_date,
        status=booking_status,
        flat_id=flat_id,
        payment_status=payment_status,
        search=search,
    )


@router.post(
    "/staff/bookings/{booking_id}/cancel",
    response_model=BookingResponse,
    summary="Cancel booking with staff override and 100% refund (Staff only)",
)
def staff_cancel_booking(
    booking_id: UUID,
    req: StaffCancelBookingRequest,
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.HELPDESK))],
    society_id: UUID | None = Query(None, description="Society ID"),
    db: Session = Depends(get_db),
) -> BookingResponse:
    soc_id = _resolve_society_id(claims, society_id)
    svc = AmenityService(db)
    booking = svc.cancel_booking_by_staff(
        society_id=soc_id,
        staff_user_id=claims.user_id,
        booking_id=booking_id,
        reason=req.reason,
    )
    db.commit()
    return svc._to_booking_response(booking)


# =============================================================================
# Resident Booking Endpoints (Me & Single Booking)
# =============================================================================


@router.get(
    "/bookings/me",
    response_model=PaginatedBookingsResponse,
    summary="Get paginated bookings for current resident",
)
def get_my_bookings(
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.RESIDENT))],
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    booking_status: BookingStatus | None = Query(
        None, alias="status", description="Filter by status"
    ),
    upcoming_only: bool = Query(False, description="Filter for upcoming confirmed bookings"),
    society_id: UUID | None = Query(None, description="Society ID"),
    db: Session = Depends(get_db),
) -> PaginatedBookingsResponse:
    soc_id = _resolve_society_id(claims, society_id)
    svc = AmenityService(db)
    return svc.get_user_bookings(
        society_id=soc_id,
        user_id=claims.user_id,
        page=page,
        page_size=page_size,
        status=booking_status,
        upcoming_only=upcoming_only,
    )


@router.get(
    "/bookings/{booking_id}",
    response_model=BookingResponse,
    summary="Get resident booking details",
)
def get_booking_details(
    booking_id: UUID,
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.RESIDENT))],
    society_id: UUID | None = Query(None, description="Society ID"),
    db: Session = Depends(get_db),
) -> BookingResponse:
    soc_id = _resolve_society_id(claims, society_id)
    svc = AmenityService(db)
    booking = svc.get_booking_by_id(
        society_id=soc_id,
        booking_id=booking_id,
        user_id=claims.user_id,
    )
    return svc._to_booking_response(booking)


@router.post(
    "/bookings/{booking_id}/cancel",
    response_model=BookingResponse,
    summary="Cancel eligible booking by resident",
)
def cancel_my_booking(
    booking_id: UUID,
    req: CancelBookingRequest,
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.RESIDENT))],
    society_id: UUID | None = Query(None, description="Society ID"),
    db: Session = Depends(get_db),
) -> BookingResponse:
    soc_id = _resolve_society_id(claims, society_id)
    svc = AmenityService(db)
    booking = svc.cancel_booking_by_resident(
        society_id=soc_id,
        user_id=claims.user_id,
        booking_id=booking_id,
        reason=req.reason,
    )
    db.commit()
    return svc._to_booking_response(booking)


@router.post(
    "/bookings/{booking_id}/pay",
    response_model=BookingResponse,
    summary="Process simulated payment for an amenity booking (Resident only)",
)
def pay_booking(
    booking_id: UUID,
    req: PayBookingRequest,
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.RESIDENT))],
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    society_id: UUID | None = Query(None, description="Society ID"),
    db: Session = Depends(get_db),
) -> BookingResponse:
    soc_id = _resolve_society_id(claims, society_id)
    svc = AmenityService(db)
    key = idempotency_key or req.idempotency_key
    resp = svc.pay_booking(
        society_id=soc_id,
        user_id=claims.user_id,
        booking_id=booking_id,
        idempotency_key=key,
        simulate_failure=req.simulate_failure,
    )
    db.commit()
    return resp


# =============================================================================
# Resident Amenity Discovery & Slot Booking Endpoints
# =============================================================================


@router.get(
    "",
    response_model=AmenityListResponse,
    summary="List all available amenities in township",
)
def list_amenities(
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.RESIDENT))],
    amenity_type: AmenityType | None = Query(None, description="Filter by amenity type"),
    society_id: UUID | None = Query(None, description="Society ID"),
    db: Session = Depends(get_db),
) -> AmenityListResponse:
    soc_id = _resolve_society_id(claims, society_id)
    svc = AmenityService(db)
    items = svc.list_amenities(
        society_id=soc_id,
        amenity_type=amenity_type,
        active_only=True,
    )
    return AmenityListResponse(
        items=[AmenityResponse.model_validate(a) for a in items],
        total=len(items),
    )


@router.get(
    "/{amenity_id}",
    response_model=AmenityResponse,
    summary="Get amenity details, guidelines, and operating hours",
)
def get_amenity_details(
    amenity_id: UUID,
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.RESIDENT))],
    society_id: UUID | None = Query(None, description="Society ID"),
    db: Session = Depends(get_db),
) -> AmenityResponse:
    soc_id = _resolve_society_id(claims, society_id)
    svc = AmenityService(db)
    amenity = svc.get_amenity(society_id=soc_id, amenity_id=amenity_id)
    return AmenityResponse.model_validate(amenity)


@router.get(
    "/{amenity_id}/slots",
    response_model=AmenitySlotsResponse,
    summary="View slot availability and remaining capacity for a date",
)
def get_amenity_slots(
    amenity_id: UUID,
    booking_date: date = Query(..., description="Date to view slots for (YYYY-MM-DD)"),
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.RESIDENT))] = None,  # type: ignore[assignment]
    society_id: UUID | None = Query(None, description="Society ID"),
    db: Session = Depends(get_db),
) -> AmenitySlotsResponse:
    soc_id = _resolve_society_id(claims, society_id)
    svc = AmenityService(db)
    return svc.get_available_slots(
        society_id=soc_id,
        amenity_id=amenity_id,
        booking_date=booking_date,
        user_id=claims.user_id,
    )


@router.post(
    "/{amenity_id}/bookings",
    response_model=BookingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Book an amenity slot",
)
def create_booking(
    amenity_id: UUID,
    req: CreateBookingRequest,
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.RESIDENT))],
    society_id: UUID | None = Query(None, description="Society ID"),
    db: Session = Depends(get_db),
) -> BookingResponse:
    soc_id = _resolve_society_id(claims, society_id)
    svc = AmenityService(db)
    booking = svc.create_booking(
        society_id=soc_id,
        user_id=claims.user_id,
        amenity_id=amenity_id,
        req=req,
    )
    db.commit()
    return svc._to_booking_response(booking)
