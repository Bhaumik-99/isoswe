"""AWS Lambda Outbox Publisher Handler

Triggered on an automated schedule (e.g. by Amazon EventBridge every 1 minute)
to scan the transactional outbox in Supabase PostgreSQL and publish pending
events to designated Amazon SQS queues.
"""

from typing import Any

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import logger
from app.messaging.outbox_publisher import OutboxPublisherService


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Scans and publishes pending outbox events within a scheduled Lambda execution."""
    logger.info("[LambdaOutbox] Scheduled outbox publisher triggered.")
    service = OutboxPublisherService()

    with SessionLocal() as db:
        published_count = service.process_pending_outbox_batch(
            db, batch_size=settings.OUTBOX_BATCH_SIZE
        )
        logger.info(
            f"[LambdaOutbox] Processed and dispatched {published_count} pending outbox events."
        )

    return {
        "statusCode": 200,
        "publishedCount": published_count,
    }
