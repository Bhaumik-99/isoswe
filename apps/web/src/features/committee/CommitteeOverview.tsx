import React from 'react';
import { Landmark, Users, Building, ShieldCheck, ScrollText } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';

export const CommitteeOverview: React.FC = () => {
  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-200">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Managing Committee Oversight</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Federation governance, multi-tower metrics, and compliance audit trail
          </p>
        </div>
        <Badge variant="neutral">Society: Marvel Greenfield Residences</Badge>
      </div>

      {/* High-Level Township Scale Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between text-slate-500 mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider">Total Apartments</span>
              <Building className="h-4 w-4 text-indigo-600" />
            </div>
            <div className="text-2xl font-bold text-slate-900">2,400</div>
            <div className="text-xs text-slate-500 mt-0.5">Across 28 residential towers</div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between text-slate-500 mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider">Facility Staff</span>
              <Users className="h-4 w-4 text-indigo-600" />
            </div>
            <div className="text-2xl font-bold text-slate-900">180</div>
            <div className="text-xs text-slate-500 mt-0.5">Facility management employees</div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between text-slate-500 mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider">Phase 1 Initial Towers</span>
              <Landmark className="h-4 w-4 text-emerald-600" />
            </div>
            <div className="text-2xl font-bold text-slate-900">3 Towers</div>
            <div className="text-xs text-slate-500 mt-0.5">T07, T12, T21 (Active Seed)</div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between text-slate-500 mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider">Audit Trail</span>
              <ShieldCheck className="h-4 w-4 text-emerald-600" />
            </div>
            <div className="text-2xl font-bold text-emerald-600">Active</div>
            <div className="text-xs text-slate-500 mt-0.5">Immutable audit_events log</div>
          </CardContent>
        </Card>
      </div>

      {/* Governance & Audit Note */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <ScrollText className="h-4 w-4 text-indigo-600" />
            <span>Governance Principles & Statutory Compliance</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="text-xs text-slate-600 space-y-2 leading-relaxed">
          <p>
            Committee viewers possess strictly read-only authorization. Modifying billing ledgers,
            membership dates, or financial allocations requires privileged administrative or finance approval.
          </p>
          <p>
            Every transaction, access event, and background outbox dispatch is logged with correlated
            request identifiers to ensure complete forensic transparency for the residents federation.
          </p>
        </CardContent>
      </Card>
    </div>
  );
};
