"""Tests for Amenity Timezone Correctness (Pune / Asia/Kolkata).

Validates:
1. Midnight boundary crossover: UTC date and Indian local date differ by 1 day.
2. Advance booking limit and past date validation based on facility local calendar date.
3. Past slot detection via timezone-aware instant comparisons.
4. Booking lead time enforcement (min_advance_hours).
5. Cancellation deadline enforcement (cancellation_deadline_hours).
6. Timezone-aware database timestamps and UTC slot metadata persistence.
7. Resident upcoming bookings filtering across midnight boundaries.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, ValidationError
from app.domains.amenities.models import (
    Amenity,
    AmenityBooking,
    AmenityType,
    BookingPaymentStatus,
    BookingStatus,
    RefundStatus,
)
from app.domains.amenities.schemas import CreateBookingRequest
from app.domains.amenities.service import (
    FACILITY_TIMEZONE,
    AmenityService,
    facility_now,
    facility_today,
    slot_to_facility_dt,
    slot_to_utc,
)

SOCIETY_PUNE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
FLAT_1203_ID = uuid.UUID("33333333-3333-3333-3333-333333331203")
NEERAJ_ID = uuid.UUID("44444444-4444-4444-4444-444444440001")


@pytest.fixture
def amenity_service(db_session: Session) -> AmenityService:
    return AmenityService(db_session)


@pytest.fixture
def timezone_test_amenity(db_session: Session) -> Amenity:
    """Tennis court with 60min slots, 2h min advance, 4h cancellation deadline, 7 days advance."""
    amenity = Amenity(
        id=uuid.uuid4(),
        society_id=SOCIETY_PUNE_ID,
        name="Pune Championship Tennis Court",
        description="Floodlit outdoor tennis court in Pune",
        amenity_type=AmenityType.TENNIS_COURT,
        location="Clubhouse Sports Arena",
        tower_id=None,
        capacity=1,
        slot_duration_minutes=60,
        opening_time="06:00",
        closing_time="22:00",
        booking_fee_paise=25000,
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


# -----------------------------------------------------------------------------
# 1. Helper Unit Tests for Asia/Kolkata Timezone Conversions
# -----------------------------------------------------------------------------


def test_facility_timezone_constants_and_helpers() -> None:
    assert ZoneInfo("Asia/Kolkata") == FACILITY_TIMEZONE

    # Fixed UTC moment: 2026-11-07 20:00:00 UTC -> 2026-11-08 01:30:00 IST (+5:30)
    fixed_utc = datetime(2026, 11, 7, 20, 0, 0, tzinfo=UTC)
    local_dt = fixed_utc.astimezone(FACILITY_TIMEZONE)
    assert local_dt.year == 2026
    assert local_dt.month == 11
    assert local_dt.day == 8
    assert local_dt.hour == 1
    assert local_dt.minute == 30

    # Local slot 06:00 IST on 2026-11-08 -> 00:30 UTC on 2026-11-08
    local_slot = slot_to_facility_dt(date(2026, 11, 8), "06:00")
    assert local_slot.tzinfo == FACILITY_TIMEZONE
    assert local_slot.hour == 6

    utc_slot = slot_to_utc(date(2026, 11, 8), "06:00")
    assert utc_slot.tzinfo == UTC
    assert utc_slot == datetime(2026, 11, 8, 0, 30, 0, tzinfo=UTC)


# -----------------------------------------------------------------------------
# 2. Midnight Boundary Tests (UTC day N vs Indian local day N+1)
# -----------------------------------------------------------------------------


def test_midnight_boundary_calendar_date_and_slot_availability(
    amenity_service: AmenityService,
    timezone_test_amenity: Amenity,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When wall-clock is 20:00 UTC on Nov 7, in Pune it is 01:30 IST on Nov 8.

    Local date is Nov 8 (today). Nov 7 is yesterday.
    Viewing or booking Nov 7 must fail with PAST_DATE.
    Viewing or booking Nov 8 must succeed.
    Advance booking limit must be calculated from Nov 8, allowing up to Nov 15.
    """
    frozen_utc = datetime(2026, 11, 7, 20, 0, 0, tzinfo=UTC)
    monkeypatch.setattr("app.domains.amenities.service.utc_now", lambda: frozen_utc)

    # Verify facility helpers reflect Pune local time
    assert facility_today() == date(2026, 11, 8)
    assert facility_now().hour == 1
    assert facility_now().minute == 30

    # 1. Viewing slots for Nov 7 (past date in Pune) must fail
    with pytest.raises(ValidationError) as exc:
        amenity_service.get_available_slots(
            society_id=SOCIETY_PUNE_ID,
            amenity_id=timezone_test_amenity.id,
            booking_date=date(2026, 11, 7),
            user_id=NEERAJ_ID,
        )
    assert exc.value.code == "PAST_DATE"

    # 2. Viewing slots for Nov 8 (today in Pune) must succeed
    resp_today = amenity_service.get_available_slots(
        society_id=SOCIETY_PUNE_ID,
        amenity_id=timezone_test_amenity.id,
        booking_date=date(2026, 11, 8),
        user_id=NEERAJ_ID,
    )
    assert resp_today.booking_date == date(2026, 11, 8)
    assert len(resp_today.slots) > 0

    # 3. Booking Nov 7 must fail with PAST_DATE
    with pytest.raises(ValidationError) as exc_book_past:
        amenity_service.create_booking(
            society_id=SOCIETY_PUNE_ID,
            user_id=NEERAJ_ID,
            amenity_id=timezone_test_amenity.id,
            req=CreateBookingRequest(
                flat_id=FLAT_1203_ID,
                booking_date=date(2026, 11, 7),
                start_time="06:00",
                end_time="07:00",
                booked_units=1,
            ),
        )
    assert exc_book_past.value.code == "PAST_DATE"

    # 4. Advance limit boundary: 7 days advance from Nov 8 allows up to Nov 15
    resp_limit = amenity_service.get_available_slots(
        society_id=SOCIETY_PUNE_ID,
        amenity_id=timezone_test_amenity.id,
        booking_date=date(2026, 11, 15),
        user_id=NEERAJ_ID,
    )
    assert resp_limit.booking_date == date(2026, 11, 15)

    # Nov 16 is 8 days in advance from Nov 8 -> must fail with ADVANCE_LIMIT_EXCEEDED
    with pytest.raises(ValidationError) as exc_adv:
        amenity_service.get_available_slots(
            society_id=SOCIETY_PUNE_ID,
            amenity_id=timezone_test_amenity.id,
            booking_date=date(2026, 11, 16),
            user_id=NEERAJ_ID,
        )
    assert exc_adv.value.code == "ADVANCE_LIMIT_EXCEEDED"


# -----------------------------------------------------------------------------
# 3. Past Slot Instant Comparison Tests
# -----------------------------------------------------------------------------


def test_past_slot_instant_comparison_in_facility_time(
    amenity_service: AmenityService,
    timezone_test_amenity: Amenity,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When wall-clock in Pune is 09:30 AM IST on 2026-11-08 (04:00:00 UTC):

    - Slot 06:00-07:00 IST (00:30-01:30 UTC): past, booking fails with PAST_SLOT.
    - Slot 09:00-10:00 IST (03:30-04:30 UTC): started 30 mins ago, past, booking fails.
    - Slot 10:00-11:00 IST (04:30-05:30 UTC): future (in 30 mins, but check min_advance_hours).
    """
    frozen_utc = datetime(2026, 11, 8, 4, 0, 0, tzinfo=UTC)  # 09:30 AM IST
    monkeypatch.setattr("app.domains.amenities.service.utc_now", lambda: frozen_utc)

    slots_resp = amenity_service.get_available_slots(
        society_id=SOCIETY_PUNE_ID,
        amenity_id=timezone_test_amenity.id,
        booking_date=date(2026, 11, 8),
        user_id=NEERAJ_ID,
    )

    slots_by_time = {s.start_time: s for s in slots_resp.slots}
    assert slots_by_time["06:00"].is_past is True
    assert slots_by_time["09:00"].is_past is True
    assert slots_by_time["10:00"].is_past is False

    # Attempting to book past slot 06:00-07:00 must fail
    with pytest.raises(ValidationError) as exc1:
        amenity_service.create_booking(
            society_id=SOCIETY_PUNE_ID,
            user_id=NEERAJ_ID,
            amenity_id=timezone_test_amenity.id,
            req=CreateBookingRequest(
                flat_id=FLAT_1203_ID,
                booking_date=date(2026, 11, 8),
                start_time="06:00",
                end_time="07:00",
                booked_units=1,
            ),
        )
    assert exc1.value.code == "PAST_SLOT"

    # Attempting to book in-progress slot 09:00-10:00 must fail
    with pytest.raises(ValidationError) as exc2:
        amenity_service.create_booking(
            society_id=SOCIETY_PUNE_ID,
            user_id=NEERAJ_ID,
            amenity_id=timezone_test_amenity.id,
            req=CreateBookingRequest(
                flat_id=FLAT_1203_ID,
                booking_date=date(2026, 11, 8),
                start_time="09:00",
                end_time="10:00",
                booked_units=1,
            ),
        )
    assert exc2.value.code == "PAST_SLOT"


# -----------------------------------------------------------------------------
# 4. Booking Lead Time Tests (min_advance_hours)
# -----------------------------------------------------------------------------


def test_booking_lead_time_enforcement_in_facility_time(
    amenity_service: AmenityService,
    timezone_test_amenity: Amenity,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Current time: 07:15 AM IST (01:45 UTC). Min advance hours: 2h.

    Cutoff is 09:15 AM IST (03:45 UTC).
    - Slot 08:00-09:00 IST (02:30 UTC): 45 mins advance (< 2h). Fails with MIN_ADVANCE_HOURS_VIOLATION.
    - Slot 10:00-11:00 IST (04:30 UTC): 2h 45m advance (>= 2h). Booking succeeds.
    """
    frozen_utc = datetime(2026, 11, 8, 1, 45, 0, tzinfo=UTC)  # 07:15 AM IST
    monkeypatch.setattr("app.domains.amenities.service.utc_now", lambda: frozen_utc)

    # Check slot availability flags
    slots_resp = amenity_service.get_available_slots(
        society_id=SOCIETY_PUNE_ID,
        amenity_id=timezone_test_amenity.id,
        booking_date=date(2026, 11, 8),
        user_id=NEERAJ_ID,
    )
    slots_by_time = {s.start_time: s for s in slots_resp.slots}
    assert slots_by_time["08:00"].is_available is False  # Violates lead time
    assert slots_by_time["10:00"].is_available is True

    # 1. Booking 08:00 slot must fail with MIN_ADVANCE_HOURS_VIOLATION
    with pytest.raises(ValidationError) as exc_lead:
        amenity_service.create_booking(
            society_id=SOCIETY_PUNE_ID,
            user_id=NEERAJ_ID,
            amenity_id=timezone_test_amenity.id,
            req=CreateBookingRequest(
                flat_id=FLAT_1203_ID,
                booking_date=date(2026, 11, 8),
                start_time="08:00",
                end_time="09:00",
                booked_units=1,
            ),
        )
    assert exc_lead.value.code == "MIN_ADVANCE_HOURS_VIOLATION"

    # 2. Booking 10:00 slot must succeed
    booking = amenity_service.create_booking(
        society_id=SOCIETY_PUNE_ID,
        user_id=NEERAJ_ID,
        amenity_id=timezone_test_amenity.id,
        req=CreateBookingRequest(
            flat_id=FLAT_1203_ID,
            booking_date=date(2026, 11, 8),
            start_time="10:00",
            end_time="11:00",
            booked_units=1,
            auto_pay=True,
        ),
    )
    assert booking.status == BookingStatus.CONFIRMED
    assert booking.start_time == "10:00"


# -----------------------------------------------------------------------------
# 5. Cancellation Deadline Tests (cancellation_deadline_hours)
# -----------------------------------------------------------------------------


def test_cancellation_deadline_enforcement_in_facility_time(
    amenity_service: AmenityService,
    timezone_test_amenity: Amenity,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Slot: 14:00 - 15:00 IST on 2026-11-08 (starts 08:30 UTC).

    cancellation_deadline_hours = 4.
    Deadline is 10:00 AM IST (04:30 UTC).

    Case A: At 09:30 AM IST (04:00 UTC) -> 4.5h before start (before deadline).
    Cancellation succeeds.

    Case B: At 10:30 AM IST (05:00 UTC) -> 3.5h before start (past deadline).
    Cancellation fails with CANCELLATION_DEADLINE_EXPIRED.
    """
    # 1. Create booking when well in advance (e.g. at 06:00 IST / 00:30 UTC)
    booking_time = datetime(2026, 11, 8, 0, 30, 0, tzinfo=UTC)
    monkeypatch.setattr("app.domains.amenities.service.utc_now", lambda: booking_time)

    booking = amenity_service.create_booking(
        society_id=SOCIETY_PUNE_ID,
        user_id=NEERAJ_ID,
        amenity_id=timezone_test_amenity.id,
        req=CreateBookingRequest(
            flat_id=FLAT_1203_ID,
            booking_date=date(2026, 11, 8),
            start_time="14:00",
            end_time="15:00",
            booked_units=1,
            auto_pay=True,
        ),
    )
    assert booking.status == BookingStatus.CONFIRMED

    # Case B first (past deadline): simulate attempt at 10:30 AM IST (05:00 UTC)
    late_time = datetime(2026, 11, 8, 5, 0, 0, tzinfo=UTC)
    monkeypatch.setattr("app.domains.amenities.service.utc_now", lambda: late_time)

    with pytest.raises(ConflictError) as exc_late:
        amenity_service.cancel_booking_by_resident(
            society_id=SOCIETY_PUNE_ID,
            user_id=NEERAJ_ID,
            booking_id=booking.id,
            reason="Can no longer attend",
        )
    assert exc_late.value.code == "CANCELLATION_DEADLINE_EXPIRED"

    # Case A (within deadline): simulate attempt at 09:30 AM IST (04:00 UTC)
    valid_time = datetime(2026, 11, 8, 4, 0, 0, tzinfo=UTC)
    monkeypatch.setattr("app.domains.amenities.service.utc_now", lambda: valid_time)

    cancelled = amenity_service.cancel_booking_by_resident(
        society_id=SOCIETY_PUNE_ID,
        user_id=NEERAJ_ID,
        booking_id=booking.id,
        reason="Plans changed before deadline",
    )
    assert cancelled.status == BookingStatus.CANCELLED
    assert cancelled.refund_status == RefundStatus.REFUNDED
    assert cancelled.refund_amount_paise == 20000  # 80% of 25000
    assert cancelled.cancelled_at == valid_time


# -----------------------------------------------------------------------------
# 6. Timezone-Aware Database Timestamps and Slot UTC Metadata Persistence
# -----------------------------------------------------------------------------


def test_booking_utc_metadata_and_timezone_aware_timestamps(
    amenity_service: AmenityService,
    timezone_test_amenity: Amenity,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies that:

    - Database timestamps (created_at, updated_at, payment_expires_at) are timezone-aware UTC.
    - booking_metadata stores slot_start_utc, slot_end_utc, and facility_timezone: "Asia/Kolkata".
    """
    fixed_now = datetime(2026, 11, 8, 1, 0, 0, tzinfo=UTC)  # 06:30 AM IST
    monkeypatch.setattr("app.domains.amenities.service.utc_now", lambda: fixed_now)

    booking = amenity_service.create_booking(
        society_id=SOCIETY_PUNE_ID,
        user_id=NEERAJ_ID,
        amenity_id=timezone_test_amenity.id,
        req=CreateBookingRequest(
            flat_id=FLAT_1203_ID,
            booking_date=date(2026, 11, 8),
            start_time="16:00",
            end_time="17:00",
            booked_units=1,
            auto_pay=False,  # Generates pending payment with 15min expiry
        ),
    )

    # 16:00 IST = 10:30 UTC
    expected_start_utc = "2026-11-08T10:30:00+00:00"
    expected_end_utc = "2026-11-08T11:30:00+00:00"

    assert booking.booking_metadata["facility_timezone"] == "Asia/Kolkata"
    assert booking.booking_metadata["slot_start_utc"] == expected_start_utc
    assert booking.booking_metadata["slot_end_utc"] == expected_end_utc

    # Verify timezone awareness of timestamps
    assert booking.created_at.tzinfo is not None
    assert booking.updated_at.tzinfo is not None
    assert booking.payment_expires_at is not None
    assert booking.payment_expires_at.tzinfo is not None
    assert booking.payment_expires_at == fixed_now + timedelta(minutes=15)


# -----------------------------------------------------------------------------
# 7. Resident Upcoming Bookings Filtering Across Midnight Boundary
# -----------------------------------------------------------------------------


def test_upcoming_bookings_filter_respects_facility_local_date(
    amenity_service: AmenityService,
    timezone_test_amenity: Amenity,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """At 20:00 UTC on Nov 7 (01:30 IST on Nov 8):

    - A booking on Nov 7 is in the past from the Pune resident's perspective.
    - A booking on Nov 8 is upcoming and must be included when upcoming_only=True.
    """
    # Create two confirmed bookings in the DB
    booking_past = AmenityBooking(
        id=uuid.uuid4(),
        society_id=SOCIETY_PUNE_ID,
        amenity_id=timezone_test_amenity.id,
        user_id=NEERAJ_ID,
        flat_id=FLAT_1203_ID,
        booking_date=date(2026, 11, 7),
        start_time="10:00",
        end_time="11:00",
        booked_units=1,
        status=BookingStatus.CONFIRMED,
        booking_fee_paise=25000,
        payment_status=BookingPaymentStatus.PAID,
    )
    booking_today = AmenityBooking(
        id=uuid.uuid4(),
        society_id=SOCIETY_PUNE_ID,
        amenity_id=timezone_test_amenity.id,
        user_id=NEERAJ_ID,
        flat_id=FLAT_1203_ID,
        booking_date=date(2026, 11, 8),
        start_time="10:00",
        end_time="11:00",
        booked_units=1,
        status=BookingStatus.CONFIRMED,
        booking_fee_paise=25000,
        payment_status=BookingPaymentStatus.PAID,
    )
    db_session.add_all([booking_past, booking_today])
    db_session.flush()

    # Freeze time to 20:00 UTC Nov 7 (= 01:30 IST Nov 8)
    frozen_utc = datetime(2026, 11, 7, 20, 0, 0, tzinfo=UTC)
    monkeypatch.setattr("app.domains.amenities.service.utc_now", lambda: frozen_utc)

    resp = amenity_service.get_user_bookings(
        society_id=SOCIETY_PUNE_ID,
        user_id=NEERAJ_ID,
        upcoming_only=True,
    )

    returned_ids = [b.id for b in resp.items]
    assert booking_today.id in returned_ids
    assert booking_past.id not in returned_ids
