import React, { useState } from 'react';
import {
  ShieldCheck,
  Wifi,
  WifiOff,
  Globe,
  FileText,
  Database,
  LogOut,
  ArrowLeft,
  AlertTriangle,
  RefreshCw,
} from 'lucide-react';
import { GateInfo } from '../../../types';
import {
  LANGUAGE_LABELS,
  SupportedLanguage,
  useLanguage,
} from '../../../i18n/LanguageContext';
import {
  useGateMigrationStatus,
  retryGateMigration,
  GateMigrationStatus,
} from '../offline/gateIndexedDB';

interface GateHeaderBannerProps {
  guardName: string;
  activeGate: GateInfo | null;
  availableGates: GateInfo[];
  onSelectGate: (gate: GateInfo) => void;
  isOnline: boolean;
  offlineQueueCount: number;
  onOpenPrivacyNotice: () => void;
  onOpenOfflineDrawer: () => void;
  onBackToStaff: () => void;
  onLogout: () => void;
  migrationStatus?: GateMigrationStatus;
  onRetryMigration?: () => void;
}

export const GateHeaderBanner: React.FC<GateHeaderBannerProps> = ({
  guardName,
  activeGate,
  availableGates,
  onSelectGate,
  isOnline,
  offlineQueueCount,
  onOpenPrivacyNotice,
  onOpenOfflineDrawer,
  onBackToStaff,
  onLogout,
  migrationStatus: propMigrationStatus,
  onRetryMigration,
}) => {
  const { language, setLanguage, t } = useLanguage();
  const liveMigrationStatus = useGateMigrationStatus();
  const effectiveMigration = propMigrationStatus || liveMigrationStatus;
  const [isRetryingMigration, setIsRetryingMigration] = useState(false);

  const handleRetryMigration = async () => {
    if (onRetryMigration) {
      onRetryMigration();
      return;
    }
    setIsRetryingMigration(true);
    try {
      await retryGateMigration();
    } catch {
      // Status updated in hook
    } finally {
      setIsRetryingMigration(false);
    }
  };

  return (
    <header className="bg-[#000000] border-b border-[#2a2a2c] text-[#ffffff]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3 flex flex-wrap items-center justify-between gap-3">
        {/* Left: Brand & Active Gate Selector */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-[11px] bg-[#0066cc] text-[#ffffff] flex items-center justify-center">
            <ShieldCheck className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base sm:text-lg font-bold tracking-tight text-white">
                {t.gate.tabletTitle}
              </h1>
              <span
                className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider ${
                  isOnline
                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                    : 'bg-amber-500/20 text-amber-300 border border-amber-500/50 animate-pulse'
                }`}
              >
                {isOnline ? <Wifi className="h-3.5 w-3.5" /> : <WifiOff className="h-3.5 w-3.5" />}
                {isOnline ? t.common.online : t.common.offline}
              </span>
            </div>
            <p className="text-xs text-slate-400 hidden sm:block">{t.gate.tabletSubtitle}</p>
          </div>
        </div>

        {/* Center: Gate Selector & Guard Identity */}
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          {availableGates.length > 1 ? (
            <div className="flex items-center gap-2 bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5">
              <span className="text-xs text-slate-400 font-semibold">
                {t.gate.assignedGateLabel}:
              </span>
              <select
                aria-label={t.gate.switchGateLabel}
                value={activeGate?.gate_id || ''}
                onChange={(e) => {
                  const found = availableGates.find((g) => g.gate_id === e.target.value);
                  if (found) onSelectGate(found);
                }}
                className="bg-slate-800 text-amber-300 text-xs font-bold rounded px-2 py-1 border border-slate-600 focus:outline-none focus:ring-2 focus:ring-amber-400"
              >
                {availableGates.map((g) => (
                  <option key={g.gate_id} value={g.gate_id}>
                    Gate #{g.gate_number} — {g.gate_name}
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <div className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs">
              <span className="text-slate-400 mr-1.5">{t.gate.assignedGateLabel}:</span>
              <span className="font-bold text-amber-300">
                {activeGate
                  ? `Gate #${activeGate.gate_number} — ${activeGate.gate_name}`
                  : 'Gate #1'}
              </span>
            </div>
          )}

          {/* Language Switcher (EN / HI / MR) */}
          <div
            className="flex items-center bg-slate-900 border border-slate-700 rounded-lg p-1"
            role="group"
            aria-label={t.common.languageLabel}
          >
            <Globe className="h-3.5 w-3.5 text-slate-400 mx-1.5" />
            {(['en', 'hi', 'mr'] as SupportedLanguage[]).map((lang) => (
              <button
                key={lang}
                type="button"
                onClick={() => setLanguage(lang)}
                className={`px-2.5 py-1 rounded-[8px] text-xs font-semibold active:scale-95 transition-transform cursor-pointer ${
                  language === lang
                    ? 'bg-[#0066cc] text-[#ffffff]'
                    : 'text-[#cccccc] hover:text-[#ffffff] hover:bg-[#1d1d1f]'
                }`}
              >
                {LANGUAGE_LABELS[lang]}
              </button>
            ))}
          </div>

          {/* Privacy Notice Button */}
          <button
            type="button"
            onClick={onOpenPrivacyNotice}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-900 hover:bg-slate-800 text-indigo-300 border border-slate-700 transition-colors"
          >
            <FileText className="h-3.5 w-3.5" />
            <span>{t.privacyNotice.buttonLabel}</span>
          </button>

          {/* Offline Queue Drawer Button */}
          <button
            type="button"
            onClick={onOpenOfflineDrawer}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold border transition-colors ${
              offlineQueueCount > 0
                ? 'bg-amber-500/20 border-amber-400 text-amber-300 hover:bg-amber-500/30'
                : 'bg-slate-900 border-slate-700 text-slate-300 hover:bg-slate-800'
            }`}
          >
            <Database className="h-3.5 w-3.5" />
            <span>{t.gate.kpiOfflineQueue}</span>
            <span className="px-1.5 py-0.5 rounded-full bg-slate-950 text-amber-300 font-mono text-[11px]">
              {offlineQueueCount}
            </span>
          </button>

          {/* Guard Profile & Logout */}
          <div className="flex items-center gap-2 pl-2 border-l border-slate-800">
            <span className="hidden lg:inline text-xs text-slate-300 font-medium">
              {guardName}
            </span>
            <button
              type="button"
              onClick={onBackToStaff}
              className="p-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-white border border-slate-700 text-xs flex items-center gap-1"
              title={t.common.backToStaff}
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">{t.common.backToStaff}</span>
            </button>
            <button
              type="button"
              onClick={onLogout}
              className="p-2 rounded-lg bg-slate-900 hover:bg-rose-950 text-slate-300 hover:text-rose-300 border border-slate-700"
              title={t.common.logout}
              aria-label={t.common.logout}
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Operational Warning Banner when Migration Fails */}
      {effectiveMigration.status === 'FAILED' && (
        <div
          role="alert"
          aria-live="assertive"
          className="bg-rose-950 border-t border-rose-500/50 text-rose-100 px-4 py-2.5 text-xs flex flex-wrap items-center justify-between gap-3 shadow-inner"
        >
          <div className="flex items-center gap-2.5">
            <AlertTriangle className="h-4 w-4 text-rose-400 flex-shrink-0 animate-pulse" />
            <div>
              <span className="font-bold uppercase tracking-wider text-rose-300 mr-2">
                Operational Warning:
              </span>
              <span>
                Offline database encryption migration incomplete
                {effectiveMigration.unmigratedCount > 0
                  ? ` (${effectiveMigration.unmigratedCount} unencrypted record${
                      effectiveMigration.unmigratedCount === 1 ? '' : 's'
                    } pending)`
                  : ''}
                . {effectiveMigration.error || 'Please retry migration.'}
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={handleRetryMigration}
            disabled={isRetryingMigration}
            className="px-3 py-1 bg-rose-900 hover:bg-rose-800 text-rose-100 rounded-lg text-xs font-bold border border-rose-500 flex items-center gap-1.5 flex-shrink-0 disabled:opacity-50"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${isRetryingMigration ? 'animate-spin' : ''}`}
            />
            <span>Retry Migration</span>
          </button>
        </div>
      )}
    </header>
  );
};

