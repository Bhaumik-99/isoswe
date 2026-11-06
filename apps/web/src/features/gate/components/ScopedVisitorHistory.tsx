import React, { useState } from 'react';
import { Search, Image, X, Clock, AlertTriangle } from 'lucide-react';
import { GateFlatOption, VisitorRecord } from '../../../types';
import { gateService } from '../../../services/gateService';
import { ApiClientError } from '../../../services/apiClient';
import { useLanguage } from '../../../i18n/LanguageContext';

interface ScopedVisitorHistoryProps {
  visitors: VisitorRecord[];
  flats: GateFlatOption[];
  searchQuery: string;
  onSearchChange: (q: string) => void;
}

export const ScopedVisitorHistory: React.FC<ScopedVisitorHistoryProps> = ({
  visitors,
  flats,
  searchQuery,
  onSearchChange,
}) => {
  const { t } = useLanguage();
  const [selectedPhotoUrl, setSelectedPhotoUrl] = useState<string | null>(null);
  const [photoModalVisitor, setPhotoModalVisitor] = useState<string | null>(null);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const [isLoadingPhoto, setIsLoadingPhoto] = useState(false);

  const resolveFlatLabel = (flatId: string) => {
    const f = flats.find((x) => x.flat_id === flatId);
    return f ? `${f.tower_number}-${f.flat_number}` : flatId.substring(0, 8);
  };

  const handleOpenPhoto = async (v: VisitorRecord) => {
    setPhotoModalVisitor(v.visitor_name);
    setSelectedPhotoUrl(null);
    setPhotoError(null);
    setIsLoadingPhoto(true);
    try {
      const res = await gateService.getVisitorPhotoUrl(v.visitor_id);
      setSelectedPhotoUrl(res.photo_url);
    } catch (err: unknown) {
      if (err instanceof ApiClientError && err.status === 410) {
        setPhotoError(t.errors.photoExpired410);
      } else {
        setPhotoError(err instanceof Error ? err.message : t.errors.genericError);
      }
    } finally {
      setIsLoadingPhoto(false);
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 sm:p-6 shadow-xl text-white space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-4 border-b border-slate-800">
        <div>
          <h2 className="text-lg font-bold text-white">{t.gate.history.sectionTitle}</h2>
          <p className="text-xs text-slate-400 mt-0.5">{t.gate.history.sectionSubtitle}</p>
        </div>

        <div className="relative w-full sm:w-72">
          <Search className="h-4 w-4 text-slate-400 absolute left-3 top-3" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder={t.gate.history.searchPlaceholder}
            className="w-full pl-9 pr-3 py-2 rounded-xl bg-slate-950 border border-slate-700 text-white placeholder-slate-500 text-xs focus:outline-none focus:ring-2 focus:ring-amber-400"
          />
        </div>
      </div>

      {visitors.length === 0 ? (
        <div className="p-8 text-center text-slate-400 text-sm bg-slate-950/50 rounded-xl border border-slate-800">
          {t.common.noData}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400 uppercase tracking-wider">
                <th className="py-3 px-3">{t.gate.history.colVisitor}</th>
                <th className="py-3 px-3">{t.gate.history.colPhone}</th>
                <th className="py-3 px-3">{t.gate.history.colFlat}</th>
                <th className="py-3 px-3">{t.gate.history.colPurpose}</th>
                <th className="py-3 px-3">{t.gate.history.colApproval}</th>
                <th className="py-3 px-3">{t.gate.history.colEntryStatus}</th>
                <th className="py-3 px-3">{t.gate.history.colTimestamps}</th>
                <th className="py-3 px-3 text-right">{t.gate.history.colActions}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/70">
              {visitors.map((v) => (
                <tr key={v.visitor_id} className="hover:bg-slate-950/50">
                  <td className="py-3 px-3 font-bold text-white">{v.visitor_name}</td>
                  <td className="py-3 px-3 font-mono text-slate-300">
                    <div>{v.phone_masked}</div>
                    {v.vehicle_number && (
                      <div className="text-[11px] text-amber-300">{v.vehicle_number}</div>
                    )}
                  </td>
                  <td className="py-3 px-3 font-semibold text-indigo-300">
                    {resolveFlatLabel(v.destination_flat_id)}
                  </td>
                  <td className="py-3 px-3 text-slate-300">{v.purpose}</td>
                  <td className="py-3 px-3">
                    <span
                      className={`px-2 py-0.5 rounded-full text-[11px] font-bold ${
                        v.approval_status === 'APPROVED' || v.approval_status === 'AUTO_APPROVED'
                          ? 'bg-emerald-500/20 text-emerald-300'
                          : v.approval_status === 'REJECTED'
                            ? 'bg-rose-500/20 text-rose-300'
                            : 'bg-amber-500/20 text-amber-300'
                      }`}
                    >
                      {t.statuses.approval[v.approval_status] || v.approval_status}
                    </span>
                  </td>
                  <td className="py-3 px-3">
                    <span
                      className={`px-2 py-0.5 rounded-full text-[11px] font-bold ${
                        v.entry_status === 'CHECKED_IN'
                          ? 'bg-indigo-500/20 text-indigo-300'
                          : v.entry_status === 'CHECKED_OUT'
                            ? 'bg-slate-800 text-slate-300'
                            : 'bg-slate-800 text-amber-300'
                      }`}
                    >
                      {t.statuses.entry[v.entry_status] || v.entry_status}
                    </span>
                  </td>
                  <td className="py-3 px-3 text-slate-400 font-mono text-[11px]">
                    <div>Reg: {new Date(v.created_at).toLocaleTimeString()}</div>
                    {v.entry_time && <div>In: {new Date(v.entry_time).toLocaleTimeString()}</div>}
                    {v.exit_time && <div>Out: {new Date(v.exit_time).toLocaleTimeString()}</div>}
                  </td>
                  <td className="py-3 px-3 text-right">
                    <button
                      type="button"
                      onClick={() => handleOpenPhoto(v)}
                      className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-indigo-300 font-semibold text-[11px] border border-slate-700"
                    >
                      <Image className="h-3.5 w-3.5" />
                      <span>{t.common.viewPhoto}</span>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Presigned Photo Modal */}
      {photoModalVisitor && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4"
          role="dialog"
          aria-modal="true"
        >
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full overflow-hidden shadow-2xl">
            <div className="px-5 py-4 bg-slate-950 border-b border-slate-800 flex items-center justify-between">
              <div className="text-sm font-bold text-white">{photoModalVisitor}</div>
              <button
                type="button"
                onClick={() => setPhotoModalVisitor(null)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="p-5 space-y-3">
              {isLoadingPhoto ? (
                <div className="py-12 text-center text-slate-400 text-xs">{t.common.loading}</div>
              ) : photoError ? (
                <div className="p-4 rounded-xl bg-amber-950/40 border border-amber-500/40 text-amber-200 text-xs flex items-start gap-2.5">
                  <AlertTriangle className="h-5 w-5 text-amber-400 flex-shrink-0" />
                  <span>{photoError}</span>
                </div>
              ) : selectedPhotoUrl ? (
                <div className="space-y-2">
                  <img
                    src={selectedPhotoUrl}
                    alt={photoModalVisitor}
                    className="w-full h-64 object-cover rounded-xl border border-slate-700"
                  />
                  <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono">
                    <span className="flex items-center gap-1">
                      <Clock className="h-3 w-3 text-amber-400" />
                      15-Min Presigned URL
                    </span>
                    <span>90-Day Retention Policy</span>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

