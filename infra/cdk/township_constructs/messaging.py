"""Messaging Construct: Amazon SQS Queues and Dedicated Dead Letter Queues (DLQs)

Creates the 5 core asynchronous queues with dedicated DLQs, redrive policies,
KMS encryption, configurable visibility timeouts, and retention settings.
"""

from typing import Dict
from aws_cdk import (
    Duration,
    RemovalPolicy,
    aws_kms as kms,
    aws_sqs as sqs,
)
from constructs import Construct
from environments.config import EnvironmentConfig


class QueueWithDLQ:
    """Wrapper grouping a main queue with its corresponding dead-letter queue."""

    def __init__(self, main_queue: sqs.Queue, dlq: sqs.Queue) -> None:
        self.main_queue = main_queue
        self.dlq = dlq


class MessagingConstruct(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        config: EnvironmentConfig,
        kms_key: kms.IKey,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        removal_policy = (
            RemovalPolicy.RETAIN if config.is_production else RemovalPolicy.DESTROY
        )

        queue_names = [
            "billing-jobs",
            "payment-events",
            "reconciliation-jobs",
            "complaint-ai-jobs",
            "notification-jobs",
        ]

        self.queues: Dict[str, QueueWithDLQ] = {}

        for q_name in queue_names:
            # 1. Dedicated Dead Letter Queue (DLQ)
            dlq = sqs.Queue(
                self,
                f"{q_name}-DLQ",
                queue_name=f"{q_name}-dlq-{config.env_name}",
                encryption=sqs.QueueEncryption.KMS,
                encryption_master_key=kms_key,
                retention_period=Duration.days(14),  # Maximum 14-day DLQ retention
                removal_policy=removal_policy,
            )

            # 2. Main Work Queue
            main_q = sqs.Queue(
                self,
                f"{q_name}-Queue",
                queue_name=f"{q_name}-{config.env_name}",
                encryption=sqs.QueueEncryption.KMS,
                encryption_master_key=kms_key,
                visibility_timeout=Duration.seconds(
                    config.sqs_visibility_timeout_seconds
                ),
                retention_period=Duration.days(4),
                dead_letter_queue=sqs.DeadLetterQueue(
                    max_receive_count=config.sqs_max_receive_count,
                    queue=dlq,
                ),
                removal_policy=removal_policy,
            )

            self.queues[q_name] = QueueWithDLQ(main_queue=main_q, dlq=dlq)
