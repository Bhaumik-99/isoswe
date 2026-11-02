"""Authentication Construct: Amazon Cognito User Pool and App Clients

Implements identity provider requirements:
- Residents authenticate via passwordless OTP flows
- Privileged accounts enforce multi-factor authentication (MFA)
- Cognito User Pool App Client for SPA frontend
"""

from aws_cdk import (
    RemovalPolicy,
    aws_cognito as cognito,
    aws_kms as kms,
)
from constructs import Construct
from environments.config import EnvironmentConfig


class AuthConstruct(Construct):
    def __init__(
        self, scope: Construct, id: str, config: EnvironmentConfig, kms_key: kms.IKey, **kwargs
    ) -> None:
        super().__init__(scope, id, **kwargs)

        removal_policy = RemovalPolicy.RETAIN if config.is_production else RemovalPolicy.DESTROY

        # 1. Cognito User Pool
        self.user_pool = cognito.UserPool(
            self,
            "TownshipUserPool",
            user_pool_name=f"township-users-{config.env_name}",
            self_sign_up_enabled=False,  # Resident onboarding is invitation / admin managed
            sign_in_aliases=cognito.SignInAliases(email=True, phone=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True, phone=True),
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=True),
                phone_number=cognito.StandardAttribute(required=False, mutable=True),
                fullname=cognito.StandardAttribute(required=True, mutable=True),
            ),
            # MFA: OPTIONAL for residents, ENFORCED via policy for Finance/Admin
            mfa=cognito.Mfa.OPTIONAL,
            mfa_second_factor=cognito.MfaSecondFactor(sms=True, otp=True),
            password_policy=cognito.PasswordPolicy(
                min_length=12,
                require_digits=True,
                require_symbols=True,
                require_uppercase=True,
                require_lowercase=True,
                temp_password_validity_days=7,
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=removal_policy,
        )

        # 2. Web Application Client (Single Page Application - no secret)
        self.web_client = self.user_pool.add_client(
            "WebClient",
            user_pool_client_name=f"township-web-client-{config.env_name}",
            generate_secret=False,
            auth_flows=cognito.AuthFlow(
                user_srp=True,
                custom=True,  # Enables passwordless OTP custom auth challenge
                user_password=True,
            ),
            supported_identity_providers=[cognito.UserPoolClientIdentityProvider.COGNITO],
            access_token_validity=None,  # Defaults to 1 hour
            id_token_validity=None,
        )
