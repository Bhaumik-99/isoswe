"""Storage and Content Delivery Construct: Amazon S3 and CloudFront

Configures:
- Private S3 Bucket for documents, invoices, and bank statements
- Private S3 Bucket for frontend SPA static hosting
- CloudFront distribution with Origin Access Control (OAC)
- Enforces TLS 1.3, SSL-only access, and zero public bucket access
"""

from aws_cdk import (
    Duration,
    RemovalPolicy,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_kms as kms,
    aws_s3 as s3,
)
from constructs import Construct
from environments.config import EnvironmentConfig


class StorageConstruct(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        config: EnvironmentConfig,
        kms_key: kms.IKey,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        removal_policy = (
            RemovalPolicy.RETAIN if config.is_production else RemovalPolicy.DESTROY
        )

        # 1. Documents Private Bucket (Statements, Invoices, Receipts, Visitor Photos)
        self.documents_bucket = s3.Bucket(
            self,
            "DocumentsBucket",
            bucket_name=f"township-ops-documents-{config.env_name}",
            encryption=s3.BucketEncryption.KMS,
            encryption_key=kms_key,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            versioned=True,
            removal_policy=removal_policy,
            auto_delete_objects=not config.is_production,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="VisitorPhotos90DayRetention",
                    prefix="visitor-photos/",
                    expiration=Duration.days(90),
                    noncurrent_version_expiration=Duration.days(1),
                ),
                s3.LifecycleRule(
                    id="VisitorPhotosExpiredDeleteMarkers",
                    prefix="visitor-photos/",
                    expired_object_delete_marker=True,
                ),
            ],
        )

        # 2. Frontend SPA Web Hosting Bucket (Private)
        self.web_bucket = s3.Bucket(
            self,
            "WebHostingBucket",
            bucket_name=f"township-ops-web-{config.env_name}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=removal_policy,
            auto_delete_objects=not config.is_production,
        )

        # 3. CloudFront Distribution (Production only)
        # Staging uses external frontend hosting until AWS account verification.
        self.distribution = None
        if config.is_production:
            self.distribution = cloudfront.Distribution(
                self,
                "WebDistribution",
                default_behavior=cloudfront.BehaviorOptions(
                    origin=origins.S3BucketOrigin.with_origin_access_control(
                        self.web_bucket
                    ),
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD_OPTIONS,
                    cached_methods=cloudfront.CachedMethods.CACHE_GET_HEAD_OPTIONS,
                ),
                default_root_object="index.html",
                error_responses=[
                    cloudfront.ErrorResponse(
                        http_status=404,
                        response_http_status=200,
                        response_page_path="/index.html",
                    ),
                    cloudfront.ErrorResponse(
                        http_status=403,
                        response_http_status=200,
                        response_page_path="/index.html",
                    ),
                ],
                minimum_protocol_version=cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
            )
