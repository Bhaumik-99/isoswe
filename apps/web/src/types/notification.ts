export type NotificationChannel = 'IN_APP' | 'EMAIL' | 'SMS';
export type NotificationPriority = 'LOW' | 'NORMAL' | 'HIGH' | 'URGENT';
export type DeliveryStatus =
  | 'PENDING'
  | 'PROCESSING'
  | 'SENT'
  | 'DELIVERED'
  | 'RETRYING'
  | 'FAILED'
  | 'SUPPRESSED';

export interface NotificationItem {
  id: string;
  society_id: string;
  recipient_user_id: string;
  event_type: string;
  title: string;
  body: string;
  channel: NotificationChannel;
  priority: NotificationPriority;
  read_at: string | null;
  aggregate_type?: string | null;
  aggregate_id?: string | null;
  action_url?: string | null;
  created_at: string;
}

export interface PaginatedNotifications {
  items: NotificationItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  unread_count: number;
}

export interface UnreadCountResponse {
  unread_count: number;
}

export interface MarkReadResponse {
  notification_id: string;
  read_at: string;
  status: string;
}

export interface MarkAllReadResponse {
  marked_count: number;
  status: string;
}

export interface NotificationPreferences {
  society_id: string;
  user_id: string;
  email_enabled: boolean;
  sms_enabled: boolean;
  in_app_enabled: boolean;
  billing_email: boolean;
  billing_sms: boolean;
  complaints_email: boolean;
  complaints_sms: boolean;
  visitor_sms: boolean;
}

export interface UpdateNotificationPreferencesPayload {
  email_enabled?: boolean;
  sms_enabled?: boolean;
  in_app_enabled?: boolean;
  billing_email?: boolean;
  billing_sms?: boolean;
  complaints_email?: boolean;
  complaints_sms?: boolean;
  visitor_sms?: boolean;
}

export interface StaffDeliveryItem {
  id: string;
  notification_id?: string | null;
  recipient_user_id: string;
  channel: string;
  provider: string;
  status: DeliveryStatus;
  attempt_count: number;
  last_error_code?: string | null;
  last_error_message?: string | null;
  sent_at?: string | null;
  delivered_at?: string | null;
  created_at: string;
}

export interface StaffNotificationOverview {
  items: StaffDeliveryItem[];
  total: number;
  delivered_count: number;
  failed_count: number;
  retrying_count: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export type NoticeCategory =
  | 'CIRCULAR'
  | 'MAINTENANCE'
  | 'EMERGENCY'
  | 'EVENT'
  | 'GENERAL'
  | 'WATER'
  | 'ELECTRICITY'
  | 'SECURITY';

export type NoticePriority = 'LOW' | 'NORMAL' | 'HIGH' | 'URGENT';
export type NoticeStatus = 'DRAFT' | 'SCHEDULED' | 'PUBLISHED' | 'ARCHIVED';
export type NoticeTargetType = 'SOCIETY' | 'TOWER' | 'FLAT';

export interface NoticeOverviewStats {
  total: number;
  published: number;
  scheduled: number;
  draft: number;
  archived: number;
  emergency: number;
}

export interface NoticeItem {
  id: string;
  society_id: string;
  title: string;
  body: string;
  category: NoticeCategory;
  priority: NoticePriority;
  status: NoticeStatus;
  target_type: NoticeTargetType;
  target_tower_id?: string | null;
  target_tower_name?: string | null;
  target_tower_ids?: string[];
  target_tower_names?: string[];
  target_flat_id?: string | null;
  target_flat_number?: string | null;
  target_flat_ids?: string[];
  target_flat_numbers?: string[];
  is_pinned: boolean;
  published_at?: string | null;
  expires_at?: string | null;
  version?: number;
  author_id: string;
  author_name?: string | null;
  is_read?: boolean;
  read_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PaginatedNotices {
  items: NoticeItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  unread_count?: number;
}

export interface CreateNoticePayload {
  title: string;
  body: string;
  category: NoticeCategory;
  priority: NoticePriority;
  status: NoticeStatus;
  target_type: NoticeTargetType;
  target_tower_id?: string | null;
  target_tower_ids?: string[];
  target_flat_id?: string | null;
  target_flat_ids?: string[];
  is_pinned?: boolean;
  published_at?: string | null;
  expires_at?: string | null;
  deliver_emergency?: boolean;
}

export interface UpdateNoticePayload {
  title?: string;
  body?: string;
  category?: NoticeCategory;
  priority?: NoticePriority;
  status?: NoticeStatus;
  target_type?: NoticeTargetType;
  target_tower_id?: string | null;
  target_tower_ids?: string[];
  target_flat_id?: string | null;
  target_flat_ids?: string[];
  is_pinned?: boolean;
  published_at?: string | null;
  expires_at?: string | null;
  deliver_emergency?: boolean;
}

export interface TowerOption {
  id: string;
  tower_number: string;
  name: string;
}

export interface FlatOption {
  id: string;
  flat_number: string;
  tower_id: string;
  tower_number: string;
  tower_name: string;
}

export interface NoticeTargetingOptionsResponse {
  towers: TowerOption[];
  flats: FlatOption[];
}


export interface MarkNoticeReadResponse {
  notice_id: string;
  read_at: string;
  status: string;
}

export interface MarkAllNoticesReadResponse {
  marked_count: number;
  status: string;
}

