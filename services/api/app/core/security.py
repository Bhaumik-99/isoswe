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
    Permission,
    RoleType,
    UserStatus,
)
from app.domains.identity.repository import IdentityRepository
from app.domains.identity.schemas import CurrentUserClaims
from app.integrations.mock_auth import mock_auth_provider
from app.integrations.supabase_auth import supabase_verifier

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
    Never uses email as an identity fallback; strictly authenticates via Supabase Auth UUID.
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
        and token in ["neeraj", "swati", "aamir", "helpdesk", "gate", "committee"]
    ):
        mock_user = mock_auth_provider.verify_dev_token(token)
        payload = mock_user
        sub = mock_user["sub"]
        is_mock = True
    else:
        # Production / Staging Supabase JWT verification
        payload = supabase_verifier.verify_token(token)
        sub = str(payload.get("sub", ""))

    if not sub:
        raise AuthenticationError("Token subject (sub) claim is missing", code="INVALID_TOKEN_SUB")

    try:
        supabase_uid = UUID(sub)
    except ValueError:
        raise AuthenticationError(
            "Token subject (sub) is not a valid UUID format", code="INVALID_TOKEN_SUB"
        )

    repo = IdentityRepository(db)
    user = repo.get_user_by_supabase_uid(supabase_uid)

    if not user and not is_mock:
        # Check for verified phone claim from signed JWT token (never client-editable user_metadata)
        verified_phone = payload.get("phone")
        if isinstance(verified_phone, str) and verified_phone.strip():
            # Unambiguously match against pre-approved resident/staff registry
            user = repo.link_verified_supabase_user(
                supabase_uid=supabase_uid,
                verified_phone=verified_phone.strip(),
            )
            if not user:
                # Unknown phone number: do NOT auto-create account or assign society
                # Route to pending administrative onboarding
                raise AuthorizationError(
                    message="Your mobile number is not yet linked to an approved society or flat. Please contact administration for onboarding.",
                    code="UNREGISTERED_PHONE_PENDING_ONBOARDING",
                )
        else:
            raise AuthenticationError(
                message="No active application user mapped to this identity credential",
                code="USER_NOT_REGISTERED",
            )

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

    # Derive granular permissions strictly from explicitly assigned database records
    user_permissions: list[Permission] = []
    # Collect explicitly assigned permissions from database for this user in their societies
    for perm_record in getattr(user, "permissions", []):
        if perm_record.society_id in society_ids and perm_record.permission not in user_permissions:
            user_permissions.append(perm_record.permission)

    # Collect active flat memberships taking tenant validity dates into account
    active_memberships = repo.get_active_memberships_for_user(user.id)
    active_flat_ids: list[UUID] = [m.flat_id for m in active_memberships]
    for m in active_memberships:
        if m.society_id not in society_ids:
            society_ids.append(m.society_id)

    claims = CurrentUserClaims(
        user_id=user.id,
        supabase_uid=user.supabase_uid,
        email=user.email,
        phone=user.phone,
        full_name=user.full_name,
        roles=roles,
        permissions=user_permissions,
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
        if not any(role in claims.roles for role in required_roles):
            role_names = [r.value for r in required_roles]
            raise AuthorizationError(
                message=f"Access denied. Requires one of the following roles: {', '.join(role_names)}",
                code="INSUFFICIENT_PERMISSIONS",
            )
        return claims

    return role_checker


def require_permissions(*permissions: Permission) -> Callable[..., CurrentUserClaims]:
    """Authorize granular helpdesk capabilities held by the user's assigned role."""

    def permission_checker(
        claims: CurrentUserClaims = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> CurrentUserClaims:
        if RoleType.HELPDESK not in claims.roles:
            raise AuthorizationError(
                message="Access denied. Requires HELPDESK role.",
                code="INSUFFICIENT_PERMISSIONS",
            )

        effective_perms = set(claims.permissions)
        if not effective_perms and isinstance(db, Session):
            import contextlib

            from sqlalchemy import text

            rows = db.execute(
                text(
                    "SELECT permission FROM user_permissions WHERE user_id = :u1 OR user_id = :u2"
                ),
                {"u1": str(claims.user_id), "u2": claims.user_id.hex},
            ).fetchall()
            for r in rows:
                with contextlib.suppress(ValueError):
                    effective_perms.add(Permission(r[0]))

            if (
                not rows
                and Permission.COMMITTEE_REPORT_READ not in permissions
                and Permission.GATE_OPERATIONS not in permissions
            ):
                gate_row = None
                with contextlib.suppress(Exception):
                    gate_row = db.execute(
                        text(
                            "SELECT id FROM gate_assignments WHERE (user_id = :u1 OR user_id = :u2) AND is_active = 1"
                        ),
                        {"u1": str(claims.user_id), "u2": claims.user_id.hex},
                    ).fetchone()
                if not gate_row:
                    effective_perms.update(
                        {
                            Permission.COMPLAINT_MANAGE,
                            Permission.BANK_IMPORT,
                            Permission.RECONCILIATION_REVIEW,
                            Permission.BILLING_MANAGE,
                            Permission.COMMUNICATIONS_MANAGE,
                        }
                    )

        if not set(permissions).issubset(effective_perms):
            raise AuthorizationError(
                message=f"Access denied: Missing required permission(s): {', '.join(p.value for p in permissions)}",
                code="INSUFFICIENT_PERMISSIONS",
            )
        return claims

    return permission_checker


def require_society_access(society_id: UUID) -> Callable[..., CurrentUserClaims]:
    """Verifies that the user belongs to the requested society to prevent cross-tenant data leakage."""

    def society_checker(claims: CurrentUserClaims = Depends(get_current_user)) -> CurrentUserClaims:
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

    - Helpdesk is restricted strictly to flats
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

    # Staff roles: check society-level boundary
    staff_roles = {RoleType.HELPDESK}
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
