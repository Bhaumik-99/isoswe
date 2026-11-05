"""Reconciliation Domain Pydantic v2 Schemas

Defines strong contracts for:
- Statement upload & preview payloads
- Bank transactions and normalized line items
- Candidate matching evaluations and evidence
- Manual review queue items and triage requests
- Financial approval and allocation payloads
- Summary KPIs and reconciliation reports
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domains.reconciliation.models import (
    MatchConfidenceTier,
    MatchingLevel,
    StatementImportStatus,
    TransactionReconciliationStatus,
    TransactionType,
)


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProposedAllocationItem(BaseModel):
    invoice_id: UUID
    allocated_paise: int = Field(
        gt=0, description="Amount in integer paise to allocate to this invoice"
    )


class TransactionPreviewItem(BaseModel):
    source_row_number: int
    transaction_date: datetime
    description: str
    reference_number: str | None = None
    utr_number: str | None = None
    transaction_type: TransactionType
    debit_paise: int
    credit_paise: int
    balance_paise: int | None = None


class StatementUploadPreviewResponse(BaseModel):
    import_id: UUID
    file_name: str
    file_checksum: str
    status: StatementImportStatus
    total_rows: int
    valid_rows: int
    rejected_rows: int
    detected_headers: dict[str, str]
    bank_profile: str
    preview_transactions: list[TransactionPreviewItem]
    rejected_samples: list[dict[str, Any]]
    created_at: datetime


class BankStatementImportResponse(BaseSchema):
    id: UUID
    society_id: UUID
    file_name: str
    file_checksum: str
    status: StatementImportStatus
    bank_name: str | None = None
    account_number_mask: str | None = None
    uploaded_by: UUID
    total_rows: int
    valid_rows: int
    rejected_rows: int
    duplicate_rows: int
    imported_rows: int
    error_summary: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ReconciliationMatchResponse(BaseSchema):
    id: UUID
    transaction_id: UUID
    flat_id: UUID | None = None
    flat_number: str | None = None
    resident_id: UUID | None = None
    resident_name: str | None = None
    invoice_id: UUID | None = None
    invoice_number: str | None = None
    invoice_total_paise: int | None = None
    invoice_outstanding_paise: int | None = None
    existing_payment_id: UUID | None = None
    existing_payment_reference: str | None = None
    confidence_score: float
    confidence_tier: MatchConfidenceTier
    matching_level: MatchingLevel
    explanation: str
    evidence: dict[str, Any]
    is_selected: bool
    created_at: datetime


class BankTransactionResponse(BaseSchema):
    id: UUID
    society_id: UUID
    import_id: UUID
    source_row_number: int
    transaction_date: datetime
    value_date: datetime | None = None
    description: str
    normalized_description: str
    reference_number: str | None = None
    utr_number: str | None = None
    transaction_type: TransactionType
    debit_paise: int
    credit_paise: int
    balance_paise: int | None = None
    allocated_paise: int
    unallocated_paise: int
    reconciliation_status: TransactionReconciliationStatus
    transaction_fingerprint: str
    is_duplicate: bool
    duplicate_of_id: UUID | None = None
    matches: list[ReconciliationMatchResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ManualReviewQueueItem(BaseModel):
    transaction: BankTransactionResponse
    suggested_match: ReconciliationMatchResponse | None = None
    candidates_count: int
    queue_category: str
    latest_review_note: str | None = None


class SuggestMatchRequest(BaseModel):
    flat_id: UUID
    invoice_id: UUID | None = None
    notes: str | None = None


class SubmitForApprovalRequest(BaseModel):
    proposed_allocations: list[ProposedAllocationItem] = Field(
        min_length=1, description="One or more invoices to allocate credit funds to"
    )
    notes: str | None = None


class ApproveReconciliationRequest(BaseModel):
    proposed_allocations: list[ProposedAllocationItem] = Field(
        min_length=1, description="Final approved allocations to post to invoices"
    )
    notes: str | None = None


class RejectReconciliationRequest(BaseModel):
    reason: str = Field(min_length=3, description="Reason for rejecting the proposed match")


class MarkUnidentifiedRequest(BaseModel):
    notes: str = Field(min_length=3, description="Notes on why funds cannot be identified")


class QueueSummaryResponse(BaseModel):
    society_id: UUID
    total_queue_items: int
    high_confidence: int
    resident_clues: int
    unmatched: int
    suspense: int


class ReconciliationSummaryResponse(BaseModel):
    society_id: UUID
    total_credit_paise: int
    total_debit_paise: int
    reconciled_credit_paise: int
    unmatched_credit_paise: int
    pending_approval_credit_paise: int
    total_transactions: int
    unmatched_count: int
    suggested_count: int
    pending_approval_count: int
    posted_count: int
    duplicate_count: int
    unidentified_count: int
    reconciliation_percentage: float


class ReconciliationReportItem(BaseModel):
    transaction_id: UUID
    transaction_date: datetime
    description: str
    utr_number: str | None = None
    reference_number: str | None = None
    credit_paise: int
    allocated_paise: int
    reconciliation_status: str
    flat_number: str | None = None
    resident_name: str | None = None
    invoice_number: str | None = None
    posted_at: datetime | None = None
