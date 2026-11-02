"""Identity Domain Pydantic v2 Schemas

Defines strong contract models for user identity, flats, societies, and session claims.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.domains.identity.models import (
    FlatStatus,
    MembershipStatus,
    MembershipType,
    Permission,
    RoleType,
    SocietyStatus,
    UserStatus,
)


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SocietySchema(BaseSchema):
    id: UUID
    name: str
    timezone: str
    preferred_currency: str
    status: SocietyStatus


class TowerSchema(BaseSchema):
    id: UUID
    society_id: UUID
    tower_number: str
    name: str


class FlatSchema(BaseSchema):
    id: UUID
    society_id: UUID
    tower_id: UUID
    flat_number: str
    area_sqft: int
    status: FlatStatus


class FlatDetailSchema(FlatSchema):
    tower_name: str | None = None
    tower_number: str | None = None
    society_name: str | None = None


class FlatMembershipSchema(BaseSchema):
    id: UUID
    society_id: UUID
    flat_id: UUID
    user_id: UUID
    membership_type: MembershipType
    valid_from: datetime
    valid_until: datetime | None = None
    is_primary: bool
    status: MembershipStatus
    flat_number: str | None = None
    tower_number: str | None = None


class UserRoleSchema(BaseSchema):
    id: UUID
    society_id: UUID
    role: RoleType


class UserProfileSchema(BaseSchema):
    id: UUID
    cognito_sub: str
    email: EmailStr
    phone: str | None = None
    full_name: str
    status: UserStatus
    created_at: datetime


class CurrentUserClaims(BaseModel):
    """Internal security context representing authenticated actor."""

    user_id: UUID
    cognito_sub: str
    email: str
    full_name: str
    roles: list[RoleType] = Field(default_factory=list)
    permissions: list[Permission] = Field(default_factory=list)
    society_ids: list[UUID] = Field(default_factory=list)
    active_flat_ids: list[UUID] = Field(default_factory=list)
    is_mock: bool = False


class MeResponse(BaseModel):
    """GET /api/v1/me response payload."""

    user: UserProfileSchema
    roles: list[UserRoleSchema]
    memberships: list[FlatMembershipSchema]
