import React, { useState } from 'react';
import { AlertCircle, CheckCircle2, ShieldCheck, X } from 'lucide-react';
import { BankTransaction, formatPaiseToINR, ProposedAllocation } from '../../../types/reconciliation';
import { reconciliationService } from '../../../services/reconciliationService';
import { Alert } from '../../../components/ui/Alert';
import { Portal } from '../../../components/ui/Portal';

interface ApprovalModalProps {
  transaction: BankTransaction;
  onClose: () => void;
  onApproved: (updatedTxn: BankTransaction) => void;
}

export const ApprovalModal: React.FC<ApprovalModalProps> = ({
  transaction,
  onClose,
  onApproved,
}) => {
  const selectedMatch = transaction.matches.find((m) => m.is_selected) || transaction.matches[0];
  const invoiceId = selectedMatch?.invoice_id || '';
  const [allocationAmountPaise, setAllocationAmountPaise] = useState<number>(
    selectedMatch?.invoice_outstanding_paise
      ? Math.min(transaction.credit_paise - transaction.allocated_paise, selectedMatch.invoice_outstanding_paise)
      : transaction.credit_paise - transaction.allocated_paise
  );
  const [notes, setNotes] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const availableCredit = transaction.credit_paise - transaction.allocated_paise;
  const targetInvoice = selectedMatch?.invoice_id === invoiceId ? selectedMatch : null;
  const currentOutstanding = targetInvoice?.invoice_outstanding_paise || allocationAmountPaise;
  const balanceAfterAllocation = Math.max(0, currentOutstanding - allocationAmountPaise);
  const unallocatedRemainder = Math.max(0, availableCredit - allocationAmountPaise);

  const handleApprove = async () => {
    if (!invoiceId) {
      setError('Please select or specify an invoice ID for allocation');
      return;
    }
    if (allocationAmountPaise <= 0) {
      setError('Allocation amount must be greater than zero');
      return;
    }
    if (allocationAmountPaise > availableCredit) {
      setError(`Allocation exceeds available bank credit (${formatPaiseToINR(availableCredit)})`);
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const idempotencyKey = 'appr-' + Math.random().toString(36).substring(2, 10) + '-' + Date.now();
      const allocations: ProposedAllocation[] = [
        {
          invoice_id: invoiceId,
          allocated_paise: allocationAmountPaise,
        },
      ];

      const res = await reconciliationService.approveAndAllocate(
        transaction.id,
        allocations,
        idempotencyKey,
        notes
      );
      onApproved(res);
      onClose();
    } catch (err: unknown) {
      setError((err as Error).message || 'Failed to approve and post allocation');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Portal>
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full border border-slate-200 overflow-hidden">
        {/* Header */}
        <div className="bg-slate-900 px-6 py-4 flex items-center justify-between text-white">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-emerald-400" />
            <h3 className="font-semibold text-lg">Financial Settlement Approval</h3>
          </div>
          <button
            onClick={onClose}
            disabled={isSubmitting}
            className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {error && <Alert variant="error" title="Allocation Error">{error}</Alert>}

          {/* Bank Transaction Overview */}
          <div className="bg-slate-50 rounded-lg p-4 border border-slate-200">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Source Bank Transaction
            </span>
            <div className="mt-2 grid grid-cols-2 gap-4">
              <div>
                <span className="text-xs text-slate-500 block">Bank Credit Received</span>
                <span className="text-xl font-bold text-emerald-700">
                  {formatPaiseToINR(transaction.credit_paise)}
                </span>
              </div>
              <div>
                <span className="text-xs text-slate-500 block">Reference / UTR</span>
                <span className="text-sm font-mono font-medium text-slate-800">
                  {transaction.utr_number || transaction.reference_number || 'None'}
                </span>
              </div>
              <div className="col-span-2">
                <span className="text-xs text-slate-500 block">Narration</span>
                <span className="text-xs font-medium text-slate-700 bg-white p-2 rounded border border-slate-200 block truncate">
                  {transaction.description}
                </span>
              </div>
            </div>
          </div>

          {/* Allocation Proposal */}
          <div className="border border-slate-200 rounded-lg p-4 space-y-4">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500 block">
              Settlement Target
            </span>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <span className="text-xs text-slate-500 block">Apartment & Resident</span>
                <span className="text-sm font-semibold text-slate-900 block">
                  {selectedMatch?.flat_number || 'Custom Selection'}
                </span>
                <span className="text-xs text-slate-600">
                  {selectedMatch?.resident_name || 'Resident not verified'}
                </span>
              </div>

              <div>
                <span className="text-xs text-slate-500 block">Invoice Number</span>
                <span className="text-sm font-mono font-semibold text-indigo-700 block">
                  {selectedMatch?.invoice_number || 'Manual Invoice'}
                </span>
                <span className="text-xs text-slate-500">
                  Current Outstanding: {formatPaiseToINR(currentOutstanding)}
                </span>
              </div>
            </div>

            {/* Allocation Amount Input */}
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">
                Amount to Allocate (INR)
              </label>
              <div className="relative">
                <span className="absolute left-3 top-2.5 text-slate-500 font-semibold">₹</span>
                <input
                  type="number"
                  step="0.01"
                  max={availableCredit / 100}
                  value={allocationAmountPaise / 100}
                  onChange={(e) => {
                    const inr = parseFloat(e.target.value) || 0;
                    setAllocationAmountPaise(Math.round(inr * 100));
                  }}
                  className="w-full pl-8 pr-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 font-semibold text-slate-900"
                />
              </div>
            </div>

            {/* Financial Ledger Impact Preview */}
            <div className="bg-indigo-50/70 border border-indigo-100 rounded-lg p-3 text-xs space-y-2">
              <div className="flex justify-between font-medium">
                <span className="text-slate-600">Invoice Outstanding Before:</span>
                <span className="text-slate-900">{formatPaiseToINR(currentOutstanding)}</span>
              </div>
              <div className="flex justify-between font-medium text-indigo-700">
                <span>Proposed Allocation Credit:</span>
                <span>- {formatPaiseToINR(allocationAmountPaise)}</span>
              </div>
              <div className="flex justify-between font-bold border-t border-indigo-200 pt-1 text-slate-900">
                <span>Invoice Balance After Posting:</span>
                <span className={balanceAfterAllocation === 0 ? 'text-emerald-700' : 'text-amber-700'}>
                  {formatPaiseToINR(balanceAfterAllocation)} {balanceAfterAllocation === 0 ? '(PAID)' : '(PARTIALLY PAID)'}
                </span>
              </div>
              {unallocatedRemainder > 0 && (
                <div className="flex justify-between text-amber-800 border-t border-indigo-200 pt-1">
                  <span>Unallocated Bank Credit Remainder:</span>
                  <span>{formatPaiseToINR(unallocatedRemainder)}</span>
                </div>
              )}
            </div>

            {/* Review Notes */}
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">
                Audit Review Notes (Optional)
              </label>
              <textarea
                rows={2}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Add audit rationale or transaction reference verification details..."
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-xs focus:ring-2 focus:ring-indigo-500"
              />
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs text-slate-500 bg-slate-50 p-3 rounded-lg border border-slate-200">
            <AlertCircle className="h-4 w-4 text-slate-400 shrink-0" />
            <span>
              This operation executes atomic double-entry ledger postings and is permanent. Corrections require compensating reversal entries.
            </span>
          </div>
        </div>

        {/* Footer */}
        <div className="bg-slate-50 px-6 py-4 flex items-center justify-end gap-3 border-t border-slate-200">
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            className="px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-200 rounded-lg transition"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleApprove}
            disabled={isSubmitting || allocationAmountPaise <= 0}
            className="px-5 py-2 text-sm font-semibold text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg shadow transition flex items-center gap-2 disabled:opacity-50"
          >
            {isSubmitting ? (
              'Posting Settlement...'
            ) : (
              <>
                <CheckCircle2 className="h-4 w-4" />
                Approve & Post Settlement
              </>
            )}
          </button>
        </div>
      </div>
      </div>
    </Portal>
  );
};
