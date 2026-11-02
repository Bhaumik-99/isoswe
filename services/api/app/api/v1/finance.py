"""Finance Restricted Endpoints

Demonstrates role-based authorization for financial operations.
Strictly restricted to users with FINANCE or PLATFORM_ADMIN roles.
"""

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_roles
from app.domains.identity.models import RoleType
from app.domains.identity.schemas import CurrentUserClaims

router = APIRouter(prefix="/finance", tags=["Finance"])


class FinanceOperationResponse(BaseModel):
    message: str
    status: str


@router.post(
    "/batch-billing/preview",
    response_model=FinanceOperationResponse,
    status_code=status.HTTP_200_OK,
)
def trigger_batch_billing_preview(
    claims: CurrentUserClaims = Depends(require_roles(RoleType.FINANCE)),
    db: Session = Depends(get_db),
) -> FinanceOperationResponse:
    """Restricted operation only executable by users with the FINANCE or PLATFORM_ADMIN role."""
    return FinanceOperationResponse(
        message=f"Finance batch billing operation authorized for {claims.email}",
        status="AUTHORIZED",
    )
