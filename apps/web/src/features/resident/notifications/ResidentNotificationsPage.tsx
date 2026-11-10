import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Bell,
  CheckCheck,
  CreditCard,
  LifeBuoy,
  UserCheck,
  Search,
  SlidersHorizontal,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  CheckCircle2,
  X,
  Loader2,
  ShieldAlert,
} from 'lucide-react';
import { notificationService } from '../../../services/notificationService';
import {
  NotificationPreferences,
  NotificationPriority,
  PaginatedNotifications,
} from '../../../types';
import { Badge } from '../../../components/ui/Badge';
import { Button } from '../../../components/ui/Button';
import { Portal } from '../../../components/ui/Portal';

export const ResidentNotificationsPage: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<PaginatedNotifications>({
    items: [],
    total: 0,
    page: 1,
    page_size: 15,
    total_pages: 1,
    unread_count: 0,
  });

  const [activeTab, setActiveTab] = useState<'ALL' | 'UNREAD' | 'BILLING' | 'COMPLAINTS' | 'VISITORS'>('ALL');
  const [searchTerm, setSearchTerm] = useState('');
  const [page, setPage] = useState(1);
  const [preferencesModalOpen, setPreferencesModalOpen] = useState(false);
  const [preferences, setPreferences] = useState<NotificationPreferences | null>(null);
  const [savingPreferences, setSavingPreferences] = useState(false);
  const [preferencesFeedback, setPreferencesFeedback] = useState<string | null>(null);

  const loadNotifications = useCallback(async () => {
    setLoading(true);
    try {
      const res = await notificationService.getMyNotifications(
        page,
        15,
        activeTab === 'UNREAD'
      );
      setData(res);
    } catch {
      // Ignore
    } finally {
      setLoading(false);
    }
  }, [page, activeTab]);

  useEffect(() => {
    loadNotifications();
  }, [loadNotifications]);

  useEffect(() => {
    const handleFocus = () => {
      void loadNotifications();
    };
    window.addEventListener('focus', handleFocus);
    return () => window.removeEventListener('focus', handleFocus);
  }, [loadNotifications]);

  const handleMarkAllRead = async () => {
    try {
      await notificationService.markAllAsRead();
      loadNotifications();
    } catch {
      // Ignore
    }
  };

  const handleMarkSingleRead = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await notificationService.markAsRead(id);
      setData((prev) => ({
        ...prev,
        unread_count: Math.max(0, prev.unread_count - 1),
        items: prev.items.map((n) =>
          n.id === id ? { ...n, read_at: new Date().toISOString() } : n
        ),
      }));
    } catch {
      // Ignore
    }
  };

  const openPreferences = async () => {
    setPreferencesModalOpen(true);
    setPreferencesFeedback(null);
    try {
      const pref = await notificationService.getPreferences();
      setPreferences(pref);
    } catch {
      // Ignore
    }
  };

  const savePreferences = async () => {
    if (!preferences) return;
    setSavingPreferences(true);
    try {
      const updated = await notificationService.updatePreferences({
        email_enabled: preferences.email_enabled,
        sms_enabled: preferences.sms_enabled,
        in_app_enabled: preferences.in_app_enabled,
        billing_email: preferences.billing_email,
        billing_sms: preferences.billing_sms,
        complaints_email: preferences.complaints_email,
        complaints_sms: preferences.complaints_sms,
        visitor_sms: preferences.visitor_sms,
      });
      setPreferences(updated);
      setPreferencesFeedback('Preferences updated successfully.');
      setTimeout(() => setPreferencesModalOpen(false), 1200);
    } catch {
      setPreferencesFeedback('Failed to update preferences. Please retry.');
    } finally {
      setSavingPreferences(false);
    }
  };

  const filteredItems = data.items.filter((item) => {
    // Filter by tab
    if (activeTab === 'BILLING' && !item.event_type.startsWith('billing.') && !item.event_type.startsWith('payment.')) {
      return false;
    }
    if (activeTab === 'COMPLAINTS' && !item.event_type.startsWith('complaint.')) {
      return false;
    }
    if (activeTab === 'VISITORS' && !item.event_type.startsWith('visitor.') && !item.event_type.startsWith('pass.')) {
      return false;
    }

    // Filter by search
    if (searchTerm.trim()) {
      const q = searchTerm.toLowerCase();
      return (
        item.title.toLowerCase().includes(q) ||
        item.body.toLowerCase().includes(q) ||
        item.event_type.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const getCategoryIcon = (eventType: string) => {
    if (eventType.startsWith('billing.') || eventType.startsWith('payment.')) {
      return <CreditCard className="h-4 w-4 text-emerald-600" />;
    }
    if (eventType.startsWith('complaint.')) {
      return <LifeBuoy className="h-4 w-4 text-indigo-600" />;
    }
    if (eventType.startsWith('visitor.') || eventType.startsWith('pass.')) {
      return <UserCheck className="h-4 w-4 text-blue-600" />;
    }
    return <Bell className="h-4 w-4 text-slate-500" />;
  };

  const getPriorityBadge = (priority: NotificationPriority) => {
    switch (priority) {
      case 'URGENT':
        return <Badge variant="danger">URGENT</Badge>;
      case 'HIGH':
        return <Badge variant="warning">HIGH</Badge>;
      case 'NORMAL':
        return <Badge variant="info">NORMAL</Badge>;
      case 'LOW':
        return <Badge variant="neutral">LOW</Badge>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header Card */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-bold text-slate-900">Notifications Inbox</h1>
            {data.unread_count > 0 && (
              <span className="px-2.5 py-0.5 text-xs font-bold bg-indigo-600 text-white rounded-full">
                {data.unread_count} Unread
              </span>
            )}
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Real-time multi-channel updates for maintenance billing, gate visitors, and facility helpdesk tickets.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {data.unread_count > 0 && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleMarkAllRead}
              className="flex items-center gap-1.5"
            >
              <CheckCheck className="h-4 w-4 text-slate-600" />
              <span>Mark all read</span>
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={openPreferences}
            className="flex items-center gap-1.5"
          >
            <SlidersHorizontal className="h-4 w-4 text-slate-600" />
            <span>Preferences</span>
          </Button>
        </div>
      </div>

      {/* Filter Tabs & Search Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-white p-3 rounded-xl border border-slate-200 shadow-sm">
        <div className="flex flex-wrap items-center gap-1">
          {[
            { id: 'ALL', label: 'All Updates' },
            { id: 'UNREAD', label: `Unread (${data.unread_count})` },
            { id: 'BILLING', label: 'Billing & Invoices' },
            { id: 'COMPLAINTS', label: 'Helpdesk & Safety' },
            { id: 'VISITORS', label: 'Visitors & Passes' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => {
                setActiveTab(tab.id as typeof activeTab);
                setPage(1);
              }}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                activeTab === tab.id
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="relative w-full sm:w-64">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search updates..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:bg-white"
          />
        </div>
      </div>

      {/* Notifications List */}
      <div className="space-y-3">
        {loading ? (
          <div className="bg-white rounded-xl border border-slate-200 p-12 text-center text-slate-500">
            <Loader2 className="h-8 w-8 animate-spin mx-auto text-indigo-600 mb-2" />
            <span className="text-sm">Fetching notifications...</span>
          </div>
        ) : filteredItems.length === 0 ? (
          <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
            <Bell className="h-10 w-10 mx-auto text-slate-300 mb-3 stroke-1" />
            <h3 className="text-base font-semibold text-slate-800">No notifications found</h3>
            <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1">
              {activeTab === 'UNREAD'
                ? 'All caught up! There are no unread notifications.'
                : 'No notification records match the current filter criteria.'}
            </p>
          </div>
        ) : (
          filteredItems.map((n) => (
            <div
              key={n.id}
              onClick={() => {
                if (n.action_url) navigate(n.action_url);
              }}
              className={`p-4 rounded-xl border transition-all cursor-pointer bg-white ${
                !n.read_at
                  ? 'border-indigo-200 bg-indigo-50/20 shadow-sm'
                  : 'border-slate-200 hover:border-slate-300'
              }`}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-start gap-3">
                  <div className="p-2 rounded-lg bg-slate-100 border border-slate-200 shrink-0 mt-0.5">
                    {getCategoryIcon(n.event_type)}
                  </div>
                  <div className="space-y-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h4
                        className={`text-sm ${
                          !n.read_at ? 'font-bold text-slate-900' : 'font-medium text-slate-800'
                        }`}
                      >
                        {n.title}
                      </h4>
                      {getPriorityBadge(n.priority)}
                      {!n.read_at && (
                        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-indigo-100 text-indigo-800">
                          New
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-600 leading-relaxed">{n.body}</p>
                    <div className="flex items-center gap-3 text-[11px] text-slate-400 pt-1">
                      <span>{new Date(n.created_at).toLocaleString()}</span>
                      <span>•</span>
                      <span className="font-mono text-[10px]">{n.event_type}</span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  {!n.read_at && (
                    <button
                      onClick={(e) => handleMarkSingleRead(n.id, e)}
                      className="p-1.5 text-slate-400 hover:text-indigo-600 rounded-lg hover:bg-slate-100 transition-colors"
                      title="Mark as read"
                    >
                      <CheckCircle2 className="h-4 w-4" />
                    </button>
                  )}
                  {n.action_url && (
                    <span className="p-1.5 text-slate-400 hover:text-slate-700">
                      <ExternalLink className="h-4 w-4" />
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Pagination Controls */}
      {data.total_pages > 1 && (
        <div className="flex items-center justify-between bg-white px-4 py-3 rounded-xl border border-slate-200">
          <span className="text-xs text-slate-500">
            Showing page {data.page} of {data.total_pages} ({data.total} total items)
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="flex items-center gap-1"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
              <span>Previous</span>
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= data.total_pages}
              onClick={() => setPage((p) => p + 1)}
              className="flex items-center gap-1"
            >
              <span>Next</span>
              <ChevronRight className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      )}

      {/* Notification Preferences Modal */}
      {preferencesModalOpen && (
        <Portal>
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-2xl border border-slate-200">
            <div className="flex items-center justify-between pb-4 border-b border-slate-200">
              <div className="flex items-center gap-2.5">
                <SlidersHorizontal className="h-5 w-5 text-indigo-600" />
                <h3 className="text-base font-bold text-slate-900">Notification Preferences</h3>
              </div>
              <button
                onClick={() => setPreferencesModalOpen(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {preferences ? (
              <div className="py-4 space-y-5">
                {/* Notice on Emergency Overrides */}
                <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl flex items-start gap-2.5">
                  <ShieldAlert className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
                  <p className="text-xs text-amber-800 leading-snug">
                    <span className="font-semibold">Security Notice:</span> Mandatory emergency alerts (such as critical elevator hazards, fire alarms, and safety escalations) always deliver across all active channels regardless of channel opt-outs.
                  </p>
                </div>

                <div className="space-y-4 divide-y divide-slate-100">
                  {/* Master Channels */}
                  <div className="space-y-3">
                    <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                      Master Communication Channels
                    </h4>
                    <div className="grid grid-cols-2 gap-3">
                      <label className="flex items-center justify-between p-3 border border-slate-200 rounded-lg cursor-pointer hover:bg-slate-50">
                        <span className="text-xs font-semibold text-slate-700">Email Alerts</span>
                        <input
                          type="checkbox"
                          checked={preferences.email_enabled}
                          onChange={(e) =>
                            setPreferences({ ...preferences, email_enabled: e.target.checked })
                          }
                          className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                        />
                      </label>
                      <label className="flex items-center justify-between p-3 border border-slate-200 rounded-lg cursor-pointer hover:bg-slate-50">
                        <span className="text-xs font-semibold text-slate-700">SMS Alerts</span>
                        <input
                          type="checkbox"
                          checked={preferences.sms_enabled}
                          onChange={(e) =>
                            setPreferences({ ...preferences, sms_enabled: e.target.checked })
                          }
                          className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                        />
                      </label>
                    </div>
                  </div>

                  {/* Domain Category Toggles */}
                  <div className="pt-4 space-y-3">
                    <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                      Topic Specific Settings
                    </h4>
                    <div className="space-y-2">
                      <label className="flex items-center justify-between p-2.5 rounded-lg hover:bg-slate-50 cursor-pointer">
                        <div>
                          <p className="text-xs font-semibold text-slate-800">Billing & Invoices via Email</p>
                          <p className="text-[11px] text-slate-500">Receive monthly invoices and receipts</p>
                        </div>
                        <input
                          type="checkbox"
                          checked={preferences.billing_email}
                          onChange={(e) =>
                            setPreferences({ ...preferences, billing_email: e.target.checked })
                          }
                          className="h-4 w-4 rounded border-slate-300 text-indigo-600"
                        />
                      </label>

                      <label className="flex items-center justify-between p-2.5 rounded-lg hover:bg-slate-50 cursor-pointer">
                        <div>
                          <p className="text-xs font-semibold text-slate-800">Complaint Updates via Email</p>
                          <p className="text-[11px] text-slate-500">Status transitions and resolution notices</p>
                        </div>
                        <input
                          type="checkbox"
                          checked={preferences.complaints_email}
                          onChange={(e) =>
                            setPreferences({ ...preferences, complaints_email: e.target.checked })
                          }
                          className="h-4 w-4 rounded border-slate-300 text-indigo-600"
                        />
                      </label>

                      <label className="flex items-center justify-between p-2.5 rounded-lg hover:bg-slate-50 cursor-pointer">
                        <div>
                          <p className="text-xs font-semibold text-slate-800">Gate Visitor SMS Notifications</p>
                          <p className="text-[11px] text-slate-500">Urgent approval requests at perimeter gate</p>
                        </div>
                        <input
                          type="checkbox"
                          checked={preferences.visitor_sms}
                          onChange={(e) =>
                            setPreferences({ ...preferences, visitor_sms: e.target.checked })
                          }
                          className="h-4 w-4 rounded border-slate-300 text-indigo-600"
                        />
                      </label>
                    </div>
                  </div>
                </div>

                {preferencesFeedback && (
                  <p className="text-xs text-center font-medium text-emerald-600">
                    {preferencesFeedback}
                  </p>
                )}
              </div>
            ) : (
              <div className="py-8 text-center">
                <Loader2 className="h-6 w-6 animate-spin mx-auto text-indigo-600" />
              </div>
            )}

            <div className="flex items-center justify-end gap-2 pt-4 border-t border-slate-200">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPreferencesModalOpen(false)}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                disabled={savingPreferences || !preferences}
                onClick={savePreferences}
              >
                {savingPreferences ? 'Saving...' : 'Save Preferences'}
              </Button>
            </div>
          </div>
          </div>
        </Portal>
      )}
    </div>
  );
};
