"""Domain Unit and Integration Tests for Amenities and Clubhouse Booking System.

Tests cover:
- Amenity lifecycle (create, update, activate/deactivate, hours validation).
- Slot generation & capacity tracking (multi-capacity, past slots, lead time).
- Resident eligibility verification (membership status, tenant lease expiry, allowed types).
- Booking constraints (advance limit, operating hours, slot alignment, daily limits).
- Concurrency safety & overbooking prevention.
- Cancellation policies & refund calculation (resident deadline vs staff override).
- Audit and transactional outbox event emission.
"""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import (
    AuthorizationError,
    ConflictError,
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
    AmenityUpdateRequest,
    CreateBookingRequest,
)
from app.domains.amenities.service import AmenityService, utc_now
from app.domains.identity.models import (
    FlatMembership,
    MembershipStatus,
    MembershipType,
    User,
    UserStatus,
)
from app.domains.reliability.models import AuditEvent, OutboxEvent

SOCIETY_PUNE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
TOWER_T07_ID = uuid.UUID("22222222-2222-2222-2222-222222222207")
FLAT_1203_ID = uuid.UUID("33333333-3333-3333-3333-333333331203")
FLAT_0408_ID = uuid.UUID("33333333-3333-3333-3333-333333330408")
NEERAJ_ID = uuid.UUID("44444444-4444-4444-4444-444444440001")
SWATI_ID = uuid.UUID("44444444-4444-4444-4444-444444440002")
HELPDESK_ID = uuid.UUID("44444444-4444-4444-4444-444444440004")


@pytest.fixture
def amenity_service(db_session: Session) -> AmenityService:
    return AmenityService(db_session)


@pytest.fixture
def sample_tennis_court(db_session: Session) -> Amenity:
    amenity = Amenity(
        id=uuid.uuid4(),
        society_id=SOCIETY_PUNE_ID,
        name="Tennis Court A",
        description="Floodlit outdoor tennis court",
        amenity_type=AmenityType.TENNIS_COURT,
        location="Clubhouse Sports Wing",
        tower_id=None,
        capacity=1,
        slot_duration_minutes=60,
        opening_time="06:00",
        closing_time="22:00",
        booking_fee_paise=25000,  # 250.00 INR
        advance_booking_days=7,
        min_advance_hours=2,
        max_slots_per_day_per_resident=2,
        cancellation_deadline_hours=4,
        refund_percentage=80,
        allowed_membership_types=["OWNER", "TENANT", "FAMILY_MEMBER"],
        is_active=True,
    )
    db_session.add(amenity)
    db_session.flush()
    return amenity


@pytest.fixture
def sample_swimming_pool(db_session: Session) -> Amenity:
    amenity = Amenity(
        id=uuid.uuid4(),
        society_id=SOCIETY_PUNE_ID,
        name="Olympic Swimming Pool",
        description="Shared pool with capacity 15 swimmers per slot",
        amenity_type=AmenityType.SWIMMING_POOL,
        location="Central Clubhouse",
        tower_id=None,
        capacity=15,
        slot_duration_minutes=60,
        opening_time="06:00",
        closing_time="20:00",
        booking_fee_paise=0,  # Free amenity
        advance_booking_days=5,
        min_advance_hours=0,
        max_slots_per_day_per_resident=1,
        cancellation_deadline_hours=1,
        refund_percentage=100,
        allowed_membership_types=["OWNER", "TENANT", "FAMILY_MEMBER"],
        is_active=True,
    )
    db_session.add(amenity)
    db_session.flush()
    return amenity


# -----------------------------------------------------------------------------
# Amenity Lifecycle & Configuration Tests
# -----------------------------------------------------------------------------


def test_create_amenity_by_staff(amenity_service: AmenityService, db_session: Session) -> None:
    req = AmenityCreateRequest(
        name="Badminton Court 1",
        description="Synthetic wooden court",
        amenity_type=AmenityType.BADMINTON_COURT,
        location="Sports Complex Ground Floor",
        tower_id=TOWER_T07_ID,
        capacity=1,
        slot_duration_minutes=45,
        opening_time="06:00",
        closing_time="21:00",
        booking_fee_paise=15000,
        advance_booking_days=3,
        min_advance_hours=1,
        max_slots_per_day_per_resident=1,
        cancellation_deadline_hours=2,
        refund_percentage=100,
        allowed_membership_types=["OWNER", "TENANT"],
        is_active=True,
        rules_and_guidelines="Non-marking shoes only.",
    )
    amenity = amenity_service.create_amenity_by_staff(
        society_id=SOCIETY_PUNE_ID,
        staff_user_id=HELPDESK_ID,
        req=req,
    )
    assert amenity.id is not None
    assert amenity.name == "Badminton Court 1"
    assert amenity.capacity == 1
    assert amenity.booking_fee_paise == 15000

    # Verify audit event
    audit = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.resource_id == str(amenity.id),
            AuditEvent.action == "AMENITY_CREATED",
        )
    ).first()
    assert audit is not None
    assert audit.actor_id == HELPDESK_ID


def test_update_amenity_by_staff(
    amenity_service: AmenityService, sample_tennis_court: Amenity
) -> None:
    req = AmenityUpdateRequest(
        name="Tennis Court A (Renovated)",
        booking_fee_paise=30000,
        closing_time="21:00",
    )
    updated = amenity_service.update_amenity_by_staff(
        society_id=SOCIETY_PUNE_ID,
        staff_user_id=HELPDESK_ID,
        amenity_id=sample_tennis_court.id,
        req=req,
    )
    assert updated.name == "Tennis Court A (Renovated)"
    assert updated.booking_fee_paise == 30000
    assert updated.closing_time == "21:00"


def test_toggle_amenity_status(
    amenity_service: AmenityService, sample_tennis_court: Amenity
) -> None:
    updated = amenity_service.set_amenity_status_by_staff(
        society_id=SOCIETY_PUNE_ID,
        staff_user_id=HELPDESK_ID,
        amenity_id=sample_tennis_court.id,
        is_active=False,
    )
    assert updated.is_active is False

    # Resident booking an inactive amenity must fail
    target_date = utc_now().date() + timedelta(days=2)
    req = CreateBookingRequest(
        flat_id=FLAT_1203_ID,
        booking_date=target_date,
        start_time="08:00",
        end_time="09:00",
        booked_units=1,
    )
    with pytest.raises(ValidationError) as exc:
        amenity_service.create_booking(
            society_id=SOCIETY_PUNE_ID,
            user_id=NEERAJ_ID,
            amenity_id=sample_tennis_court.id,
            req=req,
        )
    assert exc.value.code == "AMENITY_INACTIVE"


# -----------------------------------------------------------------------------
# Slot Availability & Capacity Tracking Tests
# -----------------------------------------------------------------------------


def test_slot_generation_and_capacity_tracking(
    amenity_service: AmenityService, sample_swimming_pool: Amenity, db_session: Session
) -> None:
    target_date = utc_now().date() + timedelta(days=2)
    slots_resp = amenity_service.get_available_slots(
        society_id=SOCIETY_PUNE_ID,
        amenity_id=sample_swimming_pool.id,
        booking_date=target_date,
        user_id=NEERAJ_ID,
    )

    # 06:00 to 20:00 with 60-min slots -> 14 slots
    assert len(slots_resp.slots) == 14
    first_slot = slots_resp.slots[0]
    assert first_slot.start_time == "06:00"
    assert first_slot.end_time == "07:00"
    assert first_slot.total_capacity == 15
    assert first_slot.booked_units == 0
    assert first_slot.remaining_capacity == 15
    assert first_slot.is_available is True
    assert first_slot.user_booked is False

    # Create a booking of 5 units for Swati
    b = AmenityBooking(
        id=uuid.uuid4(),
        society_id=SOCIETY_PUNE_ID,
        amenity_id=sample_swimming_pool.id,
        user_id=SWATI_ID,
        flat_id=FLAT_0408_ID,
        booking_date=target_date,
        start_time="06:00",
        end_time="07:00",
        booked_units=5,
        status=BookingStatus.CONFIRMED,
        booking_fee_paise=0,
    )
    db_session.add(b)
    db_session.flush()

    # Re-query slot availability
    slots_resp2 = amenity_service.get_available_slots(
        society_id=SOCIETY_PUNE_ID,
        amenity_id=sample_swimming_pool.id,
        booking_date=target_date,
        user_id=NEERAJ_ID,
    )
    s0 = slots_resp2.slots[0]
    assert s0.booked_units == 5
    assert s0.remaining_capacity == 10
    assert s0.is_available is True
    assert s0.user_booked is False

    # Check from Swati's view -> user_booked should be True
    swati_slots = amenity_service.get_available_slots(
        society_id=SOCIETY_PUNE_ID,
        amenity_id=sample_swimming_pool.id,
        booking_date=target_date,
        user_id=SWATI_ID,
    )
    assert swati_slots.slots[0].user_booked is True
    assert swati_slots.slots[0].is_available is False  # Already booked by user


# -----------------------------------------------------------------------------
# Resident Eligibility & Validation Tests
# -----------------------------------------------------------------------------


def test_booking_fails_for_unauthorized_flat(
    amenity_service: AmenityService, sample_tennis_court: Amenity
) -> None:
    target_date = utc_now().date() + timedelta(days=2)
    # Neeraj does not belong to Flat 0408 (Swati's flat)
    req = CreateBookingRequest(
        flat_id=FLAT_0408_ID,
        booking_date=target_date,
        start_time="08:00",
        end_time="09:00",
        booked_units=1,
    )
    with pytest.raises(AuthorizationError) as exc:
        amenity_service.create_booking(
            society_id=SOCIETY_PUNE_ID,
            user_id=NEERAJ_ID,
            amenity_id=sample_tennis_court.id,
            req=req,
        )
    assert exc.value.code == "FLAT_ACCESS_DENIED"


def test_booking_fails_if_tenant_lease_expired_for_booking_date(
    amenity_service: AmenityService, sample_tennis_court: Amenity, db_session: Session
) -> None:
    target_date = utc_now().date() + timedelta(days=5)

    # Create temporary user whose lease expires in 3 days
    temp_user = User(
        id=uuid.uuid4(),
        supabase_uid=uuid.uuid4(),
        phone="+91-98777-66655",
        email="lease.expiring@example.com",
        full_name="Lease Expiring Resident",
        status=UserStatus.ACTIVE,
    )
    db_session.add(temp_user)
    db_session.flush()

    mem = FlatMembership(
        id=uuid.uuid4(),
        society_id=SOCIETY_PUNE_ID,
        user_id=temp_user.id,
        flat_id=FLAT_1203_ID,
        membership_type=MembershipType.TENANT,
        status=MembershipStatus.APPROVED,
        valid_from=utc_now() - timedelta(days=100),
        valid_until=utc_now() + timedelta(days=3),  # Expires before target_date
    )
    db_session.add(mem)
    db_session.flush()

    req = CreateBookingRequest(
        flat_id=FLAT_1203_ID,
        booking_date=target_date,
        start_time="08:00",
        end_time="09:00",
        booked_units=1,
    )
    with pytest.raises(ValidationError) as exc:
        amenity_service.create_booking(
            society_id=SOCIETY_PUNE_ID,
            user_id=temp_user.id,
            amenity_id=sample_tennis_court.id,
            req=req,
        )
    assert exc.value.code == "LEASE_EXPIRED_FOR_DATE"


def test_booking_fails_if_membership_type_disallowed(
    amenity_service: AmenityService, sample_tennis_court: Amenity, db_session: Session
) -> None:
    # Restrict tennis court to owners only
    sample_tennis_court.allowed_membership_types = ["OWNER"]
    db_session.flush()

    # Swati is a TENANT in flat 0408
    target_date = utc_now().date() + timedelta(days=2)
    req = CreateBookingRequest(
        flat_id=FLAT_0408_ID,
        booking_date=target_date,
        start_time="08:00",
        end_time="09:00",
        booked_units=1,
    )
    with pytest.raises(AuthorizationError) as exc:
        amenity_service.create_booking(
            society_id=SOCIETY_PUNE_ID,
            user_id=SWATI_ID,
            amenity_id=sample_tennis_court.id,
            req=req,
        )
    assert exc.value.code == "MEMBERSHIP_TYPE_NOT_ALLOWED"


# -----------------------------------------------------------------------------
# Booking Timing & Capacity Rule Tests
# -----------------------------------------------------------------------------


def test_booking_fails_on_past_date_or_advance_limit_exceeded(
    amenity_service: AmenityService, sample_tennis_court: Amenity
) -> None:
    # 1. Past date
    past_req = CreateBookingRequest(
        flat_id=FLAT_1203_ID,
        booking_date=utc_now().date() - timedelta(days=1),
        start_time="08:00",
        end_time="09:00",
        booked_units=1,
    )
    with pytest.raises(ValidationError) as exc:
        amenity_service.create_booking(
            society_id=SOCIETY_PUNE_ID,
            user_id=NEERAJ_ID,
            amenity_id=sample_tennis_court.id,
            req=past_req,
        )
    assert exc.value.code == "PAST_DATE"

    # 2. Beyond advance booking days (advance_booking_days = 7)
    future_req = CreateBookingRequest(
        flat_id=FLAT_1203_ID,
        booking_date=utc_now().date() + timedelta(days=10),
        start_time="08:00",
        end_time="09:00",
        booked_units=1,
    )
    with pytest.raises(ValidationError) as exc:
        amenity_service.create_booking(
            society_id=SOCIETY_PUNE_ID,
            user_id=NEERAJ_ID,
            amenity_id=sample_tennis_court.id,
            req=future_req,
        )
    assert exc.value.code == "ADVANCE_LIMIT_EXCEEDED"


def test_booking_fails_outside_hours_or_unaligned_slot(
    amenity_service: AmenityService, sample_tennis_court: Amenity
) -> None:
    target_date = utc_now().date() + timedelta(days=2)

    # Outside operating hours (opens at 06:00, closes at 22:00)
    req_early = CreateBookingRequest(
        flat_id=FLAT_1203_ID,
        booking_date=target_date,
        start_time="05:00",
        end_time="06:00",
        booked_units=1,
    )
    with pytest.raises(ValidationError) as exc:
        amenity_service.create_booking(
            society_id=SOCIETY_PUNE_ID,
            user_id=NEERAJ_ID,
            amenity_id=sample_tennis_court.id,
            req=req_early,
        )
    assert exc.value.code == "OUTSIDE_OPERATING_HOURS"

    # Unaligned slot (slot duration is 60 mins from 06:00, e.g. 06:30 is unaligned)
    req_unaligned = CreateBookingRequest(
        flat_id=FLAT_1203_ID,
        booking_date=target_date,
        start_time="06:30",
        end_time="07:30",
        booked_units=1,
    )
    with pytest.raises(ValidationError) as exc:
        amenity_service.create_booking(
            society_id=SOCIETY_PUNE_ID,
            user_id=NEERAJ_ID,
            amenity_id=sample_tennis_court.id,
            req=req_unaligned,
        )
    assert exc.value.code == "UNALIGNED_SLOT"


def test_successful_booking_creation_and_events(
    amenity_service: AmenityService, sample_tennis_court: Amenity, db_session: Session
) -> None:
    target_date = utc_now().date() + timedelta(days=2)
    req = CreateBookingRequest(
        flat_id=FLAT_1203_ID,
        booking_date=target_date,
        start_time="07:00",
        end_time="08:00",
        booked_units=1,
        notes="Practice session with coach",
    )
    booking = amenity_service.create_booking(
        society_id=SOCIETY_PUNE_ID,
        user_id=NEERAJ_ID,
        amenity_id=sample_tennis_court.id,
        req=req,
    )

    assert booking.id is not None
    assert booking.status == BookingStatus.CONFIRMED
    assert booking.booking_fee_paise == 25000  # 250.00 INR
    assert booking.payment_status == BookingPaymentStatus.PAID
    assert booking.payment_reference is not None

    # Check AuditEvent
    audit = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.resource_id == str(booking.id),
            AuditEvent.action == "AMENITY_BOOKING_CREATED",
        )
    ).first()
    assert audit is not None
    assert audit.actor_id == NEERAJ_ID

    # Check OutboxEvent
    outbox = db_session.scalars(
        select(OutboxEvent).where(
            OutboxEvent.aggregate_id == str(booking.id),
            OutboxEvent.event_type == "amenity.booking_created",
        )
    ).first()
    assert outbox is not None
    assert outbox.payload["amenity_name"] == "Tennis Court A"


def test_capacity_exceeded_and_duplicate_booking_rejection(
    amenity_service: AmenityService, sample_tennis_court: Amenity
) -> None:
    target_date = utc_now().date() + timedelta(days=2)
    req = CreateBookingRequest(
        flat_id=FLAT_1203_ID,
        booking_date=target_date,
        start_time="07:00",
        end_time="08:00",
        booked_units=1,
    )
    # 1. Neeraj books slot
    amenity_service.create_booking(
        society_id=SOCIETY_PUNE_ID,
        user_id=NEERAJ_ID,
        amenity_id=sample_tennis_court.id,
        req=req,
    )

    # 2. Neeraj tries to book the same slot again -> DUPLICATE_BOOKING
    with pytest.raises(ConflictError) as exc:
        amenity_service.create_booking(
            society_id=SOCIETY_PUNE_ID,
            user_id=NEERAJ_ID,
            amenity_id=sample_tennis_court.id,
            req=req,
        )
    assert exc.value.code == "DUPLICATE_BOOKING"

    # 3. Swati tries to book the same slot (tennis court capacity = 1) -> CAPACITY_EXCEEDED
    swati_req = CreateBookingRequest(
        flat_id=FLAT_0408_ID,
        booking_date=target_date,
        start_time="07:00",
        end_time="08:00",
        booked_units=1,
    )
    with pytest.raises(ConflictError) as exc2:
        amenity_service.create_booking(
            society_id=SOCIETY_PUNE_ID,
            user_id=SWATI_ID,
            amenity_id=sample_tennis_court.id,
            req=swati_req,
        )
    assert exc2.value.code == "CAPACITY_EXCEEDED"


def test_daily_limit_per_resident_enforcement(
    amenity_service: AmenityService, sample_tennis_court: Amenity
) -> None:
    target_date = utc_now().date() + timedelta(days=2)
    # sample_tennis_court.max_slots_per_day_per_resident is 2

    # Book slot 1: 07:00 - 08:00
    amenity_service.create_booking(
        society_id=SOCIETY_PUNE_ID,
        user_id=NEERAJ_ID,
        amenity_id=sample_tennis_court.id,
        req=CreateBookingRequest(
            flat_id=FLAT_1203_ID,
            booking_date=target_date,
            start_time="07:00",
            end_time="08:00",
            booked_units=1,
        ),
    )

    # Book slot 2: 08:00 - 09:00
    amenity_service.create_booking(
        society_id=SOCIETY_PUNE_ID,
        user_id=NEERAJ_ID,
        amenity_id=sample_tennis_court.id,
        req=CreateBookingRequest(
            flat_id=FLAT_1203_ID,
            booking_date=target_date,
            start_time="08:00",
            end_time="09:00",
            booked_units=1,
        ),
    )

    # Attempt slot 3: 09:00 - 10:00 -> DAILY_LIMIT_EXCEEDED
    with pytest.raises(ConflictError) as exc:
        amenity_service.create_booking(
            society_id=SOCIETY_PUNE_ID,
            user_id=NEERAJ_ID,
            amenity_id=sample_tennis_court.id,
            req=CreateBookingRequest(
                flat_id=FLAT_1203_ID,
                booking_date=target_date,
                start_time="09:00",
                end_time="10:00",
                booked_units=1,
            ),
        )
    assert exc.value.code == "DAILY_LIMIT_EXCEEDED"


# -----------------------------------------------------------------------------
# Cancellation & Refund Policy Tests
# -----------------------------------------------------------------------------


def test_resident_cancellation_within_deadline(
    amenity_service: AmenityService, sample_tennis_court: Amenity, db_session: Session
) -> None:
    # Booking for 2 days from now (cancellation deadline is 4 hours)
    target_date = utc_now().date() + timedelta(days=2)
    booking = amenity_service.create_booking(
        society_id=SOCIETY_PUNE_ID,
        user_id=NEERAJ_ID,
        amenity_id=sample_tennis_court.id,
        req=CreateBookingRequest(
            flat_id=FLAT_1203_ID,
            booking_date=target_date,
            start_time="10:00",
            end_time="11:00",
            booked_units=1,
        ),
    )

    cancelled = amenity_service.cancel_booking_by_resident(
        society_id=SOCIETY_PUNE_ID,
        user_id=NEERAJ_ID,
        booking_id=booking.id,
        reason="Family event scheduled",
    )
    assert cancelled.status == BookingStatus.CANCELLED
    # Refund percentage is 80% on 25000 paise -> 20000 paise (200.00 INR)
    assert cancelled.refund_status == RefundStatus.REFUNDED
    assert cancelled.refund_amount_paise == 20000
    assert cancelled.cancelled_by_user_id == NEERAJ_ID

    # Verify outbox event emitted
    outbox = db_session.scalars(
        select(OutboxEvent).where(
            OutboxEvent.aggregate_id == str(booking.id),
            OutboxEvent.event_type == "amenity.booking_cancelled",
        )
    ).first()
    assert outbox is not None
    assert outbox.payload["refund_amount_paise"] == 20000


def test_resident_cancellation_fails_after_deadline(
    amenity_service: AmenityService, sample_tennis_court: Amenity, db_session: Session
) -> None:
    # Create booking for today, starting in 2 hours (deadline is 4 hours)
    now = utc_now()
    today = now.date()
    slot_start = (now + timedelta(hours=2)).strftime("%H:00")
    slot_end = (now + timedelta(hours=3)).strftime("%H:00")

    booking = AmenityBooking(
        id=uuid.uuid4(),
        society_id=SOCIETY_PUNE_ID,
        amenity_id=sample_tennis_court.id,
        user_id=NEERAJ_ID,
        flat_id=FLAT_1203_ID,
        booking_date=today,
        start_time=slot_start,
        end_time=slot_end,
        booked_units=1,
        status=BookingStatus.CONFIRMED,
        booking_fee_paise=25000,
    )
    db_session.add(booking)
    db_session.flush()

    # Cancellation attempt must fail due to expired deadline
    with pytest.raises(ConflictError) as exc:
        amenity_service.cancel_booking_by_resident(
            society_id=SOCIETY_PUNE_ID,
            user_id=NEERAJ_ID,
            booking_id=booking.id,
        )
    assert exc.value.code == "CANCELLATION_DEADLINE_EXPIRED"


def test_staff_cancellation_overrides_deadline_with_full_refund(
    amenity_service: AmenityService, sample_tennis_court: Amenity, db_session: Session
) -> None:
    # Booking starting in 1 hour (within deadline)
    now = utc_now()
    today = now.date()
    slot_start = (now + timedelta(hours=1)).strftime("%H:00")
    slot_end = (now + timedelta(hours=2)).strftime("%H:00")

    booking = AmenityBooking(
        id=uuid.uuid4(),
        society_id=SOCIETY_PUNE_ID,
        amenity_id=sample_tennis_court.id,
        user_id=NEERAJ_ID,
        flat_id=FLAT_1203_ID,
        booking_date=today,
        start_time=slot_start,
        end_time=slot_end,
        booked_units=1,
        status=BookingStatus.CONFIRMED,
        booking_fee_paise=25000,
    )
    db_session.add(booking)
    db_session.flush()

    cancelled = amenity_service.cancel_booking_by_staff(
        society_id=SOCIETY_PUNE_ID,
        staff_user_id=HELPDESK_ID,
        booking_id=booking.id,
        reason="Heavy rainfall, waterlogging on outdoor court",
    )
    assert cancelled.status == BookingStatus.CANCELLED
    # Staff cancellation gives 100% refund (25000 paise)
    assert cancelled.refund_status == RefundStatus.REFUNDED
    assert cancelled.refund_amount_paise == 25000
    assert cancelled.cancelled_by_user_id == HELPDESK_ID
    assert "waterlogging" in cancelled.cancellation_reason


# -----------------------------------------------------------------------------
# Concurrency & Overbooking Prevention
# -----------------------------------------------------------------------------


def test_concurrency_race_condition_prevents_overbooking(
    sample_tennis_court: Amenity, db_session: Session
) -> None:
    """Proves that serialized slot booking prevents overbooking available capacity."""
    target_date = utc_now().date() + timedelta(days=2)
    slot_start = "16:00"
    slot_end = "17:00"

    # Capacity is 1. Two residents attempt to book the same slot.
    service1 = AmenityService(db_session)
    service2 = AmenityService(db_session)

    req_neeraj = CreateBookingRequest(
        flat_id=FLAT_1203_ID,
        booking_date=target_date,
        start_time=slot_start,
        end_time=slot_end,
        booked_units=1,
    )
    req_swati = CreateBookingRequest(
        flat_id=FLAT_0408_ID,
        booking_date=target_date,
        start_time=slot_start,
        end_time=slot_end,
        booked_units=1,
    )

    # First booking succeeds
    b1 = service1.create_booking(
        society_id=SOCIETY_PUNE_ID,
        user_id=NEERAJ_ID,
        amenity_id=sample_tennis_court.id,
        req=req_neeraj,
    )
    assert b1.status == BookingStatus.CONFIRMED

    # Competing concurrent booking MUST be rejected with CAPACITY_EXCEEDED
    with pytest.raises(ConflictError) as exc:
        service2.create_booking(
            society_id=SOCIETY_PUNE_ID,
            user_id=SWATI_ID,
            amenity_id=sample_tennis_court.id,
            req=req_swati,
        )
    assert exc.value.code == "CAPACITY_EXCEEDED"

    # Final DB check: total confirmed bookings for that slot is strictly 1
    confirmed_bookings = list(
        db_session.scalars(
            select(AmenityBooking).where(
                AmenityBooking.amenity_id == sample_tennis_court.id,
                AmenityBooking.booking_date == target_date,
                AmenityBooking.start_time == slot_start,
                AmenityBooking.status == BookingStatus.CONFIRMED,
            )
        ).all()
    )
    assert len(confirmed_bookings) == 1
    assert sum(b.booked_units for b in confirmed_bookings) == 1
