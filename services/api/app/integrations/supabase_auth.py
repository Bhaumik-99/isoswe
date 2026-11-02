"""Supabase JWT Verification Service

Validates JSON Web Tokens using standard cryptographic libraries and Supabase Auth JWKS endpoints.
Enforces:
1. Asymmetric signature verification (ES256, RS256) using rotating JWKS public keys
2. Correct issuer validation (https://<project-ref>.supabase.co/auth/v1)
3. Explicit audience validation ('authenticated')
4. Mandatory expiration (exp) and subject (sub) validation as a valid UUID
5. Reject malformed, unexpected, or missing claims
"""

import uuid
from typing import Any

import jwt
from jwt import PyJWKClient, PyJWKClientError

from app.core.config import settings
from app.core.errors import AuthenticationError
from app.core.logging import logger


class SupabaseJwtVerifier:
    def __init__(self) -> None:
        self.supabase_url = settings.SUPABASE_URL.rstrip("/") if settings.SUPABASE_URL else ""
        self.jwks_url = settings.SUPABASE_JWKS_URL or (
            f"{self.supabase_url}/auth/v1/.well-known/jwks.json" if self.supabase_url else ""
        )
        self.expected_issuer = settings.SUPABASE_JWT_ISSUER or (
            f"{self.supabase_url}/auth/v1" if self.supabase_url else ""
        )
        self.expected_audience = settings.SUPABASE_JWT_AUDIENCE or "authenticated"
        self.supported_algorithms = ["ES256", "RS256"]
        self._jwks_client: PyJWKClient | None = None
        if self.jwks_url:
            self._jwks_client = PyJWKClient(self.jwks_url, cache_jwk_set=True, lifespan=3600)

    def _get_signing_key(self, token: str) -> Any:
        """Retrieves the signing key with support for JWKS key rotation."""
        if not self._jwks_client:
            raise AuthenticationError(
                message="Supabase JWT verifier is not configured with a valid JWKS endpoint",
                code="AUTH_CONFIG_ERROR",
            )

        try:
            return self._jwks_client.get_signing_key_from_jwt(token)
        except PyJWKClientError:
            # Key rotation scenario: kid not in cache. Refresh the JWKS cache and retry once.
            logger.info("Signing key not found in cache. Refreshing JWKS keyset for rotation...")
            try:
                self._jwks_client = PyJWKClient(self.jwks_url, cache_jwk_set=True, lifespan=3600)
                return self._jwks_client.get_signing_key_from_jwt(token)
            except Exception as e:
                logger.warning(f"Key rotation lookup failed: {e}")
                raise AuthenticationError(
                    message="Unable to locate signing key in identity provider keyset",
                    code="KEY_ROTATION_LOOKUP_FAILED",
                )

    def verify_token(self, token: str) -> dict[str, Any]:
        """Validates and decodes a Supabase Auth JWT token."""
        if not self.expected_issuer and not settings.is_local_dev:
            raise AuthenticationError(
                message="Supabase JWT verifier is not configured with a valid issuer",
                code="AUTH_CONFIG_ERROR",
            )

        try:
            signing_key = self._get_signing_key(token)

            # Strict asymmetric verification of signature, expiration, audience, and issuer
            payload: dict[str, Any] = jwt.decode(
                token,
                signing_key.key,
                algorithms=self.supported_algorithms,
                issuer=self.expected_issuer if self.expected_issuer else None,
                audience=self.expected_audience if self.expected_audience else None,
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iss": bool(self.expected_issuer),
                    "verify_aud": bool(self.expected_audience),
                    "require": ["exp", "sub"],
                },
            )

            # Validate subject claim as valid UUID
            sub = payload.get("sub")
            if not isinstance(sub, str) or not sub.strip():
                raise AuthenticationError(
                    message="Token contains missing or malformed subject (sub) claim",
                    code="MALFORMED_CLAIMS",
                )

            try:
                uuid.UUID(sub.strip())
            except ValueError:
                raise AuthenticationError(
                    message="Token subject (sub) is not a valid UUID format",
                    code="MALFORMED_CLAIMS",
                )

            # Validate expiration claim type
            exp = payload.get("exp")
            if not isinstance(exp, (int, float)):
                raise AuthenticationError(
                    message="Token contains malformed expiration (exp) claim",
                    code="MALFORMED_CLAIMS",
                )

            return payload

        except jwt.ExpiredSignatureError:
            raise AuthenticationError(message="Token has expired", code="TOKEN_EXPIRED")
        except jwt.InvalidIssuerError:
            raise AuthenticationError(message="Token issuer is invalid", code="INVALID_ISSUER")
        except jwt.InvalidAudienceError:
            raise AuthenticationError(message="Token audience is invalid", code="INVALID_AUDIENCE")
        except jwt.InvalidSignatureError:
            raise AuthenticationError(
                message="Token signature is invalid", code="INVALID_SIGNATURE"
            )
        except AuthenticationError:
            raise
        except jwt.PyJWTError as e:
            logger.warning(f"Supabase JWT verification failed: {e}")
            raise AuthenticationError(message=f"Invalid token: {str(e)}", code="INVALID_TOKEN")
        except Exception as e:
            logger.error(f"Unexpected error during Supabase JWT verification: {e}")
            raise AuthenticationError(
                message="Authentication token verification failed", code="AUTH_ERROR"
            )


supabase_verifier = SupabaseJwtVerifier()
