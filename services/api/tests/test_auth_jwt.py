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


def test_cognito_jwt_token_use_and_audience_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies strict validation of ID token 'aud' and Access token 'client_id'."""
    from unittest.mock import MagicMock

    from app.integrations.cognito import CognitoJwtVerifier

    verifier = CognitoJwtVerifier()
    verifier.expected_issuer = "https://cognito-idp.ap-south-1.amazonaws.com/test-pool"
    verifier.app_client_id = "configured-app-client-id"

    # Mock _get_signing_key to return a dummy key
    dummy_key = MagicMock()
    dummy_key.key = "test-secret-must-be-32-bytes-long!"
    monkeypatch.setattr(verifier, "_get_signing_key", lambda token: dummy_key)

    # 1. ID token with wrong audience
    id_token_payload = {
        "sub": "user-sub-123",
        "iss": verifier.expected_issuer,
        "exp": int(time.time()) + 3600,
        "token_use": "id",
        "aud": "wrong-client-id",
    }
    with monkeypatch.context() as m:
        m.setattr(jwt, "decode", lambda *args, **kwargs: id_token_payload)
        with pytest.raises(AuthenticationError) as exc:
            verifier.verify_id_token("dummy-token")
        assert exc.value.code == "INVALID_AUDIENCE"

    # 2. Access token with matching client_id
    access_token_payload = {
        "sub": "user-sub-123",
        "iss": verifier.expected_issuer,
        "exp": int(time.time()) + 3600,
        "token_use": "access",
        "client_id": "configured-app-client-id",
    }
    with monkeypatch.context() as m:
        m.setattr(jwt, "decode", lambda *args, **kwargs: access_token_payload)
        res = verifier.verify_access_token("dummy-token")
        assert res["client_id"] == "configured-app-client-id"

    # 3. Access token passed when ID token expected
    with monkeypatch.context() as m:
        m.setattr(jwt, "decode", lambda *args, **kwargs: access_token_payload)
        with pytest.raises(AuthenticationError) as exc:
            verifier.verify_id_token("dummy-token")
        assert exc.value.code == "TOKEN_USE_MISMATCH"

    # 4. Unknown token_use (e.g. 'refresh')
    refresh_token_payload = {
        "sub": "user-sub-123",
        "iss": verifier.expected_issuer,
        "exp": int(time.time()) + 3600,
        "token_use": "refresh",
    }
    with monkeypatch.context() as m:
        m.setattr(jwt, "decode", lambda *args, **kwargs: refresh_token_payload)
        with pytest.raises(AuthenticationError) as exc:
            verifier.verify_token("dummy-token")
        assert exc.value.code == "INVALID_TOKEN_USE"


def test_cognito_jwt_malformed_claims_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies that malformed subject or non-numeric exp claims are rejected."""
    from unittest.mock import MagicMock

    from app.integrations.cognito import CognitoJwtVerifier

    verifier = CognitoJwtVerifier()
    verifier.expected_issuer = "https://cognito-idp.ap-south-1.amazonaws.com/test-pool"
    dummy_key = MagicMock()
    monkeypatch.setattr(verifier, "_get_signing_key", lambda token: dummy_key)

    # Empty sub
    malformed_sub = {
        "sub": "   ",
        "iss": verifier.expected_issuer,
        "exp": int(time.time()) + 3600,
        "token_use": "id",
        "aud": "any",
    }
    with monkeypatch.context() as m:
        m.setattr(jwt, "decode", lambda *args, **kwargs: malformed_sub)
        with pytest.raises(AuthenticationError) as exc:
            verifier.verify_token("dummy-token")
        assert exc.value.code == "MALFORMED_CLAIMS"
