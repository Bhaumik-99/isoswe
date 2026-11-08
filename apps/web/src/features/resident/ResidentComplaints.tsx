import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  FileText,
  Plus,
  RefreshCw,
  Send,
  ShieldAlert,
  Sparkles,
  Star,
  X,
} from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
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
  { value: 'PLUMBING', label: 'Plumbing (Leaks, Pipes, Drains)' },
  { value: 'ELECTRICAL', label: 'Electrical (Lights, Power, Switches)' },
  { value: 'LIFT', label: 'Lift & Elevator' },
  { value: 'HOUSEKEEPING', label: 'Housekeeping & Cleaning' },
  { value: 'SECURITY', label: 'Security & Access' },
  { value: 'WATER_SUPPLY', label: 'Water Supply & Pressure' },
  { value: 'WASTE_MANAGEMENT', label: 'Waste Management & Chutes' },
  { value: 'STRUCTURAL', label: 'Structural, Seepage & Walls' },
  { value: 'COMMON_AREA', label: 'Common Amenities & Clubhouse' },
  { value: 'OTHER', label: 'Other Facilities' },
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

export const ResidentComplaints: React.FC = () => {
  const { memberships, selectedFlat } = useAuth();
  const queryClient = useQueryClient();

  const [activeTab, setActiveTab] = useState<'ALL' | 'ACTIVE' | 'RESOLVED'>('ALL');
  const [isRaiseModalOpen, setIsRaiseModalOpen] = useState(false);
  const [selectedComplaint, setSelectedComplaint] = useState<Complaint | null>(null);

  // Form states for raising complaint
  const [flatId, setFlatId] = useState<string>(selectedFlat?.flat_id || memberships[0]?.flat_id || '');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState<ComplaintCategory>('PLUMBING');
  const [subcategory, setSubcategory] = useState('');
  const [attachmentFile, setAttachmentFile] = useState<File | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  // Detail interaction states
  const [commentText, setCommentText] = useState('');
  const [ratingStars, setRatingStars] = useState<number>(5);
  const [feedbackText, setFeedbackText] = useState('');
  const [reopenReason, setReopenReason] = useState('');
  const [isReopenPromptOpen, setIsReopenPromptOpen] = useState(false);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Query resident complaints
  const { data: complaints = [], isLoading } = useQuery({
    queryKey: ['resident-complaints'],
    queryFn: () => complaintsService.listResidentComplaints(),
  });

  // Raise Complaint Mutation
  const createMutation = useMutation({
    mutationFn: async () => {
      if (!flatId) throw new Error('Please select an apartment flat.');
      if (title.trim().length < 3) throw new Error('Title must be at least 3 characters.');
      if (description.trim().length < 5) throw new Error('Description must be at least 5 characters.');

      const newComplaint = await complaintsService.createComplaint({
        flat_id: flatId,
        title: title.trim(),
        description: description.trim(),
        category,
        subcategory: subcategory.trim() || undefined,
      });

      if (attachmentFile) {
        await complaintsService.uploadAttachment(newComplaint.id, attachmentFile, false);
      }

      return newComplaint;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['resident-complaints'] });
      queryClient.invalidateQueries({ queryKey: ['resident-complaints-summary'] });
      queryClient.invalidateQueries({ queryKey: ['helpdesk-complaints'] });
      queryClient.invalidateQueries({ queryKey: ['helpdesk-dashboard-metrics'] });
      queryClient.invalidateQueries({ queryKey: ['helpdesk-safety-alerts'] });
      setIsRaiseModalOpen(false);
      setTitle('');
      setDescription('');
      setCategory('PLUMBING');
      setSubcategory('');
      setAttachmentFile(null);
      setFormError(null);
      setSelectedComplaint(data);
      setActionSuccess(`Complaint ${data.complaint_number} submitted successfully.`);
    },
    onError: (err: any) => {
      setFormError(err.message || 'Failed to submit complaint.');
    },
  });

  // Add Comment Mutation
  const commentMutation = useMutation({
    mutationFn: async () => {
      if (!selectedComplaint || !commentText.trim()) return;
      return complaintsService.addResidentComment(selectedComplaint.id, commentText.trim());
    },
    onSuccess: async () => {
      setCommentText('');
      if (selectedComplaint) {
        const updated = await complaintsService.getResidentComplaint(selectedComplaint.id);
        if (updated) setSelectedComplaint(updated);
        queryClient.invalidateQueries({ queryKey: ['resident-complaints'] });
        queryClient.invalidateQueries({ queryKey: ['helpdesk-complaints'] });
      }
    },
  });

  // Reopen Mutation
  const reopenMutation = useMutation({
    mutationFn: async () => {
      if (!selectedComplaint || !reopenReason.trim()) return;
      return complaintsService.reopenComplaint(selectedComplaint.id, reopenReason.trim());
    },
    onSuccess: (updated) => {
      if (updated) {
        setIsReopenPromptOpen(false);
        setReopenReason('');
        setSelectedComplaint(updated);
        queryClient.invalidateQueries({ queryKey: ['resident-complaints'] });
        queryClient.invalidateQueries({ queryKey: ['resident-complaints-summary'] });
        queryClient.invalidateQueries({ queryKey: ['helpdesk-complaints'] });
        queryClient.invalidateQueries({ queryKey: ['helpdesk-dashboard-metrics'] });
        setActionSuccess(`Ticket ${updated.complaint_number} reopened successfully.`);
      }
    },
    onError: (err: any) => {
      setActionError(err.message || 'Failed to reopen ticket.');
    },
  });

  // Rating Mutation
  const rateMutation = useMutation({
    mutationFn: async () => {
      if (!selectedComplaint) return;
      return complaintsService.rateComplaint(selectedComplaint.id, ratingStars, feedbackText.trim() || undefined);
    },
    onSuccess: (updated) => {
      if (updated) {
        setSelectedComplaint(updated);
        queryClient.invalidateQueries({ queryKey: ['resident-complaints'] });
        queryClient.invalidateQueries({ queryKey: ['helpdesk-complaints'] });
        setActionSuccess('Thank you for submitting your rating and feedback.');
      }
    },
    onError: (err: any) => {
      setActionError(err.message || 'Failed to record rating.');
    },
  });

  // Filter complaints
  const filteredComplaints = complaints.filter((c) => {
    if (activeTab === 'ACTIVE') {
      return !['RESOLVED', 'CLOSED', 'CANCELLED'].includes(c.status);
    }
    if (activeTab === 'RESOLVED') {
      return ['RESOLVED', 'CLOSED'].includes(c.status);
    }
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Header & Primary Action */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">Complaints & Helpdesk</h1>
          <p className="text-sm text-gray-500">
            Submit maintenance issues, track real-time resolution SLAs, and communicate with facility staff.
          </p>
        </div>
        <Button onClick={() => setIsRaiseModalOpen(true)} className="flex items-center gap-2">
          <Plus className="h-4 w-4" />
          Raise Complaint
        </Button>
      </div>

      {/* Emergency Advisory Banner */}
      <Alert variant="warning" className="flex items-start gap-3">
        <ShieldAlert className="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" />
        <div className="text-sm">
          <span className="font-semibold">Life-Threatening Emergency?</span> For immediate hazards like gas leaks,
          fire, sparking live wires, or trapped elevator passengers, call Township Security Control Room immediately or dial{' '}
          <strong className="underline">112</strong> / Fire: <strong className="underline">101</strong> / Ambulance:{' '}
          <strong className="underline">108</strong>.
        </div>
      </Alert>

      {/* Action Notices */}
      {actionSuccess && (
        <Alert variant="success" className="flex justify-between items-center">
          <span>{actionSuccess}</span>
          <button onClick={() => setActionSuccess(null)} className="text-green-600 hover:text-green-800">
            <X className="h-4 w-4" />
          </button>
        </Alert>
      )}
      {actionError && (
        <Alert variant="error" className="flex justify-between items-center">
          <span>{actionError}</span>
          <button onClick={() => setActionError(null)} className="text-red-600 hover:text-red-800">
            <X className="h-4 w-4" />
          </button>
        </Alert>
      )}

      {/* Tab Filter */}
      <div className="flex border-b border-gray-200">
        <button
          onClick={() => setActiveTab('ALL')}
          className={`py-2 px-4 text-sm font-medium border-b-2 -mb-px transition-colors ${
            activeTab === 'ALL'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          All Complaints ({complaints.length})
        </button>
        <button
          onClick={() => setActiveTab('ACTIVE')}
          className={`py-2 px-4 text-sm font-medium border-b-2 -mb-px transition-colors ${
            activeTab === 'ACTIVE'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          In Progress ({complaints.filter((c) => !['RESOLVED', 'CLOSED', 'CANCELLED'].includes(c.status)).length})
        </button>
        <button
          onClick={() => setActiveTab('RESOLVED')}
          className={`py-2 px-4 text-sm font-medium border-b-2 -mb-px transition-colors ${
            activeTab === 'RESOLVED'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          Resolved ({complaints.filter((c) => ['RESOLVED', 'CLOSED'].includes(c.status)).length})
        </button>
      </div>

      {/* Complaints List */}
      {isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : filteredComplaints.length === 0 ? (
        <Card className="text-center py-12">
          <CardContent className="space-y-3">
            <CheckCircle2 className="mx-auto h-12 w-12 text-gray-300" />
            <h3 className="text-base font-medium text-gray-900">No complaints found</h3>
            <p className="text-sm text-gray-500 max-w-sm mx-auto">
              You currently have no complaints in this category. Click &quot;Raise Complaint&quot; if you need assistance with
              your apartment or society amenities.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4">
          {filteredComplaints.map((c) => (
            <Card
              key={c.id}
              onClick={() => setSelectedComplaint(c)}
              className="hover:border-indigo-300 transition-all cursor-pointer border shadow-sm"
            >
              <CardContent className="p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs font-semibold text-gray-500">{c.complaint_number}</span>
                    <Badge variant={getStatusBadgeVariant(c.status)}>{c.status.replace('_', ' ')}</Badge>
                    <Badge variant={getPriorityBadgeVariant(c.priority)}>{c.priority}</Badge>
                    {c.safety_escalated && (
                      <Badge variant="danger" className="flex items-center gap-1">
                        <AlertTriangle className="h-3 w-3" /> Safety Critical
                      </Badge>
                    )}
                    <span className="text-xs text-gray-500 font-medium bg-gray-100 px-2 py-0.5 rounded">
                      {c.category}
                    </span>
                  </div>

                  <h3 className="text-base font-semibold text-gray-900">{c.title}</h3>
                  <p className="text-sm text-gray-600 line-clamp-1">{c.description}</p>

                  <div className="flex flex-wrap items-center gap-4 text-xs text-gray-500 pt-1">
                    <span>
                      Unit: {c.tower_number ? `Tower ${c.tower_number}` : ''} - Flat {c.flat_number || '—'}
                    </span>
                    <span>Submitted: {formatIST(c.created_at)}</span>
                    {c.assigned_to && <span>Assigned to: {c.assignee_name || 'Staff Member'}</span>}
                  </div>
                </div>

                <div className="flex flex-col md:items-end justify-between self-stretch gap-2 flex-shrink-0">
                  {c.is_sla_breached && (
                    <span className="text-xs font-medium text-red-600 flex items-center gap-1">
                      <Clock className="h-3.5 w-3.5" /> SLA Overdue
                    </span>
                  )}
                  {c.rating && (
                    <div className="flex items-center text-amber-500 text-xs font-semibold">
                      <Star className="h-3.5 w-3.5 fill-current mr-1" />
                      {c.rating}/5 Rated
                    </div>
                  )}
                  <Button variant="outline" size="sm" className="mt-auto">
                    View Details
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Raise Complaint Modal */}
      {isRaiseModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 overflow-y-auto">
          <div className="bg-white rounded-xl shadow-xl max-w-lg w-full max-h-[90vh] overflow-y-auto p-6 space-y-5">
            <div className="flex justify-between items-center border-b pb-3">
              <h2 className="text-lg font-bold text-gray-900">Raise Maintenance Complaint</h2>
              <button
                onClick={() => setIsRaiseModalOpen(false)}
                className="text-gray-400 hover:text-gray-600 rounded-lg p-1"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {formError && (
              <Alert variant="error">
                <span>{formError}</span>
              </Alert>
            )}

            <div className="space-y-4 text-sm">
              {/* Apartment Unit Selection */}
              <div>
                <label className="block font-medium text-gray-700 mb-1">Apartment Flat</label>
                <select
                  value={flatId}
                  onChange={(e) => setFlatId(e.target.value)}
                  className="w-full border rounded-lg p-2.5 bg-white text-gray-900 border-gray-300 focus:ring-2 focus:ring-indigo-500"
                >
                  {memberships.map((m) => (
                    <option key={m.flat_id} value={m.flat_id}>
                      Flat {m.flat_number || m.flat_id} {m.tower_number ? `(Tower ${m.tower_number})` : ''} -{' '}
                      {m.membership_type}
                    </option>
                  ))}
                </select>
              </div>

              {/* Category */}
              <div>
                <label className="block font-medium text-gray-700 mb-1">Category</label>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value as ComplaintCategory)}
                  className="w-full border rounded-lg p-2.5 bg-white text-gray-900 border-gray-300 focus:ring-2 focus:ring-indigo-500"
                >
                  {CATEGORIES.map((cat) => (
                    <option key={cat.value} value={cat.value}>
                      {cat.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Title */}
              <div>
                <label className="block font-medium text-gray-700 mb-1">Title</label>
                <input
                  type="text"
                  placeholder="Short summary (e.g., Washbasin drain clogged)"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  maxLength={255}
                  className="w-full border rounded-lg p-2.5 text-gray-900 border-gray-300 focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              {/* Description */}
              <div>
                <label className="block font-medium text-gray-700 mb-1">Detailed Description</label>
                <textarea
                  rows={4}
                  placeholder="Describe the issue, location inside flat, and when it started..."
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  maxLength={5000}
                  className="w-full border rounded-lg p-2.5 text-gray-900 border-gray-300 focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              {/* Photo Upload (Max 5MB) */}
              <div>
                <label className="block font-medium text-gray-700 mb-1">Attach Photo (Optional, Max 5MB)</label>
                <div className="flex items-center gap-3">
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    onChange={(e) => {
                      if (e.target.files && e.target.files[0]) {
                        const file = e.target.files[0];
                        if (file.size > 5 * 1024 * 1024) {
                          setFormError('File size exceeds the 5MB limit.');
                          return;
                        }
                        setAttachmentFile(file);
                        setFormError(null);
                      }
                    }}
                    className="text-xs text-gray-500 file:mr-3 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-xs file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100"
                  />
                  {attachmentFile && (
                    <button
                      type="button"
                      onClick={() => setAttachmentFile(null)}
                      className="text-gray-400 hover:text-red-500"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  )}
                </div>
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-3 border-t">
              <Button variant="outline" onClick={() => setIsRaiseModalOpen(false)}>
                Cancel
              </Button>
              <Button onClick={() => createMutation.mutate()} disabled={createMutation.isPending}>
                {createMutation.isPending ? 'Submitting...' : 'Submit Complaint'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Complaint Detail Drawer / Modal */}
      {selectedComplaint && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 overflow-y-auto">
          <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto p-6 space-y-6">
            {/* Header */}
            <div className="flex justify-between items-start border-b pb-4">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm font-bold text-gray-600">
                    {selectedComplaint.complaint_number}
                  </span>
                  <Badge variant={getStatusBadgeVariant(selectedComplaint.status)}>
                    {selectedComplaint.status.replace('_', ' ')}
                  </Badge>
                  <Badge variant={getPriorityBadgeVariant(selectedComplaint.priority)}>
                    {selectedComplaint.priority}
                  </Badge>
                </div>
                <h2 className="text-xl font-bold text-gray-900 mt-1">{selectedComplaint.title}</h2>
              </div>
              <button
                onClick={() => setSelectedComplaint(null)}
                className="text-gray-400 hover:text-gray-600 rounded-lg p-1"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Safety Warning if Escalated */}
            {selectedComplaint.safety_escalated && (
              <Alert variant="error" className="flex items-start gap-2">
                <AlertTriangle className="h-5 w-5 flex-shrink-0" />
                <div className="text-sm">
                  <strong>Safety Critical Incident:</strong> {selectedComplaint.safety_escalation_reason}. Township
                  quick-response team has been notified.
                </div>
              </Alert>
            )}

            {/* AI Triage Summary for Resident */}
            {selectedComplaint.ai_summary && (
              <div className="bg-indigo-50/60 border border-indigo-100 rounded-lg p-3 text-xs text-indigo-900 flex items-start gap-2">
                <Sparkles className="h-4 w-4 text-indigo-600 flex-shrink-0 mt-0.5" />
                <div>
                  <span className="font-semibold text-indigo-800">AI Triage Summary: </span>
                  <span className="text-gray-700">{selectedComplaint.ai_summary}</span>
                </div>
              </div>
            )}

            {/* Ticket Metadata Details */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 bg-gray-50 p-4 rounded-lg text-xs">
              <div>
                <span className="text-gray-500 block">Unit</span>
                <span className="font-semibold text-gray-800">
                  {selectedComplaint.tower_number ? `Tower ${selectedComplaint.tower_number}` : ''} - Flat{' '}
                  {selectedComplaint.flat_number}
                </span>
              </div>
              <div>
                <span className="text-gray-500 block">Assigned Staff</span>
                <span className="font-semibold text-gray-800">
                  {selectedComplaint.assignee_name || 'In Triage Queue'}
                </span>
              </div>
              <div>
                <span className="text-gray-500 block">Resolution SLA</span>
                <span className="font-semibold text-gray-800">
                  {formatIST(selectedComplaint.resolution_deadline)}
                </span>
              </div>
              <div>
                <span className="text-gray-500 block">Submitted</span>
                <span className="font-semibold text-gray-800">{formatIST(selectedComplaint.created_at)}</span>
              </div>
            </div>

            {/* Description */}
            <div>
              <h4 className="text-xs font-bold uppercase tracking-wider text-gray-500 mb-1">Description</h4>
              <p className="text-sm text-gray-800 bg-gray-50 p-3 rounded-lg whitespace-pre-wrap">
                {selectedComplaint.description}
              </p>
            </div>

            {/* Attachments */}
            {selectedComplaint.attachments.length > 0 && (
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-gray-500 mb-2">Photos / Attachments</h4>
                <div className="flex flex-wrap gap-3">
                  {selectedComplaint.attachments.map((att) => (
                    <a
                      key={att.id}
                      href={att.download_url}
                      target="_blank"
                      rel="noreferrer"
                      className="border rounded-lg p-2 text-xs text-indigo-600 hover:text-indigo-800 bg-gray-50 hover:bg-gray-100 flex items-center gap-2"
                    >
                      <FileText className="h-4 w-4" />
                      <span className="max-w-[150px] truncate">{att.file_name}</span>
                    </a>
                  ))}
                </div>
              </div>
            )}

            {/* Public Conversation Thread */}
            <div className="space-y-3">
              <h4 className="text-xs font-bold uppercase tracking-wider text-gray-500">Conversation & Updates</h4>
              <div className="space-y-2 max-h-48 overflow-y-auto p-1">
                {selectedComplaint.comments.length === 0 ? (
                  <p className="text-xs text-gray-400 italic">No messages yet.</p>
                ) : (
                  selectedComplaint.comments.map((comm) => (
                    <div
                      key={comm.id}
                      className={`p-3 rounded-lg text-xs space-y-1 ${
                        comm.user_role === 'HELPDESK' ? 'bg-indigo-50 border border-indigo-100' : 'bg-gray-100'
                      }`}
                    >
                      <div className="flex justify-between font-semibold text-gray-700">
                        <span>{comm.user_name || 'Resident'}</span>
                        <span className="text-gray-400 font-normal">{formatIST(comm.created_at)}</span>
                      </div>
                      <p className="text-gray-800">{comm.comment}</p>
                    </div>
                  ))
                )}
              </div>

              {/* Send Comment Box */}
              <div className="flex gap-2">
                <input
                  type="text"
                  placeholder="Add a reply or extra details..."
                  value={commentText}
                  onChange={(e) => setCommentText(e.target.value)}
                  className="flex-1 border rounded-lg px-3 py-2 text-xs border-gray-300 focus:ring-1 focus:ring-indigo-500"
                />
                <Button
                  size="sm"
                  onClick={() => commentMutation.mutate()}
                  disabled={commentMutation.isPending || !commentText.trim()}
                >
                  <Send className="h-3.5 w-3.5 mr-1" /> Send
                </Button>
              </div>
            </div>

            {/* Satisfaction Rating & Feedback (If Resolved or Closed) */}
            {['RESOLVED', 'CLOSED'].includes(selectedComplaint.status) && (
              <div className="border-t pt-4 space-y-3">
                <h4 className="text-sm font-bold text-gray-800">Resolution Feedback & Satisfaction</h4>
                {selectedComplaint.rating ? (
                  <div className="bg-amber-50 p-3 rounded-lg border border-amber-200 text-xs text-amber-900 space-y-1">
                    <div className="flex items-center gap-1 font-semibold">
                      <Star className="h-4 w-4 fill-amber-500 text-amber-500" />
                      Rated {selectedComplaint.rating} of 5 Stars
                    </div>
                    {selectedComplaint.feedback && <p>&quot;{selectedComplaint.feedback}&quot;</p>}
                  </div>
                ) : (
                  <div className="bg-gray-50 p-4 rounded-lg space-y-3 text-xs">
                    <p className="text-gray-600">How satisfied are you with the resolution of this issue?</p>
                    <div className="flex gap-2">
                      {[1, 2, 3, 4, 5].map((star) => (
                        <button
                          key={star}
                          type="button"
                          onClick={() => setRatingStars(star)}
                          className={`p-1 rounded ${
                            ratingStars >= star ? 'text-amber-500' : 'text-gray-300'
                          } hover:text-amber-400`}
                        >
                          <Star className="h-6 w-6 fill-current" />
                        </button>
                      ))}
                    </div>
                    <input
                      type="text"
                      placeholder="Optional feedback for technician..."
                      value={feedbackText}
                      onChange={(e) => setFeedbackText(e.target.value)}
                      className="w-full border rounded-lg p-2 text-xs border-gray-300"
                    />
                    <Button size="sm" onClick={() => rateMutation.mutate()} disabled={rateMutation.isPending}>
                      Submit Feedback
                    </Button>
                  </div>
                )}

                {/* 7-Day Reopen Option */}
                <div className="pt-2 flex justify-between items-center text-xs">
                  <span className="text-gray-500">Issue recurred or not resolved properly?</span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setIsReopenPromptOpen(true)}
                    className="text-red-600 border-red-200 hover:bg-red-50"
                  >
                    <RefreshCw className="h-3.5 w-3.5 mr-1" /> Reopen Ticket
                  </Button>
                </div>

                {isReopenPromptOpen && (
                  <div className="p-3 bg-red-50 border border-red-200 rounded-lg space-y-2 text-xs">
                    <label className="font-semibold text-red-800">State reason for reopening ticket:</label>
                    <input
                      type="text"
                      placeholder="e.g., Faucet started leaking again this morning"
                      value={reopenReason}
                      onChange={(e) => setReopenReason(e.target.value)}
                      className="w-full border rounded p-2 border-red-300 text-xs"
                    />
                    <div className="flex justify-end gap-2">
                      <Button size="sm" variant="outline" onClick={() => setIsReopenPromptOpen(false)}>
                        Cancel
                      </Button>
                      <Button
                        size="sm"
                        onClick={() => reopenMutation.mutate()}
                        disabled={reopenMutation.isPending || !reopenReason.trim()}
                        className="bg-red-600 hover:bg-red-700 text-white"
                      >
                        Confirm Reopen
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
