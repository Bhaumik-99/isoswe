"""AWS Lambda Visitor Photo Retention Purge Handler

Triggered on an automated schedule (e.g. by Amazon EventBridge daily)
to scan and physically delete visitor photos exceeding the 90-day statutory retention limit.
"""

from typing import Any

from app.core.database import SessionLocal
from app.core.logging import logger
from app.domains.visitors.retention_service import PhotoRetentionService


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Scans and physically purges expired visitor photos older than 90 days."""
    logger.info("[LambdaRetention] Scheduled photo retention cleanup triggered.")

    with SessionLocal() as db:
        service = PhotoRetentionService(db)
        purged_count = service.purge_expired_photos(batch_size=200)
        logger.info(f"[LambdaRetention] Successfully purged {purged_count} expired visitor photos.")

    return {
        "statusCode": 200,
        "purgedCount": purged_count,
    }
