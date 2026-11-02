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
        return response["MessageId"]

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


class LocalQueuePublisher(QueuePublisher):
    """Deterministic in-memory queue publisher for local developer environments.

    Preserves exact production interfaces while removing external AWS dependencies.
    """

    def __init__(self) -> None:
        self.queues: dict[str, list[dict[str, Any]]] = {
            QUEUE_BILLING_JOBS: [],
            QUEUE_PAYMENT_EVENTS: [],
            QUEUE_RECONCILIATION_JOBS: [],
            QUEUE_COMPLAINT_AI_JOBS: [],
            QUEUE_NOTIFICATION_JOBS: [],
        }
        self.dlqs: dict[str, list[dict[str, Any]]] = {f"{q}-dlq": [] for q in self.queues.keys()}
        self._counter = 0

    def publish(self, queue_name: str, envelope: EventEnvelope) -> str:
        if queue_name not in self.queues:
            self.queues[queue_name] = []

        self._counter += 1
        msg_id = f"local-msg-{self._counter}-{envelope.event_id}"
        message_data = {
            "message_id": msg_id,
            "receipt_handle": f"receipt-{msg_id}",
            "body": json.dumps(envelope.model_dump(mode="json")),
            "receive_count": 0,
        }
        self.queues[queue_name].append(message_data)
        logger.info(
            f"[LocalQueuePublisher] Message {msg_id} published to {queue_name} (type: {envelope.event_type})"
        )
        return msg_id

    def get_messages(self, queue_name: str, max_messages: int = 10) -> list[dict[str, Any]]:
        if queue_name not in self.queues:
            return []
        items = self.queues[queue_name][:max_messages]
        # Increment receive count
        for it in items:
            it["receive_count"] += 1
        return items

    def delete_message(self, queue_name: str, receipt_handle: str) -> None:
        if queue_name in self.queues:
            self.queues[queue_name] = [
                m for m in self.queues[queue_name] if m["receipt_handle"] != receipt_handle
            ]

    def send_to_dlq(self, queue_name: str, message: dict[str, Any], reason: str) -> None:
        dlq_name = f"{queue_name}-dlq"
        if dlq_name not in self.dlqs:
            self.dlqs[dlq_name] = []
        message["dlq_reason"] = reason
        self.dlqs[dlq_name].append(message)
        self.delete_message(queue_name, message["receipt_handle"])
        logger.warning(
            f"[LocalQueuePublisher] Message {message.get('message_id')} routed to {dlq_name}: {reason}"
        )


_global_publisher: QueuePublisher | None = None


def get_queue_publisher() -> QueuePublisher:
    global _global_publisher
    if _global_publisher is None:
        if settings.MESSAGING_PROVIDER == "aws":
            _global_publisher = SQSQueuePublisher()
        else:
            _global_publisher = LocalQueuePublisher()
    return _global_publisher
