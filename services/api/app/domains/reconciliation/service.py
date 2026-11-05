"""Reconciliation Domain Service Layer

Orchestrates authoritative business logic for bank reconciliation:
1. Bank statement CSV upload, validation, checksumming, and preview
2. Statement confirmation, transaction normalization, and multi-layer duplicate detection
3. Layered deterministic matching engine execution
4. Manual review queue management and triage
5. Atomic financial settlement integration with billing ledger:
   - Invoice row-locking (SELECT FOR UPDATE)
   - Dynamic outstanding balance recalculation
   - Idempotent approval workflow
   - Zero double-posting for existing payment provider transactions
   - Creation of bank-transfer payments, allocations, and immutable ledger entries
6. Audit logging and transactional outbox event publishing
"""

import csv
import hashlib
import io
import json
import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import AuthorizationError, ConflictError, NotFoundError, ValidationError
from app.domains.billing.models import (
    Invoice,
    InvoiceStatus,
    LedgerEntryType,
    Payment,
    PaymentAllocation,
    PaymentStatus,
)
from app.domains.billing.repository import BillingRepository
from app.domains.billing.service import BillingService
from app.domains.identity.models import Flat, RoleType, User
from app.domains.identity.schemas import CurrentUserClaims
from app.domains.reconciliation.models import (
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
from app.domains.reconciliation.normalizer import (
    MAX_STATEMENT_FILE_SIZE,
    compute_file_checksum,
    sanitize_for_csv_export,
)
from app.domains.reconciliation.parser import BankStatementParser
from app.domains.reconciliation.repository import ReconciliationRepository
from app.domains.reconciliation.schemas import (
    BankStatementImportResponse,
    BankTransactionResponse,
    ManualReviewQueueItem,
    ProposedAllocationItem,
    ReconciliationMatchResponse,
    ReconciliationSummaryResponse,
    StatementUploadPreviewResponse,
    TransactionPreviewItem,
)
from app.domains.reliability.models import AuditEvent, OutboxEvent, OutboxStatus


class ReconciliationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ReconciliationRepository(db)
        self.billing_repo = BillingRepository(db)
        self.billing_service = BillingService(db)

    # -------------------------------------------------------------------------
    # Helper: Tenant & Role Authorization
    # -------------------------------------------------------------------------
    def _verify_society_access(self, claims: CurrentUserClaims, society_id: UUID) -> None:
        """Enforces multi-tenant society isolation."""
        if society_id not in claims.society_ids:
            raise AuthorizationError(f"Access denied: User does not belong to society {society_id}")

    def _verify_helpdesk_role(self, claims: CurrentUserClaims) -> None:
        """Enforces that only authorized HELPDESK staff can perform reconciliation."""
        if RoleType.HELPDESK not in claims.roles:
            raise AuthorizationError("Access denied: Bank reconciliation requires HELPDESK role")

    # -------------------------------------------------------------------------
    # 1. Statement Upload & Preview
    # -------------------------------------------------------------------------
    def upload_statement(
        self,
        claims: CurrentUserClaims,
        society_id: UUID,
        file_name: str,
        file_bytes: bytes,
        custom_mapping: dict[str, str] | None = None,
        bank_profile: str = "AUTO",
    ) -> StatementUploadPreviewResponse:
        self._verify_helpdesk_role(claims)
        self._verify_society_access(claims, society_id)

        # 1. File extension validation
        if not file_name.lower().endswith(".csv"):
            raise ValidationError(
                "Invalid file format. Only CSV bank statements (.csv) are supported."
            )

        # 2. File size validation (Max 10MB)
        file_size = len(file_bytes)
        if file_size == 0:
            raise ValidationError("Uploaded file is empty (0 bytes).")
        if file_size > MAX_STATEMENT_FILE_SIZE:
            raise ValidationError(
                f"File size ({file_size / (1024 * 1024):.2f} MB) exceeds maximum limit of 10 MB."
            )

        # 3. Cryptographic duplicate file detection (SHA-256)
        checksum = compute_file_checksum(file_bytes)
        existing_import = self.repo.get_statement_import_by_checksum(society_id, checksum)
        if existing_import and existing_import.status in (
            StatementImportStatus.COMPLETED,
            StatementImportStatus.COMPLETED_WITH_ERRORS,
            StatementImportStatus.PROCESSING,
        ):
            raise ConflictError(
                f"Duplicate statement import: A file with identical content has already been imported "
                f"on {existing_import.created_at.strftime('%Y-%m-%d %H:%M UTC')} (Import ID: {existing_import.id})."
            )

        # 4. Parse statement
        parser = BankStatementParser(society_id)
        parse_result = parser.parse(
            file_bytes=file_bytes,
            custom_mapping=custom_mapping,
            bank_profile=bank_profile,
        )

        if not parse_result.valid_rows and parse_result.rejected_rows:
            err_msg = parse_result.rejected_rows[0].reason
            raise ValidationError(f"Bank statement parsing failed: {err_msg}")

        # 5. Persist import in READY_FOR_IMPORT status
        import_record = self.repo.create_statement_import(
            society_id=society_id,
            file_name=file_name,
            file_checksum=checksum,
            uploaded_by=claims.user_id,
            status=StatementImportStatus.READY_FOR_IMPORT,
            bank_name=bank_profile if bank_profile != "AUTO" else None,
        )
        import_record.total_rows = parse_result.total_rows
        import_record.valid_rows = len(parse_result.valid_rows)
        import_record.rejected_rows = len(parse_result.rejected_rows)
        import_record.error_summary = {
            "detected_headers": parse_result.detected_headers,
            "bank_profile": parse_result.bank_profile,
            "sample_errors": [
                {"row": r.source_row_number, "reason": r.reason}
                for r in parse_result.rejected_rows[:10]
            ],
            # Cache the serialized valid rows in metadata for confirm phase
            "cached_valid_rows": [
                {
                    "source_row_number": r.source_row_number,
                    "transaction_date": r.transaction_date.isoformat(),
                    "value_date": r.value_date.isoformat() if r.value_date else None,
                    "description": r.description,
                    "normalized_description": r.normalized_description,
                    "reference_number": r.reference_number,
                    "utr_number": r.utr_number,
                    "transaction_type": r.transaction_type.value,
                    "debit_paise": r.debit_paise,
                    "credit_paise": r.credit_paise,
                    "balance_paise": r.balance_paise,
                    "transaction_fingerprint": r.transaction_fingerprint,
                }
                for r in parse_result.valid_rows
            ],
        }

        self.db.commit()
        self.db.refresh(import_record)

        preview_items = [
            TransactionPreviewItem(
                source_row_number=r.source_row_number,
                transaction_date=r.transaction_date,
                description=r.description,
                reference_number=r.reference_number,
                utr_number=r.utr_number,
                transaction_type=r.transaction_type,
                debit_paise=r.debit_paise,
                credit_paise=r.credit_paise,
                balance_paise=r.balance_paise,
            )
            for r in parse_result.valid_rows[:15]
        ]

        return StatementUploadPreviewResponse(
            import_id=import_record.id,
            file_name=import_record.file_name,
            file_checksum=import_record.file_checksum,
            status=import_record.status,
            total_rows=import_record.total_rows,
            valid_rows=import_record.valid_rows,
            rejected_rows=import_record.rejected_rows,
            detected_headers=parse_result.detected_headers,
            bank_profile=parse_result.bank_profile,
            preview_transactions=preview_items,
            rejected_samples=[
                {"row": r.source_row_number, "reason": r.reason}
                for r in parse_result.rejected_rows[:10]
            ],
            created_at=import_record.created_at,
        )

    # -------------------------------------------------------------------------
    # 2. Confirm Import & Run Deterministic Matching Asynchronously
    # -------------------------------------------------------------------------
    def confirm_import(
        self,
        claims: CurrentUserClaims,
        import_id: UUID,
    ) -> BankStatementImportResponse:
        self._verify_helpdesk_role(claims)

        # 1. Atomically claim the statement import row using SELECT FOR UPDATE
        import_record = self.repo.get_statement_import_for_update(import_id)
        if not import_record:
            raise NotFoundError(f"Statement import {import_id} not found")
        self._verify_society_access(claims, import_record.society_id)

        if import_record.status not in (
            StatementImportStatus.READY_FOR_IMPORT,
            StatementImportStatus.UPLOADED,
        ):
            raise ValidationError(
                f"Cannot confirm statement import in status '{import_record.status}'. "
                "Only READY_FOR_IMPORT statements can be confirmed."
            )

        import_record.status = StatementImportStatus.PROCESSING
        self.db.flush()

        cached_rows = import_record.error_summary.get("cached_valid_rows", [])
        if not cached_rows:
            import_record.status = StatementImportStatus.FAILED
            self.db.commit()
            raise ValidationError("No valid transaction rows found in cached upload.")

        society_id = import_record.society_id

        # 2. Multi-layer duplicate detection
        fingerprints = [r["transaction_fingerprint"] for r in cached_rows]
        utrs = [r["utr_number"] for r in cached_rows if r.get("utr_number")]

        existing_fps = self.repo.find_duplicate_fingerprints(society_id, fingerprints)
        existing_utrs = self.repo.find_duplicate_utrs(society_id, utrs)

        # Track duplicates inside the same file as well
        seen_fps_in_file: dict[str, UUID] = {}
        seen_utrs_in_file: dict[str, UUID] = {}

        transactions_to_create: list[BankTransaction] = []
        duplicate_count = 0

        for r in cached_rows:
            txn_id = uuid.uuid4()
            fp = r["transaction_fingerprint"]
            utr = r.get("utr_number")

            if fp in existing_fps or fp in seen_fps_in_file:
                # Fingerprint already exists in DB or earlier in file -> skip insertion to satisfy uq_bank_transactions_society_fingerprint
                duplicate_count += 1
                continue
            elif utr and (utr in existing_utrs or utr in seen_utrs_in_file):
                # Duplicate by UTR, but with unique fingerprint
                duplicate_count += 1
                seen_fps_in_file[fp] = txn_id
                dup_id = existing_utrs.get(utr) or seen_utrs_in_file.get(utr)
                status = TransactionReconciliationStatus.DUPLICATE
                is_dup = True
            else:
                seen_fps_in_file[fp] = txn_id
                if utr:
                    seen_utrs_in_file[utr] = txn_id
                status = TransactionReconciliationStatus.UNMATCHED
                is_dup = False
                dup_id = None

            v_date = datetime.fromisoformat(r["value_date"]) if r.get("value_date") else None
            t_date = datetime.fromisoformat(r["transaction_date"])

            transactions_to_create.append(
                BankTransaction(
                    id=txn_id,
                    society_id=society_id,
                    import_id=import_record.id,
                    source_row_number=r["source_row_number"],
                    transaction_date=t_date,
                    value_date=v_date,
                    description=r["description"],
                    normalized_description=r["normalized_description"],
                    reference_number=r.get("reference_number"),
                    utr_number=r.get("utr_number"),
                    transaction_type=TransactionType(r["transaction_type"]),
                    debit_paise=r["debit_paise"],
                    credit_paise=r["credit_paise"],
                    balance_paise=r.get("balance_paise"),
                    allocated_paise=0,
                    reconciliation_status=status,
                    transaction_fingerprint=fp,
                    is_duplicate=is_dup,
                    duplicate_of_id=dup_id,
                )
            )

        if transactions_to_create:
            self.repo.create_transactions_batch(transactions_to_create)

        # 3. Finalize Ingestion Metadata
        import_record.duplicate_rows = duplicate_count
        import_record.imported_rows = len(transactions_to_create)
        import_record.status = StatementImportStatus.PROCESSING

        # Clear cached raw rows from metadata to save storage
        meta = dict(import_record.error_summary)
        meta.pop("cached_valid_rows", None)
        import_record.error_summary = meta

        # 4. Outbox Event: enqueue reconciliation.process_bank_statement for asynchronous matching worker
        outbox = OutboxEvent(
            event_type="reconciliation.process_bank_statement",
            aggregate_type="bank_statement_import",
            aggregate_id=str(import_record.id),
            payload={
                "import_id": str(import_record.id),
                "society_id": str(society_id),
                "imported_rows": import_record.imported_rows,
                "duplicate_rows": import_record.duplicate_rows,
            },
            status=OutboxStatus.PENDING,
        )
        self.db.add(outbox)

        # 5. Audit event
        audit = AuditEvent(
            society_id=society_id,
            actor_id=claims.user_id,
            action="STATEMENT_CONFIRMED",
            resource_type="bank_statement_import",
            resource_id=str(import_record.id),
            correlation_id=str(uuid.uuid4()),
            event_metadata={
                "file_name": import_record.file_name,
                "imported_rows": import_record.imported_rows,
                "duplicate_rows": import_record.duplicate_rows,
                "rejected_rows": import_record.rejected_rows,
            },
        )
        self.db.add(audit)

        self.db.commit()
        self.db.refresh(import_record)
        return BankStatementImportResponse.model_validate(import_record)

        return BankStatementImportResponse.model_validate(import_record)

    def cancel_import(self, claims: CurrentUserClaims, import_id: UUID) -> None:
        self._verify_helpdesk_role(claims)
        import_record = self.repo.get_statement_import_by_id(import_id)
        if not import_record:
            raise NotFoundError(f"Statement import {import_id} not found")
        self._verify_society_access(claims, import_record.society_id)

        if import_record.status != StatementImportStatus.READY_FOR_IMPORT:
            raise ValidationError(f"Cannot cancel import in status '{import_record.status}'")

        import_record.status = StatementImportStatus.CANCELLED
        self.db.commit()

    # -------------------------------------------------------------------------
    # 3. Transaction Listings & Details
    # -------------------------------------------------------------------------
    def list_transactions(
        self,
        claims: CurrentUserClaims,
        society_id: UUID,
        status: TransactionReconciliationStatus | None = None,
        transaction_type: TransactionType | None = None,
        import_id: UUID | None = None,
        search: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[BankTransactionResponse]:
        self._verify_helpdesk_role(claims)
        self._verify_society_access(claims, society_id)

        txns = self.repo.list_transactions(
            society_id=society_id,
            status=status,
            transaction_type=transaction_type,
            import_id=import_id,
            search=search,
            date_from=date_from,
            date_to=date_to,
            skip=skip,
            limit=limit,
        )

        return [self._to_transaction_response(t) for t in txns]

    def get_transaction(
        self, claims: CurrentUserClaims, transaction_id: UUID
    ) -> BankTransactionResponse:
        self._verify_helpdesk_role(claims)
        txn = self.repo.get_transaction_by_id(transaction_id)
        if not txn:
            raise NotFoundError(f"Transaction {transaction_id} not found")
        self._verify_society_access(claims, txn.society_id)

        return self._to_transaction_response(txn)

    def _to_transaction_response(self, txn: BankTransaction) -> BankTransactionResponse:
        unallocated = max(0, txn.credit_paise - txn.allocated_paise)
        matches_res: list[ReconciliationMatchResponse] = []

        # Populate flat / invoice / resident metadata for matches
        for m in txn.matches:
            flat = self.db.query(Flat).filter(Flat.id == m.flat_id).first() if m.flat_id else None
            res_user = (
                self.db.query(User).filter(User.id == m.resident_id).first()
                if m.resident_id
                else None
            )
            inv = (
                self.db.query(Invoice).filter(Invoice.id == m.invoice_id).first()
                if m.invoice_id
                else None
            )
            pay = (
                self.db.query(Payment).filter(Payment.id == m.existing_payment_id).first()
                if m.existing_payment_id
                else None
            )

            inv_out = None
            if inv:
                _, inv_out, _, _ = self.billing_service.calculate_invoice_financials(inv)

            matches_res.append(
                ReconciliationMatchResponse(
                    id=m.id,
                    transaction_id=m.transaction_id,
                    flat_id=m.flat_id,
                    flat_number=flat.flat_number if flat else None,
                    resident_id=m.resident_id,
                    resident_name=res_user.full_name if res_user else None,
                    invoice_id=m.invoice_id,
                    invoice_number=inv.invoice_number if inv else None,
                    invoice_total_paise=inv.total_paise if inv else None,
                    invoice_outstanding_paise=inv_out,
                    existing_payment_id=m.existing_payment_id,
                    existing_payment_reference=pay.provider_reference if pay else None,
                    confidence_score=m.confidence_score,
                    confidence_tier=m.confidence_tier,
                    matching_level=m.matching_level,
                    explanation=m.explanation,
                    evidence=m.evidence,
                    is_selected=m.is_selected,
                    created_at=m.created_at,
                )
            )

        return BankTransactionResponse(
            id=txn.id,
            society_id=txn.society_id,
            import_id=txn.import_id,
            source_row_number=txn.source_row_number,
            transaction_date=txn.transaction_date,
            value_date=txn.value_date,
            description=txn.description,
            normalized_description=txn.normalized_description,
            reference_number=txn.reference_number,
            utr_number=txn.utr_number,
            transaction_type=txn.transaction_type,
            debit_paise=txn.debit_paise,
            credit_paise=txn.credit_paise,
            balance_paise=txn.balance_paise,
            allocated_paise=txn.allocated_paise,
            unallocated_paise=unallocated,
            reconciliation_status=txn.reconciliation_status,
            transaction_fingerprint=txn.transaction_fingerprint,
            is_duplicate=txn.is_duplicate,
            duplicate_of_id=txn.duplicate_of_id,
            matches=matches_res,
            created_at=txn.created_at,
            updated_at=txn.updated_at,
        )

    # -------------------------------------------------------------------------
    # 4. Manual Reconciliation Review Queue
    # -------------------------------------------------------------------------
    def get_review_queue(
        self,
        claims: CurrentUserClaims,
        society_id: UUID,
        queue_category: str = "ALL",
        skip: int = 0,
        limit: int = 50,
    ) -> list[ManualReviewQueueItem]:
        self._verify_helpdesk_role(claims)
        self._verify_society_access(claims, society_id)

        # Queue categories filter
        status_filter: TransactionReconciliationStatus | None = None
        if queue_category == "UNMATCHED":
            status_filter = TransactionReconciliationStatus.UNMATCHED
        elif queue_category == "SUGGESTED":
            status_filter = TransactionReconciliationStatus.SUGGESTED
        elif queue_category == "PENDING_APPROVAL":
            status_filter = TransactionReconciliationStatus.PENDING_APPROVAL
        elif queue_category == "DUPLICATE_REVIEW":
            status_filter = TransactionReconciliationStatus.DUPLICATE

        txns = self.repo.list_transactions(
            society_id=society_id,
            status=status_filter,
            transaction_type=TransactionType.CREDIT,
            skip=skip,
            limit=limit,
        )

        items: list[ManualReviewQueueItem] = []
        for t in txns:
            # Skip already posted records from review queue unless specifically requested
            if (
                t.reconciliation_status == TransactionReconciliationStatus.POSTED
                and queue_category != "ALL"
            ):
                continue

            resp = self._to_transaction_response(t)
            top_match = next(
                (m for m in resp.matches if m.is_selected),
                resp.matches[0] if resp.matches else None,
            )

            # Determine category label
            cat = t.reconciliation_status.value
            if t.is_duplicate:
                cat = "DUPLICATE_REVIEW"
            elif top_match and top_match.evidence.get("is_ambiguous"):
                cat = "AMBIGUOUS"

            latest_review = t.reviews[0].notes if t.reviews else None

            items.append(
                ManualReviewQueueItem(
                    transaction=resp,
                    suggested_match=top_match,
                    candidates_count=len(resp.matches),
                    queue_category=cat,
                    latest_review_note=latest_review,
                )
            )

        return items

    def suggest_manual_match(
        self,
        claims: CurrentUserClaims,
        transaction_id: UUID,
        flat_id: UUID,
        invoice_id: UUID | None = None,
        notes: str | None = None,
    ) -> BankTransactionResponse:
        """Staff manually links a bank transaction to a flat and invoice."""
        self._verify_helpdesk_role(claims)
        txn = self.repo.get_transaction_by_id(transaction_id)
        if not txn:
            raise NotFoundError(f"Transaction {transaction_id} not found")
        self._verify_society_access(claims, txn.society_id)

        flat = (
            self.db.query(Flat)
            .filter(Flat.id == flat_id, Flat.society_id == txn.society_id)
            .first()
        )
        if not flat:
            raise NotFoundError(f"Flat {flat_id} not found in society")

        inv = None
        if invoice_id:
            inv = (
                self.db.query(Invoice)
                .filter(Invoice.id == invoice_id, Invoice.society_id == txn.society_id)
                .first()
            )
            if not inv:
                raise NotFoundError(f"Invoice {invoice_id} not found in society")

        # Clear existing selected matches
        for m in txn.matches:
            m.is_selected = False

        # Create manual match record
        manual_match = ReconciliationMatch(
            society_id=txn.society_id,
            transaction_id=txn.id,
            flat_id=flat.id,
            resident_id=None,
            invoice_id=inv.id if inv else None,
            existing_payment_id=None,
            confidence_score=100.0,
            confidence_tier=MatchConfidenceTier.HIGH,
            matching_level=MatchingLevel.MANUAL,
            explanation=f"Manually assigned by {claims.full_name}. Notes: {notes or 'None'}",
            evidence={"manual": True, "reviewer_id": str(claims.user_id)},
            is_selected=True,
        )
        self.db.add(manual_match)
        txn.reconciliation_status = TransactionReconciliationStatus.SUGGESTED

        self.repo.create_review(
            society_id=txn.society_id,
            transaction_id=txn.id,
            reviewer_id=claims.user_id,
            action="MANUAL_MATCH_SUGGESTED",
            notes=notes,
        )

        self.db.commit()
        return self.get_transaction(claims, transaction_id)

    def submit_for_approval(
        self,
        claims: CurrentUserClaims,
        transaction_id: UUID,
        proposed_allocations: list[ProposedAllocationItem],
        notes: str | None = None,
    ) -> BankTransactionResponse:
        """Staff proposes explicit invoice allocations and moves transaction to PENDING_APPROVAL."""
        self._verify_helpdesk_role(claims)
        txn = self.repo.get_transaction_by_id(transaction_id)
        if not txn:
            raise NotFoundError(f"Transaction {transaction_id} not found")
        self._verify_society_access(claims, txn.society_id)

        if txn.transaction_type != TransactionType.CREDIT:
            raise ValidationError("Only incoming credit transactions can be allocated to invoices.")

        if not proposed_allocations:
            raise ValidationError(
                "At least one proposed invoice allocation is required to submit for approval."
            )

        # Invariant: Sum of proposed allocations cannot exceed available credit
        total_proposed = sum(p.allocated_paise for p in proposed_allocations)
        available_credit = txn.credit_paise - txn.allocated_paise
        if total_proposed > available_credit:
            raise ValidationError(
                f"Sum of proposed allocations (₹{total_proposed / 100:,.2f}) exceeds available bank credit (₹{available_credit / 100:,.2f})."
            )

        # Validate that each invoice exists in this society
        for p in proposed_allocations:
            inv = (
                self.db.query(Invoice)
                .filter(Invoice.id == p.invoice_id, Invoice.society_id == txn.society_id)
                .first()
            )
            if not inv:
                raise NotFoundError(f"Invoice {p.invoice_id} not found in society")

        txn.reconciliation_status = TransactionReconciliationStatus.PENDING_APPROVAL

        self.repo.create_review(
            society_id=txn.society_id,
            transaction_id=txn.id,
            reviewer_id=claims.user_id,
            action="SUBMITTED_FOR_APPROVAL",
            notes=notes,
            proposed_allocations=[p.model_dump(mode="json") for p in proposed_allocations],
        )

        self.db.commit()
        return self.get_transaction(claims, transaction_id)

    # -------------------------------------------------------------------------
    # 5. Financial Allocation & Approval (Atomic & Idempotent Settlement)
    # -------------------------------------------------------------------------
    def approve_and_allocate(
        self,
        claims: CurrentUserClaims,
        transaction_id: UUID,
        proposed_allocations: list[ProposedAllocationItem],
        idempotency_key: str,
        correlation_id: str | None = None,
        notes: str | None = None,
    ) -> BankTransactionResponse:
        """Atomically approves and executes financial posting.

        FINANCIAL INVARIANTS ENFORCED:
        - Mandatory Idempotency-Key.
        - SELECT FOR UPDATE on BankTransaction and Invoice rows.
        - Dynamic recalculation of invoice balance post-lock.
        - Reconciles existing payment records without creating duplicate Payments or Ledger entries.
        - For direct bank transfers: Creates Payment, PaymentAllocation, and FinancialLedgerEntry.
        - Invoices cannot be over-allocated.
        - Bank credit cannot be over-allocated.
        - Append-only immutable ledger.
        """
        self._verify_helpdesk_role(claims)

        if not idempotency_key:
            raise ValidationError(
                "Idempotency-Key header is mandatory for reconciliation approval."
            )

        corr_id = correlation_id or str(uuid.uuid4())
        req_hash = hashlib.sha256(
            f"{claims.user_id}:{transaction_id}:{json.dumps([p.model_dump(mode='json') for p in proposed_allocations])}".encode()
        ).hexdigest()

        # STEP 1: Idempotency reservation
        idemp = self.billing_service._reserve_idempotency_key(
            idempotency_key=idempotency_key,
            scope="reconciliation_approve",
            req_hash=req_hash,
        )
        if idemp is not None:
            if idemp.request_hash != req_hash:
                raise ConflictError("Idempotency key reuse with differing payload is prohibited.")
            if idemp.response_body:
                data = json.loads(idemp.response_body)
                return BankTransactionResponse(**data)
            raise ConflictError("A reconciliation approval with this key is currently in progress.")

        try:
            # STEP 2: Lock transaction row with SELECT FOR UPDATE (resolving transaction's actual society)
            txn = self.repo.get_transaction_for_update(transaction_id)
            if not txn:
                raise NotFoundError(f"Transaction {transaction_id} not found")
            self._verify_society_access(claims, txn.society_id)

            if txn.transaction_type != TransactionType.CREDIT:
                raise ValidationError("Only credit transactions can be approved and posted.")

            # STEP 2.5: Server-side Dual Approval (Maker-Checker) Enforcement
            if txn.reconciliation_status == TransactionReconciliationStatus.PENDING_APPROVAL:
                latest_submit = (
                    self.db.query(ReconciliationReview)
                    .filter(
                        ReconciliationReview.transaction_id == txn.id,
                        ReconciliationReview.action == "SUBMITTED_FOR_APPROVAL",
                    )
                    .order_by(ReconciliationReview.created_at.desc())
                    .first()
                )
                if latest_submit:
                    # Rule 1: Segregation of duties (Approver cannot be the maker/submitter)
                    if latest_submit.reviewer_id == claims.user_id:
                        raise ValidationError(
                            "Dual approval policy violation: Approver cannot be the same user who submitted the proposal for approval (maker-checker segregation of duties). An independent authorized reviewer must approve."
                        )

                    # Adopt submitted allocations if omitted in approval request
                    if not proposed_allocations and latest_submit.proposed_allocations:
                        proposed_allocations = [
                            ProposedAllocationItem(
                                invoice_id=UUID(str(item["invoice_id"])),
                                allocated_paise=int(item["allocated_paise"]),
                            )
                            for item in latest_submit.proposed_allocations
                        ]

                    # Rule 2: Proposal integrity (Approved allocations must match submitted proposal allocations)
                    if latest_submit.proposed_allocations:
                        submitted_allocs = sorted(
                            (str(item["invoice_id"]), int(item["allocated_paise"]))
                            for item in latest_submit.proposed_allocations
                        )
                        current_allocs = sorted(
                            (str(p.invoice_id), int(p.allocated_paise))
                            for p in proposed_allocations
                        )
                        if submitted_allocs != current_allocs:
                            raise ValidationError(
                                "Dual approval policy violation: Approved allocations must match the submitted proposal allocations. If allocation modifications are necessary, reject the submission or submit an updated proposal."
                            )

            available_credit = txn.credit_paise - txn.allocated_paise
            total_alloc_paise = sum(p.allocated_paise for p in proposed_allocations)

            if total_alloc_paise > available_credit:
                raise ValidationError(
                    f"Requested allocation (₹{total_alloc_paise / 100:,.2f}) exceeds available bank credit (₹{available_credit / 100:,.2f})."
                )

            # Check if this transaction matches an existing successful provider payment
            selected_match = next(
                (m for m in txn.matches if m.is_selected and m.existing_payment_id), None
            )
            existing_payment: Payment | None = None
            if selected_match and selected_match.existing_payment_id:
                existing_payment = self.billing_repo.get_payment_for_update(
                    selected_match.existing_payment_id, society_id=txn.society_id
                )
                if not existing_payment:
                    raise NotFoundError(
                        f"Matched payment {selected_match.existing_payment_id} not found in society {txn.society_id}."
                    )

            settled_records: list[ReconciliationAllocation] = []
            settlement_metadata: dict[str, Any] = {}

            if existing_payment:
                if existing_payment.status != PaymentStatus.SUCCESS:
                    raise ValidationError(
                        f"Cannot reconcile against payment {existing_payment.id} with status {existing_payment.status}. Payment must be SUCCESS."
                    )
                if existing_payment.society_id != txn.society_id:
                    raise ValidationError(
                        f"Cross-society reconciliation rejected: payment {existing_payment.id} belongs to society {existing_payment.society_id}, not {txn.society_id}."
                    )

                # -----------------------------------------------------------------
                # Scenario A: Reconciling an EXISTING payment record (Zero Double-Count)
                # -----------------------------------------------------------------
                # Payment was already settled through payment provider and posted to ledger.
                # Do NOT create another Payment or PaymentAllocation. Link existing.
                # Do NOT create an ADJUSTMENT ledger entry (payment is already recorded on ledger).
                # Record bank matching as reconciliation metadata.
                if not existing_payment.allocations:
                    raise ValidationError(
                        f"Existing payment {existing_payment.id} has no payment allocations to reconcile."
                    )

                allocations_by_inv: dict[UUID, PaymentAllocation] = {
                    pa.invoice_id: pa for pa in existing_payment.allocations
                }

                # If caller did not provide proposed allocations, default to all allocations of the existing payment
                if not proposed_allocations:
                    proposed_allocations = [
                        ProposedAllocationItem(
                            invoice_id=pa.invoice_id, allocated_paise=pa.allocated_paise
                        )
                        for pa in existing_payment.allocations
                    ]

                total_alloc_paise = sum(p.allocated_paise for p in proposed_allocations)
                if total_alloc_paise > available_credit:
                    raise ValidationError(
                        f"Requested allocation (₹{total_alloc_paise / 100:,.2f}) exceeds available bank credit (₹{available_credit / 100:,.2f})."
                    )

                existing_alloc_total = sum(
                    pa.allocated_paise for pa in existing_payment.allocations
                )
                if total_alloc_paise != existing_alloc_total:
                    raise ValidationError(
                        f"Total allocation amount (₹{total_alloc_paise / 100:,.2f}) does not match existing payment allocated total (₹{existing_alloc_total / 100:,.2f})."
                    )

                # Lock and validate each proposed invoice
                for p in proposed_allocations:
                    inv = self.billing_repo.get_invoice_for_update(
                        p.invoice_id, society_id=txn.society_id
                    )
                    if not inv:
                        raise NotFoundError(
                            f"Invoice {p.invoice_id} not found in society {txn.society_id}."
                        )

                    # Validate invoice against existing payment's society and flat
                    if inv.society_id != existing_payment.society_id:
                        raise ValidationError(
                            f"Cross-society reconciliation rejected: invoice {inv.invoice_number} belongs to society {inv.society_id}, but payment belongs to {existing_payment.society_id}."
                        )
                    if inv.flat_id != existing_payment.flat_id:
                        raise ValidationError(
                            f"Cross-flat reconciliation rejected: invoice {inv.invoice_number} belongs to flat {inv.flat_id}, but payment belongs to flat {existing_payment.flat_id}."
                        )

                    # Validate against actual existing payment allocations
                    if p.invoice_id not in allocations_by_inv:
                        raise ValidationError(
                            f"Invoice {inv.invoice_number} is not an allocated invoice for existing payment {existing_payment.id}."
                        )
                    matched_pa = allocations_by_inv[p.invoice_id]
                    if p.allocated_paise != matched_pa.allocated_paise:
                        raise ValidationError(
                            f"Proposed allocation of ₹{p.allocated_paise / 100:,.2f} does not match existing payment allocation of ₹{matched_pa.allocated_paise / 100:,.2f} on invoice {inv.invoice_number}."
                        )

                    # Associate reconciliation allocation with the ACTUAL existing payment allocation
                    recon_alloc = self.repo.create_reconciliation_allocation(
                        society_id=txn.society_id,
                        transaction_id=txn.id,
                        invoice_id=p.invoice_id,
                        payment_id=existing_payment.id,
                        payment_allocation_id=matched_pa.id,
                        allocated_paise=p.allocated_paise,
                    )
                    settled_records.append(recon_alloc)

                settlement_metadata = {
                    "reconciliation_type": "EXISTING_PAYMENT_MATCH",
                    "matched_payment_id": str(existing_payment.id),
                    "provider": existing_payment.provider,
                    "provider_reference": existing_payment.provider_reference,
                    "payment_amount_paise": existing_payment.amount_paise,
                    "flat_id": str(existing_payment.flat_id),
                    "allocations": [
                        {
                            "invoice_id": str(p.invoice_id),
                            "payment_allocation_id": str(allocations_by_inv[p.invoice_id].id),
                            "allocated_paise": p.allocated_paise,
                        }
                        for p in proposed_allocations
                    ],
                }

            else:
                settlement_metadata = {
                    "reconciliation_type": "DIRECT_BANK_TRANSFER",
                }
                # -----------------------------------------------------------------
                # Scenario B: Direct Bank Transfer Settlement (Create Payment + Ledger)
                # -----------------------------------------------------------------
                # 1. Lock all target invoices & verify outstanding balances post-lock
                target_invoices: list[tuple[Invoice, int]] = []
                primary_flat_id: UUID | None = None

                for item in proposed_allocations:
                    inv = self.billing_repo.get_invoice_for_update(
                        item.invoice_id, society_id=txn.society_id
                    )
                    if not inv:
                        raise NotFoundError(f"Invoice {item.invoice_id} not found in society")

                    paid, outstanding, _, _ = self.billing_service.calculate_invoice_financials(inv)
                    if item.allocated_paise > outstanding:
                        raise ValidationError(
                            f"Allocation of ₹{item.allocated_paise / 100:,.2f} exceeds outstanding balance of ₹{outstanding / 100:,.2f} on invoice {inv.invoice_number}"
                        )
                    target_invoices.append((inv, item.allocated_paise))
                    primary_flat_id = inv.flat_id

                assert primary_flat_id is not None

                # 2. Group target invoices by flat_id to enforce payment-flat domain invariants
                flats_invoices: dict[UUID, list[tuple[Invoice, int]]] = {}
                for inv, alloc_paise in target_invoices:
                    flats_invoices.setdefault(inv.flat_id, []).append((inv, alloc_paise))

                base_ref = (
                    txn.utr_number or txn.reference_number or f"BANK-TXN-{txn.id.hex[:12].upper()}"
                )

                for flat_id, inv_allocs in flats_invoices.items():
                    flat_total_paise = sum(a for _, a in inv_allocs)
                    suffix = f"-{flat_id.hex[-6:].upper()}" if len(flats_invoices) > 1 else ""
                    payment_ref = f"{base_ref}{suffix}"

                    payment = self.billing_repo.create_payment(
                        society_id=txn.society_id,
                        flat_id=flat_id,
                        amount_paise=flat_total_paise,
                        provider="BANK_TRANSFER",
                        provider_reference=payment_ref,
                        status=PaymentStatus.SUCCESS,
                        initiated_by=claims.user_id,
                    )
                    self.db.flush()

                    for inv, alloc_paise in inv_allocs:
                        pay_alloc = self.billing_repo.create_payment_allocation(
                            payment_id=payment.id,
                            invoice_id=inv.id,
                            allocated_paise=alloc_paise,
                        )

                        # Update invoice status
                        _, curr_out, _, _ = self.billing_service.calculate_invoice_financials(inv)
                        new_out = max(0, curr_out - alloc_paise)
                        inv.status = (
                            InvoiceStatus.PAID if new_out == 0 else InvoiceStatus.PARTIALLY_PAID
                        )

                        # Ledger Entry: PAYMENT_RECEIVED
                        self.billing_repo.append_ledger_entry(
                            society_id=txn.society_id,
                            flat_id=inv.flat_id,
                            invoice_id=inv.id,
                            payment_id=payment.id,
                            entry_type=LedgerEntryType.PAYMENT_RECEIVED,
                            amount_paise=alloc_paise,
                            reference_id=payment_ref,
                            description=f"Bank transfer received: {txn.description[:100]}",
                        )

                        # Ledger Entry: PAYMENT_ALLOCATED
                        self.billing_repo.append_ledger_entry(
                            society_id=txn.society_id,
                            flat_id=inv.flat_id,
                            invoice_id=inv.id,
                            payment_id=payment.id,
                            entry_type=LedgerEntryType.PAYMENT_ALLOCATED,
                            amount_paise=alloc_paise,
                            reference_id=str(pay_alloc.id),
                            description=f"Funds allocated to invoice {inv.invoice_number}",
                        )

                        # Record ReconciliationAllocation
                        self.repo.create_reconciliation_allocation(
                            society_id=txn.society_id,
                            transaction_id=txn.id,
                            invoice_id=inv.id,
                            payment_id=payment.id,
                            payment_allocation_id=pay_alloc.id,
                            allocated_paise=alloc_paise,
                        )

            # Update BankTransaction allocation state
            txn.allocated_paise += total_alloc_paise
            txn.reconciliation_status = TransactionReconciliationStatus.POSTED

            # Log review action
            self.repo.create_review(
                society_id=txn.society_id,
                transaction_id=txn.id,
                reviewer_id=claims.user_id,
                action="APPROVED_AND_POSTED",
                notes=notes,
                proposed_allocations=[p.model_dump(mode="json") for p in proposed_allocations],
                metadata=settlement_metadata,
            )

            # Audit event
            audit = AuditEvent(
                society_id=txn.society_id,
                actor_id=claims.user_id,
                action="RECONCILIATION_POSTED",
                resource_type="bank_transaction",
                resource_id=str(txn.id),
                correlation_id=corr_id,
                event_metadata={
                    "allocated_paise": total_alloc_paise,
                    "remaining_unallocated_paise": txn.credit_paise - txn.allocated_paise,
                    "invoices": [str(p.invoice_id) for p in proposed_allocations],
                    "reconciliation_type": settlement_metadata.get(
                        "reconciliation_type", "UNKNOWN"
                    ),
                    "matched_payment_id": str(existing_payment.id) if existing_payment else None,
                    "provider_reference": existing_payment.provider_reference
                    if existing_payment
                    else None,
                },
            )
            self.db.add(audit)

            # Outbox event
            outbox = OutboxEvent(
                event_type="reconciliation.approved_and_posted",
                aggregate_type="bank_transaction",
                aggregate_id=str(txn.id),
                payload={
                    "transaction_id": str(txn.id),
                    "society_id": str(txn.society_id),
                    "allocated_paise": total_alloc_paise,
                    "reconciliation_type": settlement_metadata.get(
                        "reconciliation_type", "UNKNOWN"
                    ),
                    "matched_payment_id": str(existing_payment.id) if existing_payment else None,
                },
                status=OutboxStatus.PENDING,
            )
            self.db.add(outbox)

            txn_resp = self._to_transaction_response(txn)

            # Persist outcome in idempotency record
            self.billing_service._complete_idempotency_key(
                idempotency_key=idempotency_key,
                scope="reconciliation_approve",
                req_hash=req_hash,
                status=200,
                body=json.dumps(txn_resp.model_dump(mode="json")),
            )

            self.db.commit()
            return txn_resp

        except Exception as exc:
            self.db.rollback()
            self.billing_service._fail_idempotency_key(
                idempotency_key=idempotency_key,
                scope="reconciliation_approve",
                req_hash=req_hash,
                status=422,
                message=str(exc),
            )
            raise

    def reject_match(
        self,
        claims: CurrentUserClaims,
        transaction_id: UUID,
        reason: str,
    ) -> BankTransactionResponse:
        self._verify_helpdesk_role(claims)
        txn = self.repo.get_transaction_by_id(transaction_id)
        if not txn:
            raise NotFoundError(f"Transaction {transaction_id} not found")
        self._verify_society_access(claims, txn.society_id)

        txn.reconciliation_status = TransactionReconciliationStatus.REJECTED
        for m in txn.matches:
            m.is_selected = False

        self.repo.create_review(
            society_id=txn.society_id,
            transaction_id=txn.id,
            reviewer_id=claims.user_id,
            action="REJECTED",
            notes=reason,
        )

        self.db.commit()
        return self.get_transaction(claims, transaction_id)

    def mark_unidentified(
        self,
        claims: CurrentUserClaims,
        transaction_id: UUID,
        notes: str,
    ) -> BankTransactionResponse:
        self._verify_helpdesk_role(claims)
        txn = self.repo.get_transaction_by_id(transaction_id)
        if not txn:
            raise NotFoundError(f"Transaction {transaction_id} not found")
        self._verify_society_access(claims, txn.society_id)

        txn.reconciliation_status = TransactionReconciliationStatus.UNIDENTIFIED
        for m in txn.matches:
            m.is_selected = False

        self.repo.create_review(
            society_id=txn.society_id,
            transaction_id=txn.id,
            reviewer_id=claims.user_id,
            action="MARKED_UNIDENTIFIED",
            notes=notes,
        )

        self.db.commit()
        return self.get_transaction(claims, transaction_id)

    # -------------------------------------------------------------------------
    # 6. Reporting & Summary
    # -------------------------------------------------------------------------
    def get_summary(
        self, claims: CurrentUserClaims, society_id: UUID
    ) -> ReconciliationSummaryResponse:
        self._verify_helpdesk_role(claims)
        self._verify_society_access(claims, society_id)

        summary_data = self.repo.get_society_reconciliation_summary(society_id)
        return ReconciliationSummaryResponse(**summary_data)

    def export_report_csv(
        self,
        claims: CurrentUserClaims,
        society_id: UUID,
        status: TransactionReconciliationStatus | None = None,
    ) -> str:
        """Generates a CSV report with CSV formula injection protection."""
        self._verify_helpdesk_role(claims)
        self._verify_society_access(claims, society_id)

        txns = self.repo.list_transactions(society_id=society_id, status=status, limit=1000)

        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow(
            [
                "Transaction ID",
                "Date",
                "Description",
                "Reference / UTR",
                "Type",
                "Credit Amount (INR)",
                "Allocated Amount (INR)",
                "Unallocated Amount (INR)",
                "Status",
            ]
        )

        for t in txns:
            unalloc = max(0, t.credit_paise - t.allocated_paise)
            writer.writerow(
                [
                    sanitize_for_csv_export(str(t.id)),
                    sanitize_for_csv_export(t.transaction_date.strftime("%Y-%m-%d")),
                    sanitize_for_csv_export(t.description),
                    sanitize_for_csv_export(t.utr_number or t.reference_number or ""),
                    sanitize_for_csv_export(t.transaction_type.value),
                    f"{t.credit_paise / 100:.2f}",
                    f"{t.allocated_paise / 100:.2f}",
                    f"{unalloc / 100:.2f}",
                    sanitize_for_csv_export(t.reconciliation_status.value),
                ]
            )

        return output.getvalue()
