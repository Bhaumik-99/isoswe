"""Bank Statement Reconciliation Asynchronous Queue Worker

Consumes reconciliation jobs and events from QUEUE_RECONCILIATION_JOBS:
- reconciliation.process_bank_statement
- reconciliation.statement_imported
- reconciliation.approved_and_posted
"""

import uuid
from uuid import UUID

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
            "reconciliation.statement_imported",
            "reconciliation.approved_and_posted",
        ]

    def process(self, envelope: EventEnvelope, db: Session) -> None:
        logger.info(
            f"[ReconciliationWorker] Processing event {envelope.event_id} ({envelope.event_type}) for aggregate {envelope.aggregate_id}"
        )

        society_id: UUID | None = None
        try:
            if "society_id" in envelope.payload and envelope.payload["society_id"]:
                society_id = uuid.UUID(str(envelope.payload["society_id"]))
        except Exception:
            society_id = None

        if envelope.event_type == "reconciliation.statement_imported":
            logger.info(
                f"[ReconciliationWorker] Statement import {envelope.aggregate_id} confirmed and matched."
            )
        elif envelope.event_type == "reconciliation.approved_and_posted":
            logger.info(
                f"[ReconciliationWorker] Bank transaction {envelope.aggregate_id} allocated and posted."
            )

        audit = AuditEvent(
            society_id=society_id,
            actor_id=None,
            action=f"{envelope.event_type}.processed",
            resource_type="Reconciliation",
            resource_id=str(envelope.aggregate_id),
            correlation_id=envelope.metadata.correlation_id,
            event_metadata={
                "event_id": str(envelope.event_id),
                "event_type": envelope.event_type,
                "consumer": self.consumer_name,
                "payload": envelope.payload,
            },
        )
        db.add(audit)
        db.commit()
        logger.info(
            f"[ReconciliationWorker] Completed handling event {envelope.event_id} ({envelope.event_type})"
        )


reconciliation_handler = ReconciliationJobHandler()
dispatcher.register(reconciliation_handler)
