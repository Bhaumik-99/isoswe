import React, { useEffect, useState, useCallback } from 'react';
import {
  DollarSign,
  TrendingUp,
  AlertCircle,
  Clock,
  UploadCloud,
  ListFilter,
  FileSpreadsheet,
  RefreshCw,
  AlertTriangle,
} from 'lucide-react';
import { reconciliationService } from '../../../services/reconciliationService';
import {
  BankStatementImport,
  formatPaiseToINR,
  ReconciliationSummary,
  StatementImportStatus,
} from '../../../types/reconciliation';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/Card';
import { Badge } from '../../../components/ui/Badge';
import { Button } from '../../../components/ui/Button';
import { Skeleton } from '../../../components/ui/Skeleton';
import { Alert } from '../../../components/ui/Alert';

interface ReconciliationOverviewProps {
  onNavigateTab: (tab: 'upload' | 'queue' | 'transactions' | 'reports') => void;
}

function getImportStatusBadge(status: StatementImportStatus): {
  label: string;
  variant: 'neutral' | 'success' | 'warning' | 'info' | 'danger';
} {
  switch (status) {
    case 'COMPLETED':
      return { label: 'Completed', variant: 'success' };
    case 'COMPLETED_WITH_ERRORS':
      return { label: 'Completed with Errors', variant: 'warning' };
    case 'PROCESSING':
    case 'VALIDATING':
      return { label: 'Processing', variant: 'info' };
    case 'READY_FOR_IMPORT':
    case 'UPLOADED':
      return { label: 'Ready', variant: 'info' };
    case 'FAILED':
      return { label: 'Failed', variant: 'danger' };
    case 'CANCELLED':
      return { label: 'Cancelled', variant: 'neutral' };
    default:
      return { label: status, variant: 'neutral' };
  }
}

export const ReconciliationOverview: React.FC<ReconciliationOverviewProps> = ({
  onNavigateTab,
}) => {
  const [summary, setSummary] = useState<ReconciliationSummary | null>(null);
  const [imports, setImports] = useState<BankStatementImport[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [sumData, impData] = await Promise.all([
        reconciliationService.getSummary(),
        reconciliationService.listImports(),
      ]);
      setSummary(sumData);
      setImports(impData);
    } catch (err: unknown) {
      setError((err as Error).message || 'Failed to load reconciliation overview data');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <Card key={i}>
              <CardContent className="p-6">
                <Skeleton className="h-4 w-24 mb-2" />
                <Skeleton className="h-8 w-36 mb-4" />
                <Skeleton className="h-4 w-48" />
              </CardContent>
            </Card>
          ))}
        </div>
        <Card>
          <CardContent className="p-6">
            <Skeleton className="h-6 w-48 mb-4" />
            <Skeleton className="h-24 w-full" />
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {error && (
        <Alert variant="error">
          <AlertCircle className="w-4 h-4 mr-2" />
          <span>{error}</span>
          <Button
            size="sm"
            variant="secondary"
            onClick={fetchData}
            className="ml-auto"
          >
            Retry
          </Button>
        </Alert>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Bank Credits */}
        <Card className="border-l-4 border-l-blue-500 shadow-sm">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Total Credits Processed
              </span>
              <DollarSign className="w-5 h-5 text-blue-500" />
            </div>
            <div className="mt-2 text-2xl font-bold text-gray-900">
              {formatPaiseToINR(summary?.total_credit_paise || 0)}
            </div>
            <p className="mt-1 text-xs text-gray-500">
              {summary?.total_transactions || 0} total transactions imported
            </p>
          </CardContent>
        </Card>

        {/* Reconciled & Posted */}
        <Card className="border-l-4 border-l-green-500 shadow-sm">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Reconciled & Posted
              </span>
              <TrendingUp className="w-5 h-5 text-green-500" />
            </div>
            <div className="mt-2 text-2xl font-bold text-green-700">
              {formatPaiseToINR(summary?.reconciled_credit_paise || 0)}
            </div>
            <div className="mt-2 flex items-center justify-between text-xs text-gray-600">
              <span>{summary?.reconciliation_percentage ?? 0}% completed</span>
              <Badge variant="success">{summary?.posted_count || 0} posted</Badge>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-1.5 mt-2">
              <div
                className="bg-green-600 h-1.5 rounded-full transition-all duration-300"
                style={{ width: `${Math.min(100, summary?.reconciliation_percentage || 0)}%` }}
              />
            </div>
          </CardContent>
        </Card>

        {/* Pending Review & Approval */}
        <Card className="border-l-4 border-l-amber-500 shadow-sm">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Pending Review
              </span>
              <Clock className="w-5 h-5 text-amber-500" />
            </div>
            <div className="mt-2 text-2xl font-bold text-amber-700">
              {formatPaiseToINR(summary?.pending_approval_credit_paise || 0)}
            </div>
            <div className="mt-1 flex items-center justify-between text-xs text-gray-500">
              <span>{(summary?.suggested_count || 0) + (summary?.pending_approval_count || 0)} transactions</span>
              <Button
                variant="ghost"
                size="sm"
                className="text-amber-700 hover:text-amber-800 p-0 text-xs"
                onClick={() => onNavigateTab('queue')}
              >
                Review &rarr;
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Unmatched / Suspense */}
        <Card className="border-l-4 border-l-red-500 shadow-sm">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Unmatched & Suspense
              </span>
              <AlertTriangle className="w-5 h-5 text-red-500" />
            </div>
            <div className="mt-2 text-2xl font-bold text-red-700">
              {formatPaiseToINR(summary?.unmatched_credit_paise || 0)}
            </div>
            <p className="mt-1 text-xs text-gray-500">
              {summary?.unmatched_count || 0} unmatched &bull; {summary?.duplicate_count || 0} duplicates
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Quick Operations Bar */}
      <Card className="bg-gradient-to-r from-slate-50 to-gray-50 border shadow-sm">
        <CardContent className="p-4 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h3 className="font-semibold text-gray-900 text-sm">Quick Financial Operations</h3>
            <p className="text-xs text-gray-500">
              Upload statements, match bank credits with pending invoices, or inspect settled transfers.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="primary"
              size="sm"
              onClick={() => onNavigateTab('upload')}
              className="flex items-center gap-1.5 shadow-sm"
            >
              <UploadCloud className="w-4 h-4" />
              Upload Bank CSV
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => onNavigateTab('queue')}
              className="flex items-center gap-1.5"
            >
              <ListFilter className="w-4 h-4" />
              Manual Review Queue
              {((summary?.suggested_count || 0) + (summary?.pending_approval_count || 0)) > 0 && (
                <span className="ml-1 px-1.5 py-0.5 text-xs font-bold bg-amber-100 text-amber-800 rounded-full">
                  {(summary?.suggested_count || 0) + (summary?.pending_approval_count || 0)}
                </span>
              )}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => onNavigateTab('reports')}
              className="flex items-center gap-1.5"
            >
              <FileSpreadsheet className="w-4 h-4" />
              Reports & Audit
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={fetchData}
              title="Refresh Data"
              className="p-2"
            >
              <RefreshCw className="w-4 h-4 text-gray-600" />
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Statement Imports History */}
      <Card className="shadow-sm">
        <CardHeader className="flex flex-row items-center justify-between border-b pb-4">
          <div>
            <CardTitle className="text-base font-semibold text-gray-900">
              Recent Bank Statement Imports
            </CardTitle>
            <p className="text-xs text-gray-500 mt-0.5">
              History of uploaded files, checksums, and parsing results
            </p>
          </div>
          <Badge variant="neutral">{imports.length} Total</Badge>
        </CardHeader>
        <CardContent className="p-0">
          {imports.length === 0 ? (
            <div className="text-center py-12 px-4">
              <UploadCloud className="w-12 h-12 text-gray-300 mx-auto mb-3" />
              <h4 className="text-sm font-semibold text-gray-700">No bank statements uploaded yet</h4>
              <p className="text-xs text-gray-500 max-w-md mx-auto mt-1 mb-4">
                Upload society bank statements in CSV format to trigger automatic matching against outstanding resident invoices.
              </p>
              <Button size="sm" variant="primary" onClick={() => onNavigateTab('upload')}>
                Upload First Statement
              </Button>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-gray-700">
                <thead className="bg-gray-50 text-gray-600 uppercase font-semibold border-b">
                  <tr>
                    <th className="py-3 px-4">File Name / Bank</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4 text-right">Total Rows</th>
                    <th className="py-3 px-4 text-right">Imported</th>
                    <th className="py-3 px-4 text-right">Duplicates</th>
                    <th className="py-3 px-4 text-right">Rejected</th>
                    <th className="py-3 px-4">Uploaded At</th>
                    <th className="py-3 px-4">Checksum</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {imports.map((item) => {
                    const statusMeta = getImportStatusBadge(item.status);
                    return (
                      <tr key={item.id} className="hover:bg-gray-50 transition-colors">
                        <td className="py-3 px-4 font-medium text-gray-900">
                          <div>{item.file_name}</div>
                          {item.bank_name && (
                            <span className="text-[11px] text-gray-500">{item.bank_name}</span>
                          )}
                        </td>
                        <td className="py-3 px-4">
                          <Badge variant={statusMeta.variant}>{statusMeta.label}</Badge>
                        </td>
                        <td className="py-3 px-4 text-right font-medium">{item.total_rows}</td>
                        <td className="py-3 px-4 text-right text-green-700 font-medium">
                          {item.imported_rows}
                        </td>
                        <td className="py-3 px-4 text-right text-amber-700 font-medium">
                          {item.duplicate_rows}
                        </td>
                        <td className="py-3 px-4 text-right text-red-600 font-medium">
                          {item.rejected_rows}
                        </td>
                        <td className="py-3 px-4 text-gray-500">
                          {new Date(item.created_at).toLocaleString('en-IN', {
                            dateStyle: 'short',
                            timeStyle: 'short',
                          })}
                        </td>
                        <td className="py-3 px-4 font-mono text-[10px] text-gray-400">
                          {item.file_checksum.substring(0, 10)}...
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};
