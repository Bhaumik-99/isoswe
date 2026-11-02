"""Integration tests for Phase 2 Maintenance Billing & Payment Endpoints."""

from fastapi.testclient import TestClient

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
        headers=AUTH_AAMIR,
        json={"amount_paise": 1500000, "simulate_failure": False},
    )
    assert overpay_res.status_code in (400, 422)
    assert "exceed" in overpay_res.json()["error"]["message"].lower()

    # 2. Simulated payment failure: Invoice status and outstanding must remain unchanged
    fail_res = client.post(
        f"/api/v1/billing/invoices/{invoice_id}/payments",
        headers=AUTH_AAMIR,
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
        headers=AUTH_AAMIR,
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
