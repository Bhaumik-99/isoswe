/**
 * Complaints Domain TypeScript Interfaces
 *
 * Models resident tickets, SLA targets, AI triage recommendations,
 * attachments, comments, and helpdesk KPI metrics.
 */

export type ComplaintStatus =
  | 'SUBMITTED'
  | 'TRIAGED'
  | 'ASSIGNED'
  | 'IN_PROGRESS'
  | 'AWAITING_RESIDENT'
  | 'RESOLVED'
  | 'CLOSED'
  | 'REOPENED'
  | 'CANCELLED';

export type ComplaintPriority = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export type ComplaintCategory =
  | 'PLUMBING'
  | 'ELECTRICAL'
  | 'HOUSEKEEPING'
  | 'LIFT'
  | 'SECURITY'
  | 'WATER_SUPPLY'
  | 'WASTE_MANAGEMENT'
  | 'COMMON_AREA'
  | 'STRUCTURAL'
  | 'OTHER';

export interface ComplaintAttachment {
  id: string;
  complaint_id: string;
  file_name: string;
  file_size_bytes: number;
  content_type: string;
  download_url: string;
  uploaded_by: string;
  uploader_name?: string | null;
  created_at: string;
}

export interface ComplaintComment {
  id: string;
  complaint_id: string;
  user_id: string;
  user_name?: string | null;
  user_role?: string | null;
  comment: string;
  is_internal: boolean;
  created_at: string;
}

export interface ComplaintActivity {
  id: string;
  complaint_id: string;
  actor_id?: string | null;
  actor_name?: string | null;
  activity_type: string;
  old_value?: string | null;
  new_value?: string | null;
  notes?: string | null;
  created_at: string;
}

export interface Complaint {
  id: string;
  society_id: string;
  flat_id: string;
  tower_number?: string | null;
  flat_number?: string | null;
  created_by: string;
  creator_name?: string | null;
  assigned_to?: string | null;
  assignee_name?: string | null;
  complaint_number: string;
  category: ComplaintCategory;
  subcategory?: string | null;
  title: string;
  description: string;
  priority: ComplaintPriority;
  status: ComplaintStatus;

  // AI Suggestions
  ai_suggested_category?: ComplaintCategory | null;
  ai_suggested_priority?: ComplaintPriority | null;
  ai_confidence_score?: number | null;
  ai_summary?: string | null;
  ai_urgency_reason?: string | null;

  // Safety Escalation
  safety_escalated: boolean;
  safety_escalation_reason?: string | null;

  // Duplicate Tracking
  duplicate_of_id?: string | null;
  duplicate_candidates: string[];

  // SLA Tracking
  first_response_deadline?: string | null;
  resolution_deadline?: string | null;
  first_response_at?: string | null;
  resolved_at?: string | null;
  closed_at?: string | null;
  reopened_at?: string | null;
  reopened_count: number;
  is_sla_breached: boolean;

  // Rating & Feedback
  rating?: number | null;
  feedback?: string | null;

  // Child collections
  attachments: ComplaintAttachment[];
  comments: ComplaintComment[];
  activities: ComplaintActivity[];

  created_at: string;
  updated_at: string;
}

export interface CreateComplaintRequest {
  flat_id: string;
  title: string;
  description: string;
  category: ComplaintCategory;
  subcategory?: string;
}

export interface UpdateComplaintStatusRequest {
  status: ComplaintStatus;
  notes?: string;
}

export interface AssignComplaintRequest {
  assigned_to: string;
  notes?: string;
}

export interface UpdateComplaintPriorityRequest {
  priority: ComplaintPriority;
  reason?: string;
}

export interface CreateCommentRequest {
  comment: string;
  is_internal?: boolean;
}

export interface RateComplaintRequest {
  rating: number;
  feedback?: string;
}

export interface ReopenComplaintRequest {
  reason: string;
}

export interface InitiateAttachmentUploadRequest {
  file_name: string;
  file_size_bytes: number;
  content_type: string;
}

export interface PresignedUploadResponse {
  attachment_id: string;
  upload_url: string;
  storage_key: string;
  expires_in_seconds: number;
}

export interface HelpdeskDashboardMetrics {
  total_complaints: number;
  unassigned_count: number;
  in_progress_count: number;
  critical_count: number;
  overdue_count: number;
  resolved_count: number;
  average_first_response_minutes: number;
  average_resolution_minutes: number;
  resolution_rate_percentage: number;
}

export interface HelpdeskQueryParams {
  society_id?: string;
  assigned_to?: string;
  unassigned_only?: boolean;
  status?: ComplaintStatus[];
  priority?: ComplaintPriority;
  category?: ComplaintCategory;
  tower_id?: string;
  search?: string;
  is_sla_breached?: boolean;
  limit?: number;
  offset?: number;
}
