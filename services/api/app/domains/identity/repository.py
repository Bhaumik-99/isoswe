"""Identity Repository

Performs optimized database queries with eager loading and explicit tenant boundaries.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.domains.identity.models import (
    Flat,
    FlatMembership,
    MembershipStatus,
    MembershipType,
    Society,
    User,
    UserRole,
    UserStatus,
)


def ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


class IdentityRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_user_by_supabase_uid(self, supabase_uid: UUID) -> User | None:
        stmt = (
            select(User)
            .options(
                joinedload(User.roles).joinedload(UserRole.society),
                joinedload(User.memberships).joinedload(FlatMembership.flat),
            )
            .where(User.supabase_uid == supabase_uid, User.status == UserStatus.ACTIVE)
        )
        return self.db.scalars(stmt).unique().first()

    def get_user_by_id(self, user_id: UUID) -> User | None:
        stmt = (
            select(User)
            .options(
                joinedload(User.roles),
                joinedload(User.memberships).joinedload(FlatMembership.flat).joinedload(Flat.tower),
            )
            .where(User.id == user_id)
        )
        return self.db.scalars(stmt).unique().first()

    def get_user_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        return self.db.scalars(stmt).first()

    def get_society_by_id(self, society_id: UUID) -> Society | None:
        stmt = select(Society).where(Society.id == society_id)
        return self.db.scalars(stmt).first()

    def get_flat_by_id(self, flat_id: UUID) -> Flat | None:
        stmt = (
            select(Flat)
            .options(joinedload(Flat.tower), joinedload(Flat.society))
            .where(Flat.id == flat_id)
        )
        return self.db.scalars(stmt).first()

    def get_active_memberships_for_user(self, user_id: UUID) -> list[FlatMembership]:
        """Returns all valid, approved memberships for a user taking into account tenant lease dates."""
        now = datetime.now(UTC)
        stmt = (
            select(FlatMembership)
            .options(
                joinedload(FlatMembership.flat).joinedload(Flat.tower),
                joinedload(FlatMembership.flat).joinedload(Flat.society),
            )
            .where(
                FlatMembership.user_id == user_id,
                FlatMembership.status == MembershipStatus.APPROVED,
            )
        )
        memberships = list(self.db.scalars(stmt).unique().all())
        # Filter tenant memberships whose valid_until is expired or valid_from is in future
        valid_memberships: list[FlatMembership] = []
        for m in memberships:
            valid_from = ensure_utc(m.valid_from)
            if valid_from and valid_from > now:
                continue

            if m.membership_type == MembershipType.TENANT and m.valid_until is not None:
                valid_until = ensure_utc(m.valid_until)
                if valid_until and valid_until < now:
                    continue
            valid_memberships.append(m)
        return valid_memberships

    def verify_flat_access(self, user_id: UUID, flat_id: UUID) -> bool:
        """Determines if the given user is authorised to access flat-level resident data."""
        now = datetime.now(UTC)
        stmt = select(FlatMembership).where(
            FlatMembership.user_id == user_id,
            FlatMembership.flat_id == flat_id,
            FlatMembership.status == MembershipStatus.APPROVED,
        )
        memberships = self.db.scalars(stmt).all()
        for m in memberships:
            valid_from = ensure_utc(m.valid_from)
            if valid_from and valid_from > now:
                continue

            # Check tenant lease window
            if m.membership_type == MembershipType.TENANT and m.valid_until is not None:
                valid_until = ensure_utc(m.valid_until)
                if valid_until and valid_until < now:
                    continue
            return True
        return False
