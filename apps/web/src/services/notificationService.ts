import { apiClient } from './apiClient';
import {
  CreateNoticePayload,
  MarkAllNoticesReadResponse,
  MarkAllReadResponse,
  MarkNoticeReadResponse,
  MarkReadResponse,
  NoticeCategory,
  NoticeItem,
  NoticeStatus,
  NoticeTargetType,
  NotificationPreferences,
  PaginatedNotices,
  PaginatedNotifications,
  StaffNotificationOverview,
  UnreadCountResponse,
  UpdateNoticePayload,
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

  // ---------------------------------------------------------------------------
  // Resident Official Notices Feed & Read Tracking
  // ---------------------------------------------------------------------------

  async getResidentNotices(
    page = 1,
    pageSize = 20,
    category?: NoticeCategory,
    unreadOnly = false,
    societyId?: string
  ): Promise<PaginatedNotices> {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
      unread_only: String(unreadOnly),
    });
    if (category) {
      params.append('category', category);
    }
    if (societyId) {
      params.append('society_id', societyId);
    }
    return apiClient.get<PaginatedNotices>(`/api/v1/notifications/resident/notices?${params.toString()}`);
  },

  async getResidentNotice(noticeId: string, societyId?: string): Promise<NoticeItem> {
    const params = new URLSearchParams();
    if (societyId) {
      params.append('society_id', societyId);
    }
    const query = params.toString() ? `?${params.toString()}` : '';
    return apiClient.get<NoticeItem>(`/api/v1/notifications/resident/notices/${noticeId}${query}`);
  },

  async markNoticeAsRead(noticeId: string, societyId?: string): Promise<MarkNoticeReadResponse> {
    const params = new URLSearchParams();
    if (societyId) {
      params.append('society_id', societyId);
    }
    const query = params.toString() ? `?${params.toString()}` : '';
    return apiClient.patch<MarkNoticeReadResponse>(`/api/v1/notifications/resident/notices/${noticeId}/read${query}`);
  },

  async markAllNoticesAsRead(societyId?: string): Promise<MarkAllNoticesReadResponse> {
    const params = new URLSearchParams();
    if (societyId) {
      params.append('society_id', societyId);
    }
    const query = params.toString() ? `?${params.toString()}` : '';
    return apiClient.patch<MarkAllNoticesReadResponse>(`/api/v1/notifications/resident/notices/read-all${query}`);
  },

  // ---------------------------------------------------------------------------
  // Staff Official Notice Management
  // ---------------------------------------------------------------------------

  async getStaffNotices(
    page = 1,
    pageSize = 20,
    status?: NoticeStatus,
    category?: NoticeCategory,
    targetType?: NoticeTargetType,
    search?: string,
    societyId?: string
  ): Promise<PaginatedNotices> {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });
    if (status) {
      params.append('status', status);
    }
    if (category) {
      params.append('category', category);
    }
    if (targetType) {
      params.append('target_type', targetType);
    }
    if (search) {
      params.append('search', search);
    }
    if (societyId) {
      params.append('society_id', societyId);
    }
    return apiClient.get<PaginatedNotices>(`/api/v1/notifications/staff/notices?${params.toString()}`);
  },

  async getStaffNotice(noticeId: string, societyId?: string): Promise<NoticeItem> {
    const params = new URLSearchParams();
    if (societyId) {
      params.append('society_id', societyId);
    }
    const query = params.toString() ? `?${params.toString()}` : '';
    return apiClient.get<NoticeItem>(`/api/v1/notifications/staff/notices/${noticeId}${query}`);
  },

  async createStaffNotice(payload: CreateNoticePayload, societyId?: string): Promise<NoticeItem> {
    const params = new URLSearchParams();
    if (societyId) {
      params.append('society_id', societyId);
    }
    const query = params.toString() ? `?${params.toString()}` : '';
    return apiClient.post<NoticeItem>(`/api/v1/notifications/staff/notices${query}`, payload);
  },

  async updateStaffNotice(
    noticeId: string,
    payload: UpdateNoticePayload,
    societyId?: string
  ): Promise<NoticeItem> {
    const params = new URLSearchParams();
    if (societyId) {
      params.append('society_id', societyId);
    }
    const query = params.toString() ? `?${params.toString()}` : '';
    return apiClient.put<NoticeItem>(`/api/v1/notifications/staff/notices/${noticeId}${query}`, payload);
  },

  async publishStaffNotice(noticeId: string, societyId?: string): Promise<NoticeItem> {
    const params = new URLSearchParams();
    if (societyId) {
      params.append('society_id', societyId);
    }
    const query = params.toString() ? `?${params.toString()}` : '';
    return apiClient.post<NoticeItem>(`/api/v1/notifications/staff/notices/${noticeId}/publish${query}`);
  },

  async archiveStaffNotice(noticeId: string, societyId?: string): Promise<NoticeItem> {
    const params = new URLSearchParams();
    if (societyId) {
      params.append('society_id', societyId);
    }
    const query = params.toString() ? `?${params.toString()}` : '';
    return apiClient.post<NoticeItem>(`/api/v1/notifications/staff/notices/${noticeId}/archive${query}`);
  },
};
