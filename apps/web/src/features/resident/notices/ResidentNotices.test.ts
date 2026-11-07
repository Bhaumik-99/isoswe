import { describe, it, expect } from 'vitest';
import { NoticeCategory, NoticeItem, NoticePriority, NoticeStatus, NoticeTargetType } from '../../../types';

export const filterNotices = (
  notices: NoticeItem[],
  categoryFilter: NoticeCategory | 'ALL',
  unreadOnly: boolean
): NoticeItem[] => {
  return notices.filter((notice) => {
    if (categoryFilter !== 'ALL' && notice.category !== categoryFilter) {
      return false;
    }
    if (unreadOnly && notice.is_read) {
      return false;
    }
    return true;
  });
};

export const sortNoticesForResidentFeed = (notices: NoticeItem[]): NoticeItem[] => {
  return [...notices].sort((a, b) => {
    // Pinned notices first
    if (a.is_pinned !== b.is_pinned) {
      return a.is_pinned ? -1 : 1;
    }
    // Then newest published_at
    const timeA = new Date(a.published_at || a.created_at).getTime();
    const timeB = new Date(b.published_at || b.created_at).getTime();
    return timeB - timeA;
  });
};

export const isNoticeActive = (notice: NoticeItem, now = new Date()): boolean => {
  if (notice.status !== 'PUBLISHED') return false;
  if (notice.published_at && new Date(notice.published_at).getTime() > now.getTime()) {
    return false; // Scheduled in future
  }
  if (notice.expires_at && new Date(notice.expires_at).getTime() <= now.getTime()) {
    return false; // Expired
  }
  return true;
};

describe('Resident Notices Feed Business Logic', () => {
  const sampleNotices: NoticeItem[] = [
    {
      id: 'n-1',
      society_id: 'soc-1',
      title: 'Water Tank Cleaning',
      body: 'Cleaning on Saturday',
      category: 'MAINTENANCE',
      priority: 'HIGH',
      status: 'PUBLISHED',
      target_type: 'SOCIETY',
      is_pinned: false,
      is_read: true,
      published_at: '2026-11-01T10:00:00Z',
      created_at: '2026-11-01T09:00:00Z',
      updated_at: '2026-11-01T09:00:00Z',
      author_id: 'staff-1',
    },
    {
      id: 'n-2',
      society_id: 'soc-1',
      title: 'URGENT: Fire Evacuation Drill',
      body: 'Emergency drill tomorrow at 10 AM',
      category: 'EMERGENCY',
      priority: 'URGENT',
      status: 'PUBLISHED',
      target_type: 'SOCIETY',
      is_pinned: true,
      is_read: false,
      published_at: '2026-11-02T10:00:00Z',
      created_at: '2026-11-02T09:00:00Z',
      updated_at: '2026-11-02T09:00:00Z',
      author_id: 'staff-1',
    },
    {
      id: 'n-3',
      society_id: 'soc-1',
      title: 'Annual General Meeting Circular',
      body: 'AGM details and agenda',
      category: 'CIRCULAR',
      priority: 'NORMAL',
      status: 'PUBLISHED',
      target_type: 'SOCIETY',
      is_pinned: false,
      is_read: false,
      published_at: '2026-11-03T10:00:00Z',
      created_at: '2026-11-03T09:00:00Z',
      updated_at: '2026-11-03T09:00:00Z',
      author_id: 'staff-1',
    },
  ];

  it('correctly filters notices by category', () => {
    const maintenance = filterNotices(sampleNotices, 'MAINTENANCE', false);
    expect(maintenance).toHaveLength(1);
    expect(maintenance[0].title).toBe('Water Tank Cleaning');

    const emergency = filterNotices(sampleNotices, 'EMERGENCY', false);
    expect(emergency).toHaveLength(1);
    expect(emergency[0].title).toContain('Fire Evacuation Drill');

    const all = filterNotices(sampleNotices, 'ALL', false);
    expect(all).toHaveLength(3);
  });

  it('correctly filters for unread notices only', () => {
    const unread = filterNotices(sampleNotices, 'ALL', true);
    expect(unread).toHaveLength(2);
    expect(unread.some((n) => n.id === 'n-1')).toBe(false);
    expect(unread.every((n) => !n.is_read)).toBe(true);
  });

  it('sorts pinned notices to the top regardless of publication date', () => {
    const sorted = sortNoticesForResidentFeed(sampleNotices);
    // n-2 is pinned (published 2026-11-02), while n-3 is unpinned but published later (2026-11-03)
    expect(sorted[0].id).toBe('n-2');
    expect(sorted[0].is_pinned).toBe(true);
    expect(sorted[1].id).toBe('n-3');
    expect(sorted[2].id).toBe('n-1');
  });

  it('correctly evaluates notice active status (scheduled vs expired)', () => {
    const now = new Date('2026-11-07T12:00:00Z');

    const futureNotice: NoticeItem = {
      ...sampleNotices[0],
      published_at: '2026-11-10T10:00:00Z',
    };
    expect(isNoticeActive(futureNotice, now)).toBe(false);

    const expiredNotice: NoticeItem = {
      ...sampleNotices[0],
      published_at: '2026-11-01T10:00:00Z',
      expires_at: '2026-11-05T10:00:00Z',
    };
    expect(isNoticeActive(expiredNotice, now)).toBe(false);

    const activeNotice: NoticeItem = {
      ...sampleNotices[0],
      published_at: '2026-11-01T10:00:00Z',
      expires_at: '2026-11-15T10:00:00Z',
    };
    expect(isNoticeActive(activeNotice, now)).toBe(true);

    const draftNotice: NoticeItem = {
      ...sampleNotices[0],
      status: 'DRAFT',
    };
    expect(isNoticeActive(draftNotice, now)).toBe(false);
  });
});
