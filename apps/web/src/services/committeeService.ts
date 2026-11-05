/**
 * Committee Dashboard & Governance API Service
 */

import { apiClient } from './apiClient';

export interface AgeingBuckets {
  bucket_0_30_paise: number;
  bucket_31_60_paise: number;
  bucket_61_90_paise: number;
  bucket_90_plus_paise: number;
}

export interface FinancialSummary {
  total_billed_paise: number;
  total_collected_paise: number;
  total_outstanding_paise: number;
  total_overdue_paise: number;
  collection_percentage: number;
  ageing: {
    bucket_0_30_paise: number;
    bucket_31_60_paise: number;
    bucket_61_90_paise: number;
    bucket_90_plus_paise: number;
  };
}

export interface ComplaintSummary {
  total_complaints: number;
  open_complaints: number;
  in_progress_complaints: number;
  resolved_complaints: number;
  closed_complaints: number;
  safety_escalated_count: number;
  sla_breached_count: number;
  first_response_sla_breached_count: number;
  reopened_count: number;
  avg_resolution_hours: number;
  median_resolution_hours: number;
  avg_first_response_hours: number;
  median_first_response_hours: number;
}

export interface TowerFinancialMetric {
  tower_id: string;
  tower_number: string;
  tower_name: string;
  total_flats: number;
  total_billed_paise: number;
  total_collected_paise: number;
  total_outstanding_paise: number;
  open_complaints: number;
}

export interface CommitteeOverviewResponse {
  society_id: string;
  society_name: string;
  as_of_date: string;
  financials: FinancialSummary;
  complaints: ComplaintSummary;
  towers: TowerFinancialMetric[];
}

export interface MonthlyReportItem {
  billing_period: string;
  total_invoices: number;
  total_billed_paise: number;
  total_collected_paise: number;
  total_outstanding_paise: number;
  collection_percentage: number;
}

export const committeeService = {
  async getOverview(societyId?: string): Promise<CommitteeOverviewResponse> {
    const query = societyId ? `?society_id=${encodeURIComponent(societyId)}` : '';
    return apiClient.request<CommitteeOverviewResponse>(`/api/v1/committee/overview${query}`);
  },

  async getMonthlyReports(societyId?: string): Promise<MonthlyReportItem[]> {
    const query = societyId ? `?society_id=${encodeURIComponent(societyId)}` : '';
    return apiClient.request<MonthlyReportItem[]>(`/api/v1/committee/reports/monthly${query}`);
  },

  async downloadCsvExport(societyId?: string): Promise<void> {
    const query = societyId ? `?society_id=${encodeURIComponent(societyId)}` : '';
    const baseUrl = import.meta.env.VITE_API_URL || '';
    const url = `${baseUrl}/api/v1/committee/reports/export${query}`;
    const token = apiClient.getToken();

    const headers: Record<string, string> = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(url, { headers });
    if (!response.ok) {
      throw new Error(`CSV export failed with status ${response.status}`);
    }

    const blob = await response.blob();
    const downloadUrl = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.download = `committee_financial_report_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(downloadUrl);
  },
};
