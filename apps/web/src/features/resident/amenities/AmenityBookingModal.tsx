import React, { useCallback, useEffect, useState } from 'react';
import {
  X,
  Clock,
  ShieldCheck,
  CheckCircle2,
  Loader2,
  MapPin,
} from 'lucide-react';
import {
  Amenity,
  AmenityBooking,
  TimeSlotAvailability,
} from '../../../types/amenities';
import { FlatMembership } from '../../../types';
import {
  amenityService,
  formatAmenityFee,
  formatTimeRange,
} from '../../../services/amenityService';
import { ApiClientError } from '../../../services/apiClient';
import { Button } from '../../../components/ui/Button';
import { Badge } from '../../../components/ui/Badge';
import { Alert } from '../../../components/ui/Alert';
import { Skeleton } from '../../../components/ui/Skeleton';

interface AmenityBookingModalProps {
  amenity: Amenity;
  selectedFlat: FlatMembership;
  onClose: () => void;
  onBookingSuccess: (booking: AmenityBooking) => void;
}

export function formatDateToISO(date: Date): string {
  const year = date.getFullYear();
  const month = (date.getMonth() + 1).toString().padStart(2, '0');
  const day = date.getDate().toString().padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function getSelectableDates(advanceDays: number): { iso: string; label: string; weekday: string }[] {
  const dates = [];
  const today = new Date();

  for (let i = 0; i <= advanceDays; i++) {
    const d = new Date(today);
    d.setDate(today.getDate() + i);
    const iso = formatDateToISO(d);

    let weekday = d.toLocaleDateString('en-IN', { weekday: 'short' });
    if (i === 0) weekday = 'Today';
    else if (i === 1) weekday = 'Tomorrow';

    const label = d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
    dates.push({ iso, label, weekday });
  }

  return dates;
}

export const AmenityBookingModal: React.FC<AmenityBookingModalProps> = ({
  amenity,
  selectedFlat,
  onClose,
  onBookingSuccess,
}) => {
  const selectableDates = getSelectableDates(amenity.advance_booking_days);

  // States
  const [selectedDate, setSelectedDate] = useState<string>(selectableDates[0]?.iso || formatDateToISO(new Date()));
  const [slots, setSlots] = useState<TimeSlotAvailability[]>([]);
  const [selectedSlot, setSelectedSlot] = useState<TimeSlotAvailability | null>(null);
  const [notes, setNotes] = useState<string>('');
  const [autoPay, setAutoPay] = useState<boolean>(true);
  const [simulateFailure, setSimulateFailure] = useState<boolean>(false);

  const [isLoadingSlots, setIsLoadingSlots] = useState<boolean>(true);
  const [slotError, setSlotError] = useState<string | null>(null);

  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const [confirmedBooking, setConfirmedBooking] = useState<AmenityBooking | null>(null);

  // Fetch slots for selected date
  const loadSlots = useCallback(async (dateStr: string) => {
    setIsLoadingSlots(true);
    setSlotError(null);
    setSelectedSlot(null);
    try {
      const resp = await amenityService.getAvailableSlots(
        amenity.id,
        dateStr,
        selectedFlat.society_id
      );
      setSlots(resp.slots);
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setSlotError(err.message);
      } else {
        setSlotError('Unable to load available slots. Please try again.');
      }
    } finally {
      setIsLoadingSlots(false);
    }
  }, [amenity.id, selectedFlat.society_id]);

  useEffect(() => {
    void loadSlots(selectedDate);
  }, [selectedDate, loadSlots]);

  // Handle booking submission
  const handleConfirmBooking = async () => {
    if (!selectedSlot) return;

    setIsSubmitting(true);
    setSubmitError(null);

    try {
      const isPaid = amenity.booking_fee_paise > 0;
      const shouldUseAutoPay = isPaid && autoPay && !simulateFailure;

      let booking = await amenityService.createBooking(
        amenity.id,
        {
          flat_id: selectedFlat.flat_id,
          booking_date: selectedDate,
          start_time: selectedSlot.start_time,
          end_time: selectedSlot.end_time,
          booked_units: 1,
          notes: notes.trim() || null,
          auto_pay: shouldUseAutoPay,
        },
        selectedFlat.society_id
      );

      // If user opted to test simulated payment failure
      if (isPaid && autoPay && simulateFailure) {
        booking = await amenityService.payBooking(
          booking.id,
          { simulate_failure: true },
          selectedFlat.society_id
        );
      }

      setConfirmedBooking(booking);
      onBookingSuccess(booking);
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        if (err.code === 'CAPACITY_EXCEEDED' || err.code === 'DUPLICATE_BOOKING') {
          setSubmitError(
            'This slot is no longer available or was just reserved by another resident. Please select another slot.'
          );
          // Refresh slots to show updated state
          void loadSlots(selectedDate);
        } else if (err.code === 'SLOT_BLOCKED') {
          setSubmitError(
            'This slot is temporarily blocked by township management for maintenance. Please choose another time.'
          );
          void loadSlots(selectedDate);
        } else if (err.code === 'LEASE_EXPIRED_FOR_DATE') {
          setSubmitError(
            'Your tenancy lease date expires before this booking date. Reservations beyond your lease are restricted.'
          );
        } else if (err.code === 'DAILY_LIMIT_EXCEEDED') {
          setSubmitError(
            `You have reached the daily booking limit (${amenity.max_slots_per_day_per_resident} slots) for this amenity.`
          );
        } else {
          setSubmitError(err.message);
        }
      } else {
        setSubmitError('Failed to confirm booking. Please check your connection and try again.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4 sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="booking-modal-title"
    >
      <div className="bg-white rounded-2xl max-w-2xl w-full max-h-[90vh] flex flex-col shadow-2xl border border-slate-100 overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Modal Top Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/70">
          <div>
            <h2 id="booking-modal-title" className="text-lg font-bold text-slate-900">
              {confirmedBooking ? 'Booking Confirmed' : `Reserve ${amenity.name}`}
            </h2>
            <div className="flex items-center gap-3 text-xs text-slate-500 mt-0.5">
              {amenity.location && (
                <span className="flex items-center gap-1">
                  <MapPin className="h-3.5 w-3.5 text-slate-400" />
                  {amenity.location}
                </span>
              )}
              <span>•</span>
              <span>{amenity.slot_duration_minutes} min duration</span>
              <span>•</span>
              <span className="font-semibold text-slate-700">
                {formatAmenityFee(amenity.booking_fee_paise)}
              </span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-200/60 transition-colors"
            aria-label="Close dialog"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Modal Content Body */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1">
          {/* Confirmed Booking Screen */}
          {confirmedBooking ? (
            <div className="text-center py-6 space-y-5">
              <div className={`w-16 h-16 rounded-full mx-auto flex items-center justify-center ${
                confirmedBooking.status === 'CONFIRMED'
                  ? 'bg-emerald-100 text-emerald-600'
                  : confirmedBooking.status === 'PENDING_PAYMENT'
                  ? 'bg-amber-100 text-amber-600'
                  : 'bg-rose-100 text-rose-600'
              }`}>
                {confirmedBooking.status === 'CONFIRMED' ? (
                  <CheckCircle2 className="h-9 w-9" />
                ) : confirmedBooking.status === 'PENDING_PAYMENT' ? (
                  <Clock className="h-9 w-9" />
                ) : (
                  <X className="h-9 w-9" />
                )}
              </div>
              <div>
                <h3 className="text-xl font-bold text-slate-900">
                  {confirmedBooking.status === 'CONFIRMED'
                    ? 'Reservation Confirmed!'
                    : confirmedBooking.status === 'PENDING_PAYMENT'
                    ? 'Slot Reserved (Payment Pending)'
                    : 'Payment Failed'}
                </h3>
                <p className="text-sm text-slate-500 mt-1">
                  {confirmedBooking.status === 'CONFIRMED'
                    ? `Your time slot at ${amenity.name} has been booked.`
                    : confirmedBooking.status === 'PENDING_PAYMENT'
                    ? 'Your booking is temporarily on hold for 15 minutes. Please complete payment to confirm.'
                    : 'The test payment failed. Your reservation could not be confirmed.'}
                </p>
              </div>

              {/* Confirmation Details Card */}
              <div className="bg-slate-50 rounded-xl p-4 max-w-md mx-auto text-left text-xs space-y-2.5 border border-slate-200/80">
                <div className="flex justify-between py-1 border-b border-slate-200/60">
                  <span className="text-slate-500">Booking Reference</span>
                  <span className="font-mono font-semibold text-slate-800">
                    {confirmedBooking.id.substring(0, 8).toUpperCase()}
                  </span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-200/60">
                  <span className="text-slate-500">Date</span>
                  <span className="font-medium text-slate-800">{confirmedBooking.booking_date}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-200/60">
                  <span className="text-slate-500">Time Slot</span>
                  <span className="font-medium text-slate-800">
                    {formatTimeRange(confirmedBooking.start_time, confirmedBooking.end_time)}
                  </span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-200/60">
                  <span className="text-slate-500">Flat</span>
                  <span className="font-medium text-slate-800">
                    {selectedFlat.tower_number}-{selectedFlat.flat_number}
                  </span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-200/60">
                  <span className="text-slate-500">Booking Status</span>
                  <Badge
                    variant={
                      confirmedBooking.status === 'CONFIRMED'
                        ? 'success'
                        : confirmedBooking.status === 'PENDING_PAYMENT'
                        ? 'warning'
                        : 'danger'
                    }
                  >
                    {confirmedBooking.status}
                  </Badge>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-slate-500">Payment Status</span>
                  <Badge
                    variant={
                      confirmedBooking.payment_status === 'PAID'
                        ? 'success'
                        : confirmedBooking.payment_status === 'FREE'
                        ? 'neutral'
                        : confirmedBooking.payment_status === 'PENDING'
                        ? 'warning'
                        : 'danger'
                    }
                  >
                    {confirmedBooking.payment_status}
                  </Badge>
                </div>
              </div>

              <div className="pt-3">
                <Button variant="primary" className="w-full sm:w-auto px-8" onClick={onClose}>
                  Done
                </Button>
              </div>
            </div>
          ) : (
            <>
              {/* Step 1: Date Selector Bar */}
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-2">
                  Select Booking Date
                </label>
                <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-none">
                  {selectableDates.map((item) => {
                    const isSelected = item.iso === selectedDate;
                    return (
                      <button
                        key={item.iso}
                        type="button"
                        onClick={() => setSelectedDate(item.iso)}
                        className={`shrink-0 flex flex-col items-center justify-center px-4 py-2.5 rounded-xl border text-xs transition-all ${
                          isSelected
                            ? 'bg-indigo-600 border-indigo-600 text-white font-semibold shadow-sm'
                            : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-50'
                        }`}
                      >
                        <span className={`text-[10px] uppercase ${isSelected ? 'text-indigo-100' : 'text-slate-400'}`}>
                          {item.weekday}
                        </span>
                        <span className="text-sm font-bold mt-0.5">{item.label}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Step 2: Time Slots Grid */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-semibold text-slate-700 uppercase tracking-wider">
                    Available Time Slots
                  </label>
                  <span className="text-xs text-slate-500">
                    Operating Hours: {amenity.opening_time} – {amenity.closing_time}
                  </span>
                </div>

                {isLoadingSlots ? (
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
                    {Array.from({ length: 6 }).map((_, idx) => (
                      <Skeleton key={idx} className="h-16 rounded-xl" />
                    ))}
                  </div>
                ) : slotError ? (
                  <Alert variant="error" title="Could not load slots">
                    <p>{slotError}</p>
                    <Button
                      variant="outline"
                      size="sm"
                      className="mt-2 text-xs"
                      onClick={() => void loadSlots(selectedDate)}
                    >
                      Retry
                    </Button>
                  </Alert>
                ) : slots.length === 0 ? (
                  <div className="text-center py-8 bg-slate-50 rounded-xl border border-dashed border-slate-200">
                    <Clock className="h-8 w-8 text-slate-400 mx-auto mb-2" />
                    <p className="text-xs text-slate-600">No slots available on this date.</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 max-h-56 overflow-y-auto pr-1">
                    {slots.map((slot) => {
                      const isSelected = selectedSlot?.start_time === slot.start_time;
                      const isUnavailable = !slot.is_available;

                      return (
                        <button
                          key={slot.start_time}
                          type="button"
                          disabled={isUnavailable}
                          onClick={() => setSelectedSlot(slot)}
                          className={`p-3 rounded-xl border text-left flex flex-col justify-between transition-all ${
                            isSelected
                              ? 'border-indigo-600 bg-indigo-50/70 ring-1 ring-indigo-600'
                              : isUnavailable
                              ? 'border-slate-200 bg-slate-100/70 text-slate-400 cursor-not-allowed opacity-60'
                              : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <span className={`text-xs font-semibold ${isSelected ? 'text-indigo-900' : 'text-slate-800'}`}>
                              {formatTimeRange(slot.start_time, slot.end_time)}
                            </span>
                            {slot.user_booked && (
                              <CheckCircle2 className="h-3.5 w-3.5 text-indigo-600" />
                            )}
                          </div>
                          <div className="mt-2 text-[11px] flex items-center justify-between">
                            {slot.user_booked ? (
                              <span className="text-indigo-700 font-medium">You booked this</span>
                            ) : slot.is_past ? (
                              <span className="text-slate-400">Past slot</span>
                            ) : slot.is_blocked ? (
                              <span className="text-amber-600 font-medium truncate" title={slot.block_reason || 'Maintenance'}>
                                {slot.block_reason || 'Maintenance'}
                              </span>
                            ) : slot.remaining_capacity === 0 ? (
                              <span className="text-rose-500 font-medium">Fully booked</span>
                            ) : (
                              <span className="text-emerald-600 font-medium flex items-center gap-1">
                                {amenity.capacity > 1
                                  ? `${slot.remaining_capacity} left`
                                  : 'Available'}
                              </span>
                            )}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Step 3: Review Details & Confirmation */}
              {selectedSlot && (
                <div className="bg-slate-50 rounded-xl p-4 border border-slate-200 space-y-3 animate-in fade-in duration-200">
                  <h4 className="text-xs font-semibold text-slate-800 uppercase tracking-wider">
                    Booking Summary
                  </h4>

                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-slate-500 block">Flat Unit:</span>
                      <span className="font-semibold text-slate-800">
                        {selectedFlat.tower_number}-{selectedFlat.flat_number} ({selectedFlat.membership_type})
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block">Total Fee:</span>
                      <span className="font-semibold text-emerald-700 text-sm">
                        {formatAmenityFee(amenity.booking_fee_paise)}
                      </span>
                    </div>
                  </div>

                  {/* Cancellation & Policy Recap */}
                  <div className="flex items-start gap-2 text-[11px] text-slate-500 pt-1 border-t border-slate-200/60">
                    <ShieldCheck className="h-3.5 w-3.5 text-slate-400 shrink-0 mt-0.5" />
                    <span>
                      Cancellations allowed up to {amenity.cancellation_deadline_hours} hour(s) before slot start for a {amenity.refund_percentage}% refund.
                    </span>
                  </div>

                  {/* Notes input */}
                  <div>
                    <label htmlFor="booking-notes" className="block text-[11px] font-medium text-slate-600 mb-1">
                      Notes / Guest details (Optional)
                    </label>
                    <input
                      id="booking-notes"
                      type="text"
                      maxLength={500}
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      placeholder="e.g. Practice session with coach"
                      className="w-full text-xs px-3 py-2 rounded-lg border border-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 bg-white"
                    />
                  </div>

                  {/* Payment Options (When fee > 0) */}
                  {amenity.booking_fee_paise > 0 && (
                    <div className="pt-2 border-t border-slate-200/60 space-y-2">
                      <div className="flex items-center justify-between p-2.5 bg-white rounded-lg border border-slate-200 text-xs">
                        <div>
                          <span className="font-semibold text-slate-800 block">Instant Payment (Simulation)</span>
                          <span className="text-slate-500 text-[11px]">Execute payment immediately via simulated provider</span>
                        </div>
                        <input
                          type="checkbox"
                          checked={autoPay}
                          onChange={(e) => setAutoPay(e.target.checked)}
                          className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 cursor-pointer"
                        />
                      </div>

                      {autoPay ? (
                        <label className="flex items-center gap-2 text-[11px] text-slate-500 cursor-pointer pl-1">
                          <input
                            type="checkbox"
                            checked={simulateFailure}
                            onChange={(e) => setSimulateFailure(e.target.checked)}
                            className="rounded border-slate-300 text-rose-600 focus:ring-rose-500 cursor-pointer"
                          />
                          <span>Simulate Payment Failure (Test Mode)</span>
                        </label>
                      ) : (
                        <p className="text-[11px] text-amber-700 bg-amber-50 p-2 rounded border border-amber-100">
                          Slot will be held in PENDING PAYMENT status for 15 minutes. You can pay anytime before it expires.
                        </p>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Guidelines snippet */}
              {amenity.rules_and_guidelines && (
                <div className="text-[11px] text-slate-500 bg-slate-50/60 p-3 rounded-lg border border-slate-100">
                  <span className="font-semibold text-slate-700 block mb-0.5">Rules & Guidelines:</span>
                  <p className="line-clamp-2">{amenity.rules_and_guidelines}</p>
                </div>
              )}

              {/* Submit Error Alert */}
              {submitError && (
                <Alert variant="error" title="Reservation Failed">
                  {submitError}
                </Alert>
              )}
            </>
          )}
        </div>

        {/* Modal Bottom Actions */}
        {!confirmedBooking && (
          <div className="px-6 py-4 border-t border-slate-100 bg-slate-50/70 flex items-center justify-between gap-3">
            <Button variant="outline" size="sm" onClick={onClose} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              disabled={!selectedSlot || isSubmitting}
              onClick={handleConfirmBooking}
              className="flex items-center gap-1.5 px-6 font-semibold"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>Reserving...</span>
                </>
              ) : (
                <span>Confirm Booking</span>
              )}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
};
