"""Complaints Workload-Based Auto-Assignment Engine

Assigns newly triaged complaints to active helpdesk staff within the same society:
1. Filters staff with RoleType.HELPDESK and UserStatus.ACTIVE in the ticket's society_id.
2. Computes the current workload (open tickets in ASSIGNED or IN_PROGRESS status).
3. Selects the staff member with the lowest open ticket count.
4. Uses user ID as a deterministic tie-breaker.
5. Returns None if no active staff member is available in the society.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.complaints.models import Complaint, ComplaintStatus
from app.domains.identity.models import RoleType, User, UserRole, UserStatus


def find_least_loaded_staff(db: Session, society_id: uuid.UUID) -> uuid.UUID | None:
    """Finds the active helpdesk staff member with the minimum number of open tickets in the society."""
    # 1. Fetch all active helpdesk users in this society
    staff_stmt = (
        select(User.id)
        .join(UserRole, UserRole.user_id == User.id)
        .where(
            UserRole.society_id == society_id,
            UserRole.role == RoleType.HELPDESK,
            User.status == UserStatus.ACTIVE,
        )
        .order_by(User.id)
    )
    staff_result = db.execute(staff_stmt)
    staff_ids: Sequence[uuid.UUID] = staff_result.scalars().all()

    if not staff_ids:
        return None

    if len(staff_ids) == 1:
        return staff_ids[0]

    # 2. Count active complaints (ASSIGNED, IN_PROGRESS) per staff member
    active_statuses = [ComplaintStatus.ASSIGNED, ComplaintStatus.IN_PROGRESS]
    workload_stmt = (
        select(Complaint.assigned_to, func.count(Complaint.id).label("active_count"))
        .where(
            Complaint.society_id == society_id,
            Complaint.assigned_to.in_(staff_ids),
            Complaint.status.in_(active_statuses),
        )
        .group_by(Complaint.assigned_to)
    )
    workload_result = db.execute(workload_stmt)
    workload_map: dict[uuid.UUID, int] = {
        row[0]: row[1] for row in workload_result.all() if row[0] is not None
    }

    # 3. Find staff with minimum open count, deterministic tie-break by user.id
    best_staff = min(staff_ids, key=lambda sid: (workload_map.get(sid, 0), str(sid)))
    return best_staff
