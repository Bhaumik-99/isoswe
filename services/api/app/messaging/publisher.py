"""Queue Publisher Abstractions and Implementations

Supports both AWS SQS for cloud environments and an isolated LocalQueuePublisher
for developer environments without AWS credentials.
"""

import json
from abc import ABC, abstractmethod
from typing import Any

import boto3

from app.core.config import settings
from app.core.logging import logger
from app.messaging.envelope import EventEnvelope

# Canonical SQS queue names required for society operations platform
QUEUE_BILLING_JOBS = "billing-jobs"
QUEUE_PAYMENT_EVENTS = "payment-events"
QUEUE_RECONCILIATION_JOBS = "reconciliation-jobs"
QUEUE_COMPLAINT_AI_JOBS = "complaint-ai-jobs"
QUEUE_NOTIFICATION_JOBS = "notification-jobs"


class QueuePublisher(ABC):
    @abstractmethod
    def publish(self, queue_name: str, envelope: EventEnvelope) -> str:
        """Publishes an event envelope to the named queue. Returns message/receipt ID."""
        pass

    @abstractmethod
    def get_messages(self, queue_name: str, max_messages: int = 10) -> list[dict[str, Any]]:
        """Retrieves messages from the named queue (used by consumers/workers)."""
        pass

    @abstractmethod
    def delete_message(self, queue_name: str, receipt_handle: str) -> None:
        """Acknowledges and deletes a processed message from the queue."""
        pass


class SQSQueuePublisher(QueuePublisher):
    """Production AWS SQS publisher implementation."""

    def __init__(self) -> None:
        self.sqs = boto3.client("sqs", region_name=settings.AWS_REGION)
        self.queue_url_map = {
            QUEUE_BILLING_JOBS: settings.SQS_BILLING_JOBS_QUEUE_URL,
            QUEUE_PAYMENT_EVENTS: settings.SQS_PAYMENT_EVENTS_QUEUE_URL,
            QUEUE_RECONCILIATION_JOBS: settings.SQS_RECONCILIATION_JOBS_QUEUE_URL,
            QUEUE_COMPLAINT_AI_JOBS: settings.SQS_COMPLAINT_AI_JOBS_QUEUE_URL,
            QUEUE_NOTIFICATION_JOBS: settings.SQS_NOTIFICATION_JOBS_QUEUE_URL,
        }

    def _resolve_queue_url(self, queue_name: str) -> str:
        url = self.queue_url_map.get(queue_name)
        if not url:
            # Fallback to fetching queue URL by name
            res = self.sqs.get_queue_url(QueueName=queue_name)
            url = res["QueueUrl"]
            self.queue_url_map[queue_name] = url
        return url

    def publish(self, queue_name: str, envelope: EventEnvelope) -> str:
        queue_url = self._resolve_queue_url(queue_name)
        payload_json = json.dumps(envelope.model_dump(mode="json"))

        response = self.sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=payload_json,
            MessageAttributes={
                "EventType": {"DataType": "String", "StringValue": envelope.event_type},
                "CorrelationId": {
                    "DataType": "String",
                    "StringValue": envelope.metadata.correlation_id,
                },
            },
        )
        return str(response["MessageId"])

    def get_messages(self, queue_name: str, max_messages: int = 10) -> list[dict[str, Any]]:
        queue_url = self._resolve_queue_url(queue_name)
        response = self.sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=min(max_messages, 10),
            WaitTimeSeconds=5,
            MessageAttributeNames=["All"],
        )
        messages = response.get("Messages", [])
        return [
            {
                "receipt_handle": m["ReceiptHandle"],
                "body": m["Body"],
                "message_id": m["MessageId"],
            }
            for m in messages
        ]

    def delete_message(self, queue_name: str, receipt_handle: str) -> None:
        queue_url = self._resolve_queue_url(queue_name)
        self.sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)


import sqlite3
import threading


class DurableLocalQueuePublisher(QueuePublisher):
    """Durable file-backed queue adapter for local development.

    Persists published queue messages to an atomic, transactional SQLite storage layer,
    ensuring messages survive process restarts, worker crashes, and local container reboots.
    """

    def __init__(self, db_path: str = "durable_local_queue.db") -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS local_queue_messages (
                    message_id TEXT PRIMARY KEY,
                    queue_name TEXT NOT NULL,
                    receipt_handle TEXT UNIQUE NOT NULL,
                    body TEXT NOT NULL,
                    receive_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'AVAILABLE',
                    dlq_reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_lqm_queue_status ON local_queue_messages (queue_name, status);"
            )

    def publish(self, queue_name: str, envelope: EventEnvelope) -> str:
        msg_id = f"durable-msg-{envelope.event_id}"
        receipt = f"receipt-{msg_id}"
        body_json = json.dumps(envelope.model_dump(mode="json"))

        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO local_queue_messages (message_id, queue_name, receipt_handle, body, receive_count, status)
                VALUES (?, ?, ?, ?, 0, 'AVAILABLE');
                """,
                (msg_id, queue_name, receipt, body_json),
            )
        logger.info(
            f"[DurableLocalQueue] Message {msg_id} written durably to {queue_name} (type: {envelope.event_type})"
        )
        return msg_id

    def get_messages(self, queue_name: str, max_messages: int = 10) -> list[dict[str, Any]]:
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT message_id, receipt_handle, body, receive_count
                FROM local_queue_messages
                WHERE queue_name = ? AND status = 'AVAILABLE'
                ORDER BY created_at ASC
                LIMIT ?;
                """,
                (queue_name, max_messages),
            )
            rows = cursor.fetchall()
            results = []
            for row in rows:
                new_count = int(row["receive_count"]) + 1
                conn.execute(
                    "UPDATE local_queue_messages SET receive_count = ? WHERE message_id = ?",
                    (new_count, row["message_id"]),
                )
                results.append(
                    {
                        "message_id": str(row["message_id"]),
                        "receipt_handle": str(row["receipt_handle"]),
                        "body": str(row["body"]),
                        "receive_count": new_count,
                    }
                )
            return results

    def delete_message(self, queue_name: str, receipt_handle: str) -> None:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                "DELETE FROM local_queue_messages WHERE receipt_handle = ?",
                (receipt_handle,),
            )

    def send_to_dlq(self, queue_name: str, message: dict[str, Any], reason: str) -> None:
        receipt_handle = message.get("receipt_handle", "")
        with self._lock, self._get_connection() as conn:
            conn.execute(
                "UPDATE local_queue_messages SET status = 'DLQ', dlq_reason = ? WHERE receipt_handle = ?",
                (reason, receipt_handle),
            )
        logger.warning(
            f"[DurableLocalQueue] Message {message.get('message_id')} moved to DLQ: {reason}"
        )


# Backward-compatible alias
LocalQueuePublisher = DurableLocalQueuePublisher

_global_publisher: QueuePublisher | None = None


def get_queue_publisher() -> QueuePublisher:
    global _global_publisher
    if _global_publisher is None:
        if settings.MESSAGING_PROVIDER == "aws":
            _global_publisher = SQSQueuePublisher()
        else:
            _global_publisher = DurableLocalQueuePublisher()
    return _global_publisher
