import React, { useState } from 'react';
import {
  KeyRound,
  Copy,
  CheckCircle2,
  Ban,
  AlertCircle,
} from 'lucide-react';
import { GuestPass, GuestPassType } from '../../../types';
import { residentVisitorService } from '../../../services/residentVisitorService';
import { useLanguage } from '../../../i18n/LanguageContext';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/Card';
import { Button } from '../../../components/ui/Button';
import { Badge } from '../../../components/ui/Badge';

interface GuestPassManagerProps {
  flatId: string;
  passes: GuestPass[];
  onPassesUpdated: () => void;
}

export const GuestPassManager: React.FC<GuestPassManagerProps> = ({
  flatId,
  passes,
  onPassesUpdated,
}) => {
  const { t } = useLanguage();

  const [guestName, setGuestName] = useState('');
  const [guestPhone, setGuestPhone] = useState('');
  const [purpose, setPurpose] = useState('Personal Guest');
  const [passType, setPassType] = useState<GuestPassType>('SINGLE_USE');
  const [maxUses, setMaxUses] = useState<number>(1);
  const [validHours, setValidHours] = useState<number>(24);

  const [isCreating, setIsCreating] = useState(false);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [generatedCode, setGeneratedCode] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleCreatePass = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setGeneratedCode(null);
    setCopied(false);

    if (guestName.trim().length < 2) {
      setErrorMsg(t.errors.nameRequired);
      return;
    }

    const now = new Date();
    const validUntil = new Date(now.getTime() + validHours * 3600 * 1000);
    const effectiveMaxUses = passType === 'SINGLE_USE' ? 1 : Math.min(Math.max(maxUses, 2), 10);

    setIsCreating(true);
    try {
      const created = await residentVisitorService.createGuestPass({
        destination_flat_id: flatId,
        guest_name: guestName,
        guest_phone: guestPhone || null,
        purpose,
        pass_type: passType,
        max_uses: effectiveMaxUses,
        valid_from: now.toISOString(),
        valid_until: validUntil.toISOString(),
      });
      if (created.pass_code) {
        setGeneratedCode(created.pass_code);
      }
      setGuestName('');
      setGuestPhone('');
      onPassesUpdated();
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : t.errors.genericError);
    } finally {
      setIsCreating(false);
    }
  };

  const handleCopyCode = async () => {
    if (!generatedCode) return;
    try {
      await navigator.clipboard.writeText(generatedCode);
      setCopied(true);
    } catch {
      setCopied(true);
    }
  };

  const handleRevoke = async (passId: string) => {
    setRevokingId(passId);
    setErrorMsg(null);
    try {
      await residentVisitorService.revokeGuestPass(passId);
      onPassesUpdated();
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : t.errors.genericError);
    } finally {
      setRevokingId(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Create Pass Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <KeyRound className="h-4 w-4 text-indigo-600" />
            <span>{t.resident.guestPasses.createTitle}</span>
          </CardTitle>
          <p className="text-xs text-slate-500 mt-0.5">{t.resident.guestPasses.createSubtitle}</p>
        </CardHeader>
        <CardContent className="space-y-4">
          {errorMsg && (
            <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-center gap-2">
              <AlertCircle className="h-4 w-4 text-rose-600 flex-shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          {generatedCode && (
            <div className="p-4 rounded-xl bg-indigo-950 text-white border-2 border-indigo-400 space-y-2 shadow-md">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold uppercase tracking-wider text-amber-300">
                  {t.resident.guestPasses.generatedCodeBannerTitle}
                </span>
                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              </div>
              <p className="text-xs text-indigo-200">
                {t.resident.guestPasses.generatedCodeBannerSubtitle}
              </p>
              <div className="flex items-center justify-between bg-slate-900 px-4 py-3 rounded-lg border border-indigo-500/40">
                <span className="text-xl font-mono font-extrabold tracking-widest text-amber-300">
                  {generatedCode}
                </span>
                <Button
                  size="sm"
                  variant="primary"
                  onClick={handleCopyCode}
                  className="text-xs bg-indigo-600 hover:bg-indigo-500 flex items-center gap-1"
                >
                  <Copy className="h-3.5 w-3.5" />
                  <span>
                    {copied
                      ? t.resident.guestPasses.copiedLabel
                      : t.resident.guestPasses.copyCodeBtn}
                  </span>
                </Button>
              </div>
            </div>
          )}

          <form onSubmit={handleCreatePass} className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                {t.resident.guestPasses.visitorNameLabel} *
              </label>
              <input
                type="text"
                value={guestName}
                onChange={(e) => setGuestName(e.target.value)}
                placeholder="e.g.,Vikram Deshmukh"
                className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-600"
                required
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                {t.resident.guestPasses.visitorPhoneLabel}
              </label>
              <input
                type="tel"
                value={guestPhone}
                onChange={(e) => setGuestPhone(e.target.value)}
                placeholder="9823011223"
                className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-600"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                {t.resident.guestPasses.purposeLabel} *
              </label>
              <input
                type="text"
                value={purpose}
                onChange={(e) => setPurpose(e.target.value)}
                className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-600"
                required
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                {t.resident.guestPasses.passTypeLabel}
              </label>
              <select
                value={passType}
                onChange={(e) => {
                  const nextType = e.target.value as GuestPassType;
                  setPassType(nextType);
                  setMaxUses(nextType === 'SINGLE_USE' ? 1 : 3);
                }}
                className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-600"
              >
                <option value="SINGLE_USE">{t.resident.guestPasses.singleUseOption}</option>
                <option value="MULTI_USE">{t.resident.guestPasses.multiUseOption}</option>
              </select>
            </div>

            {passType === 'MULTI_USE' && (
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  {t.resident.guestPasses.maxUsesLabel}
                </label>
                <input
                  type="number"
                  min={2}
                  max={10}
                  value={maxUses}
                  onChange={(e) => setMaxUses(Number(e.target.value))}
                  className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-600"
                />
              </div>
            )}

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                {t.resident.guestPasses.validHoursLabel}
              </label>
              <select
                value={validHours}
                onChange={(e) => setValidHours(Number(e.target.value))}
                className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-600"
              >
                <option value={6}>6 Hours</option>
                <option value={12}>12 Hours</option>
                <option value={24}>24 Hours (1 Day)</option>
                <option value={72}>72 Hours (3 Days)</option>
                <option value={168}>168 Hours (7 Days)</option>
              </select>
            </div>

            <div className="sm:col-span-2 pt-1">
              <Button
                type="submit"
                variant="primary"
                isLoading={isCreating}
                className="w-full text-xs font-semibold"
              >
                {t.resident.guestPasses.generateBtn}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Active & Past Passes List */}
      <Card>
        <CardHeader>
          <CardTitle>{t.resident.guestPasses.activePassesTitle}</CardTitle>
        </CardHeader>
        <CardContent>
          {passes.length === 0 ? (
            <div className="p-8 text-center text-slate-500 text-xs bg-slate-50 rounded-lg border border-slate-200">
              {t.resident.guestPasses.emptyPassesMessage}
            </div>
          ) : (
            <div className="space-y-3">
              {passes.map((p) => (
                <div
                  key={p.pass_id}
                  className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-sm text-slate-900">{p.guest_name}</span>
                      <Badge
                        variant={
                          p.status === 'ACTIVE'
                            ? 'success'
                            : p.status === 'REVOKED'
                              ? 'danger'
                              : 'neutral'
                        }
                      >
                        {p.status}
                      </Badge>
                    </div>
                    <div className="text-xs text-slate-500 mt-0.5">
                      {p.purpose} • {p.pass_type} ({p.used_count}/{p.max_uses} used) • Valid until{' '}
                      {new Date(p.valid_until).toLocaleString()}
                    </div>
                  </div>

                  {p.status === 'ACTIVE' && (
                    <Button
                      size="sm"
                      variant="outline"
                      isLoading={revokingId === p.pass_id}
                      onClick={() => handleRevoke(p.pass_id)}
                      className="text-xs border-rose-300 text-rose-700 hover:bg-rose-50 flex items-center gap-1"
                    >
                      <Ban className="h-3.5 w-3.5" />
                      <span>{t.resident.guestPasses.revokeBtn}</span>
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

