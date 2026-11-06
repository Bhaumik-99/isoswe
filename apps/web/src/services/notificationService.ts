import { apiClient } from './apiClient';
import {
  MarkAllReadResponse,
  MarkReadResponse,
  NotificationPreferences,
  PaginatedNotifications,
  StaffNotificationOverview,
  UnreadCountResponse,
  UpdateNotificationPreferencesPayload,
} from '../types';

export const notificationService = {
  async getMyNotifications(
    page = 1,
    pageSize = 20,
    unreadOnly = false,
    societyId?: string
  ): Promise<PaginatedNotifications> {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
      unread_only: String(unreadOnly),
    });
    if (societyId) {
      params.append('society_id', societyId);
    }
    return apiClient.get<PaginatedNotifications>(`/api/v1/notifications/me?${params.toString()}`);
  },

  async getUnreadCount(societyId?: string): Promise<UnreadCountResponse> {
    const params = new URLSearchParams();
    if (societyId) {
      params.append('society_id', societyId);
    }
    const query = params.toString() ? `?${params.toString()}` : '';
    return apiClient.get<UnreadCountResponse>(`/api/v1/notifications/me/unread-count${query}`);
  },

  async markAsRead(notificationId: string, societyId?: string): Promise<MarkReadResponse> {
    const params = new URLSearchParams();
    if (societyId) {
      params.append('society_id', societyId);
    }
    const query = params.toString() ? `?${params.toString()}` : '';
    return apiClient.patch<MarkReadResponse>(`/api/v1/notifications/me/${notificationId}/read${query}`);
  },

  async markAllAsRead(societyId?: string): Promise<MarkAllReadResponse> {
    const params = new URLSearchParams();
    if (societyId) {
      params.append('society_id', societyId);
    }
    const query = params.toString() ? `?${params.toString()}` : '';
    return apiClient.patch<MarkAllReadResponse>(`/api/v1/notifications/me/read-all${query}`);
  },

  async getPreferences(societyId?: string): Promise<NotificationPreferences> {
    const params = new URLSearchParams();
    if (societyId) {
      params.append('society_id', societyId);
    }
    const query = params.toString() ? `?${params.toString()}` : '';
    return apiClient.get<NotificationPreferences>(`/api/v1/notifications/me/preferences${query}`);
  },

  async updatePreferences(
    payload: UpdateNotificationPreferencesPayload,
    societyId?: string
  ): Promise<NotificationPreferences> {
    const params = new URLSearchParams();
    if (societyId) {
      params.append('society_id', societyId);
    }
    const query = params.toString() ? `?${params.toString()}` : '';
    return apiClient.put<NotificationPreferences>(`/api/v1/notifications/me/preferences${query}`, payload);
  },

  async getStaffOverview(
    page = 1,
    pageSize = 20,
    societyId?: string
  ): Promise<StaffNotificationOverview> {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });
    if (societyId) {
      params.append('society_id', societyId);
    }
    return apiClient.get<StaffNotificationOverview>(`/api/v1/notifications/staff/overview?${params.toString()}`);
  },
};
