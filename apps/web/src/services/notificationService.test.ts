import { describe, it, expect, vi, beforeEach } from 'vitest';
import { notificationService } from './notificationService';
import { apiClient } from './apiClient';

describe('Notification Service API Client Integration', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches paginated notifications inbox with filters', async () => {
    const getSpy = vi.spyOn(apiClient, 'get').mockResolvedValue({
      items: [
        {
          id: 'n-1',
          society_id: 'soc-1',
          recipient_user_id: 'user-1',
          event_type: 'billing.invoice_generated',
          title: 'Invoice Generated',
          body: 'Your maintenance invoice is ready',
          channel: 'IN_APP',
          priority: 'NORMAL',
          read_at: null,
          created_at: new Date().toISOString(),
        },
      ],
      total: 1,
      page: 1,
      page_size: 15,
      total_pages: 1,
      unread_count: 1,
    });

    const res = await notificationService.getMyNotifications(1, 15, true, 'soc-1');

    expect(getSpy).toHaveBeenCalledTimes(1);
    const calledUrl = getSpy.mock.calls[0][0];
    expect(calledUrl).toContain('/api/v1/notifications/me?');
    expect(calledUrl).toContain('page=1');
    expect(calledUrl).toContain('page_size=15');
    expect(calledUrl).toContain('unread_only=true');
    expect(calledUrl).toContain('society_id=soc-1');
    expect(res.total).toBe(1);
    expect(res.unread_count).toBe(1);
  });

  it('fetches unread badge count', async () => {
    const getSpy = vi.spyOn(apiClient, 'get').mockResolvedValue({ unread_count: 5 });

    const res = await notificationService.getUnreadCount('soc-1');

    expect(getSpy).toHaveBeenCalledWith('/api/v1/notifications/me/unread-count?society_id=soc-1');
    expect(res.unread_count).toBe(5);
  });

  it('marks a single notification as read', async () => {
    const patchSpy = vi.spyOn(apiClient, 'patch').mockResolvedValue({
      notification_id: 'n-123',
      read_at: new Date().toISOString(),
      status: 'success',
    });

    const res = await notificationService.markAsRead('n-123');

    expect(patchSpy).toHaveBeenCalledWith('/api/v1/notifications/me/n-123/read');
    expect(res.status).toBe('success');
    expect(res.notification_id).toBe('n-123');
  });

  it('marks all notifications as read', async () => {
    const patchSpy = vi.spyOn(apiClient, 'patch').mockResolvedValue({
      marked_count: 7,
      status: 'success',
    });

    const res = await notificationService.markAllAsRead('soc-1');

    expect(patchSpy).toHaveBeenCalledWith('/api/v1/notifications/me/read-all?society_id=soc-1');
    expect(res.marked_count).toBe(7);
  });

  it('retrieves and updates user communication channel preferences', async () => {
    const defaultPrefs = {
      society_id: 'soc-1',
      user_id: 'user-1',
      email_enabled: true,
      sms_enabled: true,
      in_app_enabled: true,
      billing_email: true,
      billing_sms: true,
      complaints_email: true,
      complaints_sms: true,
      visitor_sms: true,
    };

    const getSpy = vi.spyOn(apiClient, 'get').mockResolvedValue(defaultPrefs);
    const prefs = await notificationService.getPreferences();
    expect(getSpy).toHaveBeenCalledWith('/api/v1/notifications/me/preferences');
    expect(prefs.email_enabled).toBe(true);

    const putSpy = vi.spyOn(apiClient, 'put').mockResolvedValue({
      ...defaultPrefs,
      email_enabled: false,
      complaints_email: false,
    });

    const updated = await notificationService.updatePreferences({
      email_enabled: false,
      complaints_email: false,
    });

    expect(putSpy).toHaveBeenCalledWith(
      '/api/v1/notifications/me/preferences',
      { email_enabled: false, complaints_email: false }
    );
    expect(updated.email_enabled).toBe(false);
  });

  it('fetches staff operational delivery overview', async () => {
    const getSpy = vi.spyOn(apiClient, 'get').mockResolvedValue({
      items: [
        {
          id: 'deliv-1',
          recipient_user_id: 'user-99',
          channel: 'EMAIL',
          provider: 'aws_ses',
          status: 'DELIVERED',
          attempt_count: 1,
          created_at: new Date().toISOString(),
        },
      ],
      total: 1,
      delivered_count: 1,
      failed_count: 0,
      retrying_count: 0,
      page: 1,
      page_size: 20,
      total_pages: 1,
    });

    const res = await notificationService.getStaffOverview(1, 20, 'soc-1');

    expect(getSpy).toHaveBeenCalledWith(
      '/api/v1/notifications/staff/overview?page=1&page_size=20&society_id=soc-1'
    );
    expect(res.delivered_count).toBe(1);
    expect(res.items[0].channel).toBe('EMAIL');
  });

  // ---------------------------------------------------------------------------
  // Official Notices Tests
  // ---------------------------------------------------------------------------

  it('fetches resident official notices with category and unread filters', async () => {
    const mockNotices = {
      items: [
        {
          id: 'notice-1',
          society_id: 'soc-1',
          title: 'Power Shutdown',
          body: 'Maintenance shutdown 2PM-4PM',
          category: 'MAINTENANCE',
          priority: 'HIGH',
          status: 'PUBLISHED',
          target_type: 'SOCIETY',
          is_pinned: true,
          is_read: false,
          author_id: 'staff-1',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
      total_pages: 1,
      unread_count: 1,
    };

    const getSpy = vi.spyOn(apiClient, 'get').mockResolvedValue(mockNotices);

    const res = await notificationService.getResidentNotices(1, 20, 'MAINTENANCE', true, 'soc-1');

    expect(getSpy).toHaveBeenCalledTimes(1);
    const calledUrl = getSpy.mock.calls[0][0];
    expect(calledUrl).toContain('/api/v1/notifications/resident/notices?');
    expect(calledUrl).toContain('page=1');
    expect(calledUrl).toContain('page_size=20');
    expect(calledUrl).toContain('category=MAINTENANCE');
    expect(calledUrl).toContain('unread_only=true');
    expect(calledUrl).toContain('society_id=soc-1');
    expect(res.items[0].title).toBe('Power Shutdown');
    expect(res.unread_count).toBe(1);
  });

  it('marks a notice as read and marks all notices as read', async () => {
    const patchSpy = vi.spyOn(apiClient, 'patch').mockResolvedValueOnce({
      notice_id: 'notice-1',
      read_at: new Date().toISOString(),
      status: 'success',
    }).mockResolvedValueOnce({
      marked_count: 3,
      status: 'success',
    });

    const singleRes = await notificationService.markNoticeAsRead('notice-1', 'soc-1');
    expect(patchSpy).toHaveBeenCalledWith(
      '/api/v1/notifications/resident/notices/notice-1/read?society_id=soc-1'
    );
    expect(singleRes.notice_id).toBe('notice-1');

    const allRes = await notificationService.markAllNoticesAsRead('soc-1');
    expect(patchSpy).toHaveBeenCalledWith(
      '/api/v1/notifications/resident/notices/read-all?society_id=soc-1'
    );
    expect(allRes.marked_count).toBe(3);
  });

  it('manages staff notices (create, list, publish, archive)', async () => {
    const postSpy = vi.spyOn(apiClient, 'post').mockResolvedValue({
      id: 'n-new',
      title: 'Emergency Circular',
      status: 'DRAFT',
    });

    const createRes = await notificationService.createStaffNotice(
      {
        title: 'Emergency Circular',
        body: 'Urgent gas leak advisory',
        category: 'EMERGENCY',
        priority: 'URGENT',
        status: 'DRAFT',
        target_type: 'TOWER',
        target_tower_id: 'tow-1',
      },
      'soc-1'
    );

    expect(postSpy).toHaveBeenCalledWith(
      '/api/v1/notifications/staff/notices?society_id=soc-1',
      expect.objectContaining({ title: 'Emergency Circular' })
    );
    expect(createRes.id).toBe('n-new');

    const publishSpy = vi.spyOn(apiClient, 'post').mockResolvedValue({
      id: 'n-new',
      status: 'PUBLISHED',
    });
    await notificationService.publishStaffNotice('n-new', 'soc-1');
    expect(publishSpy).toHaveBeenCalledWith(
      '/api/v1/notifications/staff/notices/n-new/publish?society_id=soc-1'
    );

    const archiveSpy = vi.spyOn(apiClient, 'post').mockResolvedValue({
      id: 'n-new',
      status: 'ARCHIVED',
    });
    await notificationService.archiveStaffNotice('n-new', 'soc-1');
    expect(archiveSpy).toHaveBeenCalledWith(
      '/api/v1/notifications/staff/notices/n-new/archive?society_id=soc-1'
    );
  });
});
