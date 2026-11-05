import { describe, it, expect, vi, beforeEach } from 'vitest';
import { reconciliationService } from './reconciliationService';
import { apiClient } from './apiClient';
import { formatPaiseToINR } from '../types/reconciliation';

describe('reconciliationService', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('formats paise correctly to Indian Rupee currency string', () => {
    expect(formatPaiseToINR(0)).toBe('₹0.00');
    expect(formatPaiseToINR(500000)).toBe('₹5,000.00');
    expect(formatPaiseToINR(12345678)).toBe('₹1,23,456.78');
  });

  it('uploads statement using FormData and correct endpoint', async () => {
    const mockPreview = {
      import_id: 'imp-1',
      file_name: 'hdfc_nov.csv',
      total_rows: 5,
      valid_rows: 5,
      rejected_rows: 0,
    };
    const requestSpy = vi.spyOn(apiClient, 'request').mockResolvedValue(mockPreview as any);

    const file = new File(['header\nrow1'], 'hdfc_nov.csv', { type: 'text/csv' });
    const result = await reconciliationService.uploadStatement(file, 'HDFC');

    expect(requestSpy).toHaveBeenCalledWith('/api/v1/reconciliation/statements', {
      method: 'POST',
      body: expect.any(FormData),
    });
    expect(result.import_id).toBe('imp-1');
  });

  it('confirms import by calling confirm endpoint', async () => {
    const mockConfirmed = { id: 'imp-1', status: 'COMPLETED' };
    const requestSpy = vi.spyOn(apiClient, 'request').mockResolvedValue(mockConfirmed as any);

    const result = await reconciliationService.confirmImport('imp-1');
    expect(requestSpy).toHaveBeenCalledWith('/api/v1/reconciliation/statements/imp-1/confirm', {
      method: 'POST',
    });
    expect(result.status).toBe('COMPLETED');
  });

  it('lists transactions with correct URL query parameters', async () => {
    const requestSpy = vi.spyOn(apiClient, 'request').mockResolvedValue([] as any);

    await reconciliationService.listTransactions({
      status: 'UNMATCHED',
      transactionType: 'CREDIT',
      search: 'NEFT',
      limit: 50,
    });

    expect(requestSpy).toHaveBeenCalledWith(
      '/api/v1/reconciliation/transactions?status=UNMATCHED&transaction_type=CREDIT&search=NEFT&limit=50'
    );
  });

  it('fetches manual review queue with category', async () => {
    const requestSpy = vi.spyOn(apiClient, 'request').mockResolvedValue([] as any);

    await reconciliationService.getReviewQueue('SUSPENSE');
    expect(requestSpy).toHaveBeenCalledWith('/api/v1/reconciliation/queue?category=SUSPENSE');
  });

  it('approves allocation with mandatory Idempotency-Key and payload', async () => {
    const mockResult = { id: 'txn-1', reconciliation_status: 'POSTED' };
    const requestSpy = vi.spyOn(apiClient, 'request').mockResolvedValue(mockResult as any);

    const allocations = [{ invoice_id: 'inv-1', allocated_paise: 500000 }];
    const idempHeader = 'Idempotency-Key';
    const testToken = '11111111-2222-3333-4444-555555555555';
    const result = await reconciliationService.approveAndAllocate(
      'txn-1',
      allocations,
      testToken,
      'Approved by helpdesk'
    );

    expect(requestSpy).toHaveBeenCalledWith('/api/v1/reconciliation/transactions/txn-1/approve', {
      method: 'POST',
      headers: {
        [idempHeader]: testToken,
      },
      body: JSON.stringify({
        proposed_allocations: allocations,
        notes: 'Approved by helpdesk',
      }),
    });
    expect(result.reconciliation_status).toBe('POSTED');
  });

  it('suggests a manual match for a transaction', async () => {
    const mockResult = { id: 'txn-2', reconciliation_status: 'SUGGESTED' };
    const requestSpy = vi.spyOn(apiClient, 'request').mockResolvedValue(mockResult as any);

    const result = await reconciliationService.suggestMatch('txn-2', 'flat-101', 'inv-101', 'Resident confirmed');
    expect(requestSpy).toHaveBeenCalledWith('/api/v1/reconciliation/transactions/txn-2/suggest', {
      method: 'POST',
      body: JSON.stringify({
        flat_id: 'flat-101',
        invoice_id: 'inv-101',
        notes: 'Resident confirmed',
      }),
    });
    expect(result.reconciliation_status).toBe('SUGGESTED');
  });

  it('marks transaction as unidentified suspense credit', async () => {
    const mockResult = { id: 'txn-3', reconciliation_status: 'UNIDENTIFIED' };
    const requestSpy = vi.spyOn(apiClient, 'request').mockResolvedValue(mockResult as any);

    const result = await reconciliationService.markUnidentified('txn-3', 'No resident claim after 30 days');
    expect(requestSpy).toHaveBeenCalledWith('/api/v1/reconciliation/transactions/txn-3/mark-unidentified', {
      method: 'POST',
      body: JSON.stringify({
        notes: 'No resident claim after 30 days',
      }),
    });
    expect(result.reconciliation_status).toBe('UNIDENTIFIED');
  });

  it('fetches reconciliation summary KPIs', async () => {
    const mockSummary = {
      society_id: 'soc-1',
      total_credit_paise: 1000000,
      reconciliation_percentage: 85.5,
    };
    const requestSpy = vi.spyOn(apiClient, 'request').mockResolvedValue(mockSummary as any);

    const result = await reconciliationService.getSummary();
    expect(requestSpy).toHaveBeenCalledWith('/api/v1/reconciliation/summary');
    expect(result.reconciliation_percentage).toBe(85.5);
  });
});
