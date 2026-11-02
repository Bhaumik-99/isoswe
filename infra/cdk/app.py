#!/usr/bin/env python3
"""AWS CDK Application Entrypoint

Initializes Township Operations Platform stacks across Development, Staging, and Production.
Usage:
  cdk synth -c env=dev
  cdk deploy -c env=staging
"""

import os
from aws_cdk import App, Environment
from environments.config import get_environment_config
from stacks.township_stack import TownshipStack

app = App()

# Read target environment from context or environment variable
target_env_name = app.node.try_get_context("env") or os.environ.get("ENVIRONMENT", "dev")
config = get_environment_config(target_env_name)

# AWS Account and Region resolution from environment
aws_env = Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT") or os.environ.get("AWS_ACCOUNT_ID"),
    region=os.environ.get("CDK_DEFAULT_REGION") or os.environ.get("AWS_REGION", "ap-south-1"),
)

stack_name = f"TownshipOps-{config.env_name.capitalize()}"

TownshipStack(
    app,
    stack_name,
    config=config,
    env=aws_env,
    description=f"Township Operations Platform Foundation - {config.env_name.upper()} Environment",
)

app.synth()
