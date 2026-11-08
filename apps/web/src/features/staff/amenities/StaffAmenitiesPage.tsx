import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Building2,
  CalendarCheck,
  Search,
  Plus,
  Ban,
  CheckCircle2,
  Eye,
  AlertTriangle,
  Loader2,
  Trash2,
} from 'lucide-react';
import {
  Amenity,
  AmenityBooking,
  AmenityType,
  BookingPaymentStatus,
  BookingStatus,
  CreateAmenityBlockRequest,
  CreateAmenityRequest,
  UpdateAmenityRequest,
} from '../../../types/amenities';
import {
  amenityService,
  formatAmenityFee,
  formatSlotTime,
  formatTimeRange,
  getAmenityCategory,
} from '../../../services/amenityService';
import { formatDateIST, formatINR } from '../../../services/billingService';
import { ApiClientError } from '../../../services/apiClient';
import { Card, CardContent } from '../../../components/ui/Card';
import { Badge } from '../../../components/ui/Badge';
import { Button } from '../../../components/ui/Button';
import { Skeleton } from '../../../components/ui/Skeleton';
import { Alert } from '../../../components/ui/Alert';

const AMENITY_TYPES: { label: string; value: AmenityType }[] = [
  { label: 'Clubhouse', value: 'CLUBHOUSE' },
  { label: 'Badminton Court', value: 'BADMINTON_COURT' },
  { label: 'Tennis Court', value: 'TENNIS_COURT' },
  { label: 'Swimming Pool', value: 'SWIMMING_POOL' },
  { label: 'Gymnasium', value: 'GYM' },
  { label: 'Community Hall', value: 'COMMUNITY_HALL' },
  { label: 'Guest Room', value: 'GUEST_ROOM' },
  { label: 'Other Facility', value: 'OTHER' },
];

export const StaffAmenitiesPage: React.FC = () => {
  const queryClient = useQueryClient();

  // Active view tab
  const [activeTab, setActiveTab] = useState<'facilities' | 'bookings'>('facilities');

  // Facilities state
  const [editingAmenity, setEditingAmenity] = useState<Amenity | null>(null);
  const [isCreatingAmenity, setIsCreatingAmenity] = useState<boolean>(false);
  const [managingBlocksAmenity, setManagingBlocksAmenity] = useState<Amenity | null>(null);

  // Bookings filter state
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [selectedAmenityFilter, setSelectedAmenityFilter] = useState<string>('');
  const [selectedStatusFilter, setSelectedStatusFilter] = useState<string>('');
  const [selectedPaymentStatusFilter, setSelectedPaymentStatusFilter] = useState<string>('');
  const [selectedDateFilter, setSelectedDateFilter] = useState<string>('');

  // Modals for bookings
  const [inspectingBooking, setInspectingBooking] = useState<AmenityBooking | null>(null);
  const [cancellingBooking, setCancellingBooking] = useState<AmenityBooking | null>(null);
  const [cancelReason, setCancelReason] = useState<string>('');
  const [cancelError, setCancelError] = useState<string | null>(null);

  // Query: Amenities List
  const {
    data: amenitiesData,
    isLoading: isLoadingAmenities,
  } = useQuery({
    queryKey: ['staff-amenities-list'],
    queryFn: () => amenityService.listAmenities(),
  });

  const amenities = amenitiesData?.items || [];

  // Query: Staff Bookings List
  const {
    data: bookingsData,
    isLoading: isLoadingBookings,
  } = useQuery({
    queryKey: [
      'staff-bookings-list',
      searchTerm,
      selectedAmenityFilter,
      selectedStatusFilter,
      selectedPaymentStatusFilter,
      selectedDateFilter,
    ],
    queryFn: () =>
      amenityService.staffListBookings({
        search: searchTerm.trim() || undefined,
        amenity_id: selectedAmenityFilter || undefined,
        status: (selectedStatusFilter as BookingStatus) || undefined,
        payment_status: (selectedPaymentStatusFilter as BookingPaymentStatus) || undefined,
        booking_date: selectedDateFilter || undefined,
        page_size: 100,
      }),
  });

  const bookings = bookingsData?.items || [];

  // Mutation: Toggle Amenity Status
  const toggleStatusMutation = useMutation({
    mutationFn: ({ amenityId, isActive }: { amenityId: string; isActive: boolean }) =>
      amenityService.staffToggleAmenityStatus(amenityId, isActive),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['staff-amenities-list'] });
      void queryClient.invalidateQueries({ queryKey: ['resident-amenities'] });
    },
  });

  // Mutation: Staff Cancel Booking
  const staffCancelMutation = useMutation({
    mutationFn: ({ bookingId, reason }: { bookingId: string; reason: string }) =>
      amenityService.staffCancelBooking(bookingId, { reason }),
    onSuccess: () => {
      setCancellingBooking(null);
      setCancelReason('');
      setCancelError(null);
      void queryClient.invalidateQueries({ queryKey: ['staff-bookings-list'] });
      void queryClient.invalidateQueries({ queryKey: ['my-amenity-bookings'] });
    },
    onError: (err: unknown) => {
      if (err instanceof ApiClientError) {
        setCancelError(err.message);
      } else {
        setCancelError('Failed to cancel booking. Please try again.');
      }
    },
  });

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-indigo-600 font-semibold text-xs tracking-wider uppercase">
            <Building2 className="h-4 w-4" />
            <span>Facility Management</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 mt-1">Amenity Operations</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Configure township facilities, manage maintenance closures, and oversee resident reservations.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="primary"
            size="sm"
            onClick={() => setIsCreatingAmenity(true)}
            className="flex items-center gap-1.5 font-semibold text-xs px-4"
          >
            <Plus className="h-4 w-4" />
            <span>Add Facility</span>
          </Button>
        </div>
      </div>

      {/* Primary Navigation Tabs */}
      <div className="flex border-b border-slate-200 gap-8">
        <button
          onClick={() => setActiveTab('facilities')}
          className={`pb-3.5 text-xs font-bold tracking-wider uppercase flex items-center gap-2 transition-all border-b-2 ${
            activeTab === 'facilities'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-slate-400 hover:text-slate-600'
          }`}
        >
          <Building2 className="h-4 w-4" />
          <span>Facilities Directory ({amenities.length})</span>
        </button>
        <button
          onClick={() => setActiveTab('bookings')}
          className={`pb-3.5 text-xs font-bold tracking-wider uppercase flex items-center gap-2 transition-all border-b-2 ${
            activeTab === 'bookings'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-slate-400 hover:text-slate-600'
          }`}
        >
          <CalendarCheck className="h-4 w-4" />
          <span>Reservations &amp; Payments ({bookingsData?.total ?? 0})</span>
        </button>
      </div>

      {/* TAB 1: Facilities Directory */}
      {activeTab === 'facilities' && (
        <div className="space-y-6">
          {/* Summary stats */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Card className="border-slate-200">
              <CardContent className="p-4 flex items-center justify-between">
                <div>
                  <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block">
                    Total Facilities
                  </span>
                  <span className="text-2xl font-bold text-slate-900 mt-0.5 block">
                    {amenities.length}
                  </span>
                </div>
                <div className="w-10 h-10 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center">
                  <Building2 className="h-5 w-5" />
                </div>
              </CardContent>
            </Card>

            <Card className="border-slate-200">
              <CardContent className="p-4 flex items-center justify-between">
                <div>
                  <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block">
                    Active &amp; Bookable
                  </span>
                  <span className="text-2xl font-bold text-emerald-600 mt-0.5 block">
                    {amenities.filter((a) => a.is_active).length}
                  </span>
                </div>
                <div className="w-10 h-10 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center">
                  <CheckCircle2 className="h-5 w-5" />
                </div>
              </CardContent>
            </Card>

            <Card className="border-slate-200">
              <CardContent className="p-4 flex items-center justify-between">
                <div>
                  <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block">
                    Offline / Inactive
                  </span>
                  <span className="text-2xl font-bold text-slate-500 mt-0.5 block">
                    {amenities.filter((a) => !a.is_active).length}
                  </span>
                </div>
                <div className="w-10 h-10 rounded-xl bg-slate-100 text-slate-500 flex items-center justify-center">
                  <Ban className="h-5 w-5" />
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Facilities Table */}
          {isLoadingAmenities ? (
            <div className="space-y-3">
              {Array.from({ length: 4 }).map((_, idx) => (
                <Skeleton key={idx} className="h-20 rounded-xl" />
              ))}
            </div>
          ) : amenities.length === 0 ? (
            <div className="text-center py-12 bg-white rounded-2xl border border-dashed border-slate-200 p-8 space-y-3">
              <Building2 className="h-10 w-10 text-slate-300 mx-auto" />
              <h3 className="text-sm font-semibold text-slate-900">No Facilities Configured</h3>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                No amenities have been registered for this society yet. Click Add Facility to register your first facility.
              </p>
              <Button
                variant="primary"
                size="sm"
                onClick={() => setIsCreatingAmenity(true)}
                className="text-xs mt-2"
              >
                Add First Facility
              </Button>
            </div>
          ) : (
            <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="bg-slate-50/80 border-b border-slate-200/70 text-slate-600 font-semibold uppercase tracking-wider">
                      <th className="py-3 px-4">Amenity</th>
                      <th className="py-3 px-4">Category</th>
                      <th className="py-3 px-4">Operating Hours</th>
                      <th className="py-3 px-4">Capacity / Slot</th>
                      <th className="py-3 px-4">Booking Fee</th>
                      <th className="py-3 px-4">Status</th>
                      <th className="py-3 px-4 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-700">
                    {amenities.map((amenity) => (
                      <tr key={amenity.id} className="hover:bg-slate-50/60 transition-colors">
                        <td className="py-3.5 px-4 font-semibold text-slate-900">
                          <div>{amenity.name}</div>
                          {amenity.location && (
                            <span className="text-[11px] font-normal text-slate-400">
                              {amenity.location}
                            </span>
                          )}
                        </td>
                        <td className="py-3.5 px-4">
                          <span className="capitalize text-slate-600 font-medium">
                            {getAmenityCategory(amenity.amenity_type)}
                          </span>
                        </td>
                        <td className="py-3.5 px-4 font-mono text-[11px]">
                          {formatSlotTime(amenity.opening_time)} – {formatSlotTime(amenity.closing_time)}
                        </td>
                        <td className="py-3.5 px-4">
                          <div>{amenity.capacity} units</div>
                          <span className="text-[11px] text-slate-400">
                            {amenity.slot_duration_minutes}m duration
                          </span>
                        </td>
                        <td className="py-3.5 px-4 font-medium">
                          {formatAmenityFee(amenity.booking_fee_paise)}
                        </td>
                        <td className="py-3.5 px-4">
                          <Badge variant={amenity.is_active ? 'success' : 'neutral'}>
                            {amenity.is_active ? 'Active' : 'Inactive'}
                          </Badge>
                        </td>
                        <td className="py-3.5 px-4 text-right">
                          <div className="flex items-center justify-end gap-1.5">
                            <Button
                              variant="outline"
                              size="sm"
                              className="text-[11px] h-7 px-2.5"
                              onClick={() => setManagingBlocksAmenity(amenity)}
                              title="Manage Maintenance Blocks"
                            >
                              Blocks
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              className="text-[11px] h-7 px-2.5"
                              onClick={() => setEditingAmenity(amenity)}
                              title="Edit Configuration"
                            >
                              Edit
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              className={`text-[11px] h-7 px-2.5 ${
                                amenity.is_active
                                  ? 'text-amber-700 hover:bg-amber-50 border-amber-200'
                                  : 'text-emerald-700 hover:bg-emerald-50 border-emerald-200'
                              }`}
                              onClick={() =>
                                toggleStatusMutation.mutate({
                                  amenityId: amenity.id,
                                  isActive: !amenity.is_active,
                                })
                              }
                            >
                              {amenity.is_active ? 'Deactivate' : 'Activate'}
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 2: Bookings & Payments Operations */}
      {activeTab === 'bookings' && (
        <div className="space-y-4">
          {/* Filters Bar */}
          <Card className="border-slate-200">
            <CardContent className="p-4 space-y-3">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 text-xs">
                {/* Search */}
                <div className="relative">
                  <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-400" />
                  <input
                    type="text"
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    placeholder="Search flat, name, ref..."
                    className="w-full pl-9 pr-3 py-2 border border-slate-200 rounded-lg text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500 bg-white"
                  />
                </div>

                {/* Amenity filter */}
                <div>
                  <select
                    value={selectedAmenityFilter}
                    onChange={(e) => setSelectedAmenityFilter(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500 bg-white"
                  >
                    <option value="">All Amenities</option>
                    {amenities.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Booking Status */}
                <div>
                  <select
                    value={selectedStatusFilter}
                    onChange={(e) => setSelectedStatusFilter(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500 bg-white"
                  >
                    <option value="">All Booking Statuses</option>
                    <option value="CONFIRMED">CONFIRMED</option>
                    <option value="PENDING_PAYMENT">PENDING PAYMENT</option>
                    <option value="CANCELLED">CANCELLED</option>
                    <option value="COMPLETED">COMPLETED</option>
                    <option value="PAYMENT_FAILED">PAYMENT FAILED</option>
                  </select>
                </div>

                {/* Payment Status */}
                <div>
                  <select
                    value={selectedPaymentStatusFilter}
                    onChange={(e) => setSelectedPaymentStatusFilter(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500 bg-white"
                  >
                    <option value="">All Payment Statuses</option>
                    <option value="PAID">PAID</option>
                    <option value="FREE">FREE</option>
                    <option value="PENDING">PENDING</option>
                    <option value="REFUNDED">REFUNDED</option>
                    <option value="FAILED">FAILED</option>
                  </select>
                </div>

                {/* Date Filter */}
                <div>
                  <input
                    type="date"
                    value={selectedDateFilter}
                    onChange={(e) => setSelectedDateFilter(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500 bg-white"
                  />
                </div>
              </div>

              {(searchTerm ||
                selectedAmenityFilter ||
                selectedStatusFilter ||
                selectedPaymentStatusFilter ||
                selectedDateFilter) && (
                <div className="flex justify-end pt-1">
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-[11px] h-6 px-2 text-slate-500"
                    onClick={() => {
                      setSearchTerm('');
                      setSelectedAmenityFilter('');
                      setSelectedStatusFilter('');
                      setSelectedPaymentStatusFilter('');
                      setSelectedDateFilter('');
                    }}
                  >
                    Clear Filters
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Bookings Table */}
          {isLoadingBookings ? (
            <div className="space-y-3">
              {Array.from({ length: 4 }).map((_, idx) => (
                <Skeleton key={idx} className="h-16 rounded-xl" />
              ))}
            </div>
          ) : bookings.length === 0 ? (
            <div className="text-center py-12 bg-white rounded-2xl border border-dashed border-slate-200 p-8 space-y-2">
              <CalendarCheck className="h-8 w-8 text-slate-300 mx-auto" />
              <h3 className="text-sm font-semibold text-slate-900">No Reservations Found</h3>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                No resident bookings match the selected filters.
              </p>
            </div>
          ) : (
            <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="bg-slate-50/80 border-b border-slate-200/70 text-slate-600 font-semibold uppercase tracking-wider">
                      <th className="py-3 px-4">Booking Ref</th>
                      <th className="py-3 px-4">Amenity</th>
                      <th className="py-3 px-4">Resident / Flat</th>
                      <th className="py-3 px-4">Slot Schedule</th>
                      <th className="py-3 px-4">Amount</th>
                      <th className="py-3 px-4">Status</th>
                      <th className="py-3 px-4">Payment</th>
                      <th className="py-3 px-4 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-700">
                    {bookings.map((booking) => (
                      <tr key={booking.id} className="hover:bg-slate-50/60 transition-colors">
                        <td className="py-3.5 px-4 font-mono font-semibold text-indigo-700">
                          {booking.id.substring(0, 8).toUpperCase()}
                        </td>
                        <td className="py-3.5 px-4 font-medium text-slate-900">
                          {booking.amenity_name || 'Amenity'}
                        </td>
                        <td className="py-3.5 px-4">
                          <div className="font-semibold text-slate-800">
                            {booking.flat_number ? `Flat ${booking.flat_number}` : 'Unit'}
                          </div>
                          <span className="text-[11px] text-slate-400 font-mono">
                            {booking.user_id.substring(0, 8)}
                          </span>
                        </td>
                        <td className="py-3.5 px-4">
                          <div>{formatDateIST(booking.booking_date)}</div>
                          <span className="text-[11px] text-slate-500 font-mono">
                            {formatTimeRange(booking.start_time, booking.end_time)}
                          </span>
                        </td>
                        <td className="py-3.5 px-4 font-medium">
                          {formatAmenityFee(booking.booking_fee_paise)}
                        </td>
                        <td className="py-3.5 px-4">
                          <Badge
                            variant={
                              booking.status === 'CONFIRMED'
                                ? 'success'
                                : booking.status === 'PENDING_PAYMENT'
                                ? 'warning'
                                : booking.status === 'CANCELLED' || booking.status === 'PAYMENT_FAILED'
                                ? 'danger'
                                : 'neutral'
                            }
                          >
                            {booking.status}
                          </Badge>
                        </td>
                        <td className="py-3.5 px-4">
                          <Badge
                            variant={
                              booking.payment_status === 'PAID'
                                ? 'success'
                                : booking.payment_status === 'PENDING'
                                ? 'warning'
                                : booking.payment_status === 'FAILED'
                                ? 'danger'
                                : 'neutral'
                            }
                          >
                            {booking.payment_status}
                          </Badge>
                        </td>
                        <td className="py-3.5 px-4 text-right">
                          <div className="flex items-center justify-end gap-1.5">
                            <Button
                              variant="outline"
                              size="sm"
                              className="text-[11px] h-7 px-2"
                              onClick={() => setInspectingBooking(booking)}
                              title="View Details"
                            >
                              <Eye className="h-3.5 w-3.5" />
                            </Button>
                            {booking.status === 'CONFIRMED' && (
                              <Button
                                variant="outline"
                                size="sm"
                                className="text-[11px] h-7 px-2 text-rose-600 border-rose-200 hover:bg-rose-50"
                                onClick={() => {
                                  setCancellingBooking(booking);
                                  setCancelReason('');
                                  setCancelError(null);
                                }}
                                title="Administrative Cancel (100% Refund)"
                              >
                                Cancel
                              </Button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* MODAL 1: Create or Edit Amenity */}
      {(isCreatingAmenity || editingAmenity) && (
        <AmenityFormModal
          amenity={editingAmenity}
          onClose={() => {
            setIsCreatingAmenity(false);
            setEditingAmenity(null);
          }}
          onSuccess={() => {
            setIsCreatingAmenity(false);
            setEditingAmenity(null);
            void queryClient.invalidateQueries({ queryKey: ['staff-amenities-list'] });
            void queryClient.invalidateQueries({ queryKey: ['resident-amenities'] });
          }}
        />
      )}

      {/* MODAL 2: Amenity Maintenance Blocks */}
      {managingBlocksAmenity && (
        <AmenityBlocksModal
          amenity={managingBlocksAmenity}
          onClose={() => setManagingBlocksAmenity(null)}
        />
      )}

      {/* MODAL 3: Administrative Booking Cancellation */}
      {cancellingBooking && (
        <div
          className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4"
          role="dialog"
          aria-modal="true"
        >
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-slate-100 space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-rose-100 text-rose-600 flex items-center justify-center shrink-0">
                <AlertTriangle className="h-5 w-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-900">Administrative Cancel</h3>
                <p className="text-xs text-slate-500">
                  {cancellingBooking.amenity_name} on {cancellingBooking.booking_date}
                </p>
              </div>
            </div>

            <div className="p-3 bg-rose-50/70 rounded-xl border border-rose-200 text-xs text-rose-800 space-y-1">
              <span className="font-bold block">100% Full Refund Policy Override (Simulated)</span>
              <p className="text-[11px] leading-relaxed">
                Staff cancellations automatically override cutoff deadlines and record a 100% simulated refund of any paid booking fee ({formatAmenityFee(cancellingBooking.booking_fee_paise)}). Note: Test mode simulation — no live banking debit or credit occurs, and maintenance ledger balances remain unaffected.
              </p>
            </div>

            <div>
              <label htmlFor="staff-cancel-reason" className="block text-xs font-semibold text-slate-700 mb-1">
                Mandatory Operational Reason <span className="text-rose-500">*</span>
              </label>
              <textarea
                id="staff-cancel-reason"
                rows={3}
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                placeholder="e.g. Unscheduled court maintenance, severe weather closure, or federation inspection."
                className="w-full text-xs p-2.5 rounded-lg border border-slate-200 focus:outline-none focus:ring-1 focus:ring-rose-500"
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
                onClick={() => setCancellingBooking(null)}
                disabled={staffCancelMutation.isPending}
              >
                Dismiss
              </Button>
              <Button
                variant="danger"
                size="sm"
                disabled={!cancelReason.trim() || staffCancelMutation.isPending}
                onClick={() =>
                  staffCancelMutation.mutate({
                    bookingId: cancellingBooking.id,
                    reason: cancelReason.trim(),
                  })
                }
                className="flex items-center gap-1.5"
              >
                {staffCancelMutation.isPending ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    <span>Processing...</span>
                  </>
                ) : (
                  <span>Confirm Administrative Cancel</span>
                )}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 4: Booking Details Inspector */}
      {inspectingBooking && (
        <div
          className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4"
          role="dialog"
          aria-modal="true"
        >
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-2xl border border-slate-100 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-200 pb-3">
              <div>
                <h3 className="text-base font-bold text-slate-900">Reservation Details</h3>
                <span className="text-xs font-mono text-slate-500">
                  ID: {inspectingBooking.id}
                </span>
              </div>
              <Badge
                variant={
                  inspectingBooking.status === 'CONFIRMED'
                    ? 'success'
                    : inspectingBooking.status === 'PENDING_PAYMENT'
                    ? 'warning'
                    : 'danger'
                }
              >
                {inspectingBooking.status}
              </Badge>
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-100 space-y-1">
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">Amenity</span>
                <span className="font-bold text-slate-800 text-sm block">
                  {inspectingBooking.amenity_name || 'Amenity'}
                </span>
                <span className="text-slate-500 text-[11px] font-mono">
                  Type: {inspectingBooking.amenity_type}
                </span>
              </div>

              <div className="p-3 bg-slate-50 rounded-xl border border-slate-100 space-y-1">
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">Schedule</span>
                <span className="font-bold text-slate-800 text-sm block">
                  {inspectingBooking.booking_date}
                </span>
                <span className="text-slate-500 text-[11px] font-mono">
                  {formatTimeRange(inspectingBooking.start_time, inspectingBooking.end_time)}
                </span>
              </div>
            </div>

            <div className="p-3 bg-slate-50 rounded-xl border border-slate-100 text-xs space-y-2">
              <div className="flex justify-between">
                <span className="text-slate-500">Flat Unit</span>
                <span className="font-semibold text-slate-800">
                  {inspectingBooking.flat_number || inspectingBooking.flat_id}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Resident User ID</span>
                <span className="font-mono text-slate-700">{inspectingBooking.user_id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Booking Fee</span>
                <span className="font-bold text-emerald-700">
                  {formatAmenityFee(inspectingBooking.booking_fee_paise)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Payment Status</span>
                <span className="font-semibold text-slate-800">
                  {inspectingBooking.payment_status}
                </span>
              </div>
              {inspectingBooking.payment_reference && (
                <div className="flex justify-between">
                  <span className="text-slate-500">Payment Reference</span>
                  <span className="font-mono text-indigo-700 font-semibold">
                    {inspectingBooking.payment_reference}
                  </span>
                </div>
              )}
              {inspectingBooking.payment_id && (
                <div className="flex justify-between">
                  <span className="text-slate-500">Billing Payment ID</span>
                  <span className="font-mono text-slate-600">
                    {inspectingBooking.payment_id}
                  </span>
                </div>
              )}
              {inspectingBooking.refund_amount_paise > 0 && (
                <div className="space-y-0.5">
                  <div className="flex justify-between text-rose-700 font-medium">
                    <span>Simulated Refund (Test Mode)</span>
                    <span>{formatINR(inspectingBooking.refund_amount_paise)} ({inspectingBooking.refund_status})</span>
                  </div>
                  <p className="text-[10px] text-slate-500 italic">
                    Simulated test refund recorded in amenity audit log; zero impact on society financial ledger.
                  </p>
                </div>
              )}
              {inspectingBooking.cancellation_reason && (
                <div className="pt-2 border-t border-slate-200">
                  <span className="text-slate-400 block text-[10px] uppercase font-semibold">Cancellation Reason</span>
                  <p className="text-slate-700 mt-0.5 italic">{inspectingBooking.cancellation_reason}</p>
                </div>
              )}
            </div>

            <div className="flex justify-end pt-2">
              <Button variant="outline" size="sm" onClick={() => setInspectingBooking(null)}>
                Close
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// -----------------------------------------------------------------------------
// Subcomponent: Amenity Form Modal (Create or Edit)
// -----------------------------------------------------------------------------

interface AmenityFormModalProps {
  amenity: Amenity | null;
  onClose: () => void;
  onSuccess: () => void;
}

const AmenityFormModal: React.FC<AmenityFormModalProps> = ({
  amenity,
  onClose,
  onSuccess,
}) => {
  const isEdit = Boolean(amenity);

  const [name, setName] = useState(amenity?.name || '');
  const [description, setDescription] = useState(amenity?.description || '');
  const [amenityType, setAmenityType] = useState<AmenityType>(amenity?.amenity_type || 'BADMINTON_COURT');
  const [location, setLocation] = useState(amenity?.location || '');
  const [capacity, setCapacity] = useState<number>(amenity?.capacity ?? 1);
  const [durationMins, setDurationMins] = useState<number>(amenity?.slot_duration_minutes ?? 60);
  const [openingTime, setOpeningTime] = useState(amenity?.opening_time || '06:00');
  const [closingTime, setClosingTime] = useState(amenity?.closing_time || '22:00');
  const [feeRupees, setFeeRupees] = useState<number>(amenity ? amenity.booking_fee_paise / 100 : 0);
  const [advanceDays, setAdvanceDays] = useState<number>(amenity?.advance_booking_days ?? 7);
  const [minAdvanceHours, setMinAdvanceHours] = useState<number>(amenity?.min_advance_hours ?? 1);
  const [maxSlotsPerDay, setMaxSlotsPerDay] = useState<number>(amenity?.max_slots_per_day_per_resident ?? 2);
  const [cancelDeadlineHours, setCancelDeadlineHours] = useState<number>(amenity?.cancellation_deadline_hours ?? 2);
  const [refundPercentage, setRefundPercentage] = useState<number>(amenity?.refund_percentage ?? 80);
  const [guidelines, setGuidelines] = useState(amenity?.rules_and_guidelines || '');

  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      const payload: CreateAmenityRequest = {
        name: name.trim(),
        description: description.trim() || null,
        amenity_type: amenityType,
        location: location.trim() || null,
        capacity: Number(capacity),
        slot_duration_minutes: Number(durationMins),
        opening_time: openingTime,
        closing_time: closingTime,
        booking_fee_paise: Math.round(Number(feeRupees) * 100),
        advance_booking_days: Number(advanceDays),
        min_advance_hours: Number(minAdvanceHours),
        max_slots_per_day_per_resident: Number(maxSlotsPerDay),
        cancellation_deadline_hours: Number(cancelDeadlineHours),
        refund_percentage: Number(refundPercentage),
        allowed_membership_types: ['OWNER', 'TENANT', 'FAMILY_MEMBER'],
        rules_and_guidelines: guidelines.trim() || null,
      };

      if (isEdit && amenity) {
        await amenityService.staffUpdateAmenity(amenity.id, payload as UpdateAmenityRequest);
      } else {
        await amenityService.staffCreateAmenity(payload);
      }

      onSuccess();
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError('Failed to save facility configuration. Please verify inputs.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
    >
      <div className="bg-white rounded-2xl max-w-xl w-full p-6 shadow-2xl border border-slate-100 space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between border-b border-slate-200 pb-3">
          <h3 className="text-base font-bold text-slate-900">
            {isEdit ? `Edit ${amenity?.name}` : 'Configure New Amenity'}
          </h3>
          <Button variant="outline" size="sm" onClick={onClose} className="h-7 px-2">
            Cancel
          </Button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 text-xs">
          {error && <Alert variant="error" title="Validation Error">{error}</Alert>}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block font-semibold text-slate-700 mb-1">Facility Name *</label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Squash Court 1"
                className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            <div>
              <label className="block font-semibold text-slate-700 mb-1">Amenity Type *</label>
              <select
                value={amenityType}
                onChange={(e) => setAmenityType(e.target.value as AmenityType)}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-500 bg-white"
              >
                {AMENITY_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block font-semibold text-slate-700 mb-1">Description</label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="e.g. Floodlit championship court with synthetic turf"
              className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block font-semibold text-slate-700 mb-1">Location / Tower</label>
              <input
                type="text"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="e.g. Clubhouse Ground Floor"
                className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            <div>
              <label className="block font-semibold text-slate-700 mb-1">Booking Fee (INR)</label>
              <input
                type="number"
                min="0"
                step="1"
                value={feeRupees}
                onChange={(e) => setFeeRupees(Number(e.target.value))}
                placeholder="0 for free"
                className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div>
              <label className="block font-semibold text-slate-700 mb-1">Opening</label>
              <input
                type="text"
                required
                pattern="^\d{2}:\d{2}$"
                value={openingTime}
                onChange={(e) => setOpeningTime(e.target.value)}
                placeholder="06:00"
                className="w-full px-3 py-2 border border-slate-200 rounded-lg font-mono focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block font-semibold text-slate-700 mb-1">Closing</label>
              <input
                type="text"
                required
                pattern="^\d{2}:\d{2}$"
                value={closingTime}
                onChange={(e) => setClosingTime(e.target.value)}
                placeholder="22:00"
                className="w-full px-3 py-2 border border-slate-200 rounded-lg font-mono focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block font-semibold text-slate-700 mb-1">Duration (Min)</label>
              <input
                type="number"
                required
                min="15"
                max="480"
                value={durationMins}
                onChange={(e) => setDurationMins(Number(e.target.value))}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block font-semibold text-slate-700 mb-1">Capacity</label>
              <input
                type="number"
                required
                min="1"
                max="50"
                value={capacity}
                onChange={(e) => setCapacity(Number(e.target.value))}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            <div>
              <label className="block font-semibold text-slate-700 mb-1">Advance Days</label>
              <input
                type="number"
                min="1"
                max="60"
                value={advanceDays}
                onChange={(e) => setAdvanceDays(Number(e.target.value))}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block font-semibold text-slate-700 mb-1">Min Lead (Hrs)</label>
              <input
                type="number"
                min="0"
                max="72"
                value={minAdvanceHours}
                onChange={(e) => setMinAdvanceHours(Number(e.target.value))}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block font-semibold text-slate-700 mb-1">Max/Day</label>
              <input
                type="number"
                min="1"
                max="10"
                value={maxSlotsPerDay}
                onChange={(e) => setMaxSlotsPerDay(Number(e.target.value))}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block font-semibold text-slate-700 mb-1">Cutoff (Hrs)</label>
              <input
                type="number"
                min="0"
                max="72"
                value={cancelDeadlineHours}
                onChange={(e) => setCancelDeadlineHours(Number(e.target.value))}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block font-semibold text-slate-700 mb-1">Refund %</label>
              <input
                type="number"
                min="0"
                max="100"
                value={refundPercentage}
                onChange={(e) => setRefundPercentage(Number(e.target.value))}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
          </div>

          <div>
            <label className="block font-semibold text-slate-700 mb-1">Rules &amp; Guidelines</label>
            <textarea
              rows={2}
              value={guidelines}
              onChange={(e) => setGuidelines(e.target.value)}
              placeholder="e.g. Non-marking shoes required. Shower before entering pool."
              className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>

          <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-200">
            <Button variant="outline" size="sm" onClick={onClose} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              type="submit"
              disabled={isSubmitting}
              className="flex items-center gap-1.5 px-5 font-semibold"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span>Saving...</span>
                </>
              ) : (
                <span>{isEdit ? 'Update Facility' : 'Create Facility'}</span>
              )}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
};

// -----------------------------------------------------------------------------
// Subcomponent: Amenity Maintenance Blocks Modal
// -----------------------------------------------------------------------------

interface AmenityBlocksModalProps {
  amenity: Amenity;
  onClose: () => void;
}

const AmenityBlocksModal: React.FC<AmenityBlocksModalProps> = ({ amenity, onClose }) => {
  const queryClient = useQueryClient();
  const [blockDate, setBlockDate] = useState('');
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');
  const [reason, setReason] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  const {
    data: blocks,
    isLoading,
  } = useQuery({
    queryKey: ['amenity-blocks', amenity.id],
    queryFn: () => amenityService.listAmenityBlocks(amenity.id),
  });

  const createBlockMutation = useMutation({
    mutationFn: (req: CreateAmenityBlockRequest) =>
      amenityService.createAmenityBlock(amenity.id, req),
    onSuccess: () => {
      setBlockDate('');
      setStartTime('');
      setEndTime('');
      setReason('');
      setFormError(null);
      void queryClient.invalidateQueries({ queryKey: ['amenity-blocks', amenity.id] });
    },
    onError: (err: unknown) => {
      if (err instanceof ApiClientError) {
        setFormError(err.message);
      } else {
        setFormError('Failed to create maintenance block.');
      }
    },
  });

  const deleteBlockMutation = useMutation({
    mutationFn: (blockId: string) => amenityService.deleteAmenityBlock(blockId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['amenity-blocks', amenity.id] });
    },
  });

  const handleCreateBlock = (e: React.FormEvent) => {
    e.preventDefault();
    if (!blockDate || !reason.trim()) {
      setFormError('Block date and operational reason are required.');
      return;
    }
    createBlockMutation.mutate({
      block_date: blockDate,
      start_time: startTime || null,
      end_time: endTime || null,
      reason: reason.trim(),
    });
  };

  return (
    <div
      className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
    >
      <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-2xl border border-slate-100 space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between border-b border-slate-200 pb-3">
          <div>
            <h3 className="text-base font-bold text-slate-900">Maintenance &amp; Event Blocks</h3>
            <span className="text-xs text-slate-500">{amenity.name}</span>
          </div>
          <Button variant="outline" size="sm" onClick={onClose} className="h-7 px-2">
            Close
          </Button>
        </div>

        {/* Add Block Form */}
        <form onSubmit={handleCreateBlock} className="p-3.5 bg-slate-50 rounded-xl border border-slate-200 text-xs space-y-3">
          <span className="font-bold text-slate-800 block">Add Temporary Closure</span>

          {formError && <Alert variant="error" title="Block Error">{formError}</Alert>}

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            <div>
              <label className="block text-slate-600 font-semibold mb-1">Date *</label>
              <input
                type="date"
                required
                value={blockDate}
                onChange={(e) => setBlockDate(e.target.value)}
                className="w-full px-2.5 py-1.5 border border-slate-200 rounded-lg bg-white"
              />
            </div>
            <div>
              <label className="block text-slate-600 font-semibold mb-1">Start (Optional)</label>
              <input
                type="text"
                pattern="^\d{2}:\d{2}$"
                placeholder="HH:MM (All-day if blank)"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                className="w-full px-2.5 py-1.5 border border-slate-200 rounded-lg bg-white font-mono"
              />
            </div>
            <div>
              <label className="block text-slate-600 font-semibold mb-1">End (Optional)</label>
              <input
                type="text"
                pattern="^\d{2}:\d{2}$"
                placeholder="HH:MM"
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
                className="w-full px-2.5 py-1.5 border border-slate-200 rounded-lg bg-white font-mono"
              />
            </div>
          </div>

          <div>
            <label className="block text-slate-600 font-semibold mb-1">Closure Reason *</label>
            <input
              type="text"
              required
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. Deep cleaning, net repairs, society badminton tournament"
              className="w-full px-2.5 py-1.5 border border-slate-200 rounded-lg bg-white"
            />
          </div>

          <div className="flex justify-end pt-1">
            <Button
              variant="primary"
              size="sm"
              type="submit"
              disabled={createBlockMutation.isPending}
              className="text-xs"
            >
              {createBlockMutation.isPending ? 'Blocking...' : 'Block Time Slot'}
            </Button>
          </div>
        </form>

        {/* Existing Blocks List */}
        <div className="space-y-2">
          <span className="font-semibold text-slate-800 text-xs block">Active &amp; Scheduled Blocks</span>

          {isLoading ? (
            <Skeleton className="h-16 rounded-xl" />
          ) : (blocks || []).length === 0 ? (
            <p className="text-xs text-slate-400 py-3 text-center border border-dashed border-slate-200 rounded-xl">
              No closures or maintenance blocks scheduled.
            </p>
          ) : (
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {(blocks || []).map((blk) => (
                <div
                  key={blk.id}
                  className="p-3 bg-amber-50/70 rounded-xl border border-amber-200/80 flex items-center justify-between text-xs"
                >
                  <div className="space-y-0.5">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-slate-900">{blk.block_date}</span>
                      <span className="font-mono text-slate-600">
                        {blk.start_time && blk.end_time
                          ? formatTimeRange(blk.start_time, blk.end_time)
                          : 'All Day Closure'}
                      </span>
                    </div>
                    <span className="text-[11px] text-amber-900">{blk.reason}</span>
                  </div>

                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7 px-2 text-rose-600 border-rose-200 hover:bg-rose-50"
                    onClick={() => deleteBlockMutation.mutate(blk.id)}
                    disabled={deleteBlockMutation.isPending}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
