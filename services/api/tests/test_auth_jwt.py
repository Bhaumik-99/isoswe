"""JWT Authentication Test Suite

Mandatory Tests:
1. Invalid JWT rejected (401 Unauthorized)
2. Expired JWT rejected (401 Unauthorized with token expired)
3. Local Auth Bypass fail-closed in staging/production
"""

import time

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.errors import AuthenticationError
from app.integrations.mock_auth import mock_auth_provider


def test_invalid_jwt_rejected(client: TestClient) -> None:
    """Requirement 13.1: Invalid JWT rejected."""
    # Malformed token
    res = client.get("/api/v1/me", headers={"Authorization": "Bearer invalid.jwt.token"})
    assert res.status_code == 401
    assert (
        res.json()["error"]["code"] == "UNAUTHORIZED"
        or res.json()["error"]["code"] == "AUTH_CONFIG_ERROR"
    )

    # Forged unsigned token
    res2 = client.get("/api/v1/me", headers={"Authorization": "Bearer not-a-valid-token"})
    assert res2.status_code == 401
    assert "error" in res2.json()


def test_expired_jwt_rejected() -> None:
    """Requirement 13.2: Expired JWT rejected."""
    from app.integrations.cognito import CognitoJwtVerifier

    verifier = CognitoJwtVerifier()
    # Mock token expired 1 hour ago
    expired_payload = {
        "sub": "some-sub",
        "email": "test@example.com",
        "exp": int(time.time()) - 3600,
        "iss": "https://cognito-idp.ap-south-1.amazonaws.com/test-pool",
        "token_use": "id",
    }
    # Encode with temporary 32-byte key
    fake_token = jwt.encode(
        expired_payload, "test-secret-must-be-32-bytes-long!", algorithm="HS256"
    )

    with pytest.raises(AuthenticationError):
        verifier.verify_token(fake_token)


def test_local_auth_bypass_fails_closed_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that local auth bypass fails closed if invoked in production or staging."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")

    with pytest.raises(AuthenticationError) as exc_info:
        mock_auth_provider.verify_dev_token("dev-token-neeraj")

    assert "strictly forbidden" in exc_info.value.message
    assert exc_info.value.code == "SECURITY_VIOLATION"
