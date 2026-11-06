import React, { useState } from 'react';
import {
  KeyRound,
  CheckCircle2,
  ShieldAlert,
  WifiOff,
  LogIn,
  AlertCircle,
} from 'lucide-react';
import { GateInfo, VerifyGuestPassResponse } from '../../../types';
import { gateService } from '../../../services/gateService';
import { ApiClientError } from '../../../services/apiClient';
import { evaluateOfflineGuestPassPolicy } from '../offline/gateIndexedDB';
import { useLanguage } from '../../../i18n/LanguageContext';

interface GuestPassVerifierProps {
  activeGate: GateInfo | null;
  isOnline: boolean;
  onPassVerifiedAndCheckedIn: () => void;
}

export const GuestPassVerifier: React.FC<GuestPassVerifierProps> = ({
  activeGate,
  isOnline,
  onPassVerifiedAndCheckedIn,
}) => {
  const { t } = useLanguage();
  const [passCode, setPassCode] = useState('');
  const [isVerifying, setIsVerifying] = useState(false);
  const [isCheckingIn, setIsCheckingIn] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [verifiedPass, setVerifiedPass] = useState<VerifyGuestPassResponse | null>(null);
  const [checkedInDone, setCheckedInDone] = useState(false);

  const offlinePolicy = evaluateOfflineGuestPassPolicy(isOnline);

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setVerifiedPass(null);
    setCheckedInDone(false);

    if (!offlinePolicy.allowed) {
      setErrorMsg(t.gate.passVerification.offlineDisabledBody);
      return;
    }

    const trimmed = passCode.trim().toUpperCase();
    if (!trimmed) {
      setErrorMsg(t.errors.passCodeRequired);
      return;
    }
    if (!activeGate) {
      setErrorMsg(t.errors.genericError);
      return;
    }

    setIsVerifying(true);
    try {
      const res = await gateService.verifyGuestPass({
        pass_code: trimmed,
        gate_id: activeGate.gate_id,
      });
      setVerifiedPass(res);
      setPassCode('');
      onPassVerifiedAndCheckedIn();
    } catch (err: unknown) {
      if (err instanceof ApiClientError && err.status === 429) {
        setErrorMsg(t.errors.rateLimited429);
      } else {
        setErrorMsg(err instanceof Error ? err.message : t.errors.genericError);
      }
    } finally {
      setIsVerifying(false);
    }
  };

  const handleCheckInVerifiedVisitor = async () => {
    if (!verifiedPass?.visitor_id) return;
    setIsCheckingIn(true);
    setErrorMsg(null);
    try {
      await gateService.checkInVisitor(verifiedPass.visitor_id);
      setCheckedInDone(true);
      onPassVerifiedAndCheckedIn();
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : t.errors.genericError);
    } finally {
      setIsCheckingIn(false);
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 sm:p-6 shadow-xl text-white">
      <div className="pb-4 border-b border-slate-800 mb-5">
        <h2 className="text-lg font-bold flex items-center gap-2 text-white">
          <KeyRound className="h-5 w-5 text-amber-400" />
          <span>{t.gate.passVerification.sectionTitle}</span>
        </h2>
        <p className="text-xs text-slate-400 mt-0.5">{t.gate.passVerification.sectionSubtitle}</p>
      </div>

      {/* Fail-Closed Offline Warning */}
      {!offlinePolicy.allowed ? (
        <div className="p-5 rounded-xl bg-amber-950/50 border-2 border-amber-500/60 text-amber-100 space-y-2">
          <div className="flex items-center gap-2 text-amber-300 font-bold text-sm">
            <WifiOff className="h-5 w-5" />
            <span>{t.gate.passVerification.offlineDisabledTitle}</span>
          </div>
          <p className="text-xs text-amber-200 leading-relaxed">
            {t.gate.passVerification.offlineDisabledBody}
          </p>
        </div>
      ) : (
        <form onSubmit={handleVerify} className="space-y-4">
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-300 mb-1.5">
              {t.gate.passVerification.passCodeLabel}
            </label>
            <input
              type="text"
              value={passCode}
              onChange={(e) => setPassCode(e.target.value.toUpperCase())}
              placeholder={t.gate.passVerification.passCodePlaceholder}
              className="w-full px-4 py-3.5 rounded-xl bg-slate-950 border border-slate-700 text-amber-300 placeholder-slate-600 text-lg font-mono tracking-widest uppercase focus:outline-none focus:ring-2 focus:ring-amber-400"
              required
            />
          </div>

          {errorMsg && (
            <div className="p-3.5 rounded-xl bg-rose-950/70 border border-rose-500/50 text-rose-200 text-xs flex items-center gap-2">
              <AlertCircle className="h-4 w-4 text-rose-400 flex-shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          <button
            type="submit"
            disabled={isVerifying}
            className="w-full py-3.5 px-6 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-extrabold text-sm uppercase tracking-wider shadow-lg transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
          >
            <ShieldAlert className="h-4 w-4" />
            <span>{isVerifying ? t.common.loading : t.gate.passVerification.verifyBtn}</span>
          </button>
        </form>
      )}

      {verifiedPass && (
        <div className="mt-5 p-4 rounded-xl bg-emerald-950/50 border border-emerald-500/50 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-emerald-300 font-bold text-sm">
              <CheckCircle2 className="h-5 w-5" />
              <span>{t.gate.passVerification.verifiedSuccessTitle}</span>
            </div>
            <span className="px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 text-xs font-mono font-bold">
              {verifiedPass.approval_status}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-3 text-xs bg-slate-950/70 p-3 rounded-lg border border-slate-800">
            <div>
              <span className="text-slate-400 block">Guest:</span>
              <span className="font-bold text-white">{verifiedPass.guest_name}</span>
            </div>
            <div>
              <span className="text-slate-400 block">Pass Type / Remaining:</span>
              <span className="font-mono font-bold text-amber-300">
                {verifiedPass.pass_type} ({verifiedPass.remaining_uses} left)
              </span>
            </div>
          </div>

          {verifiedPass.visitor_id && !checkedInDone && (
            <button
              type="button"
              disabled={isCheckingIn}
              onClick={handleCheckInVerifiedVisitor}
              className="w-full py-3 px-4 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-extrabold text-xs uppercase tracking-wider flex items-center justify-center gap-2"
            >
              <LogIn className="h-4 w-4" />
              <span>{isCheckingIn ? t.common.loading : t.gate.liveMonitor.checkInBtn}</span>
            </button>
          )}

          {checkedInDone && (
            <div className="text-xs text-emerald-300 font-bold flex items-center gap-1.5">
              <CheckCircle2 className="h-4 w-4" />
              <span>{t.gate.liveMonitor.checkedInSuccess}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

