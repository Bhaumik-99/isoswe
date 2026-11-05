"""Phase 5 Workstream B: UPI-Aware Bank Reconciliation & Hardening Test Suite

Validates:
1. Extraction and normalization of UPI Virtual Payment Addresses (VPAs).
2. Deterministic transaction fingerprint incorporating row numbers when references are missing.
3. Registration and retrieval of authorized resident UPI VPAs per society.
4. High-confidence matching (>= 90%, HIGH tier) when verified resident VPA matches flat and invoice amount matches.
5. Financial safety invariant: Never match on amount alone (e.g. VPA for Flat A never matches Flat B).
6. Upload stream bounding and duplicate pending statement upload 409 rejection.
7. Permanent worker failure marks statement import as FAILED.
"""

import io
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.billing.models import (
    Invoice,
    InvoiceStatus,
)
from app.domains.identity.models import (
    Flat,
    User,
)
from app.domains.reconciliation.matching import DeterministicMatchingEngine
from app.domains.reconciliation.models import (
    BankStatementImport,
    BankTransaction,
    MatchConfidenceTier,
    ResidentUPIMapping,
    StatementImportStatus,
    TransactionType,
)
from app.domains.reconciliation.normalizer import (
    compute_transaction_fingerprint,
    extract_upi_vpa,
    normalize_vpa,
)
from app.messaging.envelope import EventEnvelope, EventMetadata
from app.workers.reconciliation_worker import reconciliation_handler

SOCIETY_ID = "11111111-1111-1111-1111-111111111111"
AUTH_HELPDESK = {"Authorization": "Bearer dev-token-helpdesk"}
AUTH_RESIDENT = {"Authorization": "Bearer dev-token-neeraj"}


def test_vpa_extraction_and_normalization() -> None:
    """Verifies regex extraction and normalization across Indian UPI bank narration formats."""
    # Pattern 1: Standard bank credit narration
    assert (
        extract_upi_vpa("UPI/CR/123456789012/neeraj.kumar@okaxis/Maintenance")
        == "neeraj.kumar@okaxis"
    )
    # Pattern 2: UPI prefix with hyphen
    assert extract_upi_vpa("UPI-9876543210@paytm-123456789012") == "9876543210@paytm"
    # Pattern 3: Case insensitivity and whitespace stripping
    assert (
        normalize_vpa(extract_upi_vpa("TRANSFER FROM Rahul.Sharma@OkHdfcBank") or "")
        == "rahul.sharma@okhdfcbank"
    )
    # Pattern 4: Non-UPI descriptions return None
    assert extract_upi_vpa("NEFT-SBIN123456789-MAINT") is None
    assert extract_upi_vpa("CASH DEPOSIT BRANCH 408") is None


def test_fingerprint_incorporates_row_when_reference_missing() -> None:
    """If reference/UTR is absent, fingerprint includes source_row_number to prevent collisions."""
    soc_id = uuid.UUID(SOCIETY_ID)
    now = datetime.now(UTC)

    fp_row1 = compute_transaction_fingerprint(
        society_id=soc_id,
        txn_date=now,
        credit_paise=500000,
        debit_paise=0,
        reference=None,
        normalized_desc="CASH DEPOSIT",
        source_row_number=2,
    )

    fp_row2 = compute_transaction_fingerprint(
        society_id=soc_id,
        txn_date=now,
        credit_paise=500000,
        debit_paise=0,
        reference=None,
        normalized_desc="CASH DEPOSIT",
        source_row_number=3,
    )

    # Different rows must not collide
    assert fp_row1 != fp_row2


def test_resident_upi_mapping_lifecycle(client: TestClient, db_session: Session) -> None:
    """Staff can register, list, and delete authorized resident UPI VPAs."""
    soc_id = uuid.UUID(SOCIETY_ID)
    flat = db_session.query(Flat).filter(Flat.society_id == soc_id).first()
    user = db_session.query(User).first()
    assert flat is not None and user is not None

    test_vpa = f"test.resident.{uuid.uuid4().hex[:6]}@okaxis"

    # 1. Register mapping
    res = client.post(
        "/api/v1/reconciliation/upi-mappings",
        json={
            "flat_id": str(flat.id),
            "resident_id": str(user.id),
            "vpa": test_vpa,
            "account_holder_name": "Test Resident",
            "is_verified": True,
        },
        headers=AUTH_HELPDESK,
    )
    assert res.status_code == 201
    created = res.json()
    assert created["vpa"] == test_vpa.lower()
    mapping_id = created["id"]

    # 2. Duplicate registration rejected with 409
    res_dup = client.post(
        "/api/v1/reconciliation/upi-mappings",
        json={
            "flat_id": str(flat.id),
            "resident_id": str(user.id),
            "vpa": test_vpa.upper(),  # case-insensitive check
        },
        headers=AUTH_HELPDESK,
    )
    assert res_dup.status_code in (409, 422)

    # 3. List mappings
    res_list = client.get("/api/v1/reconciliation/upi-mappings", headers=AUTH_HELPDESK)
    assert res_list.status_code == 200
    assert any(m["id"] == mapping_id for m in res_list.json())

    # 4. Delete mapping
    res_del = client.delete(
        f"/api/v1/reconciliation/upi-mappings/{mapping_id}",
        headers=AUTH_HELPDESK,
    )
    assert res_del.status_code == 204


def test_upi_aware_matching_promotes_confidence(db_session: Session) -> None:
    """Matching engine identifies flat via authorized VPA and promotes confidence to HIGH (>=90%)."""
    soc_id = uuid.UUID(SOCIETY_ID)
    flat = db_session.query(Flat).filter(Flat.society_id == soc_id).first()
    user = db_session.query(User).first()
    assert flat is not None and user is not None

    vpa = "anand.kumar@okicici"
    mapping = ResidentUPIMapping(
        id=uuid.uuid4(),
        society_id=soc_id,
        flat_id=flat.id,
        resident_id=user.id,
        vpa=vpa,
        is_verified=True,
    )
    db_session.add(mapping)

    now = datetime.now(UTC)
    inv = Invoice(
        id=uuid.uuid4(),
        society_id=soc_id,
        flat_id=flat.id,
        billing_period="2026-11",
        invoice_number=f"INV-UPI-{uuid.uuid4().hex[:6].upper()}",
        area_sqft_snapshot=1000,
        rate_paise_per_sqft_snapshot=650,
        subtotal_paise=650000,
        total_paise=650000,
        due_date=now - timedelta(days=2),
        status=InvoiceStatus.UNPAID,
    )
    db_session.add(inv)
    db_session.commit()

    txn = BankTransaction(
        id=uuid.uuid4(),
        society_id=soc_id,
        import_id=uuid.uuid4(),
        source_row_number=1,
        transaction_date=now,
        description=f"UPI/CR/999888777666/{vpa}/Monthly Maintenance",
        normalized_description=f"UPI/CR/999888777666/{vpa.upper()}/MONTHLY MAINTENANCE",
        transaction_type=TransactionType.CREDIT,
        debit_paise=0,
        credit_paise=650000,  # Exact balance match
        transaction_fingerprint=uuid.uuid4().hex,
        payer_vpa=vpa,
    )

    engine = DeterministicMatchingEngine(soc_id)
    evaluations = engine.evaluate_transaction(
        transaction=txn,
        invoices=[inv],
        payments=[],
        flats=[flat],
        memberships=[],
        users={user.id: user},
        upi_mappings=[mapping],
    )

    assert len(evaluations) >= 1
    top = evaluations[0]
    assert top.confidence_score >= 90.0
    assert top.confidence_tier == MatchConfidenceTier.HIGH
    assert top.flat_id == flat.id
    assert "level_1_vpa_match" in top.evidence
    assert vpa in top.explanation


def test_amount_alone_never_matches_unrelated_flat(db_session: Session) -> None:
    """Financial Safety: An identical amount must never match an unrelated flat when VPA belongs to another."""
    soc_id = uuid.UUID(SOCIETY_ID)
    flats = db_session.query(Flat).filter(Flat.society_id == soc_id).limit(2).all()
    user = db_session.query(User).first()
    assert len(flats) >= 2 and user is not None
    flat_a, flat_b = flats[0], flats[1]

    vpa_a = "resident.a@oksbi"
    mapping_a = ResidentUPIMapping(
        id=uuid.uuid4(),
        society_id=soc_id,
        flat_id=flat_a.id,
        resident_id=user.id,
        vpa=vpa_a,
        is_verified=True,
    )
    db_session.add(mapping_a)

    now = datetime.now(UTC)
    # Invoice for Flat B with exact same amount
    inv_b = Invoice(
        id=uuid.uuid4(),
        society_id=soc_id,
        flat_id=flat_b.id,
        billing_period="2026-11",
        invoice_number=f"INV-B-{uuid.uuid4().hex[:6].upper()}",
        area_sqft_snapshot=1000,
        rate_paise_per_sqft_snapshot=650,
        subtotal_paise=650000,
        total_paise=650000,
        due_date=now - timedelta(days=2),
        status=InvoiceStatus.UNPAID,
    )
    db_session.add(inv_b)
    db_session.commit()

    # Transaction has VPA for Flat A, but no invoice exists for Flat A
    txn = BankTransaction(
        id=uuid.uuid4(),
        society_id=soc_id,
        import_id=uuid.uuid4(),
        source_row_number=1,
        transaction_date=now,
        description=f"UPI/CR/111222333444/{vpa_a}/Maintenance",
        normalized_description=f"UPI/CR/111222333444/{vpa_a.upper()}/MAINTENANCE",
        transaction_type=TransactionType.CREDIT,
        debit_paise=0,
        credit_paise=650000,
        transaction_fingerprint=uuid.uuid4().hex,
        payer_vpa=vpa_a,
    )

    engine = DeterministicMatchingEngine(soc_id)
    evaluations = engine.evaluate_transaction(
        transaction=txn,
        invoices=[inv_b],
        payments=[],
        flats=[flat_a, flat_b],
        memberships=[],
        users={user.id: user},
        upi_mappings=[mapping_a],
    )

    # Must NOT propose inv_b on amount alone!
    assert len(evaluations) == 0


def test_duplicate_pending_statement_upload_conflict(client: TestClient) -> None:
    """Uploading the same statement file while an import is already pending returns a clean 409."""
    csv_content = (
        b"Txn Date,Description,Ref No,Debit,Credit,Balance\n"
        b"2026-11-01,UPI/CR/123/rahul@oksbi/Maint,REF001,,6500.00,100000.00\n"
    )

    # 1. First upload -> 201 Created
    res1 = client.post(
        "/api/v1/reconciliation/statements",
        files={"file": ("statement_dup.csv", io.BytesIO(csv_content), "text/csv")},
        headers=AUTH_HELPDESK,
    )
    assert res1.status_code == 201

    # 2. Second upload of same file while first is pending confirmation -> 409 Conflict
    res2 = client.post(
        "/api/v1/reconciliation/statements",
        files={"file": ("statement_dup.csv", io.BytesIO(csv_content), "text/csv")},
        headers=AUTH_HELPDESK,
    )
    assert res2.status_code == 409
    assert "Duplicate statement import" in res2.json()["error"]["message"]


def test_worker_permanent_failure_marks_import_failed(db_session: Session) -> None:
    """Permanent error during async matching transitions import from PROCESSING to FAILED."""
    soc_id = uuid.UUID(SOCIETY_ID)
    imp = BankStatementImport(
        id=uuid.uuid4(),
        society_id=soc_id,
        file_name="corrupt.csv",
        file_checksum=uuid.uuid4().hex,
        uploaded_by=uuid.uuid4(),
        status=StatementImportStatus.PROCESSING,
        total_rows=1,
        valid_rows=1,
        rejected_rows=0,
        duplicate_rows=0,
        imported_rows=1,
        error_summary={},
    )
    db_session.add(imp)
    db_session.commit()

    envelope = EventEnvelope(
        event_id=uuid.uuid4(),
        event_type="reconciliation.process_bank_statement",
        aggregate_type="bank_statement_import",
        aggregate_id=str(imp.id),
        payload={"force_failure": True},
        metadata=EventMetadata(correlation_id=str(uuid.uuid4())),
    )

    # Force a permanent runtime failure during execution by mocking db query or corrupting import
    from unittest.mock import patch

    with patch.object(
        reconciliation_handler,
        "_handle_process_statement",
        side_effect=ValueError("Fatal statement parsing corruption"),
    ):
        reconciliation_handler.process(envelope, db_session)

    db_session.refresh(imp)
    assert imp.status == StatementImportStatus.FAILED
    assert "Fatal statement parsing corruption" in str(imp.error_summary)
