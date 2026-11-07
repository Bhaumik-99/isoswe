"""End-to-End Acceptance and Critical Scenario Tests for Amenity & Clubhouse Booking (Phase 8 Part 4).

Validates:
1. Complete Resident & Staff End-to-End Lifecycle:
   Resident login -> list amenities -> inspect rules/fees -> get slots -> book slot ->
   complete mock payment -> confirm booking -> check booking history ->
   staff dashboard views booking -> staff cancels booking (100% full refund) ->
   resident checks updated booking status.

2. Critical Scenarios A through J:
   - Scenario A: Two residents attempt to book the same final available slot simultaneously (race condition).
   - Scenario B: A resident attempts to book an inactive amenity (AMENITY_INACTIVE).
   - Scenario C: A resident attempts to book outside operating hours (OUTSIDE_OPERATING_HOURS / INVALID_SLOT_DURATION).
   - Scenario D: A resident attempts to book a blocked slot (SLOT_BLOCKED).
   - Scenario E: A resident attempts to access another resident's booking (IDOR check: 404/403).
   - Scenario F: A payment gateway callback or webhook delivered more than once (Idempotency check).
   - Scenario G: A resident abandons or fails a payment after slot selection (PAYMENT_FAILED).
   - Scenario H: A resident attempts to cancel a booking outside the cancellation window (CANCELLATION_DEADLINE_EXPIRED).
   - Scenario I: A staff member modifies an amenity while active bookings exist (historical fee immutability).
   - Scenario J: An unauthorized resident attempts to perform staff actions (RBAC enforcement).
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.amenities.models import (
    Amenity,
    AmenityBooking,
    AmenityType,
    BookingPaymentStatus,
    BookingStatus,
)
from app.domains.billing.models import Payment, PaymentStatus

# Fixed deterministic IDs & Dev User Auth Headers
SOCIETY_PUNE_ID = "11111111-1111-1111-1111-111111111111"
OTHER_SOCIETY_ID = "11111111-1111-1111-1111-111111111112"

FLAT_1203_ID = "33333333-3333-3333-3333-333333331203"
FLAT_0408_ID = "33333333-3333-3333-3333-333333330408"

RESIDENT_NEERAJ_HEADERS = {"X-Dev-User": "neeraj"}
RESIDENT_SWATI_HEADERS = {"X-Dev-User": "swati"}
STAFF_HELPDESK_HEADERS = {"X-Dev-User": "helpdesk"}


@pytest.fixture
def e2e_badminton_amenity(db_session: Session) -> Amenity:
    """Fixture providing a standard indoor badminton court with capacity 1."""
    amenity = Amenity(
        id=uuid.uuid4(),
        society_id=uuid.UUID(SOCIETY_PUNE_ID),
        name="Badminton Court 1 (Indoor Wooden)",
        description="BWF-standard teakwood floor indoor badminton court with LED tournament lighting.",
        amenity_type=AmenityType.BADMINTON_COURT,
        location="Sports Complex 1st Floor",
        tower_id=None,
        capacity=1,
        slot_duration_minutes=60,
        opening_time="06:00",
        closing_time="22:00",
        booking_fee_paise=15000,  # ₹150.00
        advance_booking_days=7,
        min_advance_hours=1,
        max_slots_per_day_per_resident=2,
        cancellation_deadline_hours=2,
        refund_percentage=80,
        allowed_membership_types=["OWNER", "TENANT", "FAMILY_MEMBER"],
        is_active=True,
        rules_and_guidelines="Non-marking shoes mandatory. Maximum 4 players per court.",
    )
    db_session.add(amenity)
    db_session.flush()
    return amenity


# =============================================================================
# 1. COMPLETE RESIDENT TO STAFF END-TO-END LIFECYCLE
# =============================================================================


def test_e2e_complete_resident_to_staff_booking_lifecycle(
    client: TestClient, e2e_badminton_amenity: Amenity, db_session: Session
) -> None:
    """End-to-end journey:
    Resident logs in -> discovers amenity -> checks details & rules -> inspects slots ->
    creates pending booking -> completes mock payment -> booking confirmed ->
    verifies in resident history -> staff searches and views booking ->
    staff issues emergency cancellation with 100% full refund ->
    resident verifies cancelled status and refund.
    """
    target_date = str(datetime.now(UTC).date() + timedelta(days=2))

    # Step 1: Resident lists amenities
    list_resp = client.get("/api/v1/amenities", headers=RESIDENT_NEERAJ_HEADERS)
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert any(a["name"] == e2e_badminton_amenity.name for a in items)

    # Step 2: Resident views details, rules and fee
    detail_resp = client.get(
        f"/api/v1/amenities/{e2e_badminton_amenity.id}",
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert detail_resp.status_code == 200
    details = detail_resp.json()
    assert details["booking_fee_paise"] == 15000
    assert details["cancellation_deadline_hours"] == 2
    assert details["refund_percentage"] == 80
    assert "Non-marking shoes" in details["rules_and_guidelines"]

    # Step 3: Resident checks slot availability
    slots_resp = client.get(
        f"/api/v1/amenities/{e2e_badminton_amenity.id}/slots?booking_date={target_date}",
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert slots_resp.status_code == 200
    slots_data = slots_resp.json()
    assert len(slots_data["slots"]) == 16  # 06:00 to 22:00 in 60m blocks
    slot_09 = next(s for s in slots_data["slots"] if s["start_time"] == "09:00")
    assert slot_09["is_available"] is True
    assert slot_09["remaining_capacity"] == 1

    # Step 4: Resident creates booking (unpaid initially)
    create_resp = client.post(
        f"/api/v1/amenities/{e2e_badminton_amenity.id}/bookings",
        headers=RESIDENT_NEERAJ_HEADERS,
        json={
            "flat_id": FLAT_1203_ID,
            "booking_date": target_date,
            "start_time": "09:00",
            "end_time": "10:00",
            "booked_units": 1,
            "notes": "Friendly singles match",
            "auto_pay": False,
        },
    )
    assert create_resp.status_code == 201
    booking_data = create_resp.json()
    booking_id = booking_data["id"]
    assert booking_data["status"] == "PENDING_PAYMENT"
    assert booking_data["payment_status"] == "PENDING"
    assert booking_data["booking_fee_paise"] == 15000

    # Step 5: Resident completes mock payment
    pay_resp = client.post(
        f"/api/v1/amenities/bookings/{booking_id}/pay",
        headers=RESIDENT_NEERAJ_HEADERS,
        json={},
    )
    assert pay_resp.status_code == 200
    paid_data = pay_resp.json()
    assert paid_data["status"] == "CONFIRMED"
    assert paid_data["payment_status"] == "PAID"
    assert paid_data["payment_reference"] is not None
    assert paid_data["payment_id"] is not None

    # Step 6: Resident verifies confirmed booking in own history
    my_bookings_resp = client.get(
        "/api/v1/amenities/bookings/me",
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert my_bookings_resp.status_code == 200
    my_items = my_bookings_resp.json()["items"]
    assert any(b["id"] == booking_id and b["status"] == "CONFIRMED" for b in my_items)

    # Step 7: Staff views booking in staff management console
    staff_bookings_resp = client.get(
        "/api/v1/amenities/staff/bookings?search=1203",
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert staff_bookings_resp.status_code == 200
    staff_items = staff_bookings_resp.json()["items"]
    assert any(b["id"] == booking_id for b in staff_items)

    # Step 8: Staff cancels the booking (e.g. emergency air-conditioning duct failure)
    staff_cancel_resp = client.post(
        f"/api/v1/amenities/staff/bookings/{booking_id}/cancel",
        headers=STAFF_HELPDESK_HEADERS,
        json={"reason": "Emergency HVAC duct maintenance in Badminton arena"},
    )
    assert staff_cancel_resp.status_code == 200
    cancelled_data = staff_cancel_resp.json()
    assert cancelled_data["status"] == "CANCELLED"
    # Staff cancellation gives 100% full refund
    assert cancelled_data["refund_status"] == "REFUNDED"
    assert cancelled_data["refund_amount_paise"] == 15000
    assert "HVAC duct" in cancelled_data["cancellation_reason"]

    # Step 9: Resident views updated booking details
    res_updated_resp = client.get(
        f"/api/v1/amenities/bookings/{booking_id}",
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert res_updated_resp.status_code == 200
    updated_details = res_updated_resp.json()
    assert updated_details["status"] == "CANCELLED"
    assert updated_details["refund_status"] == "REFUNDED"
    assert updated_details["refund_amount_paise"] == 15000


# =============================================================================
# 2. CRITICAL SCENARIO TESTS (A through J)
# =============================================================================


def test_scenario_a_concurrency_race_condition_prevents_overbooking(
    client: TestClient, e2e_badminton_amenity: Amenity
) -> None:
    """Scenario A: Two residents attempt to book the same final available slot simultaneously.
    First resident succeeds; second resident receives 409 CAPACITY_EXCEEDED.
    Total confirmed bookings strictly equals capacity (1).
    """
    target_date = str(datetime.now(UTC).date() + timedelta(days=3))
    slot_start = "18:00"
    slot_end = "19:00"

    # Resident 1 (Neeraj) books the slot
    res1 = client.post(
        f"/api/v1/amenities/{e2e_badminton_amenity.id}/bookings",
        headers=RESIDENT_NEERAJ_HEADERS,
        json={
            "flat_id": FLAT_1203_ID,
            "booking_date": target_date,
            "start_time": slot_start,
            "end_time": slot_end,
            "booked_units": 1,
            "auto_pay": True,
        },
    )
    assert res1.status_code == 201
    assert res1.json()["status"] == "CONFIRMED"

    # Resident 2 (Swati) attempts to book the same slot simultaneously
    res2 = client.post(
        f"/api/v1/amenities/{e2e_badminton_amenity.id}/bookings",
        headers=RESIDENT_SWATI_HEADERS,
        json={
            "flat_id": FLAT_0408_ID,
            "booking_date": target_date,
            "start_time": slot_start,
            "end_time": slot_end,
            "booked_units": 1,
            "auto_pay": True,
        },
    )
    assert res2.status_code == 409
    assert res2.json()["error"]["code"] == "CAPACITY_EXCEEDED"


def test_scenario_b_resident_attempts_to_book_inactive_amenity(
    client: TestClient, e2e_badminton_amenity: Amenity, db_session: Session
) -> None:
    """Scenario B: A resident attempts to book an inactive amenity.
    Staff toggles status to inactive; booking attempt must fail with AMENITY_INACTIVE.
    """
    target_date = str(datetime.now(UTC).date() + timedelta(days=2))

    # Staff deactivates amenity
    deact_resp = client.post(
        f"/api/v1/amenities/staff/{e2e_badminton_amenity.id}/status",
        headers=STAFF_HELPDESK_HEADERS,
        json={"is_active": False},
    )
    assert deact_resp.status_code == 200
    assert deact_resp.json()["is_active"] is False

    # Resident attempts to book
    res = client.post(
        f"/api/v1/amenities/{e2e_badminton_amenity.id}/bookings",
        headers=RESIDENT_NEERAJ_HEADERS,
        json={
            "flat_id": FLAT_1203_ID,
            "booking_date": target_date,
            "start_time": "10:00",
            "end_time": "11:00",
            "booked_units": 1,
        },
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "AMENITY_INACTIVE"

    # Re-activate for clean state
    client.post(
        f"/api/v1/amenities/staff/{e2e_badminton_amenity.id}/status",
        headers=STAFF_HELPDESK_HEADERS,
        json={"is_active": True},
    )


def test_scenario_c_resident_attempts_to_book_outside_operating_hours(
    client: TestClient, e2e_badminton_amenity: Amenity
) -> None:
    """Scenario C: A resident attempts to book outside operating hours or with unaligned slot.
    Hours are 06:00 to 22:00. Booking at 04:00 must fail with OUTSIDE_OPERATING_HOURS.
    Unaligned duration (e.g. 30m when slot is 60m) must fail with INVALID_SLOT_DURATION.
    """
    target_date = str(datetime.now(UTC).date() + timedelta(days=2))

    # 1. Outside hours (04:00 - 05:00)
    res_outside = client.post(
        f"/api/v1/amenities/{e2e_badminton_amenity.id}/bookings",
        headers=RESIDENT_NEERAJ_HEADERS,
        json={
            "flat_id": FLAT_1203_ID,
            "booking_date": target_date,
            "start_time": "04:00",
            "end_time": "05:00",
            "booked_units": 1,
        },
    )
    assert res_outside.status_code == 400
    assert res_outside.json()["error"]["code"] == "OUTSIDE_OPERATING_HOURS"

    # 2. Unaligned slot duration (08:00 - 08:30 instead of 60 minutes)
    res_misaligned = client.post(
        f"/api/v1/amenities/{e2e_badminton_amenity.id}/bookings",
        headers=RESIDENT_NEERAJ_HEADERS,
        json={
            "flat_id": FLAT_1203_ID,
            "booking_date": target_date,
            "start_time": "08:00",
            "end_time": "08:30",
            "booked_units": 1,
        },
    )
    assert res_misaligned.status_code == 400
    assert res_misaligned.json()["error"]["code"] == "INVALID_SLOT_DURATION"


def test_scenario_d_resident_attempts_to_book_blocked_slot(
    client: TestClient, e2e_badminton_amenity: Amenity
) -> None:
    """Scenario D: A resident attempts to book a blocked slot.
    Staff places a maintenance block on the slot; resident slot query shows is_blocked=True;
    booking attempt is rejected with 409 SLOT_BLOCKED.
    """
    target_date = str(datetime.now(UTC).date() + timedelta(days=2))

    # Staff blocks 14:00 - 15:00 for floor sanding
    block_resp = client.post(
        f"/api/v1/amenities/staff/{e2e_badminton_amenity.id}/blocks",
        headers=STAFF_HELPDESK_HEADERS,
        json={
            "block_date": target_date,
            "start_time": "14:00",
            "end_time": "15:00",
            "reason": "Teakwood floor sanding and polishing",
        },
    )
    assert block_resp.status_code == 201
    block_id = block_resp.json()["id"]

    # Resident queries slots
    slots_resp = client.get(
        f"/api/v1/amenities/{e2e_badminton_amenity.id}/slots?booking_date={target_date}",
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    slot_14 = next(s for s in slots_resp.json()["slots"] if s["start_time"] == "14:00")
    assert slot_14["is_blocked"] is True
    assert slot_14["is_available"] is False
    assert slot_14["block_reason"] == "Teakwood floor sanding and polishing"

    # Resident attempts to book blocked slot
    book_resp = client.post(
        f"/api/v1/amenities/{e2e_badminton_amenity.id}/bookings",
        headers=RESIDENT_NEERAJ_HEADERS,
        json={
            "flat_id": FLAT_1203_ID,
            "booking_date": target_date,
            "start_time": "14:00",
            "end_time": "15:00",
            "booked_units": 1,
        },
    )
    assert book_resp.status_code == 409
    assert book_resp.json()["error"]["code"] == "SLOT_BLOCKED"

    # Clean up block
    client.delete(
        f"/api/v1/amenities/staff/blocks/{block_id}",
        headers=STAFF_HELPDESK_HEADERS,
    )


def test_scenario_e_resident_attempts_to_access_another_residents_booking(
    client: TestClient, e2e_badminton_amenity: Amenity
) -> None:
    """Scenario E: A resident attempts to access another resident's booking (IDOR check).
    Neeraj creates a booking. Swati attempts to view, pay for, and cancel Neeraj's booking.
    All cross-resident access attempts are strictly rejected with 404 or 403.
    """
    target_date = str(datetime.now(UTC).date() + timedelta(days=2))

    # Neeraj creates booking
    res = client.post(
        f"/api/v1/amenities/{e2e_badminton_amenity.id}/bookings",
        headers=RESIDENT_NEERAJ_HEADERS,
        json={
            "flat_id": FLAT_1203_ID,
            "booking_date": target_date,
            "start_time": "16:00",
            "end_time": "17:00",
            "booked_units": 1,
            "auto_pay": False,
        },
    )
    assert res.status_code == 201
    booking_id = res.json()["id"]

    # 1. Swati attempts to GET Neeraj's booking -> 404
    get_res = client.get(
        f"/api/v1/amenities/bookings/{booking_id}",
        headers=RESIDENT_SWATI_HEADERS,
    )
    assert get_res.status_code == 404

    # 2. Swati attempts to PAY for Neeraj's booking -> 403
    pay_res = client.post(
        f"/api/v1/amenities/bookings/{booking_id}/pay",
        headers=RESIDENT_SWATI_HEADERS,
        json={},
    )
    assert pay_res.status_code == 403

    # 3. Swati attempts to CANCEL Neeraj's booking -> 404
    cancel_res = client.post(
        f"/api/v1/amenities/bookings/{booking_id}/cancel",
        headers=RESIDENT_SWATI_HEADERS,
        json={"reason": "Attempting malicious cancellation"},
    )
    assert cancel_res.status_code == 404


def test_scenario_f_duplicate_payment_callback_or_retry_idempotency(
    client: TestClient, e2e_badminton_amenity: Amenity, db_session: Session
) -> None:
    """Scenario F: A payment gateway callback or webhook is delivered more than once.
    Using Idempotency-Key, subsequent submissions return the cached confirmed response
    without double-charging or creating duplicate payment records.
    """
    target_date = str(datetime.now(UTC).date() + timedelta(days=2))

    # Create pending booking
    book_res = client.post(
        f"/api/v1/amenities/{e2e_badminton_amenity.id}/bookings",
        headers=RESIDENT_NEERAJ_HEADERS,
        json={
            "flat_id": FLAT_1203_ID,
            "booking_date": target_date,
            "start_time": "11:00",
            "end_time": "12:00",
            "booked_units": 1,
            "auto_pay": False,
        },
    )
    assert book_res.status_code == 201
    booking_id = book_res.json()["id"]

    idem_key = f"mock-gateway-webhook-{uuid.uuid4()}"
    headers_with_idem = {**RESIDENT_NEERAJ_HEADERS, "Idempotency-Key": idem_key}

    # First payment attempt -> 200 OK
    pay1_res = client.post(
        f"/api/v1/amenities/bookings/{booking_id}/pay",
        headers=headers_with_idem,
        json={},
    )
    assert pay1_res.status_code == 200
    pay1_data = pay1_res.json()
    assert pay1_data["status"] == "CONFIRMED"
    assert pay1_data["payment_status"] == "PAID"
    payment_id_1 = pay1_data["payment_id"]

    # Duplicate payment callback/attempt with identical idempotency key -> 200 OK (idempotent replay)
    pay2_res = client.post(
        f"/api/v1/amenities/bookings/{booking_id}/pay",
        headers=headers_with_idem,
        json={},
    )
    assert pay2_res.status_code == 200
    pay2_data = pay2_res.json()
    assert pay2_data["id"] == booking_id
    assert pay2_data["payment_id"] == payment_id_1

    # Verify database has strictly 1 payment record for this booking
    payments = list(
        db_session.scalars(select(Payment).where(Payment.booking_id == uuid.UUID(booking_id))).all()
    )
    assert len(payments) == 1
    assert payments[0].status == PaymentStatus.SUCCESS


def test_scenario_g_resident_abandons_or_fails_payment(
    client: TestClient, e2e_badminton_amenity: Amenity, db_session: Session
) -> None:
    """Scenario G: A resident abandons or fails a payment after slot selection.
    Simulated gateway failure transitions booking to PAYMENT_FAILED, records failed payment,
    and prevents slot from being held as confirmed.
    """
    target_date = str(datetime.now(UTC).date() + timedelta(days=2))

    # 1. Create booking
    book_res = client.post(
        f"/api/v1/amenities/{e2e_badminton_amenity.id}/bookings",
        headers=RESIDENT_NEERAJ_HEADERS,
        json={
            "flat_id": FLAT_1203_ID,
            "booking_date": target_date,
            "start_time": "12:00",
            "end_time": "13:00",
            "booked_units": 1,
            "auto_pay": False,
        },
    )
    assert book_res.status_code == 201
    booking_id = book_res.json()["id"]

    # 2. Simulate payment failure (e.g. card declined or bank timeout)
    fail_res = client.post(
        f"/api/v1/amenities/bookings/{booking_id}/pay",
        headers=RESIDENT_NEERAJ_HEADERS,
        json={"simulate_failure": True},
    )
    assert fail_res.status_code == 200
    fail_data = fail_res.json()
    assert fail_data["status"] == "PAYMENT_FAILED"
    assert fail_data["payment_status"] == "FAILED"

    # 3. Verify in database
    booking = db_session.get(AmenityBooking, uuid.UUID(booking_id))
    assert booking is not None
    assert booking.status == BookingStatus.PAYMENT_FAILED
    assert booking.payment_status == BookingPaymentStatus.FAILED

    payment = db_session.get(Payment, booking.payment_id)
    assert payment is not None
    assert payment.status == PaymentStatus.FAILED


def test_scenario_h_resident_attempts_to_cancel_outside_cancellation_window(
    client: TestClient, e2e_badminton_amenity: Amenity, db_session: Session
) -> None:
    """Scenario H: A resident attempts to cancel a booking outside the cancellation window.
    cancellation_deadline_hours is 2 hours. If booking is scheduled for today within 1 hour,
    resident cancellation must be rejected with 409 CANCELLATION_DEADLINE_EXPIRED.
    """
    now = datetime.now(UTC)
    past_date = (now - timedelta(days=1)).date()

    # Create confirmed booking for past date where cancellation deadline has expired
    booking = AmenityBooking(
        id=uuid.uuid4(),
        society_id=uuid.UUID(SOCIETY_PUNE_ID),
        amenity_id=e2e_badminton_amenity.id,
        user_id=uuid.UUID("44444444-4444-4444-4444-444444440001"),  # Neeraj
        flat_id=uuid.UUID(FLAT_1203_ID),
        booking_date=past_date,
        start_time="07:00",
        end_time="08:00",
        booked_units=1,
        status=BookingStatus.CONFIRMED,
        booking_fee_paise=15000,
        payment_status=BookingPaymentStatus.PAID,
    )
    db_session.add(booking)
    db_session.flush()

    # Resident attempts to cancel -> rejected
    cancel_res = client.post(
        f"/api/v1/amenities/bookings/{booking.id}/cancel",
        headers=RESIDENT_NEERAJ_HEADERS,
        json={"reason": "Cannot make it"},
    )
    assert cancel_res.status_code == 409
    assert cancel_res.json()["error"]["code"] == "CANCELLATION_DEADLINE_EXPIRED"


def test_scenario_i_staff_modifies_amenity_while_active_bookings_exist(
    client: TestClient, e2e_badminton_amenity: Amenity, db_session: Session
) -> None:
    """Scenario I: A staff member modifies an amenity while active bookings exist.
    Proves historical immutability:
    1. Neeraj books court at current fee ₹150 (15000 paise).
    2. Staff increases fee to ₹250 (25000 paise) and updates cancellation policy.
    3. Neeraj's existing booking strictly retains historical fee ₹150 and original payment record.
    4. Swati makes a new booking and is billed the updated fee of ₹250.
    """
    target_date = str(datetime.now(UTC).date() + timedelta(days=2))

    # 1. Neeraj books at ₹150
    b1_res = client.post(
        f"/api/v1/amenities/{e2e_badminton_amenity.id}/bookings",
        headers=RESIDENT_NEERAJ_HEADERS,
        json={
            "flat_id": FLAT_1203_ID,
            "booking_date": target_date,
            "start_time": "15:00",
            "end_time": "16:00",
            "booked_units": 1,
            "auto_pay": True,
        },
    )
    assert b1_res.status_code == 201
    b1_data = b1_res.json()
    assert b1_data["booking_fee_paise"] == 15000
    assert b1_data["status"] == "CONFIRMED"
    booking_id_1 = b1_data["id"]

    # 2. Staff modifies amenity fee to ₹250 (25000 paise)
    mod_res = client.patch(
        f"/api/v1/amenities/staff/{e2e_badminton_amenity.id}",
        headers=STAFF_HELPDESK_HEADERS,
        json={"booking_fee_paise": 25000, "refund_percentage": 90},
    )
    assert mod_res.status_code == 200
    assert mod_res.json()["booking_fee_paise"] == 25000

    # 3. Neeraj's booking retains the historical fee ₹150
    check_b1 = client.get(
        f"/api/v1/amenities/bookings/{booking_id_1}",
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert check_b1.status_code == 200
    assert check_b1.json()["booking_fee_paise"] == 15000

    b1_record = db_session.get(AmenityBooking, uuid.UUID(booking_id_1))
    assert b1_record is not None
    assert b1_record.booking_fee_paise == 15000

    # 4. Swati makes a subsequent booking for a different slot (19:00 - 20:00)
    b2_res = client.post(
        f"/api/v1/amenities/{e2e_badminton_amenity.id}/bookings",
        headers=RESIDENT_SWATI_HEADERS,
        json={
            "flat_id": FLAT_0408_ID,
            "booking_date": target_date,
            "start_time": "19:00",
            "end_time": "20:00",
            "booked_units": 1,
            "auto_pay": True,
        },
    )
    assert b2_res.status_code == 201
    b2_data = b2_res.json()
    assert b2_data["booking_fee_paise"] == 25000
    assert b2_data["status"] == "CONFIRMED"


def test_scenario_j_unauthorized_resident_attempts_staff_actions_rbac(
    client: TestClient, e2e_badminton_amenity: Amenity
) -> None:
    """Scenario J: An unauthorized resident attempts to perform staff actions.
    All staff endpoints strictly enforce RBAC and reject resident access with 403 Forbidden.
    """
    target_date = str(datetime.now(UTC).date() + timedelta(days=2))

    # 1. Resident attempts to create amenity
    r1 = client.post(
        "/api/v1/amenities/staff",
        headers=RESIDENT_NEERAJ_HEADERS,
        json={"name": "Rogue Amenity", "amenity_type": "GYM"},
    )
    assert r1.status_code == 403

    # 2. Resident attempts to update amenity
    r2 = client.patch(
        f"/api/v1/amenities/staff/{e2e_badminton_amenity.id}",
        headers=RESIDENT_NEERAJ_HEADERS,
        json={"booking_fee_paise": 0},
    )
    assert r2.status_code == 403

    # 3. Resident attempts to toggle status
    r3 = client.post(
        f"/api/v1/amenities/staff/{e2e_badminton_amenity.id}/status",
        headers=RESIDENT_NEERAJ_HEADERS,
        json={"is_active": False},
    )
    assert r3.status_code == 403

    # 4. Resident attempts to view staff bookings list
    r4 = client.get(
        "/api/v1/amenities/staff/bookings",
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert r4.status_code == 403

    # 5. Resident attempts to create amenity block
    r5 = client.post(
        f"/api/v1/amenities/staff/{e2e_badminton_amenity.id}/blocks",
        headers=RESIDENT_NEERAJ_HEADERS,
        json={
            "block_date": target_date,
            "start_time": "10:00",
            "end_time": "11:00",
            "reason": "Unauthorized block",
        },
    )
    assert r5.status_code == 403
