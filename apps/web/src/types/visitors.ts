export type VisitorApprovalStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'AUTO_APPROVED';

export type VisitorEntryStatus = 'EXPECTED' | 'CHECKED_IN' | 'CHECKED_OUT';

export type VisitorPurposeType =
  | 'GUEST'
  | 'DELIVERY'
  | 'CAB'
  | 'SERVICE_MAINTENANCE'
  | 'EMERGENCY'
  | 'OTHER';

export type GuestPassType = 'SINGLE_USE' | 'MULTI_USE';

export type GuestPassStatus = 'ACTIVE' | 'EXHAUSTED' | 'REDEEMED' | 'EXPIRED' | 'REVOKED';

export type OfflineSyncStatus = 'QUEUED' | 'SYNCING' | 'SYNCED' | 'CONFLICT' | 'FAILED';

export interface GateInfo {
  gate_id: string;
  gate_number: number;
  gate_name: string;
  assigned_from?: string | null;
  assigned_until?: string | null;
}

export interface GateSessionResponse {
  user_id: string;
  full_name: string;
  society_id: string;
  assigned_gate: GateInfo | null;
  available_gates: GateInfo[];
}

export interface GateOverviewResponse {
  user_id: string;
  full_name: string;
  society_id: string;
  gate_id: string | null;
  gate_name: string;
  assigned_gate: GateInfo | null;
  active_checked_in_count: number;
  pending_approvals_count: number;
  offline_queue_supported: boolean;
}

export interface GateFlatOption {
  flat_id: string;
  flat_number: string;
  tower_number: string;
  tower_name: string;
}

export interface VisitorRecord {
  visitor_id: string;
  society_id?: string;
  gate_id?: string;
  visitor_name: string;
  phone_masked: string;
  vehicle_number?: string | null;
  purpose: VisitorPurposeType | string;
  destination_flat_id: string;
  destination_flat?: {
    flat_id: string;
    flat_number: string;
    tower_name?: string;
  } | null;
  approval_status: VisitorApprovalStatus;
  entry_status: VisitorEntryStatus;
  photo_url?: string | null;
  photo_storage_key?: string | null;
  privacy_notice_version?: string;
  created_at: string;
  entry_time?: string | null;
  exit_time?: string | null;
}

export interface RegisterVisitorPayload {
  visitor_name: string;
  phone_number: string;
  vehicle_number?: string | null;
  purpose: VisitorPurposeType;
  destination_flat_id: string;
  photo_base64?: string | null;
  privacy_notice_version: string;
  gate_id?: string;
  client_event_id?: string | null;
}

export interface GuestPass {
  pass_id: string;
  pass_code?: string | null;
  pass_type: GuestPassType;
  max_uses: number;
  used_count: number;
  valid_from: string;
  valid_until: string;
  status: GuestPassStatus;
  destination_flat_id: string;
  guest_name: string;
  purpose: string;
}

export interface CreateGuestPassPayload {
  destination_flat_id: string;
  guest_name: string;
  guest_phone?: string | null;
  purpose: string;
  pass_type: GuestPassType;
  max_uses: number;
  valid_from: string;
  valid_until: string;
}

export interface VerifyGuestPassPayload {
  pass_code: string;
  gate_id: string;
}

export interface VerifyGuestPassResponse {
  verified: boolean;
  pass_id: string;
  visitor_id?: string | null;
  guest_name: string;
  pass_type: GuestPassType;
  remaining_uses: number;
  approval_status: VisitorApprovalStatus | string;
  entry_status: VisitorEntryStatus | string;
  destination_flat?: {
    flat_id: string;
    flat_number: string;
    tower_name?: string;
  } | null;
}

export interface VisitorPhotoUrlResponse {
  photo_url: string;
  expires_in_seconds?: number;
  expires_in?: number;
  privacy_notice_version?: string;
}

export interface PrivacyNoticeResponse {
  version: string;
  language: string;
  title: string;
  content: string;
  retention_days: number;
  grievance_contact: string;
}

export interface OfflineVisitorQueueItem {
  client_event_id: string;
  gate_id: string;
  timestamp: string;
  visitor_name: string;
  phone_number: string;
  vehicle_number: string | null;
  purpose: VisitorPurposeType;
  destination_flat_id: string;
  flat_label?: string;
  photo_base64: string | null;
  photo_sha256?: string | null;
  photo_captured_at?: string | null;
  privacy_notice_version: string;
  payload_hash: string;
  sync_status: OfflineSyncStatus;
  approval_status: 'PENDING';
  entry_status: 'EXPECTED';
  error_message?: string | null;
  retry_count: number;
  server_visitor_id?: string | null;
}

export interface SyncEventResult {
  client_event_id: string;
  status: 'ACK' | 'CONFLICT' | 'ERROR' | 'FAILED';
  visitor_id?: string | null;
  approval_status?: string | null;
  error_message?: string | null;
}

export interface BatchSyncResponse {
  gate_id: string;
  processed_count: number;
  results: SyncEventResult[];
}
