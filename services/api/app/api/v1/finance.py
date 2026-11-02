"""Finance & Reconciliation Restricted Endpoints

Demonstrates granular permission-based authorization.
Restricted to users holding BANK_IMPORT and RECONCILIATION_REVIEW permissions (HELPDESK role).
"""

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permissions
from app.domains.identity.models import Permission
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
    claims: CurrentUserClaims = Depends(
        require_permissions(Permission.BANK_IMPORT, Permission.RECONCILIATION_REVIEW)
    ),
    db: Session = Depends(get_db),
) -> FinanceOperationResponse:
    """Restricted operation executable by authorized helpdesk staff holding BANK_IMPORT & RECONCILIATION_REVIEW permissions."""
    return FinanceOperationResponse(
        message=f"Finance batch billing operation authorized for {claims.email}",
        status="AUTHORIZED",
    )
