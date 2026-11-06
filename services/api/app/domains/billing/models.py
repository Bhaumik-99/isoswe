"""Billing Domain SQLAlchemy Models

Provides persistent financial primitives for:
1. BillingConfiguration (Society maintenance rates and due date parameters)
2. Invoice (Immutable monthly maintenance billing records with snapshots)
3. InvoiceLineItem (Itemized charges composing invoice total)
4. Payment (Payment attempts and funds received via payment provider)
5. PaymentAllocation (Explicit mapping between received funds and invoices)
6. FinancialLedgerEntry (Immutable, append-only financial audit ledger)
7. BillingRun (Tracked monthly billing executions and summaries)

FINANCIAL INVARIANTS:
- All monetary fields are BIGINT integer paise (1 INR = 100 paise).
- Floating-point arithmetic is strictly prohibited.
- Ledger is append-only; corrections require compensating entries.
- Outstanding amount is derived: total_paise - sum(valid_allocated_paise).
"""

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class InvoiceStatus(str, enum.Enum):
    UNPAID = "UNPAID"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    OVERDUE = "OVERDUE"
    VOID = "VOID"


class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class LedgerEntryType(str, enum.Enum):
    CHARGE = "CHARGE"
    PAYMENT_RECEIVED = "PAYMENT_RECEIVED"
    PAYMENT_ALLOCATED = "PAYMENT_ALLOCATED"
    REVERSAL = "REVERSAL"
    ADJUSTMENT = "ADJUSTMENT"


class LateFeeCalculationMethod(str, enum.Enum):
    FLAT_FEE = "FLAT_FEE"
    PERCENTAGE_PER_MONTH = "PERCENTAGE_PER_MONTH"
    DAILY_INTEREST_PAISE = "DAILY_INTEREST_PAISE"


class BillingConfiguration(Base):
    """Society-level maintenance billing configuration."""

    __tablename__ = "billing_configurations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rate_paise_per_sqft: Mapped[int] = mapped_column(BigInteger, nullable=False, default=650)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    due_day: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "society_id", "effective_from", name="uq_billing_config_society_effective_from"
        ),
        CheckConstraint("rate_paise_per_sqft > 0", name="chk_billing_config_rate_positive"),
        CheckConstraint("due_day >= 1 AND due_day <= 28", name="chk_billing_config_due_day"),
        Index("ix_billing_config_society_effective", "society_id", "effective_from"),
    )


class Invoice(Base):
    """Monthly maintenance invoice issued to a flat."""

    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    flat_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("flats.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    billing_period: Mapped[str] = mapped_column(
        String(7), nullable=False
    )  # Format: YYYY-MM (e.g., '2026-11')
    invoice_number: Mapped[str] = mapped_column(String(64), nullable=False)
    area_sqft_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    rate_paise_per_sqft_snapshot: Mapped[int] = mapped_column(BigInteger, nullable=False)
    subtotal_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[InvoiceStatus] = mapped_column(
        SAEnum(InvoiceStatus, native_enum=False),
        nullable=False,
        default=InvoiceStatus.UNPAID,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "society_id", "flat_id", "billing_period", name="uq_invoice_society_flat_period"
        ),
        UniqueConstraint("society_id", "invoice_number", name="uq_invoice_society_number"),
        CheckConstraint("total_paise >= 0", name="chk_invoice_total_positive"),
        CheckConstraint("subtotal_paise >= 0", name="chk_invoice_subtotal_positive"),
        CheckConstraint("area_sqft_snapshot > 0", name="chk_invoice_area_positive"),
        CheckConstraint("rate_paise_per_sqft_snapshot > 0", name="chk_invoice_rate_positive"),
        Index("ix_invoices_society_period", "society_id", "billing_period"),
        Index("ix_invoices_flat_period", "flat_id", "billing_period"),
        Index("ix_invoices_flat_status", "flat_id", "status"),
    )

    # Relationships
    line_items: Mapped[list["InvoiceLineItem"]] = relationship(
        "InvoiceLineItem",
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceLineItem.created_at",
    )
    allocations: Mapped[list["PaymentAllocation"]] = relationship(
        "PaymentAllocation",
        back_populates="invoice",
        cascade="all, delete-orphan",
    )
    ledger_entries: Mapped[list["FinancialLedgerEntry"]] = relationship(
        "FinancialLedgerEntry",
        back_populates="invoice",
    )


class InvoiceLineItem(Base):
    """Itemized breakdown of an invoice."""

    __tablename__ = "invoice_line_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_rate_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint("amount_paise >= 0", name="chk_line_item_amount_positive"),
        CheckConstraint("quantity > 0", name="chk_line_item_quantity_positive"),
    )

    # Relationships
    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="line_items")


class Payment(Base):
    """Payment record captured or simulated for an apartment."""

    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    flat_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("flats.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="SIMULATED")
    provider_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(PaymentStatus, native_enum=False),
        nullable=False,
        default=PaymentStatus.PENDING,
        index=True,
    )
    initiated_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    booking_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "amenity_bookings.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_payments_booking_id",
        ),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("provider", "provider_reference", name="uq_payment_provider_reference"),
        CheckConstraint("amount_paise > 0", name="chk_payment_amount_positive"),
        Index("ix_payments_society_flat", "society_id", "flat_id"),
    )

    # Relationships
    allocations: Mapped[list["PaymentAllocation"]] = relationship(
        "PaymentAllocation",
        back_populates="payment",
        cascade="all, delete-orphan",
    )
    ledger_entries: Mapped[list["FinancialLedgerEntry"]] = relationship(
        "FinancialLedgerEntry",
        back_populates="payment",
    )


class PaymentAllocation(Base):
    """Explicit financial allocation of payment funds to an invoice."""

    __tablename__ = "payment_allocations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("payments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    allocated_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("payment_id", "invoice_id", name="uq_payment_invoice_allocation"),
        CheckConstraint("allocated_paise > 0", name="chk_allocation_amount_positive"),
    )

    # Relationships
    payment: Mapped["Payment"] = relationship("Payment", back_populates="allocations")
    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="allocations")


class FinancialLedgerEntry(Base):
    """Immutable, append-only financial journal entry.

    INVARIANT: Never modify or delete posted records.
    Corrections must use explicit REVERSAL or ADJUSTMENT entries referencing the original record.
    """

    __tablename__ = "financial_ledger_entries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    flat_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("flats.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("invoices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("payments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    entry_type: Mapped[LedgerEntryType] = mapped_column(
        SAEnum(LedgerEntryType, native_enum=False),
        nullable=False,
        index=True,
    )
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reference_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint("amount_paise > 0", name="chk_ledger_amount_positive"),
        Index("ix_ledger_society_flat", "society_id", "flat_id"),
        Index("ix_ledger_society_type", "society_id", "entry_type"),
    )

    # Relationships
    invoice: Mapped["Invoice | None"] = relationship("Invoice", back_populates="ledger_entries")
    payment: Mapped["Payment | None"] = relationship("Payment", back_populates="ledger_entries")


class BillingRun(Base):
    """Execution log for society monthly billing generation."""

    __tablename__ = "billing_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    billing_period: Mapped[str] = mapped_column(String(7), nullable=False)
    total_eligible_flats: Mapped[int] = mapped_column(Integer, nullable=False)
    total_invoiced_flats: Mapped[int] = mapped_column(Integer, nullable=False)
    total_skipped_flats: Mapped[int] = mapped_column(Integer, nullable=False)
    total_charges_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="COMPLETED")
    initiated_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    run_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (Index("ix_billing_runs_society_period", "society_id", "billing_period"),)


class LateFeePolicy(Base):
    """Configurable society maintenance late-fee policy following society bye-laws."""

    __tablename__ = "late_fee_policies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    policy_name: Mapped[str] = mapped_column(String(128), nullable=False)
    calculation_method: Mapped[LateFeeCalculationMethod] = mapped_column(
        SAEnum(LateFeeCalculationMethod, native_enum=False),
        nullable=False,
        default=LateFeeCalculationMethod.FLAT_FEE,
    )
    amount_or_rate_bps: Mapped[int] = mapped_column(
        BigInteger, nullable=False
    )  # Fixed paise or basis points (100 bps = 1.0%)
    grace_period_days: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    min_charge_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    max_charge_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "society_id",
            "policy_name",
            "effective_from",
            name="uq_late_fee_policy_society_name_from",
        ),
        Index("ix_late_fee_policies_society_active", "society_id", "is_active"),
    )


class LateFeeApplication(Base):
    """Idempotent audit record of late fee applied to an overdue invoice."""

    __tablename__ = "late_fee_applications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("late_fee_policies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    billing_period: Mapped[str] = mapped_column(String(7), nullable=False)
    applied_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    days_overdue: Mapped[int] = mapped_column(Integer, nullable=False)
    unpaid_principal_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fee_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("invoice_id", "billing_period", name="uq_late_fee_invoice_billing_period"),
        Index("ix_late_fee_apps_society_period", "society_id", "billing_period"),
    )

    # Relationships
    invoice: Mapped["Invoice"] = relationship("Invoice")
    policy: Mapped["LateFeePolicy"] = relationship("LateFeePolicy")
