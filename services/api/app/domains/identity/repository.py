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

    def get_user_by_phone(self, phone: str) -> User | None:
        """Finds user by phone number using normalized formats (E.164, raw 10 digits, hyphenated)."""
        clean = phone.strip().replace(" ", "").replace("-", "")
        digits = "".join(c for c in clean if c.isdigit())
        last_10 = digits[-10:] if len(digits) >= 10 else digits

        candidates = {
            phone.strip(),
            clean,
            f"+91{last_10}",
            last_10,
        }
        if len(last_10) == 10:
            candidates.add(f"+91-{last_10[:5]}-{last_10[5:]}")

        stmt = (
            select(User)
            .options(
                joinedload(User.roles).joinedload(UserRole.society),
                joinedload(User.memberships).joinedload(FlatMembership.flat),
            )
            .where(User.phone.in_(list(candidates)), User.status == UserStatus.ACTIVE)
        )
        found = self.db.scalars(stmt).unique().first()
        if found:
            return found

        # Fallback: match by trailing 10 digits across all active users with phones
        if len(last_10) >= 10:
            users_with_phone = (
                self.db.scalars(
                    select(User)
                    .options(
                        joinedload(User.roles).joinedload(UserRole.society),
                        joinedload(User.memberships).joinedload(FlatMembership.flat),
                    )
                    .where(User.phone.isnot(None), User.status == UserStatus.ACTIVE)
                )
                .unique()
                .all()
            )
            for u in users_with_phone:
                if u.phone:
                    u_digits = "".join(c for c in u.phone if c.isdigit())
                    if u_digits[-10:] == last_10:
                        return u

        return None

    def link_or_provision_supabase_user(
        self, supabase_uid: UUID, phone: str | None, full_name: str | None = None
    ) -> User | None:
        """Links an existing pre-seeded resident to their newly minted Supabase Auth UUID,
        or auto-provisions a new resident account so real OTP users can reliably access their flat."""
        if not phone:
            return None

        # 1. Match pre-seeded resident by phone number and link Supabase Auth UID
        existing_user = self.get_user_by_phone(phone)
        if existing_user:
            existing_user.supabase_uid = supabase_uid
            if full_name and (
                not existing_user.full_name or existing_user.full_name.startswith("Resident")
            ):
                existing_user.full_name = full_name
            self.db.add(existing_user)
            self.db.commit()
            return self.get_user_by_supabase_uid(supabase_uid)

        # 2. If no user exists, auto-provision new resident
        import uuid as _uuid

        from app.domains.identity.models import RoleType

        clean_phone = phone.strip()
        new_user = User(
            id=_uuid.uuid4(),
            supabase_uid=supabase_uid,
            phone=clean_phone,
            full_name=full_name or f"Resident {clean_phone[-4:] if len(clean_phone) >= 4 else ''}",
            status=UserStatus.ACTIVE,
        )
        self.db.add(new_user)
        self.db.flush()

        # Link default society if available
        first_society_id = self.db.scalar(select(Society.id).limit(1))
        if first_society_id:
            role = UserRole(
                id=_uuid.uuid4(),
                user_id=new_user.id,
                society_id=first_society_id,
                role=RoleType.RESIDENT,
            )
            self.db.add(role)

        self.db.commit()
        return self.get_user_by_supabase_uid(supabase_uid)

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
