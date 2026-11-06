import React from 'react';
import { Shield, X, Clock, Lock, FileCheck2, PhoneCall } from 'lucide-react';
import {
  LANGUAGE_LABELS,
  SupportedLanguage,
  useLanguage,
} from '../../../i18n/LanguageContext';

interface GatePrivacyNoticeModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const GatePrivacyNoticeModal: React.FC<GatePrivacyNoticeModalProps> = ({
  isOpen,
  onClose,
}) => {
  const { language, setLanguage, t, privacyNoticeVersion } = useLanguage();

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="privacy-notice-title"
    >
      <div className="bg-slate-900 border border-slate-700 text-white rounded-2xl max-w-2xl w-full shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 bg-slate-950 border-b border-slate-800 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-indigo-500/20 text-indigo-300 border border-indigo-500/40">
              <Shield className="h-5 w-5" />
            </div>
            <div>
              <h2 id="privacy-notice-title" className="text-base font-bold text-white">
                {t.privacyNotice.modalTitle}
              </h2>
              <span className="text-xs font-mono text-amber-300">
                Version: {privacyNoticeVersion} • Retention: 90 Days
              </span>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
            aria-label={t.common.close}
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Language Tabs inside Modal */}
        <div className="px-6 py-3 bg-slate-900/90 border-b border-slate-800 flex items-center justify-between">
          <span className="text-xs text-slate-400 font-semibold uppercase tracking-wider">
            {t.common.languageLabel}
          </span>
          <div className="flex gap-2">
            {(['en', 'hi', 'mr'] as SupportedLanguage[]).map((lang) => (
              <button
                key={lang}
                type="button"
                onClick={() => setLanguage(lang)}
                className={`px-3 py-1 rounded-md text-xs font-bold transition-colors ${
                  language === lang
                    ? 'bg-amber-500 text-slate-950'
                    : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
                }`}
              >
                {LANGUAGE_LABELS[lang]}
              </button>
            ))}
          </div>
        </div>

        {/* Body Sections */}
        <div className="p-6 space-y-4 max-h-[70vh] overflow-y-auto text-sm leading-relaxed">
          <div className="p-4 rounded-xl bg-slate-950/70 border border-slate-800">
            <h3 className="font-bold text-amber-300 flex items-center gap-2 mb-1">
              <FileCheck2 className="h-4 w-4" />
              {t.privacyNotice.collectionTitle}
            </h3>
            <p className="text-slate-300 text-xs sm:text-sm">{t.privacyNotice.collectionBody}</p>
          </div>

          <div className="p-4 rounded-xl bg-slate-950/70 border border-slate-800">
            <h3 className="font-bold text-indigo-300 flex items-center gap-2 mb-1">
              <Shield className="h-4 w-4" />
              {t.privacyNotice.purposeTitle}
            </h3>
            <p className="text-slate-300 text-xs sm:text-sm">{t.privacyNotice.purposeBody}</p>
          </div>

          <div className="p-4 rounded-xl bg-slate-950/70 border border-slate-800">
            <h3 className="font-bold text-emerald-300 flex items-center gap-2 mb-1">
              <Lock className="h-4 w-4" />
              {t.privacyNotice.accessTitle}
            </h3>
            <p className="text-slate-300 text-xs sm:text-sm">{t.privacyNotice.accessBody}</p>
          </div>

          <div className="p-4 rounded-xl bg-amber-950/30 border border-amber-500/40">
            <h3 className="font-bold text-amber-300 flex items-center gap-2 mb-1">
              <Clock className="h-4 w-4" />
              {t.privacyNotice.retentionTitle}
            </h3>
            <p className="text-amber-100 text-xs sm:text-sm">{t.privacyNotice.retentionBody}</p>
          </div>

          <div className="p-4 rounded-xl bg-slate-950/70 border border-slate-800">
            <h3 className="font-bold text-slate-200 flex items-center gap-2 mb-1">
              <PhoneCall className="h-4 w-4 text-indigo-400" />
              {t.privacyNotice.grievanceTitle}
            </h3>
            <p className="text-slate-300 text-xs sm:text-sm">{t.privacyNotice.grievanceBody}</p>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 bg-slate-950 border-t border-slate-800 flex items-center justify-between">
          <span className="text-xs font-mono text-slate-400">
            {t.privacyNotice.badgeLabel}
          </span>
          <button
            type="button"
            onClick={onClose}
            className="px-5 py-2 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs transition-colors"
          >
            {t.common.close}
          </button>
        </div>
      </div>
    </div>
  );
};

