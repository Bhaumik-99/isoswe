"""Identity Domain SQLAlchemy Models

Models for Societies, Towers, Flats, Users, Flat Memberships, and User Roles.
Enforces multi-tenant isolation, relationship integrity, check constraints, and unique indexes.
"""

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class UserStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"


class SocietyStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    ONBOARDING = "ONBOARDING"
    SUSPENDED = "SUSPENDED"


class FlatStatus(str, enum.Enum):
    OCCUPIED = "OCCUPIED"
    VACANT = "VACANT"
    UNDER_MAINTENANCE = "UNDER_MAINTENANCE"


class MembershipType(str, enum.Enum):
    OWNER = "OWNER"
    TENANT = "TENANT"
    FAMILY_MEMBER = "FAMILY_MEMBER"


class MembershipStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    TERMINATED = "TERMINATED"


class RoleType(str, enum.Enum):
    RESIDENT = "RESIDENT"
    HELPDESK = "HELPDESK"
    FINANCE = "FINANCE"
    COMMITTEE_VIEWER = "COMMITTEE_VIEWER"
    PLATFORM_ADMIN = "PLATFORM_ADMIN"


class Society(Base):
    __tablename__ = "societies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Kolkata")
    preferred_currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    status: Mapped[SocietyStatus] = mapped_column(
        SAEnum(SocietyStatus, native_enum=False), nullable=False, default=SocietyStatus.ACTIVE
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    # Relationships
    towers: Mapped[list["Tower"]] = relationship(
        "Tower", back_populates="society", cascade="all, delete-orphan"
    )
    flats: Mapped[list["Flat"]] = relationship(
        "Flat", back_populates="society", cascade="all, delete-orphan"
    )
    user_roles: Mapped[list["UserRole"]] = relationship("UserRole", back_populates="society")


class Tower(Base):
    __tablename__ = "towers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tower_number: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("society_id", "tower_number", name="uq_tower_society_number"),
    )

    # Relationships
    society: Mapped["Society"] = relationship("Society", back_populates="towers")
    flats: Mapped[list["Flat"]] = relationship(
        "Flat", back_populates="tower", cascade="all, delete-orphan"
    )


class Flat(Base):
    __tablename__ = "flats"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tower_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("towers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    flat_number: Mapped[str] = mapped_column(String(32), nullable=False)
    area_sqft: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[FlatStatus] = mapped_column(
        SAEnum(FlatStatus, native_enum=False), nullable=False, default=FlatStatus.OCCUPIED
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tower_id", "flat_number", name="uq_flat_tower_number"),
        Index("ix_flat_society_number", "society_id", "flat_number"),
    )

    # Relationships
    society: Mapped["Society"] = relationship("Society", back_populates="flats")
    tower: Mapped["Tower"] = relationship("Tower", back_populates="flats")
    memberships: Mapped[list["FlatMembership"]] = relationship(
        "FlatMembership", back_populates="flat", cascade="all, delete-orphan"
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cognito_sub: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    status: Mapped[UserStatus] = mapped_column(
        SAEnum(UserStatus, native_enum=False), nullable=False, default=UserStatus.ACTIVE
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    # Relationships
    roles: Mapped[list["UserRole"]] = relationship(
        "UserRole", back_populates="user", cascade="all, delete-orphan"
    )
    memberships: Mapped[list["FlatMembership"]] = relationship(
        "FlatMembership", back_populates="user", cascade="all, delete-orphan"
    )


class FlatMembership(Base):
    __tablename__ = "flat_memberships"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    flat_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("flats.id", ondelete="CASCADE"), nullable=False, index=True
    )
    membership_type: Mapped[MembershipType] = mapped_column(
        SAEnum(MembershipType, native_enum=False), nullable=False
    )
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[MembershipStatus] = mapped_column(
        SAEnum(MembershipStatus, native_enum=False),
        nullable=False,
        default=MembershipStatus.APPROVED,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "valid_until IS NULL OR valid_until >= valid_from",
            name="ck_membership_valid_dates",
        ),
        Index("ix_membership_user_active", "user_id", "status"),
        Index("ix_membership_flat_user", "flat_id", "user_id"),
    )

    # Relationships
    flat: Mapped["Flat"] = relationship("Flat", back_populates="memberships")
    user: Mapped["User"] = relationship("User", back_populates="memberships")


class UserRole(Base):
    __tablename__ = "user_roles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[RoleType] = mapped_column(SAEnum(RoleType, native_enum=False), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", "society_id", "role", name="uq_user_society_role"),
        Index("ix_user_roles_lookup", "user_id", "role"),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="roles")
    society: Mapped["Society"] = relationship("Society", back_populates="user_roles")
