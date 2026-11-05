"""Reconciliation Domain Database Repository

Provides persistent data access, tenant-isolated queries,
row-level locking, and transactional operations for bank reconciliation.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.domains.reconciliation.models import (
    BankStatementImport,
    BankTransaction,
    ReconciliationAllocation,
    ReconciliationMatch,
    ReconciliationReview,
    StatementImportStatus,
    TransactionReconciliationStatus,
    TransactionType,
)


class ReconciliationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # -------------------------------------------------------------------------
    # Statement Imports
    # -------------------------------------------------------------------------
    def create_statement_import(
        self,
        society_id: UUID,
        file_name: str,
        file_checksum: str,
        uploaded_by: UUID,
        status: StatementImportStatus = StatementImportStatus.UPLOADED,
        bank_name: str | None = None,
        account_number_mask: str | None = None,
        storage_key: str | None = None,
    ) -> BankStatementImport:
        stmt_import = BankStatementImport(
            society_id=society_id,
            file_name=file_name,
            file_checksum=file_checksum,
            uploaded_by=uploaded_by,
            status=status,
            bank_name=bank_name,
            account_number_mask=account_number_mask,
            storage_key=storage_key,
        )
        self.db.add(stmt_import)
        self.db.flush()
        return stmt_import

    def get_statement_import_by_id(
        self, import_id: UUID, society_id: UUID | None = None
    ) -> BankStatementImport | None:
        stmt = select(BankStatementImport).where(BankStatementImport.id == import_id)
        if society_id:
            stmt = stmt.where(BankStatementImport.society_id == society_id)
        return self.db.scalar(stmt)

    def get_statement_import_for_update(
        self, import_id: UUID, society_id: UUID | None = None
    ) -> BankStatementImport | None:
        """Locks bank statement import row using SELECT FOR UPDATE to prevent concurrent confirmation claims."""
        stmt = (
            select(BankStatementImport).where(BankStatementImport.id == import_id).with_for_update()
        )
        if society_id:
            stmt = stmt.where(BankStatementImport.society_id == society_id)
        return self.db.scalar(stmt)

    def get_statement_import_by_checksum(
        self, society_id: UUID, file_checksum: str
    ) -> BankStatementImport | None:
        stmt = select(BankStatementImport).where(
            BankStatementImport.society_id == society_id,
            BankStatementImport.file_checksum == file_checksum,
        )
        return self.db.scalar(stmt)

    def list_statement_imports(
        self,
        society_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[BankStatementImport]:
        stmt = (
            select(BankStatementImport)
            .where(BankStatementImport.society_id == society_id)
            .order_by(desc(BankStatementImport.created_at))
            .offset(skip)
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    # -------------------------------------------------------------------------
    # Bank Transactions
    # -------------------------------------------------------------------------
    def create_transactions_batch(
        self, transactions: list[BankTransaction]
    ) -> list[BankTransaction]:
        self.db.add_all(transactions)
        self.db.flush()
        return transactions

    def get_transaction_by_id(
        self, transaction_id: UUID, society_id: UUID | None = None
    ) -> BankTransaction | None:
        stmt = (
            select(BankTransaction)
            .options(
                joinedload(BankTransaction.matches),
                joinedload(BankTransaction.reviews),
                joinedload(BankTransaction.allocations),
            )
            .where(BankTransaction.id == transaction_id)
        )
        if society_id:
            stmt = stmt.where(BankTransaction.society_id == society_id)
        return self.db.scalar(stmt)

    def get_transaction_for_update(
        self, transaction_id: UUID, society_id: UUID
    ) -> BankTransaction | None:
        """Locks bank transaction row using SELECT FOR UPDATE to prevent race conditions during approval."""
        stmt = (
            select(BankTransaction)
            .where(
                BankTransaction.id == transaction_id,
                BankTransaction.society_id == society_id,
            )
            .with_for_update()
        )
        return self.db.scalar(stmt)

    def list_transactions(
        self,
        society_id: UUID,
        status: TransactionReconciliationStatus | None = None,
        transaction_type: TransactionType | None = None,
        import_id: UUID | None = None,
        search: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[BankTransaction]:
        stmt = (
            select(BankTransaction)
            .options(joinedload(BankTransaction.matches))
            .where(BankTransaction.society_id == society_id)
        )

        if status:
            stmt = stmt.where(BankTransaction.reconciliation_status == status)
        if transaction_type:
            stmt = stmt.where(BankTransaction.transaction_type == transaction_type)
        if import_id:
            stmt = stmt.where(BankTransaction.import_id == import_id)
        if date_from:
            stmt = stmt.where(BankTransaction.transaction_date >= date_from)
        if date_to:
            stmt = stmt.where(BankTransaction.transaction_date <= date_to)

        if search and search.strip():
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    BankTransaction.description.ilike(term),
                    BankTransaction.reference_number.ilike(term),
                    BankTransaction.utr_number.ilike(term),
                )
            )

        stmt = (
            stmt.order_by(desc(BankTransaction.transaction_date), desc(BankTransaction.created_at))
            .offset(skip)
            .limit(limit)
        )
        return list(self.db.scalars(stmt).unique().all())

    def find_duplicate_fingerprints(
        self, society_id: UUID, fingerprints: list[str]
    ) -> dict[str, UUID]:
        """Finds existing transactions with matching fingerprints in society."""
        if not fingerprints:
            return {}
        stmt = select(BankTransaction.transaction_fingerprint, BankTransaction.id).where(
            BankTransaction.society_id == society_id,
            BankTransaction.transaction_fingerprint.in_(fingerprints),
        )
        rows = self.db.execute(stmt).all()
        return {r[0]: r[1] for r in rows}

    def find_duplicate_utrs(self, society_id: UUID, utrs: list[str]) -> dict[str, UUID]:
        """Finds existing transactions with identical UTR numbers in society."""
        valid_utrs = [u for u in utrs if u and u.strip()]
        if not valid_utrs:
            return {}
        stmt = select(BankTransaction.utr_number, BankTransaction.id).where(
            BankTransaction.society_id == society_id,
            BankTransaction.utr_number.in_(valid_utrs),
        )
        rows = self.db.execute(stmt).all()
        return {r[0]: r[1] for r in rows if r[0]}

    # -------------------------------------------------------------------------
    # Matches & Reviews
    # -------------------------------------------------------------------------
    def create_matches_batch(self, matches: list[ReconciliationMatch]) -> list[ReconciliationMatch]:
        self.db.add_all(matches)
        self.db.flush()
        return matches

    def clear_matches_for_transaction(self, transaction_id: UUID) -> None:
        stmt = select(ReconciliationMatch).where(
            ReconciliationMatch.transaction_id == transaction_id
        )
        existing = list(self.db.scalars(stmt).all())
        for m in existing:
            self.db.delete(m)
        self.db.flush()

    def create_review(
        self,
        society_id: UUID,
        transaction_id: UUID,
        reviewer_id: UUID,
        action: str,
        notes: str | None = None,
        proposed_allocations: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ReconciliationReview:
        review = ReconciliationReview(
            society_id=society_id,
            transaction_id=transaction_id,
            reviewer_id=reviewer_id,
            action=action,
            notes=notes,
            proposed_allocations=proposed_allocations or [],
            review_metadata=metadata or {},
        )
        self.db.add(review)
        self.db.flush()
        return review

    def create_reconciliation_allocation(
        self,
        society_id: UUID,
        transaction_id: UUID,
        invoice_id: UUID,
        payment_id: UUID | None,
        payment_allocation_id: UUID | None,
        allocated_paise: int,
    ) -> ReconciliationAllocation:
        alloc = ReconciliationAllocation(
            society_id=society_id,
            transaction_id=transaction_id,
            invoice_id=invoice_id,
            payment_id=payment_id,
            payment_allocation_id=payment_allocation_id,
            allocated_paise=allocated_paise,
        )
        self.db.add(alloc)
        self.db.flush()
        return alloc

    # -------------------------------------------------------------------------
    # Aggregation & Reporting
    # -------------------------------------------------------------------------
    def get_society_reconciliation_summary(self, society_id: UUID) -> dict[str, Any]:
        """Calculates society reconciliation totals, counts, and completion percentage."""
        # Totals query
        totals_stmt = select(
            func.coalesce(func.sum(BankTransaction.credit_paise), 0).label("total_credit"),
            func.coalesce(func.sum(BankTransaction.debit_paise), 0).label("total_debit"),
            func.coalesce(func.sum(BankTransaction.allocated_paise), 0).label("reconciled_credit"),
            func.count(BankTransaction.id).label("total_txns"),
        ).where(BankTransaction.society_id == society_id)

        totals_res = self.db.execute(totals_stmt).one()
        total_credit = int(totals_res.total_credit)
        total_debit = int(totals_res.total_debit)
        reconciled_credit = int(totals_res.reconciled_credit)
        total_txns = int(totals_res.total_txns)

        # Status counts query
        counts_stmt = (
            select(
                BankTransaction.reconciliation_status,
                func.count(BankTransaction.id),
                func.coalesce(func.sum(BankTransaction.credit_paise), 0),
            )
            .where(BankTransaction.society_id == society_id)
            .group_by(BankTransaction.reconciliation_status)
        )

        status_counts: dict[str, int] = {}
        status_credits: dict[str, int] = {}
        for row in self.db.execute(counts_stmt).all():
            st = row[0].value if hasattr(row[0], "value") else str(row[0])
            status_counts[st] = int(row[1])
            status_credits[st] = int(row[2])

        unmatched_credit = status_credits.get("UNMATCHED", 0) + status_credits.get("SUGGESTED", 0)
        pending_credit = status_credits.get("PENDING_APPROVAL", 0)

        recon_pct = round((reconciled_credit / total_credit * 100), 2) if total_credit > 0 else 0.0

        return {
            "society_id": society_id,
            "total_credit_paise": total_credit,
            "total_debit_paise": total_debit,
            "reconciled_credit_paise": reconciled_credit,
            "unmatched_credit_paise": unmatched_credit,
            "pending_approval_credit_paise": pending_credit,
            "total_transactions": total_txns,
            "unmatched_count": status_counts.get("UNMATCHED", 0),
            "suggested_count": status_counts.get("SUGGESTED", 0),
            "pending_approval_count": status_counts.get("PENDING_APPROVAL", 0),
            "posted_count": status_counts.get("POSTED", 0),
            "duplicate_count": status_counts.get("DUPLICATE", 0),
            "unidentified_count": status_counts.get("UNIDENTIFIED", 0),
            "reconciliation_percentage": recon_pct,
        }
