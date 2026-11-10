import React, { useState } from 'react';
import {
  Database,
  X,
  RefreshCw,
  Trash2,
  ShieldAlert,
  CheckCircle2,
  AlertTriangle,
  Clock,
} from 'lucide-react';
import { OfflineVisitorQueueItem } from '../../../types';
import { useLanguage } from '../../../i18n/LanguageContext';
import { useGateMigrationStatus, retryGateMigration } from '../offline/gateIndexedDB';
import { Portal } from '../../../components/ui/Portal';

interface OfflineQueueDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  items: OfflineVisitorQueueItem[];
  isOnline: boolean;
  isSyncing: boolean;
  onSyncNow: () => void;
  onRetryFailed: () => void;
  onClearSynced: () => void;
}

export const OfflineQueueDrawer: React.FC<OfflineQueueDrawerProps> = ({
  isOpen,
  onClose,
  items,
  isOnline,
  isSyncing,
  onSyncNow,
  onRetryFailed,
  onClearSynced,
}) => {
  const { t } = useLanguage();
  const migrationStatus = useGateMigrationStatus();
  const [isRetryingMigration, setIsRetryingMigration] = useState(false);

  const handleRetryMigration = async () => {
    setIsRetryingMigration(true);
    try {
      await retryGateMigration();
    } catch {
      // Handled via migration status hook
    } finally {
      setIsRetryingMigration(false);
    }
  };

  if (!isOpen) return null;

  return (
    <Portal>
      <div
        className="fixed inset-0 z-50 flex justify-end bg-black/75 backdrop-blur-sm"
        role="dialog"
        aria-modal="true"
      >
      <div className="bg-slate-900 border-l border-slate-800 text-white w-full max-w-xl h-full flex flex-col shadow-2xl">
        {/* Header */}
        <div className="px-6 py-4 bg-slate-950 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-amber-500/20 text-amber-300 border border-amber-500/40">
              <Database className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white">
                {t.gate.offlineDrawer.drawerTitle}
              </h2>
              <p className="text-xs text-slate-400">{t.gate.offlineDrawer.drawerSubtitle}</p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Operational Migration Warning */}
        {migrationStatus.status === 'FAILED' && (
          <div className="px-6 py-3 bg-rose-950/80 border-b border-rose-500/50 text-rose-200 text-xs flex items-start justify-between gap-3">
            <div className="flex items-start gap-2.5">
              <AlertTriangle className="h-4 w-4 text-rose-400 flex-shrink-0 mt-0.5 animate-pulse" />
              <div>
                <p className="font-bold text-rose-100">Encryption Migration Incomplete</p>
                <p className="text-rose-300 text-[11px] mt-0.5">
                  {migrationStatus.unmigratedCount > 0
                    ? `${migrationStatus.unmigratedCount} unencrypted record(s) pending encryption.`
                    : 'Offline queue encryption migration failed.'}{' '}
                  {migrationStatus.error}
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={handleRetryMigration}
              disabled={isRetryingMigration}
              className="px-2.5 py-1 bg-rose-900 hover:bg-rose-800 text-white rounded text-xs font-semibold flex items-center gap-1 flex-shrink-0 border border-rose-500 disabled:opacity-50"
            >
              <RefreshCw
                className={`h-3 w-3 ${isRetryingMigration ? 'animate-spin' : ''}`}
              />
              <span>Retry</span>
            </button>
          </div>
        )}

        {/* Security Rule Banner */}
        <div className="px-6 py-3 bg-indigo-950/40 border-b border-indigo-500/30 text-indigo-200 text-xs flex items-center gap-2">
          <ShieldAlert className="h-4 w-4 text-indigo-400 flex-shrink-0" />
          <span>{t.gate.offlineDrawer.pendingApprovalRuleNote}</span>
        </div>

        {/* Action Buttons */}
        <div className="px-6 py-3 bg-slate-900 border-b border-slate-800 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={!isOnline || isSyncing || items.length === 0}
            onClick={onSyncNow}
            className="px-3.5 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs flex items-center gap-1.5 disabled:opacity-40"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isSyncing ? 'animate-spin' : ''}`} />
            <span>{t.gate.offlineDrawer.syncNowBtn}</span>
          </button>

          <button
            type="button"
            disabled={!isOnline || isSyncing}
            onClick={onRetryFailed}
            className="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-semibold text-xs border border-slate-700 disabled:opacity-40"
          >
            {t.gate.offlineDrawer.retryFailedBtn}
          </button>

          <button
            type="button"
            onClick={onClearSynced}
            className="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold text-xs border border-slate-700 flex items-center gap-1 ml-auto"
          >
            <Trash2 className="h-3.5 w-3.5" />
            <span>{t.gate.offlineDrawer.clearSyncedBtn}</span>
          </button>
        </div>

        {/* Queue Items */}
        <div className="flex-1 overflow-y-auto p-6 space-y-3">
          {items.length === 0 ? (
            <div className="p-8 text-center text-slate-400 text-sm bg-slate-950/60 rounded-xl border border-slate-800">
              {t.gate.offlineDrawer.emptyQueueMessage}
            </div>
          ) : (
            items.map((item) => (
              <div
                key={item.client_event_id}
                className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="font-bold text-sm text-white">{item.visitor_name}</div>
                  {item.sync_status === 'QUEUED' && (
                    <span className="px-2.5 py-0.5 rounded-full bg-amber-500/20 text-amber-300 text-[11px] font-bold flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {t.gate.offlineDrawer.statusQueued}
                    </span>
                  )}
                  {item.sync_status === 'SYNCING' && (
                    <span className="px-2.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 text-[11px] font-bold">
                      {t.gate.offlineDrawer.statusSyncing}
                    </span>
                  )}
                  {item.sync_status === 'SYNCED' && (
                    <span className="px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 text-[11px] font-bold flex items-center gap-1">
                      <CheckCircle2 className="h-3 w-3" />
                      {t.gate.offlineDrawer.statusSynced}
                    </span>
                  )}
                  {item.sync_status === 'CONFLICT' && (
                    <span className="px-2.5 py-0.5 rounded-full bg-rose-500/20 text-rose-300 text-[11px] font-bold flex items-center gap-1">
                      <AlertTriangle className="h-3 w-3" />
                      {t.gate.offlineDrawer.statusConflict}
                    </span>
                  )}
                  {item.sync_status === 'FAILED' && (
                    <span className="px-2.5 py-0.5 rounded-full bg-rose-500/20 text-rose-300 text-[11px] font-bold">
                      {t.gate.offlineDrawer.statusFailed}
                    </span>
                  )}
                </div>

                <div className="text-xs text-slate-400 flex flex-wrap gap-3">
                  <span>{item.phone_number}</span>
                  <span>•</span>
                  <span>Flat: {item.flat_label || item.destination_flat_id.substring(0, 8)}</span>
                  <span>•</span>
                  <span>{item.purpose}</span>
                </div>

                <div className="text-[10px] font-mono text-slate-500 flex items-center justify-between pt-1 border-t border-slate-900">
                  <span>Event ID: {item.client_event_id.substring(0, 12)}...</span>
                  <span>SHA256: {item.payload_hash.substring(0, 14)}...</span>
                </div>

                {item.error_message && (
                  <div className="p-2 rounded bg-rose-950/60 border border-rose-700 text-rose-200 text-[11px] font-mono">
                    {item.error_message}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>
      </div>
    </Portal>
  );
};

