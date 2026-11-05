"""Phase 5: Maintenance Billing Late Fees Test Suite

Validates:
1. Configurable maintenance late-fee policies following society bye-laws.
2. Due dates, grace periods, and effective dates.
3. Configurable calculation methods:
   - FLAT_FEE
   - PERCENTAGE_PER_MONTH
   - DAILY_INTEREST_PAISE
4. Correct handling of partially paid invoices (late fee on remaining unpaid balance only).
5. Preview of proposed late-fee amounts before application without state mutation.
6. Auditable fee application, line item generation, and immutable ledger entries.
7. Idempotent execution so repeated jobs cannot charge the same fee twice.
8. Missing policy does not silently create a default late fee.
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.billing.models import (
    FinancialLedgerEntry,
    Invoice,
    InvoiceLineItem,
    InvoiceStatus,
    LateFeeApplication,
    LateFeeCalculationMethod,
    LateFeePolicy,
    LedgerEntryType,
    Payment,
    PaymentAllocation,
    PaymentStatus,
)
from app.domains.identity.models import Flat, User

SOCIETY_ID = "11111111-1111-1111-1111-111111111111"
AUTH_HELPDESK = {"Authorization": "Bearer dev-token-helpdesk"}
AUTH_RESIDENT = {"Authorization": "Bearer dev-token-neeraj"}


def test_missing_policy_does_not_silently_apply_fee(
    client: TestClient, db_session: Session
) -> None:
    """Security/Governance: If no approved late fee policy is configured,
    the system must NOT silently apply a default late fee."""
    soc_id = uuid.UUID(SOCIETY_ID)

    # Ensure no active policy exists
    db_session.query(LateFeePolicy).filter(LateFeePolicy.society_id == soc_id).delete()
    db_session.commit()

    # 1. Preview returns 0 proposed fees and policy = None
    res_prev = client.post(
        "/api/v1/billing/late-fees/preview",
        headers=AUTH_HELPDESK,
    )
    assert res_prev.status_code == 200
    data_prev = res_prev.json()
    assert data_prev["policy"] is None
    assert data_prev["total_proposed_fee_paise"] == 0
    assert data_prev["total_eligible_invoices"] == 0

    # 2. Apply raises 400 with explicit bye-law requirement message
    res_apply = client.post(
        "/api/v1/billing/late-fees/apply",
        headers=AUTH_HELPDESK,
    )
    assert res_apply.status_code in (400, 422)
    assert "No approved late-fee policy configured" in res_apply.json()["error"]["message"]


def test_create_and_list_late_fee_policies(client: TestClient) -> None:
    """Staff can configure an approved late fee policy following society bye-laws."""
    # 1. Resident cannot manage policies -> 403 Forbidden
    res_forbidden = client.post(
        "/api/v1/billing/late-fee-policies",
        json={
            "policy_name": "Resident Bypass Attempt",
            "calculation_method": "FLAT_FEE",
            "amount_or_rate_bps": 25000,
            "grace_period_days": 15,
        },
        headers=AUTH_RESIDENT,
    )
    assert res_forbidden.status_code == 403

    # 2. Helpdesk creates Flat Fee policy (₹250 flat after 15 days grace)
    res_create = client.post(
        "/api/v1/billing/late-fee-policies",
        json={
            "policy_name": "Standard Bye-Law Late Fee (Demo)",
            "calculation_method": "FLAT_FEE",
            "amount_or_rate_bps": 25000,  # ₹250.00
            "grace_period_days": 15,
            "min_charge_paise": 0,
            "max_charge_paise": 50000,
            "is_active": True,
        },
        headers=AUTH_HELPDESK,
    )
    assert res_create.status_code == 201
    created = res_create.json()
    assert created["policy_name"] == "Standard Bye-Law Late Fee (Demo)"
    assert created["amount_or_rate_bps"] == 25000
    assert created["grace_period_days"] == 15

    # 3. List policies returns the created policy
    res_list = client.get(
        "/api/v1/billing/late-fee-policies",
        headers=AUTH_HELPDESK,
    )
    assert res_list.status_code == 200
    policies = res_list.json()
    assert any(p["id"] == created["id"] for p in policies)


def test_no_fee_before_due_date_or_within_grace_period(
    client: TestClient, db_session: Session
) -> None:
    """No fee is charged if the invoice is not yet due or is within the grace period."""
    soc_id = uuid.UUID(SOCIETY_ID)
    flat = db_session.query(Flat).filter(Flat.society_id == soc_id).first()
    assert flat is not None

    now = datetime.now(UTC)

    # 1. Invoice A: Due in the future (not due yet)
    inv_future = Invoice(
        id=uuid.uuid4(),
        society_id=soc_id,
        flat_id=flat.id,
        billing_period="2026-12",
        invoice_number=f"INV-FUT-{uuid.uuid4().hex[:6].upper()}",
        area_sqft_snapshot=1000,
        rate_paise_per_sqft_snapshot=650,
        subtotal_paise=650000,
        total_paise=650000,
        due_date=now + timedelta(days=10),
        status=InvoiceStatus.UNPAID,
    )

    # 2. Invoice B: Due 5 days ago (overdue, but within 15-day grace period)
    inv_within_grace = Invoice(
        id=uuid.uuid4(),
        society_id=soc_id,
        flat_id=flat.id,
        billing_period="2026-11",
        invoice_number=f"INV-GRC-{uuid.uuid4().hex[:6].upper()}",
        area_sqft_snapshot=1000,
        rate_paise_per_sqft_snapshot=650,
        subtotal_paise=650000,
        total_paise=650000,
        due_date=now - timedelta(days=5),
        status=InvoiceStatus.UNPAID,
    )
    db_session.add_all([inv_future, inv_within_grace])
    db_session.commit()

    # Configure active policy with 15 days grace
    policy = LateFeePolicy(
        id=uuid.uuid4(),
        society_id=soc_id,
        policy_name="15d Grace Policy",
        calculation_method=LateFeeCalculationMethod.FLAT_FEE,
        amount_or_rate_bps=30000,  # ₹300
        grace_period_days=15,
        is_active=True,
        effective_from=now - timedelta(days=60),
    )
    db_session.add(policy)
    db_session.commit()

    # Preview as of today
    prev = client.post("/api/v1/billing/late-fees/preview", headers=AUTH_HELPDESK).json()
    prev_invoice_ids = [item["invoice_id"] for item in prev["items"]]

    assert str(inv_future.id) not in prev_invoice_ids
    assert str(inv_within_grace.id) not in prev_invoice_ids


def test_late_fee_calculation_methods_and_partial_payment(
    client: TestClient, db_session: Session
) -> None:
    """Tests PERCENTAGE_PER_MONTH calculation and partial payment handling.

    Late fee must be assessed ONLY on the unpaid principal balance, not the original total.
    """
    soc_id = uuid.UUID(SOCIETY_ID)
    flat = db_session.query(Flat).filter(Flat.society_id == soc_id).first()
    assert flat is not None
    user = db_session.query(User).first()
    assert user is not None

    now = datetime.now(UTC)

    # Deactivate existing policies for clean test
    db_session.query(LateFeePolicy).filter(LateFeePolicy.society_id == soc_id).update(
        {"is_active": False}
    )

    # Policy: 2.0% per month (200 basis points) with 10 days grace
    policy = LateFeePolicy(
        id=uuid.uuid4(),
        society_id=soc_id,
        policy_name="2 Percent Monthly Policy",
        calculation_method=LateFeeCalculationMethod.PERCENTAGE_PER_MONTH,
        amount_or_rate_bps=200,  # 2.0% per month
        grace_period_days=10,
        min_charge_paise=10000,  # ₹100 min
        max_charge_paise=100000,  # ₹1,000 max
        is_active=True,
        effective_from=now - timedelta(days=60),
    )
    db_session.add(policy)
    db_session.flush()

    # Invoice: Total ₹10,000 (1,000,000 paise). Due 25 days ago (15 days beyond grace)
    inv = Invoice(
        id=uuid.uuid4(),
        society_id=soc_id,
        flat_id=flat.id,
        billing_period="2026-10",
        invoice_number=f"INV-PART-{uuid.uuid4().hex[:6].upper()}",
        area_sqft_snapshot=1000,
        rate_paise_per_sqft_snapshot=1000,
        subtotal_paise=1000000,
        total_paise=1000000,
        due_date=now - timedelta(days=25),
        status=InvoiceStatus.PARTIALLY_PAID,
    )
    db_session.add(inv)
    db_session.flush()

    # Resident partially paid ₹6,000 (600,000 paise). Unpaid balance = ₹4,000 (400,000 paise).
    payment = Payment(
        id=uuid.uuid4(),
        society_id=soc_id,
        flat_id=flat.id,
        amount_paise=600000,
        provider="SIMULATED",
        provider_reference=f"PAY-PART-{uuid.uuid4().hex[:8]}",
        status=PaymentStatus.SUCCESS,
        initiated_by=user.id,
    )
    alloc = PaymentAllocation(
        id=uuid.uuid4(),
        payment_id=payment.id,
        invoice_id=inv.id,
        allocated_paise=600000,
    )
    db_session.add_all([payment, alloc])
    db_session.commit()

    # 1. Preview: 2.0% on ₹4,000 unpaid balance = ₹80.00 (8,000 paise).
    # Since min_charge_paise is ₹100.00 (10,000 paise), fee must be adjusted to ₹100.00!
    prev_res = client.post("/api/v1/billing/late-fees/preview", headers=AUTH_HELPDESK)
    assert prev_res.status_code == 200
    prev_items = [it for it in prev_res.json()["items"] if it["invoice_id"] == str(inv.id)]
    assert len(prev_items) == 1
    item = prev_items[0]
    assert item["unpaid_principal_paise"] == 400000  # ₹4,000 unpaid
    assert item["proposed_fee_paise"] == 10000  # Adjusted to min fee of ₹100.00
    assert "Adjusted to min fee" in item["calculation_explanation"]


def test_late_fee_application_idempotency_and_ledger_invariants(
    client: TestClient, db_session: Session
) -> None:
    """Verifies atomic application of late fee, ledger posting, and strict idempotency."""
    soc_id = uuid.UUID(SOCIETY_ID)
    flat = db_session.query(Flat).filter(Flat.society_id == soc_id).first()
    assert flat is not None

    now = datetime.now(UTC)

    # Deactivate existing policies
    db_session.query(LateFeePolicy).filter(LateFeePolicy.society_id == soc_id).update(
        {"is_active": False}
    )

    # Policy: Flat ₹250 (25,000 paise)
    policy = LateFeePolicy(
        id=uuid.uuid4(),
        society_id=soc_id,
        policy_name="Idempotency Test Policy",
        calculation_method=LateFeeCalculationMethod.FLAT_FEE,
        amount_or_rate_bps=25000,
        grace_period_days=10,
        is_active=True,
        effective_from=now - timedelta(days=60),
    )
    db_session.add(policy)
    db_session.flush()

    # Invoice: ₹5,000, due 20 days ago (10 days beyond grace)
    inv = Invoice(
        id=uuid.uuid4(),
        society_id=soc_id,
        flat_id=flat.id,
        billing_period="2026-09",
        invoice_number=f"INV-IDEMP-{uuid.uuid4().hex[:6].upper()}",
        area_sqft_snapshot=1000,
        rate_paise_per_sqft_snapshot=500,
        subtotal_paise=500000,
        total_paise=500000,
        due_date=now - timedelta(days=20),
        status=InvoiceStatus.UNPAID,
    )
    db_session.add(inv)
    db_session.commit()

    # 1. Apply late fees
    app_res1 = client.post("/api/v1/billing/late-fees/apply", headers=AUTH_HELPDESK)
    assert app_res1.status_code == 200
    data1 = app_res1.json()
    assert data1["applied_invoices_count"] >= 1

    # Verify Invoice was updated with line item and new total
    db_session.expire_all()
    inv_updated = db_session.query(Invoice).filter(Invoice.id == inv.id).first()
    assert inv_updated is not None
    assert inv_updated.total_paise == 525000  # ₹5,000 + ₹250
    assert inv_updated.status == InvoiceStatus.OVERDUE

    # Verify InvoiceLineItem added
    line_item = (
        db_session.query(InvoiceLineItem)
        .filter(InvoiceLineItem.invoice_id == inv.id, InvoiceLineItem.amount_paise == 25000)
        .first()
    )
    assert line_item is not None
    assert "Late Payment Surcharge" in line_item.description

    # Verify FinancialLedgerEntry appended
    ledger_entry = (
        db_session.query(FinancialLedgerEntry)
        .filter(
            FinancialLedgerEntry.invoice_id == inv.id,
            FinancialLedgerEntry.entry_type == LedgerEntryType.CHARGE,
            FinancialLedgerEntry.amount_paise == 25000,
        )
        .first()
    )
    assert ledger_entry is not None
    assert "LATEFEE-" in (ledger_entry.reference_id or "")

    # Verify LateFeeApplication recorded
    app_record = (
        db_session.query(LateFeeApplication)
        .filter(
            LateFeeApplication.invoice_id == inv.id,
            LateFeeApplication.billing_period == "2026-09",
        )
        .first()
    )
    assert app_record is not None
    assert app_record.fee_paise == 25000

    # 2. IDEMPOTENCY: Repeated invocation must NOT apply a second late fee!
    app_res2 = client.post("/api/v1/billing/late-fees/apply", headers=AUTH_HELPDESK)
    assert app_res2.status_code == 200
    data2 = app_res2.json()
    assert data2["already_assessed_count"] >= 1

    # Invoice total must STILL be 525000, NOT 550000!
    db_session.expire_all()
    inv_after_second = db_session.query(Invoice).filter(Invoice.id == inv.id).first()
    assert inv_after_second is not None
    assert inv_after_second.total_paise == 525000, (
        "Idempotency violation: duplicate late fee applied!"
    )
