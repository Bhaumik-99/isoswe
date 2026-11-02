import React from 'react';
import { Clock, ShieldCheck } from 'lucide-react';
import { Card, CardContent } from './ui/Card';
import { Badge } from './ui/Badge';

interface UpcomingModuleNoticeProps {
  moduleName: string;
  plannedPhase: string;
  description: string;
  deliverables: string[];
}

export const UpcomingModuleNotice: React.FC<UpcomingModuleNoticeProps> = ({
  moduleName,
  plannedPhase,
  description,
  deliverables,
}) => {
  return (
    <div className="max-w-3xl mx-auto py-8 px-4">
      <Card>
        <CardContent className="p-8">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-slate-100 rounded-lg text-slate-700">
                <Clock className="h-6 w-6" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-slate-900">{moduleName}</h2>
                <p className="text-xs text-slate-500 font-mono mt-0.5">Domain Boundary Established</p>
              </div>
            </div>
            <Badge variant="warning">{plannedPhase}</Badge>
          </div>

          <p className="text-slate-600 mb-6 text-sm leading-relaxed">{description}</p>

          <div className="bg-slate-50 rounded-lg p-5 border border-slate-200">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-700 mb-3 flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-emerald-600" />
              Engineering Readiness & Target Capabilities
            </h4>
            <ul className="space-y-2 text-sm text-slate-600">
              {deliverables.map((item, index) => (
                <li key={index} className="flex items-start gap-2">
                  <span className="text-indigo-600 font-bold">•</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
