"""Domain-Specific Exceptions for Bank Statement Reconciliation

Categorizes reconciliation domain errors, distinguishing between:
- Validation errors (malformed CSV, invalid date, negative amounts)
- Conflict errors (duplicate files, duplicate fingerprints, concurrent settlements)
- Business rule violations (cross-flat allocation, over-allocation, unallocated balances)
- Retryable vs. permanent worker errors for queue processing
"""

from typing import Any


class ReconciliationError(Exception):
    """Base exception for all reconciliation domain errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class StatementParseError(ReconciliationError):
    """Raised when CSV statement parsing fails or headers cannot be mapped."""


class StatementChecksumDuplicateError(ReconciliationError):
    """Raised when an identical statement file checksum already exists in the society."""


class InvalidStatementStateError(ReconciliationError):
    """Raised when an illegal statement lifecycle state transition is attempted."""


class TransactionNotFoundError(ReconciliationError):
    """Raised when a bank transaction ID does not exist or belongs to another society."""


class TransactionAlreadySettledError(ReconciliationError):
    """Raised when attempting to allocate or settle an already posted transaction."""


class InvoiceOverAllocationError(ReconciliationError):
    """Raised when proposed allocation exceeds the current outstanding balance of the invoice."""


class CreditOverAllocationError(ReconciliationError):
    """Raised when total proposed allocations exceed the available bank transaction credit."""


class CrossSocietyAllocationError(ReconciliationError):
    """Raised when attempting to allocate funds across different society boundaries."""


class CrossFlatAllocationError(ReconciliationError):
    """Raised when an allocation violates flat tenancy or unit membership boundaries."""


class DuplicateTransactionError(ReconciliationError):
    """Raised when a transaction fingerprint matches an existing statement row."""


class RetryableReconciliationWorkerError(ReconciliationError):
    """Transient worker error that should trigger message retry in SQS queue."""


class PermanentReconciliationWorkerError(ReconciliationError):
    """Non-retryable worker error (e.g. poison pill) that should acknowledge message to DLQ."""
