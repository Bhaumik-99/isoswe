import React, { useState } from 'react';
import {
  UserPlus,
  Camera,
  Upload,
  CheckCircle2,
  WifiOff,
  Trash2,
  Shield,
  AlertCircle,
} from 'lucide-react';
import { GateFlatOption, GateInfo, VisitorPurposeType } from '../../../types';
import { gateService, isValidIndianPhone } from '../../../services/gateService';
import { ApiClientError } from '../../../services/apiClient';
import { enqueueOfflineVisitor, generateClientEventId } from '../offline/gateIndexedDB';
import { useLanguage } from '../../../i18n/LanguageContext';
import { CameraCaptureModal } from './CameraCaptureModal';

interface VisitorRegistrationFormProps {
  activeGate: GateInfo | null;
  flats: GateFlatOption[];
  isOnline: boolean;
  onRegisteredOnline: () => void;
  onRegisteredOffline: () => void;
  onOpenPrivacyModal: () => void;
}

export const VisitorRegistrationForm: React.FC<VisitorRegistrationFormProps> = ({
  activeGate,
  flats,
  isOnline,
  onRegisteredOnline,
  onRegisteredOffline,
  onOpenPrivacyModal,
}) => {
  const { t, privacyNoticeVersion } = useLanguage();

  const [visitorName, setVisitorName] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [vehicleNumber, setVehicleNumber] = useState('');
  const [purpose, setPurpose] = useState<VisitorPurposeType>('GUEST');
  const [destinationFlatId, setDestinationFlatId] = useState('');
  const [photoBase64, setPhotoBase64] = useState<string | null>(null);
  const [cameraModalOpen, setCameraModalOpen] = useState(false);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const purposeOptions: Array<{ value: VisitorPurposeType; label: string }> = [
    { value: 'GUEST', label: t.gate.registration.purposes.PERSONAL_GUEST },
    { value: 'DELIVERY', label: t.gate.registration.purposes.DELIVERY },
    { value: 'CAB', label: t.gate.registration.purposes.CAB_TAXI },
    { value: 'SERVICE_MAINTENANCE', label: t.gate.registration.purposes.SERVICE_REPAIR },
    { value: 'EMERGENCY', label: t.gate.registration.purposes.COURIER },
    { value: 'OTHER', label: t.gate.registration.purposes.OTHER },
  ];

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === 'string') {
        setPhotoBase64(reader.result);
      }
    };
    reader.readAsDataURL(file);
  };

  const resetForm = () => {
    setVisitorName('');
    setPhoneNumber('');
    setVehicleNumber('');
    setPurpose('GUEST');
    setDestinationFlatId('');
    setPhotoBase64(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessMsg(null);

    if (visitorName.trim().length < 2) {
      setErrorMsg(t.errors.nameRequired);
      return;
    }
    if (!isValidIndianPhone(phoneNumber)) {
      setErrorMsg(t.errors.phoneInvalid);
      return;
    }
    if (!destinationFlatId) {
      setErrorMsg(t.errors.flatRequired);
      return;
    }
    if (!activeGate) {
      setErrorMsg(t.errors.genericError);
      return;
    }

    const selectedFlatObj = flats.find((f) => f.flat_id === destinationFlatId);
    const flatLabel = selectedFlatObj
      ? `${selectedFlatObj.tower_number}-${selectedFlatObj.flat_number}`
      : destinationFlatId;

    setIsSubmitting(true);
    const clientEventId = generateClientEventId();

    try {
      if (!isOnline) {
        await enqueueOfflineVisitor({
          gate_id: activeGate.gate_id,
          visitor_name: visitorName,
          phone_number: phoneNumber,
          vehicle_number: vehicleNumber || null,
          purpose,
          destination_flat_id: destinationFlatId,
          flat_label: flatLabel,
          photo_base64: photoBase64,
          privacy_notice_version: privacyNoticeVersion,
          client_event_id: clientEventId,
        });
        setSuccessMsg(t.gate.registration.registeredSuccessOffline);
        resetForm();
        onRegisteredOffline();
        return;
      }

      try {
        await gateService.registerVisitor({
          visitor_name: visitorName,
          phone_number: phoneNumber,
          vehicle_number: vehicleNumber || null,
          purpose,
          destination_flat_id: destinationFlatId,
          photo_base64: photoBase64,
          privacy_notice_version: privacyNoticeVersion,
          gate_id: activeGate.gate_id,
          client_event_id: clientEventId,
        });
        setSuccessMsg(t.gate.registration.registeredSuccessOnline);
        resetForm();
        onRegisteredOnline();
      } catch (err: unknown) {
        // If network dropped mid-request (status === 0), automatically queue offline
        if (err instanceof ApiClientError && err.status === 0) {
          await enqueueOfflineVisitor({
            gate_id: activeGate.gate_id,
            visitor_name: visitorName,
            phone_number: phoneNumber,
            vehicle_number: vehicleNumber || null,
            purpose,
            destination_flat_id: destinationFlatId,
            flat_label: flatLabel,
            photo_base64: photoBase64,
            privacy_notice_version: privacyNoticeVersion,
            client_event_id: clientEventId,
          });
          setSuccessMsg(t.gate.registration.registeredSuccessOffline);
          resetForm();
          onRegisteredOffline();
        } else {
          setErrorMsg(err instanceof Error ? err.message : t.errors.genericError);
        }
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 sm:p-6 shadow-xl text-white">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 pb-4 border-b border-slate-800 mb-5">
        <div>
          <h2 className="text-lg font-bold flex items-center gap-2 text-white">
            <UserPlus className="h-5 w-5 text-amber-400" />
            <span>{t.gate.registration.sectionTitle}</span>
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">{t.gate.registration.sectionSubtitle}</p>
        </div>
        <button
          type="button"
          onClick={onOpenPrivacyModal}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-700 text-xs font-mono text-amber-300 hover:border-amber-400"
        >
          <Shield className="h-3.5 w-3.5" />
          <span>{t.privacyNotice.badgeLabel}</span>
        </button>
      </div>

      {/* Offline Banner */}
      {!isOnline && (
        <div className="mb-5 p-4 rounded-xl bg-amber-500/15 border border-amber-500/40 text-amber-200 flex items-start gap-3">
          <WifiOff className="h-5 w-5 text-amber-400 flex-shrink-0 mt-0.5" />
          <div className="text-xs">
            <p className="font-bold text-amber-300 mb-0.5">
              {t.gate.registration.offlineBannerTitle}
            </p>
            <p>{t.gate.registration.offlineBannerBody}</p>
          </div>
        </div>
      )}

      {errorMsg && (
        <div className="mb-4 p-3.5 rounded-xl bg-rose-950/70 border border-rose-500/50 text-rose-200 text-xs flex items-center gap-2">
          <AlertCircle className="h-4 w-4 text-rose-400 flex-shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      {successMsg && (
        <div className="mb-4 p-3.5 rounded-xl bg-emerald-950/70 border border-emerald-500/50 text-emerald-200 text-xs flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 text-emerald-400 flex-shrink-0" />
          <span>{successMsg}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-5">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Visitor Full Name */}
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-300 mb-1.5">
              {t.gate.registration.visitorNameLabel} *
            </label>
            <input
              type="text"
              value={visitorName}
              onChange={(e) => setVisitorName(e.target.value)}
              placeholder={t.gate.registration.visitorNamePlaceholder}
              className="w-full px-4 py-3 rounded-xl bg-slate-950 border border-slate-700 text-white placeholder-slate-500 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
              required
            />
          </div>

          {/* Phone Number */}
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-300 mb-1.5">
              {t.gate.registration.phoneLabel} *
            </label>
            <input
              type="tel"
              value={phoneNumber}
              onChange={(e) => setPhoneNumber(e.target.value)}
              placeholder={t.gate.registration.phonePlaceholder}
              className="w-full px-4 py-3 rounded-xl bg-slate-950 border border-slate-700 text-white placeholder-slate-500 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-amber-400"
              required
            />
          </div>

          {/* Destination Flat */}
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-300 mb-1.5">
              {t.gate.registration.destinationFlatLabel} *
            </label>
            <select
              value={destinationFlatId}
              onChange={(e) => setDestinationFlatId(e.target.value)}
              className="w-full px-4 py-3 rounded-xl bg-slate-950 border border-slate-700 text-white text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
              required
            >
              <option value="">{t.gate.registration.destinationFlatPlaceholder}</option>
              {flats.map((f) => (
                <option key={f.flat_id} value={f.flat_id}>
                  {f.tower_number}-{f.flat_number} ({f.tower_name})
                </option>
              ))}
            </select>
          </div>

          {/* Purpose */}
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-300 mb-1.5">
              {t.gate.registration.purposeLabel} *
            </label>
            <select
              value={purpose}
              onChange={(e) => setPurpose(e.target.value as VisitorPurposeType)}
              className="w-full px-4 py-3 rounded-xl bg-slate-950 border border-slate-700 text-white text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
            >
              {purposeOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Optional Vehicle Number */}
          <div className="md:col-span-2">
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-300 mb-1.5">
              {t.gate.registration.vehicleLabel}
            </label>
            <input
              type="text"
              value={vehicleNumber}
              onChange={(e) => setVehicleNumber(e.target.value.toUpperCase())}
              placeholder={t.gate.registration.vehiclePlaceholder}
              className="w-full px-4 py-3 rounded-xl bg-slate-950 border border-slate-700 text-white placeholder-slate-500 text-sm font-mono uppercase focus:outline-none focus:ring-2 focus:ring-amber-400"
            />
          </div>
        </div>

        {/* Visitor Photo Capture & Upload Fallback */}
        <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-300">
              {t.gate.registration.photoSectionLabel}
            </span>
            <span className="text-[11px] text-slate-400">
              {t.gate.registration.photoOptionalOfflineNote}
            </span>
          </div>

          {photoBase64 ? (
            <div className="flex flex-col sm:flex-row items-center gap-4">
              <img
                src={photoBase64}
                alt="Visitor capture preview"
                className="w-28 h-24 object-cover rounded-lg border-2 border-emerald-500"
              />
              <div className="flex-1 space-y-2">
                <div className="text-xs text-emerald-300 font-semibold flex items-center gap-1.5">
                  <CheckCircle2 className="h-4 w-4" />
                  <span>{t.gate.registration.photoCapturedReady}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setPhotoBase64(null)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-950/60 hover:bg-rose-900/60 text-rose-300 border border-rose-700 text-xs font-semibold"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  <span>{t.gate.registration.retakePhotoBtn}</span>
                </button>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setCameraModalOpen(true)}
                className="py-3 px-4 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-amber-300 font-bold text-xs flex items-center justify-center gap-2 transition-colors"
              >
                <Camera className="h-4 w-4" />
                <span>{t.gate.registration.captureCameraBtn}</span>
              </button>

              <label className="py-3 px-4 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-indigo-300 font-bold text-xs flex items-center justify-center gap-2 cursor-pointer transition-colors">
                <Upload className="h-4 w-4" />
                <span>{t.gate.registration.uploadPhotoBtn}</span>
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  onChange={handleFileUpload}
                  className="hidden"
                />
              </label>
            </div>
          )}
        </div>

        {/* Statutory Privacy Notice Version Stamp */}
        <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800 flex items-center justify-between text-xs text-slate-300">
          <span>{t.privacyNotice.acknowledgmentLabel}</span>
          <span className="font-mono text-amber-300 font-semibold ml-2">
            {privacyNoticeVersion}
          </span>
        </div>

        <button
          type="submit"
          disabled={isSubmitting}
          className={`w-full py-4 px-6 rounded-xl font-extrabold text-sm uppercase tracking-wider shadow-lg transition-all flex items-center justify-center gap-2 ${
            isOnline
              ? 'bg-amber-500 hover:bg-amber-400 text-slate-950'
              : 'bg-indigo-600 hover:bg-indigo-500 text-white'
          } disabled:opacity-50`}
        >
          <UserPlus className="h-5 w-5" />
          <span>
            {isSubmitting
              ? t.common.loading
              : isOnline
                ? t.gate.registration.submitOnlineBtn
                : t.gate.registration.submitOfflineBtn}
          </span>
        </button>
      </form>

      <CameraCaptureModal
        isOpen={cameraModalOpen}
        onClose={() => setCameraModalOpen(false)}
        onCaptureBase64={(b64) => setPhotoBase64(b64)}
      />
    </div>
  );
};

