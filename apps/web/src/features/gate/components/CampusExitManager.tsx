import React, { useState } from 'react';
import { LogOut, Search, CheckCircle2, AlertCircle } from 'lucide-react';
import { GateInfo, VisitorRecord } from '../../../types';
import { gateService } from '../../../services/gateService';
import { useLanguage } from '../../../i18n/LanguageContext';

interface CampusExitManagerProps {
  activeGate: GateInfo | null;
  visitors: VisitorRecord[];
  onCheckedOut: () => void;
}

export const CampusExitManager: React.FC<CampusExitManagerProps> = ({
  activeGate,
  visitors,
  onCheckedOut,
}) => {
  const { t } = useLanguage();
  const [searchQuery, setSearchQuery] = useState('');
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [toastMsg, setToastMsg] = useState<string | null>(null);

  const insideVisitors = visitors.filter((v) => v.entry_status === 'CHECKED_IN');

  const filtered = insideVisitors.filter((v) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.trim().toLowerCase();
    return (
      v.visitor_name.toLowerCase().includes(q) ||
      v.phone_masked.toLowerCase().includes(q) ||
      (v.vehicle_number && v.vehicle_number.toLowerCase().includes(q))
    );
  });

  const handleCheckOut = async (visitorId: string) => {
    setProcessingId(visitorId);
    setErrorMsg(null);
    setToastMsg(null);
    try {
      await gateService.checkOutVisitor(visitorId, activeGate?.gate_id);
      setToastMsg(t.gate.campusExit.checkedOutSuccess);
      onCheckedOut();
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : t.errors.genericError);
    } finally {
      setProcessingId(null);
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 sm:p-6 shadow-xl text-white space-y-4">
      <div className="pb-4 border-b border-slate-800">
        <h2 className="text-lg font-bold text-white">{t.gate.campusExit.sectionTitle}</h2>
        <p className="text-xs text-slate-400 mt-0.5">{t.gate.campusExit.sectionSubtitle}</p>
      </div>

      {/* Search Bar */}
      <div className="relative">
        <Search className="h-4 w-4 text-slate-400 absolute left-3.5 top-3.5" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder={t.gate.campusExit.searchPlaceholder}
          className="w-full pl-10 pr-4 py-3 rounded-xl bg-slate-950 border border-slate-700 text-white placeholder-slate-500 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
        />
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
          {t.gate.campusExit.noInsideVisitors}
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((v) => (
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
                  {v.entry_time && (
                    <>
                      <span>•</span>
                      <span>
                        In:{' '}
                        {new Date(v.entry_time).toLocaleTimeString([], {
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </span>
                    </>
                  )}
                </div>
              </div>

              <button
                type="button"
                disabled={processingId === v.visitor_id}
                onClick={() => handleCheckOut(v.visitor_id)}
                className="px-5 py-3 rounded-xl bg-indigo-500 hover:bg-indigo-400 text-slate-950 font-extrabold text-xs uppercase tracking-wider flex items-center justify-center gap-2 shadow-md"
              >
                <LogOut className="h-4 w-4" />
                <span>
                  {processingId === v.visitor_id
                    ? t.common.loading
                    : t.gate.campusExit.checkOutBtn}
                </span>
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

