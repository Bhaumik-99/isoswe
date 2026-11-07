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
} from 'lucide-react';
import { notificationService } from '../../../services/notificationService';
import { NoticeCategory, NoticeItem } from '../../../types';
import { Badge } from '../../../components/ui/Badge';
import { Button } from '../../../components/ui/Button';
import { Card, CardContent } from '../../../components/ui/Card';
import { Alert } from '../../../components/ui/Alert';

export const ResidentNoticesPage: React.FC = () => {
  const [notices, setNotices] = useState<NoticeItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<NoticeCategory | 'ALL'>('ALL');
  const [unreadOnly, setUnreadOnly] = useState<boolean>(false);
  const [unreadCount, setUnreadCount] = useState<number>(0);
  const [markingAll, setMarkingAll] = useState<boolean>(false);

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
      setUnreadCount(res.unread_count || 0);
    } catch {
      setError('Failed to load official notices. Please check your network and retry.');
    } finally {
      setLoading(false);
    }
  }, [selectedCategory, unreadOnly]);

  useEffect(() => {
    fetchNotices();
  }, [fetchNotices]);

  const handleMarkAsRead = async (noticeId: string) => {
    try {
      await notificationService.markNoticeAsRead(noticeId);
      setNotices((prev) =>
        prev.map((n) => (n.id === noticeId ? { ...n, is_read: true, read_at: new Date().toISOString() } : n))
      );
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

  const getCategoryIcon = (category: NoticeCategory) => {
    switch (category) {
      case 'EMERGENCY':
        return <Flame className="h-3.5 w-3.5 text-rose-600" />;
      case 'CIRCULAR':
        return <FileText className="h-3.5 w-3.5 text-indigo-600" />;
      case 'MAINTENANCE':
        return <Wrench className="h-3.5 w-3.5 text-amber-600" />;
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
      case 'EVENT':
        return 'success';
      default:
        return 'neutral';
    }
  };

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
                Official Township Notices
              </h1>
              {unreadCount > 0 && (
                <Badge variant="info" className="ml-2 font-semibold">
                  {unreadCount} unread
                </Badge>
              )}
            </div>
            <p className="text-xs text-slate-500">
              Federation circulars, water/power maintenance advisories, community updates, and emergency alerts.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleMarkAllAsRead}
              disabled={unreadCount === 0 || markingAll}
              className="text-xs font-semibold gap-1.5"
            >
              <Check className="h-3.5 w-3.5" />
              <span>{markingAll ? 'Marking...' : 'Mark all as read'}</span>
            </Button>

            <Button
              variant="ghost"
              size="sm"
              onClick={fetchNotices}
              disabled={loading}
              className="text-xs font-semibold gap-1 text-slate-600"
              aria-label="Refresh notices"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        </div>

        {/* Filters Bar */}
        <div className="mt-6 pt-4 border-t border-slate-100 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mr-1 flex items-center gap-1">
              <Filter className="h-3 w-3" /> Filter:
            </span>
            {(['ALL', 'EMERGENCY', 'CIRCULAR', 'MAINTENANCE', 'EVENT', 'GENERAL'] as const).map((cat) => (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                className={`px-3 py-1 text-xs font-medium rounded-full transition-colors ${
                  selectedCategory === cat
                    ? 'bg-slate-900 text-white font-semibold shadow-xs'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {cat === 'ALL' ? 'All Notices' : cat.charAt(0) + cat.slice(1).toLowerCase()}
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
            <span>Unread only</span>
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
                      EMERGENCY ADVISORY
                    </span>
                    <span className="text-xs text-rose-700">
                      {new Date(emg.published_at || emg.created_at).toLocaleString('en-IN', {
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
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleMarkAsRead(emg.id)}
                className="shrink-0 bg-white border-rose-300 text-rose-900 hover:bg-rose-100 text-xs font-semibold"
              >
                Acknowledge
              </Button>
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
          <h3 className="text-sm font-semibold text-slate-900">No notices found</h3>
          <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1">
            {unreadOnly
              ? 'You have read all official notices in this category.'
              : 'There are currently no active official notices published for your flat.'}
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
                          <span>Pinned</span>
                        </span>
                      )}

                      <Badge
                        variant={getCategoryBadgeVariant(notice.category)}
                        className="flex items-center gap-1 font-semibold text-[11px]"
                      >
                        {getCategoryIcon(notice.category)}
                        <span>{notice.category}</span>
                      </Badge>

                      {notice.priority === 'HIGH' && (
                        <Badge variant="warning" className="text-[11px]">
                          HIGH PRIORITY
                        </Badge>
                      )}
                      {notice.priority === 'URGENT' && (
                        <Badge variant="danger" className="text-[11px]">
                          URGENT
                        </Badge>
                      )}

                      {/* Targeting Scope */}
                      <span className="text-[11px] text-slate-500 flex items-center gap-1 font-medium bg-slate-100 px-2 py-0.5 rounded">
                        <Building className="h-3 w-3 text-slate-400" />
                        {notice.target_type === 'SOCIETY' && 'Society Wide'}
                        {notice.target_type === 'TOWER' &&
                          `Target: ${notice.target_tower_name || 'Tower'}`}
                        {notice.target_type === 'FLAT' &&
                          `Target: Unit ${notice.target_flat_number || 'Flat'}`}
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      {!notice.is_read ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleMarkAsRead(notice.id)}
                          className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 hover:bg-indigo-50 h-7 px-2.5"
                        >
                          <Check className="h-3.5 w-3.5 mr-1" />
                          Mark as read
                        </Button>
                      ) : (
                        <span className="text-[11px] text-emerald-600 flex items-center gap-1 font-medium">
                          <CheckCircle2 className="h-3.5 w-3.5" />
                          Read
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Title */}
                  <div>
                    <h2
                      className={`text-base font-bold ${
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
                        Published:{' '}
                        {new Date(notice.published_at || notice.created_at).toLocaleString('en-IN', {
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
                        Valid until:{' '}
                        {new Date(notice.expires_at).toLocaleDateString('en-IN', {
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
    </div>
  );
};
