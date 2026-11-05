"""Registry Domain API Endpoints

Provides REST endpoints for:
1. Staff resident directory search & inspection
2. Staff membership creation (Owner, Tenant with lease dates, Family Member)
3. Membership approval, rejection, and termination
4. Resident-initiated flat join requests
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AuthorizationError
from app.core.security import require_roles
from app.domains.identity.models import MembershipStatus, MembershipType, RoleType
from app.domains.identity.schemas import (
    CreateMembershipRequest,
    CurrentUserClaims,
    FlatMembershipSchema,
    ResidentDirectoryItem,
    ResidentJoinFlatRequest,
    UpdateMembershipStatusRequest,
)
from app.domains.identity.service import IdentityService

router = APIRouter(prefix="/registry", tags=["Resident & Unit Registry"])


def _resolve_society_id(claims: CurrentUserClaims, query_society_id: UUID | None) -> UUID:
    if not claims.society_ids:
        raise AuthorizationError("User is not assigned to any society")
    if query_society_id:
        if query_society_id not in claims.society_ids:
            raise AuthorizationError(f"Access denied to society {query_society_id}")
        return query_society_id
    return claims.society_ids[0]


@router.get(
    "/residents",
    response_model=list[ResidentDirectoryItem],
    summary="Search and inspect residents across towers and flats",
)
def list_residents(
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.HELPDESK))],
    society_id: UUID | None = Query(None),
    query: str | None = Query(None, description="Search by name, phone, or email"),
    tower_id: UUID | None = Query(None),
    flat_number: str | None = Query(None),
    status: MembershipStatus | None = Query(None),
    membership_type: MembershipType | None = Query(None),
    db: Session = Depends(get_db),
) -> list[ResidentDirectoryItem]:
    target_soc = _resolve_society_id(claims, society_id)
    service = IdentityService(db)
    return service.search_residents(
        claims=claims,
        society_id=target_soc,
        query=query,
        tower_id=tower_id,
        flat_number=flat_number,
        status=status,
        membership_type=membership_type,
    )


@router.get(
    "/memberships",
    response_model=list[FlatMembershipSchema],
    summary="List flat memberships with status filtering",
)
def list_memberships(
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.HELPDESK))],
    society_id: UUID | None = Query(None),
    status: MembershipStatus | None = Query(None),
    flat_id: UUID | None = Query(None),
    db: Session = Depends(get_db),
) -> list[FlatMembershipSchema]:
    target_soc = _resolve_society_id(claims, society_id)
    service = IdentityService(db)
    return service.list_memberships(
        claims=claims,
        society_id=target_soc,
        status=status,
        flat_id=flat_id,
    )


@router.post(
    "/memberships",
    response_model=FlatMembershipSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new flat membership (Owner, Tenant with lease, or Family Member)",
)
def create_membership(
    payload: CreateMembershipRequest,
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.HELPDESK))],
    society_id: UUID | None = Query(None),
    db: Session = Depends(get_db),
) -> FlatMembershipSchema:
    target_soc = _resolve_society_id(claims, society_id)
    service = IdentityService(db)
    return service.create_membership(claims=claims, society_id=target_soc, req=payload)


@router.patch(
    "/memberships/{membership_id}/status",
    response_model=FlatMembershipSchema,
    summary="Update membership status (Approve, Reject, Terminate)",
)
def update_membership_status(
    membership_id: UUID,
    payload: UpdateMembershipStatusRequest,
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.HELPDESK))],
    db: Session = Depends(get_db),
) -> FlatMembershipSchema:
    service = IdentityService(db)
    return service.update_membership_status(claims=claims, membership_id=membership_id, req=payload)


@router.post(
    "/join-flat-request",
    response_model=FlatMembershipSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Resident requests to link to an apartment",
)
def request_join_flat(
    payload: ResidentJoinFlatRequest,
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.RESIDENT))],
    db: Session = Depends(get_db),
) -> FlatMembershipSchema:
    service = IdentityService(db)
    return service.request_join_flat(claims=claims, req=payload)
