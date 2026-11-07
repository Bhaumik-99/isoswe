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
  FlatOption,
  NoticeCategory,
  NoticeItem,
  NoticeOverviewStats,
  NoticePriority,
  NoticeStatus,
  NoticeTargetType,
  StaffNotificationOverview,
  TowerOption,
  UpdateNoticePayload,
} from '../../../types';
import { Badge } from '../../../components/ui/Badge';
import { Button } from '../../../components/ui/Button';
import { Alert } from '../../../components/ui/Alert';

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
  const [overviewStats, setOverviewStats] = useState<NoticeOverviewStats | null>(null);
  const [triggeringScheduled, setTriggeringScheduled] = useState<boolean>(false);

  // Notice Composer Modal State
  const [isComposerOpen, setIsComposerOpen] = useState<boolean>(false);
  const [editingNotice, setEditingNotice] = useState<NoticeItem | null>(null);
  const [composerSubmitting, setComposerSubmitting] = useState<boolean>(false);
  const [composerError, setComposerError] = useState<string | null>(null);

  // Dynamic Targeting Options State
  const [availableTowers, setAvailableTowers] = useState<TowerOption[]>([]);
  const [availableFlats, setAvailableFlats] = useState<FlatOption[]>([]);
  const [loadingTargets, setLoadingTargets] = useState<boolean>(false);
  const [flatFilterTower, setFlatFilterTower] = useState<string>('ALL');
  const [flatSearchQuery, setFlatSearchQuery] = useState<string>('');
  const [manualFlatIdInput, setManualFlatIdInput] = useState<string>('');

  // Form Fields
  const [formData, setFormData] = useState<{
    title: string;
    body: string;
    category: NoticeCategory;
    priority: NoticePriority;
    target_type: NoticeTargetType;
    target_tower_id: string;
    target_tower_ids: string[];
    target_flat_id: string;
    target_flat_ids: string[];
    is_pinned: boolean;
    publish_now: boolean;
    published_at: string;
    expires_at: string;
    deliver_emergency: boolean;
    confirm_emergency_broadcast: boolean;
  }>({
    title: '',
    body: '',
    category: 'CIRCULAR',
    priority: 'NORMAL',
    target_type: 'SOCIETY',
    target_tower_id: '',
    target_tower_ids: [],
    target_flat_id: '',
    target_flat_ids: [],
    is_pinned: false,
    publish_now: true,
    published_at: '',
    expires_at: '',
    deliver_emergency: false,
    confirm_emergency_broadcast: false,
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
  const loadOverview = useCallback(async () => {
    try {
      const stats = await notificationService.getStaffNoticesOverview();
      setOverviewStats(stats);
    } catch {
      // Ignore
    }
  }, []);

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
      loadOverview();
    } catch {
      setNoticesError('Failed to load official notices. Please check network.');
    } finally {
      setNoticesLoading(false);
    }
  }, [noticePage, noticeStatusFilter, noticeCategoryFilter, noticeSearch, loadOverview]);

  const handleTriggerPublishScheduled = async () => {
    setTriggeringScheduled(true);
    try {
      const res = await notificationService.triggerPublishScheduledNotices();
      alert(`Scheduled notices processor: ${res.length} notice(s) published.`);
      loadNotices();
      loadOverview();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Failed to trigger scheduled publish');
    } finally {
      setTriggeringScheduled(false);
    }
  };

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

  // --- Fetch Dynamic Targeting Options ---
  const loadTargetingOptions = useCallback(async () => {
    setLoadingTargets(true);
    try {
      const res = await notificationService.getStaffTargetingOptions();
      setAvailableTowers(res.towers || []);
      setAvailableFlats(res.flats || []);
    } catch {
      try {
        const towers = await notificationService.getStaffTowers();
        setAvailableTowers(towers || []);
      } catch {
        // Ignore
      }
    } finally {
      setLoadingTargets(false);
    }
  }, []);

  useEffect(() => {
    loadTargetingOptions();
  }, [loadTargetingOptions]);

  // --- Open Composer for Create or Edit ---
  const handleOpenComposer = (noticeToEdit?: NoticeItem) => {
    if (availableTowers.length === 0) {
      loadTargetingOptions();
    }
    if (noticeToEdit) {
      setEditingNotice(noticeToEdit);
      const tIds =
        noticeToEdit.target_tower_ids && noticeToEdit.target_tower_ids.length > 0
          ? noticeToEdit.target_tower_ids
          : noticeToEdit.target_tower_id
          ? [noticeToEdit.target_tower_id]
          : [];
      const fIds =
        noticeToEdit.target_flat_ids && noticeToEdit.target_flat_ids.length > 0
          ? noticeToEdit.target_flat_ids
          : noticeToEdit.target_flat_id
          ? [noticeToEdit.target_flat_id]
          : [];

      setFormData({
        title: noticeToEdit.title,
        body: noticeToEdit.body,
        category: noticeToEdit.category,
        priority: noticeToEdit.priority,
        target_type: noticeToEdit.target_type,
        target_tower_id: tIds[0] || '',
        target_tower_ids: tIds,
        target_flat_id: fIds[0] || '',
        target_flat_ids: fIds,
        is_pinned: noticeToEdit.is_pinned,
        publish_now: noticeToEdit.status === 'PUBLISHED',
        published_at: noticeToEdit.published_at ? noticeToEdit.published_at.slice(0, 16) : '',
        expires_at: noticeToEdit.expires_at ? noticeToEdit.expires_at.slice(0, 16) : '',
        deliver_emergency: !!noticeToEdit.deliver_emergency,
        confirm_emergency_broadcast: false,
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
        target_tower_ids: [],
        target_flat_id: '',
        target_flat_ids: [],
        is_pinned: false,
        publish_now: true,
        published_at: '',
        expires_at: '',
        deliver_emergency: false,
        confirm_emergency_broadcast: false,
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
    if (formData.target_type === 'TOWER') {
      if (formData.target_tower_ids.length === 0) {
        setComposerError('Please select at least one target tower.');
        return;
      }
      if (availableTowers.length > 0) {
        const validTowerIds = new Set(availableTowers.map((t) => t.id));
        const invalid = formData.target_tower_ids.filter((id) => !validTowerIds.has(id));
        if (invalid.length > 0) {
          setComposerError('One or more selected towers do not belong to this society.');
          return;
        }
      }
    }
    if (formData.target_type === 'FLAT') {
      if (formData.target_flat_ids.length === 0) {
        setComposerError('Please select or specify at least one target flat.');
        return;
      }
      if (availableFlats.length > 0) {
        const validFlatIds = new Set(availableFlats.map((f) => f.id));
        const invalid = formData.target_flat_ids.filter((id) => !validFlatIds.has(id));
        if (invalid.length > 0) {
          setComposerError('One or more selected flats do not belong to this society.');
          return;
        }
      }
    }

    if (formData.deliver_emergency && !formData.confirm_emergency_broadcast) {
      setComposerError('Explicit confirmation is required before dispatching an emergency broadcast.');
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
      target_tower_ids: formData.target_type === 'TOWER' ? formData.target_tower_ids : [],
      target_tower_id:
        formData.target_type === 'TOWER' && formData.target_tower_ids.length > 0
          ? formData.target_tower_ids[0]
          : null,
      target_flat_ids: formData.target_type === 'FLAT' ? formData.target_flat_ids : [],
      target_flat_id:
        formData.target_type === 'FLAT' && formData.target_flat_ids.length > 0
          ? formData.target_flat_ids[0]
          : null,
      is_pinned: formData.is_pinned,
      published_at: formData.published_at ? new Date(formData.published_at).toISOString() : null,
      expires_at: formData.expires_at ? new Date(formData.expires_at).toISOString() : null,
      deliver_emergency: formData.deliver_emergency,
      confirm_emergency_broadcast: formData.confirm_emergency_broadcast,
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
  const handlePublishNotice = async (notice: NoticeItem) => {
    let payload: { deliver_emergency?: boolean; confirm_emergency_broadcast?: boolean } | undefined;
    if (notice.deliver_emergency) {
      const confirmed = window.confirm(
        '⚠️ EMERGENCY BROADCAST CONFIRMATION:\n\n' +
        'This notice has emergency delivery enabled. Publishing will trigger an immediate emergency notification broadcast to all targeted residents.\n\n' +
        'Do you confirm this emergency broadcast?'
      );
      if (!confirmed) {
        return;
      }
      payload = {
        deliver_emergency: true,
        confirm_emergency_broadcast: true,
      };
    }
    try {
      await notificationService.publishStaffNotice(notice.id, payload);
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
      case 'WATER':
        return 'info';
      case 'ELECTRICITY':
        return 'warning';
      case 'SECURITY':
        return 'neutral';
      case 'EVENT':
        return 'success';
      default:
        return 'neutral';
    }
  };

  const getNoticeStatusBadge = (status: NoticeStatus, publishedAt?: string | null) => {
    const isScheduled =
      (status === 'PUBLISHED' && publishedAt && new Date(publishedAt).getTime() > Date.now()) ||
      status === 'SCHEDULED';

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
      default:
        return <Badge variant="neutral">{status}</Badge>;
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
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={handleTriggerPublishScheduled}
                disabled={triggeringScheduled}
                className="flex items-center gap-1.5 text-xs font-semibold text-amber-700 bg-amber-50 hover:bg-amber-100 border-amber-200"
                title="Scan and publish due scheduled notices"
              >
                <Clock className={`h-3.5 w-3.5 ${triggeringScheduled ? 'animate-spin' : ''}`} />
                <span>Process Due Scheduled</span>
              </Button>

              <Button
                size="sm"
                onClick={() => handleOpenComposer()}
                className="gap-1.5 font-semibold text-xs shadow-xs"
              >
                <Plus className="h-4 w-4" />
                <span>Compose Notice</span>
              </Button>
            </>
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
          {/* 6 KPI Cards Overview */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <div className="bg-white border border-slate-200 rounded-xl p-3 shadow-xs">
              <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Total Notices</span>
              <p className="text-xl font-bold text-slate-900 mt-1">{overviewStats?.total ?? totalNotices}</p>
            </div>
            <div className="bg-white border border-slate-200 rounded-xl p-3 shadow-xs">
              <span className="text-[11px] font-semibold text-emerald-600 uppercase tracking-wider">Published</span>
              <p className="text-xl font-bold text-emerald-700 mt-1">{overviewStats?.published ?? 0}</p>
            </div>
            <div className="bg-white border border-slate-200 rounded-xl p-3 shadow-xs">
              <span className="text-[11px] font-semibold text-amber-600 uppercase tracking-wider">Scheduled</span>
              <p className="text-xl font-bold text-amber-700 mt-1">{overviewStats?.scheduled ?? 0}</p>
            </div>
            <div className="bg-white border border-slate-200 rounded-xl p-3 shadow-xs">
              <span className="text-[11px] font-semibold text-slate-600 uppercase tracking-wider">Drafts</span>
              <p className="text-xl font-bold text-slate-700 mt-1">{overviewStats?.draft ?? 0}</p>
            </div>
            <div className="bg-white border border-slate-200 rounded-xl p-3 shadow-xs">
              <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Archived</span>
              <p className="text-xl font-bold text-slate-500 mt-1">{overviewStats?.archived ?? 0}</p>
            </div>
            <div className="bg-white border border-rose-200 bg-rose-50/20 rounded-xl p-3 shadow-xs">
              <span className="text-[11px] font-semibold text-rose-600 uppercase tracking-wider">Emergencies</span>
              <p className="text-xl font-bold text-rose-700 mt-1">{overviewStats?.emergency ?? 0}</p>
            </div>
          </div>

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
                <option value="SCHEDULED">Scheduled</option>
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
                <option value="WATER">Water Supply</option>
                <option value="ELECTRICITY">Electricity</option>
                <option value="SECURITY">Security</option>
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
                            {n.target_type === 'TOWER' && (
                              <span>
                                {n.target_tower_names && n.target_tower_names.length > 0
                                  ? `${n.target_tower_names.length} Tower(s): ${n.target_tower_names.join(', ')}`
                                  : `Tower: ${n.target_tower_name || 'Specific Tower'}`}
                              </span>
                            )}
                            {n.target_type === 'FLAT' && (
                              <span>
                                {n.target_flat_numbers && n.target_flat_numbers.length > 0
                                  ? `${n.target_flat_numbers.length} Flat(s): ${n.target_flat_numbers.join(', ')}`
                                  : `Flat: ${n.target_flat_number || 'Specific Unit'}`}
                              </span>
                            )}
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
                              onClick={() => handlePublishNotice(n)}
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
                      })
                    }
                    className="w-full text-xs sm:text-sm px-3 py-2 rounded-lg border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="CIRCULAR">Federation Circular</option>
                    <option value="MAINTENANCE">Maintenance Advisory</option>
                    <option value="WATER">Water Supply Notice</option>
                    <option value="ELECTRICITY">Electricity Advisory</option>
                    <option value="SECURITY">Security Announcement</option>
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
                  <div className="pt-2 space-y-2">
                    <div className="flex items-center justify-between">
                      <label className="block text-xs font-semibold text-slate-700">
                        Target Towers *{' '}
                        <span className="font-normal text-slate-500">
                          ({formData.target_tower_ids.length} of {availableTowers.length} selected)
                        </span>
                      </label>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => {
                            const allIds = availableTowers.map((t) => t.id);
                            setFormData({
                              ...formData,
                              target_tower_ids: allIds,
                              target_tower_id: allIds[0] || '',
                            });
                          }}
                          className="text-[11px] font-semibold text-indigo-600 hover:text-indigo-800"
                        >
                          Select All ({availableTowers.length})
                        </button>
                        <span className="text-slate-300">|</span>
                        <button
                          type="button"
                          onClick={() =>
                            setFormData({
                              ...formData,
                              target_tower_ids: [],
                              target_tower_id: '',
                            })
                          }
                          className="text-[11px] font-semibold text-slate-500 hover:text-slate-700"
                        >
                          Clear
                        </button>
                      </div>
                    </div>

                    {loadingTargets && availableTowers.length === 0 ? (
                      <div className="text-center py-4 text-xs text-slate-400 flex items-center justify-center gap-2">
                        <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                        <span>Loading towers...</span>
                      </div>
                    ) : (
                      <div className="grid grid-cols-4 sm:grid-cols-7 gap-1.5 max-h-48 overflow-y-auto p-2 bg-white rounded-lg border border-slate-200">
                        {availableTowers.map((t) => {
                          const isSelected = formData.target_tower_ids.includes(t.id);
                          return (
                            <button
                              key={t.id}
                              type="button"
                              onClick={() => {
                                const newIds = isSelected
                                  ? formData.target_tower_ids.filter((id) => id !== t.id)
                                  : [...formData.target_tower_ids, t.id];
                                setFormData({
                                  ...formData,
                                  target_tower_ids: newIds,
                                  target_tower_id: newIds[0] || '',
                                });
                              }}
                              className={`py-1.5 px-2 text-xs font-semibold rounded-md border text-center transition-all ${
                                isSelected
                                  ? 'bg-indigo-600 text-white border-indigo-600 shadow-xs'
                                  : 'bg-slate-50 text-slate-700 border-slate-200 hover:bg-indigo-50 hover:border-indigo-300'
                              }`}
                              title={t.name}
                            >
                              {t.tower_number}
                            </button>
                          );
                        })}
                      </div>
                    )}
                    <span className="text-[10px] text-slate-400 block">
                      Click towers to toggle selection. Selected towers will receive this announcement.
                    </span>
                  </div>
                )}

                {formData.target_type === 'FLAT' && (
                  <div className="pt-2 space-y-2">
                    <div className="flex items-center justify-between">
                      <label className="block text-xs font-semibold text-slate-700">
                        Target Flats *{' '}
                        <span className="font-normal text-slate-500">
                          ({formData.target_flat_ids.length} selected)
                        </span>
                      </label>
                      {formData.target_flat_ids.length > 0 && (
                        <button
                          type="button"
                          onClick={() =>
                            setFormData({
                              ...formData,
                              target_flat_ids: [],
                              target_flat_id: '',
                            })
                          }
                          className="text-[11px] font-semibold text-slate-500 hover:text-slate-700"
                        >
                          Clear Selection
                        </button>
                      )}
                    </div>

                    {/* Selected Flat Chips */}
                    {formData.target_flat_ids.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 p-2 bg-indigo-50/60 border border-indigo-100 rounded-lg max-h-24 overflow-y-auto">
                        {formData.target_flat_ids.map((fid) => {
                          const flatObj = availableFlats.find((f) => f.id === fid);
                          const label = flatObj
                            ? `${flatObj.tower_number}-${flatObj.flat_number}`
                            : fid.slice(0, 8);
                          return (
                            <span
                              key={fid}
                              className="inline-flex items-center gap-1 bg-white border border-indigo-200 text-indigo-700 text-[11px] font-medium px-2 py-0.5 rounded-md shadow-2xs"
                            >
                              <span>{label}</span>
                              <button
                                type="button"
                                onClick={() => {
                                  const newIds = formData.target_flat_ids.filter((id) => id !== fid);
                                  setFormData({
                                    ...formData,
                                    target_flat_ids: newIds,
                                    target_flat_id: newIds[0] || '',
                                  });
                                }}
                                className="text-slate-400 hover:text-rose-600"
                              >
                                <X className="h-3 w-3" />
                              </button>
                            </span>
                          );
                        })}
                      </div>
                    )}

                    {/* Flat Search & Tower Filter */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                      <select
                        value={flatFilterTower}
                        onChange={(e) => setFlatFilterTower(e.target.value)}
                        className="text-xs px-2.5 py-1.5 rounded-lg border border-slate-300 bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
                      >
                        <option value="ALL">All Towers</option>
                        {availableTowers.map((t) => (
                          <option key={t.id} value={t.id}>
                            {t.tower_number} ({t.name})
                          </option>
                        ))}
                      </select>

                      <input
                        type="text"
                        placeholder="Search flat number (e.g. 1203)..."
                        value={flatSearchQuery}
                        onChange={(e) => setFlatSearchQuery(e.target.value)}
                        className="text-xs px-2.5 py-1.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                      />
                    </div>

                    {/* Flat Options Quick Selector */}
                    {availableFlats.length > 0 && (
                      <div className="grid grid-cols-3 sm:grid-cols-4 gap-1.5 max-h-36 overflow-y-auto p-2 bg-white rounded-lg border border-slate-200">
                        {availableFlats
                          .filter((f) => {
                            const matchTower =
                              flatFilterTower === 'ALL' || f.tower_id === flatFilterTower;
                            const matchSearch =
                              !flatSearchQuery.trim() ||
                              f.flat_number.toLowerCase().includes(flatSearchQuery.trim().toLowerCase());
                            return matchTower && matchSearch;
                          })
                          .slice(0, 60)
                          .map((f) => {
                            const isSelected = formData.target_flat_ids.includes(f.id);
                            return (
                              <button
                                key={f.id}
                                type="button"
                                onClick={() => {
                                  const newIds = isSelected
                                    ? formData.target_flat_ids.filter((id) => id !== f.id)
                                    : [...formData.target_flat_ids, f.id];
                                  setFormData({
                                    ...formData,
                                    target_flat_ids: newIds,
                                    target_flat_id: newIds[0] || '',
                                  });
                                }}
                                className={`py-1 px-2 text-[11px] font-medium rounded border truncate text-center transition-colors ${
                                  isSelected
                                    ? 'bg-indigo-600 text-white border-indigo-600 font-bold'
                                    : 'bg-slate-50 text-slate-700 border-slate-200 hover:bg-indigo-50'
                                }`}
                              >
                                {f.tower_number}-{f.flat_number}
                              </button>
                            );
                          })}
                      </div>
                    )}

                    {/* Manual Flat ID input for fallback */}
                    <div className="flex items-center gap-2 pt-1">
                      <input
                        type="text"
                        placeholder="Or enter flat UUID..."
                        value={manualFlatIdInput}
                        onChange={(e) => setManualFlatIdInput(e.target.value)}
                        className="flex-1 text-xs font-mono px-2.5 py-1.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                      />
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          const val = manualFlatIdInput.trim();
                          if (val && !formData.target_flat_ids.includes(val)) {
                            const newIds = [...formData.target_flat_ids, val];
                            setFormData({
                              ...formData,
                              target_flat_ids: newIds,
                              target_flat_id: newIds[0] || '',
                            });
                            setManualFlatIdInput('');
                          }
                        }}
                        className="text-xs"
                      >
                        Add Flat
                      </Button>
                    </div>
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
                      setFormData({
                        ...formData,
                        deliver_emergency: e.target.checked,
                        confirm_emergency_broadcast: e.target.checked ? formData.confirm_emergency_broadcast : false,
                      })
                    }
                    className="rounded border-slate-300 text-rose-600 focus:ring-rose-500 h-4 w-4"
                  />
                  <span className="text-xs font-semibold text-rose-900 flex items-center gap-1">
                    <Flame className="h-3.5 w-3.5 text-rose-600" /> Dispatch immediate emergency notification & outbox broadcast to all targeted residents
                  </span>
                </label>

                {formData.deliver_emergency && (
                  <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg space-y-2 mt-2">
                    <p className="text-xs text-rose-800 font-medium">
                      ⚠️ <strong>Emergency Confirmation Gate:</strong> This notice will trigger mandatory multi-channel broadcasts bypassing normal resident mute preferences. Please explicitly confirm this broadcast.
                    </p>
                    <label className="flex items-center gap-2 cursor-pointer select-none">
                      <input
                        type="checkbox"
                        checked={formData.confirm_emergency_broadcast}
                        onChange={(e) =>
                          setFormData({ ...formData, confirm_emergency_broadcast: e.target.checked })
                        }
                        className="rounded border-rose-400 text-rose-600 focus:ring-rose-500 h-4 w-4"
                      />
                      <span className="text-xs font-bold text-rose-900">
                        I confirm this is an authentic emergency broadcast authorized for immediate dispatch.
                      </span>
                    </label>
                  </div>
                )}
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

                {formData.published_at && new Date(formData.published_at).getTime() > Date.now() ? (
                  <Button
                    size="sm"
                    onClick={() => handleSaveNotice('SCHEDULED')}
                    disabled={composerSubmitting}
                    className="text-xs font-semibold gap-1 bg-amber-600 hover:bg-amber-700 text-white"
                  >
                    <Clock className="h-3.5 w-3.5" />
                    <span>{composerSubmitting ? 'Scheduling...' : 'Schedule Publication'}</span>
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    onClick={() => handleSaveNotice('PUBLISHED')}
                    disabled={composerSubmitting}
                    className="text-xs font-semibold gap-1"
                  >
                    <Send className="h-3.5 w-3.5" />
                    <span>{composerSubmitting ? 'Publishing...' : 'Publish Notice'}</span>
                  </Button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
