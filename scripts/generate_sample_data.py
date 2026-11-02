"""Sample Data Generator Utility

Generates larger synthetic data sets for load testing:
Can populate up to 28 residential towers and 2,400 flats for Pune township scale testing.
"""

import sys
import uuid
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, "services/api")

from sqlalchemy import select
from app.core.database import SessionLocal
from app.core.logging import logger
from app.domains.identity.models import Flat, FlatStatus, Society, Tower
from scripts.seed import SOCIETY_PUNE_ID


def generate_extended_sample_data(num_towers: int = 5, flats_per_tower: int = 20) -> None:
    """Generates additional towers and flats for scaling tests."""
    with SessionLocal() as db:
        society = db.get(Society, SOCIETY_PUNE_ID)
        if not society:
            logger.error("Society not found. Please run seed.py first.")
            return

        for t_idx in range(1, num_towers + 1):
            t_num = f"T{t_idx:02d}"
            # Check existing
            stmt = select(Tower).where(Tower.society_id == SOCIETY_PUNE_ID, Tower.tower_number == t_num)
            tower = db.scalars(stmt).first()
            if not tower:
                tower = Tower(
                    society_id=SOCIETY_PUNE_ID,
                    tower_number=t_num,
                    name=f"Tower {t_idx}",
                )
                db.add(tower)
                db.flush()

            for f_idx in range(101, 101 + flats_per_tower):
                f_num = f"{f_idx}"
                f_stmt = select(Flat).where(Flat.tower_id == tower.id, Flat.flat_number == f_num)
                existing_flat = db.scalars(f_stmt).first()
                if not existing_flat:
                    flat = Flat(
                        society_id=SOCIETY_PUNE_ID,
                        tower_id=tower.id,
                        flat_number=f_num,
                        area_sqft=1100 + (f_idx % 4) * 150,
                        status=FlatStatus.OCCUPIED if f_idx % 5 != 0 else FlatStatus.VACANT,
                    )
                    db.add(flat)

        db.commit()
        logger.info(f"Generated {num_towers} towers and {flats_per_tower} flats per tower.")


if __name__ == "__main__":
    generate_extended_sample_data(num_towers=5, flats_per_tower=20)
