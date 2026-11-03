import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  FileText,
  DollarSign,
  TrendingUp,
  AlertTriangle,
  Play,
  Eye,
  CheckCircle2,
  X,
  Search,
} from 'lucide-react';
import { billingService, formatINR, formatDateIST } from '../../services/billingService';
import { BillingRun, BillingRunPreview, Invoice, InvoiceStatus } from '../../types/billing';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Skeleton } from '../../components/ui/Skeleton';
import { Alert } from '../../components/ui/Alert';

export const StaffBilling: React.FC = () => {
  const queryClient = useQueryClient();

  // Filters
  const [selectedPeriod, setSelectedPeriod] = useState<string>('2026-11');
  const [selectedTower, setSelectedTower] = useState<string>('');
  const [flatSearch, setFlatSearch] = useState<string>('');
  const [selectedStatus, setSelectedStatus] = useState<string>('');
  const [currentPage, setCurrentPage] = useState<number>(1);
  const PAGE_SIZE = 25;

  // Modals & Run State
  const [isRunModalOpen, setIsRunModalOpen] = useState<boolean>(false);
  const [runPeriod, setRunPeriod] = useState<string>('2026-11');
  const [previewResult, setPreviewResult] = useState<BillingRunPreview | null>(null);
  const [executionResult, setExecutionResult] = useState<BillingRun | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [selectedInvoiceDetail, setSelectedInvoiceDetail] = useState<Invoice | null>(null);

  // Queries
  const {
    data: overview,
    isLoading: isOverviewLoading,
    error: overviewError,
  } = useQuery({
    queryKey: ['staff-billing-overview'],
    queryFn: billingService.getStaffOverview,
  });

  const {
    data: invoices,
    isLoading: isInvoicesLoading,
    error: invoicesError,
  } = useQuery({
    queryKey: ['staff-invoices', selectedPeriod, selectedTower, flatSearch, selectedStatus, currentPage],
    queryFn: () =>
      billingService.getStaffInvoices({
        billing_period: selectedPeriod || undefined,
        tower_number: selectedTower || undefined,
        flat_number: flatSearch || undefined,
        status: selectedStatus || undefined,
        limit: PAGE_SIZE,
        offset: (currentPage - 1) * PAGE_SIZE,
      }),
  });

  // Mutations
  const previewMutation = useMutation({
    mutationFn: (period: string) => billingService.previewBillingRun(period),
    onSuccess: (data) => {
      setPreviewResult(data);
      setRunError(null);
    },
    onError: (err: any) => {
      setRunError(err?.message || 'Failed to preview billing run');
    },
  });

  const executeMutation = useMutation({
    mutationFn: (period: string) => billingService.executeBillingRun(period),
    onSuccess: (run) => {
      setExecutionResult(run);
      setPreviewResult(null);
      setRunError(null);
      queryClient.invalidateQueries({ queryKey: ['staff-billing-overview'] });
      queryClient.invalidateQueries({ queryKey: ['staff-invoices'] });
    },
    onError: (err: any) => {
      setRunError(err?.message || 'Failed to execute billing run');
    },
  });

  const handleOpenRunModal = () => {
    setIsRunModalOpen(true);
    setPreviewResult(null);
    setExecutionResult(null);
    setRunError(null);
  };

  const getStatusBadge = (status: InvoiceStatus, isOverdue: boolean) => {
    if (status === 'PAID') return <Badge variant="success">PAID</Badge>;
    if (status === 'OVERDUE' || isOverdue) return <Badge variant="danger">OVERDUE</Badge>;
    if (status === 'PARTIALLY_PAID') return <Badge variant="info">PARTIALLY PAID</Badge>;
    if (status === 'VOID') return <Badge variant="neutral">VOID</Badge>;
    return <Badge variant="warning">UNPAID</Badge>;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-200">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Society Billing & Finance Dashboard</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Marvel Greenfield Residences • Society-scoped maintenance operations & ledger management
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="primary" onClick={handleOpenRunModal} className="text-xs">
            <Play className="h-3.5 w-3.5 mr-1" />
            Run Monthly Billing
          </Button>
        </div>
      </div>

      {overviewError && (
        <Alert variant="error" title="Overview Error">
          {(overviewError as any)?.message || 'Unable to load society financial overview'}
        </Alert>
      )}

      {/* KPI Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Billed */}
        <Card className="border-l-4 border-l-indigo-500">
          <CardContent className="pt-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Total Billed</p>
                {isOverviewLoading ? (
                  <Skeleton className="h-8 w-28 mt-1" />
                ) : (
                  <p className="text-2xl font-bold text-slate-900 mt-1">
                    {formatINR(overview?.total_billed_paise || 0)}
                  </p>
                )}
              </div>
              <div className="h-10 w-10 rounded-full bg-indigo-50 flex items-center justify-center text-indigo-600">
                <FileText className="h-5 w-5" />
              </div>
            </div>
            <p className="text-[11px] text-slate-500 mt-3">{overview?.total_invoices_count || 0} Invoices generated</p>
          </CardContent>
        </Card>

        {/* Total Collected */}
        <Card className="border-l-4 border-l-emerald-500">
          <CardContent className="pt-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Total Collected</p>
                {isOverviewLoading ? (
                  <Skeleton className="h-8 w-28 mt-1" />
                ) : (
                  <p className="text-2xl font-bold text-emerald-700 mt-1">
                    {formatINR(overview?.total_collected_paise || 0)}
                  </p>
                )}
              </div>
              <div className="h-10 w-10 rounded-full bg-emerald-50 flex items-center justify-center text-emerald-600">
                <TrendingUp className="h-5 w-5" />
              </div>
            </div>
            <p className="text-[11px] text-slate-500 mt-3">{overview?.paid_invoices_count || 0} Fully paid invoices</p>
          </CardContent>
        </Card>

        {/* Total Outstanding */}
        <Card className="border-l-4 border-l-amber-500">
          <CardContent className="pt-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Total Outstanding</p>
                {isOverviewLoading ? (
                  <Skeleton className="h-8 w-28 mt-1" />
                ) : (
                  <p className="text-2xl font-bold text-slate-900 mt-1">
                    {formatINR(overview?.total_outstanding_paise || 0)}
                  </p>
                )}
              </div>
              <div className="h-10 w-10 rounded-full bg-amber-50 flex items-center justify-center text-amber-600">
                <DollarSign className="h-5 w-5" />
              </div>
            </div>
            <p className="text-[11px] text-slate-500 mt-3">{overview?.unpaid_invoices_count || 0} Pending accounts</p>
          </CardContent>
        </Card>

        {/* Total Overdue */}
        <Card className="border-l-4 border-l-rose-500">
          <CardContent className="pt-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Overdue Dues</p>
                {isOverviewLoading ? (
                  <Skeleton className="h-8 w-28 mt-1" />
                ) : (
                  <p className="text-2xl font-bold text-rose-600 mt-1">
                    {formatINR(overview?.total_overdue_paise || 0)}
                  </p>
                )}
              </div>
              <div className="h-10 w-10 rounded-full bg-rose-50 flex items-center justify-center text-rose-600">
                <AlertTriangle className="h-5 w-5" />
              </div>
            </div>
            <p className="text-[11px] text-slate-500 mt-3">{overview?.overdue_invoices_count || 0} Overdue accounts</p>
          </CardContent>
        </Card>
      </div>

      {/* Filter Bar */}
      <Card>
        <CardContent className="pt-4 pb-4">
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 text-xs">
            <div>
              <label className="block text-[11px] font-semibold text-slate-500 mb-1">Billing Period</label>
              <input
                type="text"
                placeholder="YYYY-MM (e.g. 2026-11)"
                value={selectedPeriod}
                onChange={(e) => {
                  setSelectedPeriod(e.target.value);
                  setCurrentPage(1);
                }}
                className="w-full px-2.5 py-1.5 border border-slate-300 rounded focus:ring-1 focus:ring-indigo-500 text-xs"
              />
            </div>

            <div>
              <label className="block text-[11px] font-semibold text-slate-500 mb-1">Tower</label>
              <select
                value={selectedTower}
                onChange={(e) => {
                  setSelectedTower(e.target.value);
                  setCurrentPage(1);
                }}
                className="w-full px-2.5 py-1.5 border border-slate-300 rounded focus:ring-1 focus:ring-indigo-500 text-xs"
              >
                <option value="">All Towers</option>
                <option value="T07">Tower T07</option>
                <option value="T12">Tower T12</option>
                <option value="T21">Tower T21</option>
              </select>
            </div>

            <div>
              <label className="block text-[11px] font-semibold text-slate-500 mb-1">Unit Number</label>
              <div className="relative">
                <Search className="h-3.5 w-3.5 text-slate-400 absolute left-2.5 top-2" />
                <input
                  type="text"
                  placeholder="e.g. 1203"
                  value={flatSearch}
                  onChange={(e) => {
                    setFlatSearch(e.target.value);
                    setCurrentPage(1);
                  }}
                  className="w-full pl-8 pr-2.5 py-1.5 border border-slate-300 rounded focus:ring-1 focus:ring-indigo-500 text-xs"
                />
              </div>
            </div>

            <div>
              <label className="block text-[11px] font-semibold text-slate-500 mb-1">Status</label>
              <select
                value={selectedStatus}
                onChange={(e) => {
                  setSelectedStatus(e.target.value);
                  setCurrentPage(1);
                }}
                className="w-full px-2.5 py-1.5 border border-slate-300 rounded focus:ring-1 focus:ring-indigo-500 text-xs"
              >
                <option value="">All Statuses</option>
                <option value="UNPAID">UNPAID</option>
                <option value="PARTIALLY_PAID">PARTIALLY PAID</option>
                <option value="PAID">PAID</option>
                <option value="OVERDUE">OVERDUE</option>
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Invoices List */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <div>
            <CardTitle>Society Invoice Registry</CardTitle>
            <p className="text-xs text-slate-500 mt-0.5">Filterable invoices for all residential apartments</p>
          </div>
          <Badge variant="neutral">{invoices?.length || 0} Records</Badge>
        </CardHeader>
        <CardContent>
          {isInvoicesLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : invoicesError ? (
            <Alert variant="error" title="Failed to load invoices">
              {(invoicesError as any)?.message}
            </Alert>
          ) : invoices && invoices.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 text-slate-600 uppercase font-semibold border-b border-slate-200">
                  <tr>
                    <th className="py-3 px-4">Invoice #</th>
                    <th className="py-3 px-4">Period</th>
                    <th className="py-3 px-4">Tower & Unit</th>
                    <th className="py-3 px-4">Primary Resident</th>
                    <th className="py-3 px-4">Carpet Area</th>
                    <th className="py-3 px-4">Total Amount</th>
                    <th className="py-3 px-4">Paid</th>
                    <th className="py-3 px-4">Outstanding</th>
                    <th className="py-3 px-4">Due Date</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4 text-right">Inspect</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-normal">
                  {invoices.map((inv) => (
                    <tr key={inv.id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="py-3 px-4 font-mono font-medium text-slate-900">{inv.invoice_number}</td>
                      <td className="py-3 px-4 text-slate-700">{inv.billing_period}</td>
                      <td className="py-3 px-4 font-medium text-slate-900">
                        {inv.tower_number ? `${inv.tower_number}-${inv.flat_number}` : `Flat ${inv.flat_number}`}
                      </td>
                      <td className="py-3 px-4 text-slate-700">{inv.resident_name || '-'}</td>
                      <td className="py-3 px-4 text-slate-600 font-mono">{inv.area_sqft_snapshot} sq ft</td>
                      <td className="py-3 px-4 font-bold text-slate-900">{formatINR(inv.total_paise)}</td>
                      <td className="py-3 px-4 text-emerald-700 font-medium">{formatINR(inv.paid_paise)}</td>
                      <td className="py-3 px-4">
                        <span
                          className={
                            inv.outstanding_paise > 0 ? 'text-rose-600 font-bold' : 'text-slate-500 font-medium'
                          }
                        >
                          {formatINR(inv.outstanding_paise)}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-slate-600">{formatDateIST(inv.due_date)}</td>
                      <td className="py-3 px-4">{getStatusBadge(inv.status, inv.is_overdue)}</td>
                      <td className="py-3 px-4 text-right">
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => setSelectedInvoiceDetail(inv)}
                          className="text-xs h-7 px-2"
                        >
                          <Eye className="h-3.5 w-3.5 mr-1" />
                          Inspect
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {/* Pagination Controls */}
              <div className="flex items-center justify-between px-4 py-3 border-t border-slate-200 bg-slate-50 text-xs">
                <span className="text-slate-500 font-mono text-[11px]">
                  Page <strong className="text-slate-900">{currentPage}</strong> • Showing {invoices.length} invoices
                </span>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={currentPage === 1}
                    onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                    className="text-xs h-7 px-2.5"
                  >
                    Previous
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!invoices || invoices.length < PAGE_SIZE}
                    onClick={() => setCurrentPage((p) => p + 1)}
                    className="text-xs h-7 px-2.5"
                  >
                    Next
                  </Button>
                </div>
              </div>
            </div>
          ) : (
            <div className="text-center py-10 text-slate-500 text-xs">
              <FileText className="h-8 w-8 text-slate-400 mx-auto mb-2" />
              <p className="font-semibold text-slate-700">No invoices match selected criteria</p>
              <p className="text-slate-500 mt-1">Adjust filters or run monthly billing to generate invoices.</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ------------------------------------------------------------- */}
      {/* Modal: Run Monthly Billing Execution & Preview */}
      {/* ------------------------------------------------------------- */}
      {isRunModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl max-w-lg w-full border border-slate-200 overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between bg-slate-50">
              <div className="flex items-center gap-2">
                <Play className="h-5 w-5 text-indigo-600" />
                <h3 className="text-sm font-bold text-slate-900">Execute Monthly Maintenance Billing</h3>
              </div>
              <button onClick={() => setIsRunModalOpen(false)} className="text-slate-400 hover:text-slate-600 rounded p-1">
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="p-5 space-y-4 text-xs">
              {runError && (
                <Alert variant="error" title="Billing Execution Error">
                  {runError}
                </Alert>
              )}

              {/* Execution Success Card */}
              {executionResult && (
                <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-lg space-y-2">
                  <div className="flex items-center gap-2 text-emerald-800 font-bold">
                    <CheckCircle2 className="h-5 w-5 text-emerald-600" />
                    <span>Billing Run Completed Successfully</span>
                  </div>
                  <div className="font-mono text-[11px] text-emerald-900 space-y-1">
                    <div>Run ID: {executionResult.id}</div>
                    <div>Period: {executionResult.billing_period}</div>
                    <div>Generated Invoices: {executionResult.total_invoiced_flats}</div>
                    <div>Skipped (Already Generated): {executionResult.total_skipped_flats}</div>
                    <div className="font-bold">Total Assessed: {formatINR(executionResult.total_charges_paise)}</div>
                  </div>
                  <Button
                    size="sm"
                    variant="primary"
                    onClick={() => setIsRunModalOpen(false)}
                    className="w-full mt-2"
                  >
                    Done & Refresh Ledger
                  </Button>
                </div>
              )}

              {/* Inputs & Preview */}
              {!executionResult && (
                <>
                  <div className="space-y-1">
                    <label className="block font-semibold text-slate-700">Billing Period (YYYY-MM)</label>
                    <input
                      type="text"
                      value={runPeriod}
                      onChange={(e) => setRunPeriod(e.target.value)}
                      placeholder="2026-11"
                      className="w-full px-3 py-1.5 border border-slate-300 rounded font-mono text-sm focus:ring-1 focus:ring-indigo-500"
                    />
                    <p className="text-[11px] text-slate-500">
                      Standard society due date calculated as per configured society due day.
                    </p>
                  </div>

                  {previewResult && (
                    <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg space-y-2 font-mono text-[11px]">
                      <div className="font-bold text-slate-900 border-b border-slate-200 pb-1">
                        Preview Verification Summary
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">Applicable Maintenance Rate:</span>
                        <span className="font-bold text-slate-900">
                          ₹{(previewResult.rate_paise_per_sqft / 100).toFixed(2)} / sq ft
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">Eligible Residential Flats:</span>
                        <span className="font-bold text-emerald-700">{previewResult.eligible_flats_count} Units</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">Already Invoiced (Will Skip):</span>
                        <span className="font-bold text-slate-600">{previewResult.already_invoiced_count} Units</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">Excluded Units:</span>
                        <span className="font-bold text-amber-700">{previewResult.excluded_flats_count} Units</span>
                      </div>
                      <div className="flex justify-between border-t border-slate-200 pt-1 text-xs">
                        <span className="font-bold text-slate-800">Total Expected Charges:</span>
                        <span className="font-bold text-indigo-700">
                          {formatINR(previewResult.total_expected_charges_paise)}
                        </span>
                      </div>
                    </div>
                  )}

                  <div className="p-2.5 bg-slate-100 rounded text-[11px] text-slate-500">
                    <p>
                      Safety Controls: Database unique constraint enforces at most 1 invoice per apartment per period.
                      Retrying or running concurrently will not produce duplicate charges.
                    </p>
                  </div>

                  <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-200">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => previewMutation.mutate(runPeriod)}
                      isLoading={previewMutation.isPending}
                    >
                      <Eye className="h-3.5 w-3.5 mr-1" />
                      Preview Run
                    </Button>

                    <Button
                      type="button"
                      variant="primary"
                      size="sm"
                      onClick={() => executeMutation.mutate(runPeriod)}
                      isLoading={executeMutation.isPending}
                    >
                      <Play className="h-3.5 w-3.5 mr-1" />
                      Execute Billing Run
                    </Button>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* Modal: Staff Invoice Inspect */}
      {/* ------------------------------------------------------------- */}
      {selectedInvoiceDetail && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl max-w-xl w-full border border-slate-200 overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between bg-slate-50">
              <div className="flex items-center gap-2">
                <FileText className="h-5 w-5 text-indigo-600" />
                <h3 className="text-sm font-bold text-slate-900">
                  Inspect Invoice {selectedInvoiceDetail.invoice_number}
                </h3>
              </div>
              <button
                onClick={() => setSelectedInvoiceDetail(null)}
                className="text-slate-400 hover:text-slate-600 rounded p-1"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="p-5 space-y-4 text-xs font-mono">
              <div className="p-3 bg-slate-50 rounded border border-slate-200 space-y-1.5 text-[11px]">
                <div className="flex justify-between">
                  <span className="text-slate-500">Unit:</span>
                  <span className="font-bold text-slate-900">
                    {selectedInvoiceDetail.tower_number}-{selectedInvoiceDetail.flat_number}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Primary Resident:</span>
                  <span className="font-semibold text-slate-900">{selectedInvoiceDetail.resident_name || '-'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Snapshot Area:</span>
                  <span>{selectedInvoiceDetail.area_sqft_snapshot} sq ft</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Rate Applied:</span>
                  <span>₹{(selectedInvoiceDetail.rate_paise_per_sqft_snapshot / 100).toFixed(2)} / sq ft</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Due Date:</span>
                  <span>{formatDateIST(selectedInvoiceDetail.due_date)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Status:</span>
                  <span>{selectedInvoiceDetail.status}</span>
                </div>
              </div>

              <div className="border border-slate-200 rounded p-3 space-y-1 text-xs">
                <div className="flex justify-between">
                  <span>Assessed Total:</span>
                  <span className="font-bold text-slate-900">{formatINR(selectedInvoiceDetail.total_paise)}</span>
                </div>
                <div className="flex justify-between text-emerald-700">
                  <span>Allocated Collections:</span>
                  <span className="font-bold">{formatINR(selectedInvoiceDetail.paid_paise)}</span>
                </div>
                <div className="flex justify-between border-t border-slate-200 pt-1 font-bold text-rose-600">
                  <span>Remaining Outstanding:</span>
                  <span>{formatINR(selectedInvoiceDetail.outstanding_paise)}</span>
                </div>
              </div>
            </div>

            <div className="px-5 py-3 border-t border-slate-200 bg-slate-50 flex justify-end">
              <Button size="sm" variant="secondary" onClick={() => setSelectedInvoiceDetail(null)}>
                Close
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
