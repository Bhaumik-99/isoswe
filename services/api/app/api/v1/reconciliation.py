"""Reconciliation Domain API Router

Exposes secure, tenant-isolated REST endpoints for:
- Bank statement CSV upload, validation, and preview
- Statement confirmation and deterministic matching execution
- Transaction listing and candidate search
- Manual review queue operations and suggestions
- Atomic financial approval and ledger settlement (with mandatory Idempotency-Key)
- Society reconciliation summary KPIs and CSV exports
"""

import json
from datetime import datetime
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AuthorizationError, ValidationError
from app.core.security import require_roles
from app.domains.identity.models import RoleType
from app.domains.identity.schemas import CurrentUserClaims
from app.domains.reconciliation.models import (
    TransactionReconciliationStatus,
    TransactionType,
)
from app.domains.reconciliation.normalizer import MAX_STATEMENT_FILE_SIZE
from app.domains.reconciliation.schemas import (
    ApproveReconciliationRequest,
    BankStatementImportResponse,
    BankTransactionResponse,
    CreateResidentUPIMappingRequest,
    ManualReviewQueueItem,
    MarkUnidentifiedRequest,
    QueueSummaryResponse,
    ReconciliationMatchResponse,
    ReconciliationSummaryResponse,
    RejectReconciliationRequest,
    ResidentUPIMappingResponse,
    StatementUploadPreviewResponse,
    SubmitForApprovalRequest,
    SuggestMatchRequest,
)
from app.domains.reconciliation.service import ReconciliationService

router = APIRouter(prefix="/reconciliation", tags=["Reconciliation"])


def _resolve_society_id(claims: CurrentUserClaims, query_society_id: UUID | None) -> UUID:
    """Validates and resolves active society ID from authenticated claims."""
    if not claims.society_ids:
        raise AuthorizationError("User is not assigned to any society")
    if query_society_id:
        if query_society_id not in claims.society_ids:
            raise AuthorizationError(f"Access denied to society {query_society_id}")
        return query_society_id
    return claims.society_ids[0]


# -----------------------------------------------------------------------------
# 1. Statement Upload & Lifecycle
# -----------------------------------------------------------------------------
@router.post(
    "/statements",
    response_model=StatementUploadPreviewResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload bank statement CSV and preview transactions",
)
async def upload_bank_statement(
    file: UploadFile = File(...),
    bank_profile: str = Form("AUTO"),
    custom_mapping: str | None = Form(None),
    society_id: UUID | None = Query(None),
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> StatementUploadPreviewResponse:
    target_society_id = _resolve_society_id(claims, society_id)

    # Bounded stream reading to prevent unrestricted memory buffering
    chunk_size = 64 * 1024  # 64 KB
    total_bytes = 0
    chunks: list[bytes] = []
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > MAX_STATEMENT_FILE_SIZE:
            raise ValidationError(
                f"File size exceeds maximum allowable limit of {MAX_STATEMENT_FILE_SIZE // (1024 * 1024)} MB."
            )
        chunks.append(chunk)
    file_bytes = b"".join(chunks)

    mapping_dict: dict[str, str] | None = None
    if custom_mapping:
        try:
            mapping_dict = json.loads(custom_mapping)
        except Exception as exc:
            raise ValidationError(f"Invalid custom_mapping JSON: {exc}") from exc

    service = ReconciliationService(db)
    return service.upload_statement(
        claims=claims,
        society_id=target_society_id,
        file_name=file.filename or "statement.csv",
        file_bytes=file_bytes,
        custom_mapping=mapping_dict,
        bank_profile=bank_profile,
    )


@router.get(
    "/statements",
    response_model=list[BankStatementImportResponse],
    summary="List bank statement imports for society",
)
def list_statement_imports(
    society_id: UUID | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> list[BankStatementImportResponse]:
    target_society_id = _resolve_society_id(claims, society_id)
    service = ReconciliationService(db)
    imports = service.repo.list_statement_imports(
        society_id=target_society_id, skip=skip, limit=limit
    )
    return [BankStatementImportResponse.model_validate(imp) for imp in imports]


@router.get(
    "/statements/{import_id}",
    response_model=BankStatementImportResponse,
    summary="Get bank statement import details",
)
def get_statement_import(
    import_id: UUID,
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> BankStatementImportResponse:
    service = ReconciliationService(db)
    imp = service.repo.get_statement_import_by_id(import_id)
    if not imp:
        raise ValidationError(f"Statement import {import_id} not found")
    _resolve_society_id(claims, imp.society_id)
    return BankStatementImportResponse.model_validate(imp)


@router.post(
    "/statements/{import_id}/confirm",
    response_model=BankStatementImportResponse,
    summary="Confirm validated statement and execute matching engine",
)
def confirm_statement_import(
    import_id: UUID,
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> BankStatementImportResponse:
    service = ReconciliationService(db)
    return service.confirm_import(claims=claims, import_id=import_id)


@router.post(
    "/statements/{import_id}/process",
    response_model=BankStatementImportResponse,
    summary="Process and match statement (alias for /confirm)",
)
def process_statement_import(
    import_id: UUID,
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> BankStatementImportResponse:
    service = ReconciliationService(db)
    return service.confirm_import(claims=claims, import_id=import_id)


@router.post(
    "/statements/{import_id}/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancel a statement import before confirmation",
)
def cancel_statement_import(
    import_id: UUID,
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> None:
    service = ReconciliationService(db)
    service.cancel_import(claims=claims, import_id=import_id)


# -----------------------------------------------------------------------------
# 2. Bank Transactions & Details
# -----------------------------------------------------------------------------
@router.get(
    "/transactions",
    response_model=list[BankTransactionResponse],
    summary="List normalized bank transactions with filters",
)
def list_transactions(
    society_id: UUID | None = Query(None),
    status: TransactionReconciliationStatus | None = Query(None),
    transaction_type: TransactionType | None = Query(None),
    import_id: UUID | None = Query(None),
    search: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> list[BankTransactionResponse]:
    target_society_id = _resolve_society_id(claims, society_id)
    service = ReconciliationService(db)
    return service.list_transactions(
        claims=claims,
        society_id=target_society_id,
        status=status,
        transaction_type=transaction_type,
        import_id=import_id,
        search=search,
        date_from=date_from,
        date_to=date_to,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/transactions/{transaction_id}",
    response_model=BankTransactionResponse,
    summary="Get single transaction details with matches and review history",
)
def get_transaction(
    transaction_id: UUID,
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> BankTransactionResponse:
    service = ReconciliationService(db)
    return service.get_transaction(claims=claims, transaction_id=transaction_id)


# -----------------------------------------------------------------------------
# 3. Manual Reconciliation Queue & Actions
# -----------------------------------------------------------------------------
@router.get(
    "/queue",
    response_model=list[ManualReviewQueueItem],
    summary="Get transactions requiring human review",
)
def get_manual_review_queue(
    society_id: UUID | None = Query(None),
    category: str = Query(
        "ALL", description="ALL, UNMATCHED, SUGGESTED, PENDING_APPROVAL, DUPLICATE_REVIEW"
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> list[ManualReviewQueueItem]:
    target_society_id = _resolve_society_id(claims, society_id)
    service = ReconciliationService(db)
    return service.get_review_queue(
        claims=claims,
        society_id=target_society_id,
        queue_category=category,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/queue/summary",
    response_model=QueueSummaryResponse,
    summary="Get summary counts of items in the review queue",
)
def get_queue_summary(
    society_id: UUID | None = Query(None),
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> QueueSummaryResponse:
    target_society_id = _resolve_society_id(claims, society_id)
    service = ReconciliationService(db)
    summary = service.get_summary(claims=claims, society_id=target_society_id)
    return QueueSummaryResponse(
        society_id=target_society_id,
        total_queue_items=summary.unmatched_count
        + summary.suggested_count
        + summary.pending_approval_count,
        high_confidence=summary.suggested_count,
        resident_clues=summary.suggested_count,
        unmatched=summary.unmatched_count,
        suspense=summary.unidentified_count,
    )


@router.get(
    "/transactions/{transaction_id}/matches",
    response_model=list[ReconciliationMatchResponse],
    summary="List proposed candidate matches for a transaction",
)
def get_transaction_matches(
    transaction_id: UUID,
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> list[ReconciliationMatchResponse]:
    service = ReconciliationService(db)
    txn = service.get_transaction(claims=claims, transaction_id=transaction_id)
    return txn.matches


@router.post(
    "/transactions/{transaction_id}/match",
    response_model=BankTransactionResponse,
    summary="Suggest match for transaction (alias for /suggest)",
)
def match_transaction(
    transaction_id: UUID,
    payload: SuggestMatchRequest,
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> BankTransactionResponse:
    service = ReconciliationService(db)
    return service.suggest_manual_match(
        claims=claims,
        transaction_id=transaction_id,
        flat_id=payload.flat_id,
        invoice_id=payload.invoice_id,
        notes=payload.notes,
    )


@router.post(
    "/transactions/{transaction_id}/suggest",
    response_model=BankTransactionResponse,
    summary="Manually assign a matching flat and invoice to a transaction",
)
def suggest_manual_match(
    transaction_id: UUID,
    payload: SuggestMatchRequest,
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> BankTransactionResponse:
    service = ReconciliationService(db)
    return service.suggest_manual_match(
        claims=claims,
        transaction_id=transaction_id,
        flat_id=payload.flat_id,
        invoice_id=payload.invoice_id,
        notes=payload.notes,
    )


@router.post(
    "/transactions/{transaction_id}/submit-for-approval",
    response_model=BankTransactionResponse,
    summary="Submit proposed allocations for supervisory or peer review",
)
def submit_for_approval(
    transaction_id: UUID,
    payload: SubmitForApprovalRequest,
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> BankTransactionResponse:
    service = ReconciliationService(db)
    return service.submit_for_approval(
        claims=claims,
        transaction_id=transaction_id,
        proposed_allocations=payload.proposed_allocations,
        notes=payload.notes,
    )


@router.post(
    "/transactions/{transaction_id}/approve",
    response_model=BankTransactionResponse,
    summary="Approve allocation and execute atomic financial ledger settlement",
)
def approve_and_allocate(
    transaction_id: UUID,
    payload: ApproveReconciliationRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-Id"),
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> BankTransactionResponse:
    service = ReconciliationService(db)
    return service.approve_and_allocate(
        claims=claims,
        transaction_id=transaction_id,
        proposed_allocations=payload.proposed_allocations,
        idempotency_key=idempotency_key,
        correlation_id=x_correlation_id,
        notes=payload.notes,
    )


@router.post(
    "/transactions/{transaction_id}/reject",
    response_model=BankTransactionResponse,
    summary="Reject suggested match and move transaction back to review queue",
)
def reject_match(
    transaction_id: UUID,
    payload: RejectReconciliationRequest,
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> BankTransactionResponse:
    service = ReconciliationService(db)
    return service.reject_match(
        claims=claims,
        transaction_id=transaction_id,
        reason=payload.reason,
    )


@router.post(
    "/transactions/{transaction_id}/mark-unidentified",
    response_model=BankTransactionResponse,
    summary="Mark credit as unidentified / suspense account",
)
def mark_unidentified(
    transaction_id: UUID,
    payload: MarkUnidentifiedRequest,
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> BankTransactionResponse:
    service = ReconciliationService(db)
    return service.mark_unidentified(
        claims=claims,
        transaction_id=transaction_id,
        notes=payload.notes,
    )


# -----------------------------------------------------------------------------
# 4. Summary & Reports
# -----------------------------------------------------------------------------
@router.get(
    "/summary",
    response_model=ReconciliationSummaryResponse,
    summary="Get society-level reconciliation KPI metrics",
)
def get_reconciliation_summary(
    society_id: UUID | None = Query(None),
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> ReconciliationSummaryResponse:
    target_society_id = _resolve_society_id(claims, society_id)
    service = ReconciliationService(db)
    return service.get_summary(claims=claims, society_id=target_society_id)


@router.get(
    "/reports/summary",
    response_model=ReconciliationSummaryResponse,
    summary="Get society-level reconciliation KPI summary (alias for /summary)",
)
def get_reports_summary(
    society_id: UUID | None = Query(None),
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> ReconciliationSummaryResponse:
    target_society_id = _resolve_society_id(claims, society_id)
    service = ReconciliationService(db)
    return service.get_summary(claims=claims, society_id=target_society_id)


@router.get(
    "/reports/unmatched",
    response_model=list[BankTransactionResponse],
    summary="List all unmatched bank credit transactions for society",
)
def get_unmatched_report(
    society_id: UUID | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> list[BankTransactionResponse]:
    target_society_id = _resolve_society_id(claims, society_id)
    service = ReconciliationService(db)
    return service.list_transactions(
        claims=claims,
        society_id=target_society_id,
        status=TransactionReconciliationStatus.UNMATCHED,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/reports/reconciled",
    response_model=list[BankTransactionResponse],
    summary="List all reconciled and posted transactions for society",
)
def get_reconciled_report(
    society_id: UUID | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> list[BankTransactionResponse]:
    target_society_id = _resolve_society_id(claims, society_id)
    service = ReconciliationService(db)
    return service.list_transactions(
        claims=claims,
        society_id=target_society_id,
        status=TransactionReconciliationStatus.POSTED,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/reports/export",
    summary="Export reconciliation report as CSV with formula injection protection",
)
def export_reconciliation_report_csv(
    society_id: UUID | None = Query(None),
    status: TransactionReconciliationStatus | None = Query(None),
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> Response:
    target_society_id = _resolve_society_id(claims, society_id)
    service = ReconciliationService(db)
    csv_data = service.export_report_csv(claims=claims, society_id=target_society_id, status=status)

    filename = f"reconciliation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# -----------------------------------------------------------------------------
# 6. Resident UPI Mappings
# -----------------------------------------------------------------------------
@router.get(
    "/upi-mappings",
    response_model=list[ResidentUPIMappingResponse],
    summary="List registered resident UPI VPAs for society",
)
def list_resident_upi_mappings(
    society_id: UUID | None = Query(None),
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> list[ResidentUPIMappingResponse]:
    target_society_id = _resolve_society_id(claims, society_id)
    service = ReconciliationService(db)
    return service.list_resident_upi_mappings(claims=claims, society_id=target_society_id)


@router.post(
    "/upi-mappings",
    response_model=ResidentUPIMappingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register an authorized resident UPI VPA for flat auto-matching",
)
def create_resident_upi_mapping(
    payload: CreateResidentUPIMappingRequest,
    society_id: UUID | None = Query(None),
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> ResidentUPIMappingResponse:
    target_society_id = _resolve_society_id(claims, society_id)
    service = ReconciliationService(db)
    return service.create_resident_upi_mapping(
        claims=claims, society_id=target_society_id, req=payload
    )


@router.delete(
    "/upi-mappings/{mapping_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a resident UPI VPA mapping",
)
def delete_resident_upi_mapping(
    mapping_id: UUID,
    society_id: UUID | None = Query(None),
    claims: CurrentUserClaims = Depends(require_roles(RoleType.HELPDESK)),
    db: Session = Depends(get_db),
) -> None:
    target_society_id = _resolve_society_id(claims, society_id)
    service = ReconciliationService(db)
    service.delete_resident_upi_mapping(
        claims=claims, society_id=target_society_id, mapping_id=mapping_id
    )
