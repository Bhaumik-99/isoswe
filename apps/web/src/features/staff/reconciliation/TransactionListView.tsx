import React, { useState, useEffect, useCallback } from 'react';
import {
  Search,
  RefreshCw,
  ArrowDownLeft,
  ArrowUpRight,
  Eye,
} from 'lucide-react';
import { reconciliationService } from '../../../services/reconciliationService';
import {
  BankTransaction,
  formatPaiseToINR,
  TransactionReconciliationStatus,
  TransactionType,
} from '../../../types/reconciliation';
import { ApprovalModal } from './ApprovalModal';

export const TransactionListView: React.FC = () => {
  const [transactions, setTransactions] = useState<BankTransaction[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [search, setSearch] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<TransactionReconciliationStatus | ''>('');
  const [typeFilter, setTypeFilter] = useState<TransactionType | ''>('');
  const [selectedTxn, setSelectedTxn] = useState<BankTransaction | null>(null);

  const fetchTransactions = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await reconciliationService.listTransactions({
        status: statusFilter || undefined,
        transactionType: typeFilter || undefined,
        search: search.trim() || undefined,
        limit: 100,
      });
      setTransactions(data);
    } catch (err: unknown) {
      console.error('Failed to load transactions:', err);
    } finally {
      setIsLoading(false);
    }
  }, [statusFilter, typeFilter, search]);

  useEffect(() => {
    fetchTransactions();
  }, [fetchTransactions]);

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden space-y-4 p-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Bank Statement Transactions</h2>
          <p className="text-sm text-slate-500">
            Browse all parsed credit and debit line items, verify fingerprints, and inspect reconciliation allocations.
          </p>
        </div>
        <button
          onClick={fetchTransactions}
          disabled={isLoading}
          className="px-3 py-1.5 border border-slate-300 hover:bg-slate-50 text-slate-700 text-xs font-semibold rounded-lg flex items-center gap-1.5 transition"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2">
        <div className="relative">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search description, UTR, reference..."
            className="w-full pl-9 pr-3 py-2 border border-slate-300 rounded-lg text-xs focus:ring-2 focus:ring-indigo-500"
          />
        </div>

        <div>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as TransactionReconciliationStatus | '')}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-xs bg-white focus:ring-2 focus:ring-indigo-500"
          >
            <option value="">All Reconciliation Statuses</option>
            <option value="UNMATCHED">Unmatched</option>
            <option value="SUGGESTED">Suggested Match</option>
            <option value="PENDING_APPROVAL">Pending Approval</option>
            <option value="POSTED">Posted / Reconciled</option>
            <option value="DUPLICATE">Duplicate</option>
            <option value="UNIDENTIFIED">Unidentified / Suspense</option>
            <option value="REJECTED">Rejected</option>
          </select>
        </div>

        <div>
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value as TransactionType | '')}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-xs bg-white focus:ring-2 focus:ring-indigo-500"
          >
            <option value="">All Transaction Types</option>
            <option value="CREDIT">Credits (Incoming)</option>
            <option value="DEBIT">Debits (Outgoing)</option>
          </select>
        </div>
      </div>

      {/* Transactions Table */}
      {isLoading ? (
        <div className="py-12 text-center text-slate-400 flex flex-col items-center justify-center gap-2">
          <RefreshCw className="h-6 w-6 animate-spin text-indigo-500" />
          <span className="text-xs">Loading statement transactions...</span>
        </div>
      ) : transactions.length === 0 ? (
        <div className="py-12 text-center text-slate-500 text-sm">
          No transactions found matching your filters.
        </div>
      ) : (
        <div className="border border-slate-200 rounded-lg overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-600 border-b border-slate-200 font-semibold">
              <tr>
                <th className="py-2.5 px-3">Date</th>
                <th className="py-2.5 px-3">Description</th>
                <th className="py-2.5 px-3">Reference / UTR</th>
                <th className="py-2.5 px-3">Type</th>
                <th className="py-2.5 px-3 text-right">Amount</th>
                <th className="py-2.5 px-3">Recon Status</th>
                <th className="py-2.5 px-3 text-right">Allocated</th>
                <th className="py-2.5 px-3 text-center">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {transactions.map((tx) => (
                <tr key={tx.id} className="hover:bg-slate-50/80 transition">
                  <td className="py-2.5 px-3 font-medium text-slate-800 whitespace-nowrap">
                    {new Date(tx.transaction_date).toLocaleDateString('en-IN', {
                      day: '2-digit',
                      month: 'short',
                      year: 'numeric',
                    })}
                  </td>
                  <td className="py-2.5 px-3 max-w-xs truncate text-slate-700" title={tx.description}>
                    {tx.description}
                  </td>
                  <td className="py-2.5 px-3 font-mono text-slate-600">
                    {tx.utr_number || tx.reference_number || '—'}
                  </td>
                  <td className="py-2.5 px-3">
                    <span
                      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded font-semibold text-[10px] ${
                        tx.transaction_type === 'CREDIT'
                          ? 'bg-emerald-100 text-emerald-800'
                          : 'bg-rose-100 text-rose-800'
                      }`}
                    >
                      {tx.transaction_type === 'CREDIT' ? (
                        <ArrowDownLeft className="h-3 w-3" />
                      ) : (
                        <ArrowUpRight className="h-3 w-3" />
                      )}
                      {tx.transaction_type}
                    </span>
                  </td>
                  <td
                    className={`py-2.5 px-3 text-right font-semibold whitespace-nowrap ${
                      tx.transaction_type === 'CREDIT' ? 'text-emerald-700' : 'text-rose-700'
                    }`}
                  >
                    {tx.transaction_type === 'CREDIT'
                      ? formatPaiseToINR(tx.credit_paise)
                      : formatPaiseToINR(tx.debit_paise)}
                  </td>
                  <td className="py-2.5 px-3">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
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
                      {tx.reconciliation_status.replace(/_/g, ' ')}
                    </span>
                  </td>
                  <td className="py-2.5 px-3 text-right text-slate-600 font-mono">
                    {tx.allocated_paise > 0 ? formatPaiseToINR(tx.allocated_paise) : '—'}
                  </td>
                  <td className="py-2.5 px-3 text-center">
                    {tx.transaction_type === 'CREDIT' && tx.reconciliation_status !== 'POSTED' && (
                      <button
                        onClick={() => setSelectedTxn(tx)}
                        className="p-1 text-indigo-600 hover:text-indigo-800 hover:bg-indigo-50 rounded"
                        title="Approve Settlement"
                      >
                        <Eye className="h-4 w-4" />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selectedTxn && (
        <ApprovalModal
          transaction={selectedTxn}
          onClose={() => setSelectedTxn(null)}
          onApproved={() => {
            fetchTransactions();
          }}
        />
      )}
    </div>
  );
};
