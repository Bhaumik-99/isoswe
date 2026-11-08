"""Message Consumer and Event Dispatcher

Coordinates message receipt from SQS/Local queues, payload deserialization,
idempotency evaluation, and dispatch to domain worker handlers.
"""

import json
from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.core.logging import logger
from app.messaging.envelope import EventEnvelope
from app.messaging.idempotency import IdempotencyHandler
from app.messaging.publisher import QueuePublisher, get_queue_publisher


class MessageHandler(ABC):
    @property
    @abstractmethod
    def consumer_name(self) -> str:
        """Unique identifier for this consumer (used for idempotency tracking)."""
        pass

    @property
    @abstractmethod
    def supported_event_types(self) -> list[str]:
        """List of event types this handler consumes."""
        pass

    @abstractmethod
    def process(self, envelope: EventEnvelope, db: Session) -> None:
        """Executes the business logic for this event within a database transaction."""
        pass


class EventDispatcher:
    def __init__(self) -> None:
        self._handlers: dict[str, list[MessageHandler]] = {}

    def register(self, handler: MessageHandler) -> None:
        for event_type in handler.supported_event_types:
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].append(handler)
            logger.info(f"[EventDispatcher] Registered {handler.consumer_name} for '{event_type}'")

    def dispatch_envelope(self, envelope: EventEnvelope, db: Session) -> bool:
        """Dispatches an event envelope to all matching handlers with idempotent execution."""
        handlers = self._handlers.get(envelope.event_type, [])
        if not handlers:
            logger.warning(
                f"[EventDispatcher] No handler registered for event type '{envelope.event_type}'"
            )
            return False

        all_success = True
        for handler in handlers:
            try:
                # Wrap in idempotency check
                def run_handler() -> None:
                    handler.process(envelope, db)

                was_executed = IdempotencyHandler.execute_idempotently(
                    consumer_name=handler.consumer_name,
                    event_id=envelope.event_id,
                    db=db,
                    operation=run_handler,
                )

                if was_executed:
                    db.commit()
                    logger.info(
                        f"[EventDispatcher] Event {envelope.event_id} ({envelope.event_type}) successfully processed by {handler.consumer_name}"
                    )
                else:
                    logger.info(
                        f"[EventDispatcher] Event {envelope.event_id} was already processed by {handler.consumer_name}; skipped duplicate"
                    )

            except Exception as exc:
                db.rollback()
                logger.error(
                    f"[EventDispatcher] Handler {handler.consumer_name} failed for event {envelope.event_id}: {exc}"
                )
                all_success = False

        return all_success

    def process_queue_messages(
        self,
        queue_name: str,
        db: Session,
        publisher: QueuePublisher | None = None,
        max_messages: int = 10,
    ) -> int:
        """Pulls messages from the specified queue and dispatches them."""
        pub = publisher or get_queue_publisher()
        messages = pub.get_messages(queue_name, max_messages=max_messages)
        processed_count = 0

        for msg in messages:
            try:
                body_data = json.loads(msg["body"])
                envelope = EventEnvelope.model_validate(body_data)

                success = self.dispatch_envelope(envelope, db)
                if success:
                    pub.delete_message(queue_name, msg["receipt_handle"])
                    processed_count += 1
                elif int(msg.get("receive_count", 0)) >= 5 and hasattr(pub, "send_to_dlq"):
                    pub.send_to_dlq(
                        queue_name,
                        msg,
                        reason=f"Exceeded max receive_count (5) for event_type '{envelope.event_type}'",
                    )
            except Exception as exc:
                logger.error(
                    f"[EventDispatcher] Failed to deserialize or process queue message: {exc}"
                )

        return processed_count


dispatcher = EventDispatcher()
