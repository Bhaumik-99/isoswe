import React, { useState, useEffect, useCallback } from 'react';
import {
  Bell,
  RefreshCw,
  Mail,
  MessageSquare,
  Smartphone,
  CheckCircle,
  AlertTriangle,
  XCircle,
  Clock,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
  Send,
} from 'lucide-react';
import { notificationService } from '../../../services/notificationService';
import { StaffNotificationOverview } from '../../../types';
import { Badge } from '../../../components/ui/Badge';
import { Button } from '../../../components/ui/Button';

export const StaffNotificationsPage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<StaffNotificationOverview>({
    items: [],
    total: 0,
    delivered_count: 0,
    failed_count: 0,
    retrying_count: 0,
    page: 1,
    page_size: 20,
    total_pages: 1,
  });
  const [page, setPage] = useState(1);

  const loadOverview = useCallback(async () => {
    setLoading(true);
    try {
      const res = await notificationService.getStaffOverview(page, 20);
      setData(res);
    } catch {
      // Ignore
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    loadOverview();
  }, [loadOverview]);

  const getChannelIcon = (channel: string) => {
    switch (channel.toUpperCase()) {
      case 'EMAIL':
        return <Mail className="h-4 w-4 text-sky-600" />;
      case 'SMS':
        return <MessageSquare className="h-4 w-4 text-emerald-600" />;
      default:
        return <Smartphone className="h-4 w-4 text-indigo-600" />;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'DELIVERED':
      case 'SENT':
        return (
          <Badge variant="success" className="flex items-center gap-1">
            <CheckCircle className="h-3 w-3" />
            <span>{status}</span>
          </Badge>
        );
      case 'RETRYING':
        return (
          <Badge variant="warning" className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            <span>RETRYING</span>
          </Badge>
        );
      case 'FAILED':
        return (
          <Badge variant="danger" className="flex items-center gap-1">
            <XCircle className="h-3 w-3" />
            <span>FAILED</span>
          </Badge>
        );
      case 'SUPPRESSED':
        return (
          <Badge variant="neutral" className="flex items-center gap-1">
            <span>SUPPRESSED</span>
          </Badge>
        );
      default:
        return <Badge variant="info">{status}</Badge>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header Card */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <ShieldCheck className="h-6 w-6 text-indigo-600" />
            <h1 className="text-xl font-bold text-slate-900">Notification Delivery Operations</h1>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Real-time multi-channel delivery audit, exponential backoff retries, and provider failure telemetry across all 2,400 units.
          </p>
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={loadOverview}
          disabled={loading}
          className="flex items-center gap-1.5 self-start md:self-auto"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh Metrics</span>
        </Button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white rounded-xl p-5 border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Total Dispatches
            </span>
            <Send className="h-4 w-4 text-indigo-600" />
          </div>
          <p className="text-2xl font-bold text-slate-900 mt-2">{data.total.toLocaleString()}</p>
          <span className="text-[11px] text-slate-400">All communication channels</span>
        </div>

        <div className="bg-white rounded-xl p-5 border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Delivered
            </span>
            <CheckCircle className="h-4 w-4 text-emerald-600" />
          </div>
          <p className="text-2xl font-bold text-emerald-600 mt-2">
            {data.delivered_count.toLocaleString()}
          </p>
          <span className="text-[11px] text-slate-400">Confirmed deliveries</span>
        </div>

        <div className="bg-white rounded-xl p-5 border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              In Retry Backoff
            </span>
            <Clock className="h-4 w-4 text-amber-500" />
          </div>
          <p className="text-2xl font-bold text-amber-600 mt-2">
            {data.retrying_count.toLocaleString()}
          </p>
          <span className="text-[11px] text-slate-400">Automatic exponential backoff</span>
        </div>

        <div className="bg-white rounded-xl p-5 border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Failed / Suppressed
            </span>
            <AlertTriangle className="h-4 w-4 text-rose-500" />
          </div>
          <p className="text-2xl font-bold text-rose-600 mt-2">
            {data.failed_count.toLocaleString()}
          </p>
          <span className="text-[11px] text-slate-400">Permanent failures & opt-outs</span>
        </div>
      </div>

      {/* Deliveries Audit Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
          <h3 className="font-bold text-sm text-slate-900">Recent Delivery Log</h3>
          <span className="text-xs text-slate-500">Page {data.page} of {data.total_pages}</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-semibold uppercase tracking-wider">
              <tr>
                <th className="py-3 px-4">Channel</th>
                <th className="py-3 px-4">Provider</th>
                <th className="py-3 px-4">Recipient ID</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4 text-center">Attempts</th>
                <th className="py-3 px-4">Error Code / Details</th>
                <th className="py-3 px-4">Timestamp</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td colSpan={7} className="text-center py-12 text-slate-400">
                    Loading delivery audit log...
                  </td>
                </tr>
              ) : data.items.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center py-12 text-slate-400">
                    <Bell className="h-8 w-8 mx-auto text-slate-300 mb-2 stroke-1" />
                    No delivery records captured yet.
                  </td>
                </tr>
              ) : (
                data.items.map((deliv) => (
                  <tr key={deliv.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="py-3 px-4 flex items-center gap-2 font-medium text-slate-800">
                      {getChannelIcon(deliv.channel)}
                      <span>{deliv.channel}</span>
                    </td>
                    <td className="py-3 px-4 font-mono text-[11px] text-slate-600">
                      {deliv.provider}
                    </td>
                    <td className="py-3 px-4 font-mono text-[11px] text-slate-500">
                      {deliv.recipient_user_id.slice(0, 8)}...
                    </td>
                    <td className="py-3 px-4">{getStatusBadge(deliv.status)}</td>
                    <td className="py-3 px-4 text-center font-semibold text-slate-700">
                      {deliv.attempt_count}
                    </td>
                    <td className="py-3 px-4 max-w-[200px]">
                      {deliv.last_error_code ? (
                        <div>
                          <span className="font-mono text-[10px] text-rose-600 bg-rose-50 px-1.5 py-0.5 rounded">
                            {deliv.last_error_code}
                          </span>
                          {deliv.last_error_message && (
                            <p className="text-[10px] text-slate-400 truncate mt-0.5" title={deliv.last_error_message}>
                              {deliv.last_error_message}
                            </p>
                          )}
                        </div>
                      ) : (
                        <span className="text-slate-300">—</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-slate-500 whitespace-nowrap">
                      {new Date(deliv.created_at).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                      })}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Table Pagination */}
        {data.total_pages > 1 && (
          <div className="flex items-center justify-between px-6 py-3 border-t border-slate-200 bg-slate-50">
            <span className="text-xs text-slate-500">
              Showing {data.items.length} of {data.total} delivery attempts
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                <ChevronLeft className="h-3 w-3 mr-1" />
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= data.total_pages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
                <ChevronRight className="h-3 w-3 ml-1" />
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
