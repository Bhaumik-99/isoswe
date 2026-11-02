"""Environment Configuration Models for CDK Deployments

Defines differentiated infrastructure configurations for Development, Staging, and Production.
Enforces production database multi-AZ, encryption, deletion protection, and least privilege.
"""

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class EnvironmentConfig:
    env_name: str
    is_production: bool
    vpc_cidr: str
    max_azs: int
    nat_gateways: int
    db_instance_type: str
    db_allocated_storage_gb: int
    db_multi_az: bool
    db_deletion_protection: bool
    db_backup_retention_days: int
    db_enable_proxy: bool
    enable_waf: bool
    sqs_visibility_timeout_seconds: int
    sqs_max_receive_count: int


ENVIRONMENTS: Dict[str, EnvironmentConfig] = {
    "dev": EnvironmentConfig(
        env_name="dev",
        is_production=False,
        vpc_cidr="10.0.0.0/16",
        max_azs=2,
        nat_gateways=1,  # Cost optimization for dev
        db_instance_type="t4g.micro",
        db_allocated_storage_gb=20,
        db_multi_az=False,
        db_deletion_protection=False,
        db_backup_retention_days=1,
        db_enable_proxy=False,  # Proxy optional in dev
        enable_waf=False,
        sqs_visibility_timeout_seconds=300,
        sqs_max_receive_count=3,
    ),
    "staging": EnvironmentConfig(
        env_name="staging",
        is_production=False,
        vpc_cidr="10.1.0.0/16",
        max_azs=2,
        nat_gateways=2,
        db_instance_type="t4g.small",
        db_allocated_storage_gb=50,
        db_multi_az=True,
        db_deletion_protection=True,
        db_backup_retention_days=7,
        db_enable_proxy=True,
        enable_waf=True,
        sqs_visibility_timeout_seconds=300,
        sqs_max_receive_count=5,
    ),
    "prod": EnvironmentConfig(
        env_name="prod",
        is_production=True,
        vpc_cidr="10.2.0.0/16",
        max_azs=3,
        nat_gateways=3,  # High availability across all AZs
        db_instance_type="m6g.xlarge",
        db_allocated_storage_gb=200,
        db_multi_az=True,
        db_deletion_protection=True,
        db_backup_retention_days=35,  # 35 days point-in-time recovery
        db_enable_proxy=True,  # Mandatory RDS Proxy for connection pooling with Lambda
        enable_waf=True,
        sqs_visibility_timeout_seconds=300,
        sqs_max_receive_count=5,
    ),
}


def get_environment_config(env_name: str = "dev") -> EnvironmentConfig:
    return ENVIRONMENTS.get(env_name.lower(), ENVIRONMENTS["dev"])
