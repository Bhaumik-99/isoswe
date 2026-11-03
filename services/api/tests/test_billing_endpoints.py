"""Integration tests for Phase 2 Maintenance Billing & Payment Endpoints."""

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, ValidationError
from app.domains.billing.models import (
    FinancialLedgerEntry,
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentAllocation,
    PaymentStatus,
)
from app.domains.billing.repository import BillingRepository
from app.domains.billing.service import BillingService
from app.domains.identity.models import Flat, FlatStatus, Society, SocietyStatus, Tower
from app.domains.reliability.models import IdempotencyKey

SOCIETY_ID = "11111111-1111-1111-1111-111111111111"
FLAT_1203_ID = "33333333-3333-3333-3333-333333331203"
FLAT_0408_ID = "33333333-3333-3333-3333-333333330408"
FLAT_1601_ID = "33333333-3333-3333-3333-333333331601"

AUTH_HELPDESK = {"Authorization": "Bearer dev-token-helpdesk"}
AUTH_NEERAJ = {"Authorization": "Bearer dev-token-neeraj"}
AUTH_SWATI = {"Authorization": "Bearer dev-token-swati"}
AUTH_AAMIR = {"Authorization": "Bearer dev-token-aamir"}


def test_staff_billing_run_preview(client: TestClient) -> None:
    """Requirement 4 & 6: Staff can preview monthly billing run."""
    res = client.post(
        "/api/v1/billing/staff/runs/preview",
        headers=AUTH_HELPDESK,
        json={"billing_period": "2026-11"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["billing_period"] == "2026-11"
    assert data["rate_paise_per_sqft"] == 650
    # 3 eligible flats: 1203 (1,150 sqft), 0408 (980 sqft), 1601 (1,640 sqft)
    assert data["eligible_flats_count"] == 3
    # Expected charges: (1150 + 980 + 1640) * 650 = 3770 * 650 = 2,450,500 paise (₹24,505.00)
    assert data["total_expected_charges_paise"] == 2450500


def test_staff_billing_run_execution_and_duplicate_prevention(client: TestClient) -> None:
    """Requirement 4, 6 & 8: Staff executes monthly billing run; duplicates are safely prevented."""
    # 1. Execute billing run
    res = client.post(
        "/api/v1/billing/staff/runs",
        headers=AUTH_HELPDESK,
        json={"billing_period": "2026-11"},
    )
    assert res.status_code == 201
    run_data = res.json()
    assert run_data["billing_period"] == "2026-11"
    assert run_data["total_invoiced_flats"] == 3
    assert run_data["total_charges_paise"] == 2450500
    assert run_data["status"] == "COMPLETED"

    # 2. Inspect run detail
    run_id = run_data["id"]
    get_run = client.get(f"/api/v1/billing/staff/runs/{run_id}", headers=AUTH_HELPDESK)
    assert get_run.status_code == 200
    assert get_run.json()["id"] == run_id

    # 3. Repeated billing run for same period must NOT duplicate invoices
    res_repeat = client.post(
        "/api/v1/billing/staff/runs",
        headers=AUTH_HELPDESK,
        json={"billing_period": "2026-11"},
    )
    assert res_repeat.status_code == 201
    repeat_data = res_repeat.json()
    assert repeat_data["total_invoiced_flats"] == 0
    assert repeat_data["total_skipped_flats"] == 3
    assert repeat_data["total_charges_paise"] == 0


def test_staff_billing_overview_and_invoice_search(client: TestClient) -> None:
    """Requirement 4 & 6: Staff can view society overview and filter invoices."""
    # Run billing first to generate invoices
    client.post(
        "/api/v1/billing/staff/runs",
        headers=AUTH_HELPDESK,
        json={"billing_period": "2026-11"},
    )

    # 1. Overview
    overview_res = client.get(
        "/api/v1/billing/staff/overview",
        headers=AUTH_HELPDESK,
    )
    assert overview_res.status_code == 200
    overview = overview_res.json()
    assert overview["total_billed_paise"] == 2450500
    assert overview["total_collected_paise"] == 0
    assert overview["total_outstanding_paise"] == 2450500
    assert overview["unpaid_invoices_count"] == 3

    # 2. Staff invoices list with tower filter
    inv_res = client.get(
        "/api/v1/billing/staff/invoices",
        headers=AUTH_HELPDESK,
        params={"tower_number": "T07"},
    )
    assert inv_res.status_code == 200
    items = inv_res.json()
    assert len(items) == 1
    assert items[0]["flat_number"] == "1203"
    assert items[0]["total_paise"] == 747500


def test_resident_summary_and_invoice_access(client: TestClient) -> None:
    """Requirement 4 & 7: Resident can view own summary, list own invoices, and cannot access others."""
    # Run billing
    client.post(
        "/api/v1/billing/staff/runs",
        headers=AUTH_HELPDESK,
        json={"billing_period": "2026-11"},
    )

    # 1. Neeraj's summary (Flat 1203, 1,150 sqft = ₹7,475 = 747,500 paise)
    sum_res = client.get("/api/v1/billing/me/summary", headers=AUTH_NEERAJ)
    assert sum_res.status_code == 200
    summary = sum_res.json()
    assert summary["total_outstanding_paise"] == 747500
    assert summary["unpaid_count"] == 1
    assert summary["latest_invoice"] is not None
    assert summary["latest_invoice"]["invoice_number"].startswith("INV-")

    neeraj_invoice_id = summary["latest_invoice"]["id"]

    # 2. Neeraj can access own invoice
    detail_res = client.get(f"/api/v1/billing/invoices/{neeraj_invoice_id}", headers=AUTH_NEERAJ)
    assert detail_res.status_code == 200
    invoice_detail = detail_res.json()
    assert invoice_detail["area_sqft_snapshot"] == 1150
    assert invoice_detail["rate_paise_per_sqft_snapshot"] == 650
    assert invoice_detail["total_paise"] == 747500
    assert invoice_detail["status"] == "UNPAID"
    assert len(invoice_detail["line_items"]) == 1
    assert invoice_detail["line_items"][0]["amount_paise"] == 747500

    # 3. Swati cannot access Neeraj's invoice (Authorization barrier)
    forbidden_res = client.get(f"/api/v1/billing/invoices/{neeraj_invoice_id}", headers=AUTH_SWATI)
    assert forbidden_res.status_code in (403, 404)


def test_simulated_payment_partial_and_full_lifecycle(client: TestClient) -> None:
    """Requirement 1.C, 3 & 7: Simulated payment flow with partial allocation, full allocation, and overpayment prevention."""
    # Run billing
    client.post(
        "/api/v1/billing/staff/runs",
        headers=AUTH_HELPDESK,
        json={"billing_period": "2026-11"},
    )

    # Aamir's invoice: Flat 1601, 1,640 sqft * 650 = 1,066,000 paise (₹10,660.00)
    invoices_res = client.get("/api/v1/billing/me/invoices", headers=AUTH_AAMIR)
    assert invoices_res.status_code == 200
    aamir_invoice = invoices_res.json()[0]
    invoice_id = aamir_invoice["id"]
    assert aamir_invoice["total_paise"] == 1066000

    # 1. Overpayment rejection: Attempt to pay 1,500,000 paise (> 1,066,000)
    overpay_res = client.post(
        f"/api/v1/billing/invoices/{invoice_id}/payments",
        headers={**AUTH_AAMIR, "Idempotency-Key": "idemp-overpay-001"},
        json={"amount_paise": 1500000, "simulate_failure": False},
    )
    assert overpay_res.status_code in (400, 422)
    assert "exceed" in overpay_res.json()["error"]["message"].lower()

    # 2. Simulated payment failure: Invoice status and outstanding must remain unchanged
    fail_res = client.post(
        f"/api/v1/billing/invoices/{invoice_id}/payments",
        headers={**AUTH_AAMIR, "Idempotency-Key": "idemp-fail-001"},
        json={"amount_paise": 500000, "simulate_failure": True},
    )
    assert fail_res.status_code == 200
    failed_payment = fail_res.json()
    assert failed_payment["status"] == "FAILED"

    # Verify invoice remains unchanged
    inv_after_fail = client.get(f"/api/v1/billing/invoices/{invoice_id}", headers=AUTH_AAMIR).json()
    assert inv_after_fail["paid_paise"] == 0
    assert inv_after_fail["outstanding_paise"] == 1066000
    assert inv_after_fail["status"] == "UNPAID"

    # 3. Partial payment of ₹5,000 (500,000 paise)
    partial_res = client.post(
        f"/api/v1/billing/invoices/{invoice_id}/payments",
        headers={**AUTH_AAMIR, "Idempotency-Key": "idemp-partial-001"},
        json={"amount_paise": 500000, "simulate_failure": False},
    )
    assert partial_res.status_code == 200
    partial_payment = partial_res.json()
    assert partial_payment["status"] == "SUCCESS"
    assert partial_payment["amount_paise"] == 500000
    assert len(partial_payment["allocations"]) == 1
    assert partial_payment["allocations"][0]["allocated_paise"] == 500000

    # Verify invoice status is now PARTIALLY_PAID, outstanding ₹5,660 (566,000 paise)
    inv_after_partial = client.get(
        f"/api/v1/billing/invoices/{invoice_id}", headers=AUTH_AAMIR
    ).json()
    assert inv_after_partial["paid_paise"] == 500000
    assert inv_after_partial["outstanding_paise"] == 566000
    assert inv_after_partial["status"] == "PARTIALLY_PAID"

    # 4. Idempotency test: Replay payment with same Idempotency-Key must return existing payment
    replay_res = client.post(
        f"/api/v1/billing/invoices/{invoice_id}/payments",
        headers={**AUTH_AAMIR, "Idempotency-Key": "idemp-partial-001"},
        json={"amount_paise": 500000, "simulate_failure": False},
    )
    assert replay_res.status_code == 200
    assert replay_res.json()["id"] == partial_payment["id"]

    # 5. Full payment: Pay remaining outstanding ₹5,660 (566,000 paise)
    full_res = client.post(
        f"/api/v1/billing/invoices/{invoice_id}/payments",
        headers={**AUTH_AAMIR, "Idempotency-Key": "idemp-full-001"},
        json={"amount_paise": 566000, "simulate_failure": False},
    )
    assert full_res.status_code == 200
    assert full_res.json()["status"] == "SUCCESS"

    # Verify invoice is now PAID, outstanding 0
    inv_after_full = client.get(f"/api/v1/billing/invoices/{invoice_id}", headers=AUTH_AAMIR).json()
    assert inv_after_full["paid_paise"] == 1066000
    assert inv_after_full["outstanding_paise"] == 0
    assert inv_after_full["status"] == "PAID"

    # 6. Payment receipt can be fetched
    receipt_res = client.get(f"/api/v1/billing/invoices/{invoice_id}/receipt", headers=AUTH_AAMIR)
    assert receipt_res.status_code == 200
    receipt = receipt_res.json()
    assert receipt["amount_paid_paise"] == 566000
    assert receipt["remaining_outstanding_paise"] == 0
    assert receipt["receipt_number"].startswith("RCP-")

    # 7. Resident payment history
    history_res = client.get("/api/v1/billing/me/payments", headers=AUTH_AAMIR)
    assert history_res.status_code == 200
    payments = history_res.json()
    assert len(payments) >= 2


def test_resident_cannot_execute_staff_billing_run(client: TestClient) -> None:
    """Requirement 7 & 9: Residents are strictly forbidden from staff operations."""
    res = client.post(
        "/api/v1/billing/staff/runs",
        headers=AUTH_NEERAJ,
        json={"billing_period": "2026-11"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


def test_payment_idempotency_same_key_different_payload_conflict(client: TestClient) -> None:
    """Finding 2: Same idempotency key with differing payload must return 409 Conflict."""
    client.post(
        "/api/v1/billing/staff/runs",
        headers=AUTH_HELPDESK,
        json={"billing_period": "2026-11"},
    )
    inv = client.get("/api/v1/billing/me/invoices", headers=AUTH_NEERAJ).json()[0]
    invoice_id = inv["id"]

    idemp_key = "idemp-conflict-test-key-001"
    # Call 1: ₹1,000 (100,000 paise)
    res1 = client.post(
        f"/api/v1/billing/invoices/{invoice_id}/payments",
        headers={**AUTH_NEERAJ, "Idempotency-Key": idemp_key},
        json={"amount_paise": 100000, "simulate_failure": False},
    )
    assert res1.status_code == 200

    # Call 2: Same key, different amount (₹2,000) -> 409 Conflict
    res2 = client.post(
        f"/api/v1/billing/invoices/{invoice_id}/payments",
        headers={**AUTH_NEERAJ, "Idempotency-Key": idemp_key},
        json={"amount_paise": 200000, "simulate_failure": False},
    )
    assert res2.status_code == 409
    assert "differing request payload" in res2.json()["error"]["message"].lower()


def test_payment_idempotency_failed_payment_retry(client: TestClient) -> None:
    """Finding 2: Failed payment retry with same idempotency key returns stored failed response."""
    client.post(
        "/api/v1/billing/staff/runs",
        headers=AUTH_HELPDESK,
        json={"billing_period": "2026-11"},
    )
    inv = client.get("/api/v1/billing/me/invoices", headers=AUTH_SWATI).json()[0]
    invoice_id = inv["id"]

    idemp_key = "idemp-fail-retry-key-002"
    # Call 1: Simulated failure
    res1 = client.post(
        f"/api/v1/billing/invoices/{invoice_id}/payments",
        headers={**AUTH_SWATI, "Idempotency-Key": idemp_key},
        json={"amount_paise": 100000, "simulate_failure": True},
    )
    assert res1.status_code == 200
    p1 = res1.json()
    assert p1["status"] == "FAILED"

    # Call 2: Retry with exact same key and payload -> returns stored failed response
    res2 = client.post(
        f"/api/v1/billing/invoices/{invoice_id}/payments",
        headers={**AUTH_SWATI, "Idempotency-Key": idemp_key},
        json={"amount_paise": 100000, "simulate_failure": True},
    )
    assert res2.status_code == 200
    p2 = res2.json()
    assert p2["id"] == p1["id"]
    assert p2["status"] == "FAILED"


def test_strict_billing_period_validation(client: TestClient) -> None:
    """Finding 9: Billing period strictly validated for valid YYYY-MM (month 01-12)."""
    # Invalid months
    for invalid_period in ["2026-13", "2026-00", "2026-99", "2026-1", "invalid-str"]:
        res = client.post(
            "/api/v1/billing/staff/runs/preview",
            headers=AUTH_HELPDESK,
            json={"billing_period": invalid_period},
        )
        assert res.status_code in (400, 422)

        res_exec = client.post(
            "/api/v1/billing/staff/runs",
            headers=AUTH_HELPDESK,
            json={"billing_period": invalid_period},
        )
        assert res_exec.status_code in (400, 422)


def test_due_date_calculated_in_ist_converted_to_utc(client: TestClient) -> None:
    """Finding 4 & 8: Society due date is computed in Asia/Kolkata (IST) end-of-day and converted to UTC."""
    res = client.post(
        "/api/v1/billing/staff/runs/preview",
        headers=AUTH_HELPDESK,
        json={"billing_period": "2026-11"},
    )
    assert res.status_code == 200
    preview = res.json()
    due_date_str = preview["due_date"]
    # 23:59:59 IST = 18:29:59 UTC
    # Format: YYYY-12-10T18:29:59+00:00 or similar
    assert "18:29:59" in due_date_str
    assert "2026-12-10" in due_date_str


def test_resident_cross_flat_payment_denied(client: TestClient) -> None:
    """Finding 6 & Security: Resident cannot pay or access an invoice belonging to another flat."""
    client.post(
        "/api/v1/billing/staff/runs",
        headers=AUTH_HELPDESK,
        json={"billing_period": "2026-11"},
    )
    # Swati's invoice
    swati_inv = client.get("/api/v1/billing/me/invoices", headers=AUTH_SWATI).json()[0]
    swati_invoice_id = swati_inv["id"]

    # Neeraj attempts to pay Swati's invoice -> 403 Forbidden
    res = client.post(
        f"/api/v1/billing/invoices/{swati_invoice_id}/payments",
        headers={**AUTH_NEERAJ, "Idempotency-Key": "idemp-cross-flat-hack"},
        json={"amount_paise": 100000, "simulate_failure": False},
    )
    assert res.status_code == 403
    assert "only pay invoices for your own apartment" in res.json()["error"]["message"].lower()


def test_payment_over_allocation_prevented_on_subsequent_attempts(client: TestClient) -> None:
    """Finding 1: Over-allocation is strictly rejected when previous allocation reduced outstanding balance."""
    client.post(
        "/api/v1/billing/staff/runs",
        headers=AUTH_HELPDESK,
        json={"billing_period": "2026-11"},
    )
    # Neeraj: Flat 1203, 1150 sqft * 650 = 747,500 paise (₹7,475.00)
    inv = client.get("/api/v1/billing/me/invoices", headers=AUTH_NEERAJ).json()[0]
    invoice_id = inv["id"]

    # Request 1: Pay ₹5,000 (500,000 paise) -> succeeds, remaining is ₹2,475 (247,500 paise)
    res1 = client.post(
        f"/api/v1/billing/invoices/{invoice_id}/payments",
        headers={**AUTH_NEERAJ, "Idempotency-Key": "idemp-alloc-step-1"},
        json={"amount_paise": 500000, "simulate_failure": False},
    )
    assert res1.status_code == 200

    # Request 2: Attempt another ₹5,000 (500,000 paise).
    # Since remaining outstanding is 247,500 paise, this MUST be rejected (cannot exceed outstanding)!
    res2 = client.post(
        f"/api/v1/billing/invoices/{invoice_id}/payments",
        headers={**AUTH_NEERAJ, "Idempotency-Key": "idemp-alloc-step-2"},
        json={"amount_paise": 500000, "simulate_failure": False},
    )
    assert res2.status_code in (400, 422)
    assert "cannot exceed outstanding" in res2.json()["error"]["message"].lower()


def test_payment_validation_failure_persists_in_idempotency_registry(client: TestClient) -> None:
    """P0: Validation failure response survives transaction rollback and is replayable via idempotency key."""
    client.post(
        "/api/v1/billing/staff/runs",
        headers=AUTH_HELPDESK,
        json={"billing_period": "2026-11"},
    )
    inv = client.get("/api/v1/billing/me/invoices", headers=AUTH_NEERAJ).json()[0]
    invoice_id = inv["id"]

    idemp_key = f"val-fail-test-{uuid.uuid4()}"

    # 1. First attempt with overpayment amount (₹99,999.00 > outstanding ₹7,475.00) -> 400 ValidationError
    res1 = client.post(
        f"/api/v1/billing/invoices/{invoice_id}/payments",
        headers={**AUTH_NEERAJ, "Idempotency-Key": idemp_key},
        json={"amount_paise": 9999900, "simulate_failure": False},
    )
    assert res1.status_code in (400, 422)
    err1 = res1.json()["error"]["message"]
    assert "cannot exceed outstanding" in err1.lower()

    # 2. Retry with exact same key and payload -> returns cached failure response from idempotency registry!
    res2 = client.post(
        f"/api/v1/billing/invoices/{invoice_id}/payments",
        headers={**AUTH_NEERAJ, "Idempotency-Key": idemp_key},
        json={"amount_paise": 9999900, "simulate_failure": False},
    )
    assert res2.status_code in (400, 422)
    err2 = res2.json()["error"]["message"]
    assert err1 == err2

    # 3. Same key with differing payload -> 409 Conflict
    res3 = client.post(
        f"/api/v1/billing/invoices/{invoice_id}/payments",
        headers={**AUTH_NEERAJ, "Idempotency-Key": idemp_key},
        json={"amount_paise": 500000, "simulate_failure": False},
    )
    assert res3.status_code == 409
    assert "differing request payload" in res3.json()["error"]["message"].lower()


def test_backdated_billing_period_rejected_when_rate_not_effective(client: TestClient) -> None:
    """P1: Billing run cannot retroactively apply a future-effective billing configuration."""
    # Attempt preview for historical period 2020-01 (seed billing config is effective from ~2025)
    res_preview = client.post(
        "/api/v1/billing/staff/runs/preview",
        headers=AUTH_HELPDESK,
        json={"billing_period": "2020-01"},
    )
    assert res_preview.status_code in (400, 422)
    assert (
        "no billing configuration is effective for period 2020-01"
        in res_preview.json()["error"]["message"].lower()
    )

    # Attempt execution for 2020-01 -> 422
    res_exec = client.post(
        "/api/v1/billing/staff/runs",
        headers=AUTH_HELPDESK,
        json={"billing_period": "2020-01"},
    )
    assert res_exec.status_code in (400, 422)
    assert (
        "no billing configuration is effective for period 2020-01"
        in res_exec.json()["error"]["message"].lower()
    )


def test_cross_flat_payment_allocation_rejected_at_database_level(db_session: Session) -> None:
    """P1: Database-level invariant prevents allocating Flat A's payment to Flat B's invoice."""
    soc_id = uuid.UUID(SOCIETY_ID)
    flat1_id = uuid.UUID(FLAT_1203_ID)
    flat2_id = uuid.UUID(FLAT_0408_ID)

    inv1 = Invoice(
        id=uuid.uuid4(),
        society_id=soc_id,
        flat_id=flat1_id,
        billing_period="2026-11",
        invoice_number=f"INV-TEST-F1-{uuid.uuid4().hex[:6]}",
        area_sqft_snapshot=1000,
        rate_paise_per_sqft_snapshot=650,
        subtotal_paise=650000,
        total_paise=650000,
        due_date=datetime(2026, 12, 10, 18, 29, 59, tzinfo=UTC),
        status=InvoiceStatus.UNPAID,
    )
    pay2 = Payment(
        id=uuid.uuid4(),
        society_id=soc_id,
        flat_id=flat2_id,
        amount_paise=650000,
        currency="INR",
        provider="SIMULATED",
        provider_reference=f"SIM-{uuid.uuid4().hex[:8]}",
        status=PaymentStatus.SUCCESS,
        initiated_by=uuid.uuid4(),
    )
    db_session.add_all([inv1, pay2])
    db_session.commit()

    repo = BillingRepository(db_session)
    with pytest.raises(ConflictError) as exc_info:
        repo.create_payment_allocation(
            payment_id=pay2.id,
            invoice_id=inv1.id,
            allocated_paise=650000,
        )
    assert "cross-flat" in str(exc_info.value).lower()


def test_flat_deletion_restricted_when_invoices_exist(db_session: Session) -> None:
    """P1: ON DELETE RESTRICT prevents deleting a flat with historical financial records."""
    from sqlalchemy import text

    try:
        db_session.execute(text("PRAGMA foreign_keys = ON;"))

        soc_id = uuid.UUID(SOCIETY_ID)
        flat = Flat(
            id=uuid.uuid4(),
            society_id=soc_id,
            tower_id=uuid.UUID("22222222-2222-2222-2222-222222222207"),
            flat_number=f"TEST-{uuid.uuid4().hex[:4]}",
            area_sqft=1200,
            status=FlatStatus.OCCUPIED,
        )
        db_session.add(flat)
        db_session.commit()

        inv = Invoice(
            id=uuid.uuid4(),
            society_id=soc_id,
            flat_id=flat.id,
            billing_period="2026-11",
            invoice_number=f"INV-DEL-TEST-{uuid.uuid4().hex[:6]}",
            area_sqft_snapshot=1200,
            rate_paise_per_sqft_snapshot=650,
            subtotal_paise=780000,
            total_paise=780000,
            due_date=datetime(2026, 12, 10, 18, 29, 59, tzinfo=UTC),
            status=InvoiceStatus.UNPAID,
        )
        db_session.add(inv)
        db_session.commit()

        db_session.delete(flat)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()
    finally:
        db_session.execute(text("PRAGMA foreign_keys = OFF;"))


def test_idempotency_concurrent_in_flight_request_rejected(db_session: Session) -> None:
    """Requirement: Concurrent in-flight request on same idempotency key raises 409 Conflict."""
    service = BillingService(db_session)
    idemp_key = f"in-flight-key-{uuid.uuid4()}"
    req_hash = "dummy-hash-123"

    # Reserve the key (response_body is None, representing in-flight processing)
    record = service._reserve_idempotency_key(idemp_key, scope="billing_payment", req_hash=req_hash)
    assert record is None  # first caller succeeds

    # Second caller arrives with same key while first is in-flight -> returns existing in-flight record
    rec2 = service._reserve_idempotency_key(idemp_key, scope="billing_payment", req_hash=req_hash)
    assert rec2 is not None
    assert rec2.response_body is None  # still in flight


def test_billing_generation_2400_flats_batch_performance(db_session: Session) -> None:
    """P1 Performance: Generating invoices for 2,400 flats in bounded chunks completes efficiently."""
    soc_id = uuid.uuid4()
    soc = Society(id=soc_id, name="Megacity Township", status=SocietyStatus.ACTIVE)
    db_session.add(soc)

    flats = []
    for t_idx in range(10):
        tow_id = uuid.uuid4()
        tow = Tower(
            id=tow_id, society_id=soc_id, tower_number=f"T{t_idx:02d}", name=f"Tower {t_idx}"
        )
        db_session.add(tow)
        for f_idx in range(240):
            flat = Flat(
                id=uuid.uuid4(),
                society_id=soc_id,
                tower_id=tow_id,
                flat_number=f"{t_idx:02d}-{f_idx:03d}",
                area_sqft=1000 + (f_idx % 5) * 100,
                status=FlatStatus.OCCUPIED,
            )
            flats.append(flat)
    db_session.add_all(flats)
    db_session.commit()

    service = BillingService(db_session)
    # Explicitly configure rate before execution (no silent side effects)
    service.repo.create_default_billing_config(
        society_id=soc_id, effective_from=datetime(2026, 1, 1, tzinfo=UTC)
    )

    # Invariant: Verify chunk size is bounded to 500
    assert service.CHUNK_SIZE == 500

    start = time.perf_counter()
    run = service.execute_billing_run(
        society_id=soc_id,
        billing_period="2027-01",
        actor_id=uuid.uuid4(),
    )
    elapsed = time.perf_counter() - start

    assert run.total_invoiced_flats == 2400
    assert run.status == "COMPLETED"
    assert elapsed < 10.0, f"2,400 flat billing took too long: {elapsed:.2f}s"


def test_billing_preview_has_no_side_effects_on_unconfigured_society(db_session: Session) -> None:
    """Item 4: preview_billing_run() must be read-only and never silently create billing configurations."""
    soc_id = uuid.uuid4()
    soc = Society(id=soc_id, name="Unconfigured Society", status=SocietyStatus.ACTIVE)
    db_session.add(soc)
    db_session.commit()

    service = BillingService(db_session)

    # Calling preview on an unconfigured society must raise ValidationError
    with pytest.raises(ValidationError) as exc_info:
        service.preview_billing_run(society_id=soc_id, billing_period="2026-11")

    assert "no billing configuration found" in str(exc_info.value).lower()

    # Invariant: Database must have ZERO billing configuration rows for this society (no mutation)
    configs = service.repo.get_all_billing_configs(soc_id)
    assert len(configs) == 0, "preview_billing_run must not insert billing configuration rows"


def test_idempotency_key_expiry_allows_new_reservation(db_session: Session) -> None:
    """Item 1: Idempotency keys past their 24-hour expiry must be purged and not block new operations."""
    service = BillingService(db_session)
    expired_key = f"exp-key-{uuid.uuid4()}"
    req_hash = "hash-exp-123"

    # Insert an expired idempotency record (expired 1 hour ago)
    expired_record = IdempotencyKey(
        id=uuid.uuid4(),
        scope="billing_payment",
        idempotency_key=expired_key,
        request_hash=req_hash,
        response_status=200,
        response_body='{"status": "OLD_CACHED_RESULT"}',
        created_at=datetime.now(UTC) - timedelta(hours=25),
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    db_session.add(expired_record)
    db_session.commit()

    # Reserving the expired key must succeed as None (fresh reservation, clearing old record)
    res = service._reserve_idempotency_key(
        idempotency_key=expired_key,
        scope="billing_payment",
        req_hash=req_hash,
    )
    assert res is None, "Expired idempotency key must allow fresh reservation"

    # Active key in database must now have a future expiry
    active = (
        db_session.query(IdempotencyKey)
        .filter_by(scope="billing_payment", idempotency_key=expired_key)
        .first()
    )
    assert active is not None
    assert service._to_utc(active.expires_at) > datetime.now(UTC)


def test_idempotency_stuck_in_flight_timeout_recovery(db_session: Session) -> None:
    """Item 1: In-flight requests older than 2 minutes (crashed process) are safely recovered."""
    service = BillingService(db_session)
    stuck_key = f"stuck-key-{uuid.uuid4()}"
    req_hash = "hash-stuck-123"

    # Insert a hung in-flight record (started 5 minutes ago without completing)
    stuck_record = IdempotencyKey(
        id=uuid.uuid4(),
        scope="billing_payment",
        idempotency_key=stuck_key,
        request_hash=req_hash,
        response_status=None,
        response_body=None,
        created_at=datetime.now(UTC) - timedelta(minutes=5),
        expires_at=datetime.now(UTC) + timedelta(hours=23),
    )
    db_session.add(stuck_record)
    db_session.commit()

    # Reserving must recover from the hung reservation
    res = service._reserve_idempotency_key(
        idempotency_key=stuck_key,
        scope="billing_payment",
        req_hash=req_hash,
    )
    assert res is None, "Hung in-flight key must be recovered"


def test_cleanup_expired_idempotency_records(db_session: Session) -> None:
    """Item 1: Database cleanup helper purges expired records and leaves active ones untouched."""
    service = BillingService(db_session)
    now = datetime.now(UTC)

    # 2 expired records
    for i in range(2):
        db_session.add(
            IdempotencyKey(
                id=uuid.uuid4(),
                scope="cleanup_test",
                idempotency_key=f"exp-{i}-{uuid.uuid4()}",
                request_hash=f"h-exp-{i}",
                response_status=200,
                response_body="{}",
                created_at=now - timedelta(hours=30),
                expires_at=now - timedelta(hours=5),
            )
        )
    # 2 active records
    for i in range(2):
        db_session.add(
            IdempotencyKey(
                id=uuid.uuid4(),
                scope="cleanup_test",
                idempotency_key=f"act-{i}-{uuid.uuid4()}",
                request_hash=f"h-act-{i}",
                response_status=200,
                response_body="{}",
                created_at=now,
                expires_at=now + timedelta(hours=24),
            )
        )
    db_session.commit()

    deleted_count = service.cleanup_expired_idempotency_records()
    assert deleted_count >= 2

    # Verify active records still remain
    active_remaining = (
        db_session.query(IdempotencyKey).filter(IdempotencyKey.scope == "cleanup_test").count()
    )
    assert active_remaining == 2


def _create_test_invoice(db_session: Session, flat_id: str, period: str = "2026-11") -> Invoice:
    inv = Invoice(
        id=uuid.uuid4(),
        society_id=uuid.UUID(SOCIETY_ID),
        flat_id=uuid.UUID(flat_id),
        billing_period=period,
        invoice_number=f"INV-TEST-{uuid.uuid4().hex[:6]}",
        area_sqft_snapshot=1150,
        rate_paise_per_sqft_snapshot=650,
        subtotal_paise=747500,
        total_paise=747500,
        due_date=datetime(2026, 12, 10, 18, 29, 59, tzinfo=UTC),
        status=InvoiceStatus.UNPAID,
    )
    db_session.add(inv)
    db_session.commit()
    return inv


def test_successful_full_payment(client: TestClient, db_session: Session) -> None:
    """Requirement: Pay exact outstanding, invoice becomes PAID, DB allocation equals total_paise."""
    inv = _create_test_invoice(db_session, FLAT_1203_ID, period="2026-08")
    inv_id = str(inv.id)
    pay_amount = inv.total_paise

    res = client.post(
        f"/api/v1/billing/invoices/{inv_id}/payments",
        headers={**AUTH_NEERAJ, "Idempotency-Key": f"idemp-full-{uuid.uuid4()}"},
        json={"amount_paise": pay_amount, "simulate_failure": False},
    )
    assert res.status_code == 200
    payment_data = res.json()
    assert payment_data["status"] == "SUCCESS"
    assert payment_data["amount_paise"] == pay_amount

    # Verify DB state
    db_session.expire_all()
    db_invoice = db_session.get(Invoice, inv.id)
    assert db_invoice is not None
    assert db_invoice.status == InvoiceStatus.PAID

    allocations = (
        db_session.query(PaymentAllocation).filter(PaymentAllocation.invoice_id == inv.id).all()
    )
    assert len(allocations) == 1
    assert allocations[0].allocated_paise == pay_amount


def test_successful_partial_payment(client: TestClient, db_session: Session) -> None:
    """Requirement: Pay less than outstanding, invoice becomes PARTIALLY_PAID."""
    inv = _create_test_invoice(db_session, FLAT_1203_ID, period="2026-09")
    inv_id = str(inv.id)
    pay_amount = 300000

    res = client.post(
        f"/api/v1/billing/invoices/{inv_id}/payments",
        headers={**AUTH_NEERAJ, "Idempotency-Key": f"idemp-partial-{uuid.uuid4()}"},
        json={"amount_paise": pay_amount, "simulate_failure": False},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "SUCCESS"

    db_session.expire_all()
    db_invoice = db_session.get(Invoice, inv.id)
    assert db_invoice is not None
    assert db_invoice.status == InvoiceStatus.PARTIALLY_PAID

    allocations = (
        db_session.query(PaymentAllocation).filter(PaymentAllocation.invoice_id == inv.id).all()
    )
    assert len(allocations) == 1
    assert allocations[0].allocated_paise == pay_amount


def test_simulated_payment_failure_and_db_state(client: TestClient, db_session: Session) -> None:
    """Requirement: simulate_failure=True results in FAILED payment, 0 allocations, ledger unchanged."""
    inv = _create_test_invoice(db_session, FLAT_1203_ID, period="2026-10")
    inv_id = str(inv.id)

    ledger_count_before = (
        db_session.query(FinancialLedgerEntry)
        .filter(FinancialLedgerEntry.invoice_id == inv.id)
        .count()
    )

    res = client.post(
        f"/api/v1/billing/invoices/{inv_id}/payments",
        headers={**AUTH_NEERAJ, "Idempotency-Key": f"idemp-fail-{uuid.uuid4()}"},
        json={"amount_paise": 200000, "simulate_failure": True},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "FAILED"

    db_session.expire_all()
    db_invoice = db_session.get(Invoice, inv.id)
    assert db_invoice is not None
    assert db_invoice.status == InvoiceStatus.UNPAID

    # Verify no allocation created
    alloc_count = (
        db_session.query(PaymentAllocation).filter(PaymentAllocation.invoice_id == inv.id).count()
    )
    assert alloc_count == 0

    # Verify ledger entries for this invoice unchanged
    ledger_count_after = (
        db_session.query(FinancialLedgerEntry)
        .filter(FinancialLedgerEntry.invoice_id == inv.id)
        .count()
    )
    assert ledger_count_after == ledger_count_before


def test_receipt_generated_only_after_success(client: TestClient, db_session: Session) -> None:
    """Requirement: Receipt generation is 404 for invoice without successful payment."""
    inv = _create_test_invoice(db_session, FLAT_0408_ID, period="2026-10")
    inv_id = str(inv.id)

    res = client.get(f"/api/v1/billing/invoices/{inv_id}/receipt", headers=AUTH_SWATI)
    assert res.status_code == 404


def test_interrupted_payment_intent_recovery(client: TestClient, db_session: Session) -> None:
    """Requirement: Payment intents stuck in PENDING state can be recovered by helpdesk staff."""
    inv = _create_test_invoice(db_session, FLAT_1601_ID, period="2026-10")
    society_id = uuid.UUID(SOCIETY_ID)

    # Insert a simulated stuck payment in PENDING state created 10 minutes ago
    ten_min_ago = datetime.now(UTC) - timedelta(minutes=10)
    stuck_payment = Payment(
        id=uuid.uuid4(),
        society_id=society_id,
        flat_id=inv.flat_id,
        amount_paise=400000,
        currency="INR",
        provider="SIMULATED",
        provider_reference=f"SIM-STUCK-{uuid.uuid4().hex[:6]}",
        status=PaymentStatus.PENDING,
        initiated_by=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        created_at=ten_min_ago,
        updated_at=ten_min_ago,
    )
    db_session.add(stuck_payment)
    db_session.commit()

    # Call staff recovery endpoint
    res_recover = client.post(
        "/api/v1/billing/admin/payments/recover-interrupted?timeout_minutes=5",
        headers=AUTH_HELPDESK,
    )
    assert res_recover.status_code == 200
    assert res_recover.json()["recovered_count"] >= 1

    # Verify payment status is now FAILED
    db_session.expire_all()
    p_refreshed = db_session.get(Payment, stuck_payment.id)
    assert p_refreshed is not None
    assert p_refreshed.status == PaymentStatus.FAILED


def test_simulated_provider_exception_fails_closed(db_session: Session) -> None:
    """Requirement: When payment provider raises an exception, payment fails closed without allocation."""
    inv = _create_test_invoice(db_session, FLAT_1203_ID, period="2026-12")

    class CrashingProvider:
        @property
        def provider_name(self) -> str:
            return "CRASHING"

        def process_payment(self, *args, **kwargs):
            raise TimeoutError("Simulated gateway network timeout")

    service = BillingService(db_session, payment_provider=CrashingProvider())
    resp = service.process_invoice_payment(
        society_id=inv.society_id,
        invoice_id=inv.id,
        amount_paise=100000,
        user_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        idempotency_key=f"idemp-crash-{uuid.uuid4()}",
    )
    assert resp.status == PaymentStatus.FAILED

    db_session.expire_all()
    alloc_count = (
        db_session.query(PaymentAllocation).filter(PaymentAllocation.invoice_id == inv.id).count()
    )
    assert alloc_count == 0
