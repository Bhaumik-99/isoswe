import { apiClient } from './apiClient';
import {
  CreateNoticePayload,
  FlatOption,
  MarkAllNoticesReadResponse,
  MarkAllReadResponse,
  MarkNoticeReadResponse,
  MarkReadResponse,
  NoticeCategory,
  NoticeItem,
  NoticeOverviewStats,
  NoticeStatus,
  NoticeTargetingOptionsResponse,
  NoticeTargetType,
  NotificationPreferences,
  PaginatedNotices,
  PaginatedNotifications,
  PublishNoticePayload,
  StaffNotificationOverview,
  TowerOption,
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

  async getResidentNoticesUnreadCount(societyId?: string): Promise<{ unread_count: number }> {
    const params = new URLSearchParams();
    if (societyId) {
      params.append('society_id', societyId);
    }
    const query = params.toString() ? `?${params.toString()}` : '';
    return apiClient.get<{ unread_count: number }>(`/api/v1/notifications/resident/notices/unread-count${query}`);
  },

  // ---------------------------------------------------------------------------
  // Staff Official Notice Management
  // ---------------------------------------------------------------------------

  async getStaffNoticesOverview(societyId?: string): Promise<NoticeOverviewStats> {
    const params = new URLSearchParams();
    if (societyId) {
      params.append('society_id', societyId);
    }
    const query = params.toString() ? `?${params.toString()}` : '';
    return apiClient.get<NoticeOverviewStats>(`/api/v1/notifications/staff/notices/overview${query}`);
  },

  async triggerPublishScheduledNotices(societyId?: string): Promise<NoticeItem[]> {
    const params = new URLSearchParams();
    if (societyId) {
      params.append('society_id', societyId);
    }
    const query = params.toString() ? `?${params.toString()}` : '';
    return apiClient.post<NoticeItem[]>(`/api/v1/notifications/staff/notices/publish-scheduled${query}`);
  },

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

  async publishStaffNotice(
    noticeId: string,
    payloadOrSocietyId?: PublishNoticePayload | string,
    societyId?: string
  ): Promise<NoticeItem> {
    let payload: PublishNoticePayload | undefined;
    let socId = societyId;
    if (typeof payloadOrSocietyId === 'string') {
      socId = payloadOrSocietyId;
    } else if (payloadOrSocietyId && typeof payloadOrSocietyId === 'object') {
      payload = payloadOrSocietyId;
    }
    const params = new URLSearchParams();
    if (socId) {
      params.append('society_id', socId);
    }
    const query = params.toString() ? `?${params.toString()}` : '';
    const url = `/api/v1/notifications/staff/notices/${noticeId}/publish${query}`;
    return payload !== undefined
      ? apiClient.post<NoticeItem>(url, payload)
      : apiClient.post<NoticeItem>(url);
  },

  async archiveStaffNotice(noticeId: string, societyId?: string): Promise<NoticeItem> {
    const params = new URLSearchParams();
    if (societyId) {
      params.append('society_id', societyId);
    }
    const query = params.toString() ? `?${params.toString()}` : '';
    return apiClient.post<NoticeItem>(`/api/v1/notifications/staff/notices/${noticeId}/archive${query}`);
  },

  async getStaffTowers(societyId?: string): Promise<TowerOption[]> {
    const params = new URLSearchParams();
    if (societyId) {
      params.append('society_id', societyId);
    }
    const query = params.toString() ? `?${params.toString()}` : '';
    return apiClient.get<TowerOption[]>(`/api/v1/notifications/staff/towers${query}`);
  },

  async getStaffFlats(
    towerId?: string,
    search?: string,
    societyId?: string
  ): Promise<FlatOption[]> {
    const params = new URLSearchParams();
    if (towerId) {
      params.append('tower_id', towerId);
    }
    if (search) {
      params.append('search', search);
    }
    if (societyId) {
      params.append('society_id', societyId);
    }
    const query = params.toString() ? `?${params.toString()}` : '';
    return apiClient.get<FlatOption[]>(`/api/v1/notifications/staff/flats${query}`);
  },

  async getStaffTargetingOptions(societyId?: string): Promise<NoticeTargetingOptionsResponse> {
    const params = new URLSearchParams();
    if (societyId) {
      params.append('society_id', societyId);
    }
    const query = params.toString() ? `?${params.toString()}` : '';
    return apiClient.get<NoticeTargetingOptionsResponse>(
      `/api/v1/notifications/staff/targeting-options${query}`
    );
  },
};
