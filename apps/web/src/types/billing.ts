/**
 * TypeScript definitions for Phase 2 Maintenance Billing & Payments
 */

export type InvoiceStatus = 'UNPAID' | 'PARTIALLY_PAID' | 'PAID' | 'OVERDUE' | 'VOID';

export type PaymentStatus = 'PENDING' | 'SUCCESS' | 'FAILED' | 'REFUNDED';

export interface InvoiceLineItem {
  id: string;
  invoice_id: string;
  description: string;
  quantity: number;
  unit_rate_paise: number;
  amount_paise: number;
  created_at: string;
}

export interface PaymentAllocation {
  id: string;
  payment_id: string;
  invoice_id: string;
  allocated_paise: number;
  created_at: string;
}

export interface Invoice {
  id: string;
  society_id: string;
  flat_id: string;
  billing_period: string;
  invoice_number: string;
  area_sqft_snapshot: number;
  rate_paise_per_sqft_snapshot: number;
  subtotal_paise: number;
  total_paise: number;
  paid_paise: number;
  outstanding_paise: number;
  due_date: string;
  status: InvoiceStatus;
  is_overdue: boolean;
  tower_number?: string | null;
  flat_number?: string | null;
  resident_name?: string | null;
  line_items: InvoiceLineItem[];
  allocations: PaymentAllocation[];
  created_at: string;
  updated_at: string;
}

export interface Payment {
  id: string;
  society_id: string;
  flat_id: string;
  amount_paise: number;
  currency: string;
  provider: string;
  provider_reference: string;
  status: PaymentStatus;
  initiated_by: string;
  allocations: PaymentAllocation[];
  tower_number?: string | null;
  flat_number?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ResidentBillingSummary {
  total_outstanding_paise: number;
  total_invoiced_paise: number;
  total_paid_paise: number;
  total_overdue_paise: number;
  unpaid_count: number;
  partially_paid_count: number;
  paid_count: number;
  overdue_count: number;
  current_billing_period: string;
  latest_invoice?: Invoice | null;
  next_due_date?: string | null;
}

export interface StaffBillingOverview {
  total_billed_paise: number;
  total_collected_paise: number;
  total_outstanding_paise: number;
  total_overdue_paise: number;
  total_invoices_count: number;
  paid_invoices_count: number;
  unpaid_invoices_count: number;
  overdue_invoices_count: number;
  active_rate_paise_per_sqft: number;
  current_period: string;
}

export interface ReceiptResponse {
  receipt_number: string;
  payment_id: string;
  invoice_id: string;
  invoice_number: string;
  billing_period: string;
  amount_paid_paise: number;
  payment_date: string;
  payment_provider: string;
  provider_reference: string;
  tower_number: string;
  flat_number: string;
  payer_name: string;
  remaining_outstanding_paise: number;
  society_name: string;
}

export interface EligibleFlatDetail {
  flat_id: string;
  tower_number: string;
  flat_number: string;
  area_sqft: number;
  expected_amount_paise: number;
}

export interface ExcludedFlatDetail {
  flat_id: string;
  tower_number: string;
  flat_number: string;
  reason: string;
}

export interface BillingRunPreview {
  society_id: string;
  billing_period: string;
  due_date: string;
  rate_paise_per_sqft: number;
  eligible_flats_count: number;
  excluded_flats_count: number;
  already_invoiced_count: number;
  total_expected_charges_paise: number;
  eligible_flats: EligibleFlatDetail[];
  excluded_flats: ExcludedFlatDetail[];
}

export interface BillingRun {
  id: string;
  society_id: string;
  billing_period: string;
  total_eligible_flats: number;
  total_invoiced_flats: number;
  total_skipped_flats: number;
  total_charges_paise: number;
  status: string;
  initiated_by: string;
  metadata: Record<string, unknown>;
  created_at: string;
}
