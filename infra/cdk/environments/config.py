"""Environment Configuration Models for CDK Deployments

Defines differentiated infrastructure configurations for Development, Staging, and Production.
Enforces production least-privilege, KMS encryption, SQS dead-letter queues, and WAF protection.
"""

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class EnvironmentConfig:
    env_name: str
    is_production: bool
    enable_waf: bool
    sqs_visibility_timeout_seconds: int
    sqs_max_receive_count: int


ENVIRONMENTS: Dict[str, EnvironmentConfig] = {
    "dev": EnvironmentConfig(
        env_name="dev",
        is_production=False,
        enable_waf=False,
        sqs_visibility_timeout_seconds=300,
        sqs_max_receive_count=3,
    ),
    "staging": EnvironmentConfig(
        env_name="staging",
        is_production=False,
        enable_waf=True,
        sqs_visibility_timeout_seconds=300,
        sqs_max_receive_count=5,
    ),
    "prod": EnvironmentConfig(
        env_name="prod",
        is_production=True,
        enable_waf=True,
        sqs_visibility_timeout_seconds=300,
        sqs_max_receive_count=5,
    ),
}


VALID_ENV_ALIASES: Dict[str, str] = {
    "dev": "dev",
    "development": "dev",
    "staging": "staging",
    "stage": "staging",
    "prod": "prod",
    "production": "prod",
}


def get_environment_config(env_name: str = "dev") -> EnvironmentConfig:
    normalized = VALID_ENV_ALIASES.get(env_name.lower().strip())
    if not normalized or normalized not in ENVIRONMENTS:
        valid_envs = list(ENVIRONMENTS.keys())
        raise ValueError(
            f"Unknown CDK environment '{env_name}'. Valid environments are: {valid_envs}"
        )
    return ENVIRONMENTS[normalized]
