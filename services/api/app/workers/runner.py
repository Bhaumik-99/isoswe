"""Outbox and Queue Worker Runner

Continuously runs in local dev or worker containers to:
1. Scan and publish pending outbox events
2. Poll queues and dispatch incoming messages to domain workers
"""

import signal
import time

# Ensure handlers are imported and registered
import app.workers.health_worker  # noqa: F401
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import logger
from app.messaging.consumer import dispatcher
from app.messaging.outbox_publisher import OutboxPublisherService
from app.messaging.publisher import (
    QUEUE_BILLING_JOBS,
    QUEUE_COMPLAINT_AI_JOBS,
    QUEUE_NOTIFICATION_JOBS,
    QUEUE_PAYMENT_EVENTS,
    QUEUE_RECONCILIATION_JOBS,
    get_queue_publisher,
)


class WorkerRunner:
    def __init__(self) -> None:
        self.running = True
        self.outbox_service = OutboxPublisherService()
        self.publisher = get_queue_publisher()

        signal.signal(signal.SIGINT, self._handle_exit)
        signal.signal(signal.SIGTERM, self._handle_exit)

    def _handle_exit(self, signum, frame) -> None:
        logger.info("[WorkerRunner] Termination signal received. Shutting down gracefully...")
        self.running = False

    def run_cycle(self) -> None:
        """Executes a single publication and consumption pass."""
        with SessionLocal() as db:
            # Pass 1: Publish outbox events
            published = self.outbox_service.process_pending_outbox_batch(
                db, batch_size=settings.OUTBOX_BATCH_SIZE
            )
            if published > 0:
                logger.info(f"[WorkerRunner] Dispatched {published} outbox events to queues.")

            # Pass 2: Consume messages from queues
            for queue in [
                QUEUE_NOTIFICATION_JOBS,
                QUEUE_BILLING_JOBS,
                QUEUE_PAYMENT_EVENTS,
                QUEUE_RECONCILIATION_JOBS,
                QUEUE_COMPLAINT_AI_JOBS,
            ]:
                processed = dispatcher.process_queue_messages(
                    queue_name=queue, db=db, publisher=self.publisher, max_messages=10
                )
                if processed > 0:
                    logger.info(
                        f"[WorkerRunner] Consumed and processed {processed} messages from {queue}."
                    )

    def start(self) -> None:
        logger.info("[WorkerRunner] Background outbox publisher and queue worker started.")
        while self.running:
            try:
                self.run_cycle()
                time.sleep(settings.OUTBOX_POLL_INTERVAL_SECONDS)
            except Exception as e:
                logger.error(f"[WorkerRunner] Error in worker cycle: {e}")
                time.sleep(5)


if __name__ == "__main__":
    runner = WorkerRunner()
    runner.start()
