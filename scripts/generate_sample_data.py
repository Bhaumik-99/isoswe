"""Sample Data Generator Utility

Generates target-scale synthetic data sets for load and scale testing:
Populates 28 residential towers, 2,400 apartments, and 180 facility management staff
for the Pune township operations platform.
"""

import sys
import uuid

sys.path.insert(0, "services/api")
sys.path.insert(0, ".")

from app.core.database import SessionLocal
from app.core.logging import logger
from app.domains.identity.models import (
    Flat,
    FlatStatus,
    Permission,
    RoleType,
    Society,
    Tower,
    User,
    UserPermission,
    UserRole,
    UserStatus,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scripts.seed import SOCIETY_PUNE_ID


def _populate_scale_data(
    db: Session,
    num_towers: int = 28,
    total_flats: int = 2400,
    total_staff: int = 180,
) -> dict[str, int]:
    """Idempotently populates target-scale towers, flats, and staff in bulk."""
    society = db.get(Society, SOCIETY_PUNE_ID)
    if not society:
        logger.error("Society not found. Please run seed.py first.")
        return {"towers": 0, "flats": 0, "staff": 0}

    # 1. Ensure all 28 Towers exist (T01 .. T28)
    existing_towers = {
        t.tower_number: t
        for t in db.scalars(
            select(Tower).where(Tower.society_id == SOCIETY_PUNE_ID)
        ).all()
    }
    towers_by_idx: dict[int, Tower] = {}
    new_towers: list[Tower] = []

    for t_idx in range(1, num_towers + 1):
        t_num = f"T{t_idx:02d}"
        if t_num in existing_towers:
            towers_by_idx[t_idx] = existing_towers[t_num]
        else:
            tower = Tower(
                id=uuid.uuid5(SOCIETY_PUNE_ID, f"tower-{t_num}"),
                society_id=SOCIETY_PUNE_ID,
                tower_number=t_num,
                name=f"Tower {t_idx}",
            )
            new_towers.append(tower)
            towers_by_idx[t_idx] = tower

    if new_towers:
        db.add_all(new_towers)
        db.flush()

    # 2. Distribute `total_flats` across `num_towers` towers
    # E.g. 2400 // 28 = 85 flats base, first (2400 % 28 = 20) towers get 86 flats
    base_flats_per_tower = total_flats // num_towers
    extra_flats = total_flats % num_towers

    existing_flats_by_tower: dict[uuid.UUID, set[str]] = {
        t.id: set() for t in towers_by_idx.values()
    }
    for tower_id, flat_num in db.execute(
        select(Flat.tower_id, Flat.flat_number).where(
            Flat.society_id == SOCIETY_PUNE_ID
        )
    ).all():
        if tower_id in existing_flats_by_tower:
            existing_flats_by_tower[tower_id].add(flat_num)

    new_flats: list[Flat] = []
    for t_idx in range(1, num_towers + 1):
        tower = towers_by_idx[t_idx]
        target_for_tower = base_flats_per_tower + (1 if t_idx <= extra_flats else 0)
        existing_set = existing_flats_by_tower.get(tower.id, set())
        needed = max(0, target_for_tower - len(existing_set))

        candidate_num = 101
        created_for_tower = 0
        while created_for_tower < needed:
            f_num = (
                f"{candidate_num:04d}" if candidate_num < 1000 else f"{candidate_num}"
            )
            if f_num not in existing_set and str(candidate_num) not in existing_set:
                flat = Flat(
                    id=uuid.uuid5(tower.id, f"flat-{f_num}"),
                    society_id=SOCIETY_PUNE_ID,
                    tower_id=tower.id,
                    flat_number=f_num,
                    area_sqft=1100 + (candidate_num % 4) * 150,
                    status=(
                        FlatStatus.OCCUPIED
                        if candidate_num % 10 != 0
                        else FlatStatus.VACANT
                    ),
                )
                new_flats.append(flat)
                existing_set.add(f_num)
                created_for_tower += 1
            candidate_num += 1

    if new_flats:
        db.add_all(new_flats)
        db.flush()

    # 3. Ensure `total_staff` HELPDESK staff accounts exist for the society
    existing_staff_count = (
        db.scalar(
            select(func.count(UserRole.id)).where(
                UserRole.society_id == SOCIETY_PUNE_ID,
                UserRole.role == RoleType.HELPDESK,
            )
        )
        or 0
    )
    staff_needed = max(0, total_staff - existing_staff_count)
    new_users: list[User] = []
    new_roles: list[UserRole] = []
    new_perms: list[UserPermission] = []

    staff_idx = 1
    created_staff = 0
    operational_perms = [
        Permission.COMPLAINT_MANAGE,
        Permission.BANK_IMPORT,
        Permission.RECONCILIATION_REVIEW,
        Permission.BILLING_MANAGE,
    ]
    while created_staff < staff_needed:
        email = f"staff.{staff_idx:03d}@example.com"
        phone = f"+91-98111-{staff_idx:05d}"
        user_id = uuid.uuid5(SOCIETY_PUNE_ID, f"staff-user-{staff_idx:03d}")
        supa_id = uuid.uuid5(SOCIETY_PUNE_ID, f"staff-supa-{staff_idx:03d}")

        if not db.get(User, user_id):
            user = User(
                id=user_id,
                supabase_uid=supa_id,
                email=email,
                phone=phone,
                full_name=f"Facility Staff {staff_idx:03d}",
                status=UserStatus.ACTIVE,
            )
            new_users.append(user)
            new_roles.append(
                UserRole(
                    id=uuid.uuid5(SOCIETY_PUNE_ID, f"staff-role-{staff_idx:03d}"),
                    user_id=user_id,
                    society_id=SOCIETY_PUNE_ID,
                    role=RoleType.HELPDESK,
                )
            )
            for perm in operational_perms:
                new_perms.append(
                    UserPermission(
                        id=uuid.uuid5(
                            SOCIETY_PUNE_ID, f"staff-perm-{staff_idx:03d}-{perm.value}"
                        ),
                        user_id=user_id,
                        society_id=SOCIETY_PUNE_ID,
                        permission=perm,
                    )
                )
            created_staff += 1
        staff_idx += 1

    if new_users:
        db.add_all(new_users)
        db.flush()
    if new_roles:
        db.add_all(new_roles)
        db.flush()
    if new_perms:
        db.add_all(new_perms)
        db.flush()

    db.commit()

    final_towers = (
        db.scalar(
            select(func.count(Tower.id)).where(Tower.society_id == SOCIETY_PUNE_ID)
        )
        or 0
    )
    final_flats = (
        db.scalar(select(func.count(Flat.id)).where(Flat.society_id == SOCIETY_PUNE_ID))
        or 0
    )
    final_staff = (
        db.scalar(
            select(func.count(UserRole.id)).where(
                UserRole.society_id == SOCIETY_PUNE_ID,
                UserRole.role == RoleType.HELPDESK,
            )
        )
        or 0
    )
    logger.info(
        f"Target scale dataset active: {final_towers} towers, {final_flats} flats, {final_staff} staff."
    )
    return {"towers": final_towers, "flats": final_flats, "staff": final_staff}


def generate_extended_sample_data(
    num_towers: int = 28,
    flats_per_tower: int | None = None,
    total_flats: int = 2400,
    total_staff: int = 180,
    db: Session | None = None,
) -> dict[str, int]:
    """Generates target-scale towers, flats, and staff for scaling tests."""
    resolved_total_flats = (
        num_towers * flats_per_tower if flats_per_tower is not None else total_flats
    )
    if db is not None:
        return _populate_scale_data(
            db=db,
            num_towers=num_towers,
            total_flats=resolved_total_flats,
            total_staff=total_staff,
        )

    with SessionLocal() as session:
        return _populate_scale_data(
            db=session,
            num_towers=num_towers,
            total_flats=resolved_total_flats,
            total_staff=total_staff,
        )


if __name__ == "__main__":
    generate_extended_sample_data()
