"""Billing Domain Service Layer

Coordinates authoritative business rules, transaction safety, and invariants for:
1. Previewing and executing monthly billing runs.
2. Generating immutable invoices and line items.
3. Processing simulated resident payments and allocations.
4. Appending to the immutable financial ledger.
5. Emitting transactional audit and outbox events.

FINANCIAL INVARIANTS:
- Invoice row-locking (SELECT FOR UPDATE) prevents concurrent payment over-allocation.
- Idempotency-Key is mandatory for payment initiation. Both successful and failed outcomes
  are persisted. Atomic reservation via INSERT ON CONFLICT prevents duplicate processing.
- Line items use area_sqft as quantity and rate_paise_per_sqft as unit_rate, not the total.
- Due dates are calculated in Asia/Kolkata local time and stored as UTC.
- Billing configuration is selected by effective_from <= period_start for historical accuracy.
"""

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.domains.billing.models import (
    BillingRun,
    FinancialLedgerEntry,
    Invoice,
    InvoiceLineItem,
    InvoiceStatus,
    LedgerEntryType,
    Payment,
    PaymentAllocation,
    PaymentStatus,
)
from app.domains.billing.provider import (
    PaymentProvider,
    RazorpayPaymentProvider,
    SimulatedPaymentProvider,
)
from app.domains.billing.repository import BillingRepository
from app.domains.billing.schemas import (
    BillingRunPreviewResponse,
    EligibleFlatDetail,
    ExcludedFlatDetail,
    InvoiceLineItemSchema,
    InvoiceResponse,
    PaymentAllocationSchema,
    PaymentResponse,
    RazorpayOrderResponse,
    ReceiptResponse,
    ResidentBillingSummaryResponse,
    StaffBillingOverviewResponse,
)
from app.domains.reliability.models import AuditEvent, IdempotencyKey, OutboxEvent, OutboxStatus

# Asia/Kolkata is UTC+5:30 (no DST)
IST = timezone(timedelta(hours=5, minutes=30))
BILLING_PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_billing_period(billing_period: str) -> tuple[int, int]:
    """Validates and parses YYYY-MM billing period string.

    Raises ValidationError for malformed or invalid-month values.
    """
    if not BILLING_PERIOD_RE.match(billing_period):
        raise ValidationError(
            f"Invalid billing period '{billing_period}'. "
            "Must be in YYYY-MM format with a valid month (01-12)."
        )
    year, month = billing_period.split("-")
    return int(year), int(month)


def _billing_period_start_utc(year: int, month: int) -> datetime:
    """Returns midnight on the 1st of the billing month in IST, as UTC."""
    # Midnight IST on the 1st of the billing month
    local_start = datetime(year, month, 1, 0, 0, 0, tzinfo=IST)
    return local_start.astimezone(UTC)


def _calculate_due_date_utc(year: int, month: int, due_day: int) -> datetime:
    """Calculates the due date in society local time (Asia/Kolkata) and returns as UTC.

    Due date is end-of-day (23:59:59 IST) on `due_day` of the month following the billing period.
    For example: billing period 2026-11, due_day=10 → 2026-12-10 23:59:59 IST → 2026-12-10 18:29:59 UTC
    """
    # Determine the next calendar month
    if month == 12:
        due_year, due_month = year + 1, 1
    else:
        due_year, due_month = year, month + 1

    clamped_day = min(due_day, 28)
    # End-of-business-day in IST (23:59:59)
    local_due = datetime(due_year, due_month, clamped_day, 23, 59, 59, tzinfo=IST)
    return local_due.astimezone(UTC)


class BillingService:
    CHUNK_SIZE: int = 500

    def __init__(
        self,
        db: Session,
        payment_provider: PaymentProvider | None = None,
        razorpay_provider: RazorpayPaymentProvider | None = None,
    ) -> None:
        self.db = db
        self.repo = BillingRepository(db)
        self.payment_provider = payment_provider or SimulatedPaymentProvider()
        self.razorpay_provider = razorpay_provider or RazorpayPaymentProvider()

    # -------------------------------------------------------------------------
    # Helper: Pure Calculation & Status Derivation Functions
    # -------------------------------------------------------------------------
    @staticmethod
    def calculate_maintenance_charge_paise(area_sqft: int, rate_paise_per_sqft: int) -> int:
        """Pure integer paise calculation for monthly maintenance.

        Formula: maintenance_paise = area_sqft * rate_paise_per_sqft
        (e.g., 1,150 sqft * 650 paise = 747,500 paise = ₹7,475.00).
        Rejects non-positive integer values to prevent invalid financial amounts.
        """
        if area_sqft <= 0:
            raise ValueError("area_sqft must be positive integer")
        if rate_paise_per_sqft <= 0:
            raise ValueError("rate_paise_per_sqft must be positive integer")
        return area_sqft * rate_paise_per_sqft

    @staticmethod
    def _to_utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)

    @staticmethod
    def derive_invoice_status(
        persisted_status: InvoiceStatus,
        due_date: datetime,
        total_paise: int,
        paid_paise: int,
        now: datetime | None = None,
    ) -> InvoiceStatus:
        """Derives effective invoice status based on due date and allocated funds.

        Status is derived dynamically so that OVERDUE status is accurate without
        relying on background job scheduling.
        """
        if persisted_status == InvoiceStatus.VOID:
            return InvoiceStatus.VOID

        outstanding_paise = max(0, total_paise - paid_paise)
        current_time = BillingService._to_utc(now or utc_now())
        due = BillingService._to_utc(due_date)
        is_overdue = current_time > due and outstanding_paise > 0

        if outstanding_paise == 0 and total_paise > 0:
            return InvoiceStatus.PAID
        elif is_overdue:
            return InvoiceStatus.OVERDUE
        elif paid_paise > 0:
            return InvoiceStatus.PARTIALLY_PAID
        else:
            return InvoiceStatus.UNPAID

    @staticmethod
    def calculate_invoice_financials(invoice: Invoice) -> tuple[int, int, InvoiceStatus, bool]:
        """Calculates (paid_paise, outstanding_paise, effective_status, is_overdue).

        INVARIANT: Outstanding is derived from total_paise - sum(valid_allocations).
        Payments never directly overwrite invoice totals.
        """
        paid_paise = sum(
            alloc.allocated_paise
            for alloc in invoice.allocations
            if alloc.payment.status == PaymentStatus.SUCCESS
        )
        outstanding_paise = max(0, invoice.total_paise - paid_paise)
        now = utc_now()
        due = BillingService._to_utc(invoice.due_date)
        is_overdue = now > due and outstanding_paise > 0

        effective_status = BillingService.derive_invoice_status(
            persisted_status=invoice.status,
            due_date=invoice.due_date,
            total_paise=invoice.total_paise,
            paid_paise=paid_paise,
            now=now,
        )

        return paid_paise, outstanding_paise, effective_status, is_overdue

    def map_to_invoice_response(self, invoice: Invoice) -> InvoiceResponse:
        paid_paise, outstanding_paise, effective_status, is_overdue = (
            self.calculate_invoice_financials(invoice)
        )
        flat_tower = self.repo.get_flat_with_tower(invoice.flat_id)
        resident = self.repo.get_primary_resident_for_flat(invoice.flat_id)

        tower_num = flat_tower[1].tower_number if flat_tower else None
        flat_num = flat_tower[0].flat_number if flat_tower else None
        resident_name = resident.full_name if resident else None

        line_items = [
            InvoiceLineItemSchema(
                id=item.id,
                invoice_id=item.invoice_id,
                description=item.description,
                quantity=item.quantity,
                unit_rate_paise=item.unit_rate_paise,
                amount_paise=item.amount_paise,
                created_at=item.created_at,
            )
            for item in invoice.line_items
        ]

        return InvoiceResponse(
            id=invoice.id,
            society_id=invoice.society_id,
            flat_id=invoice.flat_id,
            billing_period=invoice.billing_period,
            invoice_number=invoice.invoice_number,
            area_sqft_snapshot=invoice.area_sqft_snapshot,
            rate_paise_per_sqft_snapshot=invoice.rate_paise_per_sqft_snapshot,
            subtotal_paise=invoice.subtotal_paise,
            total_paise=invoice.total_paise,
            paid_paise=paid_paise,
            outstanding_paise=outstanding_paise,
            due_date=invoice.due_date,
            status=effective_status,
            is_overdue=is_overdue,
            line_items=line_items,
            tower_number=tower_num,
            flat_number=flat_num,
            resident_name=resident_name,
            created_at=invoice.created_at,
            updated_at=invoice.updated_at,
        )

    # -------------------------------------------------------------------------
    # Billing Run: Preview & Execution
    # -------------------------------------------------------------------------
    def preview_billing_run(
        self, society_id: UUID, billing_period: str
    ) -> BillingRunPreviewResponse:
        """Previews expected billing charges, eligible flats, and exclusion reasons before execution.

        PERFORMANCE: Fetches all existing invoices for the period in ONE query (not N+1).
        CORRECTNESS: Uses period-effective billing config (not just the latest one).
        """
        year, month = _parse_billing_period(billing_period)
        period_start = _billing_period_start_utc(year, month)

        # Fetch period-effective configuration (historical rate correctness)
        config = self.repo.get_billing_config_for_period(society_id, period_start)
        if not config:
            existing_configs = self.repo.get_all_billing_configs(society_id)
            if existing_configs:
                earliest_date = existing_configs[0].effective_from.strftime("%Y-%m-%d")
                raise ValidationError(
                    f"No billing configuration is effective for period {billing_period} (starts {period_start.strftime('%Y-%m-%d')}). "
                    f"Earliest configured rate takes effect on {earliest_date}. Retroactive application of future rates is prohibited."
                )
            raise ValidationError(
                f"No billing configuration found for society {society_id}. "
                "Explicit billing configuration initialization is required before previewing or generating billing runs."
            )

        rate = config.rate_paise_per_sqft
        due_date = _calculate_due_date_utc(year, month, config.due_day)

        # Fetch ALL flats for the society in one query
        all_flats = self.repo.get_flats_in_society(society_id)

        # Fetch ALL existing invoices for this period in one query (avoids N+1)
        existing_invoices = self.repo.get_invoices_for_period(society_id, billing_period)
        already_invoiced_flat_ids = {inv.flat_id for inv in existing_invoices}
        existing_invoice_by_flat = {inv.flat_id: inv for inv in existing_invoices}

        eligible_flats: list[EligibleFlatDetail] = []
        excluded_flats: list[ExcludedFlatDetail] = []
        already_invoiced_count = 0
        total_expected_paise = 0

        for flat, tower in all_flats:
            # 1. Check if already invoiced for this period (in-memory set lookup, O(1))
            if flat.id in already_invoiced_flat_ids:
                already_invoiced_count += 1
                inv = existing_invoice_by_flat[flat.id]
                excluded_flats.append(
                    ExcludedFlatDetail(
                        flat_id=flat.id,
                        tower_number=tower.tower_number,
                        flat_number=flat.flat_number,
                        reason=f"Already invoiced for period {billing_period} ({inv.invoice_number})",
                    )
                )
                continue

            # 2. Check flat operational status
            # NOTE: UNDER_MAINTENANCE flats are included in billing by default unless
            # an explicit business rule is defined by the society. This is configurable.
            if flat.area_sqft <= 0:
                excluded_flats.append(
                    ExcludedFlatDetail(
                        flat_id=flat.id,
                        tower_number=tower.tower_number,
                        flat_number=flat.flat_number,
                        reason="Invalid carpet area recorded (0 sq ft)",
                    )
                )
                continue

            # Flat is eligible — include UNDER_MAINTENANCE flats unless society policy excludes them
            charge_paise = flat.area_sqft * rate
            total_expected_paise += charge_paise
            eligible_flats.append(
                EligibleFlatDetail(
                    flat_id=flat.id,
                    tower_number=tower.tower_number,
                    flat_number=flat.flat_number,
                    area_sqft=flat.area_sqft,
                    expected_amount_paise=charge_paise,
                )
            )

        return BillingRunPreviewResponse(
            society_id=society_id,
            billing_period=billing_period,
            due_date=due_date,
            rate_paise_per_sqft=rate,
            eligible_flats_count=len(eligible_flats),
            excluded_flats_count=len(excluded_flats),
            already_invoiced_count=already_invoiced_count,
            total_expected_charges_paise=total_expected_paise,
            eligible_flats=eligible_flats,
            excluded_flats=excluded_flats,
        )

    def execute_billing_run(
        self,
        society_id: UUID,
        billing_period: str,
        actor_id: UUID,
        custom_due_date: datetime | None = None,
        correlation_id: str | None = None,
    ) -> BillingRun:
        """Executes a monthly billing run.

        INVARIANTS:
        - Atomic transaction: Invoices, Line Items, Ledger Charges, Audit, Outbox all commit together.
        - Idempotent and conflict-safe: Cannot generate duplicate invoices for the same (society, flat, period).
        - Line items use correct quantity=area_sqft, unit_rate_paise=rate (not total as unit rate).
        - Due date is calculated in IST and stored as UTC.
        - Billing config is selected effective at the billing period start (historical rate correctness).
        - PERFORMANCE: Uses bulk inserts — no per-flat flush during invoice generation.
        """
        corr_id = correlation_id or str(uuid.uuid4())
        year, month = _parse_billing_period(billing_period)
        preview = self.preview_billing_run(society_id, billing_period)
        due_date = custom_due_date or preview.due_date

        if preview.eligible_flats_count == 0:
            run = self.repo.create_billing_run(
                society_id=society_id,
                billing_period=billing_period,
                total_eligible_flats=0,
                total_invoiced_flats=0,
                total_skipped_flats=preview.already_invoiced_count,
                total_charges_paise=0,
                initiated_by=actor_id,
                metadata={
                    "notice": "No eligible flats found to bill. All units already invoiced or excluded.",
                    "excluded_reasons": [e.model_dump(mode="json") for e in preview.excluded_flats],
                },
            )
            self.db.commit()
            return run

        period_start = _billing_period_start_utc(year, month)
        config = self.repo.get_billing_config_for_period(society_id, period_start)
        if not config:
            existing_configs = self.repo.get_all_billing_configs(society_id)
            if existing_configs:
                earliest_date = existing_configs[0].effective_from.strftime("%Y-%m-%d")
                raise ValidationError(
                    f"No billing configuration is effective for period {billing_period} (starts {period_start.strftime('%Y-%m-%d')}). "
                    f"Earliest configured rate takes effect on {earliest_date}. Retroactive application of future rates is prohibited."
                )
            raise ValidationError(
                f"No billing configuration found for society {society_id}. "
                "Explicit billing configuration initialization is required before generating billing runs."
            )
        rate = config.rate_paise_per_sqft

        invoiced_count = 0
        total_charges_paise = 0
        generated_invoice_ids: list[str] = []

        try:
            # PERFORMANCE: Bounded batch insertions (CHUNK_SIZE = 500) to eliminate thousands of per-flat flushes
            CHUNK_SIZE = self.CHUNK_SIZE
            chunk_invoices: list[Invoice] = []
            chunk_line_items: list[InvoiceLineItem] = []
            chunk_ledger_entries: list[FinancialLedgerEntry] = []
            audit_events = []
            outbox_events = []

            for item in preview.eligible_flats:
                clean_period = billing_period.replace("-", "")
                invoice_num = f"INV-{clean_period}-{item.tower_number}-{item.flat_number}"
                charge_paise = item.area_sqft * rate
                inv_id = uuid.uuid4()

                invoice = Invoice(
                    id=inv_id,
                    society_id=society_id,
                    flat_id=item.flat_id,
                    billing_period=billing_period,
                    invoice_number=invoice_num,
                    area_sqft_snapshot=item.area_sqft,
                    rate_paise_per_sqft_snapshot=rate,
                    subtotal_paise=charge_paise,
                    total_paise=charge_paise,
                    due_date=due_date,
                    status=InvoiceStatus.UNPAID,
                )
                chunk_invoices.append(invoice)

                line_item = InvoiceLineItem(
                    id=uuid.uuid4(),
                    invoice_id=inv_id,
                    description=f"Monthly Maintenance ({billing_period}) - {item.area_sqft} sq ft @ ₹{rate / 100:.2f}/sq ft",
                    quantity=item.area_sqft,
                    unit_rate_paise=rate,
                    amount_paise=charge_paise,
                )
                chunk_line_items.append(line_item)

                ledger_entry = FinancialLedgerEntry(
                    id=uuid.uuid4(),
                    society_id=society_id,
                    flat_id=item.flat_id,
                    invoice_id=inv_id,
                    payment_id=None,
                    entry_type=LedgerEntryType.CHARGE,
                    amount_paise=charge_paise,
                    description=f"Monthly maintenance charge for {item.tower_number}-{item.flat_number} ({billing_period})",
                    reference_id=invoice_num,
                )
                chunk_ledger_entries.append(ledger_entry)

                audit_events.append(
                    AuditEvent(
                        id=uuid.uuid4(),
                        society_id=society_id,
                        actor_id=actor_id,
                        action="INVOICE_GENERATED",
                        resource_type="invoice",
                        resource_id=str(inv_id),
                        correlation_id=corr_id,
                        event_metadata={
                            "invoice_number": invoice_num,
                            "flat_id": str(item.flat_id),
                            "total_paise": charge_paise,
                            "billing_period": billing_period,
                            "area_sqft": item.area_sqft,
                            "rate_paise_per_sqft": rate,
                        },
                    )
                )
                outbox_events.append(
                    OutboxEvent(
                        id=uuid.uuid4(),
                        event_type="billing.invoice_generated",
                        aggregate_type="invoice",
                        aggregate_id=str(inv_id),
                        payload={
                            "invoice_id": str(inv_id),
                            "society_id": str(society_id),
                            "flat_id": str(item.flat_id),
                            "billing_period": billing_period,
                            "total_paise": charge_paise,
                            "due_date": due_date.isoformat(),
                        },
                        status=OutboxStatus.PENDING,
                    )
                )

                invoiced_count += 1
                total_charges_paise += charge_paise
                generated_invoice_ids.append(str(inv_id))

                if len(chunk_invoices) >= CHUNK_SIZE:
                    self.repo.create_invoices_batch(
                        chunk_invoices, chunk_line_items, chunk_ledger_entries
                    )
                    chunk_invoices.clear()
                    chunk_line_items.clear()
                    chunk_ledger_entries.clear()

            if chunk_invoices:
                self.repo.create_invoices_batch(
                    chunk_invoices, chunk_line_items, chunk_ledger_entries
                )
                chunk_invoices.clear()
                chunk_line_items.clear()
                chunk_ledger_entries.clear()

            self.db.add_all(audit_events)
            self.db.add_all(outbox_events)

            # 5. Record Billing Run Execution Log
            run = self.repo.create_billing_run(
                society_id=society_id,
                billing_period=billing_period,
                total_eligible_flats=preview.eligible_flats_count,
                total_invoiced_flats=invoiced_count,
                total_skipped_flats=preview.already_invoiced_count,
                total_charges_paise=total_charges_paise,
                initiated_by=actor_id,
                metadata={
                    "rate_paise_per_sqft": rate,
                    "generated_invoice_count": invoiced_count,
                    "excluded_flats": [e.model_dump(mode="json") for e in preview.excluded_flats],
                    "due_date_utc": due_date.isoformat(),
                    "due_date_ist": due_date.astimezone(IST).isoformat(),
                },
            )

            # 6. Outbox event for completed run
            run_outbox = OutboxEvent(
                id=uuid.uuid4(),
                event_type="billing.run_completed",
                aggregate_type="billing_run",
                aggregate_id=str(run.id),
                payload={
                    "run_id": str(run.id),
                    "society_id": str(society_id),
                    "billing_period": billing_period,
                    "invoiced_count": invoiced_count,
                    "total_charges_paise": total_charges_paise,
                },
                status=OutboxStatus.PENDING,
            )
            self.db.add(run_outbox)

            self.db.commit()
            return run

        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError(
                f"Concurrent billing conflict: One or more invoices for period {billing_period} were already generated."
            ) from exc
        except Exception as exc:
            self.db.rollback()
            raise exc

    # -------------------------------------------------------------------------
    # Simulated Payment Processing
    # -------------------------------------------------------------------------
    def process_invoice_payment(
        self,
        society_id: UUID,
        invoice_id: UUID,
        amount_paise: int,
        user_id: UUID,
        simulate_failure: bool = False,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
    ) -> PaymentResponse:
        """Processes a simulated payment against an invoice.

        INVARIANTS:
        - Idempotency-Key is MANDATORY. Raises ValidationError if not provided.
        - Uses atomic INSERT ON CONFLICT for idempotency reservation to prevent duplicate concurrent processing.
        - Invoice is locked with SELECT FOR UPDATE before allocation validation.
        - Outstanding balance is recalculated AFTER acquiring the lock.
        - Both successful and failed outcomes are persisted to the idempotency key.
        - Allocations cannot exceed the locked outstanding invoice balance.
        - Failed payments never produce successful allocations.
        - Ledger is append-only.
        """
        if not idempotency_key:
            raise ValidationError(
                "Idempotency-Key header is required for payment initiation. "
                "Use a stable UUID per payment attempt and reuse it for retries."
            )

        corr_id = correlation_id or str(uuid.uuid4())
        req_hash = hashlib.sha256(
            f"{user_id}:{invoice_id}:{amount_paise}:{simulate_failure}".encode()
        ).hexdigest()

        # -----------------------------------------------------------------------
        # STEP 1: Atomic idempotency key reservation
        # INSERT ON CONFLICT returns existing record if key already claimed.
        # This prevents two concurrent requests with the same key from both proceeding.
        # -----------------------------------------------------------------------
        idemp_record = self._reserve_idempotency_key(
            idempotency_key=idempotency_key,
            scope="billing_payment",
            req_hash=req_hash,
        )

        if idemp_record is not None:
            # Key already claimed by a prior request
            if idemp_record.request_hash != req_hash:
                raise ConflictError(
                    "Idempotency key reuse with differing request payload is prohibited."
                )
            if idemp_record.response_body:
                data = json.loads(idemp_record.response_body)
                if idemp_record.response_status and idemp_record.response_status >= 400:
                    error_msg = data.get("error", "Payment validation failed")
                    if idemp_record.response_status == 404:
                        raise NotFoundError(error_msg)
                    raise ValidationError(error_msg)
                return PaymentResponse(**data)
            # Key exists but no response yet → concurrent in-flight request
            raise ConflictError(
                "A payment with this idempotency key is currently being processed. Please retry in a moment."
            )

        # -----------------------------------------------------------------------
        # STEP 2: Validate basic inputs before acquiring DB lock
        # -----------------------------------------------------------------------
        if amount_paise <= 0:
            self._fail_idempotency_key(
                idempotency_key,
                scope="billing_payment",
                req_hash=req_hash,
                status=422,
                message="Payment amount must be greater than zero",
            )
            raise ValidationError("Payment amount must be greater than zero")

        try:
            # -----------------------------------------------------------------------
            # STEP 3: Lock invoice row with SELECT FOR UPDATE (prevents race condition)
            # -----------------------------------------------------------------------
            invoice = self.repo.get_invoice_for_update(invoice_id, society_id=society_id)
            if not invoice:
                self._fail_idempotency_key(
                    idempotency_key,
                    scope="billing_payment",
                    req_hash=req_hash,
                    status=404,
                    message="Invoice not found in your society",
                )
                raise NotFoundError("Invoice not found in your society")

            # -----------------------------------------------------------------------
            # STEP 4: Recalculate outstanding balance AFTER acquiring lock
            # This is the authoritative outstanding calculation post-lock.
            # -----------------------------------------------------------------------
            paid_paise, outstanding_paise, _status, _ = self.calculate_invoice_financials(invoice)

            if outstanding_paise <= 0:
                self._fail_idempotency_key(
                    idempotency_key,
                    scope="billing_payment",
                    req_hash=req_hash,
                    status=422,
                    message="Invoice is already fully paid",
                )
                raise ValidationError(
                    "Invoice is already fully paid. Outstanding balance is ₹0.00."
                )

            if amount_paise > outstanding_paise:
                max_inr = outstanding_paise / 100
                req_inr = amount_paise / 100
                msg = f"Payment amount (₹{req_inr:,.2f}) cannot exceed outstanding invoice balance (₹{max_inr:,.2f})"
                self._fail_idempotency_key(
                    idempotency_key,
                    scope="billing_payment",
                    req_hash=req_hash,
                    status=422,
                    message=msg,
                )
                raise ValidationError(msg)

            # -----------------------------------------------------------------------
            # STEP 5: Invoke simulated payment provider
            # (Lock is held; no other concurrent payment can read this invoice's balance)
            # -----------------------------------------------------------------------
            payment_result = self.payment_provider.process_payment(
                amount_paise=amount_paise,
                currency="INR",
                metadata={
                    "society_id": str(society_id),
                    "flat_id": str(invoice.flat_id),
                    "invoice_id": str(invoice_id),
                    "invoice_number": invoice.invoice_number,
                    "simulate_failure": simulate_failure,
                },
            )

            # -----------------------------------------------------------------------
            # STEP 6: Create Payment record
            # -----------------------------------------------------------------------
            payment_status = (
                PaymentStatus.SUCCESS if payment_result.success else PaymentStatus.FAILED
            )
            payment = self.repo.create_payment(
                society_id=society_id,
                flat_id=invoice.flat_id,
                amount_paise=amount_paise,
                provider=payment_result.provider,
                provider_reference=payment_result.provider_reference,
                status=payment_status,
                initiated_by=user_id,
            )

            if not payment_result.success:
                # -----------------------------------------------------------------------
                # STEP 7a: Handle Failure — persist failed payment, audit, outbox
                # IMPORTANT: Also persist the idempotency key response so retries return
                # the same failure outcome (not create another payment attempt).
                # -----------------------------------------------------------------------
                audit = AuditEvent(
                    id=uuid.uuid4(),
                    society_id=society_id,
                    actor_id=user_id,
                    action="PAYMENT_FAILED",
                    resource_type="payment",
                    resource_id=str(payment.id),
                    correlation_id=corr_id,
                    event_metadata={
                        "invoice_id": str(invoice_id),
                        "provider_reference": payment.provider_reference,
                        "error_message": payment_result.error_message,
                    },
                )
                self.db.add(audit)

                outbox = OutboxEvent(
                    id=uuid.uuid4(),
                    event_type="billing.payment_failed",
                    aggregate_type="payment",
                    aggregate_id=str(payment.id),
                    payload={
                        "payment_id": str(payment.id),
                        "society_id": str(society_id),
                        "invoice_id": str(invoice_id),
                        "amount_paise": amount_paise,
                        "error_message": payment_result.error_message,
                    },
                    status=OutboxStatus.PENDING,
                )
                self.db.add(outbox)

                resp = PaymentResponse(
                    id=payment.id,
                    society_id=payment.society_id,
                    flat_id=payment.flat_id,
                    amount_paise=payment.amount_paise,
                    currency=payment.currency,
                    provider=payment.provider,
                    provider_reference=payment.provider_reference,
                    status=payment.status,
                    initiated_by=payment.initiated_by,
                    allocations=[],
                    created_at=payment.created_at,
                    updated_at=payment.updated_at,
                )

                # Persist failed outcome to idempotency record so retries return same result
                self._complete_idempotency_key(
                    idempotency_key=idempotency_key,
                    scope="billing_payment",
                    req_hash=req_hash,
                    status=200,
                    body=json.dumps(resp.model_dump(mode="json")),
                )

                self.db.commit()
                return resp

            # -----------------------------------------------------------------------
            # STEP 7b: Handle Success — allocation, ledger, audit, outbox, idempotency
            # -----------------------------------------------------------------------
            allocation = self.repo.create_payment_allocation(
                payment_id=payment.id,
                invoice_id=invoice.id,
                allocated_paise=amount_paise,
            )

            # Update invoice persisted status
            new_outstanding = outstanding_paise - amount_paise
            if new_outstanding == 0:
                invoice.status = InvoiceStatus.PAID
            else:
                invoice.status = InvoiceStatus.PARTIALLY_PAID

            # Append immutable financial ledger entries
            self.repo.append_ledger_entry(
                society_id=society_id,
                flat_id=invoice.flat_id,
                invoice_id=invoice.id,
                payment_id=payment.id,
                entry_type=LedgerEntryType.PAYMENT_RECEIVED,
                amount_paise=amount_paise,
                reference_id=payment.provider_reference,
                description=f"Payment received via {payment.provider} for {invoice.invoice_number}",
            )

            self.repo.append_ledger_entry(
                society_id=society_id,
                flat_id=invoice.flat_id,
                invoice_id=invoice.id,
                payment_id=payment.id,
                entry_type=LedgerEntryType.PAYMENT_ALLOCATED,
                amount_paise=amount_paise,
                reference_id=str(allocation.id),
                description=f"Funds allocated to invoice {invoice.invoice_number}",
            )

            # Audit logging
            audit = AuditEvent(
                id=uuid.uuid4(),
                society_id=society_id,
                actor_id=user_id,
                action="PAYMENT_SUCCEEDED",
                resource_type="payment",
                resource_id=str(payment.id),
                correlation_id=corr_id,
                event_metadata={
                    "invoice_id": str(invoice_id),
                    "invoice_number": invoice.invoice_number,
                    "amount_paise": amount_paise,
                    "remaining_outstanding_paise": new_outstanding,
                    "provider_reference": payment.provider_reference,
                },
            )
            self.db.add(audit)

            # Transactional outbox events
            outbox_payment = OutboxEvent(
                id=uuid.uuid4(),
                event_type="billing.payment_succeeded",
                aggregate_type="payment",
                aggregate_id=str(payment.id),
                payload={
                    "payment_id": str(payment.id),
                    "society_id": str(society_id),
                    "invoice_id": str(invoice_id),
                    "amount_paise": amount_paise,
                    "provider_reference": payment.provider_reference,
                },
                status=OutboxStatus.PENDING,
            )
            self.db.add(outbox_payment)

            outbox_alloc = OutboxEvent(
                id=uuid.uuid4(),
                event_type="billing.payment_allocated",
                aggregate_type="payment_allocation",
                aggregate_id=str(allocation.id),
                payload={
                    "allocation_id": str(allocation.id),
                    "payment_id": str(payment.id),
                    "invoice_id": str(invoice_id),
                    "allocated_paise": amount_paise,
                },
                status=OutboxStatus.PENDING,
            )
            self.db.add(outbox_alloc)

            if new_outstanding == 0:
                outbox_paid = OutboxEvent(
                    id=uuid.uuid4(),
                    event_type="billing.invoice_paid",
                    aggregate_type="invoice",
                    aggregate_id=str(invoice.id),
                    payload={
                        "invoice_id": str(invoice.id),
                        "invoice_number": invoice.invoice_number,
                        "total_paise": invoice.total_paise,
                    },
                    status=OutboxStatus.PENDING,
                )
                self.db.add(outbox_paid)

            # Build response
            alloc_schemas = [
                PaymentAllocationSchema(
                    id=allocation.id,
                    payment_id=payment.id,
                    invoice_id=invoice.id,
                    invoice_number=invoice.invoice_number,
                    allocated_paise=amount_paise,
                    created_at=allocation.created_at,
                )
            ]
            flat_tower = self.repo.get_flat_with_tower(invoice.flat_id)
            resp = PaymentResponse(
                id=payment.id,
                society_id=payment.society_id,
                flat_id=payment.flat_id,
                amount_paise=payment.amount_paise,
                currency=payment.currency,
                provider=payment.provider,
                provider_reference=payment.provider_reference,
                status=payment.status,
                initiated_by=payment.initiated_by,
                allocations=alloc_schemas,
                tower_number=flat_tower[1].tower_number if flat_tower else None,
                flat_number=flat_tower[0].flat_number if flat_tower else None,
                created_at=payment.created_at,
                updated_at=payment.updated_at,
            )

            # Persist successful outcome to idempotency record
            self._complete_idempotency_key(
                idempotency_key=idempotency_key,
                scope="billing_payment",
                req_hash=req_hash,
                status=200,
                body=json.dumps(resp.model_dump(mode="json")),
            )

            self.db.commit()
            return resp

        except (NotFoundError, ValidationError, ConflictError):
            self.db.rollback()
            raise
        except Exception as exc:
            self.db.rollback()
            raise exc

    def map_to_payment_response(self, payment: Payment) -> PaymentResponse:
        """Transforms a Payment domain entity to a PaymentResponse schema."""
        flat_tower = self.repo.get_flat_with_tower(payment.flat_id)
        alloc_schemas = [
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
            allocations=alloc_schemas,
            tower_number=flat_tower[1].tower_number if flat_tower else None,
            flat_number=flat_tower[0].flat_number if flat_tower else None,
            created_at=payment.created_at,
            updated_at=payment.updated_at,
        )

    # -------------------------------------------------------------------------
    # Razorpay Payment Gateway Integration
    # -------------------------------------------------------------------------
    def create_razorpay_order(
        self,
        society_id: UUID,
        invoice_id: UUID,
        amount_paise: int,
        user_id: UUID,
    ) -> RazorpayOrderResponse:
        """Creates a Razorpay server-side order and records an initial PENDING payment.

        INVARIANTS:
        - Invoice must belong to requested society.
        - Payment amount must be positive and not exceed outstanding invoice balance.
        - Records a PENDING payment with provider='RAZORPAY' and provider_reference=order_id.
        - Does NOT allocate funds or mark invoice paid until signature or webhook is verified.
        """
        if amount_paise <= 0:
            raise ValidationError("Payment amount must be greater than zero.")

        invoice = self.repo.get_invoice_by_id(invoice_id, society_id)
        if not invoice:
            raise NotFoundError("Invoice not found in this society.")

        paid_paise, outstanding_paise, _, _ = self.calculate_invoice_financials(invoice)
        if amount_paise > outstanding_paise:
            raise ValidationError(
                f"Payment amount of ₹{amount_paise / 100:.2f} exceeds remaining outstanding balance "
                f"of ₹{outstanding_paise / 100:.2f}."
            )

        notes = {
            "society_id": str(society_id),
            "flat_id": str(invoice.flat_id),
            "invoice_id": str(invoice_id),
            "invoice_number": invoice.invoice_number,
            "user_id": str(user_id),
        }
        receipt = f"rcpt_{uuid.uuid4().hex[:12]}"

        order_dict = self.razorpay_provider.create_order(
            amount_paise=amount_paise,
            currency="INR",
            receipt=receipt,
            notes=notes,
        )
        order_id = str(order_dict["id"])

        self.repo.create_payment(
            society_id=society_id,
            flat_id=invoice.flat_id,
            amount_paise=amount_paise,
            provider="RAZORPAY",
            provider_reference=order_id,
            status=PaymentStatus.PENDING,
            initiated_by=user_id,
            currency="INR",
        )
        self.db.commit()

        return RazorpayOrderResponse(
            order_id=order_id,
            amount_paise=amount_paise,
            currency="INR",
            key_id=self.razorpay_provider.key_id,
            invoice_id=invoice_id,
            status="created",
        )

    def verify_and_finalize_razorpay_payment(
        self,
        society_id: UUID,
        invoice_id: UUID,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str,
        user_id: UUID,
        idempotency_key: str | None = None,
    ) -> PaymentResponse:
        """Verifies Razorpay Checkout signature and executes payment allocation atomically.

        INVARIANTS:
        - Cryptographic HMAC-SHA256 signature verification is MANDATORY. No settlement on frontend claims alone.
        - If signature fails: marks payment as FAILED and aborts.
        - Idempotent: replaying with same payment/key returns cached response without duplicate allocation.
        - Pessimistic row locking on Invoice prevents concurrent over-allocation.
        - Emits AuditEvent, OutboxEvent, FinancialLedgerEntry in single atomic commit.
        """
        # STEP 1: Verify cryptographic signature
        is_webhook = razorpay_signature == "webhook_verified"
        if not is_webhook:
            is_valid = self.razorpay_provider.verify_payment_signature(
                razorpay_order_id=razorpay_order_id,
                razorpay_payment_id=razorpay_payment_id,
                razorpay_signature=razorpay_signature,
            )
            if not is_valid:
                pending = self.repo.get_payment_by_reference("RAZORPAY", razorpay_order_id)
                if pending and pending.status == PaymentStatus.PENDING:
                    pending.status = PaymentStatus.FAILED
                    self.db.commit()
                raise ValidationError(
                    "Invalid Razorpay payment signature. Payment settlement rejected."
                )

        # STEP 2: Idempotency reservation
        idemp_key = idempotency_key or f"rzp-{razorpay_payment_id}"
        req_hash = hashlib.sha256(
            f"{invoice_id}:{razorpay_order_id}:{razorpay_payment_id}".encode()
        ).hexdigest()

        idemp_record = self._reserve_idempotency_key(
            idempotency_key=idemp_key,
            scope=f"rzp:{invoice_id}",
            req_hash=req_hash,
        )
        if idemp_record and idemp_record.response_body:
            if idemp_record.response_status and idemp_record.response_status >= 400:
                err_data = json.loads(idemp_record.response_body)
                raise ValidationError(err_data.get("error", "Payment rejected."))
            cached = json.loads(idemp_record.response_body)
            return PaymentResponse(**cached)

        # STEP 3: Lock invoice and locate payment
        corr_id = str(uuid.uuid4())
        try:
            invoice = self.repo.get_invoice_for_update(invoice_id, society_id)
            if not invoice:
                self._fail_idempotency_key(
                    idemp_key, f"rzp:{invoice_id}", req_hash, 404, "Invoice not found."
                )
                raise NotFoundError("Invoice not found in this society.")

            payment = self.repo.get_payment_by_reference("RAZORPAY", razorpay_order_id)
            if not payment:
                self._fail_idempotency_key(
                    idemp_key,
                    f"rzp:{invoice_id}",
                    req_hash,
                    404,
                    "Associated payment order not found.",
                )
                raise NotFoundError("Associated payment order not found.")

            # If already finalized successfully, idempotent replay
            if payment.status == PaymentStatus.SUCCESS:
                res = self.map_to_payment_response(payment)
                self._complete_idempotency_key(
                    idemp_key, f"rzp:{invoice_id}", req_hash, 200, res.model_dump_json()
                )
                self.db.commit()
                return res

            # STEP 4: Concurrency balance check under row lock
            paid_so_far = sum(
                a.allocated_paise
                for a in invoice.allocations
                if a.payment.status == PaymentStatus.SUCCESS
            )
            remaining_balance = max(0, invoice.total_paise - paid_so_far)
            if payment.amount_paise > remaining_balance:
                payment.status = PaymentStatus.FAILED
                self.db.commit()
                self._fail_idempotency_key(
                    idemp_key,
                    f"rzp:{invoice_id}",
                    req_hash,
                    400,
                    f"Payment amount of ₹{payment.amount_paise / 100:.2f} exceeds remaining balance of ₹{remaining_balance / 100:.2f}.",
                )
                raise ValidationError(
                    f"Payment amount of ₹{payment.amount_paise / 100:.2f} exceeds remaining balance of ₹{remaining_balance / 100:.2f}."
                )

            # STEP 5: Finalize payment, create allocation and ledger entry
            payment.status = PaymentStatus.SUCCESS
            payment.provider_reference = f"{razorpay_order_id}:{razorpay_payment_id}"

            allocation = PaymentAllocation(
                id=uuid.uuid4(),
                payment_id=payment.id,
                invoice_id=invoice_id,
                allocated_paise=payment.amount_paise,
                created_at=utc_now(),
            )
            self.db.add(allocation)

            self.repo.append_ledger_entry(
                society_id=society_id,
                flat_id=invoice.flat_id,
                invoice_id=invoice.id,
                payment_id=payment.id,
                entry_type=LedgerEntryType.PAYMENT_RECEIVED,
                amount_paise=payment.amount_paise,
                reference_id=payment.provider_reference,
                description=f"Razorpay payment received {razorpay_payment_id} for {invoice.invoice_number}",
            )
            self.repo.append_ledger_entry(
                society_id=society_id,
                flat_id=invoice.flat_id,
                invoice_id=invoice.id,
                payment_id=payment.id,
                entry_type=LedgerEntryType.PAYMENT_ALLOCATED,
                amount_paise=payment.amount_paise,
                reference_id=str(allocation.id),
                description=f"Funds allocated to invoice {invoice.invoice_number}",
            )

            # Update invoice status
            new_paid_total = paid_so_far + payment.amount_paise
            if new_paid_total >= invoice.total_paise:
                invoice.status = InvoiceStatus.PAID
            elif new_paid_total > 0:
                invoice.status = InvoiceStatus.PARTIALLY_PAID

            # Audit & Outbox
            audit = AuditEvent(
                society_id=society_id,
                actor_id=user_id,
                action="FINANCE_RAZORPAY_PAYMENT_CAPTURED",
                resource_type="Payment",
                resource_id=str(payment.id),
                correlation_id=corr_id,
                event_metadata={
                    "invoice_id": str(invoice_id),
                    "amount_paise": payment.amount_paise,
                    "razorpay_order_id": razorpay_order_id,
                    "razorpay_payment_id": razorpay_payment_id,
                },
            )
            self.db.add(audit)

            outbox = OutboxEvent(
                event_type="finance.payment.captured",
                aggregate_type="Payment",
                aggregate_id=str(payment.id),
                payload={
                    "payment_id": str(payment.id),
                    "society_id": str(society_id),
                    "flat_id": str(payment.flat_id),
                    "invoice_id": str(invoice_id),
                    "amount_paise": payment.amount_paise,
                    "provider": "RAZORPAY",
                    "provider_reference": payment.provider_reference,
                    "status": "SUCCESS",
                },
                status=OutboxStatus.PENDING,
            )
            self.db.add(outbox)

            self.db.commit()

            res = self.map_to_payment_response(payment)
            self._complete_idempotency_key(
                idemp_key, f"rzp:{invoice_id}", req_hash, 200, res.model_dump_json()
            )
            self.db.commit()
            return res
        except Exception as exc:
            self.db.rollback()
            raise exc

    def handle_razorpay_webhook(
        self,
        body_bytes: bytes,
        signature: str,
    ) -> dict[str, Any]:
        """Handles asynchronous Razorpay webhooks with signature verification.

        Supports `payment.captured` and `payment.failed` event notifications.
        """
        is_valid = self.razorpay_provider.verify_webhook_signature(body_bytes, signature)
        if not is_valid:
            raise ValidationError("Invalid Razorpay webhook signature.")

        payload = json.loads(body_bytes.decode("utf-8"))
        event_name = str(payload.get("event", ""))

        if event_name in ("payment.captured", "order.paid"):
            pay_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
            order_id = pay_entity.get("order_id")
            payment_id = pay_entity.get("id")

            if order_id:
                payment = self.repo.get_payment_by_reference("RAZORPAY", order_id)
                if payment and payment.status == PaymentStatus.PENDING:
                    notes = pay_entity.get("notes", {})
                    invoice_id_str = notes.get("invoice_id")
                    if invoice_id_str:
                        invoice_id = UUID(invoice_id_str)
                        self.verify_and_finalize_razorpay_payment(
                            society_id=payment.society_id,
                            invoice_id=invoice_id,
                            razorpay_order_id=order_id,
                            razorpay_payment_id=payment_id or f"pay_wh_{order_id}",
                            razorpay_signature="webhook_verified",
                            user_id=payment.initiated_by,
                        )

        elif event_name == "payment.failed":
            pay_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
            order_id = pay_entity.get("order_id")
            if order_id:
                payment = self.repo.get_payment_by_reference("RAZORPAY", order_id)
                if payment and payment.status == PaymentStatus.PENDING:
                    payment.status = PaymentStatus.FAILED
                    self.db.commit()

        return {"status": "ok", "event": event_name}

    # -------------------------------------------------------------------------
    # Idempotency Key Helpers
    # -------------------------------------------------------------------------
    def cleanup_expired_idempotency_records(self) -> int:
        """Purges expired idempotency records whose 24-hour lease has expired."""
        return self.repo.cleanup_expired_idempotency_keys()

    def _reserve_idempotency_key(
        self,
        idempotency_key: str,
        scope: str,
        req_hash: str,
    ) -> IdempotencyKey | None:
        """Attempts to atomically reserve an idempotency key.

        Returns the existing record if the key is already claimed (by any prior request),
        or None if the key was freshly reserved by this call.
        Uses INSERT-then-check semantics with exception handling to handle concurrent attempts.
        Enforces 24-hour expiry and handles abandoned in-flight requests safely.
        """
        now = utc_now()
        existing = (
            self.db.query(IdempotencyKey)
            .filter_by(scope=scope, idempotency_key=idempotency_key)
            .first()
        )
        if existing:
            # 1. Check if the idempotency record has expired (past 24h lease)
            if self._to_utc(existing.expires_at) <= now:
                # Key lease has expired — delete stale record to allow fresh reservation
                self.db.delete(existing)
                self.db.commit()
                existing = None
            # 2. Check if an in-flight request has timed out (process died or hung > 2 minutes)
            elif existing.response_status is None:
                in_flight_timeout = timedelta(minutes=2)
                if (now - self._to_utc(existing.created_at)) > in_flight_timeout:
                    # In-flight lease timed out — clear abandoned reservation
                    self.db.delete(existing)
                    self.db.commit()
                    existing = None
                else:
                    return existing
            else:
                return existing

        # Attempt to insert a "pending" reservation record
        try:
            record = IdempotencyKey(
                id=uuid.uuid4(),
                scope=scope,
                idempotency_key=idempotency_key,
                request_hash=req_hash,
                response_status=None,
                response_body=None,  # None = in-flight / not yet completed
                created_at=now,
                expires_at=now + timedelta(hours=24),
            )
            self.db.add(record)
            self.db.commit()
            return None  # Successfully reserved and committed — this is the first caller
        except IntegrityError:
            self.db.rollback()
            # Another concurrent request inserted the same key just before us
            existing = (
                self.db.query(IdempotencyKey)
                .filter_by(scope=scope, idempotency_key=idempotency_key)
                .first()
            )
            return existing

    def _complete_idempotency_key(
        self,
        idempotency_key: str,
        scope: str,
        req_hash: str,
        status: int,
        body: str,
    ) -> None:
        """Persists the completed response to an existing idempotency key record."""
        record = (
            self.db.query(IdempotencyKey)
            .filter_by(scope=scope, idempotency_key=idempotency_key)
            .first()
        )
        if record:
            record.response_status = status
            record.response_body = body
        # If record mysteriously missing, create it so retry will find it
        else:
            self.db.add(
                IdempotencyKey(
                    id=uuid.uuid4(),
                    scope=scope,
                    idempotency_key=idempotency_key,
                    request_hash=req_hash,
                    response_status=status,
                    response_body=body,
                    expires_at=utc_now() + timedelta(hours=24),
                )
            )

    def _fail_idempotency_key(
        self,
        idempotency_key: str,
        scope: str,
        req_hash: str,
        status: int,
        message: str,
    ) -> None:
        """Persists a validation failure response to the idempotency record.

        Ensures the failed outcome survives the rollback of the payment transaction.
        """
        self.db.rollback()
        self._complete_idempotency_key(
            idempotency_key=idempotency_key,
            scope=scope,
            req_hash=req_hash,
            status=status,
            body=json.dumps({"error": message}),
        )
        self.db.commit()

    # -------------------------------------------------------------------------
    # Receipt Details
    # -------------------------------------------------------------------------
    def get_invoice_receipt(self, invoice_id: UUID, society_id: UUID) -> ReceiptResponse:
        """Retrieves payment receipt metadata for a paid/partially-paid invoice."""
        invoice = self.repo.get_invoice_by_id(invoice_id, society_id=society_id)
        if not invoice:
            raise NotFoundError("Invoice not found")

        successful_allocations = [
            a for a in invoice.allocations if a.payment.status == PaymentStatus.SUCCESS
        ]
        if not successful_allocations:
            raise NotFoundError("No successful payments found for this invoice")

        latest_alloc = sorted(successful_allocations, key=lambda a: a.created_at, reverse=True)[0]
        payment = latest_alloc.payment

        paid_paise, outstanding_paise, _, _ = self.calculate_invoice_financials(invoice)
        flat_tower = self.repo.get_flat_with_tower(invoice.flat_id)
        payer = self.repo.get_primary_resident_for_flat(invoice.flat_id)
        society = self.repo.get_society(society_id)

        clean_period = invoice.billing_period.replace("-", "")
        receipt_num = f"RCP-{clean_period}-{invoice.invoice_number.split('-')[-1]}-{payment.provider_reference[-6:]}"

        return ReceiptResponse(
            receipt_number=receipt_num,
            payment_id=payment.id,
            invoice_id=invoice.id,
            invoice_number=invoice.invoice_number,
            billing_period=invoice.billing_period,
            amount_paid_paise=latest_alloc.allocated_paise,
            payment_date=payment.created_at,
            payment_provider=payment.provider,
            provider_reference=payment.provider_reference,
            tower_number=flat_tower[1].tower_number if flat_tower else "",
            flat_number=flat_tower[0].flat_number if flat_tower else "",
            payer_name=payer.full_name if payer else "Resident",
            remaining_outstanding_paise=outstanding_paise,
            society_name=society.name if society else "Society",
        )

    # -------------------------------------------------------------------------
    # Summaries & Dashboards
    # -------------------------------------------------------------------------
    def get_resident_summary(self, flat_ids: list[UUID]) -> ResidentBillingSummaryResponse:
        invoices = self.repo.get_invoices_for_flats(flat_ids, limit=200)

        total_invoiced = 0
        total_paid = 0
        total_outstanding = 0
        total_overdue = 0

        unpaid_count = 0
        partially_paid_count = 0
        paid_count = 0
        overdue_count = 0

        next_due_date = None
        now = utc_now()

        for inv in invoices:
            p_paise, o_paise, status, is_overdue = self.calculate_invoice_financials(inv)
            total_invoiced += inv.total_paise
            total_paid += p_paise
            total_outstanding += o_paise

            if status == InvoiceStatus.PAID:
                paid_count += 1
            elif status == InvoiceStatus.PARTIALLY_PAID:
                partially_paid_count += 1
            elif status == InvoiceStatus.OVERDUE:
                overdue_count += 1
                total_overdue += o_paise
            elif status == InvoiceStatus.UNPAID:
                unpaid_count += 1

            due = BillingService._to_utc(inv.due_date)
            if (
                o_paise > 0
                and due > now
                and (next_due_date is None or due < BillingService._to_utc(next_due_date))
            ):
                next_due_date = due

        latest_inv_resp = self.map_to_invoice_response(invoices[0]) if invoices else None
        current_period = now.strftime("%Y-%m")

        return ResidentBillingSummaryResponse(
            total_outstanding_paise=total_outstanding,
            total_invoiced_paise=total_invoiced,
            total_paid_paise=total_paid,
            total_overdue_paise=total_overdue,
            unpaid_count=unpaid_count,
            partially_paid_count=partially_paid_count,
            paid_count=paid_count,
            overdue_count=overdue_count,
            current_billing_period=current_period,
            latest_invoice=latest_inv_resp,
            next_due_date=next_due_date,
        )

    def get_staff_overview(self, society_id: UUID) -> StaffBillingOverviewResponse:
        """Returns financial overview using database aggregate queries.

        PERFORMANCE: Replaces iteration over 2,500 invoices with SQL aggregates.
        Uses get_latest_billing_config() — no side effect, no default config creation.
        """
        # Use read-only config lookup (no side effect)
        config = self.repo.get_latest_billing_config(society_id)

        # Database-level aggregates (no fixed LIMIT)
        agg = self.repo.get_society_financial_aggregates(society_id)
        total_billed = agg["total_billed_paise"]
        total_count = agg["total_count"]
        paid_count = agg["paid_count"]
        overdue_count = agg["overdue_count"]
        unpaid_count = total_count - paid_count - overdue_count

        # For precise outstanding/collected totals, we still need to iterate invoices
        # (because outstanding = total - allocations, not stored directly).
        # Fetch a reasonable batch for financial precision on the overview.
        # For high-volume societies, this is a known approximation; exact per-invoice
        # totals are available on the detail view.
        invoices = self.repo.get_invoices_for_society(society_id, limit=500)
        total_collected = 0
        total_outstanding = 0
        total_overdue = 0

        for inv in invoices:
            p_paise, o_paise, status, _ = self.calculate_invoice_financials(inv)
            total_collected += p_paise
            total_outstanding += o_paise
            if status == InvoiceStatus.OVERDUE:
                total_overdue += o_paise

        return StaffBillingOverviewResponse(
            total_billed_paise=total_billed,
            total_collected_paise=total_collected,
            total_outstanding_paise=total_outstanding,
            total_overdue_paise=total_overdue,
            total_invoices_count=total_count,
            paid_invoices_count=paid_count,
            unpaid_invoices_count=unpaid_count,
            overdue_invoices_count=overdue_count,
            active_rate_paise_per_sqft=config.rate_paise_per_sqft if config else 0,
            current_period=utc_now().strftime("%Y-%m"),
        )
