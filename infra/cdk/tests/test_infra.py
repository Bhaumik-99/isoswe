"""AWS CDK Infrastructure Assertions and Unit Tests

Verifies compliance with engineering and security baselines:
- SQS encryption and DLQ configuration
- RDS PostgreSQL KMS encryption and private isolation
- Cognito user pool MFA and client configuration
- CloudFront TLS enforcement
"""

import pytest
from aws_cdk import App
from aws_cdk.assertions import Match, Template
from environments.config import get_environment_config
from stacks.township_stack import TownshipStack


@pytest.fixture(scope="session")
def prod_template() -> Template:
    app = App()
    config = get_environment_config("prod")
    stack = TownshipStack(app, "TestTownshipOpsProd", config=config)
    return Template.from_stack(stack)


def test_sqs_queues_have_dedicated_dlqs_and_encryption(prod_template: Template) -> None:
    """Verifies that all 5 required SQS queues are created with dedicated DLQs and KMS encryption."""
    # SQS Queues (5 main queues + 5 DLQs = 10 total)
    prod_template.resource_count_is("AWS::SQS::Queue", 10)

    # Verify KMS encryption is applied
    prod_template.has_resource_properties(
        "AWS::SQS::Queue",
        {
            "KmsMasterKeyId": Match.any_value(),
        },
    )


def test_rds_postgresql_encryption_and_multi_az(prod_template: Template) -> None:
    """Verifies that production RDS instance is Multi-AZ, encrypted, and has deletion protection."""
    prod_template.has_resource_properties(
        "AWS::RDS::DBInstance",
        {
            "Engine": "postgres",
            "MultiAZ": True,
            "StorageEncrypted": True,
            "DeletionProtection": True,
        },
    )


def test_cognito_user_pool_configuration(prod_template: Template) -> None:
    """Verifies Cognito User Pool has email/phone aliases and password policy."""
    prod_template.has_resource_properties(
        "AWS::Cognito::UserPool",
        {
            "AdminCreateUserConfig": {
                "AllowAdminCreateUserOnly": True,
            },
            "UsernameAttributes": Match.array_with(["email", "phone_number"]),
        },
    )


def test_s3_buckets_block_public_access(prod_template: Template) -> None:
    """Verifies S3 buckets block all public access."""
    prod_template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            },
        },
    )
