"""Network Construct: VPC, Subnet Topology, and Security Groups

Establishes network isolation:
- Public Subnets (ALB / NAT Gateways)
- Private Subnets with Egress (Lambda Functions, ECS)
- Isolated Subnets (RDS PostgreSQL, ElastiCache, RDS Proxy)
- VPC Flow Logs for network auditability
"""

from aws_cdk import (
    aws_ec2 as ec2,
    aws_kms as kms,
    aws_logs as logs,
    RemovalPolicy,
)
from constructs import Construct
from environments.config import EnvironmentConfig


class NetworkConstruct(Construct):
    def __init__(
        self, scope: Construct, id: str, config: EnvironmentConfig, kms_key: kms.IKey, **kwargs
    ) -> None:
        super().__init__(scope, id, **kwargs)

        removal_policy = RemovalPolicy.RETAIN if config.is_production else RemovalPolicy.DESTROY

        # 1. Multi-Tier VPC Topology
        self.vpc = ec2.Vpc(
            self,
            "TownshipVpc",
            ip_addresses=ec2.IpAddresses.cidr(config.vpc_cidr),
            max_azs=config.max_azs,
            nat_gateways=config.nat_gateways,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Application",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Database",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
            enable_dns_hostnames=True,
            enable_dns_support=True,
        )

        # 2. VPC Flow Logs for security monitoring
        flow_log_group = logs.LogGroup(
            self,
            "VpcFlowLogsGroup",
            encryption_key=kms_key,
            retention=logs.RetentionDays.ONE_MONTH if config.is_production else logs.RetentionDays.ONE_WEEK,
            removal_policy=removal_policy,
        )

        self.vpc.add_flow_log(
            "VpcFlowLog",
            destination=ec2.FlowLogDestination.to_cloud_watch_logs(flow_log_group),
            traffic_type=ec2.FlowLogTrafficType.ALL,
        )

        # 3. Security Groups
        # Lambda Security Group
        self.lambda_security_group = ec2.SecurityGroup(
            self,
            "LambdaSecurityGroup",
            vpc=self.vpc,
            description="Security Group for backend Lambda execution",
            allow_all_outbound=True,
        )

        # RDS Security Group
        self.db_security_group = ec2.SecurityGroup(
            self,
            "DatabaseSecurityGroup",
            vpc=self.vpc,
            description="Security Group for RDS PostgreSQL",
            allow_all_outbound=False,
        )

        # Allow inbound port 5432 only from Lambda Security Group
        self.db_security_group.add_ingress_rule(
            peer=self.lambda_security_group,
            connection=ec2.Port.tcp(5432),
            description="Allow PostgreSQL access from Lambda functions",
        )
