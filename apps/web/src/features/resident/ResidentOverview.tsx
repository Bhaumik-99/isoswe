import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Building,
  ShieldCheck,
  Calendar,
  Maximize2,
  CreditCard,
  ArrowRight,
  LifeBuoy,
  PlusCircle,
  Smartphone,
  CheckCircle2,
  UserCheck,
  XCircle,
  KeyRound,
  Sparkles,
  Megaphone,
  Pin,
  AlertTriangle,
} from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { apiClient, ApiClientError } from '../../services/apiClient';
import { billingService, formatINR, formatDateIST } from '../../services/billingService';
import { complaintsService } from '../../services/complaintsService';
import { residentVisitorService } from '../../services/residentVisitorService';
import { notificationService } from '../../services/notificationService';
import { FlatDetail, Complaint, VisitorRecord, PaginatedNotices } from '../../types';
import { useLanguage } from '../../i18n/LanguageContext';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Skeleton } from '../../components/ui/Skeleton';
import { Alert } from '../../components/ui/Alert';
import { useGsapStagger } from '../../components/motion/useGsapStagger';

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

export const ResidentOverview: React.FC = () => {
  const navigate = useNavigate();
  const { user, selectedFlat } = useAuth();
  const { t } = useLanguage();
  const [flatDetail, setFlatDetail] = useState<FlatDetail | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [isInstallDismissed, setIsInstallDismissed] = useState<boolean>(false);
  const [actingVisitorId, setActingVisitorId] = useState<string | null>(null);
  const overviewRef = useGsapStagger<HTMLDivElement>('[data-gsap-stagger]');

  const { data: billingSummary, isLoading: isBillingLoading } = useQuery({
    queryKey: ['billing-summary', user?.id, selectedFlat?.flat_id],
    queryFn: billingService.getResidentSummary,
    enabled: Boolean(selectedFlat?.flat_id),
  });

  const { data: residentComplaints = [], isLoading: isComplaintsLoading } = useQuery<Complaint[]>({
    queryKey: ['resident-complaints-summary', user?.id, selectedFlat?.flat_id],
    queryFn: () => complaintsService.listResidentComplaints(),
    enabled: Boolean(selectedFlat?.flat_id),
  });

  const { data: noticesFeed, isLoading: isNoticesLoading } = useQuery<PaginatedNotices>({
    queryKey: ['resident-notices-overview', user?.id, selectedFlat?.flat_id],
    queryFn: () => notificationService.getResidentNotices(1, 3),
    enabled: Boolean(selectedFlat?.flat_id),
  });

  const {
    data: pendingVisitors = [],
    refetch: refetchPendingVisitors,
  } = useQuery<VisitorRecord[]>({
    queryKey: ['resident-pending-visitors', user?.id, selectedFlat?.flat_id],
    queryFn: () => residentVisitorService.listPendingVisitors(),
    enabled: Boolean(selectedFlat?.flat_id),
  });

  const handleQuickVisitorAction = async (
    visitorId: string,
    action: 'APPROVE' | 'REJECT'
  ) => {
    setActingVisitorId(visitorId);
    try {
      await residentVisitorService.actOnVisitor(visitorId, action);
      await refetchPendingVisitors();
    } finally {
      setActingVisitorId(null);
    }
  };

  useEffect(() => {
    const handleBeforeInstall = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e as BeforeInstallPromptEvent);
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstall);
    return () => window.removeEventListener('beforeinstallprompt', handleBeforeInstall);
  }, []);

  const handleInstallApp = async () => {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    const choice = await deferredPrompt.userChoice;
    if (choice.outcome === 'accepted') {
      setDeferredPrompt(null);
    }
  };

  useEffect(() => {
    if (!selectedFlat) {
      setIsLoading(false);
      return;
    }

    let isMounted = true;
    setIsLoading(true);
    setError(null);

    apiClient
      .get<FlatDetail>(`/api/v1/flats/${selectedFlat.flat_id}`)
      .then((data) => {
        if (isMounted) {
          setFlatDetail(data);
          setIsLoading(false);
        }
      })
      .catch((err: ApiClientError) => {
        if (isMounted) {
          setError(err.message || 'Unable to retrieve flat details');
          setIsLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [selectedFlat]);

  if (!selectedFlat) {
    return (
      <Alert variant="warning" title="No Approved Flat Membership">
        Your account currently does not hold an approved flat membership in Marvel Greenfield Residences.
        Please contact the society helpdesk for onboarding.
      </Alert>
    );
  }

  const activeComplaints = residentComplaints.filter(
    (c) => c.status !== 'RESOLVED' && c.status !== 'CLOSED'
  );
  const latestComplaint = residentComplaints[0];

  return (
    <div ref={overviewRef} className="space-y-6">
      {/* PWA Mobile App Install Prompt Banner (Apple dark tile, no gradient) */}
      {deferredPrompt && !isInstallDismissed && (
        <div className="flex flex-col sm:flex-row items-center justify-between p-5 bg-[#272729] text-[#ffffff] rounded-[18px] gap-4">
          <div className="flex items-center gap-3.5">
            <div className="p-2.5 bg-[#2a2a2c] rounded-[11px]">
              <Smartphone className="h-5 w-5 text-[#2997ff]" aria-hidden="true" />
            </div>
            <div>
              <h3 className="font-display text-[17px] font-semibold text-[#ffffff] tracking-[-0.374px]">
                Install Isoswe Township App
              </h3>
              <p className="text-[14px] text-[#cccccc] tracking-[-0.224px]">
                Instant access to maintenance payments, receipt downloads, and ticket tracking.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2.5 w-full sm:w-auto">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setIsInstallDismissed(true)}
              className="text-[#2997ff]"
            >
              Dismiss
            </Button>
            <Button
              size="sm"
              variant="primary"
              onClick={handleInstallApp}
            >
              Install App
            </Button>
          </div>
        </div>
      )}

      {/* Page Title */}
      <div data-gsap-stagger className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-5 border-b border-[#e0e0e0]">
        <div>
          <h1 className="font-display text-[34px] font-semibold leading-[1.2] tracking-[-0.374px] text-[#1d1d1f]">
            Apartment Residence
          </h1>
          <p className="text-[14px] text-[#333333] tracking-[-0.224px] mt-1">
            Verified property membership and society operations status
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={selectedFlat.membership_type === 'OWNER' ? 'info' : 'warning'}>
            Membership: {selectedFlat.membership_type}
          </Badge>
          <Badge variant="neutral">Status: {selectedFlat.status}</Badge>
        </div>
      </div>

      {error && (
        <Alert variant="error" title="Flat Authorization Notice">
          {error}
        </Alert>
      )}

      {/* Property Details Card */}
      <Card data-gsap-stagger>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Unit Specifications & Registry</CardTitle>
          <span className="text-xs font-mono text-slate-500">ID: {selectedFlat.flat_id.substring(0, 8)}...</span>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-20 w-full" />
            </div>
          ) : flatDetail ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="p-4 rounded-lg bg-slate-50 border border-slate-200">
                <div className="flex items-center gap-2 text-slate-500 text-xs font-semibold uppercase tracking-wider mb-1">
                  <Building className="h-4 w-4 text-indigo-600" />
                  <span>Tower & Unit</span>
                </div>
                <div className="text-lg font-bold text-slate-900">
                  {flatDetail.tower_number || 'Tower'} - {flatDetail.flat_number}
                </div>
                <div className="text-xs text-slate-500">{flatDetail.tower_name || 'Residential Tower'}</div>
              </div>

              <div className="p-4 rounded-lg bg-slate-50 border border-slate-200">
                <div className="flex items-center gap-2 text-slate-500 text-xs font-semibold uppercase tracking-wider mb-1">
                  <Maximize2 className="h-4 w-4 text-indigo-600" />
                  <span>Carpet / Area</span>
                </div>
                <div className="text-lg font-bold text-slate-900">{flatDetail.area_sqft} sq ft</div>
                <div className="text-xs text-slate-500">Super built-up measure</div>
              </div>

              <div className="p-4 rounded-lg bg-slate-50 border border-slate-200">
                <div className="flex items-center gap-2 text-slate-500 text-xs font-semibold uppercase tracking-wider mb-1">
                  <ShieldCheck className="h-4 w-4 text-emerald-600" />
                  <span>Lease / Tenancy</span>
                </div>
                <div className="text-sm font-semibold text-slate-900">
                  {selectedFlat.membership_type === 'OWNER' ? 'Permanent Ownership' : 'Active Tenancy Lease'}
                </div>
                <div className="text-xs text-slate-500">
                  {selectedFlat.valid_until
                    ? `Expires: ${new Date(selectedFlat.valid_until).toLocaleDateString()}`
                    : 'Indefinite (Owner Record)'}
                </div>
              </div>

              <div className="p-4 rounded-lg bg-slate-50 border border-slate-200">
                <div className="flex items-center gap-2 text-slate-500 text-xs font-semibold uppercase tracking-wider mb-1">
                  <Calendar className="h-4 w-4 text-indigo-600" />
                  <span>Registered Since</span>
                </div>
                <div className="text-sm font-semibold text-slate-900">
                  {new Date(selectedFlat.valid_from).toLocaleDateString()}
                </div>
                <div className="text-xs text-slate-500">Approved Membership Date</div>
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {/* Official Township Notices & Circulars Card */}
      <Card className="border-l-4 border-l-indigo-600">
        <CardHeader>
          <CardTitle className="text-sm font-semibold flex items-center justify-between">
            <span className="flex items-center gap-2">
              <Megaphone className="h-4 w-4 text-indigo-600" />
              <span>Official Township Notices & Circulars</span>
            </span>
            <Badge variant={(noticesFeed?.unread_count || 0) > 0 ? 'warning' : 'info'}>
              {(noticesFeed?.unread_count || 0) > 0
                ? `${noticesFeed?.unread_count} Unread`
                : 'Up to Date'}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-xs text-slate-600">
          {isNoticesLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : noticesFeed && noticesFeed.items.length > 0 ? (
            <div className="space-y-2">
              {noticesFeed.items.map((notice) => {
                const isEmergency =
                  notice.deliver_emergency ||
                  notice.category === 'EMERGENCY' ||
                  notice.priority === 'URGENT';
                return (
                  <div
                    key={notice.id}
                    onClick={() => navigate('/resident/notices')}
                    className={`p-3 rounded-lg border cursor-pointer transition-colors flex flex-col sm:flex-row sm:items-center justify-between gap-2 ${
                      isEmergency
                        ? 'bg-rose-50/70 border-rose-200 hover:bg-rose-100/70'
                        : !notice.is_read
                        ? 'bg-indigo-50/60 border-indigo-200 hover:bg-indigo-100/60'
                        : 'bg-slate-50 border-slate-200 hover:bg-slate-100'
                    }`}
                  >
                    <div className="space-y-0.5 min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        {notice.is_pinned && (
                          <span className="inline-flex items-center gap-0.5 text-[10px] font-bold text-indigo-700 bg-indigo-100 px-1.5 py-0.5 rounded">
                            <Pin className="h-2.5 w-2.5" /> Pinned
                          </span>
                        )}
                        {isEmergency && (
                          <span className="inline-flex items-center gap-0.5 text-[10px] font-bold text-rose-700 bg-rose-100 px-1.5 py-0.5 rounded">
                            <AlertTriangle className="h-2.5 w-2.5" /> Urgent
                          </span>
                        )}
                        <span className="font-bold text-slate-900 text-xs truncate">
                          {notice.title}
                        </span>
                        {!notice.is_read && (
                          <span className="h-2 w-2 rounded-full bg-indigo-600 inline-block" />
                        )}
                      </div>
                      <p className="text-[11px] text-slate-600 line-clamp-1">{notice.body}</p>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0 text-[10px] text-slate-500">
                      <Badge variant="neutral" className="text-[10px] py-0">
                        {notice.category}
                      </Badge>
                      <span>
                        {notice.published_at
                          ? new Date(notice.published_at).toLocaleDateString()
                          : ''}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="p-3 bg-slate-50 rounded-lg border border-slate-200 flex items-center justify-between">
              <span>No active township notices for your unit at this time.</span>
              <Megaphone className="h-4 w-4 text-slate-400" />
            </div>
          )}

          <div className="pt-1">
            <Button
              size="sm"
              variant="outline"
              onClick={() => navigate('/resident/notices')}
              className="w-full text-xs font-semibold flex items-center justify-center gap-1.5"
            >
              <span>Open Official Notices & Circulars Board</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Gate Visitors & Pre-Approved Passes Card (1-Tap Approval & 2-Tap Hub) */}
      <Card className="border-l-4 border-l-amber-500">
        <CardHeader>
          <CardTitle className="text-sm font-semibold flex items-center justify-between">
            <span className="flex items-center gap-2">
              <UserCheck className="h-4 w-4 text-amber-600" />
              <span>{t.resident.homeCardTitle}</span>
            </span>
            <Badge variant={pendingVisitors.length > 0 ? 'warning' : 'success'}>
              {pendingVisitors.length > 0
                ? `${pendingVisitors.length} ${t.resident.homePendingBadge}`
                : t.resident.homeNoPendingBadge}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-xs text-slate-600">
          {pendingVisitors.length > 0 ? (
            <div className="space-y-2">
              {pendingVisitors.slice(0, 2).map((v) => (
                <div
                  key={v.visitor_id}
                  className="p-3 rounded-lg bg-amber-50 border border-amber-200 flex flex-col sm:flex-row sm:items-center justify-between gap-2"
                >
                  <div>
                    <div className="font-bold text-slate-900 text-xs">{v.visitor_name}</div>
                    <div className="text-[11px] text-slate-600">
                      {v.purpose} • {v.phone_masked}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      variant="primary"
                      isLoading={actingVisitorId === v.visitor_id}
                      onClick={() => handleQuickVisitorAction(v.visitor_id, 'APPROVE')}
                      className="text-xs bg-emerald-600 hover:bg-emerald-700 text-white"
                    >
                      <CheckCircle2 className="h-3.5 w-3.5 mr-1" />
                      {t.resident.pendingInbox.approveBtn}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={actingVisitorId === v.visitor_id}
                      onClick={() => handleQuickVisitorAction(v.visitor_id, 'REJECT')}
                      className="text-xs border-rose-300 text-rose-700 hover:bg-rose-50"
                    >
                      <XCircle className="h-3.5 w-3.5 mr-1" />
                      {t.resident.pendingInbox.rejectBtn}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="p-3 bg-slate-50 rounded-lg border border-slate-200 flex items-center justify-between">
              <span>{t.resident.homeCardSubtitle}</span>
              <KeyRound className="h-4 w-4 text-indigo-500" />
            </div>
          )}

          <div className="pt-1">
            <Button
              size="sm"
              variant="primary"
              onClick={() => navigate('/resident/visitors')}
              className="w-full text-xs font-semibold flex items-center justify-center gap-1.5"
            >
              <span>{t.resident.homeManageCta}</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Primary Action Modules Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Maintenance Billing Card */}
        <Card className="border-l-4 border-l-indigo-600">
          <CardHeader>
            <CardTitle className="text-sm font-semibold flex items-center justify-between">
              <span className="flex items-center gap-2">
                <CreditCard className="h-4 w-4 text-indigo-600" />
                <span>Maintenance Billing</span>
              </span>
              {billingSummary ? (
                billingSummary.total_outstanding_paise === 0 ? (
                  <Badge variant="success">ALL PAID</Badge>
                ) : billingSummary.total_overdue_paise > 0 ? (
                  <Badge variant="danger">OVERDUE DUES</Badge>
                ) : (
                  <Badge variant="warning">PAYMENT DUE</Badge>
                )
              ) : (
                <Badge variant="info">Operational</Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-xs text-slate-600">
            {isBillingLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-8 w-full" />
              </div>
            ) : billingSummary ? (
              <div className="space-y-3">
                <div className="flex items-baseline justify-between p-3 bg-slate-50 rounded-lg border border-slate-200">
                  <div>
                    <span className="text-[11px] text-slate-500 uppercase font-semibold">Total Outstanding</span>
                    <p
                      className={`text-xl font-bold ${
                        billingSummary.total_outstanding_paise > 0 ? 'text-rose-600' : 'text-slate-900'
                      }`}
                    >
                      {formatINR(billingSummary.total_outstanding_paise)}
                    </p>
                  </div>
                  <div className="text-right">
                    <span className="text-[11px] text-slate-500 uppercase font-semibold">Cycle / Due</span>
                    <p className="text-xs font-semibold text-slate-800">
                      {billingSummary.next_due_date ? formatDateIST(billingSummary.next_due_date) : 'Up to date'}
                    </p>
                  </div>
                </div>

                <div className="p-2.5 bg-slate-50 rounded border border-slate-200 space-y-1 font-mono text-[11px]">
                  <div className="flex justify-between">
                    <span className="text-slate-500">Rate:</span>
                    <span className="font-semibold text-slate-900">₹6.50 / sq ft</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Unit:</span>
                    <span className="font-semibold text-slate-900">
                      {selectedFlat.tower_number}-{selectedFlat.flat_number} ({flatDetail?.area_sqft || 0} sq ft)
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Latest Invoice:</span>
                    <span className="font-semibold text-indigo-600">
                      {billingSummary.latest_invoice ? billingSummary.latest_invoice.invoice_number : 'None'}
                    </span>
                  </div>
                </div>

                {/* 1-Tap Pay Now CTA */}
                <div className="flex gap-2 pt-1">
                  {billingSummary.total_outstanding_paise > 0 ? (
                    <Button
                      size="sm"
                      variant="primary"
                      onClick={() => navigate('/resident/billing')}
                      className="w-full text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white"
                    >
                      1-Tap Pay Now ({formatINR(billingSummary.total_outstanding_paise)})
                      <ArrowRight className="h-3.5 w-3.5 ml-1" />
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      variant="primary"
                      onClick={() => navigate('/resident/billing')}
                      className="w-full text-xs"
                    >
                      View Billing History & Receipts
                      <ArrowRight className="h-3.5 w-3.5 ml-1" />
                    </Button>
                  )}
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>

        {/* Facility Helpdesk & AI Complaints Card */}
        <Card className="border-l-4 border-l-emerald-600">
          <CardHeader>
            <CardTitle className="text-sm font-semibold flex items-center justify-between">
              <span className="flex items-center gap-2">
                <LifeBuoy className="h-4 w-4 text-emerald-600" />
                <span>Facility Helpdesk</span>
              </span>
              <Badge variant={activeComplaints.length > 0 ? 'warning' : 'success'}>
                {activeComplaints.length > 0 ? `${activeComplaints.length} Active Ticket${activeComplaints.length > 1 ? 's' : ''}` : 'No Active Tickets'}
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-xs text-slate-600">
            {isComplaintsLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-8 w-full" />
              </div>
            ) : (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3 p-3 bg-slate-50 rounded-lg border border-slate-200">
                  <div>
                    <span className="text-[11px] text-slate-500 uppercase font-semibold">Active Issues</span>
                    <p className="text-xl font-bold text-slate-900">{activeComplaints.length}</p>
                    <span className="text-[10px] text-slate-500">Under resolution</span>
                  </div>
                  <div className="text-right">
                    <span className="text-[11px] text-slate-500 uppercase font-semibold">Total Raised</span>
                    <p className="text-xl font-bold text-indigo-600">{residentComplaints.length}</p>
                    <span className="text-[10px] text-slate-500">All-time tickets</span>
                  </div>
                </div>

                {latestComplaint ? (
                  <div className="p-2.5 bg-slate-50 rounded border border-slate-200 space-y-1 text-[11px]">
                    <div className="flex items-center justify-between">
                      <span className="text-slate-500">Recent:</span>
                      <Badge variant="neutral" className="text-[10px] py-0">
                        {latestComplaint.status}
                      </Badge>
                    </div>
                    <div className="font-semibold text-slate-900 truncate">
                      {latestComplaint.title}
                    </div>
                    <div className="flex items-center justify-between text-slate-500 text-[10px]">
                      <span>{latestComplaint.category}</span>
                      <span>{new Date(latestComplaint.created_at).toLocaleDateString()}</span>
                    </div>
                  </div>
                ) : (
                  <div className="p-3 bg-emerald-50 rounded border border-emerald-100 flex items-center gap-2 text-emerald-800 text-[11px]">
                    <CheckCircle2 className="h-4 w-4 text-emerald-600 flex-shrink-0" />
                    <span>No active complaints recorded. All facility services operating normally.</span>
                  </div>
                )}

                {/* 1-Tap Raise Complaint CTA */}
                <div className="flex gap-2 pt-1">
                  <Button
                    size="sm"
                    variant="primary"
                    onClick={() => navigate('/resident/complaints')}
                    className="w-full text-xs font-semibold flex items-center justify-center gap-1.5"
                  >
                    <PlusCircle className="h-3.5 w-3.5" />
                    1-Tap Raise Complaint
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Amenity & Clubhouse Bookings Card */}
        <Card className="border-l-4 border-l-emerald-600 md:col-span-2">
          <CardHeader>
            <CardTitle className="text-sm font-semibold flex items-center justify-between">
              <span className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-emerald-600" />
                <span>Township Amenities & Clubhouse</span>
              </span>
              <Badge variant="success">AVAILABLE</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-xs text-slate-600 leading-relaxed">
              Reserve badminton courts, tennis courts, olympic swimming pool, fitness gym, and community halls with instant slot confirmation.
            </p>
            <div className="flex flex-col sm:flex-row gap-2 pt-1">
              <Button
                size="sm"
                variant="primary"
                onClick={() => navigate('/resident/amenities')}
                className="w-full sm:w-auto text-xs font-semibold flex items-center justify-center gap-1.5 px-6"
              >
                <span>Browse & Book Amenities</span>
                <ArrowRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

