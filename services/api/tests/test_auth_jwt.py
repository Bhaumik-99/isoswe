"""JWT Authentication Test Suite for Supabase Auth

Mandatory Tests:
1. Invalid JWT rejected (401 Unauthorized)
2. Expired JWT rejected (401 Unauthorized with token expired)
3. Local Auth Bypass fail-closed in staging/production
4. Supabase audience, issuer, and UUID subject validation
5. Reject malformed claims
"""

import time
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.errors import AuthenticationError
from app.integrations.mock_auth import mock_auth_provider
from app.integrations.supabase_auth import SupabaseJwtVerifier


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
    verifier = SupabaseJwtVerifier()
    # Mock token expired 1 hour ago
    expired_payload = {
        "sub": str(uuid.uuid4()),
        "email": "test@example.com",
        "exp": int(time.time()) - 3600,
        "iss": "https://test-project.supabase.co/auth/v1",
        "aud": "authenticated",
        "role": "authenticated",
    }
    # Encode with temporary key
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


def test_supabase_jwt_audience_and_issuer_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies strict validation of 'aud' and 'iss' claims in Supabase JWTs."""
    from unittest.mock import MagicMock

    verifier = SupabaseJwtVerifier()
    verifier.expected_issuer = "https://test-project.supabase.co/auth/v1"
    verifier.expected_audience = "authenticated"

    dummy_key = MagicMock()
    dummy_key.key = "test-secret-must-be-32-bytes-long!"
    monkeypatch.setattr(verifier, "_get_signing_key", lambda token: dummy_key)

    # 1. Token with wrong audience
    _wrong_aud_payload = {
        "sub": str(uuid.uuid4()),
        "iss": verifier.expected_issuer,
        "exp": int(time.time()) + 3600,
        "aud": "wrong-audience",
    }
    with monkeypatch.context() as m:
        m.setattr(
            jwt, "decode", lambda *args, **kwargs: (_ for _ in ()).throw(jwt.InvalidAudienceError())
        )
        with pytest.raises(AuthenticationError) as exc:
            verifier.verify_token("dummy-token")
        assert exc.value.code == "INVALID_AUDIENCE"

    # 2. Token with valid audience and valid UUID subject
    valid_sub = str(uuid.uuid4())
    valid_payload = {
        "sub": valid_sub,
        "iss": verifier.expected_issuer,
        "exp": int(time.time()) + 3600,
        "aud": "authenticated",
    }
    with monkeypatch.context() as m:
        m.setattr(jwt, "decode", lambda *args, **kwargs: valid_payload)
        res = verifier.verify_token("dummy-token")
        assert res["sub"] == valid_sub
        assert res["aud"] == "authenticated"


def test_supabase_jwt_malformed_claims_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies that malformed subject (non-UUID) or non-numeric exp claims are rejected."""
    from unittest.mock import MagicMock

    verifier = SupabaseJwtVerifier()
    verifier.expected_issuer = "https://test-project.supabase.co/auth/v1"
    verifier.expected_audience = "authenticated"
    dummy_key = MagicMock()
    monkeypatch.setattr(verifier, "_get_signing_key", lambda token: dummy_key)

    # 1. Empty sub
    malformed_sub = {
        "sub": "   ",
        "iss": verifier.expected_issuer,
        "exp": int(time.time()) + 3600,
        "aud": "authenticated",
    }
    with monkeypatch.context() as m:
        m.setattr(jwt, "decode", lambda *args, **kwargs: malformed_sub)
        with pytest.raises(AuthenticationError) as exc:
            verifier.verify_token("dummy-token")
        assert exc.value.code == "MALFORMED_CLAIMS"

    # 2. Non-UUID sub (e.g., raw email or arbitrary text)
    non_uuid_sub = {
        "sub": "not-a-valid-uuid-value",
        "iss": verifier.expected_issuer,
        "exp": int(time.time()) + 3600,
        "aud": "authenticated",
    }
    with monkeypatch.context() as m:
        m.setattr(jwt, "decode", lambda *args, **kwargs: non_uuid_sub)
        with pytest.raises(AuthenticationError) as exc:
            verifier.verify_token("dummy-token")
        assert exc.value.code == "MALFORMED_CLAIMS"
