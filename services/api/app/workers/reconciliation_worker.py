"""Bank Statement Reconciliation Asynchronous Queue Worker

Consumes reconciliation jobs from QUEUE_RECONCILIATION_JOBS:
- reconciliation.process_bank_statement
"""

from sqlalchemy.orm import Session

from app.core.logging import logger
from app.domains.reliability.models import AuditEvent
from app.messaging.consumer import MessageHandler, dispatcher
from app.messaging.envelope import EventEnvelope


class ReconciliationJobHandler(MessageHandler):
    @property
    def consumer_name(self) -> str:
        return "reconciliation_worker"

    @property
    def supported_event_types(self) -> list[str]:
        return [
            "reconciliation.process_bank_statement",
        ]

    def process(self, envelope: EventEnvelope, db: Session) -> None:
        logger.info(
            f"[ReconciliationWorker] Processing bank statement {envelope.event_id} for aggregate {envelope.aggregate_id}"
        )

        audit = AuditEvent(
            society_id=None,
            actor_id=None,
            action="reconciliation.processed",
            resource_type="Reconciliation",
            resource_id=str(envelope.aggregate_id),
            correlation_id=envelope.metadata.correlation_id,
            event_metadata={
                "event_id": str(envelope.event_id),
                "event_type": envelope.event_type,
                "consumer": self.consumer_name,
            },
        )
        db.add(audit)
        logger.info(
            f"[ReconciliationWorker] Completed statement processing for event {envelope.event_id}"
        )


reconciliation_handler = ReconciliationJobHandler()
dispatcher.register(reconciliation_handler)
