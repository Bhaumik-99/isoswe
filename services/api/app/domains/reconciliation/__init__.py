"""Reconciliation Domain Package

Provides bank statement ingestion, parsing, duplicate detection,
layered deterministic transaction matching, manual review queue,
and financial settlement integration with billing ledger.
"""

from app.domains.reconciliation.exceptions import (
    CreditOverAllocationError,
    CrossFlatAllocationError,
    CrossSocietyAllocationError,
    DuplicateTransactionError,
    InvalidStatementStateError,
    InvoiceOverAllocationError,
    PermanentReconciliationWorkerError,
    ReconciliationError,
    RetryableReconciliationWorkerError,
    StatementChecksumDuplicateError,
    StatementParseError,
    TransactionAlreadySettledError,
    TransactionNotFoundError,
)
from app.domains.reconciliation.models import (
    BankStatementImport,
    BankTransaction,
    MatchConfidenceTier,
    MatchingLevel,
    ReconciliationAllocation,
    ReconciliationMatch,
    ReconciliationReview,
    StatementImportStatus,
    TransactionReconciliationStatus,
    TransactionType,
)

__all__ = [
    "BankStatementImport",
    "BankTransaction",
    "CreditOverAllocationError",
    "CrossFlatAllocationError",
    "CrossSocietyAllocationError",
    "DuplicateTransactionError",
    "InvalidStatementStateError",
    "InvoiceOverAllocationError",
    "MatchConfidenceTier",
    "MatchingLevel",
    "PermanentReconciliationWorkerError",
    "ReconciliationAllocation",
    "ReconciliationError",
    "ReconciliationMatch",
    "ReconciliationReview",
    "RetryableReconciliationWorkerError",
    "StatementChecksumDuplicateError",
    "StatementImportStatus",
    "StatementParseError",
    "TransactionAlreadySettledError",
    "TransactionNotFoundError",
    "TransactionReconciliationStatus",
    "TransactionType",
]
