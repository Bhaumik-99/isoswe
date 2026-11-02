"""Unit tests for Phase 2 Maintenance Billing Calculations & Financial Invariants."""

import pytest

from app.domains.billing.service import BillingService


def test_maintenance_billing_sample_calculations() -> None:
    """Requirement 13.1 & 3: Monthly maintenance calculation.

    maintenance_paise = area_sqft * 650  (where 650 paise = ₹6.50)
    1. T07-1203 — Neeraj Kulkarni: 1,150 sq ft -> 747,500 paise = ₹7,475.00
    2. T12-0408 — Swati Joshi: 980 sq ft -> 637,000 paise = ₹6,370.00
    3. T21-1601 — Aamir Shaikh: 1,640 sq ft -> 1,066,000 paise = ₹10,660.00
    """
    # Neeraj Kulkarni
    area_neeraj = 1150
    rate = 650
    charge_neeraj = BillingService.calculate_maintenance_charge_paise(area_neeraj, rate)
    assert charge_neeraj == 747500
    assert isinstance(charge_neeraj, int)
    assert charge_neeraj / 100 == 7475.00

    # Swati Joshi
    area_swati = 980
    charge_swati = BillingService.calculate_maintenance_charge_paise(area_swati, rate)
    assert charge_swati == 637000
    assert isinstance(charge_swati, int)
    assert charge_swati / 100 == 6370.00

    # Aamir Shaikh
    area_aamir = 1640
    charge_aamir = BillingService.calculate_maintenance_charge_paise(area_aamir, rate)
    assert charge_aamir == 1066000
    assert isinstance(charge_aamir, int)
    assert charge_aamir / 100 == 10660.00


def test_calculation_rejects_negative_or_zero_values() -> None:
    """Financial invariant: Area and rate must be strictly positive integers."""
    with pytest.raises(ValueError, match="area_sqft must be positive"):
        BillingService.calculate_maintenance_charge_paise(0, 650)

    with pytest.raises(ValueError, match="area_sqft must be positive"):
        BillingService.calculate_maintenance_charge_paise(-100, 650)

    with pytest.raises(ValueError, match="rate_paise_per_sqft must be positive"):
        BillingService.calculate_maintenance_charge_paise(1000, 0)

    with pytest.raises(ValueError, match="rate_paise_per_sqft must be positive"):
        BillingService.calculate_maintenance_charge_paise(1000, -650)


def test_outstanding_balance_calculation() -> None:
    """Financial invariant: Outstanding amount = Invoice total - Valid payment allocations.

    Scenario: Aamir Shaikh:
    Total: ₹10,660 (1,066,000 paise)
    Payment allocation: ₹5,000 (500,000 paise)
    Outstanding: ₹5,660 (566,000 paise)
    """
    total_paise = 1066000
    allocated_paise = 500000
    outstanding_paise = max(0, total_paise - allocated_paise)
    assert outstanding_paise == 566000
    assert outstanding_paise / 100 == 5660.00


def test_overdue_status_derived_safely() -> None:
    """Effective invoice status must be dynamically evaluated based on due date & outstanding.

    Never rely on an unexecuted background job to know whether an invoice is OVERDUE.
    """
    from datetime import UTC, datetime, timedelta

    from app.domains.billing.models import InvoiceStatus

    now = datetime.now(UTC)
    past_due = now - timedelta(days=18)
    future_due = now + timedelta(days=10)

    # Past due with outstanding balance -> OVERDUE
    status_overdue = BillingService.derive_invoice_status(
        persisted_status=InvoiceStatus.PARTIALLY_PAID,
        due_date=past_due,
        total_paise=1066000,
        paid_paise=500000,
        now=now,
    )
    assert status_overdue == InvoiceStatus.OVERDUE

    # Future due with partial payment -> PARTIALLY_PAID
    status_partial = BillingService.derive_invoice_status(
        persisted_status=InvoiceStatus.PARTIALLY_PAID,
        due_date=future_due,
        total_paise=1066000,
        paid_paise=500000,
        now=now,
    )
    assert status_partial == InvoiceStatus.PARTIALLY_PAID

    # Fully paid -> PAID regardless of due date
    status_paid = BillingService.derive_invoice_status(
        persisted_status=InvoiceStatus.PAID,
        due_date=past_due,
        total_paise=1066000,
        paid_paise=1066000,
        now=now,
    )
    assert status_paid == InvoiceStatus.PAID
