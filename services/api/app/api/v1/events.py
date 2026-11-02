"""Outbox Event Triggering and Health Check Event Endpoint

POST /api/v1/health-check-event
Demonstrates atomic transaction commit containing both a business change and an outbox event.
"""

from uuid import uuid4

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.domains.identity.schemas import CurrentUserClaims
from app.domains.reliability.models import AuditEvent, OutboxEvent, OutboxStatus

router = APIRouter(prefix="/events", tags=["Events"])


class TriggerHealthEventResponse(BaseModel):
    message: str
    outbox_event_id: str
    status: str


@router.post(
    "/health-check-event",
    response_model=TriggerHealthEventResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def trigger_health_check_event(
    claims: CurrentUserClaims = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TriggerHealthEventResponse:
    """Creates an atomic transaction writing an audit event and an outbox event."""
    event_id = uuid4()
    correlation_id = str(uuid4())

    # 1. Write audit event
    audit = AuditEvent(
        society_id=claims.society_ids[0] if claims.society_ids else None,
        actor_id=claims.user_id,
        action="platform.health_check.requested",
        resource_type="Platform",
        resource_id=str(event_id),
        correlation_id=correlation_id,
        event_metadata={"initiated_by": claims.email},
    )
    db.add(audit)

    # 2. Insert outbox event in the SAME transaction
    outbox = OutboxEvent(
        id=event_id,
        event_type="platform.health_check",
        aggregate_type="Platform",
        aggregate_id="system-health",
        payload={
            "requested_by_user_id": str(claims.user_id),
            "correlation_id": correlation_id,
            "test_marker": "synthetic_health_check",
        },
        status=OutboxStatus.PENDING,
    )
    db.add(outbox)

    # 3. Commit atomically
    db.commit()

    return TriggerHealthEventResponse(
        message="Outbox health check event created atomically with business transaction",
        outbox_event_id=str(event_id),
        status="PENDING",
    )
