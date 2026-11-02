"""Billing Domain Service Layer

Coordinates authoritative business rules, transaction safety, and invariants for:
1. Previewing and executing monthly billing runs.
2. Generating immutable invoices and line items.
3. Processing simulated resident payments and allocations.
4. Appending to the immutable financial ledger.
5. Emitting transactional audit and outbox events.
"""

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.domains.billing.models import (
    BillingRun,
    Invoice,
    InvoiceStatus,
    LedgerEntryType,
    PaymentStatus,
)
from app.domains.billing.provider import PaymentProvider, SimulatedPaymentProvider
from app.domains.billing.repository import BillingRepository
from app.domains.billing.schemas import (
    BillingRunPreviewResponse,
    EligibleFlatDetail,
    ExcludedFlatDetail,
    InvoiceLineItemSchema,
    InvoiceResponse,
    PaymentAllocationSchema,
    PaymentResponse,
    ReceiptResponse,
    ResidentBillingSummaryResponse,
    StaffBillingOverviewResponse,
)
from app.domains.identity.models import FlatStatus
from app.domains.reliability.models import AuditEvent, IdempotencyKey, OutboxEvent, OutboxStatus


def utc_now() -> datetime:
    return datetime.now(UTC)


class BillingService:
    def __init__(
        self,
        db: Session,
        payment_provider: PaymentProvider | None = None,
    ) -> None:
        self.db = db
        self.repo = BillingRepository(db)
        self.payment_provider = payment_provider or SimulatedPaymentProvider()

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
        """Previews expected billing charges, eligible flats, and exclusion reasons before execution."""
        config = self.repo.get_or_create_billing_config(society_id)
        rate = config.rate_paise_per_sqft

        # Default due date: due_day of following month
        year, month = map(int, billing_period.split("-"))
        if month == 12:
            due_date = datetime(year + 1, 1, min(config.due_day, 28), 23, 59, 59, tzinfo=UTC)
        else:
            due_date = datetime(year, month + 1, min(config.due_day, 28), 23, 59, 59, tzinfo=UTC)

        all_flats = self.repo.get_flats_in_society(society_id)
        eligible_flats: list[EligibleFlatDetail] = []
        excluded_flats: list[ExcludedFlatDetail] = []
        already_invoiced_count = 0
        total_expected_paise = 0

        for flat, tower in all_flats:
            # 1. Check if already invoiced for this period
            existing = self.repo.get_invoice_by_flat_and_period(society_id, flat.id, billing_period)
            if existing:
                already_invoiced_count += 1
                excluded_flats.append(
                    ExcludedFlatDetail(
                        flat_id=flat.id,
                        tower_number=tower.tower_number,
                        flat_number=flat.flat_number,
                        reason=f"Already invoiced for period {billing_period} ({existing.invoice_number})",
                    )
                )
                continue

            # 2. Check flat operational status
            if flat.status == FlatStatus.UNDER_MAINTENANCE:
                excluded_flats.append(
                    ExcludedFlatDetail(
                        flat_id=flat.id,
                        tower_number=tower.tower_number,
                        flat_number=flat.flat_number,
                        reason="Flat is marked under maintenance; exempt from billing cycle",
                    )
                )
                continue

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

            # Flat is eligible
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
        """
        corr_id = correlation_id or str(uuid.uuid4())
        preview = self.preview_billing_run(society_id, billing_period)
        due_date = custom_due_date or preview.due_date

        if preview.eligible_flats_count == 0:
            # Create a completed run with 0 generated invoices
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

        config = self.repo.get_or_create_billing_config(society_id)
        rate = config.rate_paise_per_sqft

        invoiced_count = 0
        total_charges_paise = 0
        generated_invoice_ids: list[str] = []

        try:
            for item in preview.eligible_flats:
                # Generate unique invoice number: INV-YYYYMM-TOW-FLAT
                clean_period = billing_period.replace("-", "")
                invoice_num = f"INV-{clean_period}-{item.tower_number}-{item.flat_number}"

                # Calculate maintenance charge
                charge_paise = item.area_sqft * rate
                rate_inr = rate / 100

                line_items = [
                    {
                        "description": f"Monthly Maintenance ({item.area_sqft:,} sq ft @ ₹{rate_inr:.2f}/sq ft)",
                        "quantity": 1,
                        "unit_rate_paise": charge_paise,
                        "amount_paise": charge_paise,
                    }
                ]

                # 1. Persist Invoice and Line Item
                invoice = self.repo.create_invoice(
                    society_id=society_id,
                    flat_id=item.flat_id,
                    billing_period=billing_period,
                    invoice_number=invoice_num,
                    area_sqft_snapshot=item.area_sqft,
                    rate_paise_per_sqft_snapshot=rate,
                    subtotal_paise=charge_paise,
                    total_paise=charge_paise,
                    due_date=due_date,
                    line_items_data=line_items,
                )

                # 2. Append to immutable financial ledger
                self.repo.append_ledger_entry(
                    society_id=society_id,
                    flat_id=item.flat_id,
                    invoice_id=invoice.id,
                    entry_type=LedgerEntryType.CHARGE,
                    amount_paise=charge_paise,
                    description=f"Monthly maintenance charge for {item.tower_number}-{item.flat_number} ({billing_period})",
                    reference_id=invoice.invoice_number,
                )

                # 3. Create Audit Event
                audit = AuditEvent(
                    id=uuid.uuid4(),
                    society_id=society_id,
                    actor_id=actor_id,
                    action="INVOICE_GENERATED",
                    resource_type="invoice",
                    resource_id=str(invoice.id),
                    correlation_id=corr_id,
                    event_metadata={
                        "invoice_number": invoice.invoice_number,
                        "flat_id": str(item.flat_id),
                        "total_paise": charge_paise,
                        "billing_period": billing_period,
                    },
                )
                self.db.add(audit)

                # 4. Create Transactional Outbox Event
                outbox = OutboxEvent(
                    id=uuid.uuid4(),
                    event_type="billing.invoice_generated",
                    aggregate_type="invoice",
                    aggregate_id=str(invoice.id),
                    payload={
                        "invoice_id": str(invoice.id),
                        "society_id": str(society_id),
                        "flat_id": str(item.flat_id),
                        "billing_period": billing_period,
                        "total_paise": charge_paise,
                        "due_date": due_date.isoformat(),
                    },
                    status=OutboxStatus.PENDING,
                )
                self.db.add(outbox)

                invoiced_count += 1
                total_charges_paise += charge_paise
                generated_invoice_ids.append(str(invoice.id))

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
        - Allocations cannot exceed payment amount or remaining outstanding balance.
        - Payments do not overwrite invoice total.
        - Ledger is append-only.
        - Idempotent request handling via IdempotencyKey.
        """
        corr_id = correlation_id or str(uuid.uuid4())

        # Check idempotency if key provided
        if idempotency_key:
            req_hash = hashlib.sha256(
                f"{user_id}:{invoice_id}:{amount_paise}:{simulate_failure}".encode()
            ).hexdigest()
            idempotency_record = (
                self.db.query(IdempotencyKey)
                .filter_by(scope="billing_payment", idempotency_key=idempotency_key)
                .first()
            )
            if idempotency_record:
                if idempotency_record.request_hash != req_hash:
                    raise ConflictError(
                        "Idempotency key reuse with differing request payload is prohibited."
                    )
                if idempotency_record.response_body:
                    data = json.loads(idempotency_record.response_body)
                    return PaymentResponse(**data)

        # 1. Fetch & lock invoice for safe allocation concurrency
        invoice = self.repo.get_invoice_by_id(invoice_id, society_id=society_id)
        if not invoice:
            raise NotFoundError("Invoice not found in your society")

        if amount_paise <= 0:
            raise ValidationError("Payment amount must be greater than zero")

        paid_paise, outstanding_paise, status, _ = self.calculate_invoice_financials(invoice)
        if outstanding_paise <= 0:
            raise ValidationError("Invoice is already fully paid. Outstanding balance is ₹0.00.")

        if amount_paise > outstanding_paise:
            max_inr = outstanding_paise / 100
            req_inr = amount_paise / 100
            raise ValidationError(
                f"Payment amount (₹{req_inr:,.2f}) cannot exceed outstanding invoice balance (₹{max_inr:,.2f})"
            )

        # 2. Invoke payment provider
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

        try:
            # 3. Create Payment record
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

            # 4. Handle Failure flow
            if not payment_result.success:
                # Retain failed payment record without modifying invoice balance or ledger
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
                self.db.commit()

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
                return resp

            # 5. Handle Success flow
            # Create payment-to-invoice allocation
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

            # 6. Save Idempotency Key record if provided
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

            if idempotency_key:
                idemp = IdempotencyKey(
                    id=uuid.uuid4(),
                    scope="billing_payment",
                    idempotency_key=idempotency_key,
                    request_hash=hashlib.sha256(
                        f"{user_id}:{invoice_id}:{amount_paise}:{simulate_failure}".encode()
                    ).hexdigest(),
                    response_status=200,
                    response_body=json.dumps(resp.model_dump(mode="json")),
                    expires_at=utc_now() + timedelta(hours=24),
                )
                self.db.add(idemp)

            self.db.commit()
            return resp

        except Exception as exc:
            self.db.rollback()
            raise exc

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
        invoices = self.repo.get_invoices_for_society(society_id, limit=2500)
        config = self.repo.get_or_create_billing_config(society_id)

        total_billed = 0
        total_collected = 0
        total_outstanding = 0
        total_overdue = 0

        paid_count = 0
        unpaid_count = 0
        overdue_count = 0

        for inv in invoices:
            p_paise, o_paise, status, is_overdue = self.calculate_invoice_financials(inv)
            total_billed += inv.total_paise
            total_collected += p_paise
            total_outstanding += o_paise

            if status == InvoiceStatus.PAID:
                paid_count += 1
            elif status == InvoiceStatus.OVERDUE:
                overdue_count += 1
                total_overdue += o_paise
            else:
                unpaid_count += 1

        return StaffBillingOverviewResponse(
            total_billed_paise=total_billed,
            total_collected_paise=total_collected,
            total_outstanding_paise=total_outstanding,
            total_overdue_paise=total_overdue,
            total_invoices_count=len(invoices),
            paid_invoices_count=paid_count,
            unpaid_invoices_count=unpaid_count,
            overdue_invoices_count=overdue_count,
            active_rate_paise_per_sqft=config.rate_paise_per_sqft,
            current_period=utc_now().strftime("%Y-%m"),
        )
