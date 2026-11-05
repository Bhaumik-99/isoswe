"""Reconciliation Domain SQLAlchemy Models

Provides persistent entities for:
1. BankStatementImport (Track uploaded bank statement files, checksums, status, row counts)
2. BankTransaction (Normalized bank statement credit and debit transactions)
3. ReconciliationMatch (Candidate matches linking transactions to flats, residents, invoices or payments)
4. ReconciliationReview (Review audit history for manual triage, notes, and approval actions)
5. ReconciliationAllocation (Direct link between bank credit and invoice payment settlement)

FINANCIAL INVARIANTS:
- All monetary fields are BIGINT integer paise (1 INR = 100 paise).
- Floating-point calculations for financial amounts are strictly prohibited.
- Bank statement import is evidence of money received, not automatic permission to allocate.
- Allocations cannot exceed the bank credit available or invoice outstanding balance.
- Reconciling existing payment records must never create duplicate payments or ledger entries.
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
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
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


class StatementImportStatus(str, enum.Enum):
    UPLOADED = "UPLOADED"
    VALIDATING = "VALIDATING"
    READY_FOR_IMPORT = "READY_FOR_IMPORT"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TransactionType(str, enum.Enum):
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"


class TransactionReconciliationStatus(str, enum.Enum):
    UNMATCHED = "UNMATCHED"
    SUGGESTED = "SUGGESTED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    POSTED = "POSTED"
    REJECTED = "REJECTED"
    DUPLICATE = "DUPLICATE"
    UNIDENTIFIED = "UNIDENTIFIED"
    REVERSED = "REVERSED"


class MatchConfidenceTier(str, enum.Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class MatchingLevel(str, enum.Enum):
    LEVEL_1_UTR = "LEVEL_1_UTR"
    LEVEL_2_AMOUNT_REF = "LEVEL_2_AMOUNT_REF"
    LEVEL_3_NARRATION_RESIDENT = "LEVEL_3_NARRATION_RESIDENT"
    LEVEL_4_INVOICE_AMOUNT = "LEVEL_4_INVOICE_AMOUNT"
    LEVEL_5_UNMATCHED = "LEVEL_5_UNMATCHED"
    MANUAL = "MANUAL"


class BankStatementImport(Base):
    """Uploaded bank statement file tracking and lifecycle."""

    __tablename__ = "bank_statement_imports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[StatementImportStatus] = mapped_column(
        SAEnum(StatementImportStatus, native_enum=False),
        nullable=False,
        default=StatementImportStatus.UPLOADED,
        index=True,
    )
    bank_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    account_number_mask: Mapped[str | None] = mapped_column(String(32), nullable=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    imported_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_summary: Mapped[dict[str, Any]] = mapped_column(
        "error_summary", JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "society_id", "file_checksum", name="uq_statement_import_society_checksum"
        ),
        Index("ix_statement_imports_society_status", "society_id", "status"),
        Index("ix_statement_imports_society_created", "society_id", "created_at"),
    )

    # Relationships
    transactions: Mapped[list["BankTransaction"]] = relationship(
        "BankTransaction",
        back_populates="statement_import",
        cascade="all, delete-orphan",
        order_by="BankTransaction.source_row_number",
    )


class BankTransaction(Base):
    """Individual normalized line item from an imported bank statement."""

    __tablename__ = "bank_transactions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    import_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("bank_statement_imports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    transaction_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_description: Mapped[str] = mapped_column(Text, nullable=False)
    reference_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    utr_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    transaction_type: Mapped[TransactionType] = mapped_column(
        SAEnum(TransactionType, native_enum=False),
        nullable=False,
        default=TransactionType.CREDIT,
        index=True,
    )
    debit_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    credit_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    balance_paise: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    allocated_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    reconciliation_status: Mapped[TransactionReconciliationStatus] = mapped_column(
        SAEnum(TransactionReconciliationStatus, native_enum=False),
        nullable=False,
        default=TransactionReconciliationStatus.UNMATCHED,
        index=True,
    )
    transaction_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("bank_transactions.id", ondelete="SET NULL"),
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
        CheckConstraint("debit_paise >= 0", name="chk_bank_txn_debit_non_negative"),
        CheckConstraint("credit_paise >= 0", name="chk_bank_txn_credit_non_negative"),
        CheckConstraint("allocated_paise >= 0", name="chk_bank_txn_allocated_non_negative"),
        CheckConstraint(
            "allocated_paise <= credit_paise", name="chk_bank_txn_allocated_lte_credit"
        ),
        Index("ix_bank_txns_society_status", "society_id", "reconciliation_status"),
        Index("ix_bank_txns_society_date", "society_id", "transaction_date"),
        UniqueConstraint(
            "society_id", "transaction_fingerprint", name="uq_bank_transactions_society_fingerprint"
        ),
        Index("ix_bank_txns_society_utr", "society_id", "utr_number"),
    )

    # Relationships
    statement_import: Mapped["BankStatementImport"] = relationship(
        "BankStatementImport", back_populates="transactions"
    )
    matches: Mapped[list["ReconciliationMatch"]] = relationship(
        "ReconciliationMatch",
        back_populates="transaction",
        cascade="all, delete-orphan",
        order_by="ReconciliationMatch.confidence_score.desc()",
    )
    reviews: Mapped[list["ReconciliationReview"]] = relationship(
        "ReconciliationReview",
        back_populates="transaction",
        cascade="all, delete-orphan",
        order_by="ReconciliationReview.created_at.desc()",
    )
    allocations: Mapped[list["ReconciliationAllocation"]] = relationship(
        "ReconciliationAllocation",
        back_populates="transaction",
        cascade="all, delete-orphan",
    )


class ReconciliationMatch(Base):
    """Candidate match suggestion linking a bank transaction to a flat, resident, invoice, or payment."""

    __tablename__ = "reconciliation_matches"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("bank_transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    flat_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("flats.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    resident_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("invoices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    existing_payment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("payments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_tier: Mapped[MatchConfidenceTier] = mapped_column(
        SAEnum(MatchConfidenceTier, native_enum=False),
        nullable=False,
        default=MatchConfidenceTier.LOW,
        index=True,
    )
    matching_level: Mapped[MatchingLevel] = mapped_column(
        SAEnum(MatchingLevel, native_enum=False),
        nullable=False,
        default=MatchingLevel.LEVEL_5_UNMATCHED,
        index=True,
    )
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column("evidence", JSON, nullable=False, default=dict)
    is_selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "confidence_score >= 0.0 AND confidence_score <= 100.0",
            name="chk_match_confidence_range",
        ),
        Index("ix_reconciliation_matches_txn", "transaction_id", "confidence_score"),
        Index("ix_reconciliation_matches_invoice", "invoice_id"),
        Index("ix_reconciliation_matches_payment", "existing_payment_id"),
    )

    # Relationships
    transaction: Mapped["BankTransaction"] = relationship(
        "BankTransaction", back_populates="matches"
    )


class ReconciliationReview(Base):
    """Immutable audit trail of manual helpdesk triage decisions and notes."""

    __tablename__ = "reconciliation_reviews"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("bank_transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_allocations: Mapped[list[dict[str, Any]]] = mapped_column(
        "proposed_allocations", JSON, nullable=False, default=list
    )
    review_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (Index("ix_reconciliation_reviews_txn", "transaction_id", "created_at"),)

    # Relationships
    transaction: Mapped["BankTransaction"] = relationship(
        "BankTransaction", back_populates="reviews"
    )


class ReconciliationAllocation(Base):
    """Maps bank transaction credit to settled invoice payment."""

    __tablename__ = "reconciliation_allocations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("societies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("bank_transactions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("invoices.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("payments.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    payment_allocation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("payment_allocations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    allocated_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint("allocated_paise > 0", name="chk_recon_allocation_positive"),
        Index("ix_recon_allocations_txn", "transaction_id"),
        Index("ix_recon_allocations_invoice", "invoice_id"),
        Index("ix_recon_allocations_payment", "payment_id"),
        Index("ix_recon_allocations_society_txn", "society_id", "transaction_id"),
        Index("ix_recon_allocations_society_invoice", "society_id", "invoice_id"),
        Index("ix_recon_allocations_society_payment", "society_id", "payment_id"),
    )

    # Relationships
    transaction: Mapped["BankTransaction"] = relationship(
        "BankTransaction", back_populates="allocations"
    )
