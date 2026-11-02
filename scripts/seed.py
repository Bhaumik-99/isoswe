"""Idempotent Synthetic Seed Data Script

Populates the Pune township operations database with:
- 1 Society (Marvel Greenfield Residences, Pune)
- 3 Towers (T07, T12, T21)
- 3 Required Flats (T07-1203, T12-0408, T21-1601)
- Residents: Neeraj Kulkarni (Owner), Swati Joshi (Tenant), Aamir Shaikh (Owner)
- Staff: Helpdesk (Rajesh Shinde), Finance (Priya Deshmukh), Committee (Aniket Patwardhan), Admin (Vikram Joshi)

INVARIANT: Idempotent execution. Running multiple times produces no duplicates.
"""

import sys
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

# Ensure services/api is on sys.path
sys.path.insert(0, "services/api")

from sqlalchemy import select
from app.core.database import SessionLocal
from app.core.logging import logger
from app.domains.identity.models import (
    Flat,
    FlatMembership,
    FlatStatus,
    MembershipStatus,
    MembershipType,
    RoleType,
    Society,
    SocietyStatus,
    Tower,
    User,
    UserRole,
    UserStatus,
)

# Fixed deterministic UUIDs for seed records so they are easily referenceable in tests
SOCIETY_PUNE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
TOWER_T07_ID = uuid.UUID("22222222-2222-2222-2222-222222222207")
TOWER_T12_ID = uuid.UUID("22222222-2222-2222-2222-222222222212")
TOWER_T21_ID = uuid.UUID("22222222-2222-2222-2222-222222222221")

FLAT_1203_ID = uuid.UUID("33333333-3333-3333-3333-333333331203")
FLAT_0408_ID = uuid.UUID("33333333-3333-3333-3333-333333330408")
FLAT_1601_ID = uuid.UUID("33333333-3333-3333-3333-333333331601")

USER_NEERAJ_ID = uuid.UUID("44444444-4444-4444-4444-444444440001")
USER_SWATI_ID = uuid.UUID("44444444-4444-4444-4444-444444440002")
USER_AAMIR_ID = uuid.UUID("44444444-4444-4444-4444-444444440003")
USER_HELPDESK_ID = uuid.UUID("44444444-4444-4444-4444-444444440004")
USER_FINANCE_ID = uuid.UUID("44444444-4444-4444-4444-444444440005")
USER_COMMITTEE_ID = uuid.UUID("44444444-4444-4444-4444-444444440006")
USER_ADMIN_ID = uuid.UUID("44444444-4444-4444-4444-444444440007")


def seed_database() -> None:
    now = datetime.now(timezone.utc)
    one_year_later = now + timedelta(days=365)

    with SessionLocal() as db:
        logger.info("Starting idempotent database seed for Marvel Greenfield Residences, Pune...")

        # 1. Society
        society = db.get(Society, SOCIETY_PUNE_ID)
        if not society:
            society = Society(
                id=SOCIETY_PUNE_ID,
                name="Marvel Greenfield Residences",
                timezone="Asia/Kolkata",
                preferred_currency="INR",
                status=SocietyStatus.ACTIVE,
            )
            db.add(society)
            db.flush()
            logger.info("Created Society: Marvel Greenfield Residences")

        # 2. Towers
        towers_data = [
            (TOWER_T07_ID, "T07", "Tower 7"),
            (TOWER_T12_ID, "T12", "Tower 12"),
            (TOWER_T21_ID, "T21", "Tower 21"),
        ]
        for t_id, t_num, t_name in towers_data:
            tower = db.get(Tower, t_id)
            if not tower:
                tower = Tower(
                    id=t_id,
                    society_id=SOCIETY_PUNE_ID,
                    tower_number=t_num,
                    name=t_name,
                )
                db.add(tower)
                db.flush()
                logger.info(f"Created Tower: {t_name} ({t_num})")

        # 3. Flats
        flats_data = [
            (FLAT_1203_ID, TOWER_T07_ID, "1203", 1150, FlatStatus.OCCUPIED),
            (FLAT_0408_ID, TOWER_T12_ID, "0408", 980, FlatStatus.OCCUPIED),
            (FLAT_1601_ID, TOWER_T21_ID, "1601", 1640, FlatStatus.OCCUPIED),
        ]
        for f_id, tow_id, f_num, area, f_status in flats_data:
            flat = db.get(Flat, f_id)
            if not flat:
                flat = Flat(
                    id=f_id,
                    society_id=SOCIETY_PUNE_ID,
                    tower_id=tow_id,
                    flat_number=f_num,
                    area_sqft=area,
                    status=f_status,
                )
                db.add(flat)
                db.flush()
                logger.info(f"Created Flat: {f_num} (Area: {area} sq ft)")

        # 4. Users
        users_data = [
            (
                USER_NEERAJ_ID,
                "mock-sub-neeraj-kulkarni",
                "neeraj.kulkarni@example.com",
                "+91-98000-00001",
                "Neeraj Kulkarni",
                RoleType.RESIDENT,
            ),
            (
                USER_SWATI_ID,
                "mock-sub-swati-joshi",
                "swati.joshi@example.com",
                "+91-98000-00002",
                "Swati Joshi",
                RoleType.RESIDENT,
            ),
            (
                USER_AAMIR_ID,
                "mock-sub-aamir-shaikh",
                "aamir.shaikh@example.com",
                "+91-98000-00003",
                "Aamir Shaikh",
                RoleType.RESIDENT,
            ),
            (
                USER_HELPDESK_ID,
                "mock-sub-helpdesk-shinde",
                "helpdesk@example.com",
                "+91-98000-00004",
                "Rajesh Shinde",
                RoleType.HELPDESK,
            ),
            (
                USER_FINANCE_ID,
                "mock-sub-finance-deshmukh",
                "finance@example.com",
                "+91-98000-00005",
                "Priya Deshmukh",
                RoleType.FINANCE,
            ),
            (
                USER_COMMITTEE_ID,
                "mock-sub-committee-patwardhan",
                "committee@example.com",
                "+91-98000-00006",
                "Aniket Patwardhan",
                RoleType.COMMITTEE_VIEWER,
            ),
            (
                USER_ADMIN_ID,
                "mock-sub-admin-joshi",
                "admin@example.com",
                "+91-98000-00007",
                "Vikram Joshi",
                RoleType.PLATFORM_ADMIN,
            ),
        ]

        for u_id, sub, email, phone, name, primary_role in users_data:
            user = db.get(User, u_id)
            if not user:
                user = User(
                    id=u_id,
                    cognito_sub=sub,
                    email=email,
                    phone=phone,
                    full_name=name,
                    status=UserStatus.ACTIVE,
                )
                db.add(user)
                db.flush()
                logger.info(f"Created User: {name} ({email})")

            # Assign Role
            role_stmt = select(UserRole).where(
                UserRole.user_id == u_id,
                UserRole.society_id == SOCIETY_PUNE_ID,
                UserRole.role == primary_role,
            )
            existing_role = db.scalars(role_stmt).first()
            if not existing_role:
                new_role = UserRole(
                    user_id=u_id,
                    society_id=SOCIETY_PUNE_ID,
                    role=primary_role,
                )
                db.add(new_role)
                db.flush()
                logger.info(f"Assigned role {primary_role.value} to {name}")

        # 5. Flat Memberships
        memberships_data = [
            (
                uuid.UUID("55555555-5555-5555-5555-555555550001"),
                USER_NEERAJ_ID,
                FLAT_1203_ID,
                MembershipType.OWNER,
                now - timedelta(days=180),
                None,  # Owner has no expiry
                True,
            ),
            (
                uuid.UUID("55555555-5555-5555-5555-555555550002"),
                USER_SWATI_ID,
                FLAT_0408_ID,
                MembershipType.TENANT,
                now - timedelta(days=60),
                one_year_later,  # Tenant active lease
                True,
            ),
            (
                uuid.UUID("55555555-5555-5555-5555-555555550003"),
                USER_AAMIR_ID,
                FLAT_1601_ID,
                MembershipType.OWNER,
                now - timedelta(days=365),
                None,  # Owner has no expiry
                True,
            ),
        ]

        for m_id, u_id, f_id, m_type, v_from, v_until, is_pri in memberships_data:
            membership = db.get(FlatMembership, m_id)
            if not membership:
                membership = FlatMembership(
                    id=m_id,
                    society_id=SOCIETY_PUNE_ID,
                    user_id=u_id,
                    flat_id=f_id,
                    membership_type=m_type,
                    valid_from=v_from,
                    valid_until=v_until,
                    is_primary=is_pri,
                    status=MembershipStatus.APPROVED,
                )
                db.add(membership)
                db.flush()
                logger.info(f"Assigned {m_type.value} membership for user {u_id} to flat {f_id}")

        db.commit()
        logger.info("Seed data successfully committed without errors.")


if __name__ == "__main__":
    seed_database()
