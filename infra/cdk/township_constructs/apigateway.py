"""API Gateway Construct: Amazon API Gateway and AWS WAF

Provisions:
1. REST/HTTP API Gateway proxying to the FastAPI backend Lambda
2. CloudWatch metrics and access logging
3. AWS WAF Web ACL protecting against SQL injection, common vulnerabilities, and rate limiting
"""

from typing import List, Optional
from aws_cdk import (
    aws_apigateway as apigw,
    aws_lambda as _lambda,
    aws_wafv2 as wafv2,
)
from constructs import Construct
from environments.config import EnvironmentConfig


class ApiGatewayConstruct(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        config: EnvironmentConfig,
        api_lambda: _lambda.IFunction,
        frontend_origins: Optional[List[str]] = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        cors_origins = (
            frontend_origins
            if frontend_origins
            else (
                apigw.Cors.ALL_ORIGINS
                if not config.is_production
                else ["https://township.example.com"]
            )
        )

        # 1. API Gateway REST API with proxy integration
        self.api = apigw.LambdaRestApi(
            self,
            "TownshipApiGateway",
            rest_api_name=f"township-api-{config.env_name}",
            handler=api_lambda,
            proxy=True,
            deploy_options=apigw.StageOptions(
                stage_name=config.env_name,
                logging_level=apigw.MethodLoggingLevel.INFO,
                data_trace_enabled=not config.is_production,
                metrics_enabled=True,
                throttling_rate_limit=1000,
                throttling_burst_limit=2000,
            ),
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=cors_origins,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["*"],
            ),
        )

        # 2. AWS WAF Web ACL (Enabled for Production)
        if config.enable_waf and config.is_production:
            waf = wafv2.CfnWebACL(
                self,
                "ApiGatewayWaf",
                name=f"township-api-waf-{config.env_name}",
                scope="REGIONAL",
                default_action=wafv2.CfnWebACL.DefaultActionProperty(allow={}),
                visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                    cloud_watch_metrics_enabled=True,
                    metric_name=f"TownshipApiWafMetric-{config.env_name}",
                    sampled_requests_enabled=True,
                ),
                rules=[
                    # Common Rule Set
                    wafv2.CfnWebACL.RuleProperty(
                        name="AWSManagedRulesCommonRuleSet",
                        priority=1,
                        override_action=wafv2.CfnWebACL.OverrideActionProperty(none={}),
                        statement=wafv2.CfnWebACL.StatementProperty(
                            managed_rule_group_statement=wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                                name="AWSManagedRulesCommonRuleSet",
                                vendor_name="AWS",
                            )
                        ),
                        visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                            cloud_watch_metrics_enabled=True,
                            metric_name="CommonRuleSetMetric",
                            sampled_requests_enabled=True,
                        ),
                    ),
                    # SQL Injection Prevention
                    wafv2.CfnWebACL.RuleProperty(
                        name="AWSManagedRulesSQLiRuleSet",
                        priority=2,
                        override_action=wafv2.CfnWebACL.OverrideActionProperty(none={}),
                        statement=wafv2.CfnWebACL.StatementProperty(
                            managed_rule_group_statement=wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                                name="AWSManagedRulesSQLiRuleSet",
                                vendor_name="AWS",
                            )
                        ),
                        visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                            cloud_watch_metrics_enabled=True,
                            metric_name="SQLiRuleSetMetric",
                            sampled_requests_enabled=True,
                        ),
                    ),
                ],
            )

            # Associate WAF with API Gateway deployment stage
            waf_association = wafv2.CfnWebACLAssociation(
                self,
                "ApiWafAssociation",
                resource_arn=self.api.deployment_stage.stage_arn,
                web_acl_arn=waf.attr_arn,
            )
            # Ensure the API Gateway stage exists before the WAF association is created
            # (a hand-built ARN carries no implicit CloudFormation dependency on the stage).
            waf_association.node.add_dependency(self.api.deployment_stage)
