import { apiClient } from './apiClient';
import {
  BatchSyncResponse,
  GateFlatOption,
  GateOverviewResponse,
  GateSessionResponse,
  PrivacyNoticeResponse,
  RegisterVisitorPayload,
  VerifyGuestPassPayload,
  VerifyGuestPassResponse,
  VisitorPhotoUrlResponse,
  VisitorRecord,
} from '../types';

const FLAT_CACHE_KEY = 'isoswe_gate_cached_flats_v1';

export function formatPhoneToE164(phoneInput: string): string {
  const digits = phoneInput.replace(/\D/g, '');
  if (digits.length === 12 && digits.startsWith('91')) {
    return `+${digits}`;
  }
  if (digits.length === 10) {
    return `+91${digits}`;
  }
  if (phoneInput.trim().startsWith('+')) {
    return phoneInput.trim();
  }
  return `+91${digits}`;
}

export function isValidIndianPhone(phoneInput: string): boolean {
  const formatted = formatPhoneToE164(phoneInput);
  return /^\+91[6-9][0-9]{9}$/.test(formatted) || /^\+91[0-9]{10}$/.test(formatted);
}

export const gateService = {
  async getSession(): Promise<GateSessionResponse> {
    return apiClient.get<GateSessionResponse>('/api/v1/gate/session');
  },

  async getOverview(): Promise<GateOverviewResponse> {
    return apiClient.get<GateOverviewResponse>('/api/v1/gate/overview');
  },

  async listFlats(search?: string, limit = 50): Promise<GateFlatOption[]> {
    const params = new URLSearchParams();
    if (search && search.trim()) {
      params.set('search', search.trim());
    }
    params.set('limit', String(Math.min(limit, 50)));
    try {
      const flats = await apiClient.get<GateFlatOption[]>(`/api/v1/gate/flats?${params.toString()}`);
      if (!search) {
        try {
          localStorage.setItem(FLAT_CACHE_KEY, JSON.stringify(flats));
        } catch {
          // Ignore storage quota errors
        }
      }
      return flats;
    } catch (err) {
      // Fallback to cached flats when tablet is offline
      try {
        const cachedRaw = localStorage.getItem(FLAT_CACHE_KEY);
        if (cachedRaw) {
          const parsed = JSON.parse(cachedRaw) as GateFlatOption[];
          if (search && search.trim()) {
            const q = search.trim().toLowerCase();
            return parsed.filter(
              (f) =>
                f.flat_number.toLowerCase().includes(q) ||
                f.tower_number.toLowerCase().includes(q) ||
                f.tower_name.toLowerCase().includes(q)
            );
          }
          return parsed;
        }
      } catch {
        // Ignore parse errors
      }
      throw err;
    }
  },

  async registerVisitor(payload: RegisterVisitorPayload): Promise<VisitorRecord> {
    const normalizedPayload: RegisterVisitorPayload = {
      ...payload,
      visitor_name: payload.visitor_name.trim(),
      phone_number: formatPhoneToE164(payload.phone_number),
      vehicle_number: payload.vehicle_number?.trim() || null,
    };
    return apiClient.post<VisitorRecord>('/api/v1/gate/visitors/register', normalizedPayload);
  },

  async checkInVisitor(visitorId: string): Promise<{
    visitor_id: string;
    entry_status: string;
    entry_time: string | null;
    entry_gate_id: string | null;
  }> {
    return apiClient.post(`/api/v1/gate/visitors/${visitorId}/check-in`, {});
  },

  async checkOutVisitor(
    visitorId: string,
    exitGateId?: string
  ): Promise<{
    visitor_id: string;
    entry_status: string;
    exit_time: string | null;
    exit_gate_id: string | null;
  }> {
    return apiClient.post(`/api/v1/gate/visitors/${visitorId}/check-out`, {
      exit_gate_id: exitGateId || undefined,
    });
  },

  async listVisitors(params?: {
    status?: string;
    gate_id?: string;
    search?: string;
    limit?: number;
    offset?: number;
  }): Promise<VisitorRecord[]> {
    const query = new URLSearchParams();
    if (params?.status) query.set('status', params.status);
    if (params?.gate_id) query.set('gate_id', params.gate_id);
    if (params?.search) query.set('search', params.search);
    query.set('limit', String(Math.min(params?.limit || 25, 50)));
    query.set('offset', String(params?.offset || 0));
    return apiClient.get<VisitorRecord[]>(`/api/v1/gate/visitors?${query.toString()}`);
  },

  async listActiveInsideVisitors(limit = 50, offset = 0): Promise<VisitorRecord[]> {
    const query = new URLSearchParams({
      limit: String(Math.min(limit, 50)),
      offset: String(offset),
    });
    return apiClient.get<VisitorRecord[]>(`/api/v1/gate/visitors/active?${query.toString()}`);
  },

  async listVisitorHistory(params?: {
    search?: string;
    limit?: number;
    offset?: number;
  }): Promise<VisitorRecord[]> {
    const query = new URLSearchParams();
    if (params?.search) query.set('search', params.search);
    query.set('limit', String(Math.min(params?.limit || 25, 50)));
    query.set('offset', String(params?.offset || 0));
    return apiClient.get<VisitorRecord[]>(`/api/v1/gate/visitors/history?${query.toString()}`);
  },

  async getVisitorPhotoUrl(visitorId: string): Promise<VisitorPhotoUrlResponse> {
    return apiClient.get<VisitorPhotoUrlResponse>(`/api/v1/gate/visitors/${visitorId}/photo`);
  },

  async verifyGuestPass(payload: VerifyGuestPassPayload): Promise<VerifyGuestPassResponse> {
    return apiClient.post<VerifyGuestPassResponse>('/api/v1/gate/pass/verify', {
      pass_code: payload.pass_code.trim().toUpperCase(),
      gate_id: payload.gate_id,
    });
  },

  async syncOfflineBatch(
    gateId: string,
    events: Array<{
      client_event_id: string;
      timestamp: string;
      payload: {
        visitor_name: string;
        phone_number: string;
        vehicle_number: string | null;
        purpose: string;
        destination_flat_id: string;
        photo_base64: string | null;
        privacy_notice_version: string;
      };
    }>
  ): Promise<BatchSyncResponse> {
    return apiClient.post<BatchSyncResponse>('/api/v1/gate/sync', {
      gate_id: gateId,
      events,
    });
  },

  async getPrivacyNotice(lang = 'en'): Promise<PrivacyNoticeResponse> {
    return apiClient.get<PrivacyNoticeResponse>(`/api/v1/gate/privacy-notice?lang=${encodeURIComponent(lang)}`);
  },
};

