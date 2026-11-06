/**
 * TypeScript definitions for Amenity & Clubhouse Bookings domain.
 */

export type AmenityType =
  | 'CLUBHOUSE'
  | 'BADMINTON_COURT'
  | 'TENNIS_COURT'
  | 'SWIMMING_POOL'
  | 'GYM'
  | 'COMMUNITY_HALL'
  | 'GUEST_ROOM'
  | 'OTHER';

export type BookingStatus =
  | 'PENDING_PAYMENT'
  | 'CONFIRMED'
  | 'CANCELLED'
  | 'COMPLETED'
  | 'PAYMENT_FAILED';

export type BookingPaymentStatus = 'FREE' | 'PAID' | 'PENDING' | 'REFUNDED' | 'FAILED';

export type RefundStatus =
  | 'NOT_APPLICABLE'
  | 'PENDING_REFUND'
  | 'REFUNDED'
  | 'CANCELLED_NO_REFUND';

export interface Amenity {
  id: string;
  society_id: string;
  name: string;
  description?: string | null;
  amenity_type: AmenityType;
  location?: string | null;
  tower_id?: string | null;
  capacity: number;
  slot_duration_minutes: number;
  opening_time: string;
  closing_time: string;
  booking_fee_paise: number;
  advance_booking_days: number;
  min_advance_hours: number;
  max_slots_per_day_per_resident: number;
  cancellation_deadline_hours: number;
  refund_percentage: number;
  allowed_membership_types: string[];
  is_active: boolean;
  rules_and_guidelines?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AmenityListResponse {
  items: Amenity[];
  total: number;
}

export interface TimeSlotAvailability {
  start_time: string;
  end_time: string;
  total_capacity: number;
  booked_units: number;
  remaining_capacity: number;
  is_available: boolean;
  is_past: boolean;
  user_booked: boolean;
  is_blocked?: boolean;
  block_reason?: string | null;
}

export interface AmenitySlotsResponse {
  amenity_id: string;
  booking_date: string;
  slots: TimeSlotAvailability[];
}

export interface CreateBookingRequest {
  flat_id: string;
  booking_date: string; // YYYY-MM-DD
  start_time: string; // HH:MM
  end_time: string; // HH:MM
  booked_units?: number;
  notes?: string | null;
  auto_pay?: boolean;
}

export interface PayBookingRequest {
  simulate_failure?: boolean;
  idempotency_key?: string;
}

export interface CancelBookingRequest {
  reason?: string | null;
}

export interface StaffCancelBookingRequest {
  reason: string;
}

export interface AmenityBlock {
  id: string;
  society_id: string;
  amenity_id: string;
  block_date: string;
  start_time?: string | null;
  end_time?: string | null;
  reason: string;
  blocked_by_user_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateAmenityBlockRequest {
  block_date: string;
  start_time?: string | null;
  end_time?: string | null;
  reason: string;
}

export interface CreateAmenityRequest {
  name: string;
  description?: string | null;
  amenity_type: AmenityType;
  location?: string | null;
  tower_id?: string | null;
  capacity?: number;
  slot_duration_minutes?: number;
  opening_time?: string;
  closing_time?: string;
  booking_fee_paise?: number;
  advance_booking_days?: number;
  min_advance_hours?: number;
  max_slots_per_day_per_resident?: number;
  cancellation_deadline_hours?: number;
  refund_percentage?: number;
  allowed_membership_types?: string[];
  rules_and_guidelines?: string | null;
  is_active?: boolean;
}

export interface UpdateAmenityRequest {
  name?: string;
  description?: string | null;
  location?: string | null;
  tower_id?: string | null;
  capacity?: number;
  slot_duration_minutes?: number;
  opening_time?: string;
  closing_time?: string;
  booking_fee_paise?: number;
  advance_booking_days?: number;
  min_advance_hours?: number;
  max_slots_per_day_per_resident?: number;
  cancellation_deadline_hours?: number;
  refund_percentage?: number;
  allowed_membership_types?: string[];
  rules_and_guidelines?: string | null;
  is_active?: boolean;
}

export interface StaffBookingFilterParams {
  amenity_id?: string;
  booking_date?: string;
  status?: BookingStatus;
  payment_status?: BookingPaymentStatus;
  flat_id?: string;
  search?: string;
  page?: number;
  page_size?: number;
  society_id?: string;
}

export interface AmenityBooking {
  id: string;
  society_id: string;
  amenity_id: string;
  amenity_name?: string | null;
  amenity_type?: AmenityType | null;
  user_id: string;
  flat_id: string;
  flat_number?: string | null;
  booking_date: string;
  start_time: string;
  end_time: string;
  booked_units: number;
  status: BookingStatus;
  booking_fee_paise: number;
  payment_status: BookingPaymentStatus;
  payment_id?: string | null;
  payment_reference?: string | null;
  payment_expires_at?: string | null;
  refund_status: RefundStatus;
  refund_amount_paise: number;
  cancellation_reason?: string | null;
  cancelled_at?: string | null;
  cancelled_by_user_id?: string | null;
  notes?: string | null;
  booking_metadata?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface PaginatedBookingsResponse {
  items: AmenityBooking[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

