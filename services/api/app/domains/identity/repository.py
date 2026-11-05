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
    Tower,
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


def normalize_phone_e164(phone: str) -> str:
    """Normalizes phone numbers to standard E.164 international format (+91XXXXXXXXXX)."""
    cleaned = phone.strip().replace(" ", "").replace("-", "")
    if not cleaned:
        return ""
    if cleaned.startswith("+"):
        return cleaned
    digits = "".join(c for c in cleaned if c.isdigit())
    if len(digits) == 10:
        return f"+91{digits}"
    if len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}"
    return f"+{digits}" if digits else ""


class IdentityRepository:
    def __init__(self, db: Session) -> None:
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
        """Finds user by phone number using exact normalized E.164 matching.

        Ambiguous partial or trailing-digit fallbacks are strictly prohibited to prevent
        cross-identity account hijacking across different international dial codes.
        """
        if not phone or not phone.strip():
            return None

        clean = phone.strip()
        e164 = normalize_phone_e164(clean)

        candidates = {clean}
        if e164:
            candidates.add(e164)
            digits = "".join(c for c in e164 if c.isdigit())
            if len(digits) == 12 and digits.startswith("91"):
                ten_digits = digits[2:]
                candidates.add(ten_digits)
                candidates.add(f"+91-{ten_digits[:5]}-{ten_digits[5:]}")

        stmt = (
            select(User)
            .options(
                joinedload(User.roles).joinedload(UserRole.society),
                joinedload(User.memberships).joinedload(FlatMembership.flat),
            )
            .where(User.phone.in_(list(candidates)), User.status == UserStatus.ACTIVE)
        )
        return self.db.scalars(stmt).unique().first()

    def link_verified_supabase_user(
        self, supabase_uid: UUID, verified_phone: str, full_name: str | None = None
    ) -> User | None:
        """Links an existing pre-approved resident or staff member to their verified Supabase Auth UUID.

        Strictly enforces:
        1. Exact match against pre-approved resident/staff registry using verified phone claim.
        2. Unknown numbers are NEVER auto-provisioned or assigned a society/role here.
        3. Returns None if phone is unregistered, triggering pending onboarding (HTTP 403).
        """
        if not verified_phone:
            return None

        existing_user = self.get_user_by_phone(verified_phone)
        if not existing_user:
            return None

        # Unambiguous match found in pre-approved registry: link Supabase Auth UUID
        existing_user.supabase_uid = supabase_uid
        if full_name and (
            not existing_user.full_name or existing_user.full_name.startswith("Resident")
        ):
            existing_user.full_name = full_name
        self.db.add(existing_user)
        self.db.commit()
        return self.get_user_by_supabase_uid(supabase_uid)

    def link_or_provision_supabase_user(
        self, supabase_uid: UUID, phone: str | None, full_name: str | None = None
    ) -> User | None:
        """Deprecated compatibility alias for link_verified_supabase_user."""
        if not phone:
            return None
        return self.link_verified_supabase_user(
            supabase_uid=supabase_uid, verified_phone=phone, full_name=full_name
        )

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

    def list_residents_in_society(
        self,
        society_id: UUID,
        query: str | None = None,
        tower_id: UUID | None = None,
        flat_number: str | None = None,
        status: MembershipStatus | None = None,
    ) -> list[User]:
        """Queries residents belonging to a society with their memberships and flats eagerly loaded."""
        stmt = (
            select(User)
            .join(FlatMembership, FlatMembership.user_id == User.id)
            .join(Flat, Flat.id == FlatMembership.flat_id)
            .join(Tower, Tower.id == Flat.tower_id)
            .options(
                joinedload(User.memberships).joinedload(FlatMembership.flat).joinedload(Flat.tower)
            )
            .where(FlatMembership.society_id == society_id)
        )
        if status:
            stmt = stmt.where(FlatMembership.status == status)
        if tower_id:
            stmt = stmt.where(Flat.tower_id == tower_id)
        if flat_number:
            stmt = stmt.where(Flat.flat_number.ilike(f"%{flat_number.strip()}%"))
        if query:
            q = f"%{query.strip()}%"
            stmt = stmt.where(
                (User.full_name.ilike(q)) | (User.phone.ilike(q)) | (User.email.ilike(q))
            )

        return list(self.db.scalars(stmt).unique().all())

    def list_memberships(
        self,
        society_id: UUID,
        status: MembershipStatus | None = None,
        flat_id: UUID | None = None,
        user_id: UUID | None = None,
    ) -> list[FlatMembership]:
        stmt = (
            select(FlatMembership)
            .options(
                joinedload(FlatMembership.user),
                joinedload(FlatMembership.flat).joinedload(Flat.tower),
            )
            .where(FlatMembership.society_id == society_id)
        )
        if status:
            stmt = stmt.where(FlatMembership.status == status)
        if flat_id:
            stmt = stmt.where(FlatMembership.flat_id == flat_id)
        if user_id:
            stmt = stmt.where(FlatMembership.user_id == user_id)
        stmt = stmt.order_by(FlatMembership.created_at.desc())
        return list(self.db.scalars(stmt).unique().all())

    def get_membership_by_id(self, membership_id: UUID) -> FlatMembership | None:
        stmt = (
            select(FlatMembership)
            .options(
                joinedload(FlatMembership.user),
                joinedload(FlatMembership.flat).joinedload(Flat.tower),
            )
            .where(FlatMembership.id == membership_id)
        )
        return self.db.scalars(stmt).first()
