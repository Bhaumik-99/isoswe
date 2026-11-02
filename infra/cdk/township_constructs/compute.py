"""Compute Construct: AWS Serverless Lambda Functions and Execution Roles

Provisions:
1. API Lambda function running FastAPI with Mangum
2. SQS Worker Lambda processing asynchronous event batches with report_batch_item_failures
3. Direct TLS connection to Supabase without unnecessary VPC/NAT gateway overhead
4. Least-privilege IAM roles with access strictly limited to required SQS queues, Secrets, and KMS keys
"""

from typing import Dict, Optional
from aws_cdk import (
    Duration,
    aws_iam as iam,
    aws_kms as kms,
    aws_lambda as _lambda,
    aws_lambda_event_sources as lambda_sources,
    aws_logs as logs,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct
from environments.config import EnvironmentConfig
from township_constructs.messaging import QueueWithDLQ


class ComputeConstruct(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        config: EnvironmentConfig,
        kms_key: kms.IKey,
        db_secret: secretsmanager.ISecret,
        queues: Dict[str, QueueWithDLQ],
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        log_retention = logs.RetentionDays.ONE_MONTH if config.is_production else logs.RetentionDays.ONE_WEEK

        # 1. API Lambda IAM Role with least-privilege policy
        api_role = iam.Role(
            self,
            "ApiLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ],
        )

        # Grant Secrets Manager and KMS decrypt permissions
        db_secret.grant_read(api_role)
        kms_key.grant_encrypt_decrypt(api_role)

        # Grant SQS SendMessage permissions to all main queues
        for q_wrapper in queues.values():
            q_wrapper.main_queue.grant_send_messages(api_role)

        lambda_asset_exclude = [
            ".venv",
            ".venv/**",
            ".pytest_cache",
            ".pytest_cache/**",
            ".mypy_cache",
            ".mypy_cache/**",
            ".ruff_cache",
            ".ruff_cache/**",
            "__pycache__",
            "__pycache__/**",
            "*.pyc",
            "tests",
            "tests/**",
        ]

        # 2. FastAPI API Gateway Lambda (Direct TLS to Supabase, no NAT Gateway)
        self.api_lambda = _lambda.Function(
            self,
            "ApiFunction",
            function_name=f"township-api-{config.env_name}",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="app.handlers.lambda_api.handler",
            code=_lambda.Code.from_asset("../../services/api", exclude=lambda_asset_exclude),
            memory_size=1024,
            timeout=Duration.seconds(30),
            role=api_role,
            log_retention=log_retention,
            environment={
                "ENVIRONMENT": config.env_name,
                "LOG_LEVEL": "INFO",
                "MESSAGING_PROVIDER": "aws",
                "SUPABASE_JWT_AUDIENCE": "authenticated",
            },
        )

        # 3. SQS Asynchronous Worker Lambda
        worker_role = iam.Role(
            self,
            "WorkerLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ],
        )
        db_secret.grant_read(worker_role)
        kms_key.grant_encrypt_decrypt(worker_role)

        self.worker_lambda = _lambda.Function(
            self,
            "WorkerFunction",
            function_name=f"township-worker-{config.env_name}",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="app.handlers.lambda_sqs.handler",
            code=_lambda.Code.from_asset("../../services/api", exclude=lambda_asset_exclude),
            memory_size=512,
            timeout=Duration.seconds(60),
            role=worker_role,
            log_retention=log_retention,
            environment={
                "ENVIRONMENT": config.env_name,
                "LOG_LEVEL": "INFO",
                "MESSAGING_PROVIDER": "aws",
                "SUPABASE_JWT_AUDIENCE": "authenticated",
            },
        )

        # Attach SQS Event Source Mapping with report_batch_item_failures=True for all main queues
        for q_wrapper in queues.values():
            q_wrapper.main_queue.grant_consume_messages(worker_role)
            self.worker_lambda.add_event_source(
                lambda_sources.SqsEventSource(
                    q_wrapper.main_queue,
                    batch_size=10,
                    report_batch_item_failures=True,
                )
            )
