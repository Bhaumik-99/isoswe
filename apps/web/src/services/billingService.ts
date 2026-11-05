/**
 * Frontend Billing & Payments API Service
 *
 * Implements typed API requests for resident & helpdesk billing operations.
 */

import { apiClient } from './apiClient';
import {
  BillingRun,
  BillingRunPreview,
  Invoice,
  Payment,
  ReceiptResponse,
  ResidentBillingSummary,
  StaffBillingOverview,
} from '../types/billing';

export function formatINR(paise: number): string {
  const rupees = paise / 100;
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  }).format(rupees);
}

export function formatDateIST(dateStr: string): string {
  try {
    return new Date(dateStr).toLocaleDateString('en-IN', {
      timeZone: 'Asia/Kolkata',
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  } catch {
    return dateStr;
  }
}

export function formatDateTimeIST(dateStr: string): string {
  try {
    return new Date(dateStr).toLocaleString('en-IN', {
      timeZone: 'Asia/Kolkata',
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return dateStr;
  }
}

export type LateFeeCalculationMethod = 'FLAT_FEE' | 'PERCENTAGE_PER_MONTH' | 'DAILY_INTEREST_PAISE';

export interface LateFeePolicy {
  id: string;
  society_id: string;
  policy_name: string;
  calculation_method: LateFeeCalculationMethod;
  amount_or_rate_bps: number;
  grace_period_days: number;
  min_charge_paise: number;
  max_charge_paise: number;
  is_active: boolean;
  effective_from: string;
  effective_to?: string | null;
}

export interface CreateLateFeePolicyPayload {
  policy_name: string;
  calculation_method: LateFeeCalculationMethod;
  amount_or_rate_bps: number;
  grace_period_days: number;
  min_charge_paise?: number;
  max_charge_paise?: number;
  is_active?: boolean;
  effective_from?: string;
}

export interface LateFeePreviewItem {
  invoice_id: string;
  invoice_number: string;
  flat_number: string;
  tower_number: string;
  billing_period: string;
  due_date: string;
  days_overdue: number;
  unpaid_principal_paise: number;
  proposed_fee_paise: number;
  explanation: string;
}

export interface LateFeePreviewResponse {
  policy: LateFeePolicy | null;
  evaluated_at: string;
  total_eligible_invoices: number;
  total_proposed_fee_paise: number;
  items: LateFeePreviewItem[];
}

export interface ApplyLateFeesResponse {
  applied_invoices_count: number;
  total_fee_charged_paise: number;
  message: string;
}

export const billingService = {
  // Resident endpoints
  async getResidentSummary(): Promise<ResidentBillingSummary> {
    return apiClient.get<ResidentBillingSummary>('/api/v1/billing/me/summary');
  },

  async getResidentInvoices(billingPeriod?: string, status?: string): Promise<Invoice[]> {
    const params = new URLSearchParams();
    if (billingPeriod) params.append('billing_period', billingPeriod);
    if (status) params.append('status', status);
    const query = params.toString() ? `?${params.toString()}` : '';
    return apiClient.get<Invoice[]>(`/api/v1/billing/me/invoices${query}`);
  },

  async getResidentPayments(): Promise<Payment[]> {
    return apiClient.get<Payment[]>('/api/v1/billing/me/payments');
  },

  async getInvoiceDetail(invoiceId: string): Promise<Invoice> {
    return apiClient.get<Invoice>(`/api/v1/billing/invoices/${invoiceId}`);
  },

  async getInvoiceReceipt(invoiceId: string): Promise<ReceiptResponse> {
    return apiClient.get<ReceiptResponse>(`/api/v1/billing/invoices/${invoiceId}/receipt`);
  },

  async initiatePayment(
    invoiceId: string,
    amountPaise: number,
    simulateFailure: boolean = false,
    idempotencyKey?: string,
  ): Promise<Payment> {
    const headers: Record<string, string> = {};
    if (idempotencyKey) {
      headers['Idempotency-Key'] = idempotencyKey;
    }
    return apiClient.post<Payment>(
      `/api/v1/billing/invoices/${invoiceId}/payments`,
      {
        amount_paise: amountPaise,
        simulate_failure: simulateFailure,
      },
      { headers },
    );
  },

  // Staff endpoints
  async getStaffOverview(): Promise<StaffBillingOverview> {
    return apiClient.get<StaffBillingOverview>('/api/v1/billing/staff/overview');
  },

  async getStaffInvoices(filters?: {
    billing_period?: string;
    tower_number?: string;
    flat_number?: string;
    status?: string;
    limit?: number;
    offset?: number;
  }): Promise<Invoice[]> {
    const params = new URLSearchParams();
    if (filters?.billing_period) params.append('billing_period', filters.billing_period);
    if (filters?.tower_number) params.append('tower_number', filters.tower_number);
    if (filters?.flat_number) params.append('flat_number', filters.flat_number);
    if (filters?.status) params.append('status', filters.status);
    if (filters?.limit !== undefined) params.append('limit', filters.limit.toString());
    if (filters?.offset !== undefined) params.append('offset', filters.offset.toString());
    const query = params.toString() ? `?${params.toString()}` : '';
    return apiClient.get<Invoice[]>(`/api/v1/billing/staff/invoices${query}`);
  },

  async previewBillingRun(billingPeriod: string): Promise<BillingRunPreview> {
    return apiClient.post<BillingRunPreview>('/api/v1/billing/staff/runs/preview', {
      billing_period: billingPeriod,
    });
  },

  async executeBillingRun(billingPeriod: string): Promise<BillingRun> {
    return apiClient.post<BillingRun>('/api/v1/billing/staff/runs', {
      billing_period: billingPeriod,
    });
  },

  async getBillingRun(runId: string): Promise<BillingRun> {
    return apiClient.get<BillingRun>(`/api/v1/billing/staff/runs/${runId}`);
  },

  async getLateFeePolicies(societyId?: string): Promise<LateFeePolicy[]> {
    const params = societyId ? `?society_id=${societyId}` : '';
    return apiClient.get<LateFeePolicy[]>(`/api/v1/billing/late-fee-policies${params}`);
  },

  async createLateFeePolicy(payload: CreateLateFeePolicyPayload): Promise<LateFeePolicy> {
    return apiClient.post<LateFeePolicy>('/api/v1/billing/late-fee-policies', payload);
  },

  async previewLateFees(asOfDate?: string): Promise<LateFeePreviewResponse> {
    return apiClient.post<LateFeePreviewResponse>('/api/v1/billing/late-fees/preview', {
      as_of_date: asOfDate,
    });
  },

  async applyLateFees(asOfDate?: string): Promise<ApplyLateFeesResponse> {
    return apiClient.post<ApplyLateFeesResponse>('/api/v1/billing/late-fees/apply', {
      as_of_date: asOfDate,
    });
  },
};
