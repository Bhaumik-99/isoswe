import React, { useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Sparkles,
  Calendar,
  Search,
  RefreshCw,
  Trophy,
  Dumbbell,
  Building,
  Users,
} from 'lucide-react';
import { useAuth } from '../../auth/AuthContext';
import { Amenity } from '../../../types/amenities';
import {
  amenityService,
  getAmenityCategory,
} from '../../../services/amenityService';
import { AmenityCard } from './AmenityCard';
import { AmenityBookingModal } from './AmenityBookingModal';
import { MyBookingsList } from './MyBookingsList';
import { Button } from '../../../components/ui/Button';
import { Badge } from '../../../components/ui/Badge';
import { Alert } from '../../../components/ui/Alert';
import { Skeleton } from '../../../components/ui/Skeleton';

type AmenityCategoryFilter = 'all' | 'sports' | 'fitness' | 'clubhouse' | 'community';

export const ResidentAmenitiesPage: React.FC = () => {
  const { selectedFlat } = useAuth();
  const queryClient = useQueryClient();

  const [activeMainTab, setActiveMainTab] = useState<'discover' | 'my-bookings'>('discover');
  const [categoryFilter, setCategoryFilter] = useState<AmenityCategoryFilter>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedAmenityForBooking, setSelectedAmenityForBooking] = useState<Amenity | null>(null);
  const [bookingSuccessNotice, setBookingSuccessNotice] = useState<string | null>(null);

  // Fetch all active amenities
  const {
    data: amenitiesData,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['resident-amenities', selectedFlat?.society_id],
    queryFn: async () => {
      return amenityService.listAmenities(selectedFlat?.society_id);
    },
    enabled: Boolean(selectedFlat?.society_id),
  });

  // Fetch upcoming bookings count for tab badge
  const { data: upcomingBookingsData } = useQuery({
    queryKey: ['my-amenity-bookings', selectedFlat?.society_id, 'upcoming'],
    queryFn: async () => {
      return amenityService.getMyBookings({
        upcomingOnly: true,
        societyId: selectedFlat?.society_id,
        pageSize: 1,
      });
    },
    enabled: Boolean(selectedFlat?.society_id),
  });

  const amenities = useMemo(() => amenitiesData?.items || [], [amenitiesData]);

  // Filter amenities by category and search query
  const filteredAmenities = useMemo(() => {
    return amenities.filter((a) => {
      const matchesCategory =
        categoryFilter === 'all' || getAmenityCategory(a.amenity_type) === categoryFilter;

      const q = searchQuery.toLowerCase().trim();
      const matchesSearch =
        !q ||
        a.name.toLowerCase().includes(q) ||
        (a.location && a.location.toLowerCase().includes(q)) ||
        (a.description && a.description.toLowerCase().includes(q));

      return matchesCategory && matchesSearch;
    });
  }, [amenities, categoryFilter, searchQuery]);

  if (!selectedFlat) {
    return (
      <Alert variant="warning" title="No Active Flat Selected">
        Your account does not have an active approved flat membership selected in this township.
      </Alert>
    );
  }

  const upcomingCount = upcomingBookingsData?.total || 0;

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-200">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <Sparkles className="h-6 w-6 text-indigo-600 shrink-0" />
            <span>Amenities & Clubhouse Bookings</span>
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1">
            Reserve sports courts, swimming pool, gym, and community halls at Marvel Greenfield.
          </p>
        </div>

        {/* Flat Indicator Badge */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500">Active Flat:</span>
          <Badge variant="neutral">
            {selectedFlat.tower_number}-{selectedFlat.flat_number} ({selectedFlat.membership_type})
          </Badge>
        </div>
      </div>

      {/* Success Notification Banner */}
      {bookingSuccessNotice && (
        <Alert variant="success" title="Booking Confirmed!">
          <div className="flex items-center justify-between">
            <span>{bookingSuccessNotice}</span>
            <Button
              variant="outline"
              size="sm"
              className="text-xs bg-white ml-3"
              onClick={() => {
                setActiveMainTab('my-bookings');
                setBookingSuccessNotice(null);
              }}
            >
              View My Bookings
            </Button>
          </div>
        </Alert>
      )}

      {/* Main Mode Tabs */}
      <div className="flex items-center justify-between border-b border-slate-200">
        <div className="flex gap-6">
          <button
            type="button"
            onClick={() => setActiveMainTab('discover')}
            className={`pb-3 text-sm font-semibold tracking-wide transition-colors border-b-2 flex items-center gap-2 ${
              activeMainTab === 'discover'
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            <Sparkles className="h-4 w-4" />
            <span>Discover & Book</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveMainTab('my-bookings')}
            className={`pb-3 text-sm font-semibold tracking-wide transition-colors border-b-2 flex items-center gap-2 ${
              activeMainTab === 'my-bookings'
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            <Calendar className="h-4 w-4" />
            <span>My Bookings</span>
            {upcomingCount > 0 && (
              <Badge variant="success" className="px-1.5 py-0.2 text-[10px] ml-0.5">
                {upcomingCount}
              </Badge>
            )}
          </button>
        </div>

        <Button
          variant="outline"
          size="sm"
          className="text-xs gap-1.5 hidden sm:flex text-slate-600"
          onClick={() => {
            void refetch();
            void queryClient.invalidateQueries({ queryKey: ['my-amenity-bookings'] });
          }}
        >
          <RefreshCw className="h-3.5 w-3.5" />
          <span>Refresh</span>
        </Button>
      </div>

      {/* View 1: Discover & Book */}
      {activeMainTab === 'discover' && (
        <div className="space-y-5">
          {/* Controls: Search and Category Pills */}
          <div className="flex flex-col sm:flex-row gap-3 sm:items-center sm:justify-between">
            {/* Category Pills */}
            <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none">
              <button
                type="button"
                onClick={() => setCategoryFilter('all')}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors shrink-0 ${
                  categoryFilter === 'all'
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                All Facilities
              </button>
              <button
                type="button"
                onClick={() => setCategoryFilter('sports')}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors shrink-0 flex items-center gap-1.5 ${
                  categoryFilter === 'sports'
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                <Trophy className="h-3 w-3" />
                <span>Sports</span>
              </button>
              <button
                type="button"
                onClick={() => setCategoryFilter('fitness')}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors shrink-0 flex items-center gap-1.5 ${
                  categoryFilter === 'fitness'
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                <Dumbbell className="h-3 w-3" />
                <span>Fitness & Pool</span>
              </button>
              <button
                type="button"
                onClick={() => setCategoryFilter('clubhouse')}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors shrink-0 flex items-center gap-1.5 ${
                  categoryFilter === 'clubhouse'
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                <Building className="h-3 w-3" />
                <span>Clubhouse</span>
              </button>
              <button
                type="button"
                onClick={() => setCategoryFilter('community')}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors shrink-0 flex items-center gap-1.5 ${
                  categoryFilter === 'community'
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                <Users className="h-3 w-3" />
                <span>Community Spaces</span>
              </button>
            </div>

            {/* Search Bar */}
            <div className="relative w-full sm:w-64">
              <Search className="h-4 w-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search amenities..."
                className="w-full text-xs pl-9 pr-3 py-2 rounded-lg border border-slate-200 bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
          </div>

          {/* Amenity Cards Grid */}
          {isLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
              {Array.from({ length: 6 }).map((_, idx) => (
                <Skeleton key={idx} className="h-64 rounded-2xl" />
              ))}
            </div>
          ) : error ? (
            <Alert variant="error" title="Error Loading Amenities">
              <p>Failed to retrieve the township amenities list. Please try again.</p>
              <Button variant="outline" size="sm" className="mt-2 text-xs" onClick={() => void refetch()}>
                Retry
              </Button>
            </Alert>
          ) : filteredAmenities.length === 0 ? (
            <div className="text-center py-16 bg-white rounded-2xl border border-dashed border-slate-200 p-6 space-y-3">
              <div className="w-12 h-12 rounded-full bg-slate-100 text-slate-400 mx-auto flex items-center justify-center">
                <Search className="h-6 w-6" />
              </div>
              <h3 className="text-sm font-semibold text-slate-800">No Amenities Found</h3>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                No amenities match your selected filter or search term. Try resetting your search.
              </p>
              <Button
                variant="outline"
                size="sm"
                className="text-xs"
                onClick={() => {
                  setCategoryFilter('all');
                  setSearchQuery('');
                }}
              >
                Reset Filters
              </Button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
              {filteredAmenities.map((amenity) => (
                <AmenityCard
                  key={amenity.id}
                  amenity={amenity}
                  userMembershipType={selectedFlat.membership_type}
                  onSelectAmenity={(amn) => setSelectedAmenityForBooking(amn)}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* View 2: My Bookings */}
      {activeMainTab === 'my-bookings' && (
        <MyBookingsList
          selectedFlat={selectedFlat}
          onBrowseAmenities={() => setActiveMainTab('discover')}
        />
      )}

      {/* Booking Modal */}
      {selectedAmenityForBooking && (
        <AmenityBookingModal
          amenity={selectedAmenityForBooking}
          selectedFlat={selectedFlat}
          onClose={() => setSelectedAmenityForBooking(null)}
          onBookingSuccess={(booking) => {
            void queryClient.invalidateQueries({ queryKey: ['my-amenity-bookings'] });
            setBookingSuccessNotice(
              `Successfully booked ${selectedAmenityForBooking.name} for ${booking.booking_date} (${booking.start_time} - ${booking.end_time}).`
            );
          }}
        />
      )}
    </div>
  );
};
