/**
 * Frontend Amenities & Clubhouse Bookings API Service
 *
 * Implements typed API requests for resident amenity discovery, slot availability,
 * and reservation management.
 */

import { apiClient } from './apiClient';
import {
  Amenity,
  AmenityBlock,
  AmenityBooking,
  AmenityListResponse,
  AmenitySlotsResponse,
  AmenityType,
  BookingStatus,
  CancelBookingRequest,
  CreateAmenityBlockRequest,
  CreateAmenityRequest,
  CreateBookingRequest,
  PaginatedBookingsResponse,
  PayBookingRequest,
  StaffBookingFilterParams,
  StaffCancelBookingRequest,
  UpdateAmenityRequest,
} from '../types/amenities';
import { formatINR } from './billingService';

export function formatAmenityFee(paise: number): string {
  if (paise === 0) {
    return 'Free';
  }
  return formatINR(paise);
}

export function formatSlotTime(timeStr: string): string {
  if (!timeStr || !timeStr.includes(':')) return timeStr;
  const [hours, minutes] = timeStr.split(':').map(Number);
  const period = hours >= 12 ? 'PM' : 'AM';
  const displayHours = hours % 12 === 0 ? 12 : hours % 12;
  return `${displayHours}:${minutes.toString().padStart(2, '0')} ${period}`;
}

export function formatTimeRange(start: string, end: string): string {
  return `${formatSlotTime(start)} – ${formatSlotTime(end)}`;
}

export function getAmenityCategory(type: AmenityType): 'sports' | 'fitness' | 'clubhouse' | 'community' {
  switch (type) {
    case 'BADMINTON_COURT':
    case 'TENNIS_COURT':
      return 'sports';
    case 'GYM':
    case 'SWIMMING_POOL':
      return 'fitness';
    case 'CLUBHOUSE':
    case 'GUEST_ROOM':
      return 'clubhouse';
    case 'COMMUNITY_HALL':
    case 'OTHER':
    default:
      return 'community';
  }
}

export const amenityService = {
  /**
   * Lists active amenities available in the township.
   */
  async listAmenities(societyId?: string, amenityType?: AmenityType): Promise<AmenityListResponse> {
    const params = new URLSearchParams();
    if (societyId) params.append('society_id', societyId);
    if (amenityType) params.append('amenity_type', amenityType);
    const queryString = params.toString() ? `?${params.toString()}` : '';
    return apiClient.get<AmenityListResponse>(`/api/v1/amenities${queryString}`);
  },

  /**
   * Retrieves single amenity details, guidelines, and rules.
   */
  async getAmenity(amenityId: string, societyId?: string): Promise<Amenity> {
    const params = new URLSearchParams();
    if (societyId) params.append('society_id', societyId);
    const queryString = params.toString() ? `?${params.toString()}` : '';
    return apiClient.get<Amenity>(`/api/v1/amenities/${amenityId}${queryString}`);
  },

  /**
   * Fetches authoritative time slots and real-time remaining capacity for a date.
   */
  async getAvailableSlots(
    amenityId: string,
    bookingDate: string,
    societyId?: string
  ): Promise<AmenitySlotsResponse> {
    const params = new URLSearchParams({ booking_date: bookingDate });
    if (societyId) params.append('society_id', societyId);
    return apiClient.get<AmenitySlotsResponse>(
      `/api/v1/amenities/${amenityId}/slots?${params.toString()}`
    );
  },

  /**
   * Reserves an amenity slot. Concurrency-protected by backend row locks.
   */
  async createBooking(
    amenityId: string,
    req: CreateBookingRequest,
    societyId?: string
  ): Promise<AmenityBooking> {
    const params = new URLSearchParams();
    if (societyId) params.append('society_id', societyId);
    const queryString = params.toString() ? `?${params.toString()}` : '';
    return apiClient.post<AmenityBooking>(
      `/api/v1/amenities/${amenityId}/bookings${queryString}`,
      req
    );
  },

  /**
   * Fetches paginated list of resident's bookings.
   */
  async getMyBookings(params?: {
    page?: number;
    pageSize?: number;
    status?: BookingStatus;
    upcomingOnly?: boolean;
    societyId?: string;
  }): Promise<PaginatedBookingsResponse> {
    const query = new URLSearchParams();
    if (params?.page) query.append('page', params.page.toString());
    if (params?.pageSize) query.append('page_size', params.pageSize.toString());
    if (params?.status) query.append('status', params.status);
    if (params?.upcomingOnly !== undefined) {
      query.append('upcoming_only', params.upcomingOnly.toString());
    }
    if (params?.societyId) query.append('society_id', params.societyId);
    const queryString = query.toString() ? `?${query.toString()}` : '';
    return apiClient.get<PaginatedBookingsResponse>(`/api/v1/amenities/bookings/me${queryString}`);
  },

  /**
   * Retrieves single booking details. Enforces IDOR security.
   */
  async getBookingDetails(bookingId: string, societyId?: string): Promise<AmenityBooking> {
    const params = new URLSearchParams();
    if (societyId) params.append('society_id', societyId);
    const queryString = params.toString() ? `?${params.toString()}` : '';
    return apiClient.get<AmenityBooking>(`/api/v1/amenities/bookings/${bookingId}${queryString}`);
  },

  /**
   * Cancels an eligible booking, triggering automated refund calculation.
   */
  async cancelBooking(
    bookingId: string,
    req?: CancelBookingRequest,
    societyId?: string
  ): Promise<AmenityBooking> {
    const params = new URLSearchParams();
    if (societyId) params.append('society_id', societyId);
    const queryString = params.toString() ? `?${params.toString()}` : '';
    return apiClient.post<AmenityBooking>(
      `/api/v1/amenities/bookings/${bookingId}/cancel${queryString}`,
      req || {}
    );
  },

  /**
   * Executes simulated payment for a pending amenity booking with idempotency.
   */
  async payBooking(
    bookingId: string,
    req?: PayBookingRequest,
    societyId?: string
  ): Promise<AmenityBooking> {
    const params = new URLSearchParams();
    if (societyId) params.append('society_id', societyId);
    const queryString = params.toString() ? `?${params.toString()}` : '';

    const headers: Record<string, string> = {};
    if (req?.idempotency_key) {
      headers['Idempotency-Key'] = req.idempotency_key;
    }

    return apiClient.post<AmenityBooking>(
      `/api/v1/amenities/bookings/${bookingId}/pay${queryString}`,
      { simulate_failure: req?.simulate_failure ?? false },
      { headers }
    );
  },

  /**
   * Staff: Creates a new township amenity.
   */
  async staffCreateAmenity(
    req: CreateAmenityRequest,
    societyId?: string
  ): Promise<Amenity> {
    const params = new URLSearchParams();
    if (societyId) params.append('society_id', societyId);
    const queryString = params.toString() ? `?${params.toString()}` : '';
    return apiClient.post<Amenity>(`/api/v1/amenities/staff${queryString}`, req);
  },

  /**
   * Staff: Updates amenity configuration.
   */
  async staffUpdateAmenity(
    amenityId: string,
    req: UpdateAmenityRequest,
    societyId?: string
  ): Promise<Amenity> {
    const params = new URLSearchParams();
    if (societyId) params.append('society_id', societyId);
    const queryString = params.toString() ? `?${params.toString()}` : '';
    return apiClient.patch<Amenity>(`/api/v1/amenities/staff/${amenityId}${queryString}`, req);
  },

  /**
   * Staff: Toggles amenity active status.
   */
  async staffToggleAmenityStatus(
    amenityId: string,
    isActive: boolean,
    societyId?: string
  ): Promise<Amenity> {
    const params = new URLSearchParams();
    if (societyId) params.append('society_id', societyId);
    const queryString = params.toString() ? `?${params.toString()}` : '';
    return apiClient.post<Amenity>(
      `/api/v1/amenities/staff/${amenityId}/status${queryString}`,
      { is_active: isActive }
    );
  },

  /**
   * Staff: Lists all township bookings with comprehensive filtering and search.
   */
  async staffListBookings(
    filterParams?: StaffBookingFilterParams
  ): Promise<PaginatedBookingsResponse> {
    const query = new URLSearchParams();
    if (filterParams?.amenity_id) query.append('amenity_id', filterParams.amenity_id);
    if (filterParams?.booking_date) query.append('booking_date', filterParams.booking_date);
    if (filterParams?.status) query.append('status', filterParams.status);
    if (filterParams?.payment_status) query.append('payment_status', filterParams.payment_status);
    if (filterParams?.flat_id) query.append('flat_id', filterParams.flat_id);
    if (filterParams?.search) query.append('search', filterParams.search);
    if (filterParams?.page) query.append('page', filterParams.page.toString());
    if (filterParams?.page_size) query.append('page_size', filterParams.page_size.toString());
    if (filterParams?.society_id) query.append('society_id', filterParams.society_id);

    const queryString = query.toString() ? `?${query.toString()}` : '';
    return apiClient.get<PaginatedBookingsResponse>(`/api/v1/amenities/staff/bookings${queryString}`);
  },

  /**
   * Staff: Administratively cancels a booking with mandatory reason (100% full refund).
   */
  async staffCancelBooking(
    bookingId: string,
    req: StaffCancelBookingRequest,
    societyId?: string
  ): Promise<AmenityBooking> {
    const params = new URLSearchParams();
    if (societyId) params.append('society_id', societyId);
    const queryString = params.toString() ? `?${params.toString()}` : '';
    return apiClient.post<AmenityBooking>(
      `/api/v1/amenities/staff/bookings/${bookingId}/cancel${queryString}`,
      req
    );
  },

  /**
   * Staff: Creates a temporary maintenance/management block for an amenity.
   */
  async createAmenityBlock(
    amenityId: string,
    req: CreateAmenityBlockRequest,
    societyId?: string
  ): Promise<AmenityBlock> {
    const params = new URLSearchParams();
    if (societyId) params.append('society_id', societyId);
    const queryString = params.toString() ? `?${params.toString()}` : '';
    return apiClient.post<AmenityBlock>(
      `/api/v1/amenities/staff/${amenityId}/blocks${queryString}`,
      req
    );
  },

  /**
   * Staff: Lists all blocks for an amenity.
   */
  async listAmenityBlocks(
    amenityId: string,
    blockDate?: string,
    societyId?: string
  ): Promise<AmenityBlock[]> {
    const params = new URLSearchParams();
    if (blockDate) params.append('block_date', blockDate);
    if (societyId) params.append('society_id', societyId);
    const queryString = params.toString() ? `?${params.toString()}` : '';
    return apiClient.get<AmenityBlock[]>(
      `/api/v1/amenities/staff/${amenityId}/blocks${queryString}`
    );
  },

  /**
   * Staff: Removes a maintenance block.
   */
  async deleteAmenityBlock(blockId: string, societyId?: string): Promise<void> {
    const params = new URLSearchParams();
    if (societyId) params.append('society_id', societyId);
    const queryString = params.toString() ? `?${params.toString()}` : '';
    return apiClient.delete<void>(`/api/v1/amenities/staff/blocks/${blockId}${queryString}`);
  },
};

