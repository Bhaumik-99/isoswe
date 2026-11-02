"""Flat Resources Endpoint

GET /api/v1/flats/{flat_id}
Demonstrates resident-level flat authorization and multi-tenant isolation.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.domains.identity.schemas import CurrentUserClaims, FlatDetailSchema
from app.domains.identity.service import IdentityService

router = APIRouter(prefix="/flats", tags=["Flats"])


@router.get("/{flat_id}", response_model=FlatDetailSchema)
def get_flat_details(
    flat_id: UUID,
    claims: CurrentUserClaims = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FlatDetailSchema:
    """Retrieves flat details after asserting that the caller is authorized for this flat.

    Residents can only access flats they hold approved, non-expired memberships for.
    Staff can only access flats within their assigned society.
    """
    service = IdentityService(db)
    return service.get_flat_for_resident(flat_id, claims)
