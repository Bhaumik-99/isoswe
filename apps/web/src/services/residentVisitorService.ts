import { apiClient } from './apiClient';
import {
  CreateGuestPassPayload,
  GuestPass,
  VisitorPhotoUrlResponse,
  VisitorRecord,
} from '../types';
import { formatPhoneToE164 } from './gateService';

export const residentVisitorService = {
  async listPendingVisitors(): Promise<VisitorRecord[]> {
    return apiClient.get<VisitorRecord[]>('/api/v1/resident/visitors/pending');
  },

  async actOnVisitor(
    visitorId: string,
    action: 'APPROVE' | 'REJECT',
    reason?: string
  ): Promise<{
    visitor_id: string;
    approval_status: string;
    approved_at: string | null;
    action_by_user_id: string;
  }> {
    return apiClient.post(`/api/v1/resident/visitors/${visitorId}/action`, {
      action,
      reason: reason?.trim() || undefined,
    });
  },

  async listTodayVisitors(): Promise<VisitorRecord[]> {
    return apiClient.get<VisitorRecord[]>('/api/v1/resident/visitors/today');
  },

  async listVisitorHistory(limit = 20, offset = 0): Promise<VisitorRecord[]> {
    const query = new URLSearchParams({
      limit: String(Math.min(limit, 50)),
      offset: String(offset),
    });
    return apiClient.get<VisitorRecord[]>(`/api/v1/resident/visitors/history?${query.toString()}`);
  },

  async getVisitorPhotoUrl(visitorId: string): Promise<VisitorPhotoUrlResponse> {
    return apiClient.get<VisitorPhotoUrlResponse>(`/api/v1/resident/visitors/${visitorId}/photo`);
  },

  async createGuestPass(payload: CreateGuestPassPayload): Promise<GuestPass> {
    return apiClient.post<GuestPass>('/api/v1/resident/passes', {
      ...payload,
      guest_name: payload.guest_name.trim(),
      guest_phone: payload.guest_phone?.trim()
        ? formatPhoneToE164(payload.guest_phone)
        : undefined,
      purpose: payload.purpose.trim(),
    });
  },

  async listGuestPasses(): Promise<GuestPass[]> {
    return apiClient.get<GuestPass[]>('/api/v1/resident/passes');
  },

  async revokeGuestPass(passId: string, reason?: string): Promise<GuestPass> {
    return apiClient.post<GuestPass>(`/api/v1/resident/passes/${passId}/revoke`, {
      reason: reason || 'Revoked by resident',
    });
  },
};

