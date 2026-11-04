"""Complaints SLA Rules & Breach Calculation

Enforces township operational level agreements based on ticket priority:
- CRITICAL: 5m first response, 2h resolution
- HIGH: 30m first response, 8h resolution
- MEDIUM: 4h first response, 48h resolution
- LOW: 12h first response, 120h (5 days) resolution

All deadlines are stored in UTC and evaluated against UTC timestamps.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.domains.complaints.models import Complaint, ComplaintPriority, ComplaintStatus


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class SLAPolicy:
    first_response_delta: timedelta
    resolution_delta: timedelta


SLA_POLICIES: dict[ComplaintPriority, SLAPolicy] = {
    ComplaintPriority.CRITICAL: SLAPolicy(
        first_response_delta=timedelta(minutes=5),
        resolution_delta=timedelta(hours=2),
    ),
    ComplaintPriority.HIGH: SLAPolicy(
        first_response_delta=timedelta(minutes=30),
        resolution_delta=timedelta(hours=8),
    ),
    ComplaintPriority.MEDIUM: SLAPolicy(
        first_response_delta=timedelta(hours=4),
        resolution_delta=timedelta(hours=48),
    ),
    ComplaintPriority.LOW: SLAPolicy(
        first_response_delta=timedelta(hours=12),
        resolution_delta=timedelta(days=5),
    ),
}


def calculate_sla_deadlines(
    priority: ComplaintPriority, created_at: datetime
) -> tuple[datetime, datetime]:
    """Calculates first response deadline and resolution deadline from creation time."""
    policy = SLA_POLICIES.get(priority, SLA_POLICIES[ComplaintPriority.MEDIUM])
    first_response_deadline = created_at + policy.first_response_delta
    resolution_deadline = created_at + policy.resolution_delta
    return first_response_deadline, resolution_deadline


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def is_sla_breached(complaint: Complaint, now: datetime | None = None) -> bool:
    """Evaluates whether a complaint has breached either its first response or resolution SLA."""
    current_time = _ensure_utc(now) or utc_now()

    # Cancelled tickets are exempt from SLA breach flags
    if complaint.status == ComplaintStatus.CANCELLED:
        return False

    fr_deadline = _ensure_utc(complaint.first_response_deadline)
    fr_at = _ensure_utc(complaint.first_response_at)
    res_deadline = _ensure_utc(complaint.resolution_deadline)
    res_at = _ensure_utc(complaint.resolved_at)

    # Check First Response SLA Breach
    if fr_deadline:
        if fr_at:
            if fr_at > fr_deadline:
                return True
        elif current_time > fr_deadline:
            return True

    # Check Resolution SLA Breach
    if res_deadline:
        if res_at:
            if res_at > res_deadline:
                return True
        elif (
            complaint.status not in (ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED)
            and current_time > res_deadline
        ):
            return True

    return False
