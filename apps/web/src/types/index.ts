export type RoleType =
  | 'RESIDENT'
  | 'HELPDESK';

export type UserStatus = 'ACTIVE' | 'INACTIVE' | 'SUSPENDED';

export type MembershipType = 'OWNER' | 'TENANT' | 'FAMILY_MEMBER';

export type MembershipStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'EXPIRED' | 'TERMINATED';

export type FlatStatus = 'OCCUPIED' | 'VACANT' | 'UNDER_MAINTENANCE';

export interface UserProfile {
  id: string;
  supabase_uid: string;
  email?: string | null;
  phone?: string | null;
  full_name: string;
  status: UserStatus;
  created_at: string;
}

export interface UserRole {
  id: string;
  society_id: string;
  role: RoleType;
}

export interface FlatMembership {
  id: string;
  society_id: string;
  flat_id: string;
  user_id: string;
  membership_type: MembershipType;
  valid_from: string;
  valid_until?: string | null;
  is_primary: boolean;
  status: MembershipStatus;
  flat_number?: string | null;
  tower_number?: string | null;
}

export interface MeResponse {
  user: UserProfile;
  roles: UserRole[];
  memberships: FlatMembership[];
}

export interface FlatDetail {
  id: string;
  society_id: string;
  tower_id: string;
  flat_number: string;
  area_sqft: number;
  status: FlatStatus;
  tower_name?: string | null;
  tower_number?: string | null;
  society_name?: string | null;
}

export interface ApiErrorDetail {
  code: string;
  message: string;
  request_id: string;
  details?: Record<string, unknown> | null;
}

export interface ApiErrorResponse {
  error: ApiErrorDetail;
}
