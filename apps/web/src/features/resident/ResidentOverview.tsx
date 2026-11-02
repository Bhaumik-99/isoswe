import React, { useEffect, useState } from 'react';
import { Building, ShieldCheck, Calendar, Maximize2 } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { apiClient, ApiClientError } from '../../services/apiClient';
import { FlatDetail } from '../../types';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { Alert } from '../../components/ui/Alert';

export const ResidentOverview: React.FC = () => {
  const { selectedFlat } = useAuth();
  const [flatDetail, setFlatDetail] = useState<FlatDetail | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedFlat) {
      setIsLoading(false);
      return;
    }

    let isMounted = true;
    setIsLoading(true);
    setError(null);

    apiClient
      .get<FlatDetail>(`/api/v1/flats/${selectedFlat.flat_id}`)
      .then((data) => {
        if (isMounted) {
          setFlatDetail(data);
          setIsLoading(false);
        }
      })
      .catch((err: ApiClientError) => {
        if (isMounted) {
          setError(err.message || 'Unable to retrieve flat details');
          setIsLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [selectedFlat]);

  if (!selectedFlat) {
    return (
      <Alert variant="warning" title="No Approved Flat Membership">
        Your account currently does not hold an approved flat membership in Marvel Greenfield Residences.
        Please contact the society helpdesk for onboarding.
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Title */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-200">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Apartment Residence</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Verified property membership and society operations status
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={selectedFlat.membership_type === 'OWNER' ? 'success' : 'warning'}>
            Membership: {selectedFlat.membership_type}
          </Badge>
          <Badge variant="info">Status: {selectedFlat.status}</Badge>
        </div>
      </div>

      {error && (
        <Alert variant="error" title="Flat Authorization Notice">
          {error}
        </Alert>
      )}

      {/* Property Details Card */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Unit Specifications & Registry</CardTitle>
          <span className="text-xs font-mono text-slate-500">ID: {selectedFlat.flat_id.substring(0, 8)}...</span>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-20 w-full" />
            </div>
          ) : flatDetail ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="p-4 rounded-lg bg-slate-50 border border-slate-200">
                <div className="flex items-center gap-2 text-slate-500 text-xs font-semibold uppercase tracking-wider mb-1">
                  <Building className="h-4 w-4 text-indigo-600" />
                  <span>Tower & Unit</span>
                </div>
                <div className="text-lg font-bold text-slate-900">
                  {flatDetail.tower_number || 'Tower'} - {flatDetail.flat_number}
                </div>
                <div className="text-xs text-slate-500">{flatDetail.tower_name || 'Residential Tower'}</div>
              </div>

              <div className="p-4 rounded-lg bg-slate-50 border border-slate-200">
                <div className="flex items-center gap-2 text-slate-500 text-xs font-semibold uppercase tracking-wider mb-1">
                  <Maximize2 className="h-4 w-4 text-indigo-600" />
                  <span>Carpet / Area</span>
                </div>
                <div className="text-lg font-bold text-slate-900">{flatDetail.area_sqft} sq ft</div>
                <div className="text-xs text-slate-500">Super built-up measure</div>
              </div>

              <div className="p-4 rounded-lg bg-slate-50 border border-slate-200">
                <div className="flex items-center gap-2 text-slate-500 text-xs font-semibold uppercase tracking-wider mb-1">
                  <ShieldCheck className="h-4 w-4 text-emerald-600" />
                  <span>Lease / Tenancy</span>
                </div>
                <div className="text-sm font-semibold text-slate-900">
                  {selectedFlat.membership_type === 'OWNER' ? 'Permanent Ownership' : 'Active Tenancy Lease'}
                </div>
                <div className="text-xs text-slate-500">
                  {selectedFlat.valid_until
                    ? `Expires: ${new Date(selectedFlat.valid_until).toLocaleDateString()}`
                    : 'Indefinite (Owner Record)'}
                </div>
              </div>

              <div className="p-4 rounded-lg bg-slate-50 border border-slate-200">
                <div className="flex items-center gap-2 text-slate-500 text-xs font-semibold uppercase tracking-wider mb-1">
                  <Calendar className="h-4 w-4 text-indigo-600" />
                  <span>Registered Since</span>
                </div>
                <div className="text-sm font-semibold text-slate-900">
                  {new Date(selectedFlat.valid_from).toLocaleDateString()}
                </div>
                <div className="text-xs text-slate-500">Approved Membership Date</div>
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {/* Upcoming Modules Clarity Notice */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold flex items-center justify-between">
              <span>Maintenance & Billing Module</span>
              <Badge variant="warning">Phase 2 Scheduled</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-xs text-slate-600">
            <p>
              Automated monthly maintenance calculations based on carpet area (₹3.50/sq ft formula) and sinking fund contributions.
            </p>
            <div className="p-3 bg-slate-50 rounded border border-slate-200 space-y-1 font-mono text-[11px]">
              <div>Target Unit: {selectedFlat.tower_number}-{selectedFlat.flat_number}</div>
              <div>Billing Currency: INR (Paise precision)</div>
              <div>Payment Gateways: UPI, Netbanking, Cards</div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold flex items-center justify-between">
              <span>Facility Helpdesk & AI Complaints</span>
              <Badge variant="warning">Phase 3 Scheduled</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-xs text-slate-600">
            <p>
              Facility management ticket tracking with asynchronous Bedrock LLM classification, priority scoring, and SLA technician dispatch.
            </p>
            <div className="p-3 bg-slate-50 rounded border border-slate-200 space-y-1 font-mono text-[11px]">
              <div>Asynchronous Worker: complaint-ai-jobs (SQS)</div>
              <div>Audit Logging: audit_events ledger</div>
              <div>Technicians: 180 Facility Staff</div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};
