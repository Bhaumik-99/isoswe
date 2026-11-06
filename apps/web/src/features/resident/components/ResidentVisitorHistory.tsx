import React from 'react';
import { VisitorRecord } from '../../../types';
import { useLanguage } from '../../../i18n/LanguageContext';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/Card';
import { Badge } from '../../../components/ui/Badge';

interface ResidentVisitorHistoryProps {
  visitors: VisitorRecord[];
}

export const ResidentVisitorHistory: React.FC<ResidentVisitorHistoryProps> = ({ visitors }) => {
  const { t } = useLanguage();

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t.resident.history.title}</CardTitle>
        <p className="text-xs text-slate-500 mt-0.5">{t.resident.history.subtitle}</p>
      </CardHeader>
      <CardContent>
        {visitors.length === 0 ? (
          <div className="p-8 text-center text-slate-500 text-xs bg-slate-50 rounded-lg border border-slate-200">
            {t.resident.history.emptyMessage}
          </div>
        ) : (
          <div className="space-y-3">
            {visitors.map((v) => (
              <div
                key={v.visitor_id}
                className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-sm text-slate-900">{v.visitor_name}</span>
                    <span className="text-xs font-mono text-slate-500">{v.phone_masked}</span>
                  </div>
                  <div className="text-xs text-slate-500 mt-0.5">
                    {v.purpose} • {new Date(v.created_at).toLocaleString()}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Badge
                    variant={
                      v.approval_status === 'APPROVED' || v.approval_status === 'AUTO_APPROVED'
                        ? 'success'
                        : v.approval_status === 'REJECTED'
                          ? 'danger'
                          : 'warning'
                    }
                  >
                    {t.statuses.approval[v.approval_status] || v.approval_status}
                  </Badge>
                  <Badge variant="neutral">
                    {t.statuses.entry[v.entry_status] || v.entry_status}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

