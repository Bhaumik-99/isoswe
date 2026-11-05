import React, { useState, useEffect } from 'react';
import {
  FileSpreadsheet,
  Download,
  ShieldCheck,
  AlertTriangle,
  RefreshCw,
} from 'lucide-react';
import { reconciliationService } from '../../../services/reconciliationService';
import {
  ReconciliationSummary,
  TransactionReconciliationStatus,
} from '../../../types/reconciliation';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/Card';
import { Badge } from '../../../components/ui/Badge';
import { Button } from '../../../components/ui/Button';
import { Alert } from '../../../components/ui/Alert';

export const ReconciliationReportsView: React.FC = () => {
  const [summary, setSummary] = useState<ReconciliationSummary | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isExporting, setIsExporting] = useState<boolean>(false);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [fromDate, setFromDate] = useState<string>('');
  const [toDate, setToDate] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  const fetchSummary = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await reconciliationService.getSummary();
      setSummary(data);
    } catch (err: unknown) {
      setError((err as Error).message || 'Failed to load report summary');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchSummary();
  }, []);

  const handleExportCsv = async () => {
    setIsExporting(true);
    try {
      const query = new URLSearchParams();
      if (statusFilter) query.append('status', statusFilter);
      if (fromDate) query.append('from_date', fromDate);
      if (toDate) query.append('to_date', toDate);

      const qs = query.toString() ? `?${query.toString()}` : '';
      const exportUrl = `${reconciliationService.getExportReportUrl()}${qs}`;

      // Trigger browser download via native anchor
      const link = document.createElement('a');
      link.href = exportUrl;
      link.setAttribute('download', `bank_reconciliation_report_${new Date().toISOString().slice(0, 10)}.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (err: unknown) {
      setError((err as Error).message || 'Failed to export CSV report');
    } finally {
      setIsExporting(false);
    }
  };

  const statusRows: Array<{
    status: TransactionReconciliationStatus;
    label: string;
    description: string;
    count: number;
    badgeVariant: 'neutral' | 'success' | 'warning' | 'info' | 'danger';
  }> = [
    {
      status: 'POSTED',
      label: 'Settled & Posted',
      description: 'Fully reconciled with resident maintenance invoices and posted to financial ledger',
      count: summary?.posted_count || 0,
      badgeVariant: 'success',
    },
    {
      status: 'PENDING_APPROVAL',
      label: 'Pending Approval',
      description: 'Match proposed by operator or engine, awaiting dual verification and settlement',
      count: summary?.pending_approval_count || 0,
      badgeVariant: 'warning',
    },
    {
      status: 'SUGGESTED',
      label: 'Algorithmic Suggestions',
      description: 'Potential matching invoices found based on UTR, amount, or resident clue',
      count: summary?.suggested_count || 0,
      badgeVariant: 'info',
    },
    {
      status: 'UNMATCHED',
      label: 'Unmatched Inflow',
      description: 'Bank credit received without identified resident or invoice reference',
      count: summary?.unmatched_count || 0,
      badgeVariant: 'danger',
    },
    {
      status: 'DUPLICATE',
      label: 'Duplicate / Ignored',
      description: 'Identical statement row previously ingested and fingerprinted',
      count: summary?.duplicate_count || 0,
      badgeVariant: 'neutral',
    },
    {
      status: 'UNIDENTIFIED',
      label: 'Suspense Account',
      description: 'Marked by staff as unidentified or mystery transaction for auditor review',
      count: summary?.unidentified_count || 0,
      badgeVariant: 'neutral',
    },
  ];

  return (
    <div className="space-y-6">
      {error && (
        <Alert variant="error">
          <AlertTriangle className="w-4 h-4 mr-2" />
          <span>{error}</span>
        </Alert>
      )}

      {/* Header & Export Controls */}
      <Card className="shadow-sm">
        <CardHeader className="pb-3">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div>
              <CardTitle className="text-base font-semibold text-gray-900 flex items-center gap-2">
                <FileSpreadsheet className="w-5 h-5 text-indigo-600" />
                Reconciliation Audit Reports & CSV Export
              </CardTitle>
              <p className="text-xs text-gray-500 mt-0.5">
                Generate financial compliance reports and export sanitized transaction logs
              </p>
            </div>
            <Button
              variant="primary"
              onClick={handleExportCsv}
              disabled={isExporting}
              className="flex items-center gap-2 shadow-sm"
            >
              <Download className="w-4 h-4" />
              {isExporting ? 'Exporting...' : 'Export Filtered CSV'}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="pt-2 border-t">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Status Filter</label>
              <select
                className="w-full border rounded-lg px-3 py-1.5 text-xs text-gray-800 bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
              >
                <option value="">All Statuses</option>
                <option value="POSTED">Settled & Posted</option>
                <option value="PENDING_APPROVAL">Pending Approval</option>
                <option value="SUGGESTED">Algorithmic Match</option>
                <option value="UNMATCHED">Unmatched</option>
                <option value="DUPLICATE">Duplicate</option>
                <option value="UNIDENTIFIED">Suspense Account</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">From Date</label>
              <input
                type="date"
                className="w-full border rounded-lg px-3 py-1.5 text-xs text-gray-800 bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
                value={fromDate}
                onChange={(e) => setFromDate(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">To Date</label>
              <input
                type="date"
                className="w-full border rounded-lg px-3 py-1.5 text-xs text-gray-800 bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
                value={toDate}
                onChange={(e) => setToDate(e.target.value)}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Reconciliation Status Breakdown */}
      <Card className="shadow-sm">
        <CardHeader className="border-b pb-3 flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-sm font-semibold text-gray-900">
              Transaction Reconciliation Breakdown
            </CardTitle>
            <p className="text-xs text-gray-500">Summary count of all imported bank statement entries</p>
          </div>
          <Button variant="ghost" size="sm" onClick={fetchSummary} disabled={isLoading} title="Refresh Breakdown">
            <RefreshCw className={`w-4 h-4 text-gray-500 ${isLoading ? 'animate-spin' : ''}`} />
          </Button>
        </CardHeader>
        <CardContent className="p-0">
          <div className="divide-y divide-gray-100">
            {statusRows.map((row) => (
              <div key={row.status} className="p-4 flex items-center justify-between hover:bg-gray-50 transition-colors">
                <div className="flex items-start gap-3">
                  <Badge variant={row.badgeVariant} className="mt-0.5">
                    {row.label}
                  </Badge>
                  <div>
                    <span className="text-xs font-medium text-gray-800">{row.status}</span>
                    <p className="text-xs text-gray-500 mt-0.5">{row.description}</p>
                  </div>
                </div>
                <div className="text-right font-semibold text-sm text-gray-900">
                  {row.count} <span className="text-xs font-normal text-gray-500">txns</span>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Financial Security & Audit Invariants */}
      <Card className="bg-slate-50 border shadow-sm">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold text-gray-900 flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-600" />
            Financial Audit & Ledger Integrity Guarantees
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-2 text-xs text-gray-600 space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="bg-white p-3 rounded-lg border">
              <span className="font-semibold text-gray-900 block mb-1">Dual-Entry Immutability</span>
              Ledger entries (`PAYMENT_RECEIVED`, `PAYMENT_ALLOCATED`) are append-only. No financial rows are ever updated or deleted.
            </div>
            <div className="bg-white p-3 rounded-lg border">
              <span className="font-semibold text-gray-900 block mb-1">Zero Double Posting</span>
              Matching against existing online gateway transactions marks them reconciled without creating duplicate `Payment` or ledger entries.
            </div>
            <div className="bg-white p-3 rounded-lg border">
              <span className="font-semibold text-gray-900 block mb-1">Formula Injection Safe</span>
              CSV report exports prefix formulas starting with `=`, `+`, `-`, or `@` with a single quote to prevent spreadsheet code execution.
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
