import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Calendar,
  Clock,
  Ban,
  Receipt,
  Loader2,
} from 'lucide-react';
import { AmenityBooking, BookingStatus } from '../../../types/amenities';
import { FlatMembership } from '../../../types';
import {
  amenityService,
  formatAmenityFee,
  formatTimeRange,
} from '../../../services/amenityService';
import { formatDateIST, formatINR } from '../../../services/billingService';
import { ApiClientError } from '../../../services/apiClient';
import { Card, CardContent } from '../../../components/ui/Card';
import { Badge } from '../../../components/ui/Badge';
import { Button } from '../../../components/ui/Button';
import { Skeleton } from '../../../components/ui/Skeleton';
import { Alert } from '../../../components/ui/Alert';

interface MyBookingsListProps {
  selectedFlat: FlatMembership;
  onBrowseAmenities: () => void;
}

type BookingFilterTab = 'upcoming' | 'completed' | 'cancelled' | 'all';

export const MyBookingsList: React.FC<MyBookingsListProps> = ({
  selectedFlat,
  onBrowseAmenities,
}) => {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<BookingFilterTab>('upcoming');

  // Cancel dialog state
  const [bookingToCancel, setBookingToCancel] = useState<AmenityBooking | null>(null);
  const [cancelReason, setCancelReason] = useState<string>('');
  const [cancelError, setCancelError] = useState<string | null>(null);

  // Fetch resident bookings
  const {
    data: bookingsData,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['my-amenity-bookings', selectedFlat.society_id, activeTab],
    queryFn: async () => {
      let statusParam: BookingStatus | undefined = undefined;
      let upcomingParam: boolean | undefined = undefined;

      if (activeTab === 'upcoming') {
        upcomingParam = true;
      } else if (activeTab === 'completed') {
        statusParam = 'COMPLETED';
      } else if (activeTab === 'cancelled') {
        statusParam = 'CANCELLED';
      }

      return amenityService.getMyBookings({
        status: statusParam,
        upcomingOnly: upcomingParam,
        societyId: selectedFlat.society_id,
        pageSize: 50,
      });
    },
  });

  // Cancel mutation
  const cancelMutation = useMutation({
    mutationFn: async ({ bookingId, reason }: { bookingId: string; reason?: string }) => {
      return amenityService.cancelBooking(
        bookingId,
        { reason: reason?.trim() || null },
        selectedFlat.society_id
      );
    },
    onSuccess: () => {
      setBookingToCancel(null);
      setCancelReason('');
      setCancelError(null);
      void queryClient.invalidateQueries({ queryKey: ['my-amenity-bookings'] });
    },
    onError: (err: unknown) => {
      if (err instanceof ApiClientError) {
        if (err.code === 'CANCELLATION_DEADLINE_EXPIRED') {
          setCancelError(
            'The cancellation deadline for this booking has expired. Cancellations must be made prior to the amenity cutoff window.'
          );
        } else {
          setCancelError(err.message);
        }
      } else {
        setCancelError('Failed to cancel booking. Please try again.');
      }
    },
  });

  const bookings = bookingsData?.items || [];

  return (
    <div className="space-y-6">
      {/* Sub-Tabs */}
      <div className="flex border-b border-slate-200 gap-6">
        <button
          onClick={() => setActiveTab('upcoming')}
          className={`pb-3 text-xs font-semibold tracking-wider transition-colors border-b-2 ${
            activeTab === 'upcoming'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-slate-500 hover:text-slate-700'
          }`}
        >
          Upcoming Bookings
        </button>
        <button
          onClick={() => setActiveTab('completed')}
          className={`pb-3 text-xs font-semibold tracking-wider transition-colors border-b-2 ${
            activeTab === 'completed'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-slate-500 hover:text-slate-700'
          }`}
        >
          Completed
        </button>
        <button
          onClick={() => setActiveTab('cancelled')}
          className={`pb-3 text-xs font-semibold tracking-wider transition-colors border-b-2 ${
            activeTab === 'cancelled'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-slate-500 hover:text-slate-700'
          }`}
        >
          Cancelled
        </button>
        <button
          onClick={() => setActiveTab('all')}
          className={`pb-3 text-xs font-semibold tracking-wider transition-colors border-b-2 ${
            activeTab === 'all'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-slate-500 hover:text-slate-700'
          }`}
        >
          All
        </button>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, idx) => (
            <Skeleton key={idx} className="h-28 rounded-xl" />
          ))}
        </div>
      ) : error ? (
        <Alert variant="error" title="Error loading bookings">
          <p>Unable to retrieve your bookings. Please try again.</p>
          <Button variant="outline" size="sm" className="mt-2 text-xs" onClick={() => void refetch()}>
            Retry
          </Button>
        </Alert>
      ) : bookings.length === 0 ? (
        <div className="text-center py-12 bg-white rounded-2xl border border-dashed border-slate-200 p-6 space-y-3">
          <div className="w-12 h-12 rounded-full bg-slate-100 text-slate-400 mx-auto flex items-center justify-center">
            <Calendar className="h-6 w-6" />
          </div>
          <div>
            <h4 className="text-sm font-semibold text-slate-900">
              {activeTab === 'upcoming'
                ? 'No Upcoming Reservations'
                : 'No Booking Records Found'}
            </h4>
            <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
              {activeTab === 'upcoming'
                ? 'You do not have any active upcoming amenity bookings. Discover and reserve facilities available in your township.'
                : 'No bookings match this category.'}
            </p>
          </div>
          <div className="pt-2">
            <Button variant="primary" size="sm" onClick={onBrowseAmenities} className="text-xs font-semibold">
              Browse Amenities
            </Button>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {bookings.map((booking) => {
            const isConfirmed = booking.status === 'CONFIRMED';
            const isCancelled = booking.status === 'CANCELLED';

            return (
              <Card key={booking.id} className="border-slate-200 hover:shadow-sm transition-shadow">
                <CardContent className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div className="space-y-2">
                    {/* Header */}
                    <div className="flex items-center gap-2.5 flex-wrap">
                      <h4 className="text-sm font-bold text-slate-900">
                        {booking.amenity_name || 'Township Amenity'}
                      </h4>
                      <Badge
                        variant={
                          isConfirmed
                            ? 'success'
                            : isCancelled
                            ? 'danger'
                            : 'neutral'
                        }
                      >
                        {booking.status}
                      </Badge>
                      <span className="text-[11px] font-mono text-slate-400 bg-slate-100 px-2 py-0.5 rounded">
                        REF: {booking.id.substring(0, 8).toUpperCase()}
                      </span>
                    </div>

                    {/* Meta info */}
                    <div className="flex items-center gap-4 text-xs text-slate-600 flex-wrap">
                      <div className="flex items-center gap-1.5">
                        <Calendar className="h-3.5 w-3.5 text-slate-400" />
                        <span>{formatDateIST(booking.booking_date)}</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Clock className="h-3.5 w-3.5 text-slate-400" />
                        <span>{formatTimeRange(booking.start_time, booking.end_time)}</span>
                      </div>
                      <div className="flex items-center gap-1.5 font-medium">
                        <Receipt className="h-3.5 w-3.5 text-slate-400" />
                        <span>{formatAmenityFee(booking.booking_fee_paise)}</span>
                      </div>
                    </div>

                    {/* Refund or Cancellation details */}
                    {isCancelled && (
                      <div className="text-xs text-rose-700 bg-rose-50/70 px-3 py-1.5 rounded-lg border border-rose-100 flex items-center justify-between gap-2 flex-wrap">
                        <span>Reason: {booking.cancellation_reason || 'Cancelled'}</span>
                        {booking.refund_amount_paise > 0 && (
                          <span className="font-semibold">
                            Refund: {formatINR(booking.refund_amount_paise)}
                          </span>
                        )}
                      </div>
                    )}

                    {/* Notes */}
                    {booking.notes && (
                      <p className="text-xs text-slate-500 italic">
                        &quot;{booking.notes}&quot;
                      </p>
                    )}
                  </div>

                  {/* Actions */}
                  {isConfirmed && (
                    <div className="shrink-0 flex items-center sm:self-center">
                      <Button
                        variant="outline"
                        size="sm"
                        className="text-xs text-rose-600 border-rose-200 hover:bg-rose-50 hover:border-rose-300"
                        onClick={() => {
                          setBookingToCancel(booking);
                          setCancelReason('');
                          setCancelError(null);
                        }}
                      >
                        Cancel Booking
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Cancellation Confirmation Modal */}
      {bookingToCancel && (
        <div
          className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4"
          role="dialog"
          aria-modal="true"
        >
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-slate-100 space-y-4 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-rose-100 text-rose-600 flex items-center justify-center shrink-0">
                <Ban className="h-5 w-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-900">Cancel Reservation</h3>
                <p className="text-xs text-slate-500">
                  {bookingToCancel.amenity_name} on {formatDateIST(bookingToCancel.booking_date)}
                </p>
              </div>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed">
              Are you sure you want to cancel this booking? If the slot falls within the cancellation policy window, eligible refunds will be issued automatically.
            </p>

            <div>
              <label htmlFor="cancel-reason" className="block text-xs font-semibold text-slate-700 mb-1">
                Reason for cancellation (Optional)
              </label>
              <input
                id="cancel-reason"
                type="text"
                maxLength={500}
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                placeholder="e.g. Schedule change, unwell"
                className="w-full text-xs px-3 py-2 rounded-lg border border-slate-200 focus:outline-none focus:ring-1 focus:ring-rose-500"
              />
            </div>

            {cancelError && (
              <Alert variant="error" title="Cancellation Failed">
                {cancelError}
              </Alert>
            )}

            <div className="flex items-center justify-end gap-2 pt-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setBookingToCancel(null)}
                disabled={cancelMutation.isPending}
              >
                Keep Booking
              </Button>
              <Button
                variant="danger"
                size="sm"
                disabled={cancelMutation.isPending}
                onClick={() =>
                  cancelMutation.mutate({
                    bookingId: bookingToCancel.id,
                    reason: cancelReason,
                  })
                }
                className="flex items-center gap-1.5"
              >
                {cancelMutation.isPending ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    <span>Cancelling...</span>
                  </>
                ) : (
                  <span>Confirm Cancellation</span>
                )}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
