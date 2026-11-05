/**
 * Resident & Unit Registry API Service
 */

import { apiClient } from './apiClient';
import { MembershipType, MembershipStatus } from '../types';

export interface ResidentFlatInfo {
  membership_id: string;
  flat_id: string;
  flat_number: string;
  tower_id: string;
  tower_number: string;
  membership_type: MembershipType;
  membership_status: MembershipStatus;
  valid_from: string;
  valid_until?: string | null;
  is_primary: boolean;
}

export interface ResidentDirectoryItem {
  user_id: string;
  full_name: string;
  email?: string | null;
  phone?: string | null;
  user_status: string;
  flats: ResidentFlatInfo[];
}

export interface CreateMembershipPayload {
  society_id?: string;
  user_id?: string;
  full_name?: string;
  email?: string;
  phone?: string;
  flat_id: string;
  membership_type: MembershipType;
  valid_from: string;
  valid_until?: string | null;
  is_primary?: boolean;
}

export interface UpdateMembershipStatusPayload {
  status: MembershipStatus;
  rejection_reason?: string;
}

export const registryService = {
  async listResidents(params: {
    query?: string;
    society_id?: string;
    tower_id?: string;
    status?: string;
    membership_type?: string;
    limit?: number;
    offset?: number;
  } = {}): Promise<ResidentDirectoryItem[]> {
    const searchParams = new URLSearchParams();
    if (params.query) searchParams.append('query', params.query);
    if (params.society_id) searchParams.append('society_id', params.society_id);
    if (params.tower_id) searchParams.append('tower_id', params.tower_id);
    if (params.status && params.status !== 'ALL') searchParams.append('status', params.status);
    if (params.membership_type && params.membership_type !== 'ALL') {
      searchParams.append('membership_type', params.membership_type);
    }
    if (params.limit) searchParams.append('limit', params.limit.toString());
    if (params.offset) searchParams.append('offset', params.offset.toString());

    const queryString = searchParams.toString();
    const url = `/api/v1/registry/residents${queryString ? `?${queryString}` : ''}`;
    return apiClient.request<ResidentDirectoryItem[]>(url);
  },

  async createMembership(payload: CreateMembershipPayload): Promise<ResidentFlatInfo> {
    return apiClient.request<ResidentFlatInfo>('/api/v1/registry/memberships', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async updateMembershipStatus(
    membershipId: string,
    payload: UpdateMembershipStatusPayload
  ): Promise<ResidentFlatInfo> {
    return apiClient.request<ResidentFlatInfo>(`/api/v1/registry/memberships/${membershipId}/status`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  },
};

