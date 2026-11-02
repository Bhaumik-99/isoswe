"""Amazon Cognito JWT Verification Service

Validates JSON Web Tokens using standard cryptographic libraries and Cognito JWKS endpoints.
Enforces:
1. Valid RSA signature using rotating JWKS public keys
2. Issuer validation (Cognito User Pool ID)
3. Audience / client_id validation
4. Expiry (exp)
5. Token usage (token_use: "id" or "access")
"""

from typing import Any

import jwt
from jwt import PyJWKClient

from app.core.config import settings
from app.core.errors import AuthenticationError
from app.core.logging import logger


class CognitoJwtVerifier:
    def __init__(self) -> None:
        self.region = settings.AWS_REGION
        self.user_pool_id = settings.COGNITO_USER_POOL_ID
        self.app_client_id = settings.COGNITO_APP_CLIENT_ID
        self.jwks_url = settings.COGNITO_JWKS_URL or (
            f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}/.well-known/jwks.json"
            if self.user_pool_id
            else ""
        )
        self.expected_issuer = (
            f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}"
            if self.user_pool_id
            else ""
        )
        self._jwks_client: PyJWKClient | None = None
        if self.jwks_url:
            self._jwks_client = PyJWKClient(self.jwks_url, cache_jwk_set=True, lifespan=3600)

    def verify_token(self, token: str) -> dict[str, Any]:
        """Validates and decodes a Cognito JWT token."""
        if not self._jwks_client or not self.expected_issuer:
            raise AuthenticationError(
                message="Cognito JWT verifier is not configured with a valid user pool ID",
                code="AUTH_CONFIG_ERROR",
            )

        try:
            # Fetch signing key matching the token's kid
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)

            # Decode and verify signature, issuer, and expiration
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self.expected_issuer,
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iss": True,
                    "require": ["exp", "iss", "sub"],
                },
            )

            # Verify audience / client_id
            token_use = payload.get("token_use")
            if token_use not in ("id", "access"):
                raise AuthenticationError(
                    message=f"Invalid token_use claim '{token_use}'",
                    code="INVALID_TOKEN_USE",
                )

            # Check client_id in access token or aud in id token
            client_id = payload.get("client_id") if token_use == "access" else payload.get("aud")
            if self.app_client_id and client_id != self.app_client_id:
                raise AuthenticationError(
                    message="Token audience does not match configured app client ID",
                    code="INVALID_AUDIENCE",
                )

            return payload

        except jwt.ExpiredSignatureError:
            raise AuthenticationError(message="Token has expired", code="TOKEN_EXPIRED")
        except jwt.InvalidIssuerError:
            raise AuthenticationError(message="Token issuer is invalid", code="INVALID_ISSUER")
        except jwt.InvalidSignatureError:
            raise AuthenticationError(
                message="Token signature is invalid", code="INVALID_SIGNATURE"
            )
        except jwt.PyJWTError as e:
            logger.warning(f"Cognito JWT verification failed: {e}")
            raise AuthenticationError(message=f"Invalid token: {str(e)}", code="INVALID_TOKEN")
        except Exception as e:
            logger.error(f"Unexpected error during Cognito JWT verification: {e}")
            raise AuthenticationError(
                message="Authentication token verification failed", code="AUTH_ERROR"
            )


cognito_verifier = CognitoJwtVerifier()
