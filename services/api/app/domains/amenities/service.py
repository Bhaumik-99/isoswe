"""Amenity Domain Service

Handles business logic, operating hours, slot generation, resident eligibility,
concurrency-safe slot reservations, cancellation rules, refunds, and structured audit events.
"""

import math
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import (
    AuthorizationError,
    ConflictError,
    ResourceNotFoundError,
    ValidationError,
)
from app.domains.amenities.models import (
    Amenity,
    AmenityBooking,
    AmenityType,
    BookingPaymentStatus,
    BookingStatus,
    RefundStatus,
)
from app.domains.amenities.schemas import (
    AmenityCreateRequest,
    AmenitySlotsResponse,
    AmenityUpdateRequest,
    BookingResponse,
    CreateBookingRequest,
    PaginatedBookingsResponse,
    TimeSlotAvailability,
)
from app.domains.identity.models import FlatMembership, MembershipStatus
from app.domains.reliability.models import AuditEvent, OutboxEvent, OutboxStatus


def utc_now() -> datetime:
    return datetime.now(UTC)


def time_to_minutes(time_str: str) -> int:
    parts = time_str.split(":")
    return int(parts[0]) * 60 + int(parts[1])


def minutes_to_time(minutes: int) -> str:
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"


class AmenityService:
    """Core domain service for Amenity and Clubhouse Booking operations."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # -------------------------------------------------------------------------
    # Amenity Discovery & Configuration
    # -------------------------------------------------------------------------

    def list_amenities(
        self,
        society_id: uuid.UUID,
        amenity_type: AmenityType | None = None,
        active_only: bool = True,
    ) -> list[Amenity]:
        """Lists amenities for a given society."""
        stmt = select(Amenity).where(Amenity.society_id == society_id)
        if active_only:
            stmt = stmt.where(Amenity.is_active.is_(True))
        if amenity_type:
            stmt = stmt.where(Amenity.amenity_type == amenity_type)
        stmt = stmt.order_by(Amenity.name.asc())
        return list(self.db.scalars(stmt).all())

    def get_amenity(self, society_id: uuid.UUID, amenity_id: uuid.UUID) -> Amenity:
        """Retrieves an amenity with strict society scoping."""
        amenity = self.db.get(Amenity, amenity_id)
        if not amenity or amenity.society_id != society_id:
            raise ResourceNotFoundError(
                code="AMENITY_NOT_FOUND",
                message=f"Amenity {amenity_id} not found in society {society_id}",
            )
        return amenity

    def create_amenity_by_staff(
        self,
        society_id: uuid.UUID,
        staff_user_id: uuid.UUID,
        req: AmenityCreateRequest,
    ) -> Amenity:
        """Creates a new amenity resource (staff only)."""
        # Validate tower if provided
        if req.tower_id:
            from app.domains.identity.models import Tower

            tower = self.db.get(Tower, req.tower_id)
            if not tower or tower.society_id != society_id:
                raise ResourceNotFoundError(
                    code="TOWER_NOT_FOUND",
                    message=f"Tower {req.tower_id} not found in society {society_id}",
                )

        now = utc_now()
        amenity = Amenity(
            id=uuid.uuid4(),
            society_id=society_id,
            name=req.name.strip(),
            description=req.description.strip() if req.description else None,
            amenity_type=req.amenity_type,
            location=req.location.strip() if req.location else None,
            tower_id=req.tower_id,
            capacity=req.capacity,
            slot_duration_minutes=req.slot_duration_minutes,
            opening_time=req.opening_time,
            closing_time=req.closing_time,
            booking_fee_paise=req.booking_fee_paise,
            advance_booking_days=req.advance_booking_days,
            min_advance_hours=req.min_advance_hours,
            max_slots_per_day_per_resident=req.max_slots_per_day_per_resident,
            cancellation_deadline_hours=req.cancellation_deadline_hours,
            refund_percentage=req.refund_percentage,
            allowed_membership_types=req.allowed_membership_types,
            is_active=req.is_active,
            rules_and_guidelines=req.rules_and_guidelines,
            created_at=now,
            updated_at=now,
        )
        self.db.add(amenity)
        self.db.flush()

        # Audit Event
        audit = AuditEvent(
            id=uuid.uuid4(),
            society_id=society_id,
            actor_id=staff_user_id,
            action="AMENITY_CREATED",
            resource_type="amenity",
            resource_id=str(amenity.id),
            correlation_id=str(uuid.uuid4()),
            event_metadata={
                "name": amenity.name,
                "amenity_type": amenity.amenity_type.value,
                "capacity": amenity.capacity,
                "booking_fee_paise": amenity.booking_fee_paise,
            },
        )
        self.db.add(audit)
        self.db.flush()
        return amenity

    def update_amenity_by_staff(
        self,
        society_id: uuid.UUID,
        staff_user_id: uuid.UUID,
        amenity_id: uuid.UUID,
        req: AmenityUpdateRequest,
    ) -> Amenity:
        """Updates amenity properties (staff only)."""
        amenity = self.get_amenity(society_id, amenity_id)

        update_data = req.model_dump(exclude_unset=True)
        if "tower_id" in update_data and update_data["tower_id"] is not None:
            from app.domains.identity.models import Tower

            tower = self.db.get(Tower, update_data["tower_id"])
            if not tower or tower.society_id != society_id:
                raise ResourceNotFoundError(
                    code="TOWER_NOT_FOUND",
                    message=f"Tower {update_data['tower_id']} not found in society {society_id}",
                )

        new_opening = update_data.get("opening_time", amenity.opening_time)
        new_closing = update_data.get("closing_time", amenity.closing_time)
        if time_to_minutes(new_closing) <= time_to_minutes(new_opening):
            raise ValidationError(
                code="INVALID_OPERATING_HOURS",
                message="closing_time must be later than opening_time",
            )

        for field, value in update_data.items():
            if value is not None or field in (
                "description",
                "location",
                "rules_and_guidelines",
                "tower_id",
            ):
                setattr(amenity, field, value)

        amenity.updated_at = utc_now()
        self.db.flush()

        audit = AuditEvent(
            id=uuid.uuid4(),
            society_id=society_id,
            actor_id=staff_user_id,
            action="AMENITY_UPDATED",
            resource_type="amenity",
            resource_id=str(amenity.id),
            correlation_id=str(uuid.uuid4()),
            event_metadata={"updated_fields": list(update_data.keys())},
        )
        self.db.add(audit)
        self.db.flush()
        return amenity

    def set_amenity_status_by_staff(
        self,
        society_id: uuid.UUID,
        staff_user_id: uuid.UUID,
        amenity_id: uuid.UUID,
        is_active: bool,
    ) -> Amenity:
        """Activates or deactivates an amenity (staff only)."""
        amenity = self.get_amenity(society_id, amenity_id)
        amenity.is_active = is_active
        amenity.updated_at = utc_now()
        self.db.flush()

        audit = AuditEvent(
            id=uuid.uuid4(),
            society_id=society_id,
            actor_id=staff_user_id,
            action="AMENITY_STATUS_CHANGED",
            resource_type="amenity",
            resource_id=str(amenity.id),
            correlation_id=str(uuid.uuid4()),
            event_metadata={"is_active": is_active},
        )
        self.db.add(audit)
        self.db.flush()
        return amenity

    # -------------------------------------------------------------------------
    # Slot Availability Calculation
    # -------------------------------------------------------------------------

    def get_available_slots(
        self,
        society_id: uuid.UUID,
        amenity_id: uuid.UUID,
        booking_date: date,
        user_id: uuid.UUID | None = None,
    ) -> AmenitySlotsResponse:
        """Generates all operational time slots for a date, accounting for capacity and user bookings."""
        amenity = self.get_amenity(society_id, amenity_id)
        if not amenity.is_active:
            raise ValidationError(
                code="AMENITY_INACTIVE",
                message=f"Amenity '{amenity.name}' is currently inactive.",
            )

        now = utc_now()
        today = now.date()
        if booking_date < today:
            raise ValidationError(
                code="PAST_DATE",
                message="Cannot view slot availability for a past date.",
            )
        if booking_date > today + timedelta(days=amenity.advance_booking_days):
            raise ValidationError(
                code="ADVANCE_LIMIT_EXCEEDED",
                message=f"Slots can only be viewed up to {amenity.advance_booking_days} days in advance.",
            )

        # Query all active bookings for this amenity on booking_date
        stmt = select(AmenityBooking).where(
            AmenityBooking.society_id == society_id,
            AmenityBooking.amenity_id == amenity_id,
            AmenityBooking.booking_date == booking_date,
            AmenityBooking.status == BookingStatus.CONFIRMED,
        )
        bookings = list(self.db.scalars(stmt).all())

        # Generate slots grid
        start_min = time_to_minutes(amenity.opening_time)
        end_min = time_to_minutes(amenity.closing_time)
        duration = amenity.slot_duration_minutes

        slots: list[TimeSlotAvailability] = []
        lead_time_cutoff = now + timedelta(hours=amenity.min_advance_hours)

        while start_min + duration <= end_min:
            s_time = minutes_to_time(start_min)
            e_time = minutes_to_time(start_min + duration)

            sh, sm = map(int, s_time.split(":"))
            slot_start_dt = datetime(
                booking_date.year, booking_date.month, booking_date.day, sh, sm, tzinfo=UTC
            )

            is_past = slot_start_dt <= now
            violates_lead_time = slot_start_dt < lead_time_cutoff

            slot_bookings = [b for b in bookings if b.start_time == s_time]
            booked_units = sum(b.booked_units for b in slot_bookings)
            remaining_capacity = max(0, amenity.capacity - booked_units)
            user_booked = any(b.user_id == user_id for b in slot_bookings) if user_id else False

            is_available = (
                (not is_past)
                and (not violates_lead_time)
                and (remaining_capacity > 0)
                and (not user_booked)
            )

            slots.append(
                TimeSlotAvailability(
                    start_time=s_time,
                    end_time=e_time,
                    total_capacity=amenity.capacity,
                    booked_units=booked_units,
                    remaining_capacity=remaining_capacity,
                    is_available=is_available,
                    is_past=is_past,
                    user_booked=user_booked,
                )
            )
            start_min += duration

        return AmenitySlotsResponse(
            amenity_id=amenity_id,
            booking_date=booking_date,
            slots=slots,
        )

    # -------------------------------------------------------------------------
    # Resident Eligibility Verification
    # -------------------------------------------------------------------------

    def verify_resident_eligibility(
        self,
        society_id: uuid.UUID,
        user_id: uuid.UUID,
        flat_id: uuid.UUID,
        amenity: Amenity,
        booking_date: date,
    ) -> FlatMembership:
        """Verifies active membership, lease validity, and membership type eligibility."""
        now = utc_now()
        stmt = select(FlatMembership).where(
            FlatMembership.society_id == society_id,
            FlatMembership.user_id == user_id,
            FlatMembership.flat_id == flat_id,
            FlatMembership.status == MembershipStatus.APPROVED,
            FlatMembership.valid_from <= now,
            or_(
                FlatMembership.valid_until.is_(None),
                FlatMembership.valid_until >= now,
            ),
        )
        membership = self.db.scalars(stmt).first()
        if not membership:
            raise AuthorizationError(
                code="FLAT_ACCESS_DENIED",
                message=f"You do not hold an active, approved membership for flat {flat_id} in this society.",
            )

        # Check tenant lease expiry against booking date
        if membership.valid_until and membership.valid_until.date() < booking_date:
            raise ValidationError(
                code="LEASE_EXPIRED_FOR_DATE",
                message=f"Your tenancy lease expires on {membership.valid_until.date()}, which precedes requested booking date {booking_date}.",
            )

        # Check allowed membership types
        m_type = membership.membership_type.value
        if amenity.allowed_membership_types and m_type not in amenity.allowed_membership_types:
            raise AuthorizationError(
                code="MEMBERSHIP_TYPE_NOT_ALLOWED",
                message=f"Membership type '{m_type}' is not eligible to book {amenity.name}.",
            )

        return membership

    # -------------------------------------------------------------------------
    # Booking Creation (Concurrency-Safe with Row Locking)
    # -------------------------------------------------------------------------

    def create_booking(
        self,
        society_id: uuid.UUID,
        user_id: uuid.UUID,
        amenity_id: uuid.UUID,
        req: CreateBookingRequest,
    ) -> AmenityBooking:
        """Creates an amenity booking with concurrency protection and strict validation."""
        # Row-level lock on Amenity for concurrency serialization
        lock_stmt = (
            select(Amenity)
            .where(Amenity.id == amenity_id, Amenity.society_id == society_id)
            .with_for_update()
        )
        amenity = self.db.execute(lock_stmt).scalar_one_or_none()
        if not amenity:
            raise ResourceNotFoundError(
                code="AMENITY_NOT_FOUND",
                message=f"Amenity {amenity_id} not found in society {society_id}",
            )

        if not amenity.is_active:
            raise ValidationError(
                code="AMENITY_INACTIVE",
                message=f"Amenity '{amenity.name}' is currently inactive.",
            )

        # Validate resident eligibility
        self.verify_resident_eligibility(
            society_id=society_id,
            user_id=user_id,
            flat_id=req.flat_id,
            amenity=amenity,
            booking_date=req.booking_date,
        )

        # Validate booking date and timing
        now = utc_now()
        today = now.date()
        if req.booking_date < today:
            raise ValidationError(
                code="PAST_DATE",
                message="Cannot book a slot for a past date.",
            )
        if req.booking_date > today + timedelta(days=amenity.advance_booking_days):
            raise ValidationError(
                code="ADVANCE_LIMIT_EXCEEDED",
                message=f"Bookings can only be made up to {amenity.advance_booking_days} days in advance.",
            )

        # Operating hours & slot alignment
        start_min = time_to_minutes(req.start_time)
        end_min = time_to_minutes(req.end_time)
        opening_min = time_to_minutes(amenity.opening_time)
        closing_min = time_to_minutes(amenity.closing_time)

        if start_min < opening_min or end_min > closing_min:
            raise ValidationError(
                code="OUTSIDE_OPERATING_HOURS",
                message=f"Requested time {req.start_time}-{req.end_time} is outside operating hours ({amenity.opening_time}-{amenity.closing_time}).",
            )

        requested_duration = end_min - start_min
        if requested_duration != amenity.slot_duration_minutes:
            raise ValidationError(
                code="INVALID_SLOT_DURATION",
                message=f"Booking duration must be exactly {amenity.slot_duration_minutes} minutes.",
            )

        if (start_min - opening_min) % amenity.slot_duration_minutes != 0:
            raise ValidationError(
                code="UNALIGNED_SLOT",
                message=f"Booking slot must align with {amenity.slot_duration_minutes}-minute intervals starting from {amenity.opening_time}.",
            )

        # Lead time and past slot check
        sh, sm = map(int, req.start_time.split(":"))
        slot_start_dt = datetime(
            req.booking_date.year, req.booking_date.month, req.booking_date.day, sh, sm, tzinfo=UTC
        )
        if slot_start_dt <= now:
            raise ValidationError(
                code="PAST_SLOT",
                message="Cannot book a slot that has already begun or passed.",
            )

        if amenity.min_advance_hours > 0:
            lead_time_cutoff = now + timedelta(hours=amenity.min_advance_hours)
            if slot_start_dt < lead_time_cutoff:
                raise ValidationError(
                    code="MIN_ADVANCE_HOURS_VIOLATION",
                    message=f"Booking must be made at least {amenity.min_advance_hours} hours in advance.",
                )

        # Capacity & duplicate slot check
        active_bookings_stmt = (
            select(AmenityBooking)
            .where(
                AmenityBooking.amenity_id == amenity.id,
                AmenityBooking.booking_date == req.booking_date,
                AmenityBooking.start_time == req.start_time,
                AmenityBooking.status == BookingStatus.CONFIRMED,
            )
            .with_for_update()
        )
        active_slot_bookings = list(self.db.scalars(active_bookings_stmt).all())

        if any(b.user_id == user_id for b in active_slot_bookings):
            raise ConflictError(
                code="DUPLICATE_BOOKING",
                message="You already have an active booking for this time slot.",
            )

        currently_booked_units = sum(b.booked_units for b in active_slot_bookings)
        if currently_booked_units + req.booked_units > amenity.capacity:
            remaining = max(0, amenity.capacity - currently_booked_units)
            raise ConflictError(
                code="CAPACITY_EXCEEDED",
                message=f"Requested {req.booked_units} unit(s) exceeds remaining capacity of {remaining} for this slot.",
            )

        # Daily booking limit per resident
        daily_count_stmt = select(func.count(AmenityBooking.id)).where(
            AmenityBooking.amenity_id == amenity.id,
            AmenityBooking.user_id == user_id,
            AmenityBooking.booking_date == req.booking_date,
            AmenityBooking.status == BookingStatus.CONFIRMED,
        )
        current_daily_count = self.db.scalar(daily_count_stmt) or 0
        if current_daily_count >= amenity.max_slots_per_day_per_resident:
            raise ConflictError(
                code="DAILY_LIMIT_EXCEEDED",
                message=f"You have reached the daily limit of {amenity.max_slots_per_day_per_resident} bookings for this amenity on {req.booking_date}.",
            )

        # Fee and payment calculation
        total_fee_paise = amenity.booking_fee_paise * req.booked_units
        if total_fee_paise > 0:
            payment_status = BookingPaymentStatus.PAID
            payment_ref = f"PAY-AMN-{uuid.uuid4().hex[:10].upper()}"
            refund_status = RefundStatus.NOT_APPLICABLE
        else:
            payment_status = BookingPaymentStatus.FREE
            payment_ref = None
            refund_status = RefundStatus.NOT_APPLICABLE

        booking = AmenityBooking(
            id=uuid.uuid4(),
            society_id=society_id,
            amenity_id=amenity.id,
            user_id=user_id,
            flat_id=req.flat_id,
            booking_date=req.booking_date,
            start_time=req.start_time,
            end_time=req.end_time,
            booked_units=req.booked_units,
            status=BookingStatus.CONFIRMED,
            booking_fee_paise=total_fee_paise,
            payment_status=payment_status,
            payment_reference=payment_ref,
            refund_status=refund_status,
            refund_amount_paise=0,
            notes=req.notes.strip() if req.notes else None,
            booking_metadata={
                "amenity_name": amenity.name,
                "slot_duration_minutes": amenity.slot_duration_minutes,
                "unit_fee_paise": amenity.booking_fee_paise,
            },
            created_at=now,
            updated_at=now,
        )
        self.db.add(booking)
        self.db.flush()

        # Audit Event
        audit = AuditEvent(
            id=uuid.uuid4(),
            society_id=society_id,
            actor_id=user_id,
            action="AMENITY_BOOKING_CREATED",
            resource_type="amenity_booking",
            resource_id=str(booking.id),
            correlation_id=str(uuid.uuid4()),
            event_metadata={
                "amenity_id": str(amenity.id),
                "amenity_name": amenity.name,
                "flat_id": str(req.flat_id),
                "booking_date": str(req.booking_date),
                "start_time": req.start_time,
                "end_time": req.end_time,
                "booked_units": req.booked_units,
                "booking_fee_paise": total_fee_paise,
                "payment_status": payment_status.value,
            },
        )
        self.db.add(audit)

        # Transactional Outbox Event for Notifications
        outbox = OutboxEvent(
            id=uuid.uuid4(),
            event_type="amenity.booking_created",
            aggregate_type="amenity_booking",
            aggregate_id=str(booking.id),
            payload={
                "society_id": str(society_id),
                "amenity_id": str(amenity.id),
                "amenity_name": amenity.name,
                "user_id": str(user_id),
                "flat_id": str(req.flat_id),
                "booking_date": str(req.booking_date),
                "start_time": req.start_time,
                "end_time": req.end_time,
                "booked_units": req.booked_units,
                "booking_fee_paise": total_fee_paise,
            },
            status=OutboxStatus.PENDING,
        )
        self.db.add(outbox)
        self.db.flush()

        return booking

    # -------------------------------------------------------------------------
    # Booking Retrieval
    # -------------------------------------------------------------------------

    def get_booking_by_id(
        self,
        society_id: uuid.UUID,
        booking_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> AmenityBooking:
        """Retrieves booking with IDOR security."""
        stmt = (
            select(AmenityBooking)
            .options(joinedload(AmenityBooking.amenity), joinedload(AmenityBooking.flat))
            .where(AmenityBooking.id == booking_id, AmenityBooking.society_id == society_id)
        )
        booking = self.db.scalars(stmt).first()
        if not booking:
            raise ResourceNotFoundError(
                code="BOOKING_NOT_FOUND",
                message=f"Booking {booking_id} not found in society {society_id}",
            )
        if user_id and booking.user_id != user_id:
            raise ResourceNotFoundError(
                code="BOOKING_NOT_FOUND",
                message=f"Booking {booking_id} not found",
            )
        return booking

    def get_user_bookings(
        self,
        society_id: uuid.UUID,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        status: BookingStatus | None = None,
        upcoming_only: bool = False,
    ) -> PaginatedBookingsResponse:
        """Lists resident bookings with pagination and filters."""
        page = max(1, page)
        page_size = max(1, min(100, page_size))
        offset = (page - 1) * page_size

        filters = [
            AmenityBooking.society_id == society_id,
            AmenityBooking.user_id == user_id,
        ]
        if status:
            filters.append(AmenityBooking.status == status)
        if upcoming_only:
            today = utc_now().date()
            filters.append(AmenityBooking.booking_date >= today)
            filters.append(AmenityBooking.status == BookingStatus.CONFIRMED)

        total_stmt = select(func.count(AmenityBooking.id)).where(*filters)
        total = self.db.scalar(total_stmt) or 0

        stmt = (
            select(AmenityBooking)
            .options(joinedload(AmenityBooking.amenity), joinedload(AmenityBooking.flat))
            .where(*filters)
            .order_by(AmenityBooking.booking_date.desc(), AmenityBooking.start_time.desc())
            .offset(offset)
            .limit(page_size)
        )
        bookings = list(self.db.scalars(stmt).all())

        items = [self._to_booking_response(b) for b in bookings]
        total_pages = math.ceil(total / page_size) if total > 0 else 1

        return PaginatedBookingsResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    def list_staff_bookings(
        self,
        society_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        amenity_id: uuid.UUID | None = None,
        booking_date: date | None = None,
        status: BookingStatus | None = None,
        flat_id: uuid.UUID | None = None,
    ) -> PaginatedBookingsResponse:
        """Staff overview of all bookings across society."""
        page = max(1, page)
        page_size = max(1, min(100, page_size))
        offset = (page - 1) * page_size

        filters = [AmenityBooking.society_id == society_id]
        if amenity_id:
            filters.append(AmenityBooking.amenity_id == amenity_id)
        if booking_date:
            filters.append(AmenityBooking.booking_date == booking_date)
        if status:
            filters.append(AmenityBooking.status == status)
        if flat_id:
            filters.append(AmenityBooking.flat_id == flat_id)

        total_stmt = select(func.count(AmenityBooking.id)).where(*filters)
        total = self.db.scalar(total_stmt) or 0

        stmt = (
            select(AmenityBooking)
            .options(joinedload(AmenityBooking.amenity), joinedload(AmenityBooking.flat))
            .where(*filters)
            .order_by(AmenityBooking.booking_date.desc(), AmenityBooking.start_time.desc())
            .offset(offset)
            .limit(page_size)
        )
        bookings = list(self.db.scalars(stmt).all())

        items = [self._to_booking_response(b) for b in bookings]
        total_pages = math.ceil(total / page_size) if total > 0 else 1

        return PaginatedBookingsResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    # -------------------------------------------------------------------------
    # Booking Cancellation
    # -------------------------------------------------------------------------

    def cancel_booking_by_resident(
        self,
        society_id: uuid.UUID,
        user_id: uuid.UUID,
        booking_id: uuid.UUID,
        reason: str | None = None,
    ) -> AmenityBooking:
        """Cancels a booking by the resident, enforcing cancellation deadlines and calculating refunds."""
        booking = self.get_booking_by_id(society_id, booking_id, user_id=user_id)
        if booking.status != BookingStatus.CONFIRMED:
            raise ConflictError(
                code="INVALID_BOOKING_STATUS",
                message=f"Cannot cancel a booking with status '{booking.status.value}'.",
            )

        amenity = booking.amenity
        now = utc_now()

        # Check cancellation deadline
        sh, sm = map(int, booking.start_time.split(":"))
        slot_start_dt = datetime(
            booking.booking_date.year,
            booking.booking_date.month,
            booking.booking_date.day,
            sh,
            sm,
            tzinfo=UTC,
        )
        deadline = slot_start_dt - timedelta(hours=amenity.cancellation_deadline_hours)
        if now > deadline:
            raise ConflictError(
                code="CANCELLATION_DEADLINE_EXPIRED",
                message=f"Cancellation window expired. Cancellations must be made at least {amenity.cancellation_deadline_hours} hours prior to slot start.",
            )

        # Refund calculation
        if booking.booking_fee_paise > 0:
            refund_amount = int(booking.booking_fee_paise * (amenity.refund_percentage / 100))
            refund_status = (
                RefundStatus.REFUNDED if refund_amount > 0 else RefundStatus.CANCELLED_NO_REFUND
            )
        else:
            refund_amount = 0
            refund_status = RefundStatus.NOT_APPLICABLE

        booking.status = BookingStatus.CANCELLED
        booking.cancelled_at = now
        booking.cancelled_by_user_id = user_id
        booking.cancellation_reason = reason.strip() if reason else "Cancelled by resident"
        booking.refund_status = refund_status
        booking.refund_amount_paise = refund_amount
        booking.updated_at = now
        self.db.flush()

        # Audit Event
        audit = AuditEvent(
            id=uuid.uuid4(),
            society_id=society_id,
            actor_id=user_id,
            action="AMENITY_BOOKING_CANCELLED",
            resource_type="amenity_booking",
            resource_id=str(booking.id),
            correlation_id=str(uuid.uuid4()),
            event_metadata={
                "amenity_id": str(booking.amenity_id),
                "booking_date": str(booking.booking_date),
                "refund_amount_paise": refund_amount,
                "refund_status": refund_status.value,
                "reason": booking.cancellation_reason,
            },
        )
        self.db.add(audit)

        # Outbox event
        outbox = OutboxEvent(
            id=uuid.uuid4(),
            event_type="amenity.booking_cancelled",
            aggregate_type="amenity_booking",
            aggregate_id=str(booking.id),
            payload={
                "society_id": str(society_id),
                "amenity_id": str(booking.amenity_id),
                "amenity_name": amenity.name,
                "user_id": str(user_id),
                "cancelled_by": "RESIDENT",
                "refund_amount_paise": refund_amount,
                "refund_status": refund_status.value,
            },
            status=OutboxStatus.PENDING,
        )
        self.db.add(outbox)
        self.db.flush()

        return booking

    def cancel_booking_by_staff(
        self,
        society_id: uuid.UUID,
        staff_user_id: uuid.UUID,
        booking_id: uuid.UUID,
        reason: str,
    ) -> AmenityBooking:
        """Cancels a booking with administrative override and 100% refund."""
        booking = self.get_booking_by_id(society_id, booking_id)
        if booking.status != BookingStatus.CONFIRMED:
            raise ConflictError(
                code="INVALID_BOOKING_STATUS",
                message=f"Cannot cancel a booking with status '{booking.status.value}'.",
            )

        now = utc_now()
        # Management/facility emergency cancellation provides 100% refund
        if booking.booking_fee_paise > 0:
            refund_amount = booking.booking_fee_paise
            refund_status = RefundStatus.REFUNDED
        else:
            refund_amount = 0
            refund_status = RefundStatus.NOT_APPLICABLE

        booking.status = BookingStatus.CANCELLED
        booking.cancelled_at = now
        booking.cancelled_by_user_id = staff_user_id
        booking.cancellation_reason = f"Staff Override: {reason.strip()}"
        booking.refund_status = refund_status
        booking.refund_amount_paise = refund_amount
        booking.updated_at = now
        self.db.flush()

        # Audit Event
        audit = AuditEvent(
            id=uuid.uuid4(),
            society_id=society_id,
            actor_id=staff_user_id,
            action="AMENITY_BOOKING_STAFF_CANCELLED",
            resource_type="amenity_booking",
            resource_id=str(booking.id),
            correlation_id=str(uuid.uuid4()),
            event_metadata={
                "amenity_id": str(booking.amenity_id),
                "booking_date": str(booking.booking_date),
                "refund_amount_paise": refund_amount,
                "refund_status": refund_status.value,
                "reason": booking.cancellation_reason,
            },
        )
        self.db.add(audit)

        # Outbox event
        outbox = OutboxEvent(
            id=uuid.uuid4(),
            event_type="amenity.booking_cancelled",
            aggregate_type="amenity_booking",
            aggregate_id=str(booking.id),
            payload={
                "society_id": str(society_id),
                "amenity_id": str(booking.amenity_id),
                "amenity_name": booking.amenity.name if booking.amenity else "",
                "user_id": str(booking.user_id),
                "cancelled_by": "STAFF",
                "refund_amount_paise": refund_amount,
                "refund_status": refund_status.value,
                "reason": booking.cancellation_reason,
            },
            status=OutboxStatus.PENDING,
        )
        self.db.add(outbox)
        self.db.flush()

        return booking

    # -------------------------------------------------------------------------
    # Helper Serialization
    # -------------------------------------------------------------------------

    def _to_booking_response(self, booking: AmenityBooking) -> BookingResponse:
        return BookingResponse(
            id=booking.id,
            society_id=booking.society_id,
            amenity_id=booking.amenity_id,
            amenity_name=booking.amenity.name if booking.amenity else None,
            amenity_type=booking.amenity.amenity_type if booking.amenity else None,
            user_id=booking.user_id,
            flat_id=booking.flat_id,
            flat_number=booking.flat.flat_number if booking.flat else None,
            booking_date=booking.booking_date,
            start_time=booking.start_time,
            end_time=booking.end_time,
            booked_units=booking.booked_units,
            status=booking.status,
            booking_fee_paise=booking.booking_fee_paise,
            payment_status=booking.payment_status,
            payment_reference=booking.payment_reference,
            refund_status=booking.refund_status,
            refund_amount_paise=booking.refund_amount_paise,
            cancellation_reason=booking.cancellation_reason,
            cancelled_at=booking.cancelled_at,
            cancelled_by_user_id=booking.cancelled_by_user_id,
            notes=booking.notes,
            booking_metadata=booking.booking_metadata or {},
            created_at=booking.created_at,
            updated_at=booking.updated_at,
        )
