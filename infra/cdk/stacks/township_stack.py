"""Township Operations Primary Stack

Assembles the cohesive multi-tier architecture using modular, reusable constructs.
"""

from aws_cdk import CfnOutput, Stack
from constructs import Construct
from environments.config import EnvironmentConfig
from township_constructs.apigateway import ApiGatewayConstruct
from township_constructs.auth import AuthConstruct
from township_constructs.compute import ComputeConstruct
from township_constructs.database import DatabaseConstruct
from township_constructs.messaging import MessagingConstruct
from township_constructs.network import NetworkConstruct
from township_constructs.security import SecurityConstruct
from township_constructs.storage import StorageConstruct


class TownshipStack(Stack):
    def __init__(
        self, scope: Construct, construct_id: str, config: EnvironmentConfig, **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 1. Security & Cryptography
        security = SecurityConstruct(self, "Security", config=config)

        # 2. Network Isolation (VPC)
        network = NetworkConstruct(self, "Network", config=config, kms_key=security.kms_key)

        # 3. Authentication & User Management (Cognito)
        auth = AuthConstruct(self, "Auth", config=config, kms_key=security.kms_key)

        # 4. Asynchronous Messaging (SQS + DLQs)
        messaging = MessagingConstruct(self, "Messaging", config=config, kms_key=security.kms_key)

        # 5. Relational System of Record (RDS PostgreSQL + RDS Proxy)
        database = DatabaseConstruct(
            self,
            "Database",
            config=config,
            vpc=network.vpc,
            db_security_group=network.db_security_group,
            kms_key=security.kms_key,
            db_secret=security.db_secret,
        )

        # 6. Storage & Content Delivery (S3 + CloudFront)
        storage = StorageConstruct(self, "Storage", config=config, kms_key=security.kms_key)

        # 7. Serverless Compute (Lambda)
        compute = ComputeConstruct(
            self,
            "Compute",
            config=config,
            vpc=network.vpc,
            lambda_sg=network.lambda_security_group,
            kms_key=security.kms_key,
            db_secret=security.db_secret,
            queues=messaging.queues,
        )

        # 8. API Exposure & WAF Protection
        apigw = ApiGatewayConstruct(
            self,
            "ApiGateway",
            config=config,
            api_lambda=compute.api_lambda,
        )

        # CloudFormation Outputs
        CfnOutput(self, "ApiUrl", value=apigw.api.url, description="API Gateway Invocation URL")
        CfnOutput(self, "CloudFrontDomain", value=storage.distribution.distribution_domain_name, description="CloudFront Web App Domain")
        CfnOutput(self, "CognitoUserPoolId", value=auth.user_pool.user_pool_id, description="Cognito User Pool ID")
        CfnOutput(self, "CognitoClientId", value=auth.web_client.user_pool_client_id, description="Cognito App Client ID")
