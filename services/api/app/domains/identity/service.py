"""Identity Domain Service

Implements core domain rules and access evaluation independent of web/HTTP mechanics.
"""

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import AuthorizationError, ResourceNotFoundError, TenantIsolationError
from app.domains.identity.models import (
    RoleType,
)
from app.domains.identity.repository import IdentityRepository
from app.domains.identity.schemas import (
    CurrentUserClaims,
    FlatDetailSchema,
    FlatMembershipSchema,
    MeResponse,
    UserProfileSchema,
    UserRoleSchema,
)
from app.domains.reliability.models import AuditEvent


class IdentityService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = IdentityRepository(db)

    def get_me_profile(self, user_id: UUID) -> MeResponse:
        user = self.repo.get_user_by_id(user_id)
        if not user:
            raise ResourceNotFoundError(message=f"User {user_id} not found", code="USER_NOT_FOUND")

        valid_memberships = self.repo.get_active_memberships_for_user(user_id)

        user_profile = UserProfileSchema(
            id=user.id,
            cognito_sub=user.cognito_sub,
            email=user.email,
            phone=user.phone,
            full_name=user.full_name,
            status=user.status,
            created_at=user.created_at,
        )

        roles_schemas = [
            UserRoleSchema(id=r.id, society_id=r.society_id, role=r.role) for r in user.roles
        ]

        memberships_schemas = [
            FlatMembershipSchema(
                id=m.id,
                society_id=m.society_id,
                flat_id=m.flat_id,
                user_id=m.user_id,
                membership_type=m.membership_type,
                valid_from=m.valid_from,
                valid_until=m.valid_until,
                is_primary=m.is_primary,
                status=m.status,
                flat_number=m.flat.flat_number if m.flat else None,
                tower_number=m.flat.tower.tower_number if m.flat and m.flat.tower else None,
            )
            for m in valid_memberships
        ]

        return MeResponse(
            user=user_profile,
            roles=roles_schemas,
            memberships=memberships_schemas,
        )

    def get_flat_for_resident(self, flat_id: UUID, claims: CurrentUserClaims) -> FlatDetailSchema:
        """Retrieves flat details after strictly verifying authorization for the requesting user."""
        flat = self.repo.get_flat_by_id(flat_id)
        if not flat:
            raise ResourceNotFoundError(message=f"Flat {flat_id} not found", code="FLAT_NOT_FOUND")

        # Platform Admin and Society Staff (Helpdesk, Finance, Committee) can access flats within their society
        is_staff_or_admin = any(
            role
            in [
                RoleType.PLATFORM_ADMIN,
                RoleType.HELPDESK,
                RoleType.FINANCE,
                RoleType.COMMITTEE_VIEWER,
            ]
            for role in claims.roles
        )

        if is_staff_or_admin:
            # Check society boundary
            if (
                claims.society_ids
                and flat.society_id not in claims.society_ids
                and RoleType.PLATFORM_ADMIN not in claims.roles
            ):
                raise TenantIsolationError("Access to flat in a different society is denied")
        else:
            # For residents: must have active approved membership for this specific flat
            has_access = self.repo.verify_flat_access(claims.user_id, flat_id)
            if not has_access:
                raise AuthorizationError(
                    message="You are not authorised to access this flat or your membership has expired",
                    code="FLAT_ACCESS_DENIED",
                )

        return FlatDetailSchema(
            id=flat.id,
            society_id=flat.society_id,
            tower_id=flat.tower_id,
            flat_number=flat.flat_number,
            area_sqft=flat.area_sqft,
            status=flat.status,
            tower_name=flat.tower.name if flat.tower else None,
            tower_number=flat.tower.tower_number if flat.tower else None,
            society_name=flat.society.name if flat.society else None,
        )

    def record_audit(
        self,
        action: str,
        resource_type: str,
        resource_id: str,
        correlation_id: str,
        actor_id: UUID | None = None,
        society_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            society_id=society_id,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            correlation_id=correlation_id,
            event_metadata=metadata or {},
        )
        self.db.add(event)
        return event
