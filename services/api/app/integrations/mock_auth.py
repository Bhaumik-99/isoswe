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
        "phone": "+91-98000-00001",
        "sub": "00000000-0000-0000-0000-000000000001",
        "name": "Neeraj Kulkarni",
        "role": "RESIDENT",
    },
    "dev-token-swati": {
        "email": "swati.joshi@example.com",
        "phone": "+91-98000-00002",
        "sub": "00000000-0000-0000-0000-000000000002",
        "name": "Swati Joshi",
        "role": "RESIDENT",
    },
    "dev-token-aamir": {
        "email": "aamir.shaikh@example.com",
        "phone": "+91-98000-00003",
        "sub": "00000000-0000-0000-0000-000000000003",
        "name": "Aamir Shaikh",
        "role": "RESIDENT",
    },
    "dev-token-helpdesk": {
        "email": "helpdesk@example.com",
        "phone": "+91-98000-00004",
        "sub": "00000000-0000-0000-0000-000000000004",
        "name": "Rajesh Shinde",
        "role": "HELPDESK",
    },
    "dev-token-helpdesk-2": {
        "email": "helpdesk2@example.com",
        "phone": "+91-98000-00005",
        "sub": "00000000-0000-0000-0000-000000000005",
        "name": "Priya Patel",
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
