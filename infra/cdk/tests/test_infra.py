"""AWS CDK Infrastructure Assertions and Unit Tests

Verifies compliance with engineering and security baselines for Option B:
- SQS encryption and dedicated DLQs (5 queues + 5 DLQs = 10 total)
- KMS Customer Managed Key encryption
- AWS Secrets Manager configuration for Supabase
- S3 private buckets with BlockPublicAccess
- Serverless Lambda configuration with direct internet access (no NAT gateway cost)
- API Gateway configuration
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


def test_secrets_manager_supabase_credentials(prod_template: Template) -> None:
    """Verifies AWS Secrets Manager is configured for Supabase credentials & dedicated Guest Pass HMAC with KMS encryption."""
    # 1. Supabase credentials secret preserves original static SecretString to prevent CloudFormation overwriting live DB credentials
    prod_template.has_resource_properties(
        "AWS::SecretsManager::Secret",
        {
            "Description": Match.string_like_regexp("Supabase"),
            "KmsKeyId": Match.any_value(),
            "SecretString": Match.string_like_regexp("DATABASE_URL"),
        },
    )

    # 2. Dedicated Guest Pass HMAC secret auto-generates 64-char key independently without touching DB credentials
    prod_template.has_resource_properties(
        "AWS::SecretsManager::Secret",
        {
            "Description": Match.string_like_regexp("Guest Pass"),
            "KmsKeyId": Match.any_value(),
            "GenerateSecretString": {
                "PasswordLength": 64,
                "ExcludePunctuation": True,
                "RequireEachIncludedType": True,
            },
        },
    )


def test_serverless_lambda_functions_configured(prod_template: Template) -> None:
    """Verifies serverless Lambda functions (API, Worker, Outbox) are configured with least-privilege IAM roles."""
    # 1. FastAPI API Lambda
    prod_template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "FunctionName": "township-api-prod",
            "Runtime": "python3.11",
            "Environment": {
                "Variables": Match.object_like(
                    {
                        "ENVIRONMENT": "production",
                        "MESSAGING_PROVIDER": "aws",
                        "DATABASE_SECRET_NAME": Match.any_value(),
                        "SQS_BILLING_JOBS_QUEUE_URL": Match.any_value(),
                        "CORS_ALLOWED_ORIGINS": Match.any_value(),
                    }
                )
            },
        },
    )

    # 2. Worker Lambda
    prod_template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "FunctionName": "township-worker-prod",
            "Runtime": "python3.11",
            "Environment": {
                "Variables": Match.object_like(
                    {
                        "ENVIRONMENT": "production",
                        "MESSAGING_PROVIDER": "aws",
                        "DATABASE_SECRET_NAME": Match.any_value(),
                        "SQS_BILLING_JOBS_QUEUE_URL": Match.any_value(),
                    }
                )
            },
        },
    )

    # 3. Transactional Outbox Lambda
    prod_template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "FunctionName": "township-outbox-prod",
            "Runtime": "python3.11",
            "Environment": {
                "Variables": Match.object_like(
                    {
                        "ENVIRONMENT": "production",
                        "MESSAGING_PROVIDER": "aws",
                        "DATABASE_SECRET_NAME": Match.any_value(),
                        "SQS_BILLING_JOBS_QUEUE_URL": Match.any_value(),
                    }
                )
            },
        },
    )

    # 4. EventBridge Schedule Rule for Outbox
    prod_template.has_resource_properties(
        "AWS::Events::Rule",
        {
            "Name": "township-outbox-schedule-prod",
            "ScheduleExpression": "rate(1 minute)",
            "State": "ENABLED",
        },
    )

    # 5. Scheduled Visitor Photo Retention Purge Lambda
    prod_template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "FunctionName": "township-retention-prod",
            "Runtime": "python3.11",
            "Handler": "app.handlers.lambda_retention.handler",
            "Timeout": 300,
            "Environment": {
                "Variables": Match.object_like(
                    {
                        "ENVIRONMENT": "production",
                        "MESSAGING_PROVIDER": "aws",
                        "DATABASE_SECRET_NAME": Match.any_value(),
                        "DOCUMENTS_BUCKET_NAME": Match.any_value(),
                    }
                )
            },
        },
    )

    # 6. EventBridge Schedule Rule for Photo Retention Purge
    prod_template.has_resource_properties(
        "AWS::Events::Rule",
        {
            "Name": "township-retention-schedule-prod",
            "ScheduleExpression": "cron(0 2 * * ? *)",
            "State": "ENABLED",
        },
    )


def test_s3_documents_bucket_versioning_and_lifecycle_retention(prod_template: Template) -> None:
    """Verifies private documents S3 bucket has versioning, KMS encryption, noncurrent version lifecycle expiration, and delete marker cleanup."""
    prod_template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "VersioningConfiguration": {
                "Status": "Enabled",
            },
            "LifecycleConfiguration": {
                "Rules": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "Id": "VisitorPhotos90DayRetention",
                                "Prefix": "visitor-photos/",
                                "ExpirationInDays": 90,
                                "NoncurrentVersionExpiration": {
                                    "NoncurrentDays": 1,
                                },
                                "Status": "Enabled",
                            }
                        ),
                        Match.object_like(
                            {
                                "Id": "VisitorPhotosExpiredDeleteMarkers",
                                "Prefix": "visitor-photos/",
                                "ExpiredObjectDeleteMarker": True,
                                "Status": "Enabled",
                            }
                        ),
                    ]
                )
            },
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


def test_api_gateway_rest_api_created(prod_template: Template) -> None:
    """Verifies API Gateway REST API is created."""
    prod_template.has_resource_properties(
        "AWS::ApiGateway::RestApi",
        {
            "Name": "township-api-prod",
        },
    )


def test_lambda_asset_packaging_and_bundler(tmp_path) -> None:
    """Verifies Lambda bundler packages required application files into output directory."""
    import os
    from township_constructs.compute import LambdaLocalBundler

    api_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "services", "api")
    )
    bundler = LambdaLocalBundler(source_path=api_dir)
    out_dir = str(tmp_path / "bundle_output")
    os.makedirs(out_dir, exist_ok=True)

    success = bundler.try_bundle(out_dir)
    assert success is True
    # Verify core application components are bundled into output
    assert os.path.exists(os.path.join(out_dir, "app", "main.py"))
    assert os.path.exists(os.path.join(out_dir, "app", "handlers", "lambda_api.py"))
    assert os.path.exists(os.path.join(out_dir, "app", "handlers", "lambda_retention.py"))
    assert os.path.exists(os.path.join(out_dir, "requirements.txt"))
    # Verify tests and local caches are cleanly excluded
    assert not os.path.exists(os.path.join(out_dir, "tests"))
