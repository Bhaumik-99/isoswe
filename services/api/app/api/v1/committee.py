"""Committee Dashboard & Governance Reporting API Endpoints

Provides read-only committee reporting backed by SQL database aggregates across all 2,400 flats:
1. Committee Overview:
   - High-level financial KPIs (Billed, Collected, Outstanding, Collection %)
   - Ageing buckets (0-30, 31-60, 61-90, 90+ days)
   - Operational complaint statistics (Open, In Progress, Resolved, SLA Breached, Reopened, Safety Alerts)
   - Tower-by-tower financial & complaint breakdown
2. Monthly Financial Statements:
   - Historical month-by-month financial summary
3. CSV Report Export:
   - Neutralizes formula injection vulnerabilities (CWE-1236)
"""

import csv
import io
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AuthorizationError
from app.core.security import require_permissions
from app.domains.billing.models import (
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentAllocation,
    PaymentStatus,
)
from app.domains.complaints.models import Complaint, ComplaintStatus
from app.domains.identity.models import Flat, Permission, Society, Tower
from app.domains.identity.schemas import CurrentUserClaims
from app.domains.reconciliation.normalizer import sanitize_for_csv_export

router = APIRouter(prefix="/committee", tags=["Committee Governance"])


def _resolve_society_id(claims: CurrentUserClaims, query_society_id: UUID | None) -> UUID:
    if not claims.society_ids:
        raise AuthorizationError("User is not assigned to any society")
    if query_society_id:
        if query_society_id not in claims.society_ids:
            raise AuthorizationError(f"Access denied to society {query_society_id}")
        return query_society_id
    return claims.society_ids[0]


class AgeingBuckets(BaseModel):
    bucket_0_30_paise: int = 0
    bucket_31_60_paise: int = 0
    bucket_61_90_paise: int = 0
    bucket_90_plus_paise: int = 0


class FinancialSummary(BaseModel):
    total_billed_paise: int
    total_collected_paise: int
    total_outstanding_paise: int
    total_overdue_paise: int
    collection_percentage: float
    ageing: AgeingBuckets


class ComplaintSummary(BaseModel):
    total_complaints: int
    open_complaints: int
    in_progress_complaints: int
    resolved_complaints: int
    closed_complaints: int
    safety_escalated_count: int
    sla_breached_count: int
    first_response_sla_breached_count: int = 0
    reopened_count: int
    avg_resolution_hours: float
    median_resolution_hours: float = 0.0
    avg_first_response_hours: float = 0.0
    median_first_response_hours: float = 0.0


class TowerFinancialMetric(BaseModel):
    tower_id: UUID
    tower_number: str
    tower_name: str
    total_flats: int
    total_billed_paise: int
    total_collected_paise: int
    total_outstanding_paise: int
    open_complaints: int


class CommitteeOverviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    society_id: UUID
    society_name: str
    as_of_date: datetime
    financials: FinancialSummary
    complaints: ComplaintSummary
    towers: list[TowerFinancialMetric]


class MonthlyReportItem(BaseModel):
    billing_period: str
    total_invoices: int
    total_billed_paise: int
    total_collected_paise: int
    total_outstanding_paise: int
    collection_percentage: float


@router.get(
    "/overview",
    response_model=CommitteeOverviewResponse,
    summary="Get live database aggregates and governance metrics for committee review",
)
def get_committee_overview(
    claims: Annotated[
        CurrentUserClaims, Depends(require_permissions(Permission.COMMITTEE_REPORT_READ))
    ],
    society_id: UUID | None = Query(None),
    db: Session = Depends(get_db),
) -> CommitteeOverviewResponse:
    target_soc = _resolve_society_id(claims, society_id)
    society = db.query(Society).filter(Society.id == target_soc).first()
    society_name = society.name if society else "Township"

    now = datetime.now(UTC)

    # 1. Total Billed Paise across all invoices in society (zero limit)
    billed_stmt = select(func.coalesce(func.sum(Invoice.total_paise), 0)).where(
        Invoice.society_id == target_soc
    )
    total_billed_paise = int(db.scalar(billed_stmt) or 0)

    # 2. Total Collected Paise from successful payments
    collected_stmt = (
        select(func.coalesce(func.sum(PaymentAllocation.allocated_paise), 0))
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .where(Payment.society_id == target_soc, Payment.status == PaymentStatus.SUCCESS)
    )
    total_collected_paise = int(db.scalar(collected_stmt) or 0)
    total_outstanding_paise = max(0, total_billed_paise - total_collected_paise)

    # 3. Ageing Buckets calculation (0-30, 31-60, 61-90, 90+ days overdue)
    # Query all unpaid or partially paid invoices with their successful allocations
    unpaid_inv_stmt = (
        select(
            Invoice.id,
            Invoice.due_date,
            Invoice.total_paise,
            func.coalesce(func.sum(PaymentAllocation.allocated_paise), 0).label("allocated"),
        )
        .outerjoin(
            PaymentAllocation,
            (PaymentAllocation.invoice_id == Invoice.id)
            & (
                PaymentAllocation.payment_id.in_(
                    select(Payment.id).where(Payment.status == PaymentStatus.SUCCESS)
                )
            ),
        )
        .where(
            Invoice.society_id == target_soc,
            Invoice.status.in_(
                [InvoiceStatus.UNPAID, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE]
            ),
        )
        .group_by(Invoice.id, Invoice.due_date, Invoice.total_paise)
    )
    unpaid_rows = db.execute(unpaid_inv_stmt).all()

    b_0_30 = 0
    b_31_60 = 0
    b_61_90 = 0
    b_90_plus = 0
    total_overdue = 0

    for row in unpaid_rows:
        inv_total = int(row.total_paise or 0)
        inv_alloc = int(row.allocated or 0)
        remaining = max(0, inv_total - inv_alloc)
        if remaining <= 0:
            continue

        due_date = row.due_date
        if due_date.tzinfo is None:
            due_date = due_date.replace(tzinfo=UTC)

        if due_date >= now:
            b_0_30 += remaining
        else:
            days_overdue = (now.date() - due_date.date()).days
            total_overdue += remaining
            if days_overdue <= 30:
                b_0_30 += remaining
            elif days_overdue <= 60:
                b_31_60 += remaining
            elif days_overdue <= 90:
                b_61_90 += remaining
            else:
                b_90_plus += remaining

    collection_pct = (
        round((total_collected_paise / total_billed_paise) * 100.0, 2)
        if total_billed_paise > 0
        else 100.0
    )

    financials = FinancialSummary(
        total_billed_paise=total_billed_paise,
        total_collected_paise=total_collected_paise,
        total_outstanding_paise=total_outstanding_paise,
        total_overdue_paise=total_overdue,
        collection_percentage=collection_pct,
        ageing=AgeingBuckets(
            bucket_0_30_paise=b_0_30,
            bucket_31_60_paise=b_31_60,
            bucket_61_90_paise=b_61_90,
            bucket_90_plus_paise=b_90_plus,
        ),
    )

    # 4. Complaint Governance Aggregates
    status_counts_stmt = (
        select(Complaint.status, func.count(Complaint.id))
        .where(Complaint.society_id == target_soc)
        .group_by(Complaint.status)
    )
    status_map: dict[ComplaintStatus, int] = {
        row[0]: row[1] for row in db.execute(status_counts_stmt).all()
    }
    total_complaints = sum(status_map.values())
    open_c = (
        status_map.get(ComplaintStatus.SUBMITTED, 0)
        + status_map.get(ComplaintStatus.TRIAGED, 0)
        + status_map.get(ComplaintStatus.ASSIGNED, 0)
    )
    in_prog_c = status_map.get(ComplaintStatus.IN_PROGRESS, 0) + status_map.get(
        ComplaintStatus.AWAITING_RESIDENT, 0
    )
    resolved_c = status_map.get(ComplaintStatus.RESOLVED, 0)
    closed_c = status_map.get(ComplaintStatus.CLOSED, 0)

    safety_count = (
        db.scalar(
            select(func.count(Complaint.id)).where(
                Complaint.society_id == target_soc,
                Complaint.safety_escalated == True,  # noqa: E712
            )
        )
        or 0
    )

    sla_breached_count = (
        db.scalar(
            select(func.count(Complaint.id)).where(
                Complaint.society_id == target_soc,
                Complaint.status.notin_(
                    [ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED, ComplaintStatus.CANCELLED]
                ),
                Complaint.resolution_deadline < now,
            )
        )
        or 0
    )

    first_response_sla_breached_count = (
        db.scalar(
            select(func.count(Complaint.id)).where(
                Complaint.society_id == target_soc,
                Complaint.first_response_deadline.isnot(None),
                Complaint.status != ComplaintStatus.CANCELLED,
                or_(
                    and_(
                        Complaint.first_response_at.isnot(None),
                        Complaint.first_response_at > Complaint.first_response_deadline,
                    ),
                    and_(
                        Complaint.first_response_at.is_(None),
                        Complaint.first_response_deadline < now,
                    ),
                ),
            )
        )
        or 0
    )

    reopened_count = int(
        db.scalar(
            select(func.coalesce(func.sum(Complaint.reopened_count), 0)).where(
                Complaint.society_id == target_soc
            )
        )
        or 0
    )

    # Resolution turnaround time
    resolved_times_stmt = select(Complaint.created_at, Complaint.resolved_at).where(
        Complaint.society_id == target_soc, Complaint.resolved_at.isnot(None)
    )
    resolved_pairs = db.execute(resolved_times_stmt).all()
    avg_turnaround = 0.0
    median_resolution = 0.0
    if resolved_pairs:
        durations = sorted(
            [
                max(0.0, (r.resolved_at - r.created_at).total_seconds() / 3600.0)
                for r in resolved_pairs
            ]
        )
        avg_turnaround = round(sum(durations) / len(durations), 1)
        n_res = len(durations)
        if n_res % 2 == 1:
            median_resolution = round(durations[n_res // 2], 1)
        else:
            median_resolution = round(
                (durations[(n_res // 2) - 1] + durations[n_res // 2]) / 2.0, 1
            )

    # First response turnaround time
    first_resp_times_stmt = select(Complaint.created_at, Complaint.first_response_at).where(
        Complaint.society_id == target_soc, Complaint.first_response_at.isnot(None)
    )
    first_resp_pairs = db.execute(first_resp_times_stmt).all()
    avg_first_response = 0.0
    median_first_response = 0.0
    if first_resp_pairs:
        first_durations = sorted(
            [
                max(0.0, (r.first_response_at - r.created_at).total_seconds() / 3600.0)
                for r in first_resp_pairs
            ]
        )
        avg_first_response = round(sum(first_durations) / len(first_durations), 1)
        n_first = len(first_durations)
        if n_first % 2 == 1:
            median_first_response = round(first_durations[n_first // 2], 1)
        else:
            median_first_response = round(
                (first_durations[(n_first // 2) - 1] + first_durations[n_first // 2]) / 2.0, 1
            )

    complaints = ComplaintSummary(
        total_complaints=total_complaints,
        open_complaints=open_c,
        in_progress_complaints=in_prog_c,
        resolved_complaints=resolved_c,
        closed_complaints=closed_c,
        safety_escalated_count=safety_count,
        sla_breached_count=sla_breached_count,
        first_response_sla_breached_count=first_response_sla_breached_count,
        reopened_count=reopened_count,
        avg_resolution_hours=avg_turnaround,
        median_resolution_hours=median_resolution,
        avg_first_response_hours=avg_first_response,
        median_first_response_hours=median_first_response,
    )

    # 5. Tower-level breakdown
    towers_db = (
        db.query(Tower)
        .filter(Tower.society_id == target_soc)
        .order_by(Tower.tower_number.asc())
        .all()
    )
    tower_metrics: list[TowerFinancialMetric] = []

    for tw in towers_db:
        # Flat count
        flat_count = (
            db.scalar(
                select(func.count(Flat.id)).where(
                    Flat.tower_id == tw.id, Flat.society_id == target_soc
                )
            )
            or 0
        )

        # Tower billed
        tw_billed = int(
            db.scalar(
                select(func.coalesce(func.sum(Invoice.total_paise), 0))
                .join(Flat, Flat.id == Invoice.flat_id)
                .where(Flat.tower_id == tw.id, Flat.society_id == target_soc)
            )
            or 0
        )

        # Tower collected
        tw_collected = int(
            db.scalar(
                select(func.coalesce(func.sum(PaymentAllocation.allocated_paise), 0))
                .join(Invoice, Invoice.id == PaymentAllocation.invoice_id)
                .join(Flat, Flat.id == Invoice.flat_id)
                .join(Payment, Payment.id == PaymentAllocation.payment_id)
                .where(
                    Flat.tower_id == tw.id,
                    Flat.society_id == target_soc,
                    Payment.status == PaymentStatus.SUCCESS,
                )
            )
            or 0
        )

        # Tower open complaints
        tw_open_comp = (
            db.scalar(
                select(func.count(Complaint.id))
                .join(Flat, Flat.id == Complaint.flat_id)
                .where(
                    Flat.tower_id == tw.id,
                    Flat.society_id == target_soc,
                    Complaint.status.notin_(
                        [
                            ComplaintStatus.RESOLVED,
                            ComplaintStatus.CLOSED,
                            ComplaintStatus.CANCELLED,
                        ]
                    ),
                )
            )
            or 0
        )

        tower_metrics.append(
            TowerFinancialMetric(
                tower_id=tw.id,
                tower_number=tw.tower_number,
                tower_name=tw.name,
                total_flats=flat_count,
                total_billed_paise=tw_billed,
                total_collected_paise=tw_collected,
                total_outstanding_paise=max(0, tw_billed - tw_collected),
                open_complaints=tw_open_comp,
            )
        )

    return CommitteeOverviewResponse(
        society_id=target_soc,
        society_name=society_name,
        as_of_date=now,
        financials=financials,
        complaints=complaints,
        towers=tower_metrics,
    )


@router.get(
    "/reports/monthly",
    response_model=list[MonthlyReportItem],
    summary="Get monthly financial summaries for committee governance",
)
def get_monthly_reports(
    claims: Annotated[
        CurrentUserClaims, Depends(require_permissions(Permission.COMMITTEE_REPORT_READ))
    ],
    society_id: UUID | None = Query(None),
    db: Session = Depends(get_db),
) -> list[MonthlyReportItem]:
    target_soc = _resolve_society_id(claims, society_id)

    # Group invoices by billing_period
    period_stmt = (
        select(
            Invoice.billing_period,
            func.count(Invoice.id).label("inv_count"),
            func.coalesce(func.sum(Invoice.total_paise), 0).label("billed"),
        )
        .where(Invoice.society_id == target_soc)
        .group_by(Invoice.billing_period)
        .order_by(Invoice.billing_period.desc())
    )
    period_rows = db.execute(period_stmt).all()

    items: list[MonthlyReportItem] = []
    for r in period_rows:
        period = r.billing_period
        inv_count = int(r.inv_count or 0)
        billed_paise = int(r.billed or 0)

        # Collected for this period's invoices
        col_stmt = (
            select(func.coalesce(func.sum(PaymentAllocation.allocated_paise), 0))
            .join(Invoice, Invoice.id == PaymentAllocation.invoice_id)
            .join(Payment, Payment.id == PaymentAllocation.payment_id)
            .where(
                Invoice.society_id == target_soc,
                Invoice.billing_period == period,
                Payment.status == PaymentStatus.SUCCESS,
            )
        )
        col_paise = int(db.scalar(col_stmt) or 0)
        pct = round((col_paise / billed_paise) * 100.0, 2) if billed_paise > 0 else 100.0

        items.append(
            MonthlyReportItem(
                billing_period=period,
                total_invoices=inv_count,
                total_billed_paise=billed_paise,
                total_collected_paise=col_paise,
                total_outstanding_paise=max(0, billed_paise - col_paise),
                collection_percentage=pct,
            )
        )

    return items


@router.get(
    "/reports/export",
    summary="Export committee financial statement as CSV with formula injection protection",
)
def export_committee_report_csv(
    claims: Annotated[
        CurrentUserClaims, Depends(require_permissions(Permission.COMMITTEE_REPORT_READ))
    ],
    society_id: UUID | None = Query(None),
    db: Session = Depends(get_db),
) -> Response:
    target_soc = _resolve_society_id(claims, society_id)
    monthly_data = get_monthly_reports(claims=claims, society_id=target_soc, db=db)

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(
        [
            "Billing Period",
            "Invoices Count",
            "Billed Amount (INR)",
            "Collected Amount (INR)",
            "Outstanding Dues (INR)",
            "Collection Percentage",
        ]
    )

    for item in monthly_data:
        writer.writerow(
            [
                sanitize_for_csv_export(item.billing_period),
                sanitize_for_csv_export(item.total_invoices),
                f"{item.total_billed_paise / 100:.2f}",
                f"{item.total_collected_paise / 100:.2f}",
                f"{item.total_outstanding_paise / 100:.2f}",
                f"{item.collection_percentage:.1f}%",
            ]
        )

    filename = f"committee_financial_statement_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
