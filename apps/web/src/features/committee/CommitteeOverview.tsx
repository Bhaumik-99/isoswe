import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Landmark,
  Building,
  ShieldCheck,
  ScrollText,
  Download,
  PieChart,
  TrendingUp,
} from 'lucide-react';
import { committeeService, CommitteeOverviewResponse, MonthlyReportItem } from '../../services/committeeService';
import { formatINR } from '../../services/billingService';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Skeleton } from '../../components/ui/Skeleton';
import { Alert } from '../../components/ui/Alert';

export const CommitteeOverview: React.FC = () => {
  const [isExporting, setIsExporting] = useState<boolean>(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const {
    data: overview,
    isLoading: isOverviewLoading,
    error: overviewError,
  } = useQuery<CommitteeOverviewResponse>({
    queryKey: ['committee-overview'],
    queryFn: () => committeeService.getOverview(),
  });

  const {
    data: monthlyReports = [],
    isLoading: isMonthlyLoading,
  } = useQuery<MonthlyReportItem[]>({
    queryKey: ['committee-monthly-reports'],
    queryFn: () => committeeService.getMonthlyReports(),
  });

  const handleExportCsv = async () => {
    try {
      setIsExporting(true);
      setExportError(null);
      await committeeService.downloadCsvExport();
    } catch (err: unknown) {
      setExportError(err instanceof Error ? err.message : 'Export failed');
    } finally {
      setIsExporting(false);
    }
  };

  if (overviewError) {
    return (
      <Alert variant="error" title="Error Loading Committee Data">
        {overviewError instanceof Error ? overviewError.message : 'Failed to load committee oversight data'}
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-200">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Managing Committee Oversight</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Real-time multi-tower ledger aggregates, arrears ageing, and complaint safety governance
          </p>
        </div>
        <div className="flex items-center gap-2">
          {overview && (
            <Badge variant="neutral">Society: {overview.society_name}</Badge>
          )}
          <Button
            size="sm"
            variant="outline"
            onClick={handleExportCsv}
            disabled={isExporting}
            className="text-xs flex items-center gap-1.5"
          >
            <Download className="h-3.5 w-3.5" />
            {isExporting ? 'Exporting...' : 'Export Statement CSV'}
          </Button>
        </div>
      </div>

      {exportError && (
        <Alert variant="error" title="Export Failed">
          {exportError}
        </Alert>
      )}

      {/* Financial KPIs */}
      {isOverviewLoading || !overview ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between text-slate-500 mb-1">
                <span className="text-xs font-semibold uppercase tracking-wider">Total Billed</span>
                <Landmark className="h-4 w-4 text-indigo-600" />
              </div>
              <div className="text-2xl font-bold text-slate-900">
                {formatINR(overview.financials.total_billed_paise)}
              </div>
              <div className="text-xs text-slate-500 mt-0.5">Township-wide assessments</div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between text-slate-500 mb-1">
                <span className="text-xs font-semibold uppercase tracking-wider">Total Collected</span>
                <TrendingUp className="h-4 w-4 text-emerald-600" />
              </div>
              <div className="text-2xl font-bold text-emerald-600">
                {formatINR(overview.financials.total_collected_paise)}
              </div>
              <div className="text-xs text-slate-500 mt-0.5">
                Efficiency: {overview.financials.collection_percentage.toFixed(1)}%
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between text-slate-500 mb-1">
                <span className="text-xs font-semibold uppercase tracking-wider">Outstanding Dues</span>
                <PieChart className="h-4 w-4 text-rose-600" />
              </div>
              <div className="text-2xl font-bold text-rose-600">
                {formatINR(overview.financials.total_outstanding_paise)}
              </div>
              <div className="text-xs text-slate-500 mt-0.5">
                Overdue: {formatINR(overview.financials.total_overdue_paise)}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between text-slate-500 mb-1">
                <span className="text-xs font-semibold uppercase tracking-wider">Safety & SLA Health</span>
                <ShieldCheck className="h-4 w-4 text-indigo-600" />
              </div>
              <div className="text-2xl font-bold text-slate-900">
                {overview.complaints.safety_escalated_count === 0 ? 'Normal' : `${overview.complaints.safety_escalated_count} Alert${overview.complaints.safety_escalated_count > 1 ? 's' : ''}`}
              </div>
              <div className="text-xs text-slate-500 mt-0.5">
                SLA Breaches: {overview.complaints.sla_breached_count} | Turnaround: {overview.complaints.avg_resolution_hours.toFixed(1)}h
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Arrears Ageing & Operations Split */}
      {overview && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Ageing Buckets Card */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-semibold flex items-center justify-between">
                <span>Maintenance Arrears Ageing Buckets</span>
                <Badge variant="info">Live Balances</Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
                <div className="p-3 bg-slate-50 rounded border border-slate-200">
                  <span className="text-[10px] text-slate-500 uppercase font-bold">0 - 30 Days</span>
                  <div className="text-sm font-bold text-slate-900 mt-1">
                    {formatINR(overview.financials.ageing.bucket_0_30_paise)}
                  </div>
                </div>
                <div className="p-3 bg-amber-50 rounded border border-amber-200">
                  <span className="text-[10px] text-amber-700 uppercase font-bold">31 - 60 Days</span>
                  <div className="text-sm font-bold text-amber-900 mt-1">
                    {formatINR(overview.financials.ageing.bucket_31_60_paise)}
                  </div>
                </div>
                <div className="p-3 bg-orange-50 rounded border border-orange-200">
                  <span className="text-[10px] text-orange-700 uppercase font-bold">61 - 90 Days</span>
                  <div className="text-sm font-bold text-orange-900 mt-1">
                    {formatINR(overview.financials.ageing.bucket_61_90_paise)}
                  </div>
                </div>
                <div className="p-3 bg-rose-50 rounded border border-rose-200">
                  <span className="text-[10px] text-rose-700 uppercase font-bold">90+ Days</span>
                  <div className="text-sm font-bold text-rose-900 mt-1">
                    {formatINR(overview.financials.ageing.bucket_90_plus_paise)}
                  </div>
                </div>
              </div>
              <p className="text-[11px] text-slate-500">
                Arrears calculated across all active invoices using strict FIFO integer paise accounting.
              </p>
            </CardContent>
          </Card>

          {/* Complaint Safety & Operational Status */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-semibold flex items-center justify-between">
                <span>Facility Helpdesk Governance</span>
                <Badge variant={overview.complaints.safety_escalated_count > 0 ? 'danger' : 'success'}>
                  {overview.complaints.safety_escalated_count > 0 ? 'Safety Alerts Active' : 'All Safe'}
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="p-3 bg-slate-50 rounded border border-slate-200">
                  <span className="text-[10px] text-slate-500 uppercase font-bold">Open Tickets</span>
                  <div className="text-lg font-bold text-slate-900 mt-1">
                    {overview.complaints.open_complaints}
                  </div>
                </div>
                <div className="p-3 bg-indigo-50 rounded border border-indigo-200">
                  <span className="text-[10px] text-indigo-700 uppercase font-bold">In Progress</span>
                  <div className="text-lg font-bold text-indigo-900 mt-1">
                    {overview.complaints.in_progress_complaints}
                  </div>
                </div>
                <div className="p-3 bg-emerald-50 rounded border border-emerald-200">
                  <span className="text-[10px] text-emerald-700 uppercase font-bold">Resolved / Closed</span>
                  <div className="text-lg font-bold text-emerald-900 mt-1">
                    {overview.complaints.resolved_complaints + overview.complaints.closed_complaints}
                  </div>
                </div>
              </div>
              <div className="flex items-center justify-between p-2.5 bg-slate-50 rounded border border-slate-200 text-xs">
                <span className="text-slate-600">Reopened by Residents:</span>
                <span className="font-semibold text-slate-900">{overview.complaints.reopened_count}</span>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Tower-by-Tower Breakdown Table */}
      {overview && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold flex items-center justify-between">
              <span className="flex items-center gap-2">
                <Building className="h-4 w-4 text-indigo-600" />
                <span>Tower-by-Tower Financial & Helpdesk Distribution</span>
              </span>
              <span className="text-xs text-slate-500">{overview.towers.length} Active Towers</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200 uppercase tracking-wider text-[11px]">
                  <tr>
                    <th className="py-2.5 px-3">Tower</th>
                    <th className="py-2.5 px-3">Name</th>
                    <th className="py-2.5 px-3 text-right">Flats</th>
                    <th className="py-2.5 px-3 text-right">Total Billed</th>
                    <th className="py-2.5 px-3 text-right">Collected</th>
                    <th className="py-2.5 px-3 text-right">Outstanding</th>
                    <th className="py-2.5 px-3 text-right">Open Issues</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-mono text-[11px]">
                  {overview.towers.map((tower) => (
                    <tr key={tower.tower_id} className="hover:bg-slate-50">
                      <td className="py-2.5 px-3 font-bold text-slate-900">{tower.tower_number}</td>
                      <td className="py-2.5 px-3 font-sans text-slate-700">{tower.tower_name}</td>
                      <td className="py-2.5 px-3 text-right">{tower.total_flats}</td>
                      <td className="py-2.5 px-3 text-right text-slate-900">{formatINR(tower.total_billed_paise)}</td>
                      <td className="py-2.5 px-3 text-right text-emerald-600 font-semibold">
                        {formatINR(tower.total_collected_paise)}
                      </td>
                      <td className="py-2.5 px-3 text-right text-rose-600 font-semibold">
                        {formatINR(tower.total_outstanding_paise)}
                      </td>
                      <td className="py-2.5 px-3 text-right font-sans">
                        <Badge variant={tower.open_complaints > 0 ? 'warning' : 'neutral'}>
                          {tower.open_complaints}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Monthly Financial Performance Trend */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold flex items-center justify-between">
            <span className="flex items-center gap-2">
              <ScrollText className="h-4 w-4 text-indigo-600" />
              <span>Historical Monthly Billing Statements</span>
            </span>
            <Badge variant="neutral">Financial Governance</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isMonthlyLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          ) : monthlyReports.length === 0 ? (
            <div className="p-4 text-center text-xs text-slate-500">
              No historical billing statements recorded.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200 uppercase tracking-wider text-[11px]">
                  <tr>
                    <th className="py-2.5 px-3">Period</th>
                    <th className="py-2.5 px-3 text-right">Invoices</th>
                    <th className="py-2.5 px-3 text-right">Billed</th>
                    <th className="py-2.5 px-3 text-right">Collected</th>
                    <th className="py-2.5 px-3 text-right">Outstanding</th>
                    <th className="py-2.5 px-3 text-right">Collection Rate</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-mono text-[11px]">
                  {monthlyReports.map((report) => (
                    <tr key={report.billing_period} className="hover:bg-slate-50">
                      <td className="py-2.5 px-3 font-bold text-slate-900">{report.billing_period}</td>
                      <td className="py-2.5 px-3 text-right">{report.total_invoices}</td>
                      <td className="py-2.5 px-3 text-right">{formatINR(report.total_billed_paise)}</td>
                      <td className="py-2.5 px-3 text-right text-emerald-600 font-semibold">
                        {formatINR(report.total_collected_paise)}
                      </td>
                      <td className="py-2.5 px-3 text-right text-rose-600 font-semibold">
                        {formatINR(report.total_outstanding_paise)}
                      </td>
                      <td className="py-2.5 px-3 text-right font-sans">
                        <Badge variant={report.collection_percentage >= 90 ? 'success' : report.collection_percentage >= 70 ? 'warning' : 'danger'}>
                          {report.collection_percentage.toFixed(1)}%
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
    </div>
  );
};
