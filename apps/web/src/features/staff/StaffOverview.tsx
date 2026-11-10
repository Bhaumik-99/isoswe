import React, { useState, useEffect } from 'react';
import { Activity, CheckCircle2, Send, Shield, RefreshCw } from 'lucide-react';
import { apiClient, ApiClientError } from '../../services/apiClient';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Alert } from '../../components/ui/Alert';
import { useGsapStagger } from '../../components/motion/useGsapStagger';

interface HealthStatus {
  status: string;
  uptime_seconds?: number;
  database?: string;
  version?: string;
}

export const StaffOverview: React.FC = () => {
  const [liveHealth, setLiveHealth] = useState<HealthStatus | null>(null);
  const [readyHealth, setReadyHealth] = useState<HealthStatus | null>(null);
  const [isTriggeringEvent, setIsTriggeringEvent] = useState(false);
  const [isTestingFinance, setIsTestingFinance] = useState(false);
  const [eventResult, setEventResult] = useState<string | null>(null);
  const [financeResult, setFinanceResult] = useState<{ success: boolean; message: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const overviewRef = useGsapStagger<HTMLDivElement>('[data-gsap-stagger]');

  const checkHealth = async () => {
    try {
      const live = await apiClient.get<HealthStatus>('/health/live');
      setLiveHealth(live);
      const ready = await apiClient.get<HealthStatus>('/health/ready');
      setReadyHealth(ready);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Health check failed');
    }
  };

  useEffect(() => {
    checkHealth();
  }, []);

  const triggerOutboxHealthEvent = async () => {
    setIsTriggeringEvent(true);
    setEventResult(null);
    setError(null);
    try {
      const res = await apiClient.post<{ message: string; outbox_event_id: string }>(
        '/api/v1/events/health-check-event'
      );
      setEventResult(`Event committed to Outbox table! ID: ${res.outbox_event_id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to trigger outbox event');
    } finally {
      setIsTriggeringEvent(false);
    }
  };

  const testFinanceAction = async () => {
    setIsTestingFinance(true);
    setFinanceResult(null);
    try {
      const res = await apiClient.post<{ message: string }>(
        '/api/v1/finance/batch-billing/preview'
      );
      setFinanceResult({ success: true, message: res.message });
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setFinanceResult({
          success: false,
          message: `Backend RBAC Enforced: [${err.code}] ${err.message}`,
        });
      } else {
        setFinanceResult({ success: false, message: 'Action failed' });
      }
    } finally {
      setIsTestingFinance(false);
    }
  };

  return (
    <div ref={overviewRef} className="space-y-6">
      {/* Title */}
      <div data-gsap-stagger className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-5 border-b border-[#e0e0e0]">
        <div>
          <h1 className="font-display text-[34px] font-semibold leading-[1.2] tracking-[-0.374px] text-[#1d1d1f]">
            Operations Control Center
          </h1>
          <p className="text-[14px] text-[#333333] tracking-[-0.224px] mt-1">
            System health, asynchronous messaging verification, and RBAC evaluation
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="info">Society: Marvel Greenfield</Badge>
          <Button variant="outline" size="sm" onClick={checkHealth}>
            <RefreshCw className="h-3.5 w-3.5 mr-1.5" aria-hidden="true" />
            Refresh Probes
          </Button>
        </div>
      </div>

      {error && (
        <Alert variant="error" title="Operational Alert">
          {error}
        </Alert>
      )}

      {/* System Health Probes */}
      <div data-gsap-stagger className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold flex items-center justify-between">
              <span className="flex items-center gap-2">
                <Activity className="h-4 w-4 text-indigo-600" />
                Liveness Probe (GET /health/live)
              </span>
              {liveHealth ? (
                <Badge variant="success">Process Alive</Badge>
              ) : (
                <Badge variant="danger">Probing...</Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs font-mono">
            <div className="flex justify-between py-1 border-b border-slate-100">
              <span className="text-slate-500">Status:</span>
              <span className="font-semibold text-slate-900">{liveHealth?.status || 'Probing...'}</span>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-100">
              <span className="text-slate-500">Process Uptime:</span>
              <span className="font-semibold text-slate-900">
                {liveHealth?.uptime_seconds ? `${liveHealth.uptime_seconds}s` : '—'}
              </span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-slate-500">API Version:</span>
              <span className="font-semibold text-slate-900">{liveHealth?.version || '0.1.0'}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold flex items-center justify-between">
              <span className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                Readiness Probe (GET /health/ready)
              </span>
              {readyHealth?.database === 'healthy' ? (
                <Badge variant="success">DB Healthy</Badge>
              ) : (
                <Badge variant="warning">Checking...</Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs font-mono">
            <div className="flex justify-between py-1 border-b border-slate-100">
              <span className="text-slate-500">PostgreSQL Status:</span>
              <span className="font-semibold text-emerald-600">{readyHealth?.database || 'Probing...'}</span>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-100">
              <span className="text-slate-500">System of Record:</span>
              <span className="font-semibold text-slate-900">PostgreSQL (Psycopg 3)</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-slate-500">Isolation Mode:</span>
              <span className="font-semibold text-slate-900">Read Committed</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Asynchronous Messaging Outbox Demo */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold flex items-center justify-between">
            <span className="flex items-center gap-2">
              <Send className="h-4 w-4 text-indigo-600" />
              Asynchronous Outbox-to-SQS Journey Demonstration
            </span>
            <Badge variant="neutral">Section 6 Requirement</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-xs text-slate-600 leading-relaxed">
            Dispatches a synthetic <code className="bg-slate-100 px-1 py-0.5 rounded text-indigo-700">platform.health_check</code> event.
            The backend executes an atomic business transaction writing an <code className="bg-slate-100 px-1 py-0.5 rounded">audit_events</code> record
            and an <code className="bg-slate-100 px-1 py-0.5 rounded">outbox_events</code> record simultaneously.
            The outbox publisher picks up the event, dispatches it to SQS, and marks it published.
          </p>

          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
            <Button
              variant="primary"
              size="sm"
              isLoading={isTriggeringEvent}
              onClick={triggerOutboxHealthEvent}
            >
              <Send className="h-3.5 w-3.5 mr-1.5" />
              Dispatch Outbox Event
            </Button>
            {eventResult && (
              <span className="text-xs font-mono text-emerald-700 bg-emerald-50 px-2.5 py-1.5 rounded border border-emerald-200">
                {eventResult}
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* RBAC Boundary Test */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold flex items-center justify-between">
            <span className="flex items-center gap-2">
              <Shield className="h-4 w-4 text-slate-700" />
              Granular Permission Verification Action
            </span>
            <span className="text-xs text-slate-500">Restricted to HELPDESK (BANK_IMPORT / RECONCILIATION_REVIEW)</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-xs text-slate-600 leading-relaxed">
            Tests invoking <code className="bg-slate-100 px-1 py-0.5 rounded">POST /api/v1/finance/batch-billing/preview</code>.
            Under the two-role architecture, authenticated HELPDESK personnel holding granular finance/reconciliation permissions
            can execute this action, whereas unauthenticated users or residents are rejected with a 403 Forbidden.
          </p>

          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
            <Button
              variant="outline"
              size="sm"
              isLoading={isTestingFinance}
              onClick={testFinanceAction}
            >
              Execute Helpdesk Finance Action
            </Button>

            {financeResult && (
              <span
                className={`text-xs font-mono px-2.5 py-1.5 rounded border ${
                  financeResult.success
                    ? 'text-emerald-700 bg-emerald-50 border-emerald-200'
                    : 'text-rose-700 bg-rose-50 border-rose-200'
                }`}
              >
                {financeResult.message}
              </span>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
