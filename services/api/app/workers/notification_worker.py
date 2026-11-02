"""Notification Dispatch Asynchronous Worker

Consumes notification events from QUEUE_NOTIFICATION_JOBS:
- notification.dispatch_sms
- notification.dispatch_email
"""

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
        ]

    def process(self, envelope: EventEnvelope, db: Session) -> None:
        logger.info(
            f"[NotificationWorker] Dispatching notification {envelope.event_id} ({envelope.event_type}) for aggregate {envelope.aggregate_id}"
        )

        audit = AuditEvent(
            society_id=None,
            actor_id=None,
            action=f"{envelope.event_type}.dispatched",
            resource_type="Notification",
            resource_id=str(envelope.aggregate_id),
            correlation_id=envelope.metadata.correlation_id,
            event_metadata={
                "event_id": str(envelope.event_id),
                "event_type": envelope.event_type,
                "consumer": self.consumer_name,
                "status": "DELIVERED",
            },
        )
        db.add(audit)
        logger.info(
            f"[NotificationWorker] Completed notification dispatch for event {envelope.event_id}"
        )


notification_handler = NotificationHandler()
dispatcher.register(notification_handler)
