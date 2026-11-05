/**
 * Bank Statement Reconciliation Frontend Service Layer
 */

import { apiClient } from './apiClient';
import {
  BankStatementImport,
  BankTransaction,
  ManualReviewQueueItem,
  ProposedAllocation,
  ReconciliationSummary,
  StatementUploadPreview,
  TransactionReconciliationStatus,
  TransactionType,
} from '../types/reconciliation';

export const reconciliationService = {
  /** Uploads a CSV bank statement and returns validation preview */
  async uploadStatement(
    file: File,
    bankProfile = 'AUTO',
    customMapping?: Record<string, string>
  ): Promise<StatementUploadPreview> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('bank_profile', bankProfile);
    if (customMapping) {
      formData.append('custom_mapping', JSON.stringify(customMapping));
    }

    return apiClient.request<StatementUploadPreview>('/api/v1/reconciliation/statements', {
      method: 'POST',
      body: formData,
    });
  },

  /** Confirms validated statement import and runs matching engine */
  async confirmImport(importId: string): Promise<BankStatementImport> {
    return apiClient.request<BankStatementImport>(`/api/v1/reconciliation/statements/${importId}/confirm`, {
      method: 'POST',
    });
  },

  /** Cancels an unconfirmed statement import */
  async cancelImport(importId: string): Promise<void> {
    await apiClient.request<void>(`/api/v1/reconciliation/statements/${importId}/cancel`, {
      method: 'POST',
    });
  },

  /** Lists statement imports */
  async listImports(): Promise<BankStatementImport[]> {
    return apiClient.request<BankStatementImport[]>('/api/v1/reconciliation/statements');
  },

  /** Lists normalized bank transactions with filters */
  async listTransactions(params?: {
    status?: TransactionReconciliationStatus;
    transactionType?: TransactionType;
    importId?: string;
    search?: string;
    skip?: number;
    limit?: number;
  }): Promise<BankTransaction[]> {
    const query = new URLSearchParams();
    if (params?.status) query.append('status', params.status);
    if (params?.transactionType) query.append('transaction_type', params.transactionType);
    if (params?.importId) query.append('import_id', params.importId);
    if (params?.search) query.append('search', params.search);
    if (params?.skip !== undefined) query.append('skip', String(params.skip));
    if (params?.limit !== undefined) query.append('limit', String(params.limit));

    const qs = query.toString() ? `?${query.toString()}` : '';
    return apiClient.request<BankTransaction[]>(`/api/v1/reconciliation/transactions${qs}`);
  },

  /** Fetches a single transaction by ID */
  async getTransaction(transactionId: string): Promise<BankTransaction> {
    return apiClient.request<BankTransaction>(`/api/v1/reconciliation/transactions/${transactionId}`);
  },

  /** Fetches transactions in manual review queue */
  async getReviewQueue(category = 'ALL'): Promise<ManualReviewQueueItem[]> {
    return apiClient.request<ManualReviewQueueItem[]>(`/api/v1/reconciliation/queue?category=${category}`);
  },

  /** Suggests a manual match for a transaction */
  async suggestMatch(
    transactionId: string,
    flatId: string,
    invoiceId?: string,
    notes?: string
  ): Promise<BankTransaction> {
    return apiClient.request<BankTransaction>(`/api/v1/reconciliation/transactions/${transactionId}/suggest`, {
      method: 'POST',
      body: JSON.stringify({ flat_id: flatId, invoice_id: invoiceId, notes }),
    });
  },

  /** Submits proposed allocations for approval */
  async submitForApproval(
    transactionId: string,
    proposedAllocations: ProposedAllocation[],
    notes?: string
  ): Promise<BankTransaction> {
    return apiClient.request<BankTransaction>(
      `/api/v1/reconciliation/transactions/${transactionId}/submit-for-approval`,
      {
        method: 'POST',
        body: JSON.stringify({ proposed_allocations: proposedAllocations, notes }),
      }
    );
  },

  /** Approves allocation and executes atomic financial ledger settlement */
  async approveAndAllocate(
    transactionId: string,
    proposedAllocations: ProposedAllocation[],
    idempotencyKey: string,
    notes?: string
  ): Promise<BankTransaction> {
    return apiClient.request<BankTransaction>(`/api/v1/reconciliation/transactions/${transactionId}/approve`, {
      method: 'POST',
      headers: {
        'Idempotency-Key': idempotencyKey,
      },
      body: JSON.stringify({ proposed_allocations: proposedAllocations, notes }),
    });
  },

  /** Rejects a suggested match */
  async rejectMatch(transactionId: string, reason: string): Promise<BankTransaction> {
    return apiClient.request<BankTransaction>(`/api/v1/reconciliation/transactions/${transactionId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  },

  /** Marks transaction as unidentified / suspense credit */
  async markUnidentified(transactionId: string, notes: string): Promise<BankTransaction> {
    return apiClient.request<BankTransaction>(
      `/api/v1/reconciliation/transactions/${transactionId}/mark-unidentified`,
      {
        method: 'POST',
        body: JSON.stringify({ notes }),
      }
    );
  },

  /** Fetches society reconciliation KPI summary */
  async getSummary(): Promise<ReconciliationSummary> {
    return apiClient.request<ReconciliationSummary>('/api/v1/reconciliation/summary');
  },

  /** Returns direct CSV export URL */
  getExportReportUrl(): string {
    return '/api/v1/reconciliation/reports/export';
  },
};
