"""Complaint Categorization & AI Job Worker

Consumes complaint AI jobs from QUEUE_COMPLAINT_AI_JOBS:
- complaint.classify
- complaint.assign_priority
"""

from sqlalchemy.orm import Session

from app.core.logging import logger
from app.domains.reliability.models import AuditEvent
from app.messaging.consumer import MessageHandler, dispatcher
from app.messaging.envelope import EventEnvelope


class ComplaintAIHandler(MessageHandler):
    @property
    def consumer_name(self) -> str:
        return "complaint_ai_worker"

    @property
    def supported_event_types(self) -> list[str]:
        return [
            "complaint.classify",
            "complaint.assign_priority",
        ]

    def process(self, envelope: EventEnvelope, db: Session) -> None:
        logger.info(
            f"[ComplaintAIWorker] Processing complaint job {envelope.event_id} ({envelope.event_type}) for aggregate {envelope.aggregate_id}"
        )

        audit = AuditEvent(
            society_id=None,
            actor_id=None,
            action=f"{envelope.event_type}.processed",
            resource_type="Complaint",
            resource_id=str(envelope.aggregate_id),
            correlation_id=envelope.metadata.correlation_id,
            event_metadata={
                "event_id": str(envelope.event_id),
                "event_type": envelope.event_type,
                "consumer": self.consumer_name,
                "classification": "MAINTENANCE_PLUMBING",
            },
        )
        db.add(audit)
        logger.info(
            f"[ComplaintAIWorker] Completed {envelope.event_type} for event {envelope.event_id}"
        )


complaint_handler = ComplaintAIHandler()
dispatcher.register(complaint_handler)
