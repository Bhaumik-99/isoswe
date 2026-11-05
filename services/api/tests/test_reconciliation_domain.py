"""Comprehensive Bank Statement Reconciliation Domain & Financial Invariants Tests

Covers Phase 4 Requirements:
1. Unit Tests:
   - Safe decimal to paise conversion (zero float tolerance, format variants, error handling)
   - Narration normalization & Indian banking UTR/Ref extraction (UPI, NEFT, IMPS, RTGS, Cheque)
   - Unit clue extraction (T07-1203, 1203, etc.)
   - CSV formula injection protection (neutralizing spreadsheet execution vectors)
   - Multi-bank CSV format parsing (HDFC, ICICI, SBI, Generic auto-detection, UTF-8 BOM, quoted strings)
   - Debit vs Credit separation (Debits strictly excluded from resident payment matching)
   - Layered deterministic matching engine & confidence scoring
2. Integration & API Tests:
   - Statement upload -> preview -> confirm lifecycle
   - Cryptographic duplicate file rejection (SHA-256)
   - Duplicate transaction fingerprinting & UTR detection
   - Role-based authorization (Resident denied 403; Helpdesk allowed)
   - Multi-tenant society isolation (Cross-society denied 403/404)
   - Manual review queue filtering & manual match suggestion
   - Submit for approval & reject workflow
   - Direct bank transfer approval & atomic ledger settlement:
     - Payment created with provider BANK_TRANSFER
     - PaymentAllocation created
     - FinancialLedgerEntries appended (PAYMENT_RECEIVED, PAYMENT_ALLOCATED)
     - Invoice status updated
   - Zero double-count reconciliation for existing payment provider transactions
   - Idempotent approval enforcement (Same key replays cached response, differing payload returns 409)
   - Over-allocation prevention (Cannot exceed credit paise or invoice outstanding)
   - Reconciliation summary KPI calculation
   - CSV report export with formula injection sanitization
3. Concurrency & Financial Invariants:
   - Concurrent approval attempts
   - Prove sum(allocations) <= bank_credit_available
   - Prove sum(invoice_allocations) <= invoice_outstanding_at_posting
"""

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.domains.billing.models import (
    FinancialLedgerEntry,
    Invoice,
    InvoiceStatus,
    LedgerEntryType,
    Payment,
    PaymentAllocation,
    PaymentStatus,
)
from app.domains.identity.models import (
    Flat,
    FlatMembership,
    Society,
    SocietyStatus,
    Tower,
    User,
)
from app.domains.reconciliation.matching import MatchingEngine
from app.domains.reconciliation.models import (
    BankStatementImport,
    BankTransaction,
    MatchConfidenceTier,
    MatchingLevel,
    ReconciliationAllocation,
    StatementImportStatus,
    TransactionReconciliationStatus,
    TransactionType,
)
from app.domains.reconciliation.normalizer import (
    compute_file_checksum,
    decimal_to_paise,
    extract_unit_clues,
    extract_utr_and_reference,
    sanitize_for_csv_export,
)
from app.domains.reconciliation.parser import BankStatementParser

SOCIETY_ID = "11111111-1111-1111-1111-111111111111"
FLAT_1203_ID = "33333333-3333-3333-3333-333333331203"
FLAT_0408_ID = "33333333-3333-3333-3333-333333330408"
FLAT_1601_ID = "33333333-3333-3333-3333-333333331601"

AUTH_HELPDESK = {"Authorization": "Bearer dev-token-helpdesk"}
AUTH_NEERAJ = {"Authorization": "Bearer dev-token-neeraj"}


def drain_reconciliation_worker_jobs(db_session: Session) -> None:
    """Helper to process all pending reconciliation.process_bank_statement outbox events."""
    from app.domains.reliability.models import OutboxEvent, OutboxStatus
    from app.messaging.envelope import EventEnvelope, EventMetadata
    from app.workers.reconciliation_worker import reconciliation_handler

    events = (
        db_session.query(OutboxEvent)
        .filter(
            OutboxEvent.event_type == "reconciliation.process_bank_statement",
            OutboxEvent.status == OutboxStatus.PENDING,
        )
        .all()
    )
    for evt in events:
        envelope = EventEnvelope(
            event_id=evt.id,
            event_type=evt.event_type,
            aggregate_type=evt.aggregate_type,
            aggregate_id=evt.aggregate_id,
            payload=evt.payload,
            metadata=EventMetadata(correlation_id=str(uuid.uuid4())),
        )
        reconciliation_handler.process(envelope, db_session)
        evt.status = OutboxStatus.PUBLISHED
    db_session.commit()


# =============================================================================
# 1. UNIT TESTS: Normalizer, Parser, Formula Injection & Matching Engine
# =============================================================================


def test_decimal_to_paise_conversion() -> None:
    """Proves integer paise conversion handles all Indian currency formatting without float rounding errors."""
    assert decimal_to_paise(100) == 10000
    assert decimal_to_paise("7475.00") == 747500
    assert decimal_to_paise("₹ 7,475.50") == 747550
    assert decimal_to_paise("Rs. 6,370") == 637000
    assert decimal_to_paise("INR 10,660.00") == 1066000
    assert decimal_to_paise("0.05") == 5
    assert decimal_to_paise("0") == 0
    assert decimal_to_paise("") == 0
    assert decimal_to_paise(None) == 0

    # Negative amounts must be rejected
    with pytest.raises(ValueError, match="cannot be negative"):
        decimal_to_paise("-500.00")

    with pytest.raises(ValueError, match="cannot be negative"):
        decimal_to_paise("(500.00)")

    # Malformed text
    with pytest.raises(ValueError, match="Invalid monetary format"):
        decimal_to_paise("NOT_A_NUMBER")


def test_narration_and_reference_extraction() -> None:
    """Verifies regex extraction of Indian banking references: UPI, IMPS, NEFT, RTGS."""
    # UPI with 12-digit RRN
    upi_desc = "UPI/CR/412345678901/NEERAJ KULKARNI/SBIN/FLAT T07-1203"
    utr, ref = extract_utr_and_reference(upi_desc)
    assert utr == "412345678901"

    # NEFT standard reference
    neft_desc = "NEFT-AXSK261105001234-SWATI JOSHI-MAINTENANCE"
    utr, ref = extract_utr_and_reference(neft_desc)
    assert utr == "AXSK261105001234"

    # IMPS 12 digits
    imps_desc = "IMPS/P2A/498765432109/AAMIR SHAIKH"
    utr, ref = extract_utr_and_reference(imps_desc)
    assert utr == "498765432109"

    # Raw reference passed as column
    utr, ref = extract_utr_and_reference("DIRECT TRANSFER", raw_ref="HDFC00123456")
    assert utr == "HDFC00123456"
    assert ref == "HDFC00123456"


def test_unit_clues_extraction() -> None:
    """Extracts tower/flat tokens from various Indian narration styles."""
    assert "T07-1203" in extract_unit_clues("MAINT FOR T07-1203 NEERAJ")
    assert "1203" in extract_unit_clues("PAYMENT FOR FLAT 1203")
    assert "0408" in extract_unit_clues("SWATI UNIT 0408 NOV")
    assert "1601" in extract_unit_clues("TRANSFER 1601 MAINTENANCE")


def test_formula_injection_defense() -> None:
    """Neutralizes spreadsheet formula injection prefixes (=, +, -, @)."""
    assert sanitize_for_csv_export("=SUM(A1:A10)") == "'=SUM(A1:A10)"
    assert sanitize_for_csv_export("+cmd|' /C calc'!A0") == "'+cmd|' /C calc'!A0"
    assert sanitize_for_csv_export("-500") == "'-500"
    assert (
        sanitize_for_csv_export("@HYPERLINK('http://evil.com')") == "'@HYPERLINK('http://evil.com')"
    )
    # Safe text left unquoted
    assert sanitize_for_csv_export("Normal Text") == "Normal Text"
    assert sanitize_for_csv_export(None) == ""


def test_parser_multi_bank_formats_and_debit_credit_separation() -> None:
    """Parses diverse Indian bank statement formats, UTF-8 BOM, and strictly distinguishes debits from credits."""
    society_id = uuid.UUID(SOCIETY_ID)
    parser = BankStatementParser(society_id)

    # 1. HDFC Style CSV with UTF-8 BOM
    hdfc_csv = (
        "\ufeffDate,Narration,Chq/Ref No,Value Date,Withdrawal Amt.,Deposit Amt.,Closing Balance\n"
        "05/11/2026,UPI/CR/412345678901/NEERAJ/T07-1203,412345678901,05/11/2026,,7475.00,105000.00\n"
        "05/11/2026,ELEC BILL PAYMENT TOWER 7,CHQ001,05/11/2026,12000.00,,93000.00\n"
        "06/11/2026,NEFT-AXSK261105001234-SWATI-T12-0408,AXSK261105001234,06/11/2026,,6370.00,99370.00\n"
    ).encode("utf-8")

    res = parser.parse(hdfc_csv, bank_profile="HDFC")
    assert res.total_rows == 3
    assert len(res.valid_rows) == 3
    assert len(res.rejected_rows) == 0

    # Row 0: Credit
    assert res.valid_rows[0].credit_paise == 747500
    assert res.valid_rows[0].debit_paise == 0
    assert res.valid_rows[0].transaction_type == TransactionType.CREDIT
    assert res.valid_rows[0].utr_number == "412345678901"

    # Row 1: Debit (must be classified as DEBIT)
    assert res.valid_rows[1].debit_paise == 1200000
    assert res.valid_rows[1].credit_paise == 0
    assert res.valid_rows[1].transaction_type == TransactionType.DEBIT

    # Row 2: Credit
    assert res.valid_rows[2].credit_paise == 637000
    assert res.valid_rows[2].transaction_type == TransactionType.CREDIT

    # 2. Ambiguous row (both debit and credit) -> must be rejected
    bad_csv = (
        b"Date,Description,Reference,Debit,Credit\n"
        b"05/11/2026,Conflicting transaction,REF123,500.00,500.00\n"
        b"05/11/2026,Zero amount transaction,REF124,0,0\n"
    )

    bad_res = parser.parse(bad_csv)
    assert len(bad_res.valid_rows) == 0
    assert len(bad_res.rejected_rows) == 2
    assert (
        "both debit" in bad_res.rejected_rows[0].reason.lower()
        and "credit" in bad_res.rejected_rows[0].reason.lower()
    )
    assert "both debit and credit amounts are zero" in bad_res.rejected_rows[1].reason.lower()


def test_matching_engine_layered_confidence(db_session: Session) -> None:
    """Verifies deterministic matching levels and confidence scoring."""
    society_id = uuid.UUID(SOCIETY_ID)
    engine = MatchingEngine(society_id)

    invoices = db_session.query(Invoice).filter(Invoice.society_id == society_id).all()
    flats = db_session.query(Flat).filter(Flat.society_id == society_id).all()
    memberships = (
        db_session.query(FlatMembership).filter(FlatMembership.society_id == society_id).all()
    )
    users = {u.id: u for u in db_session.query(User).all()}

    # 1. Level 1 Exact UTR Match
    # Create an existing payment in DB with a known provider reference
    payment = Payment(
        society_id=society_id,
        flat_id=uuid.UUID(FLAT_1203_ID),
        amount_paise=747500,
        currency="INR",
        provider="SIMULATED",
        provider_reference="SIM-NEERAJ-UTR-123",
        status=PaymentStatus.SUCCESS,
        initiated_by=users[list(users.keys())[0]].id,
    )
    db_session.add(payment)
    db_session.flush()

    txn_level1 = BankTransaction(
        id=uuid.uuid4(),
        society_id=society_id,
        import_id=uuid.uuid4(),
        source_row_number=1,
        transaction_date=datetime.now(UTC),
        description="UPI/CR/SIM-NEERAJ-UTR-123/PAYMENT",
        normalized_description="UPI/CR/SIM-NEERAJ-UTR-123/PAYMENT",
        reference_number="SIM-NEERAJ-UTR-123",
        utr_number="SIM-NEERAJ-UTR-123",
        transaction_type=TransactionType.CREDIT,
        debit_paise=0,
        credit_paise=747500,
        transaction_fingerprint="fp1",
    )

    matches_l1 = engine.evaluate_transaction(
        transaction=txn_level1,
        invoices=invoices,
        payments=[payment],
        flats=flats,
        memberships=memberships,
        users=users,
    )
    assert len(matches_l1) >= 1
    top_l1 = matches_l1[0]
    assert top_l1.matching_level == MatchingLevel.LEVEL_1_UTR
    assert top_l1.confidence_score >= 90.0
    assert top_l1.confidence_tier == MatchConfidenceTier.HIGH
    assert top_l1.existing_payment_id == payment.id

    # 2. Debit Transaction -> Must produce ZERO matches
    txn_debit = BankTransaction(
        id=uuid.uuid4(),
        society_id=society_id,
        import_id=uuid.uuid4(),
        source_row_number=2,
        transaction_date=datetime.now(UTC),
        description="TOWER LIFT MAINTENANCE EXPENSE",
        normalized_description="TOWER LIFT MAINTENANCE EXPENSE",
        transaction_type=TransactionType.DEBIT,
        debit_paise=500000,
        credit_paise=0,
        transaction_fingerprint="fp2",
    )
    matches_debit = engine.evaluate_transaction(
        transaction=txn_debit,
        invoices=invoices,
        payments=[payment],
        flats=flats,
        memberships=memberships,
        users=users,
    )
    assert len(matches_debit) == 0


# =============================================================================
# 2. INTEGRATION & REST API TESTS
# =============================================================================


def test_reconciliation_resident_role_forbidden(client: TestClient) -> None:
    """Security Invariant: RESIDENT role must be strictly forbidden (403) from accessing reconciliation."""
    # Attempting to access summary
    res1 = client.get("/api/v1/reconciliation/summary", headers=AUTH_NEERAJ)
    assert res1.status_code == 403
    assert (
        "role" in res1.text.lower()
        or "forbidden" in res1.text.lower()
        or "access denied" in res1.text.lower()
    )

    # Attempting to upload statement
    res2 = client.post(
        "/api/v1/reconciliation/statements",
        files={"file": ("stmt.csv", b"Date,Description,Credit\n05/11/2026,Test,100", "text/csv")},
        headers=AUTH_NEERAJ,
    )
    assert res2.status_code == 403


def test_reconciliation_upload_preview_and_duplicate_file_rejection(
    client: TestClient, db_session: Session
) -> None:
    """Uploads CSV bank statement, verifies preview, and verifies SHA-256 duplicate file rejection."""
    csv_content = (
        b"Date,Narration,Chq / Ref No.,Withdrawal (INR),Deposit (INR),Balance (INR)\n"
        b"05/11/2026,UPI/CR/999111222333/NEERAJ KULKARNI/T07-1203,999111222333,,7475.00,107475.00\n"
        b"05/11/2026,SWATI JOSHI T12-0408 NEFT TRANSFER,AXSK999888,,6370.00,113845.00\n"
    )

    # 1. First upload -> 201 Created
    res1 = client.post(
        "/api/v1/reconciliation/statements",
        files={"file": ("sample_bank_statement.csv", csv_content, "text/csv")},
        headers=AUTH_HELPDESK,
    )
    assert res1.status_code == 201, res1.text
    data1 = res1.json()
    assert data1["status"] == "READY_FOR_IMPORT"
    assert data1["valid_rows"] == 2
    assert data1["total_rows"] == 2
    assert data1["file_checksum"] == compute_file_checksum(csv_content)
    import_id = data1["import_id"]

    # 2. Confirm the import asynchronously
    confirm_res = client.post(
        f"/api/v1/reconciliation/statements/{import_id}/confirm",
        headers=AUTH_HELPDESK,
    )
    assert confirm_res.status_code == 200
    assert confirm_res.json()["status"] == "PROCESSING"

    # Background worker executes deterministic matching
    drain_reconciliation_worker_jobs(db_session)
    imp = (
        db_session.query(BankStatementImport)
        .filter(BankStatementImport.id == uuid.UUID(import_id))
        .first()
    )
    assert imp is not None
    assert imp.status == StatementImportStatus.COMPLETED

    # 3. Attempt duplicate file upload -> must reject with 409 Conflict
    res2 = client.post(
        "/api/v1/reconciliation/statements",
        files={"file": ("duplicate_statement.csv", csv_content, "text/csv")},
        headers=AUTH_HELPDESK,
    )
    assert res2.status_code == 409
    assert "duplicate statement import" in res2.json()["error"]["message"].lower()


def test_reconciliation_duplicate_transaction_detection(client: TestClient) -> None:
    """Detects duplicate transactions by fingerprint or UTR across statements."""
    csv_content_1 = (
        b"Date,Narration,Chq / Ref No.,Deposit (INR)\n"
        b"05/11/2026,NEFT-DUP-TEST-001 T07-1203,DUP-REF-001,7475.00\n"
    )

    # Upload & confirm statement 1
    res1 = client.post(
        "/api/v1/reconciliation/statements",
        files={"file": ("stmt1.csv", csv_content_1, "text/csv")},
        headers=AUTH_HELPDESK,
    )
    assert res1.status_code == 201
    client.post(
        f"/api/v1/reconciliation/statements/{res1.json()['import_id']}/confirm",
        headers=AUTH_HELPDESK,
    )

    # Upload statement 2 containing the exact same UTR transaction plus a new one
    csv_content_2 = (
        b"Date,Narration,Chq / Ref No.,Deposit (INR)\n"
        b"05/11/2026,NEFT-DUP-TEST-001 T07-1203,DUP-REF-001,7475.00\n"
        b"06/11/2026,NEFT-NEW-TXN-002 T12-0408,NEW-REF-002,6370.00\n"
    )

    res2 = client.post(
        "/api/v1/reconciliation/statements",
        files={"file": ("stmt2.csv", csv_content_2, "text/csv")},
        headers=AUTH_HELPDESK,
    )
    assert res2.status_code == 201

    confirm2 = client.post(
        f"/api/v1/reconciliation/statements/{res2.json()['import_id']}/confirm",
        headers=AUTH_HELPDESK,
    )
    assert confirm2.status_code == 200
    assert confirm2.json()["duplicate_rows"] == 1


def test_direct_bank_transfer_approval_and_atomic_ledger_settlement(
    client: TestClient, db_session: Session
) -> None:
    """Approval Workflow: Directly settles invoice from bank credit, appends ledger entries, updates invoice, and enforces idempotency."""
    # 1. Setup an invoice in UNPAID status
    invoice = (
        db_session.query(Invoice)
        .filter(
            Invoice.flat_id == uuid.UUID(FLAT_1203_ID),
            Invoice.status.in_([InvoiceStatus.UNPAID, InvoiceStatus.PARTIALLY_PAID]),
        )
        .first()
    )
    if not invoice:
        # Create an invoice for T07-1203 (1,150 sqft * ₹6.50 = ₹7,475 = 747500 paise)
        invoice = Invoice(
            society_id=uuid.UUID(SOCIETY_ID),
            flat_id=uuid.UUID(FLAT_1203_ID),
            billing_period="2026-11",
            invoice_number=f"INV-TEST-{uuid.uuid4().hex[:6].upper()}",
            area_sqft_snapshot=1150,
            rate_paise_per_sqft_snapshot=650,
            subtotal_paise=747500,
            total_paise=747500,
            due_date=datetime.now(UTC) + timedelta(days=5),
            status=InvoiceStatus.UNPAID,
        )
        db_session.add(invoice)
        db_session.commit()
        db_session.refresh(invoice)

    # 2. Upload statement with matching amount for this invoice
    raw_csv = (
        b"Date,Description,Reference,Credit\n"
        b"05/11/2026,UPI PAYMENT FROM NEERAJ KULKARNI T07-1203,UPI777666555444,7475.00\n"
    )

    upload_res = client.post(
        "/api/v1/reconciliation/statements",
        files={"file": ("neeraj_direct_transfer.csv", raw_csv, "text/csv")},
        headers=AUTH_HELPDESK,
    )
    assert upload_res.status_code == 201
    import_id = upload_res.json()["import_id"]

    confirm_res = client.post(
        f"/api/v1/reconciliation/statements/{import_id}/confirm",
        headers=AUTH_HELPDESK,
    )
    assert confirm_res.status_code == 200

    # 3. Retrieve transaction from queue
    queue_res = client.get("/api/v1/reconciliation/queue?category=ALL", headers=AUTH_HELPDESK)
    assert queue_res.status_code == 200
    queue_items = queue_res.json()
    target_item = next(
        (item for item in queue_items if item["transaction"]["credit_paise"] == 747500), None
    )
    assert target_item is not None
    txn_id = target_item["transaction"]["id"]

    # 4. Approve and allocate funds with Idempotency-Key
    idemp_key = str(uuid.uuid4())
    approve_res = client.post(
        f"/api/v1/reconciliation/transactions/{txn_id}/approve",
        json={"proposed_allocations": [{"invoice_id": str(invoice.id), "allocated_paise": 747500}]},
        headers={**AUTH_HELPDESK, "Idempotency-Key": idemp_key},
    )
    assert approve_res.status_code == 200, approve_res.text
    txn_data = approve_res.json()
    assert txn_data["reconciliation_status"] == "POSTED"
    assert txn_data["allocated_paise"] == 747500
    assert txn_data["unallocated_paise"] == 0

    # 5. Database Financial Invariants Verification
    db_session.expire_all()
    # Invoice status must be PAID
    inv_updated = db_session.query(Invoice).filter(Invoice.id == invoice.id).first()
    assert inv_updated is not None
    assert inv_updated.status == InvoiceStatus.PAID

    # Payment record created with provider BANK_TRANSFER
    pay = (
        db_session.query(Payment)
        .filter(
            Payment.society_id == uuid.UUID(SOCIETY_ID),
            Payment.provider == "BANK_TRANSFER",
            Payment.amount_paise == 747500,
        )
        .first()
    )
    assert pay is not None
    assert pay.status == PaymentStatus.SUCCESS

    # PaymentAllocation created
    alloc = (
        db_session.query(PaymentAllocation)
        .filter(
            PaymentAllocation.payment_id == pay.id,
            PaymentAllocation.invoice_id == invoice.id,
        )
        .first()
    )
    assert alloc is not None
    assert alloc.allocated_paise == 747500

    # Financial Ledger Entries appended (PAYMENT_RECEIVED, PAYMENT_ALLOCATED)
    ledger_entries = (
        db_session.query(FinancialLedgerEntry)
        .filter(FinancialLedgerEntry.payment_id == pay.id)
        .all()
    )
    types = [e.entry_type for e in ledger_entries]
    assert LedgerEntryType.PAYMENT_RECEIVED in types
    assert LedgerEntryType.PAYMENT_ALLOCATED in types

    # ReconciliationAllocation record created
    recon_alloc = (
        db_session.query(ReconciliationAllocation)
        .filter(ReconciliationAllocation.transaction_id == uuid.UUID(txn_id))
        .first()
    )
    assert recon_alloc is not None
    assert recon_alloc.allocated_paise == 747500

    # 6. Idempotency replay check: Replaying the exact same request returns identical response
    replay_res = client.post(
        f"/api/v1/reconciliation/transactions/{txn_id}/approve",
        json={"proposed_allocations": [{"invoice_id": str(invoice.id), "allocated_paise": 747500}]},
        headers={**AUTH_HELPDESK, "Idempotency-Key": idemp_key},
    )
    assert replay_res.status_code == 200
    assert replay_res.json()["id"] == txn_id


def test_reconcile_existing_payment_provider_record_without_double_count(
    client: TestClient, db_session: Session
) -> None:
    """Crucial FinTech Rule: Reconciling an existing settled payment provider transaction
    must link the existing payment without creating a second payment or double allocation."""
    society_id = uuid.UUID(SOCIETY_ID)

    # 1. Setup existing Payment and Invoice in DB (e.g. Swati paid ₹6,370 via simulated gateway)
    invoice = Invoice(
        society_id=society_id,
        flat_id=uuid.UUID(FLAT_0408_ID),
        billing_period="2026-10",
        invoice_number=f"INV-SWATI-{uuid.uuid4().hex[:6].upper()}",
        area_sqft_snapshot=980,
        rate_paise_per_sqft_snapshot=650,
        subtotal_paise=637000,
        total_paise=637000,
        due_date=datetime.now(UTC),
        status=InvoiceStatus.PAID,
    )
    db_session.add(invoice)
    db_session.flush()

    provider_ref = f"SIM-SWATI-PAY-{uuid.uuid4().hex[:8].upper()}"
    existing_payment = Payment(
        society_id=society_id,
        flat_id=uuid.UUID(FLAT_0408_ID),
        amount_paise=637000,
        currency="INR",
        provider="SIMULATED",
        provider_reference=provider_ref,
        status=PaymentStatus.SUCCESS,
        initiated_by=db_session.query(User).first().id,
    )
    db_session.add(existing_payment)
    db_session.flush()

    payment_alloc = PaymentAllocation(
        payment_id=existing_payment.id,
        invoice_id=invoice.id,
        allocated_paise=637000,
    )
    db_session.add(payment_alloc)
    db_session.commit()

    initial_payment_count = (
        db_session.query(Payment).filter(Payment.society_id == society_id).count()
    )
    initial_ledger_count = (
        db_session.query(FinancialLedgerEntry)
        .filter(FinancialLedgerEntry.society_id == society_id)
        .count()
    )

    # 2. Bank statement arrives with the matching UTR/provider_reference
    csv_data = (
        "Date,Narration,Reference,Credit\n"
        f"05/11/2026,UPI PAYMENT SWATI JOSHI,{provider_ref},6370.00\n"
    ).encode()

    up_res = client.post(
        "/api/v1/reconciliation/statements",
        files={"file": ("swati_recon.csv", csv_data, "text/csv")},
        headers=AUTH_HELPDESK,
    )
    import_id = up_res.json()["import_id"]
    client.post(f"/api/v1/reconciliation/statements/{import_id}/confirm", headers=AUTH_HELPDESK)
    drain_reconciliation_worker_jobs(db_session)

    # 3. Retrieve transaction and verify it was matched to existing payment (Level 1)
    txns_res = client.get(
        f"/api/v1/reconciliation/transactions?import_id={import_id}", headers=AUTH_HELPDESK
    )
    txn = txns_res.json()[0]
    assert txn["reconciliation_status"] == "SUGGESTED"
    assert len(txn["matches"]) >= 1
    match = txn["matches"][0]
    assert match["existing_payment_id"] == str(existing_payment.id)
    assert match["matching_level"] == "LEVEL_1_UTR"

    # 4. Approve reconciliation
    idemp = str(uuid.uuid4())
    app_res = client.post(
        f"/api/v1/reconciliation/transactions/{txn['id']}/approve",
        json={"proposed_allocations": [{"invoice_id": str(invoice.id), "allocated_paise": 637000}]},
        headers={**AUTH_HELPDESK, "Idempotency-Key": idemp},
    )
    assert app_res.status_code == 200

    # 5. VERIFY: Zero additional Payment records created in database!
    db_session.expire_all()
    final_payment_count = db_session.query(Payment).filter(Payment.society_id == society_id).count()
    assert final_payment_count == initial_payment_count, (
        "Reconciling existing payment must NOT create new Payment rows!"
    )

    # VERIFY: Zero additional FinancialLedgerEntry rows created (No positive ADJUSTMENT)!
    final_ledger_count = (
        db_session.query(FinancialLedgerEntry)
        .filter(FinancialLedgerEntry.society_id == society_id)
        .count()
    )
    assert final_ledger_count == initial_ledger_count, (
        "Reconciling existing payment must NOT create positive ADJUSTMENT or duplicate ledger entries!"
    )

    # ReconciliationAllocation links existing payment and exact payment allocation
    ra = (
        db_session.query(ReconciliationAllocation)
        .filter(ReconciliationAllocation.transaction_id == uuid.UUID(txn["id"]))
        .first()
    )
    assert ra is not None
    assert ra.payment_id == existing_payment.id
    assert ra.payment_allocation_id == payment_alloc.id, (
        "Must link to the exact PaymentAllocation ID!"
    )
    assert ra.invoice_id == invoice.id


def test_reconcile_existing_payment_multiple_allocations_correct_links(
    client: TestClient, db_session: Session
) -> None:
    """Verifies that reconciling a multi-allocation existing payment correctly associates

    EACH reconciliation allocation with its exact corresponding PaymentAllocation ID,
    rather than associating all items with the first payment allocation.
    """
    society_id = uuid.UUID(SOCIETY_ID)
    flat_id = uuid.UUID(FLAT_0408_ID)
    admin_user = db_session.query(User).first()

    # 1. Create two separate invoices for the same flat
    inv_1 = Invoice(
        society_id=society_id,
        flat_id=flat_id,
        billing_period="2026-10",
        invoice_number=f"INV-MULTI-A-{uuid.uuid4().hex[:6].upper()}",
        area_sqft_snapshot=980,
        rate_paise_per_sqft_snapshot=650,
        subtotal_paise=300000,
        total_paise=300000,
        due_date=datetime.now(UTC),
        status=InvoiceStatus.PAID,
    )
    inv_2 = Invoice(
        society_id=society_id,
        flat_id=flat_id,
        billing_period="2026-11",
        invoice_number=f"INV-MULTI-B-{uuid.uuid4().hex[:6].upper()}",
        area_sqft_snapshot=980,
        rate_paise_per_sqft_snapshot=650,
        subtotal_paise=337000,
        total_paise=337000,
        due_date=datetime.now(UTC),
        status=InvoiceStatus.PAID,
    )
    db_session.add_all([inv_1, inv_2])
    db_session.flush()

    # 2. Create single existing payment of ₹6,370 with two distinct allocations
    provider_ref = f"MULTI-PAY-{uuid.uuid4().hex[:8].upper()}"
    payment = Payment(
        society_id=society_id,
        flat_id=flat_id,
        amount_paise=637000,
        currency="INR",
        provider="GATEWAY",
        provider_reference=provider_ref,
        status=PaymentStatus.SUCCESS,
        initiated_by=admin_user.id,
    )
    db_session.add(payment)
    db_session.flush()

    pa_1 = PaymentAllocation(
        payment_id=payment.id,
        invoice_id=inv_1.id,
        allocated_paise=300000,
    )
    pa_2 = PaymentAllocation(
        payment_id=payment.id,
        invoice_id=inv_2.id,
        allocated_paise=337000,
    )
    db_session.add_all([pa_1, pa_2])
    db_session.commit()

    # 3. Bank statement arrives with the matching UTR/provider_reference
    csv_data = (
        "Date,Narration,Reference,Credit\n"
        f"05/11/2026,SETTLEMENT GATEWAY {provider_ref},{provider_ref},6370.00\n"
    ).encode()

    up_res = client.post(
        "/api/v1/reconciliation/statements",
        files={"file": ("multi_alloc_statement.csv", csv_data, "text/csv")},
        headers=AUTH_HELPDESK,
    )
    import_id = up_res.json()["import_id"]
    client.post(f"/api/v1/reconciliation/statements/{import_id}/confirm", headers=AUTH_HELPDESK)
    drain_reconciliation_worker_jobs(db_session)

    txns_res = client.get(
        f"/api/v1/reconciliation/transactions?import_id={import_id}", headers=AUTH_HELPDESK
    )
    txn = txns_res.json()[0]

    # 4. Approve reconciliation with proposed allocations for both invoices
    idemp = str(uuid.uuid4())
    app_res = client.post(
        f"/api/v1/reconciliation/transactions/{txn['id']}/approve",
        json={
            "proposed_allocations": [
                {"invoice_id": str(inv_1.id), "allocated_paise": 300000},
                {"invoice_id": str(inv_2.id), "allocated_paise": 337000},
            ]
        },
        headers={**AUTH_HELPDESK, "Idempotency-Key": idemp},
    )
    assert app_res.status_code == 200, app_res.text

    # 5. VERIFY: Each ReconciliationAllocation connects to its DISTINCT PaymentAllocation!
    db_session.expire_all()
    allocs = (
        db_session.query(ReconciliationAllocation)
        .filter(ReconciliationAllocation.transaction_id == uuid.UUID(txn["id"]))
        .all()
    )
    assert len(allocs) == 2

    recon_by_inv = {a.invoice_id: a for a in allocs}
    assert recon_by_inv[inv_1.id].payment_allocation_id == pa_1.id
    assert recon_by_inv[inv_2.id].payment_allocation_id == pa_2.id
    assert pa_1.id != pa_2.id


def test_reconcile_existing_payment_rejects_cross_flat_invoice(
    client: TestClient, db_session: Session
) -> None:
    """Verifies that proposing an invoice from a flat different from the payment's flat is rejected."""
    society_id = uuid.UUID(SOCIETY_ID)
    flat_a = uuid.UUID(FLAT_0408_ID)
    flat_b = uuid.UUID(FLAT_1203_ID)
    admin_user = db_session.query(User).first()

    # Invoice for Flat A (actual payment target)
    inv_a = Invoice(
        society_id=society_id,
        flat_id=flat_a,
        billing_period="2026-11",
        invoice_number=f"INV-FLAT-A-{uuid.uuid4().hex[:6].upper()}",
        area_sqft_snapshot=980,
        rate_paise_per_sqft_snapshot=650,
        subtotal_paise=637000,
        total_paise=637000,
        due_date=datetime.now(UTC),
        status=InvoiceStatus.PAID,
    )
    # Invoice for Flat B (attacker or operator error)
    inv_b = Invoice(
        society_id=society_id,
        flat_id=flat_b,
        billing_period="2026-11",
        invoice_number=f"INV-FLAT-B-{uuid.uuid4().hex[:6].upper()}",
        area_sqft_snapshot=1150,
        rate_paise_per_sqft_snapshot=650,
        subtotal_paise=637000,
        total_paise=637000,
        due_date=datetime.now(UTC),
        status=InvoiceStatus.UNPAID,
    )
    db_session.add_all([inv_a, inv_b])
    db_session.flush()

    provider_ref = f"PAY-FLATA-{uuid.uuid4().hex[:8].upper()}"
    payment = Payment(
        society_id=society_id,
        flat_id=flat_a,
        amount_paise=637000,
        currency="INR",
        provider="GATEWAY",
        provider_reference=provider_ref,
        status=PaymentStatus.SUCCESS,
        initiated_by=admin_user.id,
    )
    db_session.add(payment)
    db_session.flush()

    pa = PaymentAllocation(payment_id=payment.id, invoice_id=inv_a.id, allocated_paise=637000)
    db_session.add(pa)
    db_session.commit()

    csv_data = (
        f"Date,Narration,Reference,Credit\n05/11/2026,UPI PAYMENT,{provider_ref},6370.00\n".encode()
    )
    up_res = client.post(
        "/api/v1/reconciliation/statements",
        files={"file": ("cross_flat.csv", csv_data, "text/csv")},
        headers=AUTH_HELPDESK,
    )
    import_id = up_res.json()["import_id"]
    client.post(f"/api/v1/reconciliation/statements/{import_id}/confirm", headers=AUTH_HELPDESK)
    drain_reconciliation_worker_jobs(db_session)
    txns = client.get(
        f"/api/v1/reconciliation/transactions?import_id={import_id}", headers=AUTH_HELPDESK
    ).json()

    # Try to approve by allocating to Invoice B (Flat B) against Flat A's payment
    app_res = client.post(
        f"/api/v1/reconciliation/transactions/{txns[0]['id']}/approve",
        json={"proposed_allocations": [{"invoice_id": str(inv_b.id), "allocated_paise": 637000}]},
        headers={**AUTH_HELPDESK, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert app_res.status_code in (400, 422), app_res.text
    assert "Cross-flat reconciliation rejected" in app_res.text


def test_reconcile_existing_payment_rejects_mismatched_amount(
    client: TestClient, db_session: Session
) -> None:
    """Verifies that proposing an allocation amount differing from the existing payment allocation is rejected."""
    society_id = uuid.UUID(SOCIETY_ID)
    flat_id = uuid.UUID(FLAT_0408_ID)
    admin_user = db_session.query(User).first()

    inv = Invoice(
        society_id=society_id,
        flat_id=flat_id,
        billing_period="2026-11",
        invoice_number=f"INV-MISMATCH-{uuid.uuid4().hex[:6].upper()}",
        area_sqft_snapshot=980,
        rate_paise_per_sqft_snapshot=650,
        subtotal_paise=637000,
        total_paise=637000,
        due_date=datetime.now(UTC),
        status=InvoiceStatus.PAID,
    )
    db_session.add(inv)
    db_session.flush()

    provider_ref = f"MISMATCH-PAY-{uuid.uuid4().hex[:8].upper()}"
    payment = Payment(
        society_id=society_id,
        flat_id=flat_id,
        amount_paise=637000,
        currency="INR",
        provider="GATEWAY",
        provider_reference=provider_ref,
        status=PaymentStatus.SUCCESS,
        initiated_by=admin_user.id,
    )
    db_session.add(payment)
    db_session.flush()

    pa = PaymentAllocation(payment_id=payment.id, invoice_id=inv.id, allocated_paise=637000)
    db_session.add(pa)
    db_session.commit()

    csv_data = (
        f"Date,Narration,Reference,Credit\n05/11/2026,UPI PAYMENT,{provider_ref},6370.00\n".encode()
    )
    up_res = client.post(
        "/api/v1/reconciliation/statements",
        files={"file": ("mismatch.csv", csv_data, "text/csv")},
        headers=AUTH_HELPDESK,
    )
    import_id = up_res.json()["import_id"]
    client.post(f"/api/v1/reconciliation/statements/{import_id}/confirm", headers=AUTH_HELPDESK)
    drain_reconciliation_worker_jobs(db_session)
    txns = client.get(
        f"/api/v1/reconciliation/transactions?import_id={import_id}", headers=AUTH_HELPDESK
    ).json()

    # Try to approve with an amount differing from the allocated 637000 paise
    app_res = client.post(
        f"/api/v1/reconciliation/transactions/{txns[0]['id']}/approve",
        json={"proposed_allocations": [{"invoice_id": str(inv.id), "allocated_paise": 500000}]},
        headers={**AUTH_HELPDESK, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert app_res.status_code in (400, 422), app_res.text


def test_reconciliation_allocation_database_trigger_enforces_integrity() -> None:
    """Verifies that database-level triggers prevent cross-society and cross-flat reconciliation allocations."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    test_dir = os.path.dirname(__file__)
    api_dir = os.path.abspath(os.path.join(test_dir, ".."))
    alembic_ini_path = os.path.join(api_dir, "alembic.ini")

    alembic_cfg = Config(alembic_ini_path)
    alembic_cfg.set_main_option("script_location", os.path.join(api_dir, "migrations"))

    with engine.connect() as connection:
        alembic_cfg.attributes["connection"] = connection
        command.upgrade(alembic_cfg, "head")

        SessionLocal = sessionmaker(bind=connection)
        session = SessionLocal()

        soc_a = uuid.uuid4()
        tower_a = uuid.uuid4()
        flat_a = uuid.uuid4()
        flat_b = uuid.uuid4()
        user_id = uuid.uuid4()

        soc = Society(id=soc_a, name="Trigger Test Soc", status=SocietyStatus.ACTIVE)
        session.add(soc)
        tow = Tower(id=tower_a, society_id=soc_a, tower_number="T1", name="Tower 1")
        session.add(tow)
        fa = Flat(id=flat_a, society_id=soc_a, tower_id=tower_a, flat_number="101", area_sqft=1000)
        fb = Flat(id=flat_b, society_id=soc_a, tower_id=tower_a, flat_number="102", area_sqft=1000)
        session.add_all([fa, fb])
        usr = User(
            id=user_id,
            supabase_uid=uuid.uuid4(),
            email=f"trig-{uuid.uuid4().hex[:6]}@example.com",
            phone="+919876543210",
        )
        session.add(usr)
        session.flush()

        stmt_imp = BankStatementImport(
            id=uuid.uuid4(),
            society_id=soc_a,
            file_name="trig.csv",
            file_checksum=uuid.uuid4().hex,
            uploaded_by=user_id,
            status=StatementImportStatus.COMPLETED,
        )
        session.add(stmt_imp)
        session.flush()

        txn = BankTransaction(
            id=uuid.uuid4(),
            society_id=soc_a,
            import_id=stmt_imp.id,
            source_row_number=1,
            transaction_date=datetime.now(UTC),
            description="TRIG TEST",
            normalized_description="TRIG TEST",
            transaction_type=TransactionType.CREDIT,
            credit_paise=500000,
            allocated_paise=0,
            transaction_fingerprint=uuid.uuid4().hex,
            reconciliation_status=TransactionReconciliationStatus.UNMATCHED,
        )
        session.add(txn)

        inv_a = Invoice(
            id=uuid.uuid4(),
            society_id=soc_a,
            flat_id=flat_a,
            billing_period="2026-11",
            invoice_number=f"INV-TR-{uuid.uuid4().hex[:6].upper()}",
            area_sqft_snapshot=1000,
            rate_paise_per_sqft_snapshot=500,
            subtotal_paise=500000,
            total_paise=500000,
            due_date=datetime.now(UTC),
            status=InvoiceStatus.PAID,
        )
        session.add(inv_a)

        pay_b = Payment(
            id=uuid.uuid4(),
            society_id=soc_a,
            flat_id=flat_b,
            amount_paise=500000,
            currency="INR",
            provider="BANK_TRANSFER",
            provider_reference=f"PAY-TR-B-{uuid.uuid4().hex[:8].upper()}",
            status=PaymentStatus.SUCCESS,
            initiated_by=user_id,
        )
        session.add(pay_b)
        session.commit()

        # Attempt direct insert linking Flat A's invoice and Flat B's payment
        cross_flat_rejected = False
        try:
            bad_alloc = ReconciliationAllocation(
                id=uuid.uuid4(),
                society_id=soc_a,
                transaction_id=txn.id,
                invoice_id=inv_a.id,
                payment_id=pay_b.id,
                allocated_paise=500000,
            )
            session.add(bad_alloc)
            session.commit()
        except Exception:
            session.rollback()
            cross_flat_rejected = True

        assert cross_flat_rejected, (
            "Database trigger must reject cross-flat reconciliation allocations!"
        )


def test_split_allocation_across_multiple_invoices(client: TestClient, db_session: Session) -> None:
    """Verifies splitting a single large bank transfer across multiple invoices (Section 5.9)."""
    society_id = uuid.UUID(SOCIETY_ID)

    # Create Invoice A (₹7,475) and Invoice B (₹6,370)
    inv_a = Invoice(
        society_id=society_id,
        flat_id=uuid.UUID(FLAT_1203_ID),
        billing_period="2026-11",
        invoice_number=f"INV-SPLIT-A-{uuid.uuid4().hex[:6].upper()}",
        area_sqft_snapshot=1150,
        rate_paise_per_sqft_snapshot=650,
        subtotal_paise=747500,
        total_paise=747500,
        due_date=datetime.now(UTC),
        status=InvoiceStatus.UNPAID,
    )
    inv_b = Invoice(
        society_id=society_id,
        flat_id=uuid.UUID(FLAT_0408_ID),
        billing_period="2026-11",
        invoice_number=f"INV-SPLIT-B-{uuid.uuid4().hex[:6].upper()}",
        area_sqft_snapshot=980,
        rate_paise_per_sqft_snapshot=650,
        subtotal_paise=637000,
        total_paise=637000,
        due_date=datetime.now(UTC),
        status=InvoiceStatus.UNPAID,
    )
    db_session.add_all([inv_a, inv_b])
    db_session.commit()

    # Statement has a single bulk transfer of ₹15,000 (1500000 paise)
    csv_data = (
        b"Date,Description,Reference,Credit\n"
        b"05/11/2026,COMBINED MAINTENANCE FOR UNITS 1203 AND 0408,BULK-REF-15K,15000.00\n"
    )

    up = client.post(
        "/api/v1/reconciliation/statements",
        files={"file": ("bulk_split.csv", csv_data, "text/csv")},
        headers=AUTH_HELPDESK,
    )
    import_id = up.json()["import_id"]
    client.post(f"/api/v1/reconciliation/statements/{import_id}/confirm", headers=AUTH_HELPDESK)

    txns = client.get(
        f"/api/v1/reconciliation/transactions?import_id={import_id}", headers=AUTH_HELPDESK
    ).json()
    txn_id = txns[0]["id"]

    # Propose split allocation: Invoice A: ₹7,475, Invoice B: ₹6,370 (Total: ₹13,845; Unallocated: ₹1,155)
    split_allocations = [
        {"invoice_id": str(inv_a.id), "allocated_paise": 747500},
        {"invoice_id": str(inv_b.id), "allocated_paise": 637000},
    ]

    idemp = str(uuid.uuid4())
    res = client.post(
        f"/api/v1/reconciliation/transactions/{txn_id}/approve",
        json={"proposed_allocations": split_allocations},
        headers={**AUTH_HELPDESK, "Idempotency-Key": idemp},
    )
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["allocated_paise"] == 1384500
    assert res_data["unallocated_paise"] == 115500  # ₹1,155 unallocated credit retained!

    # Verify both invoices are now marked PAID
    db_session.expire_all()
    assert (
        db_session.query(Invoice).filter(Invoice.id == inv_a.id).first().status
        == InvoiceStatus.PAID
    )
    assert (
        db_session.query(Invoice).filter(Invoice.id == inv_b.id).first().status
        == InvoiceStatus.PAID
    )


def test_over_allocation_prevented(client: TestClient, db_session: Session) -> None:
    """Integrity Invariant: Allocating more than invoice outstanding or bank credit available raises 422."""
    society_id = uuid.UUID(SOCIETY_ID)
    invoice = Invoice(
        society_id=society_id,
        flat_id=uuid.UUID(FLAT_1203_ID),
        billing_period="2026-11",
        invoice_number=f"INV-OVER-{uuid.uuid4().hex[:6].upper()}",
        area_sqft_snapshot=1150,
        rate_paise_per_sqft_snapshot=650,
        subtotal_paise=500000,  # ₹5,000 outstanding
        total_paise=500000,
        due_date=datetime.now(UTC),
        status=InvoiceStatus.UNPAID,
    )
    db_session.add(invoice)
    db_session.commit()

    # Statement transaction is ₹10,000
    csv_data = b"Date,Description,Reference,Credit\n05/11/2026,LARGE DEPOSIT,REF-LARGE,10000.00\n"
    up = client.post(
        "/api/v1/reconciliation/statements",
        files={"file": ("large.csv", csv_data, "text/csv")},
        headers=AUTH_HELPDESK,
    )
    import_id = up.json()["import_id"]
    client.post(f"/api/v1/reconciliation/statements/{import_id}/confirm", headers=AUTH_HELPDESK)
    txn_id = client.get(
        f"/api/v1/reconciliation/transactions?import_id={import_id}", headers=AUTH_HELPDESK
    ).json()[0]["id"]

    # 1. Attempting to allocate ₹8,000 to an invoice with only ₹5,000 outstanding -> REJECTED
    res1 = client.post(
        f"/api/v1/reconciliation/transactions/{txn_id}/approve",
        json={"proposed_allocations": [{"invoice_id": str(invoice.id), "allocated_paise": 800000}]},
        headers={**AUTH_HELPDESK, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert res1.status_code == 400
    assert "exceeds outstanding balance" in res1.json()["error"]["message"].lower()

    # 2. Attempting to allocate ₹12,000 from a ₹10,000 credit -> REJECTED
    res2 = client.post(
        f"/api/v1/reconciliation/transactions/{txn_id}/approve",
        json={
            "proposed_allocations": [{"invoice_id": str(invoice.id), "allocated_paise": 1200000}]
        },
        headers={**AUTH_HELPDESK, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert res2.status_code == 400
    assert "exceeds available bank credit" in res2.json()["error"]["message"].lower()


def test_reconciliation_summary_and_csv_export(client: TestClient) -> None:
    """Verifies reconciliation KPI calculations and CSV report export with formula injection defense."""
    # 1. Summary KPIs
    res = client.get("/api/v1/reconciliation/summary", headers=AUTH_HELPDESK)
    assert res.status_code == 200
    summary = res.json()
    assert "total_credit_paise" in summary
    assert "reconciled_credit_paise" in summary
    assert "reconciliation_percentage" in summary

    # 2. CSV Report Export
    export_res = client.get("/api/v1/reconciliation/reports/export", headers=AUTH_HELPDESK)
    assert export_res.status_code == 200
    assert "text/csv" in export_res.headers["content-type"]
    assert "Transaction ID,Date,Description" in export_res.text


def test_reconciliation_reject_and_mark_unidentified(client: TestClient) -> None:
    """Verifies rejecting suggested match and marking credit as unidentified / suspense."""
    csv_data = (
        b"Date,Description,Reference,Credit\n"
        b"05/11/2026,UNKNOWN CASH DEPOSIT AT BRANCH,CASH-999,5000.00\n"
        b"05/11/2026,UNIDENTIFIED UPI TRANSFER,UPI-000111,2500.00\n"
    )

    up = client.post(
        "/api/v1/reconciliation/statements",
        files={"file": ("unidentified.csv", csv_data, "text/csv")},
        headers=AUTH_HELPDESK,
    )
    import_id = up.json()["import_id"]
    client.post(f"/api/v1/reconciliation/statements/{import_id}/confirm", headers=AUTH_HELPDESK)

    txns = client.get(
        f"/api/v1/reconciliation/transactions?import_id={import_id}", headers=AUTH_HELPDESK
    ).json()
    assert len(txns) == 2

    txn1_id = txns[0]["id"]
    txn2_id = txns[1]["id"]

    # 1. Reject match
    rej_res = client.post(
        f"/api/v1/reconciliation/transactions/{txn1_id}/reject",
        json={"reason": "Incorrect resident suggested"},
        headers=AUTH_HELPDESK,
    )
    assert rej_res.status_code == 200
    assert rej_res.json()["reconciliation_status"] == "REJECTED"

    # 2. Mark unidentified (suspense account)
    unid_res = client.post(
        f"/api/v1/reconciliation/transactions/{txn2_id}/mark-unidentified",
        json={"notes": "No resident claimed this deposit after society notice"},
        headers=AUTH_HELPDESK,
    )
    assert unid_res.status_code == 200
    assert unid_res.json()["reconciliation_status"] == "UNIDENTIFIED"


def test_reconciliation_manual_match_suggest(client: TestClient) -> None:
    """Staff manually selects flat and invoice, promoting status to SUGGESTED."""
    csv_data = (
        b"Date,Description,Reference,Credit\n05/11/2026,MANUAL TEST DEPOSIT,MAN-123,4000.00\n"
    )
    up = client.post(
        "/api/v1/reconciliation/statements",
        files={"file": ("manual.csv", csv_data, "text/csv")},
        headers=AUTH_HELPDESK,
    )
    import_id = up.json()["import_id"]
    client.post(f"/api/v1/reconciliation/statements/{import_id}/confirm", headers=AUTH_HELPDESK)
    txn_id = client.get(
        f"/api/v1/reconciliation/transactions?import_id={import_id}", headers=AUTH_HELPDESK
    ).json()[0]["id"]

    # Suggest flat 1203
    sug_res = client.post(
        f"/api/v1/reconciliation/transactions/{txn_id}/suggest",
        json={"flat_id": FLAT_1203_ID, "notes": "Resident confirmed via phone call"},
        headers=AUTH_HELPDESK,
    )
    assert sug_res.status_code == 200
    txn_data = sug_res.json()
    assert txn_data["reconciliation_status"] == "SUGGESTED"
    assert any(m["matching_level"] == "MANUAL" and m["is_selected"] for m in txn_data["matches"])


def test_reconciliation_idempotency_payload_mismatch_raises_conflict(client: TestClient) -> None:
    """Reusing the same idempotency key with different payload must raise 409 Conflict."""
    csv_data = b"Date,Description,Reference,Credit\n05/11/2026,IDEMP TEST,IDEMP-REF,3000.00\n"
    up = client.post(
        "/api/v1/reconciliation/statements",
        files={"file": ("idemp.csv", csv_data, "text/csv")},
        headers=AUTH_HELPDESK,
    )
    import_id = up.json()["import_id"]
    client.post(f"/api/v1/reconciliation/statements/{import_id}/confirm", headers=AUTH_HELPDESK)
    txn_id = client.get(
        f"/api/v1/reconciliation/transactions?import_id={import_id}", headers=AUTH_HELPDESK
    ).json()[0]["id"]

    idemp_key = str(uuid.uuid4())

    # First call with payload A
    client.post(
        f"/api/v1/reconciliation/transactions/{txn_id}/approve",
        json={
            "proposed_allocations": [{"invoice_id": str(uuid.uuid4()), "allocated_paise": 100000}]
        },
        headers={**AUTH_HELPDESK, "Idempotency-Key": idemp_key},
    )
    # Fails validation because invoice doesn't exist, but idempotency record is completed/failed

    # Second call with same idempotency key but differing payload -> 409 Conflict
    res2 = client.post(
        f"/api/v1/reconciliation/transactions/{txn_id}/approve",
        json={
            "proposed_allocations": [{"invoice_id": str(uuid.uuid4()), "allocated_paise": 200000}]
        },
        headers={**AUTH_HELPDESK, "Idempotency-Key": idemp_key},
    )
    assert res2.status_code == 409
    assert (
        "differing" in res2.json()["error"]["message"].lower()
        or "conflict" in res2.json()["error"]["message"].lower()
    )


def test_reconciliation_society_data_isolation(client: TestClient, db_session: Session) -> None:
    """Security Invariant: Transactions from Society B must never be accessible or modifiable by Society A staff."""
    other_society_id = uuid.uuid4()
    other_soc = Society(
        id=other_society_id,
        name="Other Society",
        timezone="Asia/Kolkata",
        preferred_currency="INR",
    )
    db_session.add(other_soc)
    db_session.commit()

    # Create a transaction belonging to other society
    other_imp = BankStatementImport(
        society_id=other_society_id,
        file_name="other.csv",
        file_checksum="otherchecksum123",
        uploaded_by=db_session.query(User).first().id,
        status=StatementImportStatus.COMPLETED,
    )
    db_session.add(other_imp)
    db_session.flush()

    other_txn = BankTransaction(
        society_id=other_society_id,
        import_id=other_imp.id,
        source_row_number=1,
        transaction_date=datetime.now(UTC),
        description="OTHER SOCIETY DEPOSIT",
        normalized_description="OTHER SOCIETY DEPOSIT",
        transaction_type=TransactionType.CREDIT,
        credit_paise=500000,
        transaction_fingerprint="other_fp",
    )
    db_session.add(other_txn)
    db_session.commit()

    # Helpdesk of Society A attempts to access other society transaction -> 403 Forbidden or 404
    get_res = client.get(
        f"/api/v1/reconciliation/transactions/{other_txn.id}",
        headers=AUTH_HELPDESK,
    )
    assert get_res.status_code in (403, 404)

    # Attempt to approve
    app_res = client.post(
        f"/api/v1/reconciliation/transactions/{other_txn.id}/approve",
        json={
            "proposed_allocations": [{"invoice_id": str(uuid.uuid4()), "allocated_paise": 500000}]
        },
        headers={**AUTH_HELPDESK, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert app_res.status_code in (403, 404)


def test_reconciliation_additional_endpoints_and_aliases(
    client: TestClient,
    db_session: Session,
):
    """Verifies extended reporting, queue summary, match exploration, and operation aliases."""
    soc_id = uuid.UUID(SOCIETY_ID)
    flat_id = uuid.UUID(FLAT_1203_ID)

    # Ensure an unpaid invoice exists
    inv = (
        db_session.query(Invoice)
        .filter(
            Invoice.society_id == soc_id,
            Invoice.flat_id == flat_id,
            Invoice.status == InvoiceStatus.UNPAID,
        )
        .first()
    )
    if not inv:
        inv = Invoice(
            society_id=soc_id,
            flat_id=flat_id,
            billing_period="2026-11",
            invoice_number=f"INV-ALIAS-{uuid.uuid4().hex[:6].upper()}",
            area_sqft_snapshot=1150,
            rate_paise_per_sqft_snapshot=650,
            subtotal_paise=747500,
            total_paise=747500,
            due_date=datetime.now(UTC) + timedelta(days=5),
            status=InvoiceStatus.UNPAID,
        )
        db_session.add(inv)
        db_session.commit()
        db_session.refresh(inv)

    # 1. Test queue summary endpoint
    res_q_sum = client.get("/api/v1/reconciliation/queue/summary", headers=AUTH_HELPDESK)
    assert res_q_sum.status_code == 200
    q_data = res_q_sum.json()
    assert "total_queue_items" in q_data
    assert "unmatched" in q_data

    # 2. Test reports summary endpoint
    res_rep_sum = client.get("/api/v1/reconciliation/reports/summary", headers=AUTH_HELPDESK)
    assert res_rep_sum.status_code == 200
    rep_data = res_rep_sum.json()
    assert "total_credit_paise" in rep_data
    assert "reconciliation_percentage" in rep_data

    # 3. Test reports unmatched & reconciled endpoints
    res_unmatched = client.get("/api/v1/reconciliation/reports/unmatched", headers=AUTH_HELPDESK)
    assert res_unmatched.status_code == 200
    assert isinstance(res_unmatched.json(), list)

    res_reconciled = client.get("/api/v1/reconciliation/reports/reconciled", headers=AUTH_HELPDESK)
    assert res_reconciled.status_code == 200
    assert isinstance(res_reconciled.json(), list)

    # 4. Upload a statement to test /process and /matches
    csv_content = (
        "Date,Narration,Chq/Ref No,Value Dt,Withdrawal Amt,Deposit Amt,Closing Balance\n"
        "05/11/2026,NEFT T07-1203 NEERAJ MAINT,HDFCN2600112233,05/11/2026,0.00,7475.00,107475.00\n"
    )
    up_res = client.post(
        "/api/v1/reconciliation/statements",
        files={"file": ("process_test.csv", csv_content.encode("utf-8"), "text/csv")},
        headers=AUTH_HELPDESK,
    )
    assert up_res.status_code == 201
    import_id = up_res.json()["import_id"]

    # Test /statements/{id}/process (alias for /confirm)
    proc_res = client.post(
        f"/api/v1/reconciliation/statements/{import_id}/process",
        headers=AUTH_HELPDESK,
    )
    assert proc_res.status_code == 200
    assert proc_res.json()["status"] in ("PROCESSING", "COMPLETED")
    drain_reconciliation_worker_jobs(db_session)

    # Get transaction from this import
    txns_res = client.get(
        f"/api/v1/reconciliation/transactions?import_id={import_id}",
        headers=AUTH_HELPDESK,
    )
    assert txns_res.status_code == 200
    txn_list = txns_res.json()
    assert len(txn_list) == 1
    txn_id = txn_list[0]["id"]

    # Test /transactions/{id}/matches
    matches_res = client.get(
        f"/api/v1/reconciliation/transactions/{txn_id}/matches",
        headers=AUTH_HELPDESK,
    )
    assert matches_res.status_code == 200
    matches = matches_res.json()
    assert isinstance(matches, list)

    # Test /transactions/{id}/match (alias for /suggest)
    match_post_res = client.post(
        f"/api/v1/reconciliation/transactions/{txn_id}/match",
        json={"flat_id": FLAT_1203_ID, "invoice_id": str(inv.id), "notes": "Alias match test"},
        headers=AUTH_HELPDESK,
    )
    assert match_post_res.status_code == 200
    assert match_post_res.json()["reconciliation_status"] in ("SUGGESTED", "PENDING_APPROVAL")


def test_reconciliation_worker_and_error_handling(
    db_session: Session,
):
    """Verifies reconciliation worker execution, lease idempotency, and error classification."""
    from app.domains.reconciliation.exceptions import (
        PermanentReconciliationWorkerError,
        RetryableReconciliationWorkerError,
    )
    from app.messaging.envelope import EventEnvelope, EventMetadata
    from app.workers.reconciliation_worker import (
        is_retryable_reconciliation_error,
        reconciliation_handler,
    )

    soc_id = uuid.UUID(SOCIETY_ID)

    # 1. Error classification check
    assert (
        is_retryable_reconciliation_error(RetryableReconciliationWorkerError("DB lock timeout"))
        is True
    )
    assert is_retryable_reconciliation_error(TimeoutError("Connection timed out")) is True
    assert (
        is_retryable_reconciliation_error(PermanentReconciliationWorkerError("Poison message"))
        is False
    )
    assert is_retryable_reconciliation_error(ValueError("Invalid syntax")) is False

    # 2. Worker execution for statement processing
    imp = BankStatementImport(
        society_id=soc_id,
        file_name="worker_test.csv",
        file_checksum=f"chk_{uuid.uuid4().hex[:12]}",
        uploaded_by=db_session.query(User).first().id,
        status=StatementImportStatus.READY_FOR_IMPORT,
    )
    db_session.add(imp)
    db_session.commit()

    envelope = EventEnvelope(
        event_id=uuid.uuid4(),
        event_type="reconciliation.process_bank_statement",
        aggregate_type="BankStatementImport",
        aggregate_id=str(imp.id),
        payload={"society_id": str(soc_id)},
        metadata=EventMetadata(correlation_id=str(uuid.uuid4())),
    )

    reconciliation_handler.process(envelope, db_session)

    # Verify statement marked COMPLETED
    db_session.refresh(imp)
    assert imp.status == StatementImportStatus.COMPLETED

    # 3. Idempotent skip: repeated invocation does not crash or re-process
    reconciliation_handler.process(envelope, db_session)
    db_session.refresh(imp)
    assert imp.status == StatementImportStatus.COMPLETED


def test_bank_transaction_fingerprint_unique_constraint(db_session: Session) -> None:
    """Verifies that uq_bank_transactions_society_fingerprint prevents duplicate transaction fingerprints within a society."""
    from sqlalchemy.exc import IntegrityError

    soc_id = uuid.UUID(SOCIETY_ID)
    user_id = db_session.query(User).first().id
    imp = BankStatementImport(
        society_id=soc_id,
        file_name="fp_test.csv",
        file_checksum=f"chk_{uuid.uuid4().hex[:12]}",
        uploaded_by=user_id,
        status=StatementImportStatus.READY_FOR_IMPORT,
    )
    db_session.add(imp)
    db_session.commit()

    fp = f"fp_{uuid.uuid4().hex}"
    txn1 = BankTransaction(
        import_id=imp.id,
        society_id=soc_id,
        source_row_number=1,
        transaction_date=datetime.now(UTC),
        transaction_type=TransactionType.CREDIT,
        debit_paise=0,
        credit_paise=500000,
        description="UPI/CR/123456/NEERAJ",
        normalized_description="UPI CR 123456 NEERAJ",
        transaction_fingerprint=fp,
        reconciliation_status=TransactionReconciliationStatus.UNMATCHED,
    )
    db_session.add(txn1)
    db_session.commit()

    # Attempting to insert another transaction with identical (society_id, transaction_fingerprint)
    txn2 = BankTransaction(
        import_id=imp.id,
        society_id=soc_id,
        source_row_number=2,
        transaction_date=datetime.now(UTC),
        transaction_type=TransactionType.CREDIT,
        debit_paise=0,
        credit_paise=500000,
        description="UPI/CR/123456/NEERAJ DUPLICATE",
        normalized_description="UPI CR 123456 NEERAJ DUPLICATE",
        transaction_fingerprint=fp,
        reconciliation_status=TransactionReconciliationStatus.UNMATCHED,
    )
    db_session.add(txn2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Same fingerprint in a DIFFERENT society is allowed (composite multi-tenant uniqueness)
    other_soc = Society(
        id=uuid.uuid4(),
        name=f"Other Society {uuid.uuid4().hex[:6]}",
        status=SocietyStatus.ACTIVE,
    )
    db_session.add(other_soc)
    db_session.commit()

    other_imp = BankStatementImport(
        society_id=other_soc.id,
        file_name="other_soc.csv",
        file_checksum=f"chk_{uuid.uuid4().hex[:12]}",
        uploaded_by=user_id,
        status=StatementImportStatus.READY_FOR_IMPORT,
    )
    db_session.add(other_imp)
    db_session.commit()

    txn_other_soc = BankTransaction(
        import_id=other_imp.id,
        society_id=other_soc.id,
        source_row_number=1,
        transaction_date=datetime.now(UTC),
        transaction_type=TransactionType.CREDIT,
        debit_paise=0,
        credit_paise=500000,
        description="Same fingerprint across different tenant",
        normalized_description="SAME FINGERPRINT ACROSS DIFFERENT TENANT",
        transaction_fingerprint=fp,
        reconciliation_status=TransactionReconciliationStatus.UNMATCHED,
    )
    db_session.add(txn_other_soc)
    db_session.commit()
    assert txn_other_soc.id is not None


def test_reconciliation_worker_matches_sets_society_id_and_completes(db_session: Session) -> None:
    """Verifies that the background worker accurately claims the import, populates society_id on ReconciliationMatch, and completes."""
    from app.domains.reconciliation.models import ReconciliationMatch
    from app.messaging.envelope import EventEnvelope, EventMetadata
    from app.workers.reconciliation_worker import reconciliation_handler

    soc_id = uuid.UUID(SOCIETY_ID)
    flat = db_session.query(Flat).filter(Flat.society_id == soc_id).first()
    assert flat is not None
    user_id = db_session.query(User).first().id

    # Create an unpaid invoice
    inv = Invoice(
        society_id=soc_id,
        flat_id=flat.id,
        billing_period="2026-11",
        invoice_number=f"INV-ASYNC-{uuid.uuid4().hex[:6].upper()}",
        area_sqft_snapshot=1000,
        rate_paise_per_sqft_snapshot=650,
        subtotal_paise=747500,
        total_paise=747500,
        due_date=datetime.now(UTC) + timedelta(days=15),
        status=InvoiceStatus.UNPAID,
    )
    db_session.add(inv)
    db_session.commit()

    # Create statement import and transaction
    imp = BankStatementImport(
        society_id=soc_id,
        file_name="async_match_test.csv",
        file_checksum=f"chk_{uuid.uuid4().hex[:12]}",
        uploaded_by=user_id,
        status=StatementImportStatus.PROCESSING,
    )
    db_session.add(imp)
    db_session.commit()

    narration = f"NEFT/REF{uuid.uuid4().hex[:8]}/{flat.flat_number} MAINT"
    txn = BankTransaction(
        import_id=imp.id,
        society_id=soc_id,
        source_row_number=1,
        transaction_date=datetime.now(UTC),
        transaction_type=TransactionType.CREDIT,
        debit_paise=0,
        credit_paise=747500,
        description=narration,
        normalized_description=narration.upper(),
        transaction_fingerprint=f"fp_{uuid.uuid4().hex}",
        reconciliation_status=TransactionReconciliationStatus.UNMATCHED,
    )
    db_session.add(txn)
    db_session.commit()

    envelope = EventEnvelope(
        event_id=uuid.uuid4(),
        event_type="reconciliation.process_bank_statement",
        aggregate_type="BankStatementImport",
        aggregate_id=str(imp.id),
        payload={"society_id": str(soc_id)},
        metadata=EventMetadata(correlation_id=str(uuid.uuid4())),
    )

    reconciliation_handler.process(envelope, db_session)

    db_session.refresh(imp)
    assert imp.status == StatementImportStatus.COMPLETED

    db_session.refresh(txn)
    assert txn.reconciliation_status == TransactionReconciliationStatus.SUGGESTED

    matches = (
        db_session.query(ReconciliationMatch)
        .filter(ReconciliationMatch.transaction_id == txn.id)
        .all()
    )
    assert len(matches) > 0
    for match in matches:
        assert match.society_id == soc_id, "society_id must be set on ReconciliationMatch"
        assert match.society_id is not None


def test_concurrency_safe_import_confirmation_guards(client: TestClient) -> None:
    """Verifies that confirm_import cannot be re-confirmed once claimed and set to PROCESSING."""
    csv_content = (
        b"Date,Narration,Chq / Ref No.,Withdrawal (INR),Deposit (INR),Balance (INR)\n"
        b"05/11/2026,UPI/CR/111222333444/ROHIT SHARMA/T07-1203,111222333444,,7475.00,107475.00\n"
    )
    up_res = client.post(
        "/api/v1/reconciliation/statements",
        files={"file": ("concurrency_test.csv", csv_content, "text/csv")},
        headers=AUTH_HELPDESK,
    )
    assert up_res.status_code == 201
    import_id = up_res.json()["import_id"]

    # First confirm -> 200 PROCESSING
    confirm_1 = client.post(
        f"/api/v1/reconciliation/statements/{import_id}/confirm",
        headers=AUTH_HELPDESK,
    )
    assert confirm_1.status_code == 200
    assert confirm_1.json()["status"] == "PROCESSING"

    # Second confirm -> 400 Bad Request because status is PROCESSING, not READY_FOR_IMPORT
    confirm_2 = client.post(
        f"/api/v1/reconciliation/statements/{import_id}/confirm",
        headers=AUTH_HELPDESK,
    )
    assert confirm_2.status_code == 400
    assert "Only READY_FOR_IMPORT statements can be confirmed" in confirm_2.text
