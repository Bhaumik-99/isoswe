"""Idempotency Handler

Guarantees at-least-once message delivery produces exactly-once business side effects.
Uses PostgreSQL processed_events registry within the consumer's transactional unit of work.
"""

from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.domains.reliability.models import ProcessedEvent


class IdempotencyHandler:
    @staticmethod
    def is_event_processed(consumer_name: str, event_id: UUID, db: Session) -> bool:
        """Checks if this consumer has previously committed this event."""
        stmt = select(ProcessedEvent).where(
            ProcessedEvent.consumer_name == consumer_name,
            ProcessedEvent.event_id == event_id,
        )
        return db.scalars(stmt).first() is not None

    @staticmethod
    def mark_event_processed(consumer_name: str, event_id: UUID, db: Session) -> ProcessedEvent:
        """Records the event as processed within the current active transaction."""
        processed = ProcessedEvent(
            consumer_name=consumer_name,
            event_id=event_id,
        )
        db.add(processed)
        return processed

    @classmethod
    def execute_idempotently(
        cls,
        consumer_name: str,
        event_id: UUID,
        db: Session,
        operation: Callable[[], Any],
    ) -> bool:
        """Executes the given operation only if this event has not been processed.

        Returns True if newly processed, False if duplicate.
        """
        if cls.is_event_processed(consumer_name, event_id, db):
            logger.info(
                f"[IdempotencyHandler] Duplicate event {event_id} skipped for consumer {consumer_name}"
            )
            return False

        # Execute the domain operation
        operation()

        # Mark processed within the same atomic transaction
        cls.mark_event_processed(consumer_name, event_id, db)
        return True
