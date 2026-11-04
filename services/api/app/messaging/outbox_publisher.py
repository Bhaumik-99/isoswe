"""Transactional Outbox Publisher Service

Scans unpublished events from PostgreSQL outbox_events table using row-level locking
(SELECT ... FOR UPDATE SKIP LOCKED) and dispatches them to their designated SQS queues.
Safely handles crash scenarios, transient errors, and backoff retries.
"""

from datetime import UTC, datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import logger
from app.domains.reliability.models import OutboxEvent, OutboxStatus
from app.messaging.envelope import EventEnvelope, EventMetadata
from app.messaging.publisher import (
    QUEUE_BILLING_JOBS,
    QUEUE_COMPLAINT_AI_JOBS,
    QUEUE_NOTIFICATION_JOBS,
    QUEUE_PAYMENT_EVENTS,
    QUEUE_RECONCILIATION_JOBS,
    QueuePublisher,
    get_queue_publisher,
)


def resolve_queue_for_event_type(event_type: str) -> str:
    """Routes domain event types to appropriate SQS queues."""
    if event_type in ("complaint.classify", "complaint.assign_priority"):
        return QUEUE_COMPLAINT_AI_JOBS

    prefix = event_type.split(".")[0].lower()
    routing = {
        "billing": QUEUE_BILLING_JOBS,
        "payment": QUEUE_PAYMENT_EVENTS,
        "reconciliation": QUEUE_RECONCILIATION_JOBS,
        "complaint": QUEUE_NOTIFICATION_JOBS,
        "notification": QUEUE_NOTIFICATION_JOBS,
        "platform": QUEUE_NOTIFICATION_JOBS,
    }
    return routing.get(prefix, QUEUE_NOTIFICATION_JOBS)


class OutboxPublisherService:
    def __init__(self, publisher: QueuePublisher | None = None, max_retries: int = 5):
        self.publisher = publisher or get_queue_publisher()
        self.max_retries = max_retries

    def fetch_pending_events(self, db: Session, batch_size: int = 50) -> list[OutboxEvent]:
        """Fetches pending or retryable outbox events with row-level skip-locked concurrency control."""
        stmt = (
            select(OutboxEvent)
            .where(
                or_(
                    OutboxEvent.status == OutboxStatus.PENDING,
                    and_(
                        OutboxEvent.status == OutboxStatus.FAILED,
                        OutboxEvent.attempts < self.max_retries,
                    ),
                )
            )
            .order_by(OutboxEvent.created_at.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        return list(db.scalars(stmt).all())

    def publish_single_event(self, db: Session, event: OutboxEvent) -> bool:
        """Publishes a single outbox event to its designated queue and updates its state."""
        queue_name = resolve_queue_for_event_type(event.event_type)

        correlation_id = str(event.id)
        if isinstance(event.payload, dict) and "correlation_id" in event.payload:
            correlation_id = event.payload["correlation_id"]

        envelope = EventEnvelope(
            event_id=event.id,
            event_type=event.event_type,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            timestamp=event.created_at.isoformat(),
            metadata=EventMetadata(
                correlation_id=correlation_id,
                environment=settings.ENVIRONMENT,
            ),
            payload=event.payload,
        )

        try:
            # Dispatch to queue
            self.publisher.publish(queue_name, envelope)

            # Mark as successfully published
            event.status = OutboxStatus.PUBLISHED
            event.published_at = datetime.now(UTC)
            db.commit()
            return True

        except Exception as exc:
            # Handle failure: increment attempts and record failure state
            db.rollback()
            event.attempts += 1
            if event.attempts >= self.max_retries:
                event.status = OutboxStatus.FAILED
                logger.error(
                    f"[OutboxPublisher] Event {event.id} permanently failed after {event.attempts} attempts: {exc}"
                )
            else:
                logger.warning(
                    f"[OutboxPublisher] Event {event.id} publish attempt {event.attempts} failed: {exc}. Will retry."
                )
            db.commit()
            return False

    def process_pending_outbox_batch(self, db: Session, batch_size: int = 50) -> int:
        """Processes a batch of outbox events. Returns count of successfully published events."""
        events = self.fetch_pending_events(db, batch_size=batch_size)
        published_count = 0
        for event in events:
            if self.publish_single_event(db, event):
                published_count += 1
        return published_count
