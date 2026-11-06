import React, { useState } from 'react';
import {
  CheckCircle2,
  XCircle,
  Clock,
  Image,
  AlertCircle,
  X,
  AlertTriangle,
} from 'lucide-react';
import { VisitorRecord } from '../../../types';
import { residentVisitorService } from '../../../services/residentVisitorService';
import { ApiClientError } from '../../../services/apiClient';
import { useLanguage } from '../../../i18n/LanguageContext';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/Card';
import { Button } from '../../../components/ui/Button';
import { Badge } from '../../../components/ui/Badge';

interface PendingApprovalsInboxProps {
  visitors: VisitorRecord[];
  onActionCompleted: () => void;
}

export const PendingApprovalsInbox: React.FC<PendingApprovalsInboxProps> = ({
  visitors,
  onActionCompleted,
}) => {
  const { t } = useLanguage();
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectionReason, setRejectionReason] = useState('');
  const [feedbackMsg, setFeedbackMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [photoModalVisitor, setPhotoModalVisitor] = useState<string | null>(null);
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [photoError, setPhotoError] = useState<string | null>(null);

  const handleAction = async (
    visitorId: string,
    action: 'APPROVE' | 'REJECT',
    reason?: string
  ) => {
    setProcessingId(visitorId);
    setErrorMsg(null);
    setFeedbackMsg(null);
    try {
      await residentVisitorService.actOnVisitor(visitorId, action, reason);
      setFeedbackMsg(
        action === 'APPROVE'
          ? t.resident.pendingInbox.approvedToast
          : t.resident.pendingInbox.rejectedToast
      );
      setRejectingId(null);
      setRejectionReason('');
      onActionCompleted();
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : t.errors.genericError);
    } finally {
      setProcessingId(null);
    }
  };

  const handleViewPhoto = async (v: VisitorRecord) => {
    setPhotoModalVisitor(v.visitor_name);
    setPhotoUrl(v.photo_url || null);
    setPhotoError(null);
    if (v.photo_url) return;
    try {
      const res = await residentVisitorService.getVisitorPhotoUrl(v.visitor_id);
      setPhotoUrl(res.photo_url);
    } catch (err: unknown) {
      if (err instanceof ApiClientError && err.status === 410) {
        setPhotoError(t.errors.photoExpired410);
      } else {
        setPhotoError(err instanceof Error ? err.message : t.errors.genericError);
      }
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>{t.resident.pendingInbox.title}</span>
          <Badge variant={visitors.length > 0 ? 'warning' : 'success'}>
            {visitors.length} {t.statuses.approval.PENDING}
          </Badge>
        </CardTitle>
        <p className="text-xs text-slate-500 mt-0.5">{t.resident.pendingInbox.subtitle}</p>
      </CardHeader>
      <CardContent className="space-y-4">
        {errorMsg && (
          <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-rose-600 flex-shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        {feedbackMsg && (
          <div className="p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-emerald-600 flex-shrink-0" />
            <span>{feedbackMsg}</span>
          </div>
        )}

        {visitors.length === 0 ? (
          <div className="p-8 text-center text-slate-500 text-xs bg-slate-50 rounded-lg border border-slate-200">
            {t.resident.pendingInbox.emptyMessage}
          </div>
        ) : (
          <div className="space-y-3">
            {visitors.map((v) => (
              <div
                key={v.visitor_id}
                className="p-4 rounded-xl bg-amber-50/50 border border-amber-200 flex flex-col gap-3"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-bold text-sm text-slate-900">{v.visitor_name}</span>
                      <span className="text-xs font-mono text-slate-500">{v.phone_masked}</span>
                      <Badge variant="warning">{v.purpose}</Badge>
                    </div>
                    <div className="text-xs text-slate-500 flex items-center gap-2">
                      <Clock className="h-3.5 w-3.5 text-amber-600" />
                      <span>{new Date(v.created_at).toLocaleString()}</span>
                      {v.vehicle_number && (
                        <span className="font-mono text-slate-700">• {v.vehicle_number}</span>
                      )}
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleViewPhoto(v)}
                      className="text-xs flex items-center gap-1"
                    >
                      <Image className="h-3.5 w-3.5" />
                      <span>{t.common.viewPhoto}</span>
                    </Button>

                    <Button
                      size="sm"
                      variant="primary"
                      isLoading={processingId === v.visitor_id}
                      onClick={() => handleAction(v.visitor_id, 'APPROVE')}
                      className="text-xs bg-emerald-600 hover:bg-emerald-700 text-white font-semibold flex items-center gap-1"
                    >
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      <span>{t.resident.pendingInbox.approveBtn}</span>
                    </Button>

                    <Button
                      size="sm"
                      variant="outline"
                      disabled={processingId === v.visitor_id}
                      onClick={() =>
                        setRejectingId(rejectingId === v.visitor_id ? null : v.visitor_id)
                      }
                      className="text-xs border-rose-300 text-rose-700 hover:bg-rose-50 flex items-center gap-1"
                    >
                      <XCircle className="h-3.5 w-3.5" />
                      <span>{t.resident.pendingInbox.rejectBtn}</span>
                    </Button>
                  </div>
                </div>

                {rejectingId === v.visitor_id && (
                  <div className="pt-2 border-t border-amber-200 flex flex-col sm:flex-row gap-2">
                    <input
                      type="text"
                      value={rejectionReason}
                      onChange={(e) => setRejectionReason(e.target.value)}
                      placeholder={t.resident.pendingInbox.rejectionReasonPlaceholder}
                      className="flex-1 px-3 py-1.5 text-xs border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-rose-500"
                    />
                    <Button
                      size="sm"
                      variant="primary"
                      isLoading={processingId === v.visitor_id}
                      onClick={() => handleAction(v.visitor_id, 'REJECT', rejectionReason)}
                      className="text-xs bg-rose-600 hover:bg-rose-700 text-white"
                    >
                      {t.resident.pendingInbox.confirmRejectBtn}
                    </Button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Photo Modal */}
        {photoModalVisitor && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/70 backdrop-blur-sm p-4"
            role="dialog"
            aria-modal="true"
          >
            <div className="bg-white border border-slate-200 rounded-xl max-w-md w-full overflow-hidden shadow-xl">
              <div className="px-4 py-3 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
                <span className="font-bold text-sm text-slate-900">{photoModalVisitor}</span>
                <button
                  type="button"
                  onClick={() => setPhotoModalVisitor(null)}
                  className="p-1 text-slate-400 hover:text-slate-700"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="p-4">
                {photoError ? (
                  <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-xs flex items-start gap-2">
                    <AlertTriangle className="h-4 w-4 text-amber-600 flex-shrink-0" />
                    <span>{photoError}</span>
                  </div>
                ) : photoUrl ? (
                  <img
                    src={photoUrl}
                    alt={photoModalVisitor}
                    className="w-full h-60 object-cover rounded-lg border border-slate-200"
                  />
                ) : (
                  <div className="py-8 text-center text-xs text-slate-500">{t.common.loading}</div>
                )}
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

