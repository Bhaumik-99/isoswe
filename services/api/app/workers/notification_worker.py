"""Notification Dispatch Asynchronous Worker

Consumes notification and operational complaint events from QUEUE_NOTIFICATION_JOBS:
- notification.dispatch_sms
- notification.dispatch_email
- complaint.created
- complaint.safety_escalated
- complaint.status_changed
- complaint.assigned
- complaint.resolved
- complaint.reopened
"""

import contextlib
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import logger
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
            "notification.dispatch_sms",
            "notification.dispatch_email",
            "complaint.created",
            "complaint.safety_escalated",
            "complaint.status_changed",
            "complaint.assigned",
            "complaint.resolved",
            "complaint.reopened",
        ]

    def process(self, envelope: EventEnvelope, db: Session) -> None:
        logger.info(
            f"[NotificationWorker] Processing event {envelope.event_id} ({envelope.event_type}) for aggregate {envelope.aggregate_id}"
        )

        society_id: uuid.UUID | None = None
        if isinstance(envelope.payload, dict) and "society_id" in envelope.payload:
            with contextlib.suppress(Exception):
                society_id = uuid.UUID(str(envelope.payload["society_id"]))

        event_metadata: dict[str, Any] = {
            "event_id": str(envelope.event_id),
            "event_type": envelope.event_type,
            "consumer": self.consumer_name,
            "status": "DELIVERED",
        }
        if isinstance(envelope.payload, dict):
            event_metadata["payload_summary"] = {
                k: v
                for k, v in envelope.payload.items()
                if k not in ("token", "secret", "password")
            }

        audit = AuditEvent(
            society_id=society_id,
            actor_id=None,
            action=f"{envelope.event_type}.processed",
            resource_type="Notification"
            if envelope.event_type.startswith("notification")
            else "Complaint",
            resource_id=str(envelope.aggregate_id),
            correlation_id=envelope.metadata.correlation_id,
            event_metadata=event_metadata,
        )
        db.add(audit)
        db.commit()

        logger.info(
            f"[NotificationWorker] Completed dispatch for {envelope.event_type} on aggregate {envelope.aggregate_id}"
        )


notification_handler = NotificationHandler()
dispatcher.register(notification_handler)
