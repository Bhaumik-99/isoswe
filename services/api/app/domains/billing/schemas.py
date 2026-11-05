"""Billing Domain Pydantic v2 Schemas

Strict typed schemas for:
- Invoices & Line items
- Payment initiation & allocations
- Receipts
- Society billing runs & previews
- Staff & Resident overview summaries
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domains.billing.models import InvoiceStatus, LateFeeCalculationMethod, PaymentStatus


class InvoiceLineItemSchema(BaseModel):
    id: UUID
    invoice_id: UUID
    description: str
    quantity: int
    unit_rate_paise: int
    amount_paise: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaymentAllocationSchema(BaseModel):
    id: UUID
    payment_id: UUID
    invoice_id: UUID
    invoice_number: str | None = None
    allocated_paise: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InvoiceResponse(BaseModel):
    id: UUID
    society_id: UUID
    flat_id: UUID
    billing_period: str
    invoice_number: str
    area_sqft_snapshot: int
    rate_paise_per_sqft_snapshot: int
    subtotal_paise: int
    total_paise: int
    paid_paise: int
    outstanding_paise: int
    due_date: datetime
    status: InvoiceStatus
    is_overdue: bool
    line_items: list[InvoiceLineItemSchema] = Field(default_factory=list)
    tower_number: str | None = None
    flat_number: str | None = None
    resident_name: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ResidentBillingSummaryResponse(BaseModel):
    total_outstanding_paise: int
    total_invoiced_paise: int
    total_paid_paise: int
    total_overdue_paise: int
    unpaid_count: int
    partially_paid_count: int
    paid_count: int
    overdue_count: int
    current_billing_period: str
    latest_invoice: InvoiceResponse | None = None
    next_due_date: datetime | None = None


class PaymentResponse(BaseModel):
    id: UUID
    society_id: UUID
    flat_id: UUID
    amount_paise: int
    currency: str
    provider: str
    provider_reference: str
    status: PaymentStatus
    initiated_by: UUID
    allocations: list[PaymentAllocationSchema] = Field(default_factory=list)
    tower_number: str | None = None
    flat_number: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InitiatePaymentRequest(BaseModel):
    amount_paise: int = Field(..., gt=0, description="Amount in integer paise (1 INR = 100 paise)")
    simulate_failure: bool = Field(
        default=False, description="Set to true for demonstration of controlled payment failure"
    )


class ReceiptResponse(BaseModel):
    receipt_number: str
    payment_id: UUID
    invoice_id: UUID
    invoice_number: str
    billing_period: str
    amount_paid_paise: int
    payment_date: datetime
    payment_provider: str
    provider_reference: str
    tower_number: str
    flat_number: str
    payer_name: str
    remaining_outstanding_paise: int
    society_name: str


class ExcludedFlatDetail(BaseModel):
    flat_id: UUID
    tower_number: str
    flat_number: str
    reason: str


class EligibleFlatDetail(BaseModel):
    flat_id: UUID
    tower_number: str
    flat_number: str
    area_sqft: int
    expected_amount_paise: int


class BillingRunPreviewResponse(BaseModel):
    society_id: UUID
    billing_period: str
    due_date: datetime
    rate_paise_per_sqft: int
    eligible_flats_count: int
    excluded_flats_count: int
    already_invoiced_count: int
    total_expected_charges_paise: int
    eligible_flats: list[EligibleFlatDetail] = Field(default_factory=list)
    excluded_flats: list[ExcludedFlatDetail] = Field(default_factory=list)


class ExecuteBillingRunRequest(BaseModel):
    billing_period: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}$",
        description="Target monthly billing period in YYYY-MM format (e.g. '2026-11')",
    )
    due_date: datetime | None = Field(
        default=None,
        description="Optional custom due date; defaults to society due day of following month",
    )


class BillingRunResponse(BaseModel):
    id: UUID
    society_id: UUID
    billing_period: str
    total_eligible_flats: int
    total_invoiced_flats: int
    total_skipped_flats: int
    total_charges_paise: int
    status: str
    initiated_by: UUID
    run_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StaffBillingOverviewResponse(BaseModel):
    total_billed_paise: int
    total_collected_paise: int
    total_outstanding_paise: int
    total_overdue_paise: int
    total_invoices_count: int
    paid_invoices_count: int
    unpaid_invoices_count: int
    overdue_invoices_count: int
    active_rate_paise_per_sqft: int
    current_period: str


class CreateLateFeePolicyRequest(BaseModel):
    policy_name: str = Field(..., min_length=3, max_length=128)
    calculation_method: LateFeeCalculationMethod = Field(
        default=LateFeeCalculationMethod.FLAT_FEE,
        description="Calculation method: FLAT_FEE, PERCENTAGE_PER_MONTH, or DAILY_INTEREST_PAISE",
    )
    amount_or_rate_bps: int = Field(
        ...,
        gt=0,
        description="Fixed fee in paise or basis points (e.g. 200 bps = 2.0% per month)",
    )
    grace_period_days: int = Field(
        ...,
        ge=0,
        le=90,
        description="Grace period in days as explicitly specified in society bye-laws",
    )
    min_charge_paise: int = Field(default=0, ge=0)
    max_charge_paise: int = Field(default=0, ge=0)
    effective_from: datetime | None = None
    is_active: bool = True


class LateFeePolicyResponse(BaseModel):
    id: UUID
    society_id: UUID
    policy_name: str
    calculation_method: LateFeeCalculationMethod
    amount_or_rate_bps: int
    grace_period_days: int
    min_charge_paise: int
    max_charge_paise: int
    is_active: bool
    effective_from: datetime
    effective_to: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LateFeePreviewItem(BaseModel):
    invoice_id: UUID
    invoice_number: str
    flat_id: UUID
    flat_number: str
    tower_number: str
    billing_period: str
    due_date: datetime
    days_overdue: int
    unpaid_principal_paise: int
    proposed_fee_paise: int
    calculation_explanation: str


class LateFeePreviewResponse(BaseModel):
    society_id: UUID
    policy: LateFeePolicyResponse | None
    total_eligible_invoices: int
    total_proposed_fee_paise: int
    as_of_date: datetime
    items: list[LateFeePreviewItem] = Field(default_factory=list)


class ApplyLateFeesRequest(BaseModel):
    as_of_date: datetime | None = None


class ApplyLateFeesResponse(BaseModel):
    society_id: UUID
    policy_id: UUID
    applied_invoices_count: int
    total_fee_charged_paise: int
    already_assessed_count: int = 0
