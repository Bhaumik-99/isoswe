import React, { useState } from 'react';
import {
  CheckCircle2,
  Clock,
  XCircle,
  LogIn,
  RefreshCw,
  AlertCircle,
} from 'lucide-react';
import { VisitorRecord } from '../../../types';
import { gateService } from '../../../services/gateService';
import { useLanguage } from '../../../i18n/LanguageContext';

interface LiveApprovalMonitorProps {
  visitors: VisitorRecord[];
  isLoading: boolean;
  onRefresh: () => void;
  onCheckedIn: () => void;
}

export const LiveApprovalMonitor: React.FC<LiveApprovalMonitorProps> = ({
  visitors,
  isLoading,
  onRefresh,
  onCheckedIn,
}) => {
  const { t } = useLanguage();
  const [filter, setFilter] = useState<'ALL' | 'PENDING' | 'APPROVED' | 'REJECTED'>('ALL');
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [toastMsg, setToastMsg] = useState<string | null>(null);

  // Only show visitors that haven't checked out yet in the Live Approval & Entry queue
  const candidates = visitors.filter((v) => v.entry_status === 'EXPECTED');

  const filtered = candidates.filter((v) => {
    if (filter === 'ALL') return true;
    if (filter === 'APPROVED') {
      return v.approval_status === 'APPROVED' || v.approval_status === 'AUTO_APPROVED';
    }
    return v.approval_status === filter;
  });

  const handleCheckIn = async (visitorId: string) => {
    setProcessingId(visitorId);
    setErrorMsg(null);
    setToastMsg(null);
    try {
      await gateService.checkInVisitor(visitorId);
      setToastMsg(t.gate.liveMonitor.checkedInSuccess);
      onCheckedIn();
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : t.errors.genericError);
    } finally {
      setProcessingId(null);
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 sm:p-6 shadow-xl text-white space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-4 border-b border-slate-800">
        <div>
          <h2 className="text-lg font-bold text-white">{t.gate.liveMonitor.sectionTitle}</h2>
          <p className="text-xs text-slate-400 mt-0.5">{t.gate.liveMonitor.sectionSubtitle}</p>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-bold text-slate-200 border border-slate-700"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          <span>{t.common.refresh}</span>
        </button>
      </div>

      {/* Filter Pills */}
      <div className="flex flex-wrap gap-2">
        {(
          [
            { key: 'ALL', label: t.gate.liveMonitor.filterAll },
            { key: 'PENDING', label: t.gate.liveMonitor.filterPending },
            { key: 'APPROVED', label: t.gate.liveMonitor.filterApproved },
            { key: 'REJECTED', label: t.gate.liveMonitor.filterRejected },
          ] as const
        ).map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setFilter(tab.key)}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-colors ${
              filter === tab.key
                ? 'bg-amber-500 text-slate-950'
                : 'bg-slate-950 text-slate-300 border border-slate-800 hover:border-slate-700'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {errorMsg && (
        <div className="p-3 rounded-xl bg-rose-950/70 border border-rose-500/50 text-rose-200 text-xs flex items-center gap-2">
          <AlertCircle className="h-4 w-4 text-rose-400 flex-shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      {toastMsg && (
        <div className="p-3 rounded-xl bg-emerald-950/70 border border-emerald-500/50 text-emerald-200 text-xs flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 text-emerald-400 flex-shrink-0" />
          <span>{toastMsg}</span>
        </div>
      )}

      {filtered.length === 0 ? (
        <div className="p-8 text-center text-slate-400 text-sm bg-slate-950/50 rounded-xl border border-slate-800">
          {t.common.noData}
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((v) => {
            const canCheckIn =
              v.approval_status === 'APPROVED' || v.approval_status === 'AUTO_APPROVED';
            return (
              <div
                key={v.visitor_id}
                className="p-4 rounded-xl bg-slate-950 border border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-4"
              >
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-bold text-base text-white">{v.visitor_name}</span>
                    <span className="text-xs font-mono text-slate-400">{v.phone_masked}</span>
                    {v.vehicle_number && (
                      <span className="px-2 py-0.5 rounded bg-slate-800 text-amber-300 font-mono text-xs">
                        {v.vehicle_number}
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-slate-400 flex flex-wrap items-center gap-3">
                    <span>
                      {t.gate.history.colPurpose}: <strong className="text-slate-200">{v.purpose}</strong>
                    </span>
                    <span>•</span>
                    <span>
                      {new Date(v.created_at).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-3">
                  {/* Approval Badge */}
                  {v.approval_status === 'PENDING' && (
                    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40 text-xs font-bold">
                      <Clock className="h-3.5 w-3.5" />
                      {t.statuses.approval.PENDING}
                    </span>
                  )}
                  {(v.approval_status === 'APPROVED' || v.approval_status === 'AUTO_APPROVED') && (
                    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-xs font-bold">
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      {t.statuses.approval[v.approval_status]}
                    </span>
                  )}
                  {v.approval_status === 'REJECTED' && (
                    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/40 text-xs font-bold">
                      <XCircle className="h-3.5 w-3.5" />
                      {t.statuses.approval.REJECTED}
                    </span>
                  )}

                  {/* Check-In Button (Enabled strictly when APPROVED or AUTO_APPROVED) */}
                  {canCheckIn ? (
                    <button
                      type="button"
                      disabled={processingId === v.visitor_id}
                      onClick={() => handleCheckIn(v.visitor_id)}
                      className="px-4 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-extrabold text-xs uppercase tracking-wider flex items-center gap-1.5 shadow-md"
                    >
                      <LogIn className="h-4 w-4" />
                      <span>
                        {processingId === v.visitor_id
                          ? t.common.loading
                          : t.gate.liveMonitor.checkInBtn}
                      </span>
                    </button>
                  ) : v.approval_status === 'PENDING' ? (
                    <span className="text-xs text-slate-400 italic">
                      {t.gate.liveMonitor.awaitingResidentNotice}
                    </span>
                  ) : (
                    <span className="text-xs text-rose-400 font-semibold">
                      {t.gate.liveMonitor.rejectedByResidentNotice}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

