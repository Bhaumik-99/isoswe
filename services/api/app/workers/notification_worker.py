"""Notification Dispatch Asynchronous Worker

Consumes domain events across Billing, Payments, Complaints, Gate Visitors, and Direct Dispatches:
- billing.invoice_generated
- billing.run_completed
- billing.payment_succeeded
- billing.payment_failed
- billing.payment_allocated
- billing.invoice_paid
- payment.succeeded
- payment.failed
- complaint.created
- complaint.safety_escalated
- complaint.status_changed
- complaint.assigned
- complaint.resolved
- complaint.reopened
- visitor.approval_requested
- visitor.approved
- visitor.rejected
- visitor.checked_in
- pass.revoked
- notification.dispatch_sms
- notification.dispatch_email
"""

import contextlib
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import logger
from app.domains.notifications.service import NotificationService
from app.domains.reliability.models import AuditEvent
from app.messaging.consumer import MessageHandler, dispatcher
from app.messaging.envelope import EventEnvelope


class NotificationHandler(MessageHandler):
    @property
    def consumer_name(self) -> str:
        return "notification_worker"

    @property
    def supported_event_types(self) -> list[str]:
        return [
            # Billing & Payments
            "billing.invoice_generated",
            "billing.run_completed",
            "billing.payment_succeeded",
            "billing.payment_failed",
            "billing.payment_allocated",
            "billing.invoice_paid",
            "payment.succeeded",
            "payment.failed",
            # Complaints & Helpdesk
            "complaint.created",
            "complaint.safety_escalated",
            "complaint.status_changed",
            "complaint.assigned",
            "complaint.resolved",
            "complaint.reopened",
            # Gate & Visitors
            "visitor.approval_requested",
            "visitor.approved",
            "visitor.rejected",
            "visitor.checked_in",
            "pass.revoked",
            # Amenities & Clubhouses
            "amenity.booking_created",
            "amenity.booking_confirmed",
            "amenity.booking_payment_failed",
            "amenity.booking_cancelled",
            # Official Notices & Circulars
            "notice.published",
            "notice.emergency_broadcast",
            "notice.archived",
            # Direct dispatches
            "notification.dispatch_sms",
            "notification.dispatch_email",
        ]

    def process(self, envelope: EventEnvelope, db: Session) -> None:
        logger.info(
            f"[NotificationWorker] Processing event {envelope.event_id} ({envelope.event_type}) for aggregate {envelope.aggregate_id}"
        )

        service = NotificationService(db)
        created_count = service.process_domain_event(envelope)

        society_id: uuid.UUID | None = None
        if isinstance(envelope.payload, dict) and "society_id" in envelope.payload:
            with contextlib.suppress(Exception):
                society_id = uuid.UUID(str(envelope.payload["society_id"]))

        # Record idempotent execution audit record
        event_metadata: dict[str, Any] = {
            "event_id": str(envelope.event_id),
            "event_type": envelope.event_type,
            "consumer": self.consumer_name,
            "notifications_created": created_count,
            "status": "PROCESSED",
        }
        if isinstance(envelope.payload, dict):
            event_metadata["payload_summary"] = {
                k: v
                for k, v in envelope.payload.items()
                if k not in ("token", "secret", "password", "notes", "pass_code")
            }

        audit = AuditEvent(
            society_id=society_id,
            actor_id=None,
            action=f"{envelope.event_type}.processed",
            resource_type="Notification",
            resource_id=str(envelope.aggregate_id),
            correlation_id=envelope.metadata.correlation_id,
            event_metadata=event_metadata,
        )
        db.add(audit)
        db.commit()

        logger.info(
            f"[NotificationWorker] Completed notification dispatch for {envelope.event_type} on aggregate {envelope.aggregate_id} ({created_count} notifications created)"
        )


notification_handler = NotificationHandler()
dispatcher.register(notification_handler)
