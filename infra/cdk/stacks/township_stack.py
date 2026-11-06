"""Township Operations Primary Stack: Supabase + AWS Serverless Architecture

Assembles the cohesive serverless architecture using modular, reusable constructs:
- AWS KMS Customer Managed Key for encryption at rest
- AWS Secrets Manager for Supabase connection string and credentials
- Amazon SQS (5 business queues + 5 dedicated DLQs)
- Amazon S3 + CloudFront CDN for frontend and receipts storage
- AWS Lambda (FastAPI API + Asynchronous SQS Worker) with direct TLS to Supabase
- Amazon API Gateway with AWS WAF protection
"""

from aws_cdk import CfnOutput, Stack
from constructs import Construct
from environments.config import EnvironmentConfig
from township_constructs.apigateway import ApiGatewayConstruct
from township_constructs.compute import ComputeConstruct
from township_constructs.messaging import MessagingConstruct
from township_constructs.security import SecurityConstruct
from township_constructs.storage import StorageConstruct


class TownshipStack(Stack):
    def __init__(
        self, scope: Construct, construct_id: str, config: EnvironmentConfig, **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 1. Security & Cryptography (KMS CMK, Secrets Manager, CloudTrail)
        security = SecurityConstruct(self, "Security", config=config)

        # 2. Asynchronous Messaging (5 SQS Queues + 5 Dedicated DLQs + KMS)
        messaging = MessagingConstruct(
            self, "Messaging", config=config, kms_key=security.kms_key
        )

        # 3. Storage & Content Delivery (S3 Private Buckets + CloudFront CDN)
        storage = StorageConstruct(
            self, "Storage", config=config, kms_key=security.kms_key
        )

        # Single source of truth for allowed frontend origins across CloudFront, API Gateway, and FastAPI
        cf_origin = f"https://{storage.distribution.distribution_domain_name}"
        frontend_origins = [cf_origin]
        if config.is_production:
            frontend_origins.append("https://township.example.com")
        else:
            frontend_origins.extend(
                [
                    "http://localhost:5173",
                    "http://localhost:3000",
                    "http://127.0.0.1:5173",
                ]
            )

        # 4. Serverless Compute (FastAPI Lambda + SQS Worker Lambda + Scheduled Tasks)
        compute = ComputeConstruct(
            self,
            "Compute",
            config=config,
            kms_key=security.kms_key,
            db_secret=security.db_secret,
            queues=messaging.queues,
            frontend_origins=frontend_origins,
            documents_bucket=storage.documents_bucket,
        )

        # 5. API Exposure & WAF Protection (API Gateway + WAF)
        apigw = ApiGatewayConstruct(
            self,
            "ApiGateway",
            config=config,
            api_lambda=compute.api_lambda,
            frontend_origins=frontend_origins,
        )

        # CloudFormation Outputs
        CfnOutput(
            self,
            "ApiUrl",
            value=apigw.api.url,
            description="API Gateway Invocation URL",
        )
        CfnOutput(
            self,
            "CloudFrontDomain",
            value=storage.distribution.distribution_domain_name,
            description="CloudFront Web App Domain",
        )
        CfnOutput(
            self,
            "SupabaseSecretArn",
            value=security.db_secret.secret_arn,
            description="AWS Secrets Manager Supabase Secret ARN",
        )
