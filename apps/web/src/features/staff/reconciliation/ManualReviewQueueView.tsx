import React, { useState, useEffect, useCallback } from 'react';
import {
  CheckCircle,
  HelpCircle,
  RefreshCw,
  ThumbsDown,
  UserCheck,
} from 'lucide-react';
import { reconciliationService } from '../../../services/reconciliationService';
import {
  BankTransaction,
  formatPaiseToINR,
  ManualReviewQueueItem,
} from '../../../types/reconciliation';
import { ApprovalModal } from './ApprovalModal';
import { Alert } from '../../../components/ui/Alert';

export const ManualReviewQueueView: React.FC = () => {
  const [category, setCategory] = useState<string>('ALL');
  const [items, setItems] = useState<ManualReviewQueueItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [selectedTxnForApproval, setSelectedTxnForApproval] = useState<BankTransaction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  const fetchQueue = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await reconciliationService.getReviewQueue(category);
      setItems(data);
    } catch (err: unknown) {
      setError((err as Error).message || 'Failed to load reconciliation review queue');
    } finally {
      setIsLoading(false);
    }
  }, [category]);

  useEffect(() => {
    fetchQueue();
  }, [fetchQueue]);

  const handleReject = async (transactionId: string) => {
    const reason = prompt('Please enter the reason for rejecting this match:');
    if (!reason) return;

    try {
      await reconciliationService.rejectMatch(transactionId, reason);
      setActionSuccess('Match rejected successfully.');
      fetchQueue();
    } catch (err: unknown) {
      setError((err as Error).message || 'Failed to reject match');
    }
  };

  const handleMarkUnidentified = async (transactionId: string) => {
    const notes = prompt('Enter notes for unidentified credit (suspense account):');
    if (!notes) return;

    try {
      await reconciliationService.markUnidentified(transactionId, notes);
      setActionSuccess('Transaction marked as unidentified suspense credit.');
      fetchQueue();
    } catch (err: unknown) {
      setError((err as Error).message || 'Failed to mark unidentified');
    }
  };

  const handleApprovalSuccess = () => {
    setActionSuccess('Settlement successfully approved and posted to financial ledger!');
    fetchQueue();
  };

  return (
    <div className="space-y-6">
      {error && <Alert variant="error" title="Queue Error">{error}</Alert>}
      {actionSuccess && <Alert variant="success" title="Action Completed">{actionSuccess}</Alert>}

      {/* Header & Category Tabs */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <h2 className="text-lg font-bold text-slate-900">Manual Reconciliation Review Queue</h2>
            <p className="text-sm text-slate-500 mt-0.5">
              Review and approve deterministic candidate matches, split allocations, or resolve suspense credits.
            </p>
          </div>
          <button
            onClick={fetchQueue}
            disabled={isLoading}
            className="px-3 py-1.5 border border-slate-300 hover:bg-slate-50 text-slate-700 text-xs font-semibold rounded-lg flex items-center gap-1.5 transition"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh Queue
          </button>
        </div>

        {/* Filter Pills */}
        <div className="flex flex-wrap gap-2 mt-6 border-b border-slate-200 pb-4">
          {[
            { id: 'ALL', label: 'All Items' },
            { id: 'SUGGESTED', label: 'High/Medium Confidence Matches' },
            { id: 'PENDING_APPROVAL', label: 'Pending Approval' },
            { id: 'UNMATCHED', label: 'Unmatched Transactions' },
            { id: 'DUPLICATE_REVIEW', label: 'Duplicate Review' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setCategory(tab.id)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                category === tab.id
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'bg-slate-100 hover:bg-slate-200 text-slate-600'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* List of Queue Items */}
        {isLoading ? (
          <div className="p-12 text-center text-slate-400 flex flex-col items-center justify-center gap-2">
            <RefreshCw className="h-6 w-6 animate-spin text-indigo-500" />
            <span className="text-sm">Loading review queue transactions...</span>
          </div>
        ) : items.length === 0 ? (
          <div className="p-12 text-center text-slate-500 space-y-2">
            <CheckCircle className="h-10 w-10 text-emerald-500 mx-auto" />
            <span className="font-semibold text-slate-800 block text-base">
              No transactions in this queue category
            </span>
            <span className="text-xs text-slate-400 block">
              All transactions for this filter have been reconciled or moved to another state.
            </span>
          </div>
        ) : (
          <div className="mt-6 space-y-4">
            {items.map((item) => {
              const tx = item.transaction;
              const match = item.suggested_match;
              const isPosted = tx.reconciliation_status === 'POSTED';
              const unallocated = tx.credit_paise - tx.allocated_paise;

              return (
                <div
                  key={tx.id}
                  className="border border-slate-200 rounded-xl p-5 hover:border-slate-300 transition bg-white shadow-sm space-y-4"
                >
                  {/* Top Bar: Date, Reference, Amount */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-3">
                    <div className="flex items-center gap-3">
                      <span className="text-xs font-semibold text-slate-500">
                        {new Date(tx.transaction_date).toLocaleDateString('en-IN', {
                          day: '2-digit',
                          month: 'short',
                          year: 'numeric',
                        })}
                      </span>
                      <span className="text-xs font-mono font-medium px-2 py-0.5 bg-slate-100 text-slate-700 rounded">
                        {tx.utr_number || tx.reference_number || 'No UTR Reference'}
                      </span>
                      <span
                        className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wider ${
                          tx.reconciliation_status === 'POSTED'
                            ? 'bg-emerald-100 text-emerald-800'
                            : tx.reconciliation_status === 'SUGGESTED'
                            ? 'bg-indigo-100 text-indigo-800'
                            : tx.reconciliation_status === 'PENDING_APPROVAL'
                            ? 'bg-amber-100 text-amber-800'
                            : tx.reconciliation_status === 'DUPLICATE'
                            ? 'bg-rose-100 text-rose-800'
                            : 'bg-slate-100 text-slate-700'
                        }`}
                      >
                        {tx.reconciliation_status.replace('_', ' ')}
                      </span>
                    </div>

                    <div className="text-right">
                      <span className="text-lg font-bold text-slate-900 block leading-tight">
                        {formatPaiseToINR(tx.credit_paise)}
                      </span>
                      {tx.allocated_paise > 0 && (
                        <span className="text-xs text-slate-500">
                          Allocated: {formatPaiseToINR(tx.allocated_paise)} • Remainder:{' '}
                          {formatPaiseToINR(unallocated)}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Narration */}
                  <div className="text-xs text-slate-700 bg-slate-50 p-2.5 rounded-lg border border-slate-100 font-mono">
                    {tx.description}
                  </div>

                  {/* Candidate Match Suggestion Card */}
                  {match ? (
                    <div className="bg-indigo-50/50 border border-indigo-100 rounded-lg p-4 space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <UserCheck className="h-4 w-4 text-indigo-600" />
                          <span className="text-xs font-bold text-indigo-950 uppercase tracking-wider">
                            Suggested Match ({match.matching_level.replace(/_/g, ' ')})
                          </span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <span
                            className={`text-xs font-bold px-2 py-0.5 rounded-full ${
                              match.confidence_score >= 90
                                ? 'bg-emerald-100 text-emerald-800'
                                : match.confidence_score >= 70
                                ? 'bg-blue-100 text-blue-800'
                                : 'bg-amber-100 text-amber-800'
                            }`}
                          >
                            Confidence: {Math.round(match.confidence_score)}%
                          </span>
                        </div>
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs pt-1">
                        <div>
                          <span className="text-slate-500 block">Flat / Resident:</span>
                          <span className="font-semibold text-slate-900">
                            {match.flat_number || 'Unknown Unit'} • {match.resident_name || 'Resident'}
                          </span>
                        </div>
                        <div>
                          <span className="text-slate-500 block">Invoice Reference:</span>
                          <span className="font-semibold text-slate-900">
                            {match.invoice_number || 'Direct Transfer'}
                          </span>
                        </div>
                        <div>
                          <span className="text-slate-500 block">Invoice Outstanding:</span>
                          <span className="font-semibold text-slate-900">
                            {match.invoice_outstanding_paise !== null && match.invoice_outstanding_paise !== undefined
                              ? formatPaiseToINR(match.invoice_outstanding_paise)
                              : '—'}
                          </span>
                        </div>
                      </div>

                      <p className="text-xs text-slate-600 pt-1 border-t border-indigo-100/70">
                        {match.explanation}
                      </p>
                    </div>
                  ) : (
                    <div className="bg-amber-50/60 border border-amber-200 rounded-lg p-3 text-xs text-amber-800 flex items-center gap-2">
                      <HelpCircle className="h-4 w-4 text-amber-600 shrink-0" />
                      <span>
                        No high-confidence match found. Narration does not match known resident UTR or unit number. Manual assignment required.
                      </span>
                    </div>
                  )}

                  {/* Action Buttons */}
                  {!isPosted && (
                    <div className="flex items-center justify-end gap-2 pt-2">
                      <button
                        onClick={() => handleMarkUnidentified(tx.id)}
                        className="px-3 py-1.5 border border-slate-300 hover:bg-slate-50 text-slate-700 text-xs font-medium rounded-lg transition"
                      >
                        Mark Unidentified
                      </button>
                      {match && (
                        <button
                          onClick={() => handleReject(tx.id)}
                          className="px-3 py-1.5 border border-rose-300 hover:bg-rose-50 text-rose-700 text-xs font-medium rounded-lg transition flex items-center gap-1"
                        >
                          <ThumbsDown className="h-3 w-3" />
                          Reject Suggestion
                        </button>
                      )}
                      <button
                        onClick={() => setSelectedTxnForApproval(tx)}
                        className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold rounded-lg shadow-sm transition flex items-center gap-1.5"
                      >
                        <CheckCircle className="h-3.5 w-3.5" />
                        Approve Settlement
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Settlement Approval Modal */}
      {selectedTxnForApproval && (
        <ApprovalModal
          transaction={selectedTxnForApproval}
          onClose={() => setSelectedTxnForApproval(null)}
          onApproved={handleApprovalSuccess}
        />
      )}
    </div>
  );
};
