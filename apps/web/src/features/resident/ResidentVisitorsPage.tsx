import React, { useCallback, useEffect, useState } from 'react';
import {
  UserCheck,
  Clock,
  Calendar,
  KeyRound,
  History,
  Globe,
  RefreshCw,
} from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { GuestPass, VisitorRecord } from '../../types';
import { residentVisitorService } from '../../services/residentVisitorService';
import {
  LANGUAGE_LABELS,
  SupportedLanguage,
  useLanguage,
} from '../../i18n/LanguageContext';
import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { PendingApprovalsInbox } from './components/PendingApprovalsInbox';
import { TodayVisitorsFeed } from './components/TodayVisitorsFeed';
import { GuestPassManager } from './components/GuestPassManager';
import { ResidentVisitorHistory } from './components/ResidentVisitorHistory';

type ResidentVisitorTab = 'pending' | 'today' | 'passes' | 'history';

export const ResidentVisitorsPage: React.FC = () => {
  const { selectedFlat } = useAuth();
  const { language, setLanguage, t } = useLanguage();

  const [activeTab, setActiveTab] = useState<ResidentVisitorTab>('pending');
  const [pendingVisitors, setPendingVisitors] = useState<VisitorRecord[]>([]);
  const [todayVisitors, setTodayVisitors] = useState<VisitorRecord[]>([]);
  const [historyVisitors, setHistoryVisitors] = useState<VisitorRecord[]>([]);
  const [passes, setPasses] = useState<GuestPass[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const loadAllVisitorData = useCallback(async () => {
    if (!selectedFlat) return;
    setIsLoading(true);
    try {
      const [pendingList, todayList, historyList, passList] = await Promise.all([
        residentVisitorService.listPendingVisitors(),
        residentVisitorService.listTodayVisitors(),
        residentVisitorService.listVisitorHistory(25, 0),
        residentVisitorService.listGuestPasses(),
      ]);
      // Filter to active selected flat if resident holds multiple flats
      setPendingVisitors(
        pendingList.filter((v) => v.destination_flat_id === selectedFlat.flat_id)
      );
      setTodayVisitors(
        todayList.filter((v) => v.destination_flat_id === selectedFlat.flat_id)
      );
      setHistoryVisitors(
        historyList.filter((v) => v.destination_flat_id === selectedFlat.flat_id)
      );
      setPasses(passList.filter((p) => p.destination_flat_id === selectedFlat.flat_id));
    } finally {
      setIsLoading(false);
    }
  }, [selectedFlat]);

  useEffect(() => {
    void loadAllVisitorData();
  }, [loadAllVisitorData]);

  useEffect(() => {
    const onFocus = () => {
      void loadAllVisitorData();
    };
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [loadAllVisitorData]);

  if (!selectedFlat) {
    return (
      <Alert variant="warning" title="No Approved Flat Membership">
        Your account does not hold an active, approved flat membership.
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header & Language Switcher */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-200">
        <div>
          <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2">
            <UserCheck className="h-5 w-5 text-indigo-600" />
            <span>{t.resident.pageTitle}</span>
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">{t.resident.pageSubtitle}</p>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center bg-slate-100 border border-slate-200 rounded-lg p-1">
            <Globe className="h-3.5 w-3.5 text-slate-500 mx-1.5" />
            {(['en', 'hi', 'mr'] as SupportedLanguage[]).map((lang) => (
              <button
                key={lang}
                type="button"
                onClick={() => setLanguage(lang)}
                className={`px-2.5 py-1 rounded text-xs font-semibold transition-colors ${
                  language === lang
                    ? 'bg-indigo-600 text-white'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                {LANGUAGE_LABELS[lang]}
              </button>
            ))}
          </div>

          <Button
            size="sm"
            variant="outline"
            onClick={() => void loadAllVisitorData()}
            className="text-xs flex items-center gap-1"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            <span>{t.common.refresh}</span>
          </Button>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 bg-slate-100 p-1.5 rounded-xl border border-slate-200">
        {(
          [
            {
              id: 'pending',
              label: `${t.resident.tabs.pending} (${pendingVisitors.length})`,
              icon: Clock,
            },
            {
              id: 'today',
              label: `${t.resident.tabs.today} (${todayVisitors.length})`,
              icon: Calendar,
            },
            {
              id: 'passes',
              label: `${t.resident.tabs.passes} (${passes.length})`,
              icon: KeyRound,
            },
            {
              id: 'history',
              label: t.resident.tabs.history,
              icon: History,
            },
          ] as const
        ).map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`py-2.5 px-3 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors ${
                isActive
                  ? 'bg-white text-indigo-700 shadow-sm font-bold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* Active Tab Content */}
      {activeTab === 'pending' && (
        <PendingApprovalsInbox
          visitors={pendingVisitors}
          onActionCompleted={() => void loadAllVisitorData()}
        />
      )}

      {activeTab === 'today' && <TodayVisitorsFeed visitors={todayVisitors} />}

      {activeTab === 'passes' && (
        <GuestPassManager
          flatId={selectedFlat.flat_id}
          passes={passes}
          onPassesUpdated={() => void loadAllVisitorData()}
        />
      )}

      {activeTab === 'history' && <ResidentVisitorHistory visitors={historyVisitors} />}
    </div>
  );
};

