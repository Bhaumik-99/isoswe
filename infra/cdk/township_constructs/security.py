"""Security Construct: KMS Keys, CloudTrail, and Secrets Manager

Provides cryptographic foundation and audit trail across the stack.
"""

from aws_cdk import (
    RemovalPolicy,
    SecretValue,
    aws_cloudtrail as cloudtrail,
    aws_kms as kms,
    aws_s3 as s3,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct
from environments.config import EnvironmentConfig


class SecurityConstruct(Construct):
    def __init__(self, scope: Construct, id: str, config: EnvironmentConfig, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        removal_policy = RemovalPolicy.RETAIN if config.is_production else RemovalPolicy.DESTROY

        # 1. Master Customer Managed Key (CMK) for encryption at rest
        self.kms_key = kms.Key(
            self,
            "TownshipMasterKey",
            description=f"KMS Master Encryption Key - {config.env_name}",
            enable_key_rotation=True,
            removal_policy=removal_policy,
        )

        # 2. Supabase Connection & Credentials Secret (AWS Secrets Manager)
        # Provisioned as structured JSON template for Supabase pooler connection string and project URL
        # (SUPABASE_SERVICE_ROLE_KEY removed as backend communicates directly via pooled PostgreSQL TLS)
        self.db_secret = secretsmanager.Secret(
            self,
            "DatabaseSecret",
            secret_name=f"township-supabase-credentials-{config.env_name}",
            description=f"Supabase PostgreSQL Connection & Credentials - {config.env_name}",
            secret_object_value={
                "DATABASE_URL": SecretValue.unsafe_plain_text(""),
                "SUPABASE_URL": SecretValue.unsafe_plain_text(""),
            },
            encryption_key=self.kms_key,
            removal_policy=removal_policy,
        )

        # 3. CloudTrail Audit Trail (Governance & Compliance)
        trail_bucket = s3.Bucket(
            self,
            "CloudTrailBucket",
            encryption=s3.BucketEncryption.KMS,
            encryption_key=self.kms_key,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=removal_policy,
            auto_delete_objects=not config.is_production,
        )

        self.trail = cloudtrail.Trail(
            self,
            "TownshipAuditTrail",
            bucket=trail_bucket,
            enable_file_validation=True,
            is_multi_region_trail=config.is_production,
            send_to_cloud_watch_logs=True,
        )
