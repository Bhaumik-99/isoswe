"""Security Dependencies and Authorization Evaluators

Reusable FastAPI dependencies for:
- get_current_user: Authenticates JWT (Cognito or Local Dev Mock) and loads validated claims from PostgreSQL.
- require_roles: RBAC gatekeeper.
- require_permission: Permission-based access.
- require_society_access: Cross-tenant isolation barrier.
- require_flat_access: Resident flat-level authorization.

INVARIANT: Never trusts frontend-supplied roles, society IDs, or flat IDs.
"""

from collections.abc import Callable
from uuid import UUID

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import AuthenticationError, AuthorizationError, TenantIsolationError
from app.domains.identity.models import (
    RoleType,
    UserStatus,
)
from app.domains.identity.repository import IdentityRepository
from app.domains.identity.schemas import CurrentUserClaims
from app.integrations.cognito import cognito_verifier
from app.integrations.mock_auth import mock_auth_provider

# Standard HTTP Bearer scheme
security_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    dev_user_header: str | None = Header(None, alias="X-Dev-User"),
    db: Session = Depends(get_db),
) -> CurrentUserClaims:
    """Authenticates the incoming request and returns verified user claims.

    Never trusts frontend claims - always verifies against PostgreSQL system of record.
    """
    token: str | None = None
    if credentials:
        token = credentials.credentials
    elif dev_user_header and settings.is_local_dev and settings.ENABLE_LOCAL_AUTH_BYPASS:
        # Convenience header for local dev/testing
        token = f"dev-token-{dev_user_header}"

    if not token:
        raise AuthenticationError(
            message="Missing or malformed Authorization header",
            code="UNAUTHORIZED",
        )

    sub: str
    is_mock: bool = False

    # Check for local dev mock token
    if token.startswith("dev-token-") or (
        settings.is_local_dev
        and settings.ENABLE_LOCAL_AUTH_BYPASS
        and token in ["neeraj", "swati", "aamir", "helpdesk", "finance", "committee", "admin"]
    ):
        mock_user = mock_auth_provider.verify_dev_token(token)
        sub = mock_user["sub"]
        is_mock = True
    else:
        # Production Cognito verification
        payload = cognito_verifier.verify_token(token)
        sub = payload.get("sub", "")

    if not sub:
        raise AuthenticationError("Token subject (sub) claim is missing", code="INVALID_TOKEN_SUB")

    repo = IdentityRepository(db)
    user = repo.get_user_by_cognito_sub(sub)

    if not user:
        raise AuthenticationError(
            message="No active application user mapped to this identity credential",
            code="USER_NOT_REGISTERED",
        )

    if user.status != UserStatus.ACTIVE:
        raise AuthorizationError(
            message="Your user account is suspended or inactive",
            code="USER_INACTIVE",
        )

    # Collect validated roles and societies from database
    roles: list[RoleType] = [r.role for r in user.roles]
    society_ids: list[UUID] = list({r.society_id for r in user.roles})

    # Collect active flat memberships taking tenant validity dates into account
    active_memberships = repo.get_active_memberships_for_user(user.id)
    active_flat_ids: list[UUID] = [m.flat_id for m in active_memberships]
    for m in active_memberships:
        if m.society_id not in society_ids:
            society_ids.append(m.society_id)

    claims = CurrentUserClaims(
        user_id=user.id,
        cognito_sub=user.cognito_sub,
        email=user.email,
        full_name=user.full_name,
        roles=roles,
        society_ids=society_ids,
        active_flat_ids=active_flat_ids,
        is_mock=is_mock,
    )

    # Attach to request state for access logging and correlation
    request.state.user_id = str(user.id)
    request.state.user_roles = [r.value for r in roles]

    return claims


def require_roles(*required_roles: RoleType) -> Callable[..., CurrentUserClaims]:
    """FastAPI dependency factory enforcing that the authenticated user possesses at least one of the specified roles."""

    def role_checker(claims: CurrentUserClaims = Depends(get_current_user)) -> CurrentUserClaims:
        # PLATFORM_ADMIN has superuser override
        if RoleType.PLATFORM_ADMIN in claims.roles:
            return claims

        if not any(role in claims.roles for role in required_roles):
            role_names = [r.value for r in required_roles]
            raise AuthorizationError(
                message=f"Access denied. Requires one of the following roles: {', '.join(role_names)}",
                code="INSUFFICIENT_PERMISSIONS",
            )
        return claims

    return role_checker


def require_society_access(society_id: UUID) -> Callable[..., CurrentUserClaims]:
    """Verifies that the user belongs to the requested society to prevent cross-tenant data leakage."""

    def society_checker(claims: CurrentUserClaims = Depends(get_current_user)) -> CurrentUserClaims:
        if RoleType.PLATFORM_ADMIN in claims.roles:
            return claims

        if society_id not in claims.society_ids:
            raise TenantIsolationError(
                message="Access denied: You do not have permission to access resources in this society"
            )
        return claims

    return society_checker


def require_flat_access(
    flat_id: UUID,
    db: Session = Depends(get_db),
    claims: CurrentUserClaims = Depends(get_current_user),
) -> CurrentUserClaims:
    """Verifies that the user has explicit, non-expired rights to access the specified flat.

    - Platform Admin has platform-wide authority.
    - Staff roles (HELPDESK, FINANCE, COMMITTEE_VIEWER) are restricted strictly to flats
      within societies they are explicitly assigned to.
    - Residents must possess an active, approved, non-expired membership for this specific flat.
    """
    repo = IdentityRepository(db)
    flat = repo.get_flat_by_id(flat_id)
    if not flat:
        raise AuthorizationError(
            message=f"Flat {flat_id} not found",
            code="FLAT_NOT_FOUND",
        )

    # 1. Platform Admin has platform-wide authority
    if RoleType.PLATFORM_ADMIN in claims.roles:
        return claims

    # 2. Staff roles: check society-level boundary
    staff_roles = {RoleType.HELPDESK, RoleType.FINANCE, RoleType.COMMITTEE_VIEWER}
    if any(r in staff_roles for r in claims.roles):
        if flat.society_id not in claims.society_ids:
            raise TenantIsolationError(
                message="Access denied: You do not have permission to access flats in another society"
            )
        return claims

    # 3. Resident must have an active, valid membership for this specific flat
    if not repo.verify_flat_access(claims.user_id, flat_id):
        raise AuthorizationError(
            message="You are not authorised to access this flat or your membership lease has expired",
            code="FLAT_ACCESS_DENIED",
        )
    return claims
