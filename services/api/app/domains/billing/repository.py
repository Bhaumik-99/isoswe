"""Billing Domain SQLAlchemy Repository

Provides authoritative data access and database query optimization for:
- Billing configuration
- Invoices and line items
- Payments and allocations
- Immutable financial ledger entries
- Batch billing runs
"""

import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import ConflictError
from app.domains.billing.models import (
    BillingConfiguration,
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
from app.domains.identity.models import (
    Flat,
    FlatMembership,
    MembershipStatus,
    Society,
    Tower,
    User,
)
from app.domains.reliability.models import IdempotencyKey


def utc_now() -> datetime:
    return datetime.now(UTC)


class BillingRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # -------------------------------------------------------------------------
    # Configuration
    # -------------------------------------------------------------------------
    def get_or_create_billing_config(self, society_id: UUID) -> BillingConfiguration:
        """Retrieves active billing configuration for society, creating default (₹6.50 / 650 paise) if missing.

        NOTE: This method has a side effect (creates config if absent). Do NOT call from
        read-only dashboard/reporting methods. Use get_billing_config_for_period() for
        historical-period-correct rate selection, or get_latest_billing_config() for
        current-period display.
        """
        stmt = (
            select(BillingConfiguration)
            .where(BillingConfiguration.society_id == society_id)
            .order_by(BillingConfiguration.effective_from.desc())
        )
        config = self.db.scalars(stmt).first()
        if not config:
            config = BillingConfiguration(
                id=uuid.uuid4(),
                society_id=society_id,
                rate_paise_per_sqft=650,  # ₹6.50 / sq ft = 650 paise
                currency="INR",
                effective_from=utc_now(),
                due_day=10,
            )
            self.db.add(config)
            self.db.flush()
        return config

    def get_billing_config_for_period(
        self, society_id: UUID, billing_period_start: datetime
    ) -> BillingConfiguration | None:
        """Returns the configuration that was effective at the start of the requested billing period.

        INVARIANT: Selects the latest config whose effective_from <= billing_period_start.
        This ensures historical invoices always use the rate that was active at the time,
        even if the rate was later changed.
        """
        stmt = (
            select(BillingConfiguration)
            .where(
                BillingConfiguration.society_id == society_id,
                BillingConfiguration.effective_from <= billing_period_start,
            )
            .order_by(BillingConfiguration.effective_from.desc())
        )
        return self.db.scalars(stmt).first()

    def get_all_billing_configs(self, society_id: UUID) -> list[BillingConfiguration]:
        """Returns all billing configurations for a society ordered by effective date ascending."""
        stmt = (
            select(BillingConfiguration)
            .where(BillingConfiguration.society_id == society_id)
            .order_by(BillingConfiguration.effective_from.asc())
        )
        return list(self.db.scalars(stmt).all())

    def create_default_billing_config(
        self, society_id: UUID, effective_from: datetime | None = None
    ) -> BillingConfiguration:
        """Creates the initial default billing configuration with an explicit effective date."""
        config = BillingConfiguration(
            id=uuid.uuid4(),
            society_id=society_id,
            rate_paise_per_sqft=650,  # ₹6.50 / sq ft = 650 paise
            currency="INR",
            effective_from=effective_from or utc_now(),
            due_day=10,
        )
        self.db.add(config)
        self.db.flush()
        return config

    def get_latest_billing_config(self, society_id: UUID) -> BillingConfiguration | None:
        """Returns the most recently created configuration WITHOUT creating a default.

        Safe to call from read-only dashboard and reporting methods.
        Returns None if no configuration exists.
        """
        stmt = (
            select(BillingConfiguration)
            .where(BillingConfiguration.society_id == society_id)
            .order_by(BillingConfiguration.effective_from.desc())
        )
        return self.db.scalars(stmt).first()

    # -------------------------------------------------------------------------
    # Invoices
    # -------------------------------------------------------------------------
    def get_invoice_by_id(self, invoice_id: UUID, society_id: UUID | None = None) -> Invoice | None:
        """Retrieves invoice with eager loaded line items and allocations."""
        stmt = (
            select(Invoice)
            .options(
                joinedload(Invoice.line_items),
                joinedload(Invoice.allocations).joinedload(PaymentAllocation.payment),
            )
            .where(Invoice.id == invoice_id)
        )
        if society_id:
            stmt = stmt.where(Invoice.society_id == society_id)
        return self.db.scalars(stmt).unique().first()

    def get_invoice_for_update(self, invoice_id: UUID, society_id: UUID) -> Invoice | None:
        """Fetches invoice with a PostgreSQL SELECT ... FOR UPDATE row lock.

        MUST be called inside an active transaction.
        After acquiring the lock, reload allocations separately to get the freshest data.
        This prevents concurrent payment requests from over-allocating funds to the same invoice.
        """
        # Step 1: Lock the invoice row (plain query, no joinedload — joinedload + FOR UPDATE
        # can produce ambiguous locking behavior with PostgreSQL).
        lock_stmt = (
            select(Invoice)
            .where(
                Invoice.id == invoice_id,
                Invoice.society_id == society_id,
            )
            .with_for_update()
        )
        invoice = self.db.scalar(lock_stmt)
        if not invoice:
            return None

        # Step 2: Eager-load related data in a separate query now that the row is locked.
        full_stmt = (
            select(Invoice)
            .options(
                joinedload(Invoice.line_items),
                joinedload(Invoice.allocations).joinedload(PaymentAllocation.payment),
            )
            .where(Invoice.id == invoice_id)
        )
        return self.db.scalars(full_stmt).unique().first()

    def get_invoices_for_period(self, society_id: UUID, billing_period: str) -> list[Invoice]:
        """Fetches all invoices for a society and billing period in a single query.

        Used by billing preview/generation to avoid N+1 queries.
        Returns lightweight Invoice objects (no eager-loading of allocations).
        """
        stmt = select(Invoice).where(
            Invoice.society_id == society_id,
            Invoice.billing_period == billing_period,
        )
        return list(self.db.scalars(stmt).all())

    def get_invoice_by_flat_and_period(
        self, society_id: UUID, flat_id: UUID, billing_period: str
    ) -> Invoice | None:
        stmt = select(Invoice).where(
            Invoice.society_id == society_id,
            Invoice.flat_id == flat_id,
            Invoice.billing_period == billing_period,
        )
        return self.db.scalars(stmt).first()

    def get_invoices_for_flats(
        self,
        flat_ids: list[UUID],
        billing_period: str | None = None,
        status: InvoiceStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Invoice]:
        if not flat_ids:
            return []
        stmt = (
            select(Invoice)
            .options(
                joinedload(Invoice.line_items),
                joinedload(Invoice.allocations).joinedload(PaymentAllocation.payment),
            )
            .where(Invoice.flat_id.in_(flat_ids))
        )
        if billing_period:
            stmt = stmt.where(Invoice.billing_period == billing_period)
        if status:
            stmt = stmt.where(Invoice.status == status)
        stmt = stmt.order_by(Invoice.billing_period.desc(), Invoice.created_at.desc())
        stmt = stmt.limit(limit).offset(offset)
        return list(self.db.scalars(stmt).unique().all())

    def get_invoices_for_society(
        self,
        society_id: UUID,
        billing_period: str | None = None,
        tower_number: str | None = None,
        flat_number: str | None = None,
        status: InvoiceStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Invoice]:
        stmt = (
            select(Invoice)
            .join(Flat, Flat.id == Invoice.flat_id)
            .join(Tower, Tower.id == Flat.tower_id)
            .options(
                joinedload(Invoice.line_items),
                joinedload(Invoice.allocations).joinedload(PaymentAllocation.payment),
            )
            .where(Invoice.society_id == society_id)
        )
        if billing_period:
            stmt = stmt.where(Invoice.billing_period == billing_period)
        if tower_number:
            stmt = stmt.where(Tower.tower_number == tower_number)
        if flat_number:
            stmt = stmt.where(Flat.flat_number == flat_number)
        if status:
            stmt = stmt.where(Invoice.status == status)
        stmt = stmt.order_by(Invoice.billing_period.desc(), Tower.tower_number, Flat.flat_number)
        stmt = stmt.limit(limit).offset(offset)
        return list(self.db.scalars(stmt).unique().all())

    def count_invoices_for_society(
        self,
        society_id: UUID,
        billing_period: str | None = None,
        tower_number: str | None = None,
        flat_number: str | None = None,
        status: InvoiceStatus | None = None,
    ) -> int:
        stmt = (
            select(func.count(Invoice.id))
            .join(Flat, Flat.id == Invoice.flat_id)
            .join(Tower, Tower.id == Flat.tower_id)
            .where(Invoice.society_id == society_id)
        )
        if billing_period:
            stmt = stmt.where(Invoice.billing_period == billing_period)
        if tower_number:
            stmt = stmt.where(Tower.tower_number == tower_number)
        if flat_number:
            stmt = stmt.where(Flat.flat_number == flat_number)
        if status:
            stmt = stmt.where(Invoice.status == status)
        return self.db.scalar(stmt) or 0

    def create_invoice(
        self,
        society_id: UUID,
        flat_id: UUID,
        billing_period: str,
        invoice_number: str,
        area_sqft_snapshot: int,
        rate_paise_per_sqft_snapshot: int,
        subtotal_paise: int,
        total_paise: int,
        due_date: datetime,
        line_items_data: list[dict[str, Any]],
    ) -> Invoice:
        invoice = Invoice(
            id=uuid.uuid4(),
            society_id=society_id,
            flat_id=flat_id,
            billing_period=billing_period,
            invoice_number=invoice_number,
            area_sqft_snapshot=area_sqft_snapshot,
            rate_paise_per_sqft_snapshot=rate_paise_per_sqft_snapshot,
            subtotal_paise=subtotal_paise,
            total_paise=total_paise,
            due_date=due_date,
            status=InvoiceStatus.UNPAID,
        )
        self.db.add(invoice)
        self.db.flush()

        for item in line_items_data:
            line_item = InvoiceLineItem(
                id=uuid.uuid4(),
                invoice_id=invoice.id,
                description=item["description"],
                quantity=item.get("quantity", 1),
                unit_rate_paise=item["unit_rate_paise"],
                amount_paise=item["amount_paise"],
            )
            self.db.add(line_item)

        self.db.flush()
        return invoice

    def create_invoices_batch(
        self,
        invoices: list[Invoice],
        line_items: list[InvoiceLineItem],
        ledger_entries: list[FinancialLedgerEntry],
    ) -> None:
        """Batch persists invoices, line items, and ledger entries in bounded chunks without per-flat flushes."""
        self.db.add_all(invoices)
        self.db.add_all(line_items)
        self.db.add_all(ledger_entries)
        self.db.flush()

    # -------------------------------------------------------------------------
    # Payments & Allocations
    # -------------------------------------------------------------------------
    def get_payment_by_id(self, payment_id: UUID, society_id: UUID | None = None) -> Payment | None:
        stmt = (
            select(Payment)
            .options(
                joinedload(Payment.allocations).joinedload(PaymentAllocation.invoice),
            )
            .where(Payment.id == payment_id)
        )
        if society_id:
            stmt = stmt.where(Payment.society_id == society_id)
        return self.db.scalars(stmt).unique().first()

    def get_payment_for_update(self, payment_id: UUID, society_id: UUID) -> Payment | None:
        """Fetches payment with a PostgreSQL SELECT ... FOR UPDATE row lock.

        MUST be called inside an active transaction.
        After acquiring the lock, reload allocations separately to get the freshest data.
        """
        lock_stmt = (
            select(Payment)
            .where(
                Payment.id == payment_id,
                Payment.society_id == society_id,
            )
            .with_for_update()
        )
        payment = self.db.scalar(lock_stmt)
        if not payment:
            return None
        full_stmt = (
            select(Payment)
            .options(
                joinedload(Payment.allocations).joinedload(PaymentAllocation.invoice),
            )
            .where(Payment.id == payment_id)
        )
        return self.db.scalars(full_stmt).unique().first()

    def get_payment_by_reference(self, provider: str, provider_reference: str) -> Payment | None:
        """Finds a payment record by payment provider and reference (e.g. Razorpay order_id or payment_id)."""
        stmt = (
            select(Payment)
            .options(
                joinedload(Payment.allocations).joinedload(PaymentAllocation.invoice),
            )
            .where(
                Payment.provider == provider,
                Payment.provider_reference == provider_reference,
            )
        )
        return self.db.scalars(stmt).unique().first()

    def get_payments_for_flats(
        self,
        flat_ids: list[UUID],
        limit: int = 50,
        offset: int = 0,
    ) -> list[Payment]:
        if not flat_ids:
            return []
        stmt = (
            select(Payment)
            .options(
                joinedload(Payment.allocations).joinedload(PaymentAllocation.invoice),
            )
            .where(Payment.flat_id.in_(flat_ids))
            .order_by(Payment.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(stmt).unique().all())

    def create_payment(
        self,
        society_id: UUID,
        flat_id: UUID,
        amount_paise: int,
        provider: str,
        provider_reference: str,
        status: PaymentStatus,
        initiated_by: UUID,
        currency: str = "INR",
    ) -> Payment:
        payment = Payment(
            id=uuid.uuid4(),
            society_id=society_id,
            flat_id=flat_id,
            amount_paise=amount_paise,
            currency=currency,
            provider=provider,
            provider_reference=provider_reference,
            status=status,
            initiated_by=initiated_by,
        )
        self.db.add(payment)
        self.db.flush()
        return payment

    def create_payment_allocation(
        self,
        payment_id: UUID,
        invoice_id: UUID,
        allocated_paise: int,
    ) -> PaymentAllocation:
        # Enforce that payment and invoice belong to identical society and flat
        payment = self.db.get(Payment, payment_id)
        invoice = self.db.get(Invoice, invoice_id)
        if payment and invoice:
            if payment.society_id != invoice.society_id:
                raise ConflictError("Cross-society payment allocation rejected: society mismatch")
            if payment.flat_id != invoice.flat_id:
                raise ConflictError("Cross-flat payment allocation rejected: flat mismatch")

        allocation = PaymentAllocation(
            id=uuid.uuid4(),
            payment_id=payment_id,
            invoice_id=invoice_id,
            allocated_paise=allocated_paise,
        )
        self.db.add(allocation)
        self.db.flush()
        return allocation

    # -------------------------------------------------------------------------
    # Financial Ledger
    # -------------------------------------------------------------------------
    def append_ledger_entry(
        self,
        society_id: UUID,
        flat_id: UUID,
        entry_type: LedgerEntryType,
        amount_paise: int,
        description: str,
        invoice_id: UUID | None = None,
        payment_id: UUID | None = None,
        reference_id: str | None = None,
    ) -> FinancialLedgerEntry:
        """Appends an immutable financial transaction journal entry."""
        entry = FinancialLedgerEntry(
            id=uuid.uuid4(),
            society_id=society_id,
            flat_id=flat_id,
            invoice_id=invoice_id,
            payment_id=payment_id,
            entry_type=entry_type,
            amount_paise=amount_paise,
            reference_id=reference_id,
            description=description,
        )
        self.db.add(entry)
        self.db.flush()
        return entry

    # -------------------------------------------------------------------------
    # Batch Billing Runs
    # -------------------------------------------------------------------------
    def create_billing_run(
        self,
        society_id: UUID,
        billing_period: str,
        total_eligible_flats: int,
        total_invoiced_flats: int,
        total_skipped_flats: int,
        total_charges_paise: int,
        initiated_by: UUID,
        status: str = "COMPLETED",
        metadata: dict[str, Any] | None = None,
    ) -> BillingRun:
        run = BillingRun(
            id=uuid.uuid4(),
            society_id=society_id,
            billing_period=billing_period,
            total_eligible_flats=total_eligible_flats,
            total_invoiced_flats=total_invoiced_flats,
            total_skipped_flats=total_skipped_flats,
            total_charges_paise=total_charges_paise,
            status=status,
            initiated_by=initiated_by,
            run_metadata=metadata or {},
        )
        self.db.add(run)
        self.db.flush()
        return run

    def get_billing_run_by_id(
        self, run_id: UUID, society_id: UUID | None = None
    ) -> BillingRun | None:
        stmt = select(BillingRun).where(BillingRun.id == run_id)
        if society_id:
            stmt = stmt.where(BillingRun.society_id == society_id)
        return self.db.scalars(stmt).first()

    # -------------------------------------------------------------------------
    # Auxiliary Flat, Society, and Membership Helpers
    # -------------------------------------------------------------------------
    def get_flat_with_tower(self, flat_id: UUID) -> tuple[Flat, Tower] | None:
        stmt = select(Flat, Tower).join(Tower, Tower.id == Flat.tower_id).where(Flat.id == flat_id)
        result = self.db.execute(stmt).first()
        if not result:
            return None
        return result[0], result[1]

    def get_society(self, society_id: UUID) -> Society | None:
        return self.db.get(Society, society_id)

    def get_primary_resident_for_flat(self, flat_id: UUID) -> User | None:
        stmt = (
            select(User)
            .join(FlatMembership, FlatMembership.user_id == User.id)
            .where(
                FlatMembership.flat_id == flat_id,
                FlatMembership.status == MembershipStatus.APPROVED,
            )
            .order_by(FlatMembership.is_primary.desc(), FlatMembership.created_at.asc())
        )
        return self.db.scalars(stmt).first()

    def get_flats_in_society(self, society_id: UUID) -> list[tuple[Flat, Tower]]:
        stmt = (
            select(Flat, Tower)
            .join(Tower, Tower.id == Flat.tower_id)
            .where(Flat.society_id == society_id)
            .order_by(Tower.tower_number, Flat.flat_number)
        )
        rows = self.db.execute(stmt).all()
        return [(r[0], r[1]) for r in rows]

    def get_society_financial_aggregates(
        self, society_id: UUID, billing_period: str | None = None
    ) -> dict[str, Any]:
        """Returns aggregate financial totals for a society using a single SQL query.

        Replaces in-memory iteration over 2,500+ invoices with a database aggregate.
        INVARIANT: Outstanding amount is derived from database-persisted invoice status
        for the aggregate display; individual invoice outstanding is still calculated
        from allocations in detail views.
        """
        base_filter = [Invoice.society_id == society_id]
        if billing_period:
            base_filter.append(Invoice.billing_period == billing_period)

        # Aggregate invoice totals and counts by status
        agg = self.db.execute(
            select(
                func.count(Invoice.id).label("total_count"),
                func.sum(Invoice.total_paise).label("total_billed_paise"),
                func.count(Invoice.id)
                .filter(Invoice.status == InvoiceStatus.PAID)
                .label("paid_count"),
                func.count(Invoice.id)
                .filter(Invoice.status == InvoiceStatus.OVERDUE)
                .label("overdue_count"),
            ).where(*base_filter)
        ).one()

        return {
            "total_count": agg.total_count or 0,
            "total_billed_paise": agg.total_billed_paise or 0,
            "paid_count": agg.paid_count or 0,
            "overdue_count": agg.overdue_count or 0,
        }

    def cleanup_expired_idempotency_keys(self) -> int:
        """Deletes expired idempotency records from the database.

        Returns the number of deleted records.
        """
        now = utc_now()
        stmt = delete(IdempotencyKey).where(IdempotencyKey.expires_at <= now)
        res = self.db.execute(stmt)
        self.db.commit()
        return res.rowcount or 0
