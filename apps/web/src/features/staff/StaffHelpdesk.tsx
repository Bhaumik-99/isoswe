import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  CheckCircle2,
  Copy,
  Lock,
  RefreshCw,
  Search,
  Send,
  ShieldAlert,
  Sparkles,
  X,
} from 'lucide-react';
import { complaintsService } from '../../services/complaintsService';
import {
  Complaint,
  ComplaintCategory,
  ComplaintPriority,
  ComplaintStatus,
} from '../../types/complaints';
import { Card, CardContent } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Skeleton } from '../../components/ui/Skeleton';
import { Alert } from '../../components/ui/Alert';

const CATEGORIES: { value: ComplaintCategory; label: string }[] = [
  { value: 'PLUMBING', label: 'Plumbing' },
  { value: 'ELECTRICAL', label: 'Electrical' },
  { value: 'LIFT', label: 'Lift & Elevator' },
  { value: 'HOUSEKEEPING', label: 'Housekeeping' },
  { value: 'SECURITY', label: 'Security' },
  { value: 'WATER_SUPPLY', label: 'Water Supply' },
  { value: 'WASTE_MANAGEMENT', label: 'Waste Management' },
  { value: 'STRUCTURAL', label: 'Structural & Seepage' },
  { value: 'COMMON_AREA', label: 'Common Area' },
  { value: 'OTHER', label: 'Other' },
];

function getStatusBadgeVariant(status: ComplaintStatus): 'neutral' | 'success' | 'warning' | 'info' | 'danger' {
  switch (status) {
    case 'RESOLVED':
    case 'CLOSED':
      return 'success';
    case 'IN_PROGRESS':
    case 'ASSIGNED':
      return 'info';
    case 'AWAITING_RESIDENT':
    case 'REOPENED':
      return 'warning';
    case 'CANCELLED':
      return 'neutral';
    default:
      return 'neutral';
  }
}

function getPriorityBadgeVariant(priority: ComplaintPriority): 'neutral' | 'success' | 'warning' | 'info' | 'danger' {
  switch (priority) {
    case 'CRITICAL':
    case 'HIGH':
      return 'danger';
    case 'MEDIUM':
      return 'warning';
    case 'LOW':
      return 'neutral';
    default:
      return 'neutral';
  }
}

function formatIST(dateStr?: string | null): string {
  if (!dateStr) return '—';
  try {
    const d = new Date(dateStr);
    return d.toLocaleString('en-IN', {
      timeZone: 'Asia/Kolkata',
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return dateStr;
  }
}

export const StaffHelpdesk: React.FC = () => {
  const queryClient = useQueryClient();

  // Filters
  const [selectedQueue, setSelectedQueue] = useState<'ALL' | 'UNASSIGNED' | 'CRITICAL' | 'IN_PROGRESS' | 'OVERDUE' | 'RESOLVED'>('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<string>('');
  const [priorityFilter, setPriorityFilter] = useState<string>('');

  // Selected complaint for management modal
  const [activeTicket, setActiveTicket] = useState<Complaint | null>(null);
  const [commentText, setCommentText] = useState('');
  const [isInternalNote, setIsInternalNote] = useState(false);
  const [transitionNotes, setTransitionNotes] = useState('');
  const [feedbackNotice, setFeedbackNotice] = useState<string | null>(null);

  // Governance state
  const [newCategorySelection, setNewCategorySelection] = useState<ComplaintCategory | ''>('');
  const [categoryCorrectionReason, setCategoryCorrectionReason] = useState('');
  const [primaryTicketIdInput, setPrimaryTicketIdInput] = useState('');
  const [duplicateLinkReason, setDuplicateLinkReason] = useState('');

  // Queries
  const { data: metrics, isLoading: isMetricsLoading } = useQuery({
    queryKey: ['helpdesk-dashboard-metrics'],
    queryFn: () => complaintsService.getHelpdeskDashboardMetrics(),
    refetchInterval: 15000,
  });

  const { data: safetyAlerts = [] } = useQuery({
    queryKey: ['helpdesk-safety-alerts'],
    queryFn: () => complaintsService.getSafetyAlerts(true),
    refetchInterval: 10000,
  });

  const ackSafetyAlertMutation = useMutation({
    mutationFn: (alertId: string) => complaintsService.acknowledgeSafetyAlert(alertId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['helpdesk-safety-alerts'] });
      queryClient.invalidateQueries({ queryKey: ['helpdesk-dashboard-metrics'] });
      setFeedbackNotice('Safety alert acknowledged by duty manager');
    },
  });

  const correctCategoryMutation = useMutation({
    mutationFn: () => {
      if (!activeTicket || !newCategorySelection) throw new Error('Category required');
      return complaintsService.correctCategory(
        activeTicket.id,
        newCategorySelection as ComplaintCategory,
        categoryCorrectionReason.trim() || undefined
      );
    },
    onSuccess: (updated) => {
      setActiveTicket(updated);
      setNewCategorySelection('');
      setCategoryCorrectionReason('');
      setFeedbackNotice('Category successfully corrected and audit trail recorded');
      queryClient.invalidateQueries({ queryKey: ['helpdesk-complaints'] });
    },
    onError: (err: any) => {
      setFeedbackNotice(err?.message || 'Failed to correct category');
    },
  });

  const linkDuplicateMutation = useMutation({
    mutationFn: () => {
      if (!activeTicket || !primaryTicketIdInput.trim()) throw new Error('Primary ID required');
      return complaintsService.linkDuplicate(
        activeTicket.id,
        primaryTicketIdInput.trim(),
        duplicateLinkReason.trim() || undefined
      );
    },
    onSuccess: (updated) => {
      setActiveTicket(updated);
      setPrimaryTicketIdInput('');
      setDuplicateLinkReason('');
      setFeedbackNotice('Complaint linked as duplicate (independent SLA preserved)');
      queryClient.invalidateQueries({ queryKey: ['helpdesk-complaints'] });
    },
    onError: (err: any) => {
      setFeedbackNotice(err?.message || 'Failed to link duplicate');
    },
  });

  const unlinkDuplicateMutation = useMutation({
    mutationFn: () => {
      if (!activeTicket) throw new Error('No active ticket');
      return complaintsService.unlinkDuplicate(activeTicket.id);
    },
    onSuccess: (updated) => {
      setActiveTicket(updated);
      setFeedbackNotice('Duplicate link removed');
      queryClient.invalidateQueries({ queryKey: ['helpdesk-complaints'] });
    },
    onError: (err: any) => {
      setFeedbackNotice(err?.message || 'Failed to unlink duplicate');
    },
  });

  const { data: complaints = [], isLoading: isListLoading, refetch } = useQuery({
    queryKey: [
      'helpdesk-complaints',
      selectedQueue,
      searchQuery,
      categoryFilter,
      priorityFilter,
    ],
    queryFn: () => {
      const params: any = {};
      if (searchQuery.trim()) params.search = searchQuery.trim();
      if (categoryFilter) params.category = categoryFilter as ComplaintCategory;
      if (priorityFilter) params.priority = priorityFilter as ComplaintPriority;

      if (selectedQueue === 'UNASSIGNED') params.unassigned_only = true;
      if (selectedQueue === 'CRITICAL') params.priority = 'CRITICAL';
      if (selectedQueue === 'IN_PROGRESS') params.status = ['IN_PROGRESS'];
      if (selectedQueue === 'OVERDUE') params.is_sla_breached = true;
      if (selectedQueue === 'RESOLVED') params.status = ['RESOLVED', 'CLOSED'];

      return complaintsService.listHelpdeskComplaints(params);
    },
  });

  // Fetch full details when opening ticket
  const openTicketModal = async (ticket: Complaint) => {
    try {
      const detailed = await complaintsService.getHelpdeskComplaint(ticket.id);
      setActiveTicket(detailed);
    } catch {
      setActiveTicket(ticket);
    }
  };

  // Status transition mutation
  const statusMutation = useMutation({
    mutationFn: async ({ status, notes }: { status: ComplaintStatus; notes?: string }) => {
      if (!activeTicket) return;
      return complaintsService.updateComplaintStatus(activeTicket.id, status, notes);
    },
    onSuccess: (updated) => {
      if (updated) setActiveTicket(updated);
      setTransitionNotes('');
      queryClient.invalidateQueries({ queryKey: ['helpdesk-complaints'] });
      queryClient.invalidateQueries({ queryKey: ['helpdesk-dashboard-metrics'] });
      setFeedbackNotice(`Ticket status updated to ${updated?.status}`);
    },
  });

  // Priority update mutation
  const priorityMutation = useMutation({
    mutationFn: async (priority: ComplaintPriority) => {
      if (!activeTicket) return;
      return complaintsService.updateComplaintPriority(activeTicket.id, priority);
    },
    onSuccess: (updated) => {
      if (updated) setActiveTicket(updated);
      queryClient.invalidateQueries({ queryKey: ['helpdesk-complaints'] });
      queryClient.invalidateQueries({ queryKey: ['helpdesk-dashboard-metrics'] });
      setFeedbackNotice(`Priority updated to ${updated?.priority}`);
    },
  });

  // Add Comment / Internal Note mutation
  const commentMutation = useMutation({
    mutationFn: async () => {
      if (!activeTicket || !commentText.trim()) return;
      return complaintsService.addHelpdeskComment(activeTicket.id, commentText.trim(), isInternalNote);
    },
    onSuccess: async () => {
      setCommentText('');
      if (activeTicket) {
        const refreshed = await complaintsService.getHelpdeskComplaint(activeTicket.id);
        if (refreshed) setActiveTicket(refreshed);
        queryClient.invalidateQueries({ queryKey: ['helpdesk-complaints'] });
      }
    },
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">Helpdesk Operations & AI Triage</h1>
          <p className="text-sm text-gray-500">
            Township facility management queue for 2,400 apartments, 28 towers, and 180 staff members.
          </p>
        </div>
        <Button variant="outline" onClick={() => refetch()} className="flex items-center gap-2">
          <RefreshCw className="h-4 w-4" /> Refresh
        </Button>
      </div>

      {/* Emergency Duty Manager Safety Alerts Banner */}
      {safetyAlerts.length > 0 && (
        <div className="bg-rose-50 border-2 border-rose-300 rounded-xl p-4 shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-rose-800 font-bold text-sm">
              <ShieldAlert className="h-5 w-5 text-rose-600 animate-pulse" />
              <span>EMERGENCY DUTY-MANAGER SAFETY QUEUE ({safetyAlerts.length} Unacknowledged)</span>
            </div>
            <Badge variant="danger" className="text-xs font-mono">
              CRITICAL HAZARD DISPATCH
            </Badge>
          </div>
          <div className="space-y-2">
            {safetyAlerts.map((alert) => (
              <div
                key={alert.id}
                className="flex flex-col sm:flex-row sm:items-center justify-between bg-white p-3 rounded-lg border border-rose-200 gap-2 shadow-xs"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-rose-900 text-xs font-mono">{alert.hazard_type}</span>
                    <span className="text-slate-500 text-[11px]">• Flat {alert.flat_number || 'Common Area'}</span>
                    <span className="text-[10px] text-slate-400 font-mono">
                      Raised {new Date(alert.created_at).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                  <p className="text-xs text-slate-800 font-medium mt-0.5">{alert.complaint_title}</p>
                </div>
                <Button
                  size="sm"
                  variant="primary"
                  onClick={() => ackSafetyAlertMutation.mutate(alert.id)}
                  disabled={ackSafetyAlertMutation.isPending}
                  className="bg-rose-600 hover:bg-rose-700 text-white text-xs shrink-0"
                >
                  {ackSafetyAlertMutation.isPending ? 'Acknowledging...' : 'Acknowledge Hazard'}
                </Button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* KPI Cards */}
      {isMetricsLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <Card className="p-3 border shadow-sm">
            <span className="text-xs text-gray-500 block font-medium">Total Tickets</span>
            <span className="text-xl font-bold text-gray-900">{metrics?.total_complaints || 0}</span>
          </Card>
          <Card className="p-3 border shadow-sm bg-amber-50/50 border-amber-200">
            <span className="text-xs text-amber-800 block font-medium">Unassigned</span>
            <span className="text-xl font-bold text-amber-900">{metrics?.unassigned_count || 0}</span>
          </Card>
          <Card className="p-3 border shadow-sm">
            <span className="text-xs text-gray-500 block font-medium">In Progress</span>
            <span className="text-xl font-bold text-indigo-600">{metrics?.in_progress_count || 0}</span>
          </Card>
          <Card className="p-3 border shadow-sm bg-red-50/50 border-red-200">
            <span className="text-xs text-red-700 block font-medium">Critical Hazards</span>
            <span className="text-xl font-bold text-red-700">{metrics?.critical_count || 0}</span>
          </Card>
          <Card className="p-3 border shadow-sm">
            <span className="text-xs text-gray-500 block font-medium">SLA Overdue</span>
            <span className="text-xl font-bold text-red-600">{metrics?.overdue_count || 0}</span>
          </Card>
          <Card className="p-3 border shadow-sm bg-green-50/50 border-green-200">
            <span className="text-xs text-green-800 block font-medium">Resolution Rate</span>
            <span className="text-xl font-bold text-green-800">{metrics?.resolution_rate_percentage || 0}%</span>
          </Card>
        </div>
      )}

      {/* Queue Tabs */}
      <div className="flex border-b border-gray-200 overflow-x-auto text-sm">
        {(
          [
            ['ALL', 'All Tickets'],
            ['UNASSIGNED', 'Unassigned Queue'],
            ['CRITICAL', 'Safety Critical'],
            ['IN_PROGRESS', 'In Progress'],
            ['OVERDUE', 'SLA Breached'],
            ['RESOLVED', 'Resolved & Closed'],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setSelectedQueue(key)}
            className={`py-2 px-4 whitespace-nowrap font-medium border-b-2 -mb-px transition-colors ${
              selectedQueue === key
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Filters Bar */}
      <div className="flex flex-wrap gap-3 items-center bg-gray-50 p-3 rounded-lg border">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search complaint #, unit, title, or keywords..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 border rounded-md text-xs bg-white text-gray-900 border-gray-300"
          />
        </div>

        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="border rounded-md px-2.5 py-1.5 text-xs bg-white text-gray-900 border-gray-300"
        >
          <option value="">All Categories</option>
          {CATEGORIES.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>

        <select
          value={priorityFilter}
          onChange={(e) => setPriorityFilter(e.target.value)}
          className="border rounded-md px-2.5 py-1.5 text-xs bg-white text-gray-900 border-gray-300"
        >
          <option value="">All Priorities</option>
          <option value="CRITICAL">Critical</option>
          <option value="HIGH">High</option>
          <option value="MEDIUM">Medium</option>
          <option value="LOW">Low</option>
        </select>
      </div>

      {/* Action Notice */}
      {feedbackNotice && (
        <Alert variant="info" className="flex justify-between items-center py-2">
          <span className="text-xs">{feedbackNotice}</span>
          <button onClick={() => setFeedbackNotice(null)} className="text-indigo-600 hover:text-indigo-800">
            <X className="h-4 w-4" />
          </button>
        </Alert>
      )}

      {/* Tickets Table */}
      {isListLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : complaints.length === 0 ? (
        <Card className="text-center py-12">
          <CardContent className="space-y-2">
            <CheckCircle2 className="mx-auto h-10 w-10 text-gray-300" />
            <h3 className="text-sm font-semibold text-gray-900">Queue is clear</h3>
            <p className="text-xs text-gray-500">No active complaints match the selected filter criteria.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="border rounded-lg bg-white overflow-hidden shadow-sm">
          <table className="min-w-full divide-y divide-gray-200 text-xs">
            <thead className="bg-gray-50 font-medium text-gray-600">
              <tr>
                <th className="py-3 px-4 text-left">Complaint #</th>
                <th className="py-3 px-4 text-left">Apartment Unit</th>
                <th className="py-3 px-4 text-left">Subject / Category</th>
                <th className="py-3 px-4 text-left">Priority</th>
                <th className="py-3 px-4 text-left">Status</th>
                <th className="py-3 px-4 text-left">Assigned Staff</th>
                <th className="py-3 px-4 text-left">Resolution SLA</th>
                <th className="py-3 px-4 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 text-gray-800">
              {complaints.map((c) => (
                <tr
                  key={c.id}
                  onClick={() => openTicketModal(c)}
                  className="hover:bg-gray-50 cursor-pointer transition-colors"
                >
                  <td className="py-3 px-4 font-mono font-bold text-gray-700">{c.complaint_number}</td>
                  <td className="py-3 px-4">
                    <span className="font-semibold">
                      {c.tower_number ? `T${c.tower_number}` : ''} - {c.flat_number}
                    </span>
                    <span className="block text-[11px] text-gray-400">{c.creator_name || 'Resident'}</span>
                  </td>
                  <td className="py-3 px-4 max-w-xs">
                    <div className="font-medium truncate text-gray-900">{c.title}</div>
                    <span className="text-[11px] text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">
                      {c.category}
                    </span>
                  </td>
                  <td className="py-3 px-4">
                    <Badge variant={getPriorityBadgeVariant(c.priority)}>
                      {c.safety_escalated ? '🚨 CRITICAL' : c.priority}
                    </Badge>
                  </td>
                  <td className="py-3 px-4">
                    <Badge variant={getStatusBadgeVariant(c.status)}>{c.status.replace('_', ' ')}</Badge>
                  </td>
                  <td className="py-3 px-4 text-gray-600">{c.assignee_name || '—'}</td>
                  <td className="py-3 px-4">
                    <span className={c.is_sla_breached ? 'text-red-600 font-bold' : 'text-gray-600'}>
                      {formatIST(c.resolution_deadline)}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-right">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={(e) => {
                        e.stopPropagation();
                        openTicketModal(c);
                      }}
                    >
                      Manage
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Ticket Management Modal */}
      {activeTicket && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 overflow-y-auto">
          <div className="bg-white rounded-xl shadow-2xl max-w-3xl w-full max-h-[92vh] overflow-y-auto p-6 space-y-5">
            {/* Modal Header */}
            <div className="flex justify-between items-start border-b pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm font-bold text-gray-600">{activeTicket.complaint_number}</span>
                  <Badge variant={getStatusBadgeVariant(activeTicket.status)}>
                    {activeTicket.status.replace('_', ' ')}
                  </Badge>
                  <Badge variant={getPriorityBadgeVariant(activeTicket.priority)}>{activeTicket.priority}</Badge>
                </div>
                <h2 className="text-xl font-bold text-gray-900 mt-1">{activeTicket.title}</h2>
              </div>
              <button
                onClick={() => setActiveTicket(null)}
                className="text-gray-400 hover:text-gray-600 rounded-lg p-1"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Safety Hazard Banner */}
            {activeTicket.safety_escalated && (
              <Alert variant="error" className="flex items-start gap-2">
                <ShieldAlert className="h-5 w-5 flex-shrink-0 mt-0.5" />
                <div className="text-xs">
                  <strong>Critical Safety Incident Flagged:</strong> {activeTicket.safety_escalation_reason}. Priority is
                  locked to CRITICAL per safety protocol.
                </div>
              </Alert>
            )}

            {/* AI Triage Card */}
            <div className="bg-gradient-to-r from-purple-50 to-indigo-50 border border-indigo-100 rounded-lg p-4 space-y-3 text-xs">
              <div className="flex flex-wrap items-center gap-2 font-bold text-indigo-900">
                <Sparkles className="h-4 w-4 text-indigo-600" />
                <span>AI Advisory Triage Analysis</span>
                <span className="font-normal text-xs text-indigo-700 bg-white px-2 py-0.5 rounded border border-indigo-200">
                  {activeTicket.ai_status || 'COMPLETED'}
                </span>
                {activeTicket.ai_confidence_score !== undefined && activeTicket.ai_confidence_score !== null && (
                  <span className="font-normal text-xs text-indigo-600 bg-white px-2 py-0.5 rounded border border-indigo-200">
                    Confidence: {Math.round(activeTicket.ai_confidence_score * 100)}%
                  </span>
                )}
                {activeTicket.ai_model && (
                  <span className="font-mono text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded text-[11px]">
                    {activeTicket.ai_model}
                  </span>
                )}
                {activeTicket.ai_confidence_score !== null &&
                  activeTicket.ai_confidence_score !== undefined &&
                  activeTicket.ai_confidence_score < 0.75 && (
                    <span className="font-bold text-amber-700 bg-amber-100 px-2 py-0.5 rounded border border-amber-300">
                      Requires Human Review
                    </span>
                  )}
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-indigo-800">
                <div>
                  <span className="text-indigo-500 block">Suggested Category:</span>
                  <span className="font-semibold">{activeTicket.ai_suggested_category || activeTicket.category}</span>
                </div>
                <div>
                  <span className="text-indigo-500 block">Suggested Priority:</span>
                  <span className="font-semibold">{activeTicket.ai_suggested_priority || activeTicket.priority}</span>
                </div>
                <div>
                  <span className="text-indigo-500 block">Urgency Justification:</span>
                  <span className="italic">{activeTicket.ai_urgency_reason || 'Standard township maintenance'}</span>
                </div>
              </div>
              {activeTicket.ai_reasoning && (
                <div className="pt-2 border-t border-indigo-100 text-indigo-900">
                  <span className="font-semibold text-indigo-600 block mb-0.5">AI Analysis & Reasoning:</span>
                  <p className="text-gray-700 leading-relaxed">{activeTicket.ai_reasoning}</p>
                </div>
              )}
            </div>

            {/* Duplicate Candidate Warning */}
            {activeTicket.duplicate_candidates && activeTicket.duplicate_candidates.length > 0 && (
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-900 flex items-start gap-2">
                <Copy className="h-4 w-4 text-amber-600 flex-shrink-0 mt-0.5" />
                <div>
                  <span className="font-bold">Potential Duplicate Detected:</span> Found{' '}
                  {activeTicket.duplicate_candidates.length} active ticket(s) in this society with matching symptoms.
                  Inspect candidates before dispatching multiple technicians.
                </div>
              </div>
            )}

            {/* Operational Action Controls */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 bg-gray-50 p-4 rounded-lg border text-xs">
              <div>
                <label className="block font-semibold text-gray-700 mb-1">Update Status</label>
                <select
                  value={activeTicket.status}
                  onChange={(e) =>
                    statusMutation.mutate({
                      status: e.target.value as ComplaintStatus,
                      notes: transitionNotes || undefined,
                    })
                  }
                  className="w-full border rounded p-2 bg-white text-gray-900 border-gray-300"
                >
                  <option value="SUBMITTED">Submitted</option>
                  <option value="TRIAGED">Triaged</option>
                  <option value="ASSIGNED">Assigned</option>
                  <option value="IN_PROGRESS">In Progress</option>
                  <option value="AWAITING_RESIDENT">Awaiting Resident Response</option>
                  <option value="RESOLVED">Resolved</option>
                  <option value="CLOSED">Closed</option>
                  <option value="CANCELLED">Cancelled</option>
                </select>
              </div>

              <div>
                <label className="block font-semibold text-gray-700 mb-1">Operational Priority</label>
                <select
                  value={activeTicket.priority}
                  disabled={activeTicket.safety_escalated}
                  onChange={(e) => priorityMutation.mutate(e.target.value as ComplaintPriority)}
                  className="w-full border rounded p-2 bg-white text-gray-900 border-gray-300 disabled:bg-gray-100 disabled:text-gray-400"
                >
                  <option value="LOW">Low (5 Days SLA)</option>
                  <option value="MEDIUM">Medium (48 Hours SLA)</option>
                  <option value="HIGH">High (8 Hours SLA)</option>
                  <option value="CRITICAL">Critical (2 Hours SLA)</option>
                </select>
                {activeTicket.safety_escalated && (
                  <span className="text-[10px] text-gray-400">Locked to Critical due to safety escalation</span>
                )}
              </div>
            </div>

            {/* Category Governance & AI Feedback */}
            <div className="bg-indigo-50/60 border border-indigo-200 rounded-lg p-3 text-xs space-y-2">
              <div className="flex items-center justify-between">
                <div className="font-bold text-indigo-950 flex items-center gap-1.5">
                  <Sparkles className="h-4 w-4 text-indigo-600" />
                  <span>Category Governance & AI Feedback</span>
                </div>
                {activeTicket.original_category && (
                  <Badge variant="warning" className="text-[10px] py-0 px-1.5 font-mono">
                    Original AI Category: {activeTicket.original_category} (Corrected)
                  </Badge>
                )}
              </div>
              <div className="flex flex-col sm:flex-row gap-2">
                <select
                  value={newCategorySelection}
                  onChange={(e) => setNewCategorySelection(e.target.value as ComplaintCategory)}
                  className="border rounded p-1.5 bg-white text-gray-900 border-indigo-300 flex-1 text-xs"
                >
                  <option value="">Change Category (Current: {activeTicket.category})...</option>
                  {CATEGORIES.filter((c) => c.value !== activeTicket.category).map((cat) => (
                    <option key={cat.value} value={cat.value}>
                      {cat.label}
                    </option>
                  ))}
                </select>
                <input
                  type="text"
                  placeholder="Correction reason (optional audit note)"
                  value={categoryCorrectionReason}
                  onChange={(e) => setCategoryCorrectionReason(e.target.value)}
                  className="border rounded p-1.5 bg-white text-gray-900 border-indigo-300 flex-1 text-xs"
                />
                <Button
                  size="sm"
                  variant="primary"
                  disabled={!newCategorySelection || correctCategoryMutation.isPending}
                  onClick={() => correctCategoryMutation.mutate()}
                  className="text-xs shrink-0 bg-indigo-600 hover:bg-indigo-700 text-white"
                >
                  {correctCategoryMutation.isPending ? 'Updating...' : 'Correct Category'}
                </Button>
              </div>
            </div>

            {/* Duplicate Incident Linking (Independent SLAs) */}
            <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 text-xs space-y-2">
              <div className="flex items-center justify-between">
                <div className="font-bold text-slate-800 flex items-center gap-1.5">
                  <Copy className="h-4 w-4 text-slate-600" />
                  <span>Duplicate Incident Linking (Independent SLAs Preserved)</span>
                </div>
                {activeTicket.duplicate_of_id ? (
                  <div className="flex items-center gap-2">
                    <Badge variant="info" className="text-[10px] py-0 font-mono">
                      Linked to Parent #{activeTicket.duplicate_of_id.slice(0, 8)}
                    </Badge>
                    <button
                      onClick={() => unlinkDuplicateMutation.mutate()}
                      disabled={unlinkDuplicateMutation.isPending}
                      className="text-rose-600 hover:text-rose-800 text-[11px] underline"
                    >
                      Unlink
                    </button>
                  </div>
                ) : (
                  <span className="text-[11px] text-slate-500">Primary Incident</span>
                )}
              </div>
              {!activeTicket.duplicate_of_id && (
                <div className="flex flex-col sm:flex-row gap-2">
                  <input
                    type="text"
                    placeholder="Parent Complaint UUID..."
                    value={primaryTicketIdInput}
                    onChange={(e) => setPrimaryTicketIdInput(e.target.value)}
                    className="border rounded p-1.5 bg-white text-gray-900 border-gray-300 flex-1 text-xs font-mono"
                  />
                  <input
                    type="text"
                    placeholder="Linking note..."
                    value={duplicateLinkReason}
                    onChange={(e) => setDuplicateLinkReason(e.target.value)}
                    className="border rounded p-1.5 bg-white text-gray-900 border-gray-300 flex-1 text-xs"
                  />
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!primaryTicketIdInput.trim() || linkDuplicateMutation.isPending}
                    onClick={() => linkDuplicateMutation.mutate()}
                    className="text-xs shrink-0"
                  >
                    {linkDuplicateMutation.isPending ? 'Linking...' : 'Link Duplicate'}
                  </Button>
                </div>
              )}
            </div>

            {/* Resident Description & Metadata */}
            <div className="space-y-1 text-xs">
              <span className="font-bold text-gray-500 uppercase tracking-wider">Complaint Details</span>
              <p className="bg-gray-50 p-3 rounded-lg text-gray-800 whitespace-pre-wrap">{activeTicket.description}</p>
            </div>

            {/* Comments & Internal Staff Notes */}
            <div className="space-y-3 text-xs">
              <div className="flex justify-between items-center">
                <span className="font-bold text-gray-700 uppercase tracking-wider">
                  Timeline, Resident Chats & Internal Notes
                </span>
                <span className="text-[11px] text-indigo-600 flex items-center gap-1">
                  <Lock className="h-3 w-3" /> Internal notes hidden from residents
                </span>
              </div>

              <div className="space-y-2 max-h-52 overflow-y-auto p-1 border rounded-lg bg-gray-50">
                {activeTicket.comments.length === 0 ? (
                  <p className="text-gray-400 italic p-3 text-center">No conversation entries yet.</p>
                ) : (
                  activeTicket.comments.map((comm) => (
                    <div
                      key={comm.id}
                      className={`p-3 rounded-lg space-y-1 ${
                        comm.is_internal
                          ? 'bg-amber-50 border border-amber-200 text-amber-950'
                          : 'bg-white border border-gray-200 text-gray-800'
                      }`}
                    >
                      <div className="flex justify-between font-semibold">
                        <span className="flex items-center gap-1.5">
                          {comm.is_internal && (
                            <span className="bg-amber-200 text-amber-800 text-[10px] px-1.5 py-0.2 rounded font-bold">
                              INTERNAL NOTE
                            </span>
                          )}
                          {comm.user_name || 'Staff Member'}
                        </span>
                        <span className="text-gray-400 font-normal">{formatIST(comm.created_at)}</span>
                      </div>
                      <p>{comm.comment}</p>
                    </div>
                  ))
                )}
              </div>

              {/* Add Comment / Internal Note Form */}
              <div className="space-y-2 border-t pt-2">
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    placeholder={
                      isInternalNote
                        ? 'Write internal note (hidden from resident)...'
                        : 'Write reply to resident...'
                    }
                    value={commentText}
                    onChange={(e) => setCommentText(e.target.value)}
                    className="flex-1 border rounded-lg px-3 py-2 text-xs border-gray-300 focus:ring-1 focus:ring-indigo-500"
                  />
                  <Button
                    size="sm"
                    onClick={() => commentMutation.mutate()}
                    disabled={commentMutation.isPending || !commentText.trim()}
                  >
                    <Send className="h-3.5 w-3.5 mr-1" /> Post
                  </Button>
                </div>
                <label className="flex items-center gap-2 text-xs text-gray-600 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={isInternalNote}
                    onChange={(e) => setIsInternalNote(e.target.checked)}
                    className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  <span className="font-medium">
                    Mark as Internal Note <span className="text-gray-400 font-normal">(Helpdesk only)</span>
                  </span>
                </label>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
