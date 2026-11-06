import React from 'react';
import {
  MapPin,
  Clock,
  Timer,
  Users,
  ShieldCheck,
  Dumbbell,
  Waves,
  Trophy,
  Building,
  BedDouble,
  Sparkles,
  AlertCircle,
} from 'lucide-react';
import { Amenity, AmenityType } from '../../../types/amenities';
import { Card, CardContent } from '../../../components/ui/Card';
import { Badge } from '../../../components/ui/Badge';
import { Button } from '../../../components/ui/Button';
import { formatAmenityFee } from '../../../services/amenityService';

interface AmenityCardProps {
  amenity: Amenity;
  userMembershipType?: string;
  onSelectAmenity: (amenity: Amenity) => void;
}

export function getAmenityIcon(type: AmenityType) {
  switch (type) {
    case 'BADMINTON_COURT':
    case 'TENNIS_COURT':
      return Trophy;
    case 'SWIMMING_POOL':
      return Waves;
    case 'GYM':
      return Dumbbell;
    case 'GUEST_ROOM':
      return BedDouble;
    case 'COMMUNITY_HALL':
    case 'CLUBHOUSE':
      return Building;
    default:
      return Sparkles;
  }
}

export function formatAmenityTypeName(type: AmenityType): string {
  switch (type) {
    case 'BADMINTON_COURT':
      return 'Badminton Court';
    case 'TENNIS_COURT':
      return 'Tennis Court';
    case 'SWIMMING_POOL':
      return 'Swimming Pool';
    case 'GYM':
      return 'Fitness Gym';
    case 'COMMUNITY_HALL':
      return 'Community Hall';
    case 'CLUBHOUSE':
      return 'Clubhouse';
    case 'GUEST_ROOM':
      return 'Guest Suite';
    default:
      return 'Township Amenity';
  }
}

export const AmenityCard: React.FC<AmenityCardProps> = ({
  amenity,
  userMembershipType,
  onSelectAmenity,
}) => {
  const IconComponent = getAmenityIcon(amenity.amenity_type);
  const isFree = amenity.booking_fee_paise === 0;

  // Check resident eligibility
  const isEligible =
    !userMembershipType ||
    !amenity.allowed_membership_types ||
    amenity.allowed_membership_types.includes(userMembershipType);

  return (
    <Card className="hover:shadow-md transition-shadow flex flex-col justify-between border-slate-200">
      <CardContent className="p-5 flex flex-col h-full justify-between">
        <div className="space-y-4">
          {/* Header & Badges */}
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                <IconComponent className="h-5 w-5" />
              </div>
              <div>
                <h3 className="text-base font-semibold text-slate-900 leading-tight">
                  {amenity.name}
                </h3>
                <span className="text-xs text-slate-500 font-medium">
                  {formatAmenityTypeName(amenity.amenity_type)}
                </span>
              </div>
            </div>
            <div className="shrink-0 flex flex-col items-end gap-1">
              <Badge variant={isFree ? 'success' : 'neutral'}>
                {formatAmenityFee(amenity.booking_fee_paise)}
              </Badge>
              {!amenity.is_active && (
                <Badge variant="warning">Maintenance</Badge>
              )}
            </div>
          </div>

          {/* Description */}
          {amenity.description && (
            <p className="text-xs text-slate-600 line-clamp-2 leading-relaxed">
              {amenity.description}
            </p>
          )}

          {/* Key Attributes Grid */}
          <div className="grid grid-cols-2 gap-2 text-xs text-slate-600 pt-1 border-t border-slate-100">
            {amenity.location && (
              <div className="flex items-center gap-1.5 truncate">
                <MapPin className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                <span className="truncate">{amenity.location}</span>
              </div>
            )}
            <div className="flex items-center gap-1.5">
              <Clock className="h-3.5 w-3.5 text-slate-400 shrink-0" />
              <span>{amenity.opening_time} – {amenity.closing_time}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Timer className="h-3.5 w-3.5 text-slate-400 shrink-0" />
              <span>{amenity.slot_duration_minutes} min slots</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Users className="h-3.5 w-3.5 text-slate-400 shrink-0" />
              <span>
                {amenity.capacity > 1
                  ? `${amenity.capacity} max spots`
                  : 'Single reservation'}
              </span>
            </div>
          </div>

          {/* Rules / Policy Snippet */}
          <div className="flex items-center justify-between text-[11px] text-slate-500 bg-slate-50 px-2.5 py-1.5 rounded-md">
            <span className="flex items-center gap-1">
              <ShieldCheck className="h-3 w-3 text-slate-400" />
              Cancel up to {amenity.cancellation_deadline_hours}h prior
            </span>
            <span>{amenity.refund_percentage}% refund</span>
          </div>

          {/* Membership Restriction Notice if ineligible */}
          {!isEligible && (
            <div className="flex items-center gap-1.5 text-xs text-amber-700 bg-amber-50 px-2.5 py-1.5 rounded-md">
              <AlertCircle className="h-3.5 w-3.5 shrink-0" />
              <span>
                Reserved for {amenity.allowed_membership_types.join(' & ')}
              </span>
            </div>
          )}
        </div>

        {/* Action Button */}
        <div className="pt-4 mt-2">
          <Button
            variant={isEligible && amenity.is_active ? 'primary' : 'outline'}
            className="w-full text-xs font-semibold py-2"
            disabled={!isEligible || !amenity.is_active}
            onClick={() => onSelectAmenity(amenity)}
          >
            {!amenity.is_active
              ? 'Temporarily Unavailable'
              : !isEligible
              ? 'Not Eligible for Flat'
              : 'View Slots & Book'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
};
