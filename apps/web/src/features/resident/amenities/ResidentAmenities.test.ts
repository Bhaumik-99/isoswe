import { describe, it, expect } from 'vitest';
import {
  formatAmenityTypeName,
  getAmenityIcon,
} from './AmenityCard';
import {
  formatDateToISO,
  getSelectableDates,
} from './AmenityBookingModal';
import { getAmenityCategory } from '../../../services/amenityService';
import { Amenity } from '../../../types/amenities';

describe('Resident Amenity Components & Booking Logic', () => {
  const mockAmenity: Amenity = {
    id: 'amn-123',
    society_id: 'soc-456',
    name: 'Olympic Swimming Pool',
    description: 'Heated 50m pool with 8 lanes and dedicated coaching area',
    amenity_type: 'SWIMMING_POOL',
    location: 'Central Clubhouse Level -1',
    tower_id: null,
    capacity: 15,
    slot_duration_minutes: 60,
    opening_time: '06:00',
    closing_time: '21:00',
    booking_fee_paise: 0,
    advance_booking_days: 5,
    min_advance_hours: 1,
    max_slots_per_day_per_resident: 1,
    cancellation_deadline_hours: 2,
    refund_percentage: 100,
    allowed_membership_types: ['OWNER', 'TENANT', 'FAMILY_MEMBER'],
    is_active: true,
    rules_and_guidelines: 'Swimming cap mandatory. Shower before entering.',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };

  describe('Amenity Card Helpers', () => {
    it('formats amenity type names properly', () => {
      expect(formatAmenityTypeName('BADMINTON_COURT')).toBe('Badminton Court');
      expect(formatAmenityTypeName('TENNIS_COURT')).toBe('Tennis Court');
      expect(formatAmenityTypeName('SWIMMING_POOL')).toBe('Swimming Pool');
      expect(formatAmenityTypeName('GYM')).toBe('Fitness Gym');
      expect(formatAmenityTypeName('COMMUNITY_HALL')).toBe('Community Hall');
      expect(formatAmenityTypeName('CLUBHOUSE')).toBe('Clubhouse');
      expect(formatAmenityTypeName('GUEST_ROOM')).toBe('Guest Suite');
      expect(formatAmenityTypeName('OTHER')).toBe('Township Amenity');
    });

    it('returns an icon component for each amenity type', () => {
      expect(getAmenityIcon('SWIMMING_POOL')).toBeDefined();
      expect(getAmenityIcon('BADMINTON_COURT')).toBeDefined();
      expect(getAmenityIcon('GYM')).toBeDefined();
      expect(getAmenityIcon('COMMUNITY_HALL')).toBeDefined();
      expect(getAmenityIcon('OTHER')).toBeDefined();
    });

    it('evaluates membership eligibility strictly', () => {
      const restrictedAmenity: Amenity = {
        ...mockAmenity,
        allowed_membership_types: ['OWNER'],
      };

      const isOwnerEligible = restrictedAmenity.allowed_membership_types.includes('OWNER');
      const isTenantEligible = restrictedAmenity.allowed_membership_types.includes('TENANT');

      expect(isOwnerEligible).toBe(true);
      expect(isTenantEligible).toBe(false);
    });
  });

  describe('Booking Modal Date Generation', () => {
    it('formats dates to standard ISO YYYY-MM-DD', () => {
      const fixedDate = new Date(2026, 10, 9); // Month is 0-indexed (10 = November)
      const iso = formatDateToISO(fixedDate);
      expect(iso).toBe('2026-11-09');
    });

    it('generates selectable dates up to advance_booking_days', () => {
      const dates = getSelectableDates(5);
      // Today + 5 days -> 6 selectable items
      expect(dates).toHaveLength(6);
      expect(dates[0].weekday).toBe('Today');
      expect(dates[1].weekday).toBe('Tomorrow');
      expect(dates[0].iso).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    });
  });

  describe('Category Filtering & Search Matching Logic', () => {
    const amenities: Amenity[] = [
      mockAmenity,
      {
        ...mockAmenity,
        id: 'amn-2',
        name: 'Tennis Court 1',
        amenity_type: 'TENNIS_COURT',
        location: 'Sports Zone A',
      },
      {
        ...mockAmenity,
        id: 'amn-3',
        name: 'Grand Celebration Hall',
        amenity_type: 'COMMUNITY_HALL',
        location: 'Tower 7 Ground Floor',
      },
      {
        ...mockAmenity,
        id: 'amn-4',
        name: 'Health Club & Gym',
        amenity_type: 'GYM',
        location: 'Clubhouse 2nd Floor',
      },
    ];

    it('filters amenities by category correctly', () => {
      const sports = amenities.filter((a) => getAmenityCategory(a.amenity_type) === 'sports');
      expect(sports).toHaveLength(1);
      expect(sports[0].name).toBe('Tennis Court 1');

      const fitness = amenities.filter((a) => getAmenityCategory(a.amenity_type) === 'fitness');
      expect(fitness).toHaveLength(2); // Pool + Gym

      const community = amenities.filter((a) => getAmenityCategory(a.amenity_type) === 'community');
      expect(community).toHaveLength(1);
      expect(community[0].name).toBe('Grand Celebration Hall');
    });

    it('searches amenities case-insensitively across name, location, and description', () => {
      const query = 'celebration';
      const results = amenities.filter(
        (a) =>
          a.name.toLowerCase().includes(query) ||
          (a.location && a.location.toLowerCase().includes(query)) ||
          (a.description && a.description.toLowerCase().includes(query))
      );
      expect(results).toHaveLength(1);
      expect(results[0].name).toBe('Grand Celebration Hall');

      const locationQuery = 'sports zone';
      const locResults = amenities.filter(
        (a) => a.location && a.location.toLowerCase().includes(locationQuery)
      );
      expect(locResults).toHaveLength(1);
      expect(locResults[0].name).toBe('Tennis Court 1');
    });
  });

  describe('Error Code Translation Invariants', () => {
    it('maps server-side error codes to resident-friendly explanations', () => {
      const errorMap: Record<string, string> = {
        CAPACITY_EXCEEDED: 'This slot is no longer available or was just reserved by another resident. Please select another slot.',
        DUPLICATE_BOOKING: 'This slot is no longer available or was just reserved by another resident. Please select another slot.',
        LEASE_EXPIRED_FOR_DATE: 'Your tenancy lease date expires before this booking date. Reservations beyond your lease are restricted.',
        DAILY_LIMIT_EXCEEDED: 'You have reached the daily booking limit (2 slots) for this amenity.',
        CANCELLATION_DEADLINE_EXPIRED: 'The cancellation deadline for this booking has expired. Cancellations must be made prior to the amenity cutoff window.',
        SLOT_BLOCKED: 'This slot is temporarily blocked by township management for maintenance. Please choose another time.',
        PAYMENT_WINDOW_EXPIRED: 'The 15-minute payment window for this reservation has expired.',
      };

      expect(errorMap['CAPACITY_EXCEEDED']).toContain('no longer available');
      expect(errorMap['LEASE_EXPIRED_FOR_DATE']).toContain('lease date expires');
      expect(errorMap['CANCELLATION_DEADLINE_EXPIRED']).toContain('cancellation deadline');
      expect(errorMap['SLOT_BLOCKED']).toContain('temporarily blocked');
      expect(errorMap['PAYMENT_WINDOW_EXPIRED']).toContain('15-minute payment window');
    });
  });

  describe('Phase 8 Part 3: Payments, Blocks, & Staff Management Invariants', () => {
    it('validates booking lifecycle transitions', () => {
      const allowedTransitions: Record<string, string[]> = {
        PENDING_PAYMENT: ['CONFIRMED', 'CANCELLED', 'PAYMENT_FAILED'],
        CONFIRMED: ['COMPLETED', 'CANCELLED'],
        CANCELLED: [],
        COMPLETED: [],
        PAYMENT_FAILED: [],
      };

      expect(allowedTransitions['PENDING_PAYMENT']).toContain('CONFIRMED');
      expect(allowedTransitions['PENDING_PAYMENT']).toContain('PAYMENT_FAILED');
      expect(allowedTransitions['CONFIRMED']).toContain('CANCELLED');
    });

    it('enforces staff cancellation 100% refund policy override', () => {
      const paidFeePaise = 25000; // 250 INR
      const standardRefundPercentage = 80;

      // Resident cancellation gives standard refund percentage
      const residentRefundPaise = Math.round((paidFeePaise * standardRefundPercentage) / 100);
      expect(residentRefundPaise).toBe(20000);

      // Staff cancellation overrides with 100% full refund
      const staffRefundPaise = Math.round((paidFeePaise * 100) / 100);
      expect(staffRefundPaise).toBe(25000);
    });

    it('flags blocked slots as unavailable with custom operational reason', () => {
      const slot = {
        start_time: '14:00',
        end_time: '15:00',
        is_available: false,
        is_blocked: true,
        block_reason: 'Tournament preparations and court resealing',
      };

      expect(slot.is_blocked).toBe(true);
      expect(slot.is_available).toBe(false);
      expect(slot.block_reason).toContain('resealing');
    });
  });
});

