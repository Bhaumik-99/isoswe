/**
 * Complaints & Helpdesk Operations API Service
 */

import {
  AssignComplaintRequest,
  Complaint,
  ComplaintAttachment,
  ComplaintCategory,
  ComplaintComment,
  ComplaintPriority,
  ComplaintStatus,
  CreateCommentRequest,
  CreateComplaintRequest,
  HelpdeskDashboardMetrics,
  HelpdeskQueryParams,
  InitiateAttachmentUploadRequest,
  PresignedUploadResponse,
  RateComplaintRequest,
  ReopenComplaintRequest,
  SafetyAlert,
  UpdateComplaintPriorityRequest,
  UpdateComplaintStatusRequest,
} from '../types';
import { apiClient } from './apiClient';

export const complaintsService = {
  // =========================================================================
  // Resident Operations
  // =========================================================================

  async createComplaint(payload: CreateComplaintRequest): Promise<Complaint> {
    return apiClient.request<Complaint>('/api/v1/complaints', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async listResidentComplaints(status?: ComplaintStatus): Promise<Complaint[]> {
    const query = status ? `?status=${encodeURIComponent(status)}` : '';
    return apiClient.request<Complaint[]>(`/api/v1/complaints/me${query}`);
  },

  async getResidentComplaint(complaintId: string): Promise<Complaint> {
    return apiClient.request<Complaint>(`/api/v1/complaints/me/${complaintId}`);
  },

  async addResidentComment(complaintId: string, comment: string): Promise<ComplaintComment> {
    const payload: CreateCommentRequest = { comment, is_internal: false };
    return apiClient.request<ComplaintComment>(`/api/v1/complaints/me/${complaintId}/comments`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async reopenComplaint(complaintId: string, reason: string): Promise<Complaint> {
    const payload: ReopenComplaintRequest = { reason };
    return apiClient.request<Complaint>(`/api/v1/complaints/me/${complaintId}/reopen`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async rateComplaint(complaintId: string, rating: number, feedback?: string): Promise<Complaint> {
    const payload: RateComplaintRequest = { rating, feedback };
    return apiClient.request<Complaint>(`/api/v1/complaints/me/${complaintId}/rating`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  // =========================================================================
  // Helpdesk Staff Operations
  // =========================================================================

  async getHelpdeskDashboardMetrics(societyId?: string): Promise<HelpdeskDashboardMetrics> {
    const query = societyId ? `?society_id=${encodeURIComponent(societyId)}` : '';
    return apiClient.request<HelpdeskDashboardMetrics>(`/api/v1/complaints/helpdesk/dashboard${query}`);
  },

  async listHelpdeskComplaints(params: HelpdeskQueryParams = {}): Promise<Complaint[]> {
    const searchParams = new URLSearchParams();
    if (params.society_id) searchParams.set('society_id', params.society_id);
    if (params.assigned_to) searchParams.set('assigned_to', params.assigned_to);
    if (params.unassigned_only) searchParams.set('unassigned_only', 'true');
    if (params.priority) searchParams.set('priority', params.priority);
    if (params.category) searchParams.set('category', params.category);
    if (params.tower_id) searchParams.set('tower_id', params.tower_id);
    if (params.search) searchParams.set('search', params.search);
    if (params.is_sla_breached) searchParams.set('is_sla_breached', 'true');
    if (params.limit) searchParams.set('limit', String(params.limit));
    if (params.offset) searchParams.set('offset', String(params.offset));
    if (params.status && params.status.length > 0) {
      params.status.forEach((st) => searchParams.append('status', st));
    }

    const queryStr = searchParams.toString();
    const endpoint = `/api/v1/complaints/helpdesk${queryStr ? `?${queryStr}` : ''}`;
    return apiClient.request<Complaint[]>(endpoint);
  },

  async getHelpdeskComplaint(complaintId: string): Promise<Complaint> {
    return apiClient.request<Complaint>(`/api/v1/complaints/helpdesk/${complaintId}`);
  },

  async updateComplaintStatus(
    complaintId: string,
    status: ComplaintStatus,
    notes?: string
  ): Promise<Complaint> {
    const payload: UpdateComplaintStatusRequest = { status, notes };
    return apiClient.request<Complaint>(`/api/v1/complaints/helpdesk/${complaintId}/status`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  },

  async assignComplaint(complaintId: string, assignedTo: string, notes?: string): Promise<Complaint> {
    const payload: AssignComplaintRequest = { assigned_to: assignedTo, notes };
    return apiClient.request<Complaint>(`/api/v1/complaints/helpdesk/${complaintId}/assign`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  },

  async updateComplaintPriority(
    complaintId: string,
    priority: ComplaintPriority,
    reason?: string
  ): Promise<Complaint> {
    const payload: UpdateComplaintPriorityRequest = { priority, reason };
    return apiClient.request<Complaint>(`/api/v1/complaints/helpdesk/${complaintId}/priority`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  },

  async addHelpdeskComment(
    complaintId: string,
    comment: string,
    isInternal = false
  ): Promise<ComplaintComment> {
    const payload: CreateCommentRequest = { comment, is_internal: isInternal };
    return apiClient.request<ComplaintComment>(`/api/v1/complaints/helpdesk/${complaintId}/comments`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  // =========================================================================
  // Attachments Upload
  // =========================================================================

  async completeAttachmentUpload(
    complaintId: string,
    attachmentId: string,
    isStaff = false
  ): Promise<ComplaintAttachment> {
    const endpoint = isStaff
      ? `/api/v1/complaints/helpdesk/${complaintId}/attachments/${attachmentId}/complete`
      : `/api/v1/complaints/me/${complaintId}/attachments/${attachmentId}/complete`;
    return apiClient.request<ComplaintAttachment>(endpoint, {
      method: 'POST',
    });
  },

  async uploadAttachment(
    complaintId: string,
    file: File,
    isStaff = false
  ): Promise<ComplaintAttachment> {
    const initiatePayload: InitiateAttachmentUploadRequest = {
      file_name: file.name,
      file_size_bytes: file.size,
      content_type: file.type,
    };

    const endpoint = isStaff
      ? `/api/v1/complaints/helpdesk/${complaintId}/attachments`
      : `/api/v1/complaints/me/${complaintId}/attachments`;

    const presigned = await apiClient.request<PresignedUploadResponse>(endpoint, {
      method: 'POST',
      body: JSON.stringify(initiatePayload),
    });

    // Upload directly to presigned URL (simulate in dev for mock-storage.local)
    const isMockUrl = presigned.upload_url.includes('mock-storage.local');
    if (!isMockUrl) {
      const uploadRes = await fetch(presigned.upload_url, {
        method: 'PUT',
        body: file,
        headers: {
          'Content-Type': file.type,
        },
      });

      if (!uploadRes.ok) {
        throw new Error(
          `Attachment upload failed: Storage server responded with status ${uploadRes.status} (${uploadRes.statusText || 'Upload Rejected'})`
        );
      }
    }

    return this.completeAttachmentUpload(complaintId, presigned.attachment_id, isStaff);
  },

  // =========================================================================
  // Phase 5 Complaint Governance & Safety Alerts
  // =========================================================================

  async correctCategory(
    complaintId: string,
    newCategory: ComplaintCategory,
    reason?: string
  ): Promise<Complaint> {
    return apiClient.request<Complaint>(`/api/v1/complaints/${complaintId}/category`, {
      method: 'PATCH',
      body: JSON.stringify({
        new_category: newCategory,
        reason,
      }),
    });
  },

  async linkDuplicate(
    complaintId: string,
    primaryComplaintId: string,
    reason?: string
  ): Promise<Complaint> {
    return apiClient.request<Complaint>(`/api/v1/complaints/${complaintId}/link-duplicate`, {
      method: 'POST',
      body: JSON.stringify({
        primary_complaint_id: primaryComplaintId,
        reason,
      }),
    });
  },

  async unlinkDuplicate(complaintId: string): Promise<Complaint> {
    return apiClient.request<Complaint>(`/api/v1/complaints/${complaintId}/unlink-duplicate`, {
      method: 'POST',
    });
  },

  async getLinkedDuplicates(complaintId: string): Promise<Complaint[]> {
    return apiClient.request<Complaint[]>(`/api/v1/complaints/${complaintId}/linked-duplicates`);
  },

  async getSafetyAlerts(unreadOnly = true): Promise<SafetyAlert[]> {
    return apiClient.request<SafetyAlert[]>(
      `/api/v1/complaints/safety-alerts?unread_only=${unreadOnly}`
    );
  },

  async acknowledgeSafetyAlert(alertId: string, notes?: string): Promise<SafetyAlert> {
    return apiClient.request<SafetyAlert>(`/api/v1/complaints/safety-alerts/${alertId}/ack`, {
      method: 'POST',
      body: JSON.stringify({
        notes: notes || 'Acknowledged by duty manager',
      }),
    });
  },
};
