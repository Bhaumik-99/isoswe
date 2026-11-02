"""Amazon Cognito JWT Verification Service

Validates JSON Web Tokens using standard cryptographic libraries and Cognito JWKS endpoints.
Enforces:
1. RS256 signature verification using rotating JWKS public keys with rotation support
2. Correct issuer validation (https://cognito-idp.<region>.amazonaws.com/<user_pool_id>)
3. Explicit ID token ('aud') and Access token ('client_id') validation
4. Mandatory expiration (exp), subject (sub), and token_use validation
5. Reject malformed, unexpected, or missing claims
"""

from typing import Any, Literal, cast

import jwt
from jwt import PyJWKClient, PyJWKClientError

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

    def _get_signing_key(self, token: str) -> Any:
        """Retrieves the signing key with support for JWKS key rotation."""
        if not self._jwks_client:
            raise AuthenticationError(
                message="Cognito JWT verifier is not configured with a valid JWKS endpoint",
                code="AUTH_CONFIG_ERROR",
            )

        try:
            return self._jwks_client.get_signing_key_from_jwt(token)
        except PyJWKClientError:
            # Key rotation scenario: kid not in cache. Refresh the JWKS cache and retry once.
            logger.info("Signing key not found in cache. Refreshing JWKS keyset for rotation...")
            try:
                # Invalidate cache and retry
                self._jwks_client = PyJWKClient(self.jwks_url, cache_jwk_set=True, lifespan=3600)
                return self._jwks_client.get_signing_key_from_jwt(token)
            except Exception as e:
                logger.warning(f"Key rotation lookup failed: {e}")
                raise AuthenticationError(
                    message="Unable to locate signing key in identity provider keyset",
                    code="KEY_ROTATION_LOOKUP_FAILED",
                )

    def verify_token(
        self, token: str, expected_token_use: Literal["id", "access", "any"] = "any"
    ) -> dict[str, Any]:
        """Validates and decodes a Cognito JWT token (ID token or Access token)."""
        if not self.expected_issuer:
            raise AuthenticationError(
                message="Cognito JWT verifier is not configured with a valid user pool ID",
                code="AUTH_CONFIG_ERROR",
            )

        try:
            signing_key = self._get_signing_key(token)

            # Strict RS256 verification of signature, expiration, and issuer
            payload: dict[str, Any] = cast(
                dict[str, Any],
                jwt.decode(
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
                ),
            )

            # Validate subject claim
            sub = payload.get("sub")
            if not isinstance(sub, str) or not sub.strip():
                raise AuthenticationError(
                    message="Token contains missing or malformed subject (sub) claim",
                    code="MALFORMED_CLAIMS",
                )

            # Validate expiration claim type
            exp = payload.get("exp")
            if not isinstance(exp, (int, float)):
                raise AuthenticationError(
                    message="Token contains malformed expiration (exp) claim",
                    code="MALFORMED_CLAIMS",
                )

            # Validate token_use claim
            token_use = payload.get("token_use")
            if token_use not in ("id", "access"):
                raise AuthenticationError(
                    message=f"Invalid or unsupported token_use claim '{token_use}'",
                    code="INVALID_TOKEN_USE",
                )

            if expected_token_use != "any" and token_use != expected_token_use:
                raise AuthenticationError(
                    message=f"Expected token of type '{expected_token_use}', got '{token_use}'",
                    code="TOKEN_USE_MISMATCH",
                )

            # Token-type-specific validation
            if token_use == "id":
                aud = payload.get("aud")
                if not aud:
                    raise AuthenticationError(
                        message="ID token is missing mandatory 'aud' claim",
                        code="MISSING_AUDIENCE",
                    )
                if self.app_client_id and aud != self.app_client_id:
                    raise AuthenticationError(
                        message="ID token audience does not match configured app client ID",
                        code="INVALID_AUDIENCE",
                    )
            elif token_use == "access":
                client_id = payload.get("client_id")
                if not client_id:
                    raise AuthenticationError(
                        message="Access token is missing mandatory 'client_id' claim",
                        code="MISSING_CLIENT_ID",
                    )
                if self.app_client_id and client_id != self.app_client_id:
                    raise AuthenticationError(
                        message="Access token client_id does not match configured app client ID",
                        code="INVALID_CLIENT_ID",
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
        except AuthenticationError:
            raise
        except jwt.PyJWTError as e:
            logger.warning(f"Cognito JWT verification failed: {e}")
            raise AuthenticationError(message=f"Invalid token: {str(e)}", code="INVALID_TOKEN")
        except Exception as e:
            logger.error(f"Unexpected error during Cognito JWT verification: {e}")
            raise AuthenticationError(
                message="Authentication token verification failed", code="AUTH_ERROR"
            )

    def verify_id_token(self, token: str) -> dict[str, Any]:
        """Convenience method enforcing that the provided token is strictly an ID token."""
        return self.verify_token(token, expected_token_use="id")

    def verify_access_token(self, token: str) -> dict[str, Any]:
        """Convenience method enforcing that the provided token is strictly an Access token."""
        return self.verify_token(token, expected_token_use="access")


cognito_verifier = CognitoJwtVerifier()
