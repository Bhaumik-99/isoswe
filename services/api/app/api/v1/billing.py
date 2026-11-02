"""API Version 1 Maintenance Billing & Payment Endpoints

Provides versioned REST endpoints for:
- Resident invoice history, summaries, payments, and receipts
- Staff society-wide billing overview, invoice search, previews, and batch billing generation
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AuthorizationError, NotFoundError
from app.core.security import get_current_user, require_roles
from app.domains.billing.models import InvoiceStatus
from app.domains.billing.schemas import (
    BillingRunPreviewResponse,
    BillingRunResponse,
    ExecuteBillingRunRequest,
    InitiatePaymentRequest,
    InvoiceResponse,
    PaymentAllocationSchema,
    PaymentResponse,
    ReceiptResponse,
    ResidentBillingSummaryResponse,
    StaffBillingOverviewResponse,
)
from app.domains.billing.service import BillingService
from app.domains.identity.models import RoleType
from app.domains.identity.schemas import CurrentUserClaims

router = APIRouter(prefix="/billing", tags=["Billing & Payments"])


# =============================================================================
# Resident Endpoints
# =============================================================================
@router.get(
    "/me/summary",
    response_model=ResidentBillingSummaryResponse,
    summary="Get resident maintenance balance and summary",
)
def get_resident_summary(
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.RESIDENT))],
    db: Session = Depends(get_db),
) -> ResidentBillingSummaryResponse:
    """Returns total outstanding balance, overdue amounts, counts, and latest invoice for the authenticated resident."""
    service = BillingService(db)
    return service.get_resident_summary(claims.active_flat_ids)


@router.get(
    "/me/invoices",
    response_model=list[InvoiceResponse],
    summary="List invoices for resident's authorized flats",
)
def list_resident_invoices(
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.RESIDENT))],
    billing_period: str | None = Query(None, description="Filter by YYYY-MM (e.g. '2026-11')"),
    status: InvoiceStatus | None = Query(None, description="Filter by invoice status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[InvoiceResponse]:
    """Returns persistent invoices belonging only to the resident's active, approved flat memberships."""
    service = BillingService(db)
    invoices = service.repo.get_invoices_for_flats(
        flat_ids=claims.active_flat_ids,
        billing_period=billing_period,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [service.map_to_invoice_response(inv) for inv in invoices]


@router.get(
    "/me/payments",
    response_model=list[PaymentResponse],
    summary="List payment history for resident's flats",
)
def list_resident_payments(
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.RESIDENT))],
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[PaymentResponse]:
    """Returns payment history for the resident's approved flat memberships."""
    service = BillingService(db)
    payments = service.repo.get_payments_for_flats(
        flat_ids=claims.active_flat_ids,
        limit=limit,
        offset=offset,
    )
    res: list[PaymentResponse] = []
    for p in payments:
        flat_tower = service.repo.get_flat_with_tower(p.flat_id)
        allocs = [
            {
                "id": a.id,
                "payment_id": a.payment_id,
                "invoice_id": a.invoice_id,
                "invoice_number": a.invoice.invoice_number if a.invoice else None,
                "allocated_paise": a.allocated_paise,
                "created_at": a.created_at,
            }
            for a in p.allocations
        ]
        res.append(
            PaymentResponse(
                id=p.id,
                society_id=p.society_id,
                flat_id=p.flat_id,
                amount_paise=p.amount_paise,
                currency=p.currency,
                provider=p.provider,
                provider_reference=p.provider_reference,
                status=p.status,
                initiated_by=p.initiated_by,
                allocations=allocs,  # type: ignore[arg-type]
                tower_number=flat_tower[1].tower_number if flat_tower else None,
                flat_number=flat_tower[0].flat_number if flat_tower else None,
                created_at=p.created_at,
                updated_at=p.updated_at,
            )
        )
    return res


@router.get(
    "/invoices/{invoice_id}",
    response_model=InvoiceResponse,
    summary="Get invoice detail by ID",
)
def get_invoice_detail(
    invoice_id: UUID,
    claims: Annotated[CurrentUserClaims, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> InvoiceResponse:
    """Retrieves invoice details.

    AUTHORIZATION:
    - Residents can only access invoices for their approved active flat memberships.
    - Helpdesk can only access invoices belonging to their authorized society.
    """
    service = BillingService(db)
    invoice = service.repo.get_invoice_by_id(invoice_id)
    if not invoice:
        raise NotFoundError("Invoice not found")

    # Authorize resident or staff
    if RoleType.RESIDENT in claims.roles and RoleType.HELPDESK not in claims.roles:
        if invoice.flat_id not in claims.active_flat_ids:
            raise AuthorizationError(
                "Access denied: You are not authorized to view invoices for this apartment"
            )
    elif RoleType.HELPDESK in claims.roles:
        if invoice.society_id not in claims.society_ids:
            raise AuthorizationError(
                "Access denied: You are not authorized to view records from another society"
            )
    else:
        raise AuthorizationError("Access denied")

    return service.map_to_invoice_response(invoice)


@router.get(
    "/invoices/{invoice_id}/receipt",
    response_model=ReceiptResponse,
    summary="Get invoice payment receipt",
)
def get_invoice_receipt(
    invoice_id: UUID,
    claims: Annotated[CurrentUserClaims, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> ReceiptResponse:
    """Retrieves official payment receipt for an invoice."""
    service = BillingService(db)
    invoice = service.repo.get_invoice_by_id(invoice_id)
    if not invoice:
        raise NotFoundError("Invoice not found")

    if RoleType.RESIDENT in claims.roles and RoleType.HELPDESK not in claims.roles:
        if invoice.flat_id not in claims.active_flat_ids:
            raise AuthorizationError("Access denied")
    elif RoleType.HELPDESK in claims.roles and invoice.society_id not in claims.society_ids:
        raise AuthorizationError("Access denied")

    return service.get_invoice_receipt(invoice_id, invoice.society_id)


@router.post(
    "/invoices/{invoice_id}/payments",
    response_model=PaymentResponse,
    status_code=status.HTTP_200_OK,
    summary="Initiate simulated test payment for invoice",
)
def initiate_invoice_payment(
    invoice_id: UUID,
    payload: InitiatePaymentRequest,
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.RESIDENT))],
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> PaymentResponse:
    """Executes a simulated payment against an invoice.

    INVARIANTS:
    - Resident can only pay for their own approved flat's invoice.
    - Amount cannot exceed outstanding balance.
    - Ledger is updated append-only.
    - Supports Idempotency-Key.
    """
    service = BillingService(db)
    invoice = service.repo.get_invoice_by_id(invoice_id)
    if not invoice:
        raise NotFoundError("Invoice not found")

    if invoice.flat_id not in claims.active_flat_ids:
        raise AuthorizationError("Access denied: You can only pay invoices for your own apartment")

    return service.process_invoice_payment(
        society_id=invoice.society_id,
        invoice_id=invoice_id,
        amount_paise=payload.amount_paise,
        user_id=claims.user_id,
        simulate_failure=payload.simulate_failure,
        idempotency_key=idempotency_key,
    )


@router.get(
    "/payments/{payment_id}",
    response_model=PaymentResponse,
    summary="Get payment details and allocations",
)
def get_payment_detail(
    payment_id: UUID,
    claims: Annotated[CurrentUserClaims, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> PaymentResponse:
    """Retrieves payment details and invoice allocations."""
    service = BillingService(db)
    payment = service.repo.get_payment_by_id(payment_id)
    if not payment:
        raise NotFoundError("Payment record not found")

    if RoleType.RESIDENT in claims.roles and RoleType.HELPDESK not in claims.roles:
        if payment.flat_id not in claims.active_flat_ids:
            raise AuthorizationError("Access denied")
    elif RoleType.HELPDESK in claims.roles and payment.society_id not in claims.society_ids:
        raise AuthorizationError("Access denied")

    flat_tower = service.repo.get_flat_with_tower(payment.flat_id)
    allocs = [
        PaymentAllocationSchema(
            id=a.id,
            payment_id=a.payment_id,
            invoice_id=a.invoice_id,
            invoice_number=a.invoice.invoice_number if a.invoice else None,
            allocated_paise=a.allocated_paise,
            created_at=a.created_at,
        )
        for a in payment.allocations
    ]
    return PaymentResponse(
        id=payment.id,
        society_id=payment.society_id,
        flat_id=payment.flat_id,
        amount_paise=payment.amount_paise,
        currency=payment.currency,
        provider=payment.provider,
        provider_reference=payment.provider_reference,
        status=payment.status,
        initiated_by=payment.initiated_by,
        allocations=allocs,
        tower_number=flat_tower[1].tower_number if flat_tower else None,
        flat_number=flat_tower[0].flat_number if flat_tower else None,
        created_at=payment.created_at,
        updated_at=payment.updated_at,
    )


# =============================================================================
# Staff (Helpdesk) Endpoints
# =============================================================================
@router.get(
    "/staff/overview",
    response_model=StaffBillingOverviewResponse,
    summary="Get society-wide billing overview",
)
def get_staff_overview(
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.HELPDESK))],
    db: Session = Depends(get_db),
) -> StaffBillingOverviewResponse:
    """Returns society-wide billing totals, collection metrics, and overdue tracking."""
    if not claims.society_ids:
        raise AuthorizationError("No authorized society associated with your staff account")
    service = BillingService(db)
    return service.get_staff_overview(claims.society_ids[0])


@router.get(
    "/staff/invoices",
    response_model=list[InvoiceResponse],
    summary="Search and filter society invoices",
)
def list_staff_invoices(
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.HELPDESK))],
    billing_period: str | None = Query(None, description="Filter by YYYY-MM (e.g. '2026-11')"),
    tower_number: str | None = Query(None, description="Filter by tower (e.g. 'T07')"),
    flat_number: str | None = Query(None, description="Filter by unit (e.g. '1203')"),
    status: InvoiceStatus | None = Query(None, description="Filter by invoice status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[InvoiceResponse]:
    """Returns paginated society invoices with filters."""
    if not claims.society_ids:
        raise AuthorizationError("No authorized society associated with your staff account")
    service = BillingService(db)
    invoices = service.repo.get_invoices_for_society(
        society_id=claims.society_ids[0],
        billing_period=billing_period,
        tower_number=tower_number,
        flat_number=flat_number,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [service.map_to_invoice_response(inv) for inv in invoices]


@router.post(
    "/staff/runs/preview",
    response_model=BillingRunPreviewResponse,
    summary="Preview monthly billing run",
)
def preview_monthly_billing(
    payload: ExecuteBillingRunRequest,
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.HELPDESK))],
    db: Session = Depends(get_db),
) -> BillingRunPreviewResponse:
    """Previews eligible flats, expected charges, and exclusions before running batch billing."""
    if not claims.society_ids:
        raise AuthorizationError("No authorized society associated with your staff account")
    service = BillingService(db)
    return service.preview_billing_run(
        society_id=claims.society_ids[0],
        billing_period=payload.billing_period,
    )


@router.post(
    "/staff/runs",
    response_model=BillingRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate monthly maintenance invoices",
)
def execute_monthly_billing(
    payload: ExecuteBillingRunRequest,
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.HELPDESK))],
    db: Session = Depends(get_db),
) -> BillingRunResponse:
    """Executes monthly maintenance billing run across society units.

    INVARIANTS:
    - Atomic transaction: Invoices, line items, ledger charges, and outbox records commit together.
    - Concurrency safe: Prevents duplicate invoices via unique constraints.
    """
    if not claims.society_ids:
        raise AuthorizationError("No authorized society associated with your staff account")
    service = BillingService(db)
    run = service.execute_billing_run(
        society_id=claims.society_ids[0],
        billing_period=payload.billing_period,
        actor_id=claims.user_id,
        custom_due_date=payload.due_date,
    )
    return BillingRunResponse(
        id=run.id,
        society_id=run.society_id,
        billing_period=run.billing_period,
        total_eligible_flats=run.total_eligible_flats,
        total_invoiced_flats=run.total_invoiced_flats,
        total_skipped_flats=run.total_skipped_flats,
        total_charges_paise=run.total_charges_paise,
        status=run.status,
        initiated_by=run.initiated_by,
        run_metadata=run.run_metadata,
        created_at=run.created_at,
    )


@router.get(
    "/staff/runs/{run_id}",
    response_model=BillingRunResponse,
    summary="Get billing run details",
)
def get_billing_run_detail(
    run_id: UUID,
    claims: Annotated[CurrentUserClaims, Depends(require_roles(RoleType.HELPDESK))],
    db: Session = Depends(get_db),
) -> BillingRunResponse:
    """Retrieves log details of a specific monthly billing run."""
    if not claims.society_ids:
        raise AuthorizationError("No authorized society associated with your staff account")
    service = BillingService(db)
    run = service.repo.get_billing_run_by_id(run_id, society_id=claims.society_ids[0])
    if not run:
        raise NotFoundError("Billing run record not found")
    return BillingRunResponse(
        id=run.id,
        society_id=run.society_id,
        billing_period=run.billing_period,
        total_eligible_flats=run.total_eligible_flats,
        total_invoiced_flats=run.total_invoiced_flats,
        total_skipped_flats=run.total_skipped_flats,
        total_charges_paise=run.total_charges_paise,
        status=run.status,
        initiated_by=run.initiated_by,
        run_metadata=run.run_metadata,
        created_at=run.created_at,
    )
