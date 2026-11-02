"""Local Development Mock Authentication Provider

Enables local development and deterministic integration testing without requiring
live AWS Cognito connectivity.

SECURITY INVARIANTS:
1. ONLY executes when ENABLE_LOCAL_AUTH_BYPASS is explicitly True.
2. FAILS CLOSED if executed in 'production' or 'staging' environments.
3. Maps known synthetic users deterministically.
"""

from app.core.config import settings
from app.core.errors import AuthenticationError
from app.core.logging import logger

# Deterministic synthetic accounts matching our Pune township seed dataset
MOCK_USERS: dict[str, dict[str, str]] = {
    "dev-token-neeraj": {
        "email": "neeraj.kulkarni@example.com",
        "sub": "mock-sub-neeraj-kulkarni",
        "name": "Neeraj Kulkarni",
        "role": "RESIDENT",
    },
    "dev-token-swati": {
        "email": "swati.joshi@example.com",
        "sub": "mock-sub-swati-joshi",
        "name": "Swati Joshi",
        "role": "RESIDENT",
    },
    "dev-token-aamir": {
        "email": "aamir.shaikh@example.com",
        "sub": "mock-sub-aamir-shaikh",
        "name": "Aamir Shaikh",
        "role": "RESIDENT",
    },
    "dev-token-helpdesk": {
        "email": "helpdesk@example.com",
        "sub": "mock-sub-helpdesk-shinde",
        "name": "Rajesh Shinde",
        "role": "HELPDESK",
    },
}


class MockAuthProvider:
    """Mock Identity Provider for local developer environments."""

    @staticmethod
    def verify_dev_token(token: str) -> dict[str, str]:
        # Critical Fail-Closed Security Assertion
        if settings.ENVIRONMENT in ("production", "staging"):
            logger.critical(
                "CRITICAL SECURITY ALERT: Mock auth provider invoked in production or staging environment!"
            )
            raise AuthenticationError(
                message="Mock authentication is strictly forbidden in non-development environments",
                code="SECURITY_VIOLATION",
            )

        if not settings.ENABLE_LOCAL_AUTH_BYPASS:
            raise AuthenticationError(
                message="Local authentication bypass is not enabled in this environment",
                code="MOCK_AUTH_DISABLED",
            )

        # Allow simple alias like "neeraj" or full "dev-token-neeraj" or "Bearer dev-token-neeraj"
        token_clean = token.replace("Bearer ", "").strip()
        if not token_clean.startswith("dev-token-") and f"dev-token-{token_clean}" in MOCK_USERS:
            token_clean = f"dev-token-{token_clean}"

        user_info = MOCK_USERS.get(token_clean)
        if not user_info:
            raise AuthenticationError(
                message=f"Unknown mock user token '{token_clean}'. Valid tokens: {list(MOCK_USERS.keys())}",
                code="INVALID_DEV_TOKEN",
            )

        return user_info


mock_auth_provider = MockAuthProvider()
