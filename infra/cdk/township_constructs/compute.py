"""Compute Construct: AWS Serverless Lambda Functions and Execution Roles

Provisions:
1. API Lambda function running FastAPI with Mangum
2. SQS Worker Lambda processing asynchronous event batches with report_batch_item_failures
3. Direct TLS connection to Supabase without unnecessary VPC/NAT gateway overhead
4. Least-privilege IAM roles with access strictly limited to required SQS queues, Secrets, and KMS keys
"""

import os
import shutil
import sys
from typing import Dict, List, Optional

import jsii
import aws_cdk as cdk
from aws_cdk import (
    BundlingOptions,
    Duration,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_kms as kms,
    aws_lambda as _lambda,
    aws_lambda_event_sources as lambda_sources,
    aws_logs as logs,
    aws_s3 as s3,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct
from environments.config import EnvironmentConfig
from township_constructs.messaging import QueueWithDLQ


@jsii.implements(cdk.ILocalBundling)
class LambdaLocalBundler:
    """Local bundler implementation for test synthesis and offline development.

    Bypasses Docker container execution when CDK_SKIP_DOCKER_BUNDLING=true or in test sessions,
    falling back to direct asset packaging so CDK synthesis remains fast and decoupled from Docker.
    """

    def __init__(self, source_path: str) -> None:
        self.source_path = source_path

    def try_bundle(self, output_dir: str, *args, **kwargs) -> bool:
        skip_docker = os.environ.get("CDK_SKIP_DOCKER_BUNDLING", "false").lower() in (
            "true",
            "1",
            "yes",
        )
        if skip_docker or "pytest" in sys.modules:
            excluded = {
                ".venv",
                ".pytest_cache",
                ".mypy_cache",
                ".ruff_cache",
                "__pycache__",
                "tests",
            }
            for item in os.listdir(self.source_path):
                if item in excluded or item.endswith(".pyc"):
                    continue
                s = os.path.join(self.source_path, item)
                d = os.path.join(output_dir, item)
                if os.path.isdir(s):
                    shutil.copytree(
                        s,
                        d,
                        dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                    )
                else:
                    shutil.copy2(s, d)
            return True
        return False


class ComputeConstruct(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        config: EnvironmentConfig,
        kms_key: kms.IKey,
        db_secret: secretsmanager.ISecret,
        queues: Dict[str, QueueWithDLQ],
        frontend_origins: Optional[List[str]] = None,
        documents_bucket: Optional[s3.IBucket] = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        log_retention = (
            logs.RetentionDays.ONE_MONTH
            if config.is_production
            else logs.RetentionDays.ONE_WEEK
        )

        # 1. API Lambda IAM Role with least-privilege policy
        api_role = iam.Role(
            self,
            "ApiLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )

        # Grant Secrets Manager and KMS decrypt permissions
        db_secret.grant_read(api_role)
        kms_key.grant_encrypt_decrypt(api_role)
        if documents_bucket:
            documents_bucket.grant_read_write(api_role)

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

        canonical_env = (
            "production"
            if config.is_production
            else ("staging" if config.env_name == "staging" else "development")
        )

        # Common environment variables for all serverless application Lambdas
        lambda_environment = {
            "ENVIRONMENT": canonical_env,
            "LOG_LEVEL": "INFO",
            "MESSAGING_PROVIDER": "aws",
            "SUPABASE_JWT_AUDIENCE": "authenticated",
            "DATABASE_SECRET_NAME": db_secret.secret_name,
            "DATABASE_SECRET_ARN": db_secret.secret_arn,
            "SQS_BILLING_JOBS_QUEUE_URL": queues["billing-jobs"].main_queue.queue_url,
            "SQS_PAYMENT_EVENTS_QUEUE_URL": queues[
                "payment-events"
            ].main_queue.queue_url,
            "SQS_RECONCILIATION_JOBS_QUEUE_URL": queues[
                "reconciliation-jobs"
            ].main_queue.queue_url,
            "SQS_COMPLAINT_AI_JOBS_QUEUE_URL": queues[
                "complaint-ai-jobs"
            ].main_queue.queue_url,
            "SQS_NOTIFICATION_JOBS_QUEUE_URL": queues[
                "notification-jobs"
            ].main_queue.queue_url,
        }

        if frontend_origins:
            lambda_environment["CORS_ALLOWED_ORIGINS"] = ",".join(frontend_origins)

        if documents_bucket:
            lambda_environment["DOCUMENTS_BUCKET_NAME"] = documents_bucket.bucket_name
            lambda_environment["S3_ATTACHMENTS_BUCKET_NAME"] = documents_bucket.bucket_name

        # Production Lambda asset with Amazon Linux Python 3.11 Docker bundling and local test fallback
        api_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "services", "api")
        )

        bundling_options = BundlingOptions(
            image=_lambda.Runtime.PYTHON_3_11.bundling_image,
            command=[
                "bash",
                "-c",
                "pip install --no-cache-dir -r requirements.txt -t /asset-output && cp -au . /asset-output",
            ],
            local=LambdaLocalBundler(source_path=api_dir),
        )

        lambda_code = _lambda.Code.from_asset(
            api_dir,
            exclude=lambda_asset_exclude,
            bundling=bundling_options,
        )

        # 2. FastAPI API Gateway Lambda (Direct TLS to Supabase, no NAT Gateway)
        self.api_lambda = _lambda.Function(
            self,
            "ApiFunction",
            function_name=f"township-api-{config.env_name}",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="app.handlers.lambda_api.handler",
            code=lambda_code,
            memory_size=1024,
            timeout=Duration.seconds(30),
            role=api_role,
            log_retention=log_retention,
            environment=lambda_environment,
        )

        # 3. SQS Asynchronous Worker Lambda
        worker_role = iam.Role(
            self,
            "WorkerLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )
        db_secret.grant_read(worker_role)
        kms_key.grant_encrypt_decrypt(worker_role)
        if documents_bucket:
            documents_bucket.grant_read_write(worker_role)

        self.worker_lambda = _lambda.Function(
            self,
            "WorkerFunction",
            function_name=f"township-worker-{config.env_name}",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="app.handlers.lambda_sqs.handler",
            code=lambda_code,
            memory_size=512,
            timeout=Duration.seconds(60),
            role=worker_role,
            log_retention=log_retention,
            environment=lambda_environment,
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

        # 4. Transactional Outbox Publisher Lambda (Scheduled via EventBridge)
        outbox_role = iam.Role(
            self,
            "OutboxLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )
        db_secret.grant_read(outbox_role)
        kms_key.grant_encrypt_decrypt(outbox_role)
        for q_wrapper in queues.values():
            q_wrapper.main_queue.grant_send_messages(outbox_role)

        self.outbox_lambda = _lambda.Function(
            self,
            "OutboxFunction",
            function_name=f"township-outbox-{config.env_name}",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="app.handlers.lambda_outbox.handler",
            code=lambda_code,
            memory_size=512,
            timeout=Duration.seconds(60),
            role=outbox_role,
            log_retention=log_retention,
            environment=lambda_environment,
        )

        # EventBridge Schedule Rule: triggers outbox drain every 1 minute
        events.Rule(
            self,
            "OutboxScheduleRule",
            rule_name=f"township-outbox-schedule-{config.env_name}",
            description=f"Scheduled trigger for Transactional Outbox publisher ({config.env_name})",
            schedule=events.Schedule.rate(Duration.minutes(1)),
            targets=[targets.LambdaFunction(self.outbox_lambda)],
        )

        # 5. Scheduled Visitor Photo Retention Purge Lambda
        retention_role = iam.Role(
            self,
            "RetentionLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )
        db_secret.grant_read(retention_role)
        kms_key.grant_encrypt_decrypt(retention_role)
        if documents_bucket:
            documents_bucket.grant_read_write(retention_role)

        self.retention_lambda = _lambda.Function(
            self,
            "RetentionFunction",
            function_name=f"township-retention-{config.env_name}",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="app.handlers.lambda_retention.handler",
            code=lambda_code,
            memory_size=512,
            timeout=Duration.seconds(300),
            role=retention_role,
            log_retention=log_retention,
            environment=lambda_environment,
        )

        # EventBridge Schedule Rule: triggers photo retention purge daily at 02:00 UTC
        events.Rule(
            self,
            "RetentionScheduleRule",
            rule_name=f"township-retention-schedule-{config.env_name}",
            description=f"Scheduled daily trigger for Visitor Photo Retention purge ({config.env_name})",
            schedule=events.Schedule.cron(minute="0", hour="2"),
            targets=[targets.LambdaFunction(self.retention_lambda)],
        )
