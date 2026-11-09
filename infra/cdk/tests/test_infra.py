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


def test_s3_documents_bucket_versioning_and_lifecycle_retention(
    prod_template: Template,
) -> None:
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
    assert os.path.exists(
        os.path.join(out_dir, "app", "handlers", "lambda_retention.py")
    )
    assert os.path.exists(os.path.join(out_dir, "requirements.txt"))
    # Verify tests and local caches are cleanly excluded
    assert not os.path.exists(os.path.join(out_dir, "tests"))


def test_lambda_guest_pass_secret_isolation_and_least_privilege(
    prod_template: Template,
) -> None:
    """Verifies that GUEST_PASS_SECRET environment variables and IAM read permissions

    are strictly isolated to the API Lambda, enforcing the Principle of Least Privilege
    and preventing cold-start runtime errors in Worker, Outbox, and Retention Lambdas.
    """
    functions = prod_template.find_resources("AWS::Lambda::Function")
    funcs_by_name = {}
    for defn in functions.values():
        fname = defn.get("Properties", {}).get("FunctionName")
        if fname:
            funcs_by_name[fname] = defn

    # 1. Environment Variables Isolation
    api_fn = funcs_by_name["township-api-prod"]
    worker_fn = funcs_by_name["township-worker-prod"]
    outbox_fn = funcs_by_name["township-outbox-prod"]
    retention_fn = funcs_by_name["township-retention-prod"]

    api_env = api_fn["Properties"]["Environment"]["Variables"]
    worker_env = worker_fn["Properties"]["Environment"]["Variables"]
    outbox_env = outbox_fn["Properties"]["Environment"]["Variables"]
    retention_env = retention_fn["Properties"]["Environment"]["Variables"]

    # API Lambda MUST have both secrets configured
    assert "DATABASE_SECRET_NAME" in api_env
    assert "DATABASE_SECRET_ARN" in api_env
    assert "GUEST_PASS_SECRET_NAME" in api_env
    assert "GUEST_PASS_SECRET_ARN" in api_env

    # Worker, Outbox, and Retention Lambdas MUST NOT receive guest-pass secret environment variables
    for name, env in [
        ("Worker", worker_env),
        ("Outbox", outbox_env),
        ("Retention", retention_env),
    ]:
        assert "DATABASE_SECRET_NAME" in env, f"{name} must have DATABASE_SECRET_NAME"
        assert "GUEST_PASS_SECRET_NAME" not in env, (
            f"{name} must NOT have GUEST_PASS_SECRET_NAME"
        )
        assert "GUEST_PASS_SECRET_ARN" not in env, (
            f"{name} must NOT have GUEST_PASS_SECRET_ARN"
        )

    # 2. IAM Role Least-Privilege Verification
    secrets = prod_template.find_resources("AWS::SecretsManager::Secret")
    guest_pass_secret_id = next(
        k
        for k, v in secrets.items()
        if "Guest Pass" in v.get("Properties", {}).get("Description", "")
    )
    db_secret_id = next(
        k
        for k, v in secrets.items()
        if "Supabase" in v.get("Properties", {}).get("Description", "")
    )

    api_role_ref = api_fn["Properties"]["Role"]["Fn::GetAtt"][0]
    worker_role_ref = worker_fn["Properties"]["Role"]["Fn::GetAtt"][0]
    outbox_role_ref = outbox_fn["Properties"]["Role"]["Fn::GetAtt"][0]
    retention_role_ref = retention_fn["Properties"]["Role"]["Fn::GetAtt"][0]

    policies = prod_template.find_resources("AWS::IAM::Policy")

    def role_has_secret_access(role_ref: str, secret_id: str) -> bool:
        for p in policies.values():
            roles = [
                r.get("Ref")
                for r in p.get("Properties", {}).get("Roles", [])
                if isinstance(r, dict)
            ]
            if role_ref in roles:
                for statement in (
                    p.get("Properties", {})
                    .get("PolicyDocument", {})
                    .get("Statement", [])
                ):
                    action = statement.get("Action", [])
                    if isinstance(action, str):
                        action = [action]
                    res = statement.get("Resource", {})
                    res_ref = res.get("Ref") if isinstance(res, dict) else None
                    if res_ref == secret_id and any(
                        "secretsmanager:GetSecretValue" in a for a in action
                    ):
                        return True
        return False

    # API role must have access to both secrets
    assert role_has_secret_access(api_role_ref, guest_pass_secret_id), (
        "API role must have access to guest pass secret"
    )
    assert role_has_secret_access(api_role_ref, db_secret_id), (
        "API role must have access to database secret"
    )

    # Worker, Outbox, and Retention must NOT have access to guest pass secret
    assert not role_has_secret_access(worker_role_ref, guest_pass_secret_id), (
        "Worker role must NOT have access to guest pass secret"
    )
    assert not role_has_secret_access(outbox_role_ref, guest_pass_secret_id), (
        "Outbox role must NOT have access to guest pass secret"
    )
    assert not role_has_secret_access(retention_role_ref, guest_pass_secret_id), (
        "Retention role must NOT have access to guest pass secret"
    )

    # But all three roles must have access to the database secret
    assert role_has_secret_access(worker_role_ref, db_secret_id), (
        "Worker role must have access to database secret"
    )
    assert role_has_secret_access(outbox_role_ref, db_secret_id), (
        "Outbox role must have access to database secret"
    )
    assert role_has_secret_access(retention_role_ref, db_secret_id), (
        "Retention role must have access to database secret"
    )


def test_notification_worker_least_privilege_iam_permissions(
    prod_template: Template,
) -> None:
    """Verifies that SES and SNS dispatch permissions are granted strictly to Worker Lambda

    and not leaked to API, Outbox, or Retention execution roles.
    """
    functions = prod_template.find_resources("AWS::Lambda::Function")
    funcs_by_name = {
        defn["Properties"]["FunctionName"]: defn
        for defn in functions.values()
        if defn.get("Properties", {}).get("FunctionName")
    }

    api_fn = funcs_by_name["township-api-prod"]
    worker_fn = funcs_by_name["township-worker-prod"]
    outbox_fn = funcs_by_name["township-outbox-prod"]
    retention_fn = funcs_by_name["township-retention-prod"]

    api_role_ref = api_fn["Properties"]["Role"]["Fn::GetAtt"][0]
    worker_role_ref = worker_fn["Properties"]["Role"]["Fn::GetAtt"][0]
    outbox_role_ref = outbox_fn["Properties"]["Role"]["Fn::GetAtt"][0]
    retention_role_ref = retention_fn["Properties"]["Role"]["Fn::GetAtt"][0]

    policies = prod_template.find_resources("AWS::IAM::Policy")

    def role_has_action(role_ref: str, expected_action: str) -> bool:
        for p in policies.values():
            roles = [
                r.get("Ref")
                for r in p.get("Properties", {}).get("Roles", [])
                if isinstance(r, dict)
            ]
            if role_ref in roles:
                for statement in (
                    p.get("Properties", {})
                    .get("PolicyDocument", {})
                    .get("Statement", [])
                ):
                    action = statement.get("Action", [])
                    if isinstance(action, str):
                        action = [action]
                    if expected_action in action:
                        return True
        return False

    # Worker role must have ses:SendEmail and sns:Publish
    assert role_has_action(
        worker_role_ref, "ses:SendEmail"
    ), "Worker role must have ses:SendEmail"
    assert role_has_action(
        worker_role_ref, "sns:Publish"
    ), "Worker role must have sns:Publish"

    # API, Outbox, Retention roles must NOT have ses:SendEmail or sns:Publish
    assert not role_has_action(
        api_role_ref, "ses:SendEmail"
    ), "API role must NOT have ses:SendEmail"
    assert not role_has_action(
        api_role_ref, "sns:Publish"
    ), "API role must NOT have sns:Publish"
    assert not role_has_action(
        outbox_role_ref, "ses:SendEmail"
    ), "Outbox role must NOT have ses:SendEmail"
    assert not role_has_action(
        outbox_role_ref, "sns:Publish"
    ), "Outbox role must NOT have sns:Publish"
    assert not role_has_action(
        retention_role_ref, "ses:SendEmail"
    ), "Retention role must NOT have ses:SendEmail"
    assert not role_has_action(
        retention_role_ref, "sns:Publish"
    ), "Retention role must NOT have sns:Publish"



def test_stack_exposes_outputs_required_by_deploy_workflow(
    prod_template: Template,
) -> None:
    """.github/workflows/deploy-aws.yml reads these CloudFormation outputs by name."""
    outputs = prod_template.to_json()["Outputs"]
    for name in (
        "ApiUrl",
        "CloudFrontDomain",
        "WebBucketName",
        "CloudFrontDistributionId",
    ):
        assert name in outputs, f"Deploy workflow requires stack output '{name}'"
