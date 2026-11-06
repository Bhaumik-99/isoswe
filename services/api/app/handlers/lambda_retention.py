"""AWS Lambda Visitor Photo Retention Purge Handler

Triggered on an automated schedule (e.g. by Amazon EventBridge daily)
to scan and physically delete visitor photos exceeding the 90-day statutory retention limit.

Processes successive batches within a bounded Lambda execution window, with deterministic
FIFO ordering, retry isolation (failed records skipped in subsequent batches to prevent head-of-line blocking),
and comprehensive observability metrics.
"""

import time
import uuid
from typing import Any

from app.core.database import SessionLocal
from app.core.logging import logger
from app.domains.visitors.retention_service import PhotoRetentionService, RetentionBatchResult


def handler(event: dict[str, Any] | None = None, context: Any = None) -> dict[str, Any]:
    """Scans and physically purges expired visitor photos older than 90 days.

    Processes successive batches of expired photos in a bounded execution loop to ensure
    backlogs exceeding a single batch (e.g. >200 records) are completely cleared without
    falling behind, while safely terminating before Lambda timeout limits.
    """
    event = event or {}
    logger.info("[LambdaRetention] Scheduled photo retention cleanup triggered.")

    batch_size: int = int(event.get("batch_size", 200))
    max_batches: int = int(event.get("max_batches", 50))  # Up to 10,000 records per invocation
    min_remaining_time_ms: int = int(event.get("min_remaining_time_ms", 30000))  # 30s buffer
    max_runtime_seconds: float = float(event.get("max_runtime_seconds", 270.0))  # 4.5 minutes

    start_time = time.monotonic()
    total_purged: int = 0
    total_failed: int = 0
    remaining_count: int = 0
    batches_executed: int = 0
    failed_ids: set[uuid.UUID] = set()
    exit_reason: str = "completed"

    with SessionLocal() as db:
        service = PhotoRetentionService(db)

        # Log initial backlog metric
        initial_backlog = service.count_expired_photos()
        logger.info(f"[LambdaRetention] Initial expired unpurged photos count: {initial_backlog}")

        while batches_executed < max_batches:
            # Check AWS Lambda execution time remaining if context is provided
            if context and hasattr(context, "get_remaining_time_in_millis"):
                try:
                    remaining_ms = context.get_remaining_time_in_millis()
                    if remaining_ms <= min_remaining_time_ms:
                        logger.warning(
                            f"[LambdaRetention] Approaching execution deadline ({remaining_ms}ms remaining <= {min_remaining_time_ms}ms buffer). Halting batch loop."
                        )
                        exit_reason = "lambda_timeout_buffer_reached"
                        break
                except Exception as exc:
                    logger.debug(
                        f"[LambdaRetention] Could not retrieve remaining execution time: {exc}"
                    )

            # Check wall-clock runtime limit
            elapsed = time.monotonic() - start_time
            if elapsed >= max_runtime_seconds:
                logger.warning(
                    f"[LambdaRetention] Wall-clock runtime threshold reached ({elapsed:.1f}s >= {max_runtime_seconds:.1f}s). Halting batch loop."
                )
                exit_reason = "max_runtime_exceeded"
                break

            # Execute a single deterministic batch purge
            batch_result: RetentionBatchResult = service.purge_batch(
                batch_size=batch_size,
                exclude_ids=failed_ids,
            )

            batches_executed += 1
            total_purged += batch_result.purged
            total_failed += batch_result.failed
            for fid in batch_result.failed_ids:
                failed_ids.add(fid)
            remaining_count = batch_result.remaining

            logger.info(
                f"[LambdaRetention] Batch {batches_executed} executed: purged={batch_result.purged}, "
                f"failed={batch_result.failed}, remaining={remaining_count}"
            )

            # If no photos were purged in this batch and either no failures occurred or remaining is 0,
            # the backlog is fully drained.
            if batch_result.purged == 0:
                if remaining_count == 0 or batch_result.failed == 0:
                    exit_reason = "all_eligible_purged"
                    break
                # If all records selected in this batch failed, they've been added to failed_ids.
                # If no more records remain outside failed_ids, stop to prevent spinning.
                if remaining_count == 0:
                    exit_reason = "only_failed_records_remain"
                    break

            # If remaining count reached 0, backlog is completely clear
            if remaining_count == 0:
                exit_reason = "all_eligible_purged"
                break
        else:
            if batches_executed >= max_batches:
                exit_reason = "max_batches_reached"

        # Final recount for accuracy
        remaining_count = service.count_expired_photos(exclude_ids=failed_ids)

    duration_seconds = round(time.monotonic() - start_time, 2)
    logger.info(
        f"[LambdaRetention] Retention purge cycle complete in {duration_seconds}s: "
        f"total_purged={total_purged}, total_failed={total_failed}, "
        f"remaining_count={remaining_count}, batches_executed={batches_executed}, "
        f"exit_reason='{exit_reason}'"
    )

    return {
        "statusCode": 200,
        "purgedCount": total_purged,
        "failedCount": total_failed,
        "remainingCount": remaining_count,
        "batchesExecuted": batches_executed,
        "exitReason": exit_reason,
        "failedIds": [str(fid) for fid in failed_ids],
    }
