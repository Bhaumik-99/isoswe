"""User Profile Endpoint

GET /api/v1/me
Returns current authenticated user profile, roles, and approved flat memberships.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.domains.identity.schemas import CurrentUserClaims, MeResponse
from app.domains.identity.service import IdentityService

router = APIRouter(prefix="/me", tags=["Identity"])


@router.get("", response_model=MeResponse)
def get_current_user_profile(
    claims: CurrentUserClaims = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MeResponse:
    """Returns profile, assigned roles, and active flat memberships for the authenticated user."""
    service = IdentityService(db)
    return service.get_me_profile(claims.user_id)
