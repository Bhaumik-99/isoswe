"""Complaints Domain SQLAlchemy Repository

Provides authoritative data access and query optimization for:
- Complaints and lifecycle tracking
- Attachments metadata
- Public comments & internal helpdesk notes
- Activity audit trail
- Helpdesk operational metrics and SLA breach queries
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.domains.complaints.models import (
    Complaint,
    ComplaintActivity,
    ComplaintAttachment,
    ComplaintCategory,
    ComplaintComment,
    ComplaintPriority,
    ComplaintStatus,
)
from app.domains.identity.models import Flat, Tower, User


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def utc_now() -> datetime:
    return datetime.now(UTC)


class ComplaintRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def generate_complaint_number(self, society_id: UUID) -> str:
        """Generates a sequential human-readable complaint identifier: CMP-YYYYMM-XXXX."""
        now = utc_now()
        prefix = f"CMP-{now.strftime('%Y%m')}"

        # Count existing complaints for this society in this month
        count_stmt = select(func.count(Complaint.id)).where(
            Complaint.society_id == society_id,
            Complaint.complaint_number.like(f"{prefix}-%"),
        )
        current_count = self.db.execute(count_stmt).scalar() or 0
        seq = current_count + 1

        complaint_number = f"{prefix}-{seq:04d}"

        # If a collision exists (e.g., deleted or concurrent ticket), increment until unique
        check_stmt = select(Complaint.id).where(
            Complaint.society_id == society_id,
            Complaint.complaint_number == complaint_number,
        )
        while self.db.execute(check_stmt).scalar() is not None:
            seq += 1
            complaint_number = f"{prefix}-{seq:04d}"
            check_stmt = select(Complaint.id).where(
                Complaint.society_id == society_id,
                Complaint.complaint_number == complaint_number,
            )

        return complaint_number

    def create_complaint(self, complaint: Complaint) -> Complaint:
        self.db.add(complaint)
        self.db.flush()
        return complaint

    def get_complaint_by_id(self, complaint_id: UUID, society_id: UUID) -> Complaint | None:
        stmt = (
            select(Complaint)
            .where(Complaint.id == complaint_id, Complaint.society_id == society_id)
            .options(
                joinedload(Complaint.attachments),
                joinedload(Complaint.comments),
                joinedload(Complaint.activities),
            )
        )
        return self.db.execute(stmt).unique().scalar_one_or_none()

    def list_complaints(
        self,
        society_id: UUID,
        *,
        flat_ids: list[UUID] | None = None,
        created_by: UUID | None = None,
        assigned_to: UUID | None = None,
        unassigned_only: bool = False,
        statuses: list[ComplaintStatus] | None = None,
        priority: ComplaintPriority | None = None,
        category: ComplaintCategory | None = None,
        tower_id: UUID | None = None,
        search: str | None = None,
        is_sla_breached_only: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Complaint], int]:
        stmt = select(Complaint).where(Complaint.society_id == society_id)

        if flat_ids is not None:
            stmt = stmt.where(Complaint.flat_id.in_(flat_ids))

        if created_by is not None:
            stmt = stmt.where(Complaint.created_by == created_by)

        if unassigned_only:
            stmt = stmt.where(Complaint.assigned_to.is_(None))
        elif assigned_to is not None:
            stmt = stmt.where(Complaint.assigned_to == assigned_to)

        if statuses:
            stmt = stmt.where(Complaint.status.in_(statuses))

        if priority is not None:
            stmt = stmt.where(Complaint.priority == priority)

        if category is not None:
            stmt = stmt.where(Complaint.category == category)

        if tower_id is not None:
            stmt = stmt.join(Flat, Flat.id == Complaint.flat_id).where(Flat.tower_id == tower_id)

        if search:
            search_pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    Complaint.complaint_number.ilike(search_pattern),
                    Complaint.title.ilike(search_pattern),
                    Complaint.description.ilike(search_pattern),
                )
            )

        if is_sla_breached_only:
            now = utc_now()
            stmt = stmt.where(
                or_(
                    (Complaint.first_response_at.is_(None))
                    & (Complaint.first_response_deadline < now),
                    (Complaint.first_response_at.is_not(None))
                    & (Complaint.first_response_at > Complaint.first_response_deadline),
                    (Complaint.resolved_at.is_(None))
                    & (~Complaint.status.in_([ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED]))
                    & (Complaint.resolution_deadline < now),
                    (Complaint.resolved_at.is_not(None))
                    & (Complaint.resolved_at > Complaint.resolution_deadline),
                )
            )

        # Count query
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_count = self.db.execute(count_stmt).scalar() or 0

        # Eagerly load attachments, comments, activities and paginate
        stmt = (
            stmt.options(
                joinedload(Complaint.attachments),
                joinedload(Complaint.comments),
                joinedload(Complaint.activities),
            )
            .order_by(Complaint.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        complaints = list(self.db.execute(stmt).unique().scalars().all())
        return complaints, total_count

    def get_active_complaints_for_society(
        self, society_id: UUID, limit: int = 150
    ) -> list[Complaint]:
        """Fetches active complaints in the society for duplicate checking."""
        stmt = (
            select(Complaint)
            .where(
                Complaint.society_id == society_id,
                Complaint.status.not_in([ComplaintStatus.CLOSED, ComplaintStatus.CANCELLED]),
            )
            .order_by(Complaint.created_at.desc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    def add_attachment(self, attachment: ComplaintAttachment) -> ComplaintAttachment:
        self.db.add(attachment)
        self.db.flush()
        return attachment

    def get_attachment_by_id(
        self, attachment_id: UUID, society_id: UUID
    ) -> ComplaintAttachment | None:
        stmt = select(ComplaintAttachment).where(
            ComplaintAttachment.id == attachment_id,
            ComplaintAttachment.society_id == society_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def add_comment(self, comment: ComplaintComment) -> ComplaintComment:
        self.db.add(comment)
        self.db.flush()
        return comment

    def add_activity(self, activity: ComplaintActivity) -> ComplaintActivity:
        self.db.add(activity)
        self.db.flush()
        return activity

    def get_flat_with_tower(self, flat_id: UUID, society_id: UUID) -> tuple[Flat, Tower] | None:
        stmt = (
            select(Flat, Tower)
            .join(Tower, Tower.id == Flat.tower_id)
            .where(Flat.id == flat_id, Flat.society_id == society_id)
        )
        result = self.db.execute(stmt).first()
        if not result:
            return None
        return result[0], result[1]

    def get_users_by_ids(self, user_ids: list[UUID]) -> dict[UUID, User]:
        if not user_ids:
            return {}
        stmt = select(User).where(User.id.in_(user_ids))
        users = self.db.execute(stmt).scalars().all()
        return {u.id: u for u in users}

    def get_dashboard_metrics(self, society_id: UUID) -> dict[str, Any]:
        """Aggregates operational KPI metrics for helpdesk staff."""
        now = utc_now()

        # Total complaints
        total_stmt = select(func.count(Complaint.id)).where(Complaint.society_id == society_id)
        total_complaints = self.db.execute(total_stmt).scalar() or 0

        # Unassigned count (assigned_to is NULL and not closed/cancelled)
        unassigned_stmt = select(func.count(Complaint.id)).where(
            Complaint.society_id == society_id,
            Complaint.assigned_to.is_(None),
            Complaint.status.not_in([ComplaintStatus.CLOSED, ComplaintStatus.CANCELLED]),
        )
        unassigned_count = self.db.execute(unassigned_stmt).scalar() or 0

        # In-Progress count
        in_progress_stmt = select(func.count(Complaint.id)).where(
            Complaint.society_id == society_id,
            Complaint.status == ComplaintStatus.IN_PROGRESS,
        )
        in_progress_count = self.db.execute(in_progress_stmt).scalar() or 0

        # Critical active count
        critical_stmt = select(func.count(Complaint.id)).where(
            Complaint.society_id == society_id,
            Complaint.priority == ComplaintPriority.CRITICAL,
            Complaint.status.not_in(
                [ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED, ComplaintStatus.CANCELLED]
            ),
        )
        critical_count = self.db.execute(critical_stmt).scalar() or 0

        # Resolved count
        resolved_stmt = select(func.count(Complaint.id)).where(
            Complaint.society_id == society_id,
            Complaint.status.in_([ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED]),
        )
        resolved_count = self.db.execute(resolved_stmt).scalar() or 0

        # Overdue / SLA breached count
        overdue_stmt = select(func.count(Complaint.id)).where(
            Complaint.society_id == society_id,
            Complaint.status.not_in([ComplaintStatus.CLOSED, ComplaintStatus.CANCELLED]),
            or_(
                (Complaint.first_response_at.is_(None)) & (Complaint.first_response_deadline < now),
                (Complaint.first_response_at.is_not(None))
                & (Complaint.first_response_at > Complaint.first_response_deadline),
                (Complaint.resolved_at.is_(None))
                & (~Complaint.status.in_([ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED]))
                & (Complaint.resolution_deadline < now),
                (Complaint.resolved_at.is_not(None))
                & (Complaint.resolved_at > Complaint.resolution_deadline),
            ),
        )
        overdue_count = self.db.execute(overdue_stmt).scalar() or 0

        # Calculate average first response minutes and resolution minutes
        # We query the responded and resolved complaints to compute averages
        avg_fr_stmt = select(
            Complaint.created_at,
            Complaint.first_response_at,
        ).where(
            Complaint.society_id == society_id,
            Complaint.first_response_at.is_not(None),
        )
        fr_rows = self.db.execute(avg_fr_stmt).all()
        if fr_rows:
            total_fr_seconds = 0.0
            for row in fr_rows:
                if row[0] and row[1]:
                    t0 = _ensure_utc(row[0])
                    t1 = _ensure_utc(row[1])
                    if t0 and t1:
                        total_fr_seconds += max(0.0, (t1 - t0).total_seconds())
            avg_fr_minutes = round((total_fr_seconds / len(fr_rows)) / 60.0, 1)
        else:
            avg_fr_minutes = 0.0

        avg_res_stmt = select(
            Complaint.created_at,
            Complaint.resolved_at,
        ).where(
            Complaint.society_id == society_id,
            Complaint.resolved_at.is_not(None),
        )
        res_rows = self.db.execute(avg_res_stmt).all()
        if res_rows:
            total_res_seconds = 0.0
            for row in res_rows:
                if row[0] and row[1]:
                    t0 = _ensure_utc(row[0])
                    t1 = _ensure_utc(row[1])
                    if t0 and t1:
                        total_res_seconds += max(0.0, (t1 - t0).total_seconds())
            avg_res_minutes = round((total_res_seconds / len(res_rows)) / 60.0, 1)
        else:
            avg_res_minutes = 0.0

        resolution_rate = (
            round((resolved_count / total_complaints) * 100.0, 1) if total_complaints > 0 else 100.0
        )

        return {
            "total_complaints": total_complaints,
            "unassigned_count": unassigned_count,
            "in_progress_count": in_progress_count,
            "critical_count": critical_count,
            "overdue_count": overdue_count,
            "resolved_count": resolved_count,
            "average_first_response_minutes": avg_fr_minutes,
            "average_resolution_minutes": avg_res_minutes,
            "resolution_rate_percentage": resolution_rate,
        }
