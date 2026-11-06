import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  amenityService,
  formatAmenityFee,
  formatSlotTime,
  formatTimeRange,
  getAmenityCategory,
} from './amenityService';
import { apiClient } from './apiClient';

describe('Amenity Service API Client Integration', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('formats amenity fees correctly', () => {
    expect(formatAmenityFee(0)).toBe('Free');
    expect(formatAmenityFee(25000)).toContain('250');
  });

  it('formats 24h slot times to 12h AM/PM format', () => {
    expect(formatSlotTime('06:00')).toBe('6:00 AM');
    expect(formatSlotTime('12:30')).toBe('12:30 PM');
    expect(formatSlotTime('18:00')).toBe('6:00 PM');
    expect(formatSlotTime('22:15')).toBe('10:15 PM');
    expect(formatTimeRange('06:00', '07:00')).toBe('6:00 AM – 7:00 AM');
  });

  it('categorizes amenity types appropriately', () => {
    expect(getAmenityCategory('BADMINTON_COURT')).toBe('sports');
    expect(getAmenityCategory('TENNIS_COURT')).toBe('sports');
    expect(getAmenityCategory('GYM')).toBe('fitness');
    expect(getAmenityCategory('SWIMMING_POOL')).toBe('fitness');
    expect(getAmenityCategory('CLUBHOUSE')).toBe('clubhouse');
    expect(getAmenityCategory('GUEST_ROOM')).toBe('clubhouse');
    expect(getAmenityCategory('COMMUNITY_HALL')).toBe('community');
  });

  it('fetches list of amenities with query params', async () => {
    const getSpy = vi.spyOn(apiClient, 'get').mockResolvedValue({
      items: [
        {
          id: 'amn-1',
          society_id: 'soc-1',
          name: 'Tennis Court A',
          amenity_type: 'TENNIS_COURT',
          capacity: 1,
          slot_duration_minutes: 60,
          opening_time: '06:00',
          closing_time: '22:00',
          booking_fee_paise: 25000,
          advance_booking_days: 7,
          min_advance_hours: 2,
          max_slots_per_day_per_resident: 2,
          cancellation_deadline_hours: 4,
          refund_percentage: 80,
          allowed_membership_types: ['OWNER', 'TENANT'],
          is_active: true,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
      total: 1,
    });

    const res = await amenityService.listAmenities('soc-1', 'TENNIS_COURT');

    expect(getSpy).toHaveBeenCalledTimes(1);
    const calledUrl = getSpy.mock.calls[0][0];
    expect(calledUrl).toContain('/api/v1/amenities?');
    expect(calledUrl).toContain('society_id=soc-1');
    expect(calledUrl).toContain('amenity_type=TENNIS_COURT');
    expect(res.total).toBe(1);
    expect(res.items[0].name).toBe('Tennis Court A');
  });

  it('fetches single amenity details', async () => {
    const getSpy = vi.spyOn(apiClient, 'get').mockResolvedValue({
      id: 'amn-1',
      name: 'Badminton Court 1',
      amenity_type: 'BADMINTON_COURT',
      booking_fee_paise: 15000,
    });

    const res = await amenityService.getAmenity('amn-1', 'soc-1');
    expect(getSpy).toHaveBeenCalledWith('/api/v1/amenities/amn-1?society_id=soc-1');
    expect(res.name).toBe('Badminton Court 1');
  });

  it('fetches available slots for an amenity on a date', async () => {
    const getSpy = vi.spyOn(apiClient, 'get').mockResolvedValue({
      amenity_id: 'amn-1',
      booking_date: '2026-11-09',
      slots: [
        {
          start_time: '06:00',
          end_time: '07:00',
          total_capacity: 1,
          booked_units: 0,
          remaining_capacity: 1,
          is_available: true,
          is_past: false,
          user_booked: false,
        },
      ],
    });

    const res = await amenityService.getAvailableSlots('amn-1', '2026-11-09', 'soc-1');
    expect(getSpy).toHaveBeenCalledWith(
      '/api/v1/amenities/amn-1/slots?booking_date=2026-11-09&society_id=soc-1'
    );
    expect(res.slots).toHaveLength(1);
    expect(res.slots[0].is_available).toBe(true);
  });

  it('creates an amenity booking', async () => {
    const postSpy = vi.spyOn(apiClient, 'post').mockResolvedValue({
      id: 'book-1',
      amenity_id: 'amn-1',
      status: 'CONFIRMED',
      booking_fee_paise: 25000,
      payment_status: 'PAID',
    });

    const req = {
      flat_id: 'flat-1',
      booking_date: '2026-11-09',
      start_time: '07:00',
      end_time: '08:00',
      booked_units: 1,
      notes: 'Match practice',
    };

    const res = await amenityService.createBooking('amn-1', req, 'soc-1');
    expect(postSpy).toHaveBeenCalledWith(
      '/api/v1/amenities/amn-1/bookings?society_id=soc-1',
      req
    );
    expect(res.id).toBe('book-1');
    expect(res.status).toBe('CONFIRMED');
  });

  it('fetches resident bookings with pagination and upcoming filter', async () => {
    const getSpy = vi.spyOn(apiClient, 'get').mockResolvedValue({
      items: [
        {
          id: 'book-1',
          amenity_name: 'Tennis Court A',
          status: 'CONFIRMED',
          booking_date: '2026-11-09',
        },
      ],
      total: 1,
      page: 1,
      page_size: 10,
      total_pages: 1,
    });

    const res = await amenityService.getMyBookings({
      page: 1,
      pageSize: 10,
      upcomingOnly: true,
      societyId: 'soc-1',
    });

    expect(getSpy).toHaveBeenCalledTimes(1);
    const calledUrl = getSpy.mock.calls[0][0];
    expect(calledUrl).toContain('/api/v1/amenities/bookings/me?');
    expect(calledUrl).toContain('page=1');
    expect(calledUrl).toContain('page_size=10');
    expect(calledUrl).toContain('upcoming_only=true');
    expect(calledUrl).toContain('society_id=soc-1');
    expect(res.items).toHaveLength(1);
  });

  it('cancels resident booking with optional reason', async () => {
    const postSpy = vi.spyOn(apiClient, 'post').mockResolvedValue({
      id: 'book-1',
      status: 'CANCELLED',
      refund_status: 'REFUNDED',
      refund_amount_paise: 20000,
    });

    const res = await amenityService.cancelBooking(
      'book-1',
      { reason: 'Plan changed' },
      'soc-1'
    );
    expect(postSpy).toHaveBeenCalledWith(
      '/api/v1/amenities/bookings/book-1/cancel?society_id=soc-1',
      { reason: 'Plan changed' }
    );
    expect(res.status).toBe('CANCELLED');
    expect(res.refund_status).toBe('REFUNDED');
  });
});
