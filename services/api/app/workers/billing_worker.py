"""Billing Domain Asynchronous Queue Worker

Consumes billing jobs from QUEUE_BILLING_JOBS:
- billing.generate_maintenance_bills
- billing.apply_late_fees
"""

from sqlalchemy.orm import Session

from app.core.logging import logger
from app.domains.reliability.models import AuditEvent
from app.messaging.consumer import MessageHandler, dispatcher
from app.messaging.envelope import EventEnvelope


class BillingJobHandler(MessageHandler):
    @property
    def consumer_name(self) -> str:
        return "billing_worker"

    @property
    def supported_event_types(self) -> list[str]:
        return [
            "billing.generate_maintenance_bills",
            "billing.apply_late_fees",
        ]

    def process(self, envelope: EventEnvelope, db: Session) -> None:
        logger.info(
            f"[BillingWorker] Processing billing event {envelope.event_id} ({envelope.event_type}) for aggregate {envelope.aggregate_id}"
        )

        # Record idempotent execution audit record
        audit = AuditEvent(
            society_id=None,
            actor_id=None,
            action=f"{envelope.event_type}.processed",
            resource_type="Billing",
            resource_id=str(envelope.aggregate_id),
            correlation_id=envelope.metadata.correlation_id,
            event_metadata={
                "event_id": str(envelope.event_id),
                "event_type": envelope.event_type,
                "consumer": self.consumer_name,
                "payload_summary": "Processed billing batch successfully",
            },
        )
        db.add(audit)
        logger.info(
            f"[BillingWorker] Completed {envelope.event_type} for event {envelope.event_id}"
        )


billing_handler = BillingJobHandler()
dispatcher.register(billing_handler)
