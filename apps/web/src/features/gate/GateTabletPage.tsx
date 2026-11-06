import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  UserPlus,
  KeyRound,
  CheckCircle2,
  LogOut,
  History,
  Users,
  Clock,
  Database,
} from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import {
  GateFlatOption,
  GateInfo,
  OfflineVisitorQueueItem,
  VisitorRecord,
} from '../../types';
import { gateService } from '../../services/gateService';
import {
  listOfflineQueue,
  removeSyncedOfflineItems,
} from './offline/gateIndexedDB';
import { gateSyncManager } from './offline/syncManager';
import { useLanguage } from '../../i18n/LanguageContext';
import { GateHeaderBanner } from './components/GateHeaderBanner';
import { GatePrivacyNoticeModal } from './components/GatePrivacyNoticeModal';
import { VisitorRegistrationForm } from './components/VisitorRegistrationForm';
import { GuestPassVerifier } from './components/GuestPassVerifier';
import { LiveApprovalMonitor } from './components/LiveApprovalMonitor';
import { CampusExitManager } from './components/CampusExitManager';
import { ScopedVisitorHistory } from './components/ScopedVisitorHistory';
import { OfflineQueueDrawer } from './components/OfflineQueueDrawer';

type GateTab = 'register' | 'passVerify' | 'liveMonitor' | 'campusExit' | 'history';

export const GateTabletPage: React.FC = () => {
  const { user, logout } = useAuth();
  const { t } = useLanguage();
  const navigate = useNavigate();

  const [activeTab, setActiveTab] = useState<GateTab>('register');
  const [isOnline, setIsOnline] = useState<boolean>(
    typeof navigator !== 'undefined' ? navigator.onLine : true
  );

  const [activeGate, setActiveGate] = useState<GateInfo | null>(null);
  const [availableGates, setAvailableGates] = useState<GateInfo[]>([]);
  const [flats, setFlats] = useState<GateFlatOption[]>([]);
  const [visitors, setVisitors] = useState<VisitorRecord[]>([]);
  const [historySearch, setHistorySearch] = useState('');
  const [isLoadingData, setIsLoadingData] = useState(false);

  const [offlineQueue, setOfflineQueue] = useState<OfflineVisitorQueueItem[]>([]);
  const [isSyncingQueue, setIsSyncingQueue] = useState(false);
  const [privacyModalOpen, setPrivacyModalOpen] = useState(false);
  const [offlineDrawerOpen, setOfflineDrawerOpen] = useState(false);

  const refreshOfflineQueue = useCallback(async (gateId?: string) => {
    const items = await listOfflineQueue(gateId);
    setOfflineQueue(items);
  }, []);

  const fetchGateData = useCallback(
    async (selectedGateId?: string, search?: string) => {
      setIsLoadingData(true);
      try {
        const [sessionRes, flatsList, visitorsList] = await Promise.all([
          gateService.getSession(),
          gateService.listFlats(),
          gateService.listVisitors({
            gate_id: selectedGateId,
            search: search || undefined,
            limit: 50,
          }),
        ]);
        setAvailableGates(sessionRes.available_gates || []);
        if (!activeGate && sessionRes.assigned_gate) {
          setActiveGate(sessionRes.assigned_gate);
        }
        setFlats(flatsList);
        setVisitors(visitorsList);
      } catch {
        // When offline, still load cached flats
        try {
          const cachedFlats = await gateService.listFlats();
          setFlats(cachedFlats);
        } catch {
          // Ignore if no cache yet
        }
      } finally {
        setIsLoadingData(false);
      }
    },
    [activeGate]
  );

  useEffect(() => {
    void fetchGateData(activeGate?.gate_id, historySearch);
    void refreshOfflineQueue(activeGate?.gate_id);
  }, [fetchGateData, refreshOfflineQueue, activeGate?.gate_id, historySearch]);

  // Listen for browser online / offline transitions and auto-sync queued events on reconnect
  useEffect(() => {
    const handleOnline = async () => {
      setIsOnline(true);
      if (activeGate?.gate_id) {
        setIsSyncingQueue(true);
        try {
          await gateSyncManager.syncGateQueue(activeGate.gate_id, false);
          await refreshOfflineQueue(activeGate.gate_id);
          await fetchGateData(activeGate.gate_id, historySearch);
        } finally {
          setIsSyncingQueue(false);
        }
      }
    };

    const handleOffline = () => {
      setIsOnline(false);
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, [activeGate?.gate_id, fetchGateData, historySearch, refreshOfflineQueue]);

  const handleSyncNow = async (includeFailed = false) => {
    if (!activeGate?.gate_id) return;
    setIsSyncingQueue(true);
    try {
      await gateSyncManager.syncGateQueue(activeGate.gate_id, includeFailed);
      await refreshOfflineQueue(activeGate.gate_id);
      await fetchGateData(activeGate.gate_id, historySearch);
    } finally {
      setIsSyncingQueue(false);
    }
  };

  const handleClearSynced = async () => {
    await removeSyncedOfflineItems(activeGate?.gate_id);
    await refreshOfflineQueue(activeGate?.gate_id);
  };

  const pendingCount = visitors.filter((v) => v.approval_status === 'PENDING').length;
  const insideCount = visitors.filter((v) => v.entry_status === 'CHECKED_IN').length;
  const checkedOutCount = visitors.filter((v) => v.entry_status === 'CHECKED_OUT').length;
  const unsyncedOfflineCount = offlineQueue.filter((q) => q.sync_status !== 'SYNCED').length;

  return (
    <div className="min-h-screen bg-slate-950 text-white flex flex-col">
      <GateHeaderBanner
        guardName={user?.full_name || 'Gate Security'}
        activeGate={activeGate}
        availableGates={availableGates}
        onSelectGate={(gate) => setActiveGate(gate)}
        isOnline={isOnline}
        offlineQueueCount={unsyncedOfflineCount}
        onOpenPrivacyNotice={() => setPrivacyModalOpen(true)}
        onOpenOfflineDrawer={() => setOfflineDrawerOpen(true)}
        onBackToStaff={() => navigate('/staff/overview')}
        onLogout={() => {
          logout();
          navigate('/login');
        }}
      />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 w-full flex-1 space-y-6">
        {/* KPI Strip */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4">
          <div className="p-4 rounded-2xl bg-slate-900 border border-slate-800 flex items-center justify-between">
            <div>
              <span className="text-xs text-slate-400 font-semibold block">
                {t.gate.kpiTodayVisitors}
              </span>
              <span className="text-2xl font-extrabold text-white">{visitors.length}</span>
            </div>
            <Users className="h-7 w-7 text-indigo-400" />
          </div>

          <div className="p-4 rounded-2xl bg-slate-900 border border-slate-800 flex items-center justify-between">
            <div>
              <span className="text-xs text-slate-400 font-semibold block">
                {t.gate.kpiPendingApprovals}
              </span>
              <span className="text-2xl font-extrabold text-amber-400">{pendingCount}</span>
            </div>
            <Clock className="h-7 w-7 text-amber-400" />
          </div>

          <div className="p-4 rounded-2xl bg-slate-900 border border-slate-800 flex items-center justify-between">
            <div>
              <span className="text-xs text-slate-400 font-semibold block">
                {t.gate.kpiCurrentlyInside}
              </span>
              <span className="text-2xl font-extrabold text-emerald-400">{insideCount}</span>
            </div>
            <CheckCircle2 className="h-7 w-7 text-emerald-400" />
          </div>

          <div className="p-4 rounded-2xl bg-slate-900 border border-slate-800 flex items-center justify-between">
            <div>
              <span className="text-xs text-slate-400 font-semibold block">
                {t.gate.kpiCheckedOutToday}
              </span>
              <span className="text-2xl font-extrabold text-slate-300">{checkedOutCount}</span>
            </div>
            <Database className="h-7 w-7 text-slate-400" />
          </div>
        </div>

        {/* High-Contrast Tablet Navigation Tabs */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 bg-slate-900 p-2 rounded-2xl border border-slate-800">
          {(
            [
              { id: 'register', label: t.gate.tabs.register, icon: UserPlus },
              { id: 'passVerify', label: t.gate.tabs.passVerify, icon: KeyRound },
              {
                id: 'liveMonitor',
                label: `${t.gate.tabs.liveMonitor} (${pendingCount})`,
                icon: CheckCircle2,
              },
              {
                id: 'campusExit',
                label: `${t.gate.tabs.campusExit} (${insideCount})`,
                icon: LogOut,
              },
              { id: 'history', label: t.gate.tabs.history, icon: History },
            ] as const
          ).map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`py-3 px-3 rounded-xl font-bold text-xs sm:text-sm flex items-center justify-center gap-2 transition-all ${
                  isActive
                    ? 'bg-amber-500 text-slate-950 shadow-md'
                    : 'text-slate-300 hover:text-white hover:bg-slate-800'
                }`}
              >
                <Icon className="h-4 w-4 flex-shrink-0" />
                <span className="truncate">{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Active Tab View */}
        {activeTab === 'register' && (
          <VisitorRegistrationForm
            activeGate={activeGate}
            flats={flats}
            isOnline={isOnline}
            onRegisteredOnline={() => void fetchGateData(activeGate?.gate_id, historySearch)}
            onRegisteredOffline={() => void refreshOfflineQueue(activeGate?.gate_id)}
            onOpenPrivacyModal={() => setPrivacyModalOpen(true)}
          />
        )}

        {activeTab === 'passVerify' && (
          <GuestPassVerifier
            activeGate={activeGate}
            isOnline={isOnline}
            onPassVerifiedAndCheckedIn={() =>
              void fetchGateData(activeGate?.gate_id, historySearch)
            }
          />
        )}

        {activeTab === 'liveMonitor' && (
          <LiveApprovalMonitor
            visitors={visitors}
            isLoading={isLoadingData}
            onRefresh={() => void fetchGateData(activeGate?.gate_id, historySearch)}
            onCheckedIn={() => void fetchGateData(activeGate?.gate_id, historySearch)}
          />
        )}

        {activeTab === 'campusExit' && (
          <CampusExitManager
            activeGate={activeGate}
            visitors={visitors}
            onCheckedOut={() => void fetchGateData(activeGate?.gate_id, historySearch)}
          />
        )}

        {activeTab === 'history' && (
          <ScopedVisitorHistory
            visitors={visitors}
            flats={flats}
            searchQuery={historySearch}
            onSearchChange={(q) => setHistorySearch(q)}
          />
        )}
      </main>

      <GatePrivacyNoticeModal
        isOpen={privacyModalOpen}
        onClose={() => setPrivacyModalOpen(false)}
      />

      <OfflineQueueDrawer
        isOpen={offlineDrawerOpen}
        onClose={() => setOfflineDrawerOpen(false)}
        items={offlineQueue}
        isOnline={isOnline}
        isSyncing={isSyncingQueue}
        onSyncNow={() => void handleSyncNow(false)}
        onRetryFailed={() => void handleSyncNow(true)}
        onClearSynced={() => void handleClearSynced()}
      />
    </div>
  );
};

