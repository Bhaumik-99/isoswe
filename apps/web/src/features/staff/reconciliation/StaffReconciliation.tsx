import React, { useState } from 'react';
import {
  LayoutDashboard,
  UploadCloud,
  ListFilter,
  Receipt,
  FileSpreadsheet,
} from 'lucide-react';
import { ReconciliationOverview } from './ReconciliationOverview';
import { StatementUploadView } from './StatementUploadView';
import { ManualReviewQueueView } from './ManualReviewQueueView';
import { TransactionListView } from './TransactionListView';
import { ReconciliationReportsView } from './ReconciliationReportsView';

type ReconciliationTab = 'overview' | 'upload' | 'queue' | 'transactions' | 'reports';

export const StaffReconciliation: React.FC = () => {
  const [activeTab, setActiveTab] = useState<ReconciliationTab>('overview');

  const tabs: Array<{
    id: ReconciliationTab;
    label: string;
    icon: React.ComponentType<{ className?: string }>;
  }> = [
    { id: 'overview', label: 'Overview', icon: LayoutDashboard },
    { id: 'upload', label: 'Upload Statement', icon: UploadCloud },
    { id: 'queue', label: 'Review Queue', icon: ListFilter },
    { id: 'transactions', label: 'All Transactions', icon: Receipt },
    { id: 'reports', label: 'Reports & Audit', icon: FileSpreadsheet },
  ];

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 tracking-tight">
          Bank Statement Reconciliation
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          Automated CSV ingestion, multi-tier matching engine, and auditable financial ledger settlement
        </p>
      </div>

      {/* Tabs Bar */}
      <div className="border-b border-gray-200">
        <nav className="flex space-x-2 sm:space-x-4 overflow-x-auto" aria-label="Reconciliation Tabs">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 py-3 px-3 sm:px-4 text-xs sm:text-sm font-medium border-b-2 whitespace-nowrap transition-colors ${
                  isActive
                    ? 'border-indigo-600 text-indigo-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? 'text-indigo-600' : 'text-gray-400'}`} />
                {tab.label}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Tab Panels */}
      <div className="mt-4">
        {activeTab === 'overview' && (
          <ReconciliationOverview onNavigateTab={(tab) => setActiveTab(tab)} />
        )}
        {activeTab === 'upload' && (
          <StatementUploadView
            onImportConfirmed={() => {
              setActiveTab('queue');
            }}
          />
        )}
        {activeTab === 'queue' && <ManualReviewQueueView />}
        {activeTab === 'transactions' && <TransactionListView />}
        {activeTab === 'reports' && <ReconciliationReportsView />}
      </div>
    </div>
  );
};
