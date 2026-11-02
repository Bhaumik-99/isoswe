"""Payment Domain Asynchronous Queue Worker

Consumes payment events from QUEUE_PAYMENT_EVENTS:
- payment.received
- payment.failed
"""

from sqlalchemy.orm import Session

from app.core.logging import logger
from app.domains.reliability.models import AuditEvent
from app.messaging.consumer import MessageHandler, dispatcher
from app.messaging.envelope import EventEnvelope


class PaymentEventHandler(MessageHandler):
    @property
    def consumer_name(self) -> str:
        return "payment_worker"

    @property
    def supported_event_types(self) -> list[str]:
        return [
            "payment.received",
            "payment.failed",
        ]

    def process(self, envelope: EventEnvelope, db: Session) -> None:
        logger.info(
            f"[PaymentWorker] Processing payment event {envelope.event_id} ({envelope.event_type}) for aggregate {envelope.aggregate_id}"
        )

        audit = AuditEvent(
            society_id=None,
            actor_id=None,
            action=f"{envelope.event_type}.processed",
            resource_type="Payment",
            resource_id=str(envelope.aggregate_id),
            correlation_id=envelope.metadata.correlation_id,
            event_metadata={
                "event_id": str(envelope.event_id),
                "event_type": envelope.event_type,
                "consumer": self.consumer_name,
                "status": "RECORDED",
            },
        )
        db.add(audit)
        logger.info(
            f"[PaymentWorker] Completed {envelope.event_type} for event {envelope.event_id}"
        )


payment_handler = PaymentEventHandler()
dispatcher.register(payment_handler)
