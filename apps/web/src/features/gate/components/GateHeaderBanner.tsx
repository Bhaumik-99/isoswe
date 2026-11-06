import React from 'react';
import {
  ShieldCheck,
  Wifi,
  WifiOff,
  Globe,
  FileText,
  Database,
  LogOut,
  ArrowLeft,
} from 'lucide-react';
import { GateInfo } from '../../../types';
import {
  LANGUAGE_LABELS,
  SupportedLanguage,
  useLanguage,
} from '../../../i18n/LanguageContext';

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
}) => {
  const { language, setLanguage, t } = useLanguage();

  return (
    <header className="bg-slate-950 border-b border-slate-800 text-white sticky top-0 z-30 shadow-lg">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3 flex flex-wrap items-center justify-between gap-3">
        {/* Left: Brand & Active Gate Selector */}
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-xl bg-amber-500 text-slate-950 flex items-center justify-center font-extrabold shadow-md">
            <ShieldCheck className="h-6 w-6" />
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
                className={`px-2.5 py-1 rounded text-xs font-bold transition-colors ${
                  language === lang
                    ? 'bg-amber-500 text-slate-950'
                    : 'text-slate-300 hover:text-white hover:bg-slate-800'
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
    </header>
  );
};

