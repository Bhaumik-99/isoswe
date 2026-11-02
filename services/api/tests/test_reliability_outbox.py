"""Transactional Outbox, Messaging, and Idempotency Test Suite

Mandatory Tests:
8. Outbox event is committed with its business transaction (atomic integrity)
9. Duplicate event cannot be processed twice (idempotency handler)
10. Failed SQS publishing leaves the event recoverable
"""

import uuid

from sqlalchemy.orm import Session

from app.domains.reliability.models import AuditEvent, OutboxEvent, OutboxStatus
from app.messaging.envelope import EventEnvelope
from app.messaging.idempotency import IdempotencyHandler
from app.messaging.outbox_publisher import OutboxPublisherService
from app.messaging.publisher import QueuePublisher


class FailingMockPublisher(QueuePublisher):
    """Simulates transient or network outages when publishing to SQS."""

    def publish(self, queue_name: str, envelope: EventEnvelope) -> str:
        raise ConnectionResetError("Simulated AWS SQS network timeout")

    def get_messages(self, queue_name: str, max_messages: int = 10) -> list:
        return []

    def delete_message(self, queue_name: str, receipt_handle: str) -> None:
        pass


def test_outbox_event_committed_with_business_transaction(db_session: Session) -> None:
    """Requirement 13.8: Outbox event is committed with its business transaction."""
    event_id = uuid.uuid4()
    correlation_id = str(uuid.uuid4())

    # 1. Successful atomic transaction
    audit = AuditEvent(
        society_id=None,
        actor_id=None,
        action="test.atomic.action",
        resource_type="Test",
        resource_id=str(event_id),
        correlation_id=correlation_id,
        event_metadata={"info": "success"},
    )
    outbox = OutboxEvent(
        id=event_id,
        event_type="test.event",
        aggregate_type="TestAggregate",
        aggregate_id="123",
        payload={"data": "sample"},
        status=OutboxStatus.PENDING,
    )
    db_session.add(audit)
    db_session.add(outbox)
    db_session.commit()

    # Verify both exist
    assert db_session.get(AuditEvent, audit.id) is not None
    assert db_session.get(OutboxEvent, event_id) is not None

    # 2. Rollback scenario: verify atomicity
    fail_event_id = uuid.uuid4()
    try:
        fail_audit = AuditEvent(
            society_id=None,
            actor_id=None,
            action="test.fail.action",
            resource_type="Test",
            resource_id=str(fail_event_id),
            correlation_id=str(uuid.uuid4()),
            event_metadata={"info": "fail"},
        )
        fail_outbox = OutboxEvent(
            id=fail_event_id,
            event_type="test.fail",
            aggregate_type="TestAggregate",
            aggregate_id="456",
            payload={"data": "fail"},
            status=OutboxStatus.PENDING,
        )
        db_session.add(fail_audit)
        db_session.add(fail_outbox)
        # Force an error before commit
        raise RuntimeError("Simulated failure during business processing")
    except RuntimeError:
        db_session.rollback()

    # Assert neither record exists in database
    assert db_session.get(OutboxEvent, fail_event_id) is None


def test_duplicate_event_cannot_be_processed_twice(db_session: Session) -> None:
    """Requirement 13.9: Duplicate event cannot be processed twice (idempotency verification)."""
    event_id = uuid.uuid4()
    consumer_name = "test_billing_consumer"
    counter = {"executions": 0}

    def business_action():
        counter["executions"] += 1

    # First execution: should execute
    executed_1 = IdempotencyHandler.execute_idempotently(
        consumer_name=consumer_name,
        event_id=event_id,
        db=db_session,
        operation=business_action,
    )
    db_session.commit()

    assert executed_1 is True
    assert counter["executions"] == 1
    assert IdempotencyHandler.is_event_processed(consumer_name, event_id, db_session) is True

    # Second execution (duplicate event delivery): MUST be skipped
    executed_2 = IdempotencyHandler.execute_idempotently(
        consumer_name=consumer_name,
        event_id=event_id,
        db=db_session,
        operation=business_action,
    )
    db_session.commit()

    assert executed_2 is False
    assert counter["executions"] == 1  # Execution count did NOT increase!


def test_failed_sqs_publishing_leaves_event_recoverable(db_session: Session) -> None:
    """Requirement 13.10: Failed SQS publishing leaves the event recoverable."""
    event_id = uuid.uuid4()
    outbox = OutboxEvent(
        id=event_id,
        event_type="platform.health_check",
        aggregate_type="Platform",
        aggregate_id="test",
        payload={"test": "data"},
        status=OutboxStatus.PENDING,
        attempts=0,
    )
    db_session.add(outbox)
    db_session.commit()

    # Outbox service with failing publisher
    failing_publisher = FailingMockPublisher()
    outbox_service = OutboxPublisherService(publisher=failing_publisher, max_retries=3)

    # Attempt publishing
    success = outbox_service.publish_single_event(db_session, outbox)
    assert success is False

    # Verify event remains in DB, attempts incremented, not lost
    refetched = db_session.get(OutboxEvent, event_id)
    assert refetched is not None
    assert refetched.attempts == 1
    assert refetched.status == OutboxStatus.PENDING  # still pending because attempts < max_retries

    # After max retries reached, transitions to FAILED but is still preserved for investigation
    outbox_service.publish_single_event(db_session, refetched)
    outbox_service.publish_single_event(db_session, refetched)

    db_session.refresh(refetched)
    assert refetched.attempts == 3
    assert refetched.status == OutboxStatus.FAILED
    assert refetched.published_at is None


def test_publisher_crash_duplicate_delivery_produces_single_business_effect(
    db_session: Session,
) -> None:
    """Requirement: Publisher crashes after sending to SQS but before marking outbox event published.

    Subsequent redelivery delivers the same event ID. Consumer must produce exactly one business effect.
    """
    event_id = uuid.uuid4()
    consumer_name = "payment_processor"
    business_state = {"charge_count": 0}

    def process_charge():
        business_state["charge_count"] += 1

    # First delivery arrives at worker Lambda/consumer
    handled_first = IdempotencyHandler.execute_idempotently(
        consumer_name=consumer_name,
        event_id=event_id,
        db=db_session,
        operation=process_charge,
    )
    db_session.commit()

    assert handled_first is True
    assert business_state["charge_count"] == 1

    # Redelivered event arrives (due to publisher crashing before DB commit, or SQS visibility timeout)
    handled_second = IdempotencyHandler.execute_idempotently(
        consumer_name=consumer_name,
        event_id=event_id,
        db=db_session,
        operation=process_charge,
    )
    db_session.commit()

    # Must be intercepted as duplicate - business action must NOT run again
    assert handled_second is False
    assert business_state["charge_count"] == 1  # Exactly ONE business effect!
