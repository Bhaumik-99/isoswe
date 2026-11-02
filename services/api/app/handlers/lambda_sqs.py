"""AWS Lambda SQS Trigger Handler

Processes native AWS SQS invocation batches within Lambda.
Ensures batch item failures report correctly back to SQS for automatic retry and DLQ routing.
"""

import json
from typing import Any

import app.workers.health_worker  # noqa: F401
from app.core.database import SessionLocal
from app.core.logging import logger
from app.messaging.consumer import dispatcher
from app.messaging.envelope import EventEnvelope


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handles SQS event batches from AWS Lambda event source mappings."""
    records = event.get("Records", [])
    logger.info(f"[LambdaSQS] Received {len(records)} SQS message records.")

    batch_item_failures: list[dict[str, str]] = []

    with SessionLocal() as db:
        for record in records:
            message_id = record.get("messageId", "")
            try:
                body = json.loads(record.get("body", "{}"))
                envelope = EventEnvelope.model_validate(body)

                success = dispatcher.dispatch_envelope(envelope, db)
                if not success:
                    batch_item_failures.append({"itemIdentifier": message_id})

            except Exception as exc:
                logger.error(f"[LambdaSQS] Error processing SQS record {message_id}: {exc}")
                batch_item_failures.append({"itemIdentifier": message_id})

    # Return partial batch failure response for AWS SQS
    return {"batchItemFailures": batch_item_failures}
