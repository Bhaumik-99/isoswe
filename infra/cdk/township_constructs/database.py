"""Database Construct: Amazon RDS PostgreSQL and Amazon RDS Proxy

Configures:
- PostgreSQL 16 engine in isolated subnets
- Multi-AZ for high availability (staging/production)
- Automated backups and Point-In-Time Recovery (PITR)
- Storage encryption with Customer Managed Key (KMS)
- Amazon RDS Proxy for Lambda connection pooling and connection storms prevention
- Deletion protection
"""

from aws_cdk import (
    Duration,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_kms as kms,
    aws_rds as rds,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct
from environments.config import EnvironmentConfig


class DatabaseConstruct(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        config: EnvironmentConfig,
        vpc: ec2.IVpc,
        db_security_group: ec2.ISecurityGroup,
        kms_key: kms.IKey,
        db_secret: secretsmanager.ISecret,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        removal_policy = RemovalPolicy.SNAPSHOT if config.is_production else RemovalPolicy.DESTROY

        # 1. RDS PostgreSQL Instance
        self.db_instance = rds.DatabaseInstance(
            self,
            "TownshipDatabase",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_16_3
            ),
            instance_type=ec2.InstanceType(config.db_instance_type),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[db_security_group],
            credentials=rds.Credentials.from_secret(db_secret),
            database_name="township_ops",
            allocated_storage=config.db_allocated_storage_gb,
            max_allocated_storage=config.db_allocated_storage_gb * 2,
            storage_encrypted=True,
            storage_encryption_key=kms_key,
            multi_az=config.db_multi_az,
            deletion_protection=config.db_deletion_protection,
            backup_retention=Duration.days(config.db_backup_retention_days),
            copy_tags_to_snapshot=True,
            auto_minor_version_upgrade=True,
            removal_policy=removal_policy,
        )

        # 2. Amazon RDS Proxy (Lambda connection pooling)
        self.proxy: rds.DatabaseProxy | None = None
        if config.db_enable_proxy:
            self.proxy = self.db_instance.add_proxy(
                "TownshipRdsProxy",
                db_proxy_name=f"township-db-proxy-{config.env_name}",
                secrets=[db_secret],
                vpc=vpc,
                vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
                security_groups=[db_security_group],
                require_tls=True,
                idle_client_timeout=Duration.minutes(15),
                max_connections_percent=100,
            )
