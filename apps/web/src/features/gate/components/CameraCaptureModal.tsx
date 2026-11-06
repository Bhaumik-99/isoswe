import React, { useEffect, useRef, useState } from 'react';
import { Camera, Upload, X, AlertTriangle } from 'lucide-react';
import { useLanguage } from '../../../i18n/LanguageContext';

interface CameraCaptureModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCaptureBase64: (base64Jpeg: string) => void;
}

export const CameraCaptureModal: React.FC<CameraCaptureModalProps> = ({
  isOpen,
  onClose,
  onCaptureBase64,
}) => {
  const { t } = useLanguage();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);

  useEffect(() => {
    if (!isOpen) {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      }
      setIsStreaming(false);
      setCameraError(null);
      return;
    }

    let cancelled = false;
    async function startCamera() {
      setCameraError(null);
      if (
        typeof navigator === 'undefined' ||
        !navigator.mediaDevices ||
        typeof navigator.mediaDevices.getUserMedia !== 'function'
      ) {
        setCameraError(t.errors.cameraUnavailable);
        return;
      }

      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: 'environment',
            width: { ideal: 640 },
            height: { ideal: 480 },
          },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play().catch(() => undefined);
        }
        setIsStreaming(true);
      } catch {
        if (!cancelled) {
          setCameraError(t.errors.cameraUnavailable);
        }
      }
    }

    void startCamera();

    return () => {
      cancelled = true;
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      }
    };
  }, [isOpen, t.errors.cameraUnavailable]);

  if (!isOpen) return null;

  const handleCaptureSnapshot = () => {
    const video = videoRef.current;
    if (!video) return;

    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL('image/jpeg', 0.82);
    onCaptureBase64(dataUrl);
    onClose();
  };

  const handleFileFallback = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === 'string') {
        onCaptureBase64(reader.result);
        onClose();
      }
    };
    reader.readAsDataURL(file);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4"
      role="dialog"
      aria-modal="true"
    >
      <div className="bg-slate-900 border border-slate-700 text-white rounded-2xl max-w-lg w-full overflow-hidden shadow-2xl">
        <div className="px-5 py-4 bg-slate-950 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2 font-bold text-sm">
            <Camera className="h-4 w-4 text-amber-400" />
            <span>{t.gate.registration.photoSectionLabel}</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {cameraError ? (
            <div className="p-4 rounded-xl bg-amber-950/40 border border-amber-500/40 text-amber-200 text-xs flex items-start gap-2.5">
              <AlertTriangle className="h-5 w-5 text-amber-400 flex-shrink-0" />
              <div>
                <p className="font-semibold mb-1">{cameraError}</p>
                <p className="text-amber-300/80">{t.gate.registration.photoOptionalOfflineNote}</p>
              </div>
            </div>
          ) : (
            <div className="relative rounded-xl overflow-hidden bg-black aspect-video border border-slate-700 flex items-center justify-center">
              <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                className="w-full h-full object-cover"
              />
            </div>
          )}

          <div className="flex flex-col sm:flex-row gap-3">
            {isStreaming && !cameraError && (
              <button
                type="button"
                onClick={handleCaptureSnapshot}
                className="flex-1 py-3 px-4 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-sm flex items-center justify-center gap-2 shadow-md"
              >
                <Camera className="h-4 w-4" />
                <span>{t.gate.registration.captureCameraBtn}</span>
              </button>
            )}

            <label className="flex-1 py-3 px-4 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-semibold text-sm flex items-center justify-center gap-2 border border-slate-600 cursor-pointer">
              <Upload className="h-4 w-4 text-indigo-400" />
              <span>{t.gate.registration.uploadPhotoBtn}</span>
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                capture="environment"
                onChange={handleFileFallback}
                className="hidden"
              />
            </label>
          </div>
        </div>
      </div>
    </div>
  );
};

