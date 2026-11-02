"""Platform Health Check Worker Handler

Consumes synthetic 'platform.health_check' events to verify the end-to-end
transactional outbox -> SQS -> worker journey without touching live resident/billing data.
"""

from sqlalchemy.orm import Session

from app.core.logging import logger
from app.domains.reliability.models import AuditEvent
from app.messaging.consumer import MessageHandler, dispatcher
from app.messaging.envelope import EventEnvelope


class PlatformHealthCheckHandler(MessageHandler):
    @property
    def consumer_name(self) -> str:
        return "platform_health_worker"

    @property
    def supported_event_types(self) -> list[str]:
        return ["platform.health_check"]

    def process(self, envelope: EventEnvelope, db: Session) -> None:
        logger.info(
            f"[HealthWorker] Executing platform health check event {envelope.event_id}. Aggregate: {envelope.aggregate_id}"
        )

        # Record verification audit event in PostgreSQL
        audit = AuditEvent(
            society_id=None,
            actor_id=None,
            action="platform.health_check.processed",
            resource_type="Platform",
            resource_id=str(envelope.event_id),
            correlation_id=envelope.metadata.correlation_id,
            event_metadata={
                "event_type": envelope.event_type,
                "timestamp": envelope.timestamp,
                "consumer": self.consumer_name,
                "status": "HEALTHY",
            },
        )
        db.add(audit)
        logger.info("[HealthWorker] Health check confirmed and recorded in audit ledger.")


# Register worker handler
health_handler = PlatformHealthCheckHandler()
dispatcher.register(health_handler)
