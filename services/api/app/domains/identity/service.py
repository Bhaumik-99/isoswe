"""Identity Domain Service

Implements core domain rules and access evaluation independent of web/HTTP mechanics.
"""

import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import (
    AuthorizationError,
    ResourceNotFoundError,
    TenantIsolationError,
    ValidationError,
)
from app.domains.identity.models import (
    FlatMembership,
    MembershipStatus,
    MembershipType,
    RoleType,
    User,
    UserRole,
    UserStatus,
)
from app.domains.identity.repository import IdentityRepository
from app.domains.identity.schemas import (
    CreateMembershipRequest,
    CurrentUserClaims,
    FlatDetailSchema,
    FlatMembershipSchema,
    MeResponse,
    ResidentDirectoryItem,
    ResidentFlatInfo,
    ResidentJoinFlatRequest,
    UpdateMembershipStatusRequest,
    UserProfileSchema,
    UserRoleSchema,
)
from app.domains.reliability.models import AuditEvent


class IdentityService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = IdentityRepository(db)

    def get_me_profile(self, user_id: UUID) -> MeResponse:
        user = self.repo.get_user_by_id(user_id)
        if not user:
            raise ResourceNotFoundError(message=f"User {user_id} not found", code="USER_NOT_FOUND")

        valid_memberships = self.repo.get_active_memberships_for_user(user_id)

        user_profile = UserProfileSchema(
            id=user.id,
            supabase_uid=user.supabase_uid,
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

        # Society helpdesk and committee members can access flats within assigned society
        is_staff_or_admin = any(
            role
            in [
                RoleType.HELPDESK,
                RoleType.COMMITTEE,
            ]
            for role in claims.roles
        )

        if is_staff_or_admin:
            # Check society boundary
            if claims.society_ids and flat.society_id not in claims.society_ids:
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

    # =========================================================================
    # Phase 5 Registry & Membership Management
    # =========================================================================

    def search_residents(
        self,
        claims: CurrentUserClaims,
        society_id: UUID,
        query: str | None = None,
        tower_id: UUID | None = None,
        flat_number: str | None = None,
        status: MembershipStatus | None = None,
        membership_type: MembershipType | None = None,
    ) -> list[ResidentDirectoryItem]:
        if society_id not in claims.society_ids:
            raise TenantIsolationError(f"Access denied to society {society_id}")

        users = self.repo.list_residents_in_society(
            society_id=society_id,
            query=query,
            tower_id=tower_id,
            flat_number=flat_number,
            status=status,
            membership_type=membership_type,
        )
        items: list[ResidentDirectoryItem] = []
        for u in users:
            flat_infos: list[ResidentFlatInfo] = []
            for m in u.memberships:
                if m.society_id == society_id:
                    if membership_type and m.membership_type != membership_type:
                        continue
                    if status and m.status != status:
                        continue
                    flat_infos.append(
                        ResidentFlatInfo(
                            membership_id=m.id,
                            flat_id=m.flat_id,
                            flat_number=m.flat.flat_number if m.flat else "",
                            tower_number=(
                                m.flat.tower.tower_number if m.flat and m.flat.tower else ""
                            ),
                            membership_type=m.membership_type,
                            status=m.status,
                            membership_status=m.status,
                            valid_from=m.valid_from,
                            valid_until=m.valid_until,
                            is_primary=m.is_primary,
                        )
                    )
            items.append(
                ResidentDirectoryItem(
                    user_id=u.id,
                    full_name=u.full_name,
                    phone=u.phone,
                    email=u.email,
                    status=u.status,
                    user_status=u.status,
                    flats=flat_infos,
                    created_at=u.created_at,
                )
            )
        return items

    def list_memberships(
        self,
        claims: CurrentUserClaims,
        society_id: UUID,
        status: MembershipStatus | None = None,
        flat_id: UUID | None = None,
    ) -> list[FlatMembershipSchema]:
        if society_id not in claims.society_ids:
            raise TenantIsolationError(f"Access denied to society {society_id}")

        memberships = self.repo.list_memberships(
            society_id=society_id,
            status=status,
            flat_id=flat_id,
        )
        return [
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
            for m in memberships
        ]

    def create_membership(
        self,
        claims: CurrentUserClaims,
        society_id: UUID,
        req: CreateMembershipRequest,
    ) -> FlatMembershipSchema:
        if society_id not in claims.society_ids:
            raise TenantIsolationError(f"Access denied to society {society_id}")
        if RoleType.HELPDESK not in claims.roles:
            raise AuthorizationError("Only helpdesk staff can register memberships directly")

        # Lease validation: if valid_until is provided, ensure valid_until >= valid_from
        v_from = req.valid_from or datetime.now(UTC)
        v_until = req.valid_until
        if v_until and v_until < v_from:
            raise ValidationError(
                "Lease end date (valid_until) cannot be before start date (valid_from)"
            )

        # Verify flat belongs to society
        flat = self.repo.get_flat_by_id(req.flat_id)
        if not flat or flat.society_id != society_id:
            raise ResourceNotFoundError(f"Flat {req.flat_id} not found in society {society_id}")

        try:
            # Find or create user by phone
            clean_phone = req.phone.strip()
            user = self.repo.get_user_by_phone(clean_phone)
            if not user:
                user = User(
                    id=uuid.uuid4(),
                    supabase_uid=uuid.uuid4(),
                    phone=clean_phone,
                    full_name=req.full_name or f"Resident {clean_phone[-4:]}",
                    status=UserStatus.ACTIVE,
                )
                self.db.add(user)
                self.db.flush()

            existing = (
                self.db.query(FlatMembership)
                .filter(FlatMembership.flat_id == flat.id, FlatMembership.user_id == user.id)
                .first()
            )
            if existing:
                existing.membership_type = req.membership_type
                existing.valid_from = v_from
                existing.valid_until = v_until
                existing.is_primary = req.is_primary
                existing.status = MembershipStatus.APPROVED
                m = existing
            else:
                m = FlatMembership(
                    id=uuid.uuid4(),
                    society_id=society_id,
                    flat_id=flat.id,
                    user_id=user.id,
                    membership_type=req.membership_type,
                    valid_from=v_from,
                    valid_until=v_until,
                    is_primary=req.is_primary,
                    status=MembershipStatus.APPROVED,
                )
                self.db.add(m)
            self.db.flush()

            has_role = (
                self.db.query(UserRole)
                .filter(
                    UserRole.user_id == user.id,
                    UserRole.society_id == society_id,
                    UserRole.role == RoleType.RESIDENT,
                )
                .first()
            )
            if not has_role:
                self.db.add(
                    UserRole(
                        id=uuid.uuid4(),
                        user_id=user.id,
                        society_id=society_id,
                        role=RoleType.RESIDENT,
                    )
                )

            self.record_audit(
                action="identity.membership.created",
                resource_type="flat_membership",
                resource_id=str(m.id),
                correlation_id=str(uuid.uuid4()),
                actor_id=claims.user_id,
                society_id=society_id,
                metadata={
                    "flat_id": str(flat.id),
                    "user_id": str(user.id),
                    "membership_type": m.membership_type.value,
                    "status": m.status.value,
                },
            )
            self.db.commit()
            self.db.refresh(m)
        except Exception:
            self.db.rollback()
            raise

        return FlatMembershipSchema(
            id=m.id,
            society_id=m.society_id,
            flat_id=m.flat_id,
            user_id=m.user_id,
            membership_type=m.membership_type,
            valid_from=m.valid_from,
            valid_until=m.valid_until,
            is_primary=m.is_primary,
            status=m.status,
            flat_number=flat.flat_number,
            tower_number=flat.tower.tower_number if flat.tower else None,
        )

    def update_membership_status(
        self,
        claims: CurrentUserClaims,
        membership_id: UUID,
        req: UpdateMembershipStatusRequest,
    ) -> FlatMembershipSchema:
        m = self.repo.get_membership_by_id(membership_id)
        if not m:
            raise ResourceNotFoundError(f"Membership {membership_id} not found")
        if m.society_id not in claims.society_ids:
            raise TenantIsolationError("Access denied to membership in different society")
        if RoleType.HELPDESK not in claims.roles:
            raise AuthorizationError("Only helpdesk staff can update membership status")

        try:
            prev_status = m.status
            m.status = req.status
            notes = req.notes or req.rejection_reason
            self.record_audit(
                action=f"identity.membership.{req.status.value.lower()}",
                resource_type="flat_membership",
                resource_id=str(m.id),
                correlation_id=str(uuid.uuid4()),
                actor_id=claims.user_id,
                society_id=m.society_id,
                metadata={
                    "previous_status": prev_status.value,
                    "new_status": req.status.value,
                    "notes": notes,
                },
            )
            self.db.commit()
            self.db.refresh(m)
        except Exception:
            self.db.rollback()
            raise

        return FlatMembershipSchema(
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

    def request_join_flat(
        self,
        claims: CurrentUserClaims,
        req: ResidentJoinFlatRequest,
    ) -> FlatMembershipSchema:
        flat = self.repo.get_flat_by_id(req.flat_id)
        if not flat:
            raise ResourceNotFoundError(f"Flat {req.flat_id} not found")
        if flat.society_id not in claims.society_ids:
            raise TenantIsolationError("Flat belongs to a society you are not authorized to join")

        v_from = req.valid_from or datetime.now(UTC)
        v_until = req.valid_until
        if v_until and v_until < v_from:
            raise ValidationError("Lease end date cannot be before start date")

        existing = (
            self.db.query(FlatMembership)
            .filter(FlatMembership.flat_id == flat.id, FlatMembership.user_id == claims.user_id)
            .first()
        )
        if existing and existing.status in (MembershipStatus.APPROVED, MembershipStatus.PENDING):
            raise ValidationError(
                f"You already have an active or pending membership for this flat ({existing.status.value})"
            )

        try:
            m = FlatMembership(
                id=uuid.uuid4(),
                society_id=flat.society_id,
                flat_id=flat.id,
                user_id=claims.user_id,
                membership_type=req.membership_type,
                valid_from=v_from,
                valid_until=v_until,
                is_primary=False,
                status=MembershipStatus.PENDING,
            )
            self.db.add(m)
            self.db.flush()

            self.record_audit(
                action="identity.membership.join_requested",
                resource_type="flat_membership",
                resource_id=str(m.id),
                correlation_id=str(uuid.uuid4()),
                actor_id=claims.user_id,
                society_id=flat.society_id,
                metadata={
                    "flat_id": str(flat.id),
                    "membership_type": req.membership_type.value,
                    "status": m.status.value,
                },
            )
            self.db.commit()
            self.db.refresh(m)
        except Exception:
            self.db.rollback()
            raise

        return FlatMembershipSchema(
            id=m.id,
            society_id=m.society_id,
            flat_id=m.flat_id,
            user_id=m.user_id,
            membership_type=m.membership_type,
            valid_from=m.valid_from,
            valid_until=m.valid_until,
            is_primary=m.is_primary,
            status=m.status,
            flat_number=flat.flat_number,
            tower_number=flat.tower.tower_number if flat.tower else None,
        )
