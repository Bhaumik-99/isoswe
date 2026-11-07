import React, { useState, useEffect, useCallback } from 'react';
import {
  Bell,
  CheckCircle2,
  AlertTriangle,
  Pin,
  Calendar,
  Building,
  RefreshCw,
  Clock,
  Filter,
  Check,
  Flame,
  FileText,
  Wrench,
  PartyPopper,
  Droplets,
  Zap,
  Shield,
  Eye,
  Globe,
  X,
} from 'lucide-react';
import { notificationService } from '../../../services/notificationService';
import { NoticeCategory, NoticeItem } from '../../../types';
import { Badge } from '../../../components/ui/Badge';
import { Button } from '../../../components/ui/Button';
import { Card, CardContent } from '../../../components/ui/Card';
import { Alert } from '../../../components/ui/Alert';
import { useLanguage, SupportedLanguage } from '../../../i18n/LanguageContext';

export const ResidentNoticesPage: React.FC = () => {
  const { t, language, setLanguage } = useLanguage();
  const [notices, setNotices] = useState<NoticeItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<NoticeCategory | 'ALL'>('ALL');
  const [unreadOnly, setUnreadOnly] = useState<boolean>(false);
  const [unreadCount, setUnreadCount] = useState<number>(0);
  const [markingAll, setMarkingAll] = useState<boolean>(false);
  const [detailModalNotice, setDetailModalNotice] = useState<NoticeItem | null>(null);

  const fetchNotices = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const categoryParam = selectedCategory === 'ALL' ? undefined : selectedCategory;
      const res = await notificationService.getResidentNotices(
        1,
        50,
        categoryParam,
        unreadOnly
      );
      setNotices(res.items);
      try {
        const countRes = await notificationService.getResidentNoticesUnreadCount();
        setUnreadCount(countRes.unread_count);
      } catch {
        setUnreadCount(res.unread_count || 0);
      }
    } catch {
      setError(t.errors.genericError || 'Failed to load official notices.');
    } finally {
      setLoading(false);
    }
  }, [selectedCategory, unreadOnly, t]);

  useEffect(() => {
    fetchNotices();
  }, [fetchNotices]);

  const handleMarkAsRead = async (noticeId: string) => {
    try {
      await notificationService.markNoticeAsRead(noticeId);
      setNotices((prev) =>
        prev.map((n) => (n.id === noticeId ? { ...n, is_read: true, read_at: new Date().toISOString() } : n))
      );
      if (detailModalNotice?.id === noticeId) {
        setDetailModalNotice((prev) =>
          prev ? { ...prev, is_read: true, read_at: new Date().toISOString() } : null
        );
      }
      setUnreadCount((c) => Math.max(0, c - 1));
    } catch {
      // Ignore
    }
  };

  const handleMarkAllAsRead = async () => {
    setMarkingAll(true);
    try {
      await notificationService.markAllNoticesAsRead();
      setNotices((prev) =>
        prev.map((n) => ({ ...n, is_read: true, read_at: new Date().toISOString() }))
      );
      setUnreadCount(0);
    } catch {
      // Ignore
    } finally {
      setMarkingAll(false);
    }
  };

  const handleOpenDetail = (notice: NoticeItem) => {
    setDetailModalNotice(notice);
    if (!notice.is_read) {
      handleMarkAsRead(notice.id);
    }
  };

  const getCategoryIcon = (category: NoticeCategory) => {
    switch (category) {
      case 'EMERGENCY':
        return <Flame className="h-3.5 w-3.5 text-rose-600" />;
      case 'CIRCULAR':
        return <FileText className="h-3.5 w-3.5 text-indigo-600" />;
      case 'MAINTENANCE':
        return <Wrench className="h-3.5 w-3.5 text-amber-600" />;
      case 'WATER':
        return <Droplets className="h-3.5 w-3.5 text-cyan-600" />;
      case 'ELECTRICITY':
        return <Zap className="h-3.5 w-3.5 text-yellow-600" />;
      case 'SECURITY':
        return <Shield className="h-3.5 w-3.5 text-purple-600" />;
      case 'EVENT':
        return <PartyPopper className="h-3.5 w-3.5 text-emerald-600" />;
      default:
        return <Bell className="h-3.5 w-3.5 text-slate-600" />;
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

  const getCategoryLabel = (category: NoticeCategory | 'ALL'): string => {
    switch (category) {
      case 'ALL':
        return t.notices.filters.all;
      case 'EMERGENCY':
        return t.notices.filters.emergency;
      case 'CIRCULAR':
        return t.notices.filters.circular;
      case 'MAINTENANCE':
        return t.notices.filters.maintenance;
      case 'WATER':
        return t.notices.filters.water;
      case 'ELECTRICITY':
        return t.notices.filters.electricity;
      case 'SECURITY':
        return t.notices.filters.security;
      case 'EVENT':
        return t.notices.filters.event;
      case 'GENERAL':
        return t.notices.filters.general;
      default:
        return category;
    }
  };

  const categoryOptions: (NoticeCategory | 'ALL')[] = [
    'ALL',
    'EMERGENCY',
    'CIRCULAR',
    'MAINTENANCE',
    'WATER',
    'ELECTRICITY',
    'SECURITY',
    'EVENT',
    'GENERAL',
  ];

  const emergencyNotices = notices.filter(
    (n) => (n.category === 'EMERGENCY' || n.priority === 'URGENT') && !n.is_read
  );

  return (
    <div className="space-y-6 max-w-5xl mx-auto pb-12">
      {/* Top Header Card */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center font-bold">
                <Bell className="h-5 w-5" />
              </div>
              <h1 className="text-xl font-bold text-slate-900 tracking-tight">
                {t.notices.title}
              </h1>
              {unreadCount > 0 && (
                <Badge variant="info" className="ml-2 font-semibold">
                  {unreadCount} {t.notices.unread.toLowerCase()}
                </Badge>
              )}
            </div>
            <p className="text-xs text-slate-500">
              {t.notices.subtitle}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* Language Switcher Pill */}
            <div className="flex items-center bg-slate-100 rounded-lg p-0.5 border border-slate-200 text-xs">
              <span className="px-2 text-slate-400 flex items-center gap-1 font-medium">
                <Globe className="h-3 w-3" />
              </span>
              {(['en', 'hi', 'mr'] as SupportedLanguage[]).map((lang) => (
                <button
                  key={lang}
                  onClick={() => setLanguage(lang)}
                  className={`px-2.5 py-1 rounded-md font-semibold transition-all ${
                    language === lang
                      ? 'bg-white text-indigo-600 shadow-xs'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  {lang.toUpperCase()}
                </button>
              ))}
            </div>

            <Button
              variant="outline"
              size="sm"
              onClick={handleMarkAllAsRead}
              disabled={unreadCount === 0 || markingAll}
              className="text-xs font-semibold gap-1.5"
            >
              <Check className="h-3.5 w-3.5" />
              <span>{markingAll ? '...' : t.notices.actions.markAllRead}</span>
            </Button>

            <Button
              variant="ghost"
              size="sm"
              onClick={fetchNotices}
              disabled={loading}
              className="text-xs font-semibold gap-1 text-slate-600"
              aria-label={t.notices.actions.refresh}
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        </div>

        {/* Filters Bar */}
        <div className="mt-6 pt-4 border-t border-slate-100 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mr-1 flex items-center gap-1">
              <Filter className="h-3 w-3" /> {t.notices.actions.filter}:
            </span>
            {categoryOptions.map((cat) => (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                className={`px-3 py-1 text-xs font-medium rounded-full transition-colors flex items-center gap-1 ${
                  selectedCategory === cat
                    ? 'bg-slate-900 text-white font-semibold shadow-xs'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {cat !== 'ALL' && getCategoryIcon(cat)}
                <span>{getCategoryLabel(cat)}</span>
              </button>
            ))}
          </div>

          <label className="flex items-center gap-2 text-xs font-medium text-slate-700 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={unreadOnly}
              onChange={(e) => setUnreadOnly(e.target.checked)}
              className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 h-4 w-4"
            />
            <span>{t.notices.filters.unread}</span>
          </label>
        </div>
      </div>

      {/* Emergency Alert Callout (If active unread emergency exists) */}
      {emergencyNotices.length > 0 && (
        <div className="space-y-3">
          {emergencyNotices.map((emg) => (
            <div
              key={emg.id}
              className="bg-rose-50 border-2 border-rose-300 rounded-xl p-4 shadow-sm text-rose-950 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 animate-pulse"
            >
              <div className="flex items-start gap-3">
                <div className="p-2 bg-rose-200 text-rose-800 rounded-lg shrink-0 mt-0.5">
                  <Flame className="h-5 w-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold uppercase tracking-wider px-2 py-0.5 bg-rose-200 text-rose-900 rounded">
                      {t.notices.emergencyAlerts}
                    </span>
                    <span className="text-xs text-rose-700">
                      {new Date(emg.published_at || emg.created_at).toLocaleString(language === 'en' ? 'en-IN' : language === 'hi' ? 'hi-IN' : 'mr-IN', {
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                  </div>
                  <h3 className="font-bold text-sm text-rose-950 mt-1">{emg.title}</h3>
                  <p className="text-xs text-rose-900 mt-0.5 line-clamp-2">{emg.body}</p>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleOpenDetail(emg)}
                  className="bg-white border-rose-200 text-rose-900 hover:bg-rose-100 text-xs font-semibold gap-1"
                >
                  <Eye className="h-3.5 w-3.5" />
                  <span>{t.notices.actions.viewDetails}</span>
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleMarkAsRead(emg.id)}
                  className="bg-rose-600 text-white hover:bg-rose-700 border-transparent text-xs font-semibold"
                >
                  {t.notices.actions.markRead}
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Error state */}
      {error && (
        <Alert variant="error">
          <AlertTriangle className="h-4 w-4" />
          <span>{error}</span>
        </Alert>
      )}

      {/* Loading Skeletons */}
      {loading && (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm animate-pulse space-y-3">
              <div className="h-4 bg-slate-200 rounded w-1/4"></div>
              <div className="h-5 bg-slate-200 rounded w-3/4"></div>
              <div className="h-12 bg-slate-100 rounded w-full"></div>
            </div>
          ))}
        </div>
      )}

      {/* Empty State */}
      {!loading && !error && notices.length === 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-12 text-center shadow-sm">
          <div className="w-12 h-12 rounded-full bg-slate-100 text-slate-400 mx-auto flex items-center justify-center mb-3">
            <CheckCircle2 className="h-6 w-6" />
          </div>
          <h3 className="text-sm font-semibold text-slate-900">{t.notices.emptyState}</h3>
          <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1">
            {unreadOnly
              ? t.notices.emptyDesc
              : t.notices.emptyDesc}
          </p>
        </div>
      )}

      {/* Notice Feed List */}
      {!loading && notices.length > 0 && (
        <div className="space-y-4">
          {notices.map((notice) => {
            const isPinned = notice.is_pinned;
            const isEmergency = notice.category === 'EMERGENCY' || notice.priority === 'URGENT';

            return (
              <Card
                key={notice.id}
                className={`transition-all ${
                  isPinned
                    ? 'border-amber-300 bg-amber-50/20 shadow-xs'
                    : notice.is_read
                    ? 'border-slate-200 bg-white'
                    : 'border-indigo-200 bg-indigo-50/10 shadow-xs'
                }`}
              >
                <CardContent className="p-5 sm:p-6 space-y-3">
                  {/* Notice Meta Top Row */}
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      {isPinned && (
                        <span className="flex items-center gap-1 text-[11px] font-bold text-amber-800 bg-amber-100 px-2 py-0.5 rounded-full border border-amber-200">
                          <Pin className="h-3 w-3 fill-amber-700" />
                          <span>{t.notices.pinnedNotices}</span>
                        </span>
                      )}

                      <Badge
                        variant={getCategoryBadgeVariant(notice.category)}
                        className="flex items-center gap-1 font-semibold text-[11px]"
                      >
                        {getCategoryIcon(notice.category)}
                        <span>{getCategoryLabel(notice.category)}</span>
                      </Badge>

                      {notice.priority === 'HIGH' && (
                        <Badge variant="warning" className="text-[11px]">
                          {t.notices.priorities.high}
                        </Badge>
                      )}
                      {notice.priority === 'URGENT' && (
                        <Badge variant="danger" className="text-[11px]">
                          {t.notices.priorities.urgent}
                        </Badge>
                      )}

                      {/* Targeting Scope */}
                      <span className="text-[11px] text-slate-500 flex items-center gap-1 font-medium bg-slate-100 px-2 py-0.5 rounded">
                        <Building className="h-3 w-3 text-slate-400" />
                        {notice.target_type === 'SOCIETY' && 'Society Wide'}
                        {notice.target_type === 'TOWER' &&
                          `Target: ${
                            notice.target_tower_names && notice.target_tower_names.length > 0
                              ? notice.target_tower_names.join(', ')
                              : notice.target_tower_name || 'Tower'
                          }`}
                        {notice.target_type === 'FLAT' &&
                          `Target: ${
                            notice.target_flat_numbers && notice.target_flat_numbers.length > 0
                              ? `Flats ${notice.target_flat_numbers.join(', ')}`
                              : `Unit ${notice.target_flat_number || 'Flat'}`
                          }`}
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleOpenDetail(notice)}
                        className="text-xs font-medium text-slate-600 hover:text-slate-900 h-7 px-2"
                      >
                        <Eye className="h-3.5 w-3.5 mr-1" />
                        {t.notices.actions.viewDetails}
                      </Button>

                      {!notice.is_read ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleMarkAsRead(notice.id)}
                          className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 hover:bg-indigo-50 h-7 px-2.5"
                        >
                          <Check className="h-3.5 w-3.5 mr-1" />
                          {t.notices.actions.markRead}
                        </Button>
                      ) : (
                        <span className="text-[11px] text-emerald-600 flex items-center gap-1 font-medium">
                          <CheckCircle2 className="h-3.5 w-3.5" />
                          {t.notices.read}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Title */}
                  <div>
                    <h2
                      onClick={() => handleOpenDetail(notice)}
                      className={`text-base font-bold cursor-pointer hover:underline ${
                        isEmergency ? 'text-rose-950' : 'text-slate-900'
                      }`}
                    >
                      {notice.title}
                    </h2>
                  </div>

                  {/* Body Text */}
                  <div className="text-xs sm:text-sm text-slate-700 whitespace-pre-line leading-relaxed">
                    {notice.body}
                  </div>

                  {/* Notice Footer: Dates & Expiry */}
                  <div className="pt-2 border-t border-slate-100 flex flex-wrap items-center justify-between text-[11px] text-slate-400 gap-2">
                    <div className="flex items-center gap-3">
                      <span className="flex items-center gap-1">
                        <Calendar className="h-3 w-3" />
                        {new Date(notice.published_at || notice.created_at).toLocaleString(language === 'en' ? 'en-IN' : language === 'hi' ? 'hi-IN' : 'mr-IN', {
                          month: 'short',
                          day: 'numeric',
                          year: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </span>

                      {notice.author_name && (
                        <span>By: {notice.author_name}</span>
                      )}
                    </div>

                    {notice.expires_at && (
                      <span className="flex items-center gap-1 text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
                        <Clock className="h-3 w-3" />
                        {new Date(notice.expires_at).toLocaleDateString(language === 'en' ? 'en-IN' : language === 'hi' ? 'hi-IN' : 'mr-IN', {
                          month: 'short',
                          day: 'numeric',
                          year: 'numeric',
                        })}
                      </span>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Full Detail Modal */}
      {detailModalNotice && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs">
          <div className="bg-white rounded-2xl max-w-2xl w-full p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-start justify-between gap-4 border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <Badge variant={getCategoryBadgeVariant(detailModalNotice.category)}>
                  {getCategoryLabel(detailModalNotice.category)}
                </Badge>
                {detailModalNotice.is_pinned && (
                  <Badge variant="warning">{t.notices.pinnedNotices}</Badge>
                )}
                {detailModalNotice.is_read && (
                  <Badge variant="success" className="text-[10px]">{t.notices.readReceipt}</Badge>
                )}
              </div>
              <button
                onClick={() => setDetailModalNotice(null)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div>
              <h2 className="text-lg font-bold text-slate-900">{detailModalNotice.title}</h2>
              <p className="text-xs text-slate-400 mt-1 flex items-center gap-2">
                <span>
                  {new Date(detailModalNotice.published_at || detailModalNotice.created_at).toLocaleString()}
                </span>
                {detailModalNotice.author_name && (
                  <span>• Author: {detailModalNotice.author_name}</span>
                )}
                {detailModalNotice.version && detailModalNotice.version > 1 && (
                  <span>• v{detailModalNotice.version}</span>
                )}
              </p>
            </div>

            <div className="text-sm text-slate-700 whitespace-pre-line leading-relaxed bg-slate-50 p-4 rounded-xl border border-slate-200">
              {detailModalNotice.body}
            </div>

            {detailModalNotice.expires_at && (
              <p className="text-xs text-amber-700 bg-amber-50 p-2.5 rounded-lg border border-amber-200 flex items-center gap-2">
                <Clock className="h-4 w-4" />
                <span>Expires on: {new Date(detailModalNotice.expires_at).toLocaleString()}</span>
              </p>
            )}

            <div className="flex justify-end pt-2">
              <Button onClick={() => setDetailModalNotice(null)} variant="primary" size="sm">
                Close
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
