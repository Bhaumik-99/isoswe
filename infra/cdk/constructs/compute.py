"""Compute Construct: AWS Lambda Functions and Execution Roles

Provisions:
1. API Lambda function running FastAPI with Mangum
2. SQS Worker Lambda processing asynchronous event batches
3. Least-privilege IAM roles with access strictly limited to required SQS queues, Secrets, and KMS keys
4. VPC integration with application subnets
"""

from typing import Dict
from aws_cdk import (
    Duration,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_kms as kms,
    aws_lambda as _lambda,
    aws_lambda_event_sources as lambda_sources,
    aws_logs as logs,
    aws_secretsmanager as secretsmanager,
    aws_sqs as sqs,
)
from constructs import Construct
from environments.config import EnvironmentConfig
from constructs.messaging import QueueWithDLQ


class ComputeConstruct(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        config: EnvironmentConfig,
        vpc: ec2.IVpc,
        lambda_sg: ec2.ISecurityGroup,
        kms_key: kms.IKey,
        db_secret: secretsmanager.ISecret,
        queues: Dict[str, QueueWithDLQ],
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        log_retention = logs.RetentionDays.ONE_MONTH if config.is_production else logs.RetentionDays.ONE_WEEK

        # 1. Base IAM Role with least-privilege policy
        api_role = iam.Role(
            self,
            "ApiLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaVPCAccessExecutionRole")
            ],
        )

        # Grant Secrets Manager and KMS decrypt permissions
        db_secret.grant_read(api_role)
        kms_key.grant_encrypt_decrypt(api_role)

        # Grant SQS SendMessage permissions to all main queues
        for q_wrapper in queues.values():
            q_wrapper.main_queue.grant_send_messages(api_role)

        # 2. FastAPI API Gateway Lambda
        self.api_lambda = _lambda.Function(
            self,
            "ApiFunction",
            function_name=f"township-api-{config.env_name}",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="app.handlers.lambda_api.handler",
            code=_lambda.Code.from_asset("../../services/api"),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[lambda_sg],
            memory_size=1024,
            timeout=Duration.seconds(30),
            role=api_role,
            log_retention=log_retention,
            environment={
                "ENVIRONMENT": config.env_name,
                "LOG_LEVEL": "INFO",
                "MESSAGING_PROVIDER": "aws",
            },
        )

        # 3. SQS Asynchronous Worker Lambda
        worker_role = iam.Role(
            self,
            "WorkerLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaVPCAccessExecutionRole")
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
            code=_lambda.Code.from_asset("../../services/api"),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[lambda_sg],
            memory_size=512,
            timeout=Duration.seconds(60),
            role=worker_role,
            log_retention=log_retention,
            environment={
                "ENVIRONMENT": config.env_name,
                "LOG_LEVEL": "INFO",
                "MESSAGING_PROVIDER": "aws",
            },
        )

        # Attach SQS Event Source Mapping with report_batch_item_failures=True
        notification_queue = queues.get("notification-jobs")
        if notification_queue:
            notification_queue.main_queue.grant_consume_messages(worker_role)
            self.worker_lambda.add_event_source(
                lambda_sources.SqsEventSource(
                    notification_queue.main_queue,
                    batch_size=10,
                    report_batch_item_failures=True,
                )
            )
