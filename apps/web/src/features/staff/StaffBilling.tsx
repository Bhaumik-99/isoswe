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
  Clock,
  ShieldCheck,
  Plus,
  Scale,
} from 'lucide-react';
import {
  billingService,
  formatINR,
  formatDateIST,
  LateFeePolicy,
  LateFeePreviewResponse,
  ApplyLateFeesResponse,
} from '../../services/billingService';
import { BillingRun, BillingRunPreview, Invoice, InvoiceStatus } from '../../types/billing';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Skeleton } from '../../components/ui/Skeleton';
import { Alert } from '../../components/ui/Alert';

export const StaffBilling: React.FC = () => {
  const queryClient = useQueryClient();

  // Tab navigation
  const [activeTab, setActiveTab] = useState<'INVOICES' | 'LATE_FEES'>('INVOICES');

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

  // Late Fee State
  const [isPolicyModalOpen, setIsPolicyModalOpen] = useState(false);
  const [policyError, setPolicyError] = useState<string | null>(null);
  const [newPolicy, setNewPolicy] = useState<{
    policy_name: string;
    calculation_method: 'FLAT_FEE' | 'PERCENTAGE_PER_MONTH' | 'DAILY_INTEREST_PAISE';
    rate_or_amount: string;
    grace_period_days: number;
    min_charge_inr: string;
    max_charge_inr: string;
  }>({
    policy_name: 'Standard Society Bye-Law Late Fee',
    calculation_method: 'PERCENTAGE_PER_MONTH',
    rate_or_amount: '2.0',
    grace_period_days: 15,
    min_charge_inr: '100',
    max_charge_inr: '1000',
  });
  const [lateFeePreview, setLateFeePreview] = useState<LateFeePreviewResponse | null>(null);
  const [lateFeeResult, setLateFeeResult] = useState<ApplyLateFeesResponse | null>(null);
  const [lateFeeActionError, setLateFeeActionError] = useState<string | null>(null);

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

  const {
    data: lateFeePolicies = [],
    isLoading: isPoliciesLoading,
  } = useQuery<LateFeePolicy[]>({
    queryKey: ['staff-late-fee-policies'],
    queryFn: () => billingService.getLateFeePolicies(),
  });

  const createPolicyMutation = useMutation({
    mutationFn: () => {
      const isPercent = newPolicy.calculation_method === 'PERCENTAGE_PER_MONTH';
      const bpsOrPaise = isPercent
        ? Math.round(parseFloat(newPolicy.rate_or_amount) * 100)
        : Math.round(parseFloat(newPolicy.rate_or_amount) * 100);
      return billingService.createLateFeePolicy({
        policy_name: newPolicy.policy_name,
        calculation_method: newPolicy.calculation_method,
        amount_or_rate_bps: bpsOrPaise,
        grace_period_days: Number(newPolicy.grace_period_days),
        min_charge_paise: Math.round((parseFloat(newPolicy.min_charge_inr) || 0) * 100),
        max_charge_paise: Math.round((parseFloat(newPolicy.max_charge_inr) || 0) * 100),
        is_active: true,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['staff-late-fee-policies'] });
      setIsPolicyModalOpen(false);
      setPolicyError(null);
    },
    onError: (err: any) => {
      setPolicyError(err?.message || 'Failed to configure policy');
    },
  });

  const previewLateFeeMutation = useMutation({
    mutationFn: () => billingService.previewLateFees(),
    onSuccess: (data) => {
      setLateFeePreview(data);
      setLateFeeActionError(null);
    },
    onError: (err: any) => {
      setLateFeeActionError(err?.message || 'Failed to preview late fees');
    },
  });

  const applyLateFeeMutation = useMutation({
    mutationFn: () => billingService.applyLateFees(),
    onSuccess: (res) => {
      setLateFeeResult(res);
      setLateFeePreview(null);
      setLateFeeActionError(null);
      queryClient.invalidateQueries({ queryKey: ['staff-invoices'] });
      queryClient.invalidateQueries({ queryKey: ['staff-billing-overview'] });
      queryClient.invalidateQueries({ queryKey: ['staff-late-fee-policies'] });
    },
    onError: (err: any) => {
      setLateFeeActionError(err?.message || 'Failed to apply late fees');
    },
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

      {/* Sub-navigation Tabs */}
      <div className="flex border-b border-slate-200 gap-6 text-xs font-medium">
        <button
          onClick={() => setActiveTab('INVOICES')}
          className={`pb-3 px-1 border-b-2 flex items-center gap-1.5 ${
            activeTab === 'INVOICES'
              ? 'border-indigo-600 text-indigo-600 font-bold'
              : 'border-transparent text-slate-500 hover:text-slate-700'
          }`}
        >
          <FileText className="h-4 w-4" />
          <span>Invoices & Accounts</span>
        </button>
        <button
          onClick={() => setActiveTab('LATE_FEES')}
          className={`pb-3 px-1 border-b-2 flex items-center gap-1.5 ${
            activeTab === 'LATE_FEES'
              ? 'border-indigo-600 text-indigo-600 font-bold'
              : 'border-transparent text-slate-500 hover:text-slate-700'
          }`}
        >
          <Scale className="h-4 w-4" />
          <span>Late-Fee Bye-Law Governance</span>
          {lateFeePolicies.length > 0 && (
            <Badge variant="success" className="text-[10px] py-0 px-1.5 ml-1">
              {lateFeePolicies.length} Configured
            </Badge>
          )}
        </button>
      </div>

      {activeTab === 'INVOICES' && (
        <>
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
      </>
      )}

      {/* ------------------------------------------------------------- */}
      {/* Tab: Late-Fee Bye-Law Governance */}
      {/* ------------------------------------------------------------- */}
      {activeTab === 'LATE_FEES' && (
        <div className="space-y-6">
          {/* Action & Alerts Header */}
          {lateFeeActionError && (
            <Alert variant="error" title="Late Fee Assessment Error">
              {lateFeeActionError}
            </Alert>
          )}

          {lateFeeResult && (
            <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-lg space-y-2">
              <div className="flex items-center gap-2 text-emerald-800 font-bold text-sm">
                <CheckCircle2 className="h-5 w-5 text-emerald-600" />
                <span>Late Fees Assessed Successfully</span>
              </div>
              <p className="text-xs text-emerald-900 font-mono">
                {lateFeeResult.message} • Invoices Charged: {lateFeeResult.applied_invoices_count} • Total Assessed:{' '}
                {formatINR(lateFeeResult.total_fee_charged_paise)}
              </p>
            </div>
          )}

          {/* Configured Bye-Law Policies */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <div>
                <CardTitle className="text-sm font-bold text-slate-900 flex items-center gap-2">
                  <ShieldCheck className="h-4 w-4 text-indigo-600" />
                  Configured Society Bye-Law Late Fee Policies
                </CardTitle>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  Society maintenance bye-laws dictate permissible interest and surcharge formulas.
                </p>
              </div>
              <Button
                size="sm"
                variant="primary"
                onClick={() => setIsPolicyModalOpen(true)}
                className="text-xs"
              >
                <Plus className="h-3.5 w-3.5 mr-1" />
                Configure Bye-Law Policy
              </Button>
            </CardHeader>
            <CardContent>
              {isPoliciesLoading ? (
                <div className="space-y-2 py-4">
                  <Skeleton className="h-8 w-full" />
                  <Skeleton className="h-8 w-full" />
                </div>
              ) : lateFeePolicies.length === 0 ? (
                <div className="p-8 text-center text-xs text-slate-500">
                  <AlertTriangle className="h-8 w-8 text-amber-500 mx-auto mb-2" />
                  <p className="font-semibold text-slate-800">No Approved Late Fee Policy Configured</p>
                  <p className="mt-1">
                    The platform requires an explicit bye-law policy. Dues cannot be surcharged without an active policy.
                  </p>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setIsPolicyModalOpen(true)}
                    className="mt-3 text-xs"
                  >
                    Configure Policy Now
                  </Button>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200">
                      <tr>
                        <th className="py-2.5 px-3">Policy Name</th>
                        <th className="py-2.5 px-3">Calculation Method</th>
                        <th className="py-2.5 px-3">Rate / Amount</th>
                        <th className="py-2.5 px-3">Grace Period</th>
                        <th className="py-2.5 px-3">Min / Max Cap</th>
                        <th className="py-2.5 px-3">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 font-mono text-[11px]">
                      {lateFeePolicies.map((pol) => (
                        <tr key={pol.id} className="hover:bg-slate-50">
                          <td className="py-3 px-3 font-semibold text-slate-900 font-sans">{pol.policy_name}</td>
                          <td className="py-3 px-3 font-sans">
                            <Badge variant="neutral">{pol.calculation_method}</Badge>
                          </td>
                          <td className="py-3 px-3">
                            {pol.calculation_method === 'PERCENTAGE_PER_MONTH'
                              ? `${(pol.amount_or_rate_bps / 100).toFixed(2)}% / month`
                              : formatINR(pol.amount_or_rate_bps)}
                          </td>
                          <td className="py-3 px-3 font-sans">
                            <span className="font-bold text-indigo-700">{pol.grace_period_days} days</span> from due date
                          </td>
                          <td className="py-3 px-3 text-slate-500">
                            {pol.min_charge_paise > 0 ? formatINR(pol.min_charge_paise) : 'None'} /{' '}
                            {pol.max_charge_paise > 0 ? formatINR(pol.max_charge_paise) : 'No Cap'}
                          </td>
                          <td className="py-3 px-3 font-sans">
                            <Badge variant={pol.is_active ? 'success' : 'neutral'}>
                              {pol.is_active ? 'ACTIVE' : 'INACTIVE'}
                            </Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Assessment & Preview */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <div>
                <CardTitle className="text-sm font-bold text-slate-900 flex items-center gap-2">
                  <Clock className="h-4 w-4 text-rose-600" />
                  Overdue Accounts Assessment & Execution
                </CardTitle>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  Evaluates unpaid principal after grace period. Surcharges are partial-payment aware and generate immutable ledger entries.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => previewLateFeeMutation.mutate()}
                  disabled={previewLateFeeMutation.isPending || lateFeePolicies.length === 0}
                  className="text-xs"
                >
                  <Eye className="h-3.5 w-3.5 mr-1" />
                  {previewLateFeeMutation.isPending ? 'Evaluating...' : 'Preview Surcharges'}
                </Button>
                <Button
                  size="sm"
                  variant="primary"
                  onClick={() => applyLateFeeMutation.mutate()}
                  disabled={applyLateFeeMutation.isPending || lateFeePolicies.length === 0}
                  className="text-xs bg-rose-600 hover:bg-rose-700 text-white"
                >
                  <Play className="h-3.5 w-3.5 mr-1" />
                  {applyLateFeeMutation.isPending ? 'Applying...' : 'Apply Late Fees'}
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {lateFeePreview ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs">
                    <div>
                      <span className="text-slate-500 block">Active Policy:</span>
                      <span className="font-bold text-slate-900">{lateFeePreview.policy?.policy_name || 'None'}</span>
                    </div>
                    <div>
                      <span className="text-slate-500 block">Eligible Overdue Invoices:</span>
                      <span className="font-bold text-rose-600">{lateFeePreview.total_eligible_invoices}</span>
                    </div>
                    <div>
                      <span className="text-slate-500 block">Total Proposed Surcharges:</span>
                      <span className="font-bold text-slate-900">{formatINR(lateFeePreview.total_proposed_fee_paise)}</span>
                    </div>
                  </div>

                  {lateFeePreview.items.length === 0 ? (
                    <p className="text-center py-6 text-slate-500 text-xs">
                      No invoices are currently beyond their grace period for this billing cycle.
                    </p>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-xs">
                        <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200">
                          <tr>
                            <th className="py-2.5 px-3">Invoice</th>
                            <th className="py-2.5 px-3">Flat / Tower</th>
                            <th className="py-2.5 px-3">Period</th>
                            <th className="py-2.5 px-3">Due Date</th>
                            <th className="py-2.5 px-3">Days Overdue</th>
                            <th className="py-2.5 px-3">Unpaid Principal</th>
                            <th className="py-2.5 px-3">Proposed Surcharge</th>
                            <th className="py-2.5 px-3">Calculation Basis</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 font-mono text-[11px]">
                          {lateFeePreview.items.map((item) => (
                            <tr key={item.invoice_id} className="hover:bg-slate-50">
                              <td className="py-2.5 px-3 font-semibold text-slate-900">{item.invoice_number}</td>
                              <td className="py-2.5 px-3 font-sans">
                                {item.tower_number} - {item.flat_number}
                              </td>
                              <td className="py-2.5 px-3">{item.billing_period}</td>
                              <td className="py-2.5 px-3">{formatDateIST(item.due_date)}</td>
                              <td className="py-2.5 px-3 text-rose-600 font-bold">{item.days_overdue} days</td>
                              <td className="py-2.5 px-3">{formatINR(item.unpaid_principal_paise)}</td>
                              <td className="py-2.5 px-3 font-bold text-slate-900">{formatINR(item.proposed_fee_paise)}</td>
                              <td className="py-2.5 px-3 text-slate-500 font-sans text-[10px]">{item.explanation}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              ) : (
                <div className="p-8 text-center text-xs text-slate-500">
                  <p>Click <strong>Preview Surcharges</strong> to inspect eligible overdue accounts before execution.</p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* Modal: Configure Bye-Law Policy */}
      {/* ------------------------------------------------------------- */}
      {isPolicyModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl max-w-lg w-full border border-slate-200 overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between bg-slate-50">
              <div className="flex items-center gap-2">
                <Scale className="h-5 w-5 text-indigo-600" />
                <h3 className="text-sm font-bold text-slate-900">Configure Bye-Law Late Fee Policy</h3>
              </div>
              <button onClick={() => setIsPolicyModalOpen(false)} className="text-slate-400 hover:text-slate-600 rounded p-1">
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="p-5 space-y-4 text-xs">
              {policyError && (
                <Alert variant="error" title="Policy Configuration Error">
                  {policyError}
                </Alert>
              )}

              <div className="space-y-1">
                <label className="block font-semibold text-slate-700">Policy Name</label>
                <input
                  type="text"
                  value={newPolicy.policy_name}
                  onChange={(e) => setNewPolicy((p) => ({ ...p, policy_name: e.target.value }))}
                  className="w-full px-3 py-1.5 border border-slate-300 rounded text-xs"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="block font-semibold text-slate-700">Calculation Method</label>
                  <select
                    value={newPolicy.calculation_method}
                    onChange={(e) =>
                      setNewPolicy((p) => ({
                        ...p,
                        calculation_method: e.target.value as any,
                      }))
                    }
                    className="w-full px-3 py-1.5 border border-slate-300 rounded text-xs"
                  >
                    <option value="PERCENTAGE_PER_MONTH">Percentage per Month</option>
                    <option value="FLAT_FEE">Flat Fee (₹)</option>
                    <option value="DAILY_INTEREST_PAISE">Daily Interest (paise)</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <label className="block font-semibold text-slate-700">
                    {newPolicy.calculation_method === 'PERCENTAGE_PER_MONTH'
                      ? 'Rate (% per month)'
                      : 'Fixed Amount (₹)'}
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={newPolicy.rate_or_amount}
                    onChange={(e) => setNewPolicy((p) => ({ ...p, rate_or_amount: e.target.value }))}
                    className="w-full px-3 py-1.5 border border-slate-300 rounded text-xs"
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="block font-semibold text-slate-700">
                  Explicit Grace Period (Days from Due Date)
                </label>
                <input
                  type="number"
                  min="0"
                  max="90"
                  value={newPolicy.grace_period_days}
                  onChange={(e) =>
                    setNewPolicy((p) => ({
                      ...p,
                      grace_period_days: parseInt(e.target.value, 10) || 0,
                    }))
                  }
                  className="w-full px-3 py-1.5 border border-slate-300 rounded text-xs"
                />
                <p className="text-[10px] text-slate-500">
                  Must strictly align with society bye-laws. Surcharges begin after grace period expires.
                </p>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="block font-semibold text-slate-700">Minimum Surcharge (₹)</label>
                  <input
                    type="number"
                    value={newPolicy.min_charge_inr}
                    onChange={(e) => setNewPolicy((p) => ({ ...p, min_charge_inr: e.target.value }))}
                    className="w-full px-3 py-1.5 border border-slate-300 rounded text-xs"
                  />
                </div>
                <div className="space-y-1">
                  <label className="block font-semibold text-slate-700">Maximum Cap (₹, 0 for none)</label>
                  <input
                    type="number"
                    value={newPolicy.max_charge_inr}
                    onChange={(e) => setNewPolicy((p) => ({ ...p, max_charge_inr: e.target.value }))}
                    className="w-full px-3 py-1.5 border border-slate-300 rounded text-xs"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-slate-200">
                <Button size="sm" variant="outline" onClick={() => setIsPolicyModalOpen(false)}>
                  Cancel
                </Button>
                <Button
                  size="sm"
                  variant="primary"
                  onClick={() => createPolicyMutation.mutate()}
                  disabled={createPolicyMutation.isPending}
                >
                  {createPolicyMutation.isPending ? 'Saving...' : 'Save & Activate Policy'}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

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
