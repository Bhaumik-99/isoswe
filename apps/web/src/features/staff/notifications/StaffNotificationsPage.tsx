import React, { useState, useEffect, useCallback } from 'react';
import {
  Plus,
  Edit2,
  Send,
  Archive,
  RefreshCw,
  Pin,
  AlertTriangle,
  CheckCircle,
  Clock,
  Search,
  ShieldCheck,
  Mail,
  MessageSquare,
  Smartphone,
  ChevronLeft,
  ChevronRight,
  X,
  Building,
  Flame,
  FileText,
} from 'lucide-react';
import { notificationService } from '../../../services/notificationService';
import {
  CreateNoticePayload,
  NoticeCategory,
  NoticeItem,
  NoticePriority,
  NoticeStatus,
  NoticeTargetType,
  StaffNotificationOverview,
  UpdateNoticePayload,
} from '../../../types';
import { Badge } from '../../../components/ui/Badge';
import { Button } from '../../../components/ui/Button';
import { Alert } from '../../../components/ui/Alert';

const KNOWN_TOWERS = [
  { id: '22222222-2222-2222-2222-222222222207', name: 'Tower 7 (T07)' },
  { id: '22222222-2222-2222-2222-222222222212', name: 'Tower 12 (T12)' },
  { id: '22222222-2222-2222-2222-222222222221', name: 'Tower 21 (T21)' },
];

export const StaffNotificationsPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'NOTICES' | 'DELIVERIES'>('NOTICES');

  // --- Official Notices State ---
  const [notices, setNotices] = useState<NoticeItem[]>([]);
  const [noticesLoading, setNoticesLoading] = useState<boolean>(true);
  const [noticesError, setNoticesError] = useState<string | null>(null);
  const [noticeSearch, setNoticeSearch] = useState<string>('');
  const [noticeStatusFilter, setNoticeStatusFilter] = useState<NoticeStatus | 'ALL'>('ALL');
  const [noticeCategoryFilter, setNoticeCategoryFilter] = useState<NoticeCategory | 'ALL'>('ALL');
  const [noticePage, setNoticePage] = useState<number>(1);
  const [totalNoticePages, setTotalNoticePages] = useState<number>(1);
  const [totalNotices, setTotalNotices] = useState<number>(0);

  // Notice Composer Modal State
  const [isComposerOpen, setIsComposerOpen] = useState<boolean>(false);
  const [editingNotice, setEditingNotice] = useState<NoticeItem | null>(null);
  const [composerSubmitting, setComposerSubmitting] = useState<boolean>(false);
  const [composerError, setComposerError] = useState<string | null>(null);

  // Form Fields
  const [formData, setFormData] = useState<{
    title: string;
    body: string;
    category: NoticeCategory;
    priority: NoticePriority;
    target_type: NoticeTargetType;
    target_tower_id: string;
    target_flat_id: string;
    is_pinned: boolean;
    publish_now: boolean;
    published_at: string;
    expires_at: string;
    deliver_emergency: boolean;
  }>({
    title: '',
    body: '',
    category: 'CIRCULAR',
    priority: 'NORMAL',
    target_type: 'SOCIETY',
    target_tower_id: '',
    target_flat_id: '',
    is_pinned: false,
    publish_now: true,
    published_at: '',
    expires_at: '',
    deliver_emergency: false,
  });

  // --- Delivery Overview State ---
  const [deliveryLoading, setDeliveryLoading] = useState(true);
  const [deliveryData, setDeliveryData] = useState<StaffNotificationOverview>({
    items: [],
    total: 0,
    delivered_count: 0,
    failed_count: 0,
    retrying_count: 0,
    page: 1,
    page_size: 20,
    total_pages: 1,
  });
  const [deliveryPage, setDeliveryPage] = useState(1);

  // --- Fetch Notices ---
  const loadNotices = useCallback(async () => {
    setNoticesLoading(true);
    setNoticesError(null);
    try {
      const statusParam = noticeStatusFilter === 'ALL' ? undefined : noticeStatusFilter;
      const catParam = noticeCategoryFilter === 'ALL' ? undefined : noticeCategoryFilter;
      const res = await notificationService.getStaffNotices(
        noticePage,
        15,
        statusParam,
        catParam,
        undefined,
        noticeSearch.trim() || undefined
      );
      setNotices(res.items);
      setTotalNotices(res.total);
      setTotalNoticePages(res.total_pages);
    } catch {
      setNoticesError('Failed to load official notices. Please check network.');
    } finally {
      setNoticesLoading(false);
    }
  }, [noticePage, noticeStatusFilter, noticeCategoryFilter, noticeSearch]);

  // --- Fetch Deliveries ---
  const loadDeliveries = useCallback(async () => {
    setDeliveryLoading(true);
    try {
      const res = await notificationService.getStaffOverview(deliveryPage, 20);
      setDeliveryData(res);
    } catch {
      // Ignore
    } finally {
      setDeliveryLoading(false);
    }
  }, [deliveryPage]);

  useEffect(() => {
    if (activeTab === 'NOTICES') {
      loadNotices();
    } else {
      loadDeliveries();
    }
  }, [activeTab, loadNotices, loadDeliveries]);

  // --- Open Composer for Create or Edit ---
  const handleOpenComposer = (noticeToEdit?: NoticeItem) => {
    if (noticeToEdit) {
      setEditingNotice(noticeToEdit);
      setFormData({
        title: noticeToEdit.title,
        body: noticeToEdit.body,
        category: noticeToEdit.category,
        priority: noticeToEdit.priority,
        target_type: noticeToEdit.target_type,
        target_tower_id: noticeToEdit.target_tower_id || '',
        target_flat_id: noticeToEdit.target_flat_id || '',
        is_pinned: noticeToEdit.is_pinned,
        publish_now: noticeToEdit.status === 'PUBLISHED',
        published_at: noticeToEdit.published_at ? noticeToEdit.published_at.slice(0, 16) : '',
        expires_at: noticeToEdit.expires_at ? noticeToEdit.expires_at.slice(0, 16) : '',
        deliver_emergency: false,
      });
    } else {
      setEditingNotice(null);
      setFormData({
        title: '',
        body: '',
        category: 'CIRCULAR',
        priority: 'NORMAL',
        target_type: 'SOCIETY',
        target_tower_id: '',
        target_flat_id: '',
        is_pinned: false,
        publish_now: true,
        published_at: '',
        expires_at: '',
        deliver_emergency: false,
      });
    }
    setComposerError(null);
    setIsComposerOpen(true);
  };

  // --- Submit Composer ---
  const handleSaveNotice = async (status: NoticeStatus) => {
    if (!formData.title.trim()) {
      setComposerError('Notice title is required.');
      return;
    }
    if (!formData.body.trim()) {
      setComposerError('Notice body content is required.');
      return;
    }
    if (formData.target_type === 'TOWER' && !formData.target_tower_id) {
      setComposerError('Please select a target tower.');
      return;
    }
    if (formData.target_type === 'FLAT' && !formData.target_flat_id) {
      setComposerError('Please enter a target flat ID.');
      return;
    }

    setComposerSubmitting(true);
    setComposerError(null);

    const payload: CreateNoticePayload | UpdateNoticePayload = {
      title: formData.title.trim(),
      body: formData.body.trim(),
      category: formData.category,
      priority: formData.priority,
      status,
      target_type: formData.target_type,
      target_tower_id: formData.target_type === 'TOWER' ? formData.target_tower_id : null,
      target_flat_id: formData.target_type === 'FLAT' ? formData.target_flat_id : null,
      is_pinned: formData.is_pinned,
      published_at: formData.published_at ? new Date(formData.published_at).toISOString() : null,
      expires_at: formData.expires_at ? new Date(formData.expires_at).toISOString() : null,
      deliver_emergency: formData.deliver_emergency,
    };

    try {
      if (editingNotice) {
        await notificationService.updateStaffNotice(editingNotice.id, payload);
      } else {
        await notificationService.createStaffNotice(payload as CreateNoticePayload);
      }
      setIsComposerOpen(false);
      loadNotices();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to save notice.';
      setComposerError(msg);
    } finally {
      setComposerSubmitting(false);
    }
  };

  // --- Publish Notice Action ---
  const handlePublishNotice = async (noticeId: string) => {
    try {
      await notificationService.publishStaffNotice(noticeId);
      loadNotices();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Failed to publish notice');
    }
  };

  // --- Archive Notice Action ---
  const handleArchiveNotice = async (noticeId: string) => {
    if (!confirm('Are you sure you want to archive this notice? It will no longer be visible in resident feeds.')) {
      return;
    }
    try {
      await notificationService.archiveStaffNotice(noticeId);
      loadNotices();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Failed to archive notice');
    }
  };

  const getCategoryBadgeVariant = (category: NoticeCategory) => {
    switch (category) {
      case 'EMERGENCY':
        return 'danger';
      case 'CIRCULAR':
        return 'info';
      case 'MAINTENANCE':
        return 'warning';
      case 'EVENT':
        return 'success';
      default:
        return 'neutral';
    }
  };

  const getNoticeStatusBadge = (status: NoticeStatus, publishedAt?: string | null) => {
    const isScheduled =
      status === 'PUBLISHED' && publishedAt && new Date(publishedAt).getTime() > Date.now();

    if (isScheduled) {
      return (
        <Badge variant="warning" className="flex items-center gap-1">
          <Clock className="h-3 w-3" />
          <span>SCHEDULED</span>
        </Badge>
      );
    }

    switch (status) {
      case 'PUBLISHED':
        return (
          <Badge variant="success" className="flex items-center gap-1">
            <CheckCircle className="h-3 w-3" />
            <span>PUBLISHED</span>
          </Badge>
        );
      case 'DRAFT':
        return (
          <Badge variant="neutral" className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            <span>DRAFT</span>
          </Badge>
        );
      case 'ARCHIVED':
        return (
          <Badge variant="neutral" className="flex items-center gap-1 opacity-70">
            <Archive className="h-3 w-3" />
            <span>ARCHIVED</span>
          </Badge>
        );
    }
  };

  const getChannelIcon = (channel: string) => {
    switch (channel.toUpperCase()) {
      case 'EMAIL':
        return <Mail className="h-4 w-4 text-sky-600" />;
      case 'SMS':
        return <MessageSquare className="h-4 w-4 text-emerald-600" />;
      default:
        return <Smartphone className="h-4 w-4 text-indigo-600" />;
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* Top Header Card */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="w-10 h-10 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center font-bold">
              <ShieldCheck className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-slate-900 tracking-tight">
                Township Communications & Deliveries
              </h1>
              <p className="text-xs text-slate-500 mt-0.5">
                Official federation circulars, maintenance advisories, emergency alerts, and delivery audit telemetry.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {activeTab === 'NOTICES' && (
            <Button
              size="sm"
              onClick={() => handleOpenComposer()}
              className="gap-1.5 font-semibold text-xs shadow-xs"
            >
              <Plus className="h-4 w-4" />
              <span>Compose Notice</span>
            </Button>
          )}

          <Button
            variant="outline"
            size="sm"
            onClick={activeTab === 'NOTICES' ? loadNotices : loadDeliveries}
            disabled={activeTab === 'NOTICES' ? noticesLoading : deliveryLoading}
            className="flex items-center gap-1.5 text-xs font-semibold"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${
                (activeTab === 'NOTICES' ? noticesLoading : deliveryLoading) ? 'animate-spin' : ''
              }`}
            />
            <span>Refresh</span>
          </Button>
        </div>
      </div>

      {/* Main Tabs Navigation */}
      <div className="flex border-b border-slate-200">
        <button
          onClick={() => setActiveTab('NOTICES')}
          className={`pb-3 px-4 text-sm font-semibold border-b-2 flex items-center gap-2 transition-colors ${
            activeTab === 'NOTICES'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-slate-500 hover:text-slate-700'
          }`}
        >
          <FileText className="h-4 w-4" />
          <span>Official Notices & Circulars</span>
          {totalNotices > 0 && (
            <span className="text-[11px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full font-medium">
              {totalNotices}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab('DELIVERIES')}
          className={`pb-3 px-4 text-sm font-semibold border-b-2 flex items-center gap-2 transition-colors ${
            activeTab === 'DELIVERIES'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-slate-500 hover:text-slate-700'
          }`}
        >
          <Send className="h-4 w-4" />
          <span>Multi-Channel Delivery Audit</span>
        </button>
      </div>

      {/* ========================================================================= */}
      {/* TAB 1: OFFICIAL NOTICES COMPOSER & MANAGEMENT                             */}
      {/* ========================================================================= */}
      {activeTab === 'NOTICES' && (
        <div className="space-y-4">
          {/* Filter & Search Bar */}
          <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search className="h-3.5 w-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  placeholder="Search notices..."
                  value={noticeSearch}
                  onChange={(e) => setNoticeSearch(e.target.value)}
                  className="pl-8 pr-3 py-1.5 text-xs rounded-lg border border-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 w-48 sm:w-60"
                />
              </div>

              {/* Status Filter */}
              <select
                value={noticeStatusFilter}
                onChange={(e) => setNoticeStatusFilter(e.target.value as NoticeStatus | 'ALL')}
                className="text-xs py-1.5 px-3 rounded-lg border border-slate-200 bg-white text-slate-700 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                <option value="ALL">All Statuses</option>
                <option value="PUBLISHED">Published</option>
                <option value="DRAFT">Drafts</option>
                <option value="ARCHIVED">Archived</option>
              </select>

              {/* Category Filter */}
              <select
                value={noticeCategoryFilter}
                onChange={(e) => setNoticeCategoryFilter(e.target.value as NoticeCategory | 'ALL')}
                className="text-xs py-1.5 px-3 rounded-lg border border-slate-200 bg-white text-slate-700 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                <option value="ALL">All Categories</option>
                <option value="CIRCULAR">Circular</option>
                <option value="MAINTENANCE">Maintenance</option>
                <option value="EMERGENCY">Emergency</option>
                <option value="EVENT">Event</option>
                <option value="GENERAL">General</option>
              </select>
            </div>

            <span className="text-xs text-slate-500 font-medium">
              Showing {notices.length} of {totalNotices} notice(s)
            </span>
          </div>

          {noticesError && (
            <Alert variant="error">
              <AlertTriangle className="h-4 w-4" />
              <span>{noticesError}</span>
            </Alert>
          )}

          {/* Notices Table */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-semibold uppercase tracking-wider">
                  <tr>
                    <th className="py-3 px-4">Title & Scope</th>
                    <th className="py-3 px-4">Category</th>
                    <th className="py-3 px-4">Priority</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Publication / Expiry</th>
                    <th className="py-3 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {noticesLoading ? (
                    <tr>
                      <td colSpan={6} className="text-center py-12 text-slate-400">
                        <RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2 text-indigo-500" />
                        Loading notices...
                      </td>
                    </tr>
                  ) : notices.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="text-center py-12 text-slate-500">
                        No notices found matching current filters. Click "Compose Notice" to create one.
                      </td>
                    </tr>
                  ) : (
                    notices.map((n) => (
                      <tr key={n.id} className="hover:bg-slate-50/70 transition-colors">
                        <td className="py-3.5 px-4 max-w-xs">
                          <div className="flex items-center gap-1.5">
                            {n.is_pinned && (
                              <Pin className="h-3 w-3 text-amber-600 fill-amber-500 shrink-0" />
                            )}
                            <span className="font-bold text-slate-900 truncate block">
                              {n.title}
                            </span>
                          </div>
                          <span className="text-[11px] text-slate-500 line-clamp-1 mt-0.5">
                            {n.body}
                          </span>
                          <div className="flex items-center gap-1 text-[10px] text-slate-400 mt-1">
                            <Building className="h-2.5 w-2.5" />
                            {n.target_type === 'SOCIETY' && 'Society Wide'}
                            {n.target_type === 'TOWER' &&
                              `Tower: ${n.target_tower_name || 'Specific Tower'}`}
                            {n.target_type === 'FLAT' &&
                              `Flat: ${n.target_flat_number || 'Specific Unit'}`}
                          </div>
                        </td>

                        <td className="py-3.5 px-4">
                          <Badge variant={getCategoryBadgeVariant(n.category)} className="text-[11px]">
                            {n.category}
                          </Badge>
                        </td>

                        <td className="py-3.5 px-4">
                          {n.priority === 'URGENT' ? (
                            <Badge variant="danger" className="text-[11px]">
                              URGENT
                            </Badge>
                          ) : n.priority === 'HIGH' ? (
                            <Badge variant="warning" className="text-[11px]">
                              HIGH
                            </Badge>
                          ) : (
                            <span className="text-slate-500 font-medium">{n.priority}</span>
                          )}
                        </td>

                        <td className="py-3.5 px-4">
                          {getNoticeStatusBadge(n.status, n.published_at)}
                        </td>

                        <td className="py-3.5 px-4 text-slate-500">
                          {n.published_at ? (
                            <div>
                              <span>{new Date(n.published_at).toLocaleDateString('en-IN')}</span>
                              {n.expires_at && (
                                <div className="text-[10px] text-amber-700">
                                  Exp: {new Date(n.expires_at).toLocaleDateString('en-IN')}
                                </div>
                              )}
                            </div>
                          ) : (
                            <span className="text-slate-400 italic">Not published</span>
                          )}
                        </td>

                        <td className="py-3.5 px-4 text-right space-x-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleOpenComposer(n)}
                            className="h-7 px-2 text-xs font-semibold text-slate-600 hover:text-slate-900"
                            title="Edit Notice"
                          >
                            <Edit2 className="h-3 w-3 mr-1" />
                            Edit
                          </Button>

                          {n.status !== 'PUBLISHED' && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handlePublishNotice(n.id)}
                              className="h-7 px-2 text-xs font-semibold text-emerald-600 hover:text-emerald-800"
                              title="Publish Now"
                            >
                              <Send className="h-3 w-3 mr-1" />
                              Publish
                            </Button>
                          )}

                          {n.status === 'PUBLISHED' && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleArchiveNotice(n.id)}
                              className="h-7 px-2 text-xs font-semibold text-rose-600 hover:text-rose-800"
                              title="Archive Notice"
                            >
                              <Archive className="h-3 w-3 mr-1" />
                              Archive
                            </Button>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalNoticePages > 1 && (
              <div className="px-6 py-3 border-t border-slate-200 bg-slate-50/50 flex items-center justify-between">
                <span className="text-xs text-slate-500">
                  Page {noticePage} of {totalNoticePages}
                </span>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={noticePage <= 1}
                    onClick={() => setNoticePage((p) => p - 1)}
                    className="h-7 px-2.5 text-xs"
                  >
                    <ChevronLeft className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={noticePage >= totalNoticePages}
                    onClick={() => setNoticePage((p) => p + 1)}
                    className="h-7 px-2.5 text-xs"
                  >
                    <ChevronRight className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 2: MULTI-CHANNEL DELIVERY OVERVIEW & TELEMETRY                        */}
      {/* ========================================================================= */}
      {activeTab === 'DELIVERIES' && (
        <div className="space-y-6">
          {/* KPI Cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-white rounded-xl p-5 border border-slate-200 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                  Total Dispatches
                </span>
                <Send className="h-4 w-4 text-indigo-600" />
              </div>
              <p className="text-2xl font-bold text-slate-900 mt-2">
                {deliveryData.total.toLocaleString()}
              </p>
              <span className="text-[11px] text-slate-400">All communication channels</span>
            </div>

            <div className="bg-white rounded-xl p-5 border border-slate-200 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                  Delivered
                </span>
                <CheckCircle className="h-4 w-4 text-emerald-600" />
              </div>
              <p className="text-2xl font-bold text-emerald-600 mt-2">
                {deliveryData.delivered_count.toLocaleString()}
              </p>
              <span className="text-[11px] text-slate-400">Confirmed deliveries</span>
            </div>

            <div className="bg-white rounded-xl p-5 border border-slate-200 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                  In Retry Backoff
                </span>
                <Clock className="h-4 w-4 text-amber-500" />
              </div>
              <p className="text-2xl font-bold text-amber-600 mt-2">
                {deliveryData.retrying_count.toLocaleString()}
              </p>
              <span className="text-[11px] text-slate-400">Automatic exponential backoff</span>
            </div>

            <div className="bg-white rounded-xl p-5 border border-slate-200 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                  Failed / Suppressed
                </span>
                <AlertTriangle className="h-4 w-4 text-rose-500" />
              </div>
              <p className="text-2xl font-bold text-rose-600 mt-2">
                {deliveryData.failed_count.toLocaleString()}
              </p>
              <span className="text-[11px] text-slate-400">Permanent failures & opt-outs</span>
            </div>
          </div>

          {/* Deliveries Audit Table */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
              <h3 className="font-bold text-sm text-slate-900">Recent Delivery Log</h3>
              <span className="text-xs text-slate-500">
                Page {deliveryData.page} of {deliveryData.total_pages}
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-semibold uppercase tracking-wider">
                  <tr>
                    <th className="py-3 px-4">Channel</th>
                    <th className="py-3 px-4">Provider</th>
                    <th className="py-3 px-4">Recipient ID</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4 text-center">Attempts</th>
                    <th className="py-3 px-4">Error Code / Details</th>
                    <th className="py-3 px-4">Timestamp</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {deliveryLoading ? (
                    <tr>
                      <td colSpan={7} className="text-center py-12 text-slate-400">
                        <RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2 text-indigo-500" />
                        Loading delivery records...
                      </td>
                    </tr>
                  ) : deliveryData.items.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="text-center py-12 text-slate-500">
                        No delivery records found for this society.
                      </td>
                    </tr>
                  ) : (
                    deliveryData.items.map((item) => (
                      <tr key={item.id} className="hover:bg-slate-50">
                        <td className="py-3 px-4 flex items-center gap-2">
                          {getChannelIcon(item.channel)}
                          <span className="font-medium">{item.channel}</span>
                        </td>
                        <td className="py-3 px-4 text-slate-600">{item.provider}</td>
                        <td className="py-3 px-4 font-mono text-[11px] text-slate-600 truncate max-w-[120px]">
                          {item.recipient_user_id}
                        </td>
                        <td className="py-3 px-4">
                          <Badge
                            variant={
                              item.status === 'DELIVERED' || item.status === 'SENT'
                                ? 'success'
                                : item.status === 'RETRYING'
                                ? 'warning'
                                : item.status === 'FAILED'
                                ? 'danger'
                                : 'neutral'
                            }
                          >
                            {item.status}
                          </Badge>
                        </td>
                        <td className="py-3 px-4 text-center font-semibold">
                          {item.attempt_count}
                        </td>
                        <td className="py-3 px-4 text-slate-500 max-w-xs truncate">
                          {item.last_error_code || item.last_error_message || (
                            <span className="text-slate-300">-</span>
                          )}
                        </td>
                        <td className="py-3 px-4 text-slate-500">
                          {new Date(item.created_at).toLocaleString('en-IN', {
                            month: 'short',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {deliveryData.total_pages > 1 && (
              <div className="px-6 py-4 border-t border-slate-200 flex items-center justify-between">
                <span className="text-xs text-slate-500">
                  Page {deliveryData.page} of {deliveryData.total_pages}
                </span>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={deliveryPage <= 1}
                    onClick={() => setDeliveryPage((p) => p - 1)}
                    className="flex items-center gap-1"
                  >
                    <ChevronLeft className="h-4 w-4" />
                    <span>Previous</span>
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={deliveryPage >= deliveryData.total_pages}
                    onClick={() => setDeliveryPage((p) => p + 1)}
                    className="flex items-center gap-1"
                  >
                    <span>Next</span>
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* NOTICE COMPOSER / EDITOR MODAL                                            */}
      {/* ========================================================================= */}
      {isComposerOpen && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl border border-slate-200 w-full max-w-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-slate-900">
                  {editingNotice ? 'Edit Official Notice' : 'Compose Official Township Notice'}
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Targeted circulars, water/power maintenance alerts, and emergency announcements.
                </p>
              </div>
              <button
                onClick={() => setIsComposerOpen(false)}
                className="text-slate-400 hover:text-slate-600 p-1.5 rounded-lg hover:bg-slate-100"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Modal Body Form */}
            <div className="p-6 space-y-4 max-h-[75vh] overflow-y-auto">
              {composerError && (
                <Alert variant="error">
                  <AlertTriangle className="h-4 w-4" />
                  <span>{composerError}</span>
                </Alert>
              )}

              {/* Title */}
              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
                  Notice Title *
                </label>
                <input
                  type="text"
                  placeholder="e.g. Annual General Meeting or Power Cut Advisory"
                  value={formData.title}
                  onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                  className="w-full text-xs sm:text-sm px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              {/* Category & Priority Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
                    Notice Category *
                  </label>
                  <select
                    value={formData.category}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        category: e.target.value as NoticeCategory,
                        deliver_emergency:
                          e.target.value === 'EMERGENCY' ? true : formData.deliver_emergency,
                      })
                    }
                    className="w-full text-xs sm:text-sm px-3 py-2 rounded-lg border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="CIRCULAR">Federation Circular</option>
                    <option value="MAINTENANCE">Maintenance Advisory</option>
                    <option value="EMERGENCY">Emergency Announcement</option>
                    <option value="EVENT">Community Event</option>
                    <option value="GENERAL">General Notice</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
                    Priority Level *
                  </label>
                  <select
                    value={formData.priority}
                    onChange={(e) =>
                      setFormData({ ...formData, priority: e.target.value as NoticePriority })
                    }
                    className="w-full text-xs sm:text-sm px-3 py-2 rounded-lg border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="LOW">Low</option>
                    <option value="NORMAL">Normal</option>
                    <option value="HIGH">High Priority</option>
                    <option value="URGENT">Urgent / Emergency</option>
                  </select>
                </div>
              </div>

              {/* Targeting Scope */}
              <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-3">
                <span className="block text-xs font-bold text-slate-700 uppercase tracking-wider">
                  Target Audience *
                </span>
                <div className="grid grid-cols-3 gap-2">
                  {(['SOCIETY', 'TOWER', 'FLAT'] as const).map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => setFormData({ ...formData, target_type: t })}
                      className={`py-2 px-3 text-xs font-semibold rounded-lg border text-center transition-all ${
                        formData.target_type === t
                          ? 'bg-indigo-600 text-white border-indigo-600 shadow-xs'
                          : 'bg-white text-slate-700 border-slate-300 hover:bg-slate-100'
                      }`}
                    >
                      {t === 'SOCIETY' && 'All Society'}
                      {t === 'TOWER' && 'Specific Tower'}
                      {t === 'FLAT' && 'Specific Flat'}
                    </button>
                  ))}
                </div>

                {formData.target_type === 'TOWER' && (
                  <div className="pt-2">
                    <label className="block text-xs font-medium text-slate-700 mb-1">
                      Select Tower *
                    </label>
                    <select
                      value={formData.target_tower_id}
                      onChange={(e) => setFormData({ ...formData, target_tower_id: e.target.value })}
                      className="w-full text-xs px-3 py-2 rounded-lg border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    >
                      <option value="">-- Choose Tower --</option>
                      {KNOWN_TOWERS.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.name}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                {formData.target_type === 'FLAT' && (
                  <div className="pt-2">
                    <label className="block text-xs font-medium text-slate-700 mb-1">
                      Target Flat ID (UUID) *
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. 33333333-3333-3333-3333-333333331203"
                      value={formData.target_flat_id}
                      onChange={(e) => setFormData({ ...formData, target_flat_id: e.target.value })}
                      className="w-full text-xs font-mono px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                  </div>
                )}
              </div>

              {/* Notice Body */}
              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
                  Notice Content *
                </label>
                <textarea
                  rows={5}
                  placeholder="Provide detailed instructions, timings, affected towers, and contact numbers..."
                  value={formData.body}
                  onChange={(e) => setFormData({ ...formData, body: e.target.value })}
                  className="w-full text-xs sm:text-sm px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              {/* Pinning & Scheduling */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
                    Scheduled Publish Date & Time
                  </label>
                  <input
                    type="datetime-local"
                    value={formData.published_at}
                    onChange={(e) => setFormData({ ...formData, published_at: e.target.value })}
                    className="w-full text-xs px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                  <span className="text-[10px] text-slate-400">Leave blank to publish immediately upon approval.</span>
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
                    Notice Expiry Date
                  </label>
                  <input
                    type="datetime-local"
                    value={formData.expires_at}
                    onChange={(e) => setFormData({ ...formData, expires_at: e.target.value })}
                    className="w-full text-xs px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                  <span className="text-[10px] text-slate-400">Optional. Notice archives automatically after expiry.</span>
                </div>
              </div>

              {/* Pinning and Emergency Checkboxes */}
              <div className="space-y-2 pt-2 border-t border-slate-100">
                <label className="flex items-center gap-2 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={formData.is_pinned}
                    onChange={(e) => setFormData({ ...formData, is_pinned: e.target.checked })}
                    className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 h-4 w-4"
                  />
                  <span className="text-xs font-semibold text-slate-800 flex items-center gap-1">
                    <Pin className="h-3.5 w-3.5 text-amber-600" /> Pin notice to top of resident feed
                  </span>
                </label>

                <label className="flex items-center gap-2 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={formData.deliver_emergency}
                    onChange={(e) =>
                      setFormData({ ...formData, deliver_emergency: e.target.checked })
                    }
                    className="rounded border-slate-300 text-rose-600 focus:ring-rose-500 h-4 w-4"
                  />
                  <span className="text-xs font-semibold text-rose-900 flex items-center gap-1">
                    <Flame className="h-3.5 w-3.5 text-rose-600" /> Dispatch immediate emergency notification & outbox broadcast to all targeted residents
                  </span>
                </label>
              </div>
            </div>

            {/* Modal Footer Actions */}
            <div className="px-6 py-4 bg-slate-50 border-t border-slate-200 flex items-center justify-between gap-3">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsComposerOpen(false)}
                disabled={composerSubmitting}
                className="text-xs font-semibold"
              >
                Cancel
              </Button>

              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleSaveNotice('DRAFT')}
                  disabled={composerSubmitting}
                  className="text-xs font-semibold"
                >
                  Save as Draft
                </Button>

                <Button
                  size="sm"
                  onClick={() => handleSaveNotice('PUBLISHED')}
                  disabled={composerSubmitting}
                  className="text-xs font-semibold gap-1"
                >
                  <Send className="h-3.5 w-3.5" />
                  <span>{composerSubmitting ? 'Publishing...' : 'Publish Notice'}</span>
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
