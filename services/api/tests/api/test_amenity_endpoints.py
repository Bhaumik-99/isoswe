"""API Integration Tests for Amenity and Clubhouse Booking Endpoints.

Tests all endpoints under /api/v1/amenities:
- GET /api/v1/amenities (list active amenities)
- GET /api/v1/amenities/{id} (amenity details)
- GET /api/v1/amenities/{id}/slots (slot availability)
- POST /api/v1/amenities/{id}/bookings (create booking)
- GET /api/v1/amenities/bookings/me (resident bookings)
- GET /api/v1/amenities/bookings/{id} (booking details & IDOR check)
- POST /api/v1/amenities/bookings/{id}/cancel (resident cancel booking)
- POST /api/v1/amenities/staff (staff create amenity)
- PATCH /api/v1/amenities/staff/{id} (staff update amenity)
- POST /api/v1/amenities/staff/{id}/status (staff toggle status)
- GET /api/v1/amenities/staff/bookings (staff list bookings)
- POST /api/v1/amenities/staff/bookings/{id}/cancel (staff cancel booking)
- RBAC and Tenant Isolation security boundaries
"""

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.amenities.models import Amenity, AmenityType
from app.domains.amenities.service import utc_now

RESIDENT_NEERAJ_HEADERS = {"X-Dev-User": "neeraj"}
RESIDENT_SWATI_HEADERS = {"X-Dev-User": "swati"}
STAFF_HELPDESK_HEADERS = {"X-Dev-User": "helpdesk"}

SOCIETY_PUNE_ID = "11111111-1111-1111-1111-111111111111"
OTHER_SOCIETY_ID = "11111111-1111-1111-1111-111111111112"
FLAT_1203_ID = "33333333-3333-3333-3333-333333331203"
FLAT_0408_ID = "33333333-3333-3333-3333-333333330408"


@pytest.fixture
def test_amenity(db_session: Session) -> Amenity:
    amenity = Amenity(
        id=uuid.uuid4(),
        society_id=uuid.UUID(SOCIETY_PUNE_ID),
        name="Badminton Court Premium",
        description="Air-conditioned indoor badminton court",
        amenity_type=AmenityType.BADMINTON_COURT,
        location="Clubhouse 1st Floor",
        tower_id=None,
        capacity=1,
        slot_duration_minutes=60,
        opening_time="06:00",
        closing_time="22:00",
        booking_fee_paise=15000,
        advance_booking_days=7,
        min_advance_hours=1,
        max_slots_per_day_per_resident=2,
        cancellation_deadline_hours=2,
        refund_percentage=90,
        allowed_membership_types=["OWNER", "TENANT", "FAMILY_MEMBER"],
        is_active=True,
    )
    db_session.add(amenity)
    db_session.flush()
    return amenity


# -----------------------------------------------------------------------------
# Resident Amenity Discovery & Slot Retrieval
# -----------------------------------------------------------------------------


def test_resident_list_amenities(client: TestClient, test_amenity: Amenity) -> None:
    resp = client.get("/api/v1/amenities", headers=RESIDENT_NEERAJ_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    names = [a["name"] for a in data["items"]]
    assert "Badminton Court Premium" in names

    # Filter by amenity type
    resp_filtered = client.get(
        "/api/v1/amenities?amenity_type=BADMINTON_COURT",
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert resp_filtered.status_code == 200
    for item in resp_filtered.json()["items"]:
        assert item["amenity_type"] == "BADMINTON_COURT"


def test_resident_get_amenity_details(client: TestClient, test_amenity: Amenity) -> None:
    resp = client.get(
        f"/api/v1/amenities/{test_amenity.id}",
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(test_amenity.id)
    assert data["booking_fee_paise"] == 15000
    assert data["cancellation_deadline_hours"] == 2
    assert data["refund_percentage"] == 90


def test_resident_get_slots(client: TestClient, test_amenity: Amenity) -> None:
    target_date = str(utc_now().date() + timedelta(days=2))
    resp = client.get(
        f"/api/v1/amenities/{test_amenity.id}/slots?booking_date={target_date}",
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["amenity_id"] == str(test_amenity.id)
    assert data["booking_date"] == target_date
    assert len(data["slots"]) == 16  # 06:00 to 22:00 in 60-min steps


# -----------------------------------------------------------------------------
# Resident Booking Flow & IDOR Security
# -----------------------------------------------------------------------------


def test_resident_create_and_view_booking(client: TestClient, test_amenity: Amenity) -> None:
    target_date = str(utc_now().date() + timedelta(days=2))
    booking_payload = {
        "flat_id": FLAT_1203_ID,
        "booking_date": target_date,
        "start_time": "08:00",
        "end_time": "09:00",
        "booked_units": 1,
        "notes": "Morning match with friend",
    }

    # 1. Neeraj creates booking
    create_resp = client.post(
        f"/api/v1/amenities/{test_amenity.id}/bookings",
        headers=RESIDENT_NEERAJ_HEADERS,
        json=booking_payload,
    )
    assert create_resp.status_code == 201
    booking_data = create_resp.json()
    booking_id = booking_data["id"]
    assert booking_data["status"] == "CONFIRMED"
    assert booking_data["booking_fee_paise"] == 15000
    assert booking_data["payment_status"] == "PAID"

    # 2. Neeraj views own bookings list
    me_resp = client.get("/api/v1/amenities/bookings/me", headers=RESIDENT_NEERAJ_HEADERS)
    assert me_resp.status_code == 200
    assert me_resp.json()["total"] >= 1
    my_ids = [b["id"] for b in me_resp.json()["items"]]
    assert booking_id in my_ids

    # 3. Neeraj views single booking details
    detail_resp = client.get(
        f"/api/v1/amenities/bookings/{booking_id}",
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert detail_resp.status_code == 200
    assert detail_resp.json()["id"] == booking_id

    # 4. IDOR Protection: Swati attempts to view Neeraj's booking -> 404
    idor_get = client.get(
        f"/api/v1/amenities/bookings/{booking_id}",
        headers=RESIDENT_SWATI_HEADERS,
    )
    assert idor_get.status_code == 404

    # 5. IDOR Protection: Swati attempts to cancel Neeraj's booking -> 404
    idor_cancel = client.post(
        f"/api/v1/amenities/bookings/{booking_id}/cancel",
        headers=RESIDENT_SWATI_HEADERS,
        json={"reason": "Malicious cancellation attempt"},
    )
    assert idor_cancel.status_code == 404

    # 6. Neeraj cancels own booking -> 200 with refund
    cancel_resp = client.post(
        f"/api/v1/amenities/bookings/{booking_id}/cancel",
        headers=RESIDENT_NEERAJ_HEADERS,
        json={"reason": "Cannot attend"},
    )
    assert cancel_resp.status_code == 200
    cancel_data = cancel_resp.json()
    assert cancel_data["status"] == "CANCELLED"
    # 90% of 15000 paise = 13500 paise
    assert cancel_data["refund_status"] == "REFUNDED"
    assert cancel_data["refund_amount_paise"] == 13500


def test_booking_capacity_conflict(client: TestClient, test_amenity: Amenity) -> None:
    target_date = str(utc_now().date() + timedelta(days=2))
    payload = {
        "flat_id": FLAT_1203_ID,
        "booking_date": target_date,
        "start_time": "14:00",
        "end_time": "15:00",
        "booked_units": 1,
    }
    # 1. Neeraj books
    res1 = client.post(
        f"/api/v1/amenities/{test_amenity.id}/bookings",
        headers=RESIDENT_NEERAJ_HEADERS,
        json=payload,
    )
    assert res1.status_code == 201

    # 2. Swati tries to book same slot (capacity is 1) -> 409 Conflict
    swati_payload = {
        "flat_id": FLAT_0408_ID,
        "booking_date": target_date,
        "start_time": "14:00",
        "end_time": "15:00",
        "booked_units": 1,
    }
    res2 = client.post(
        f"/api/v1/amenities/{test_amenity.id}/bookings",
        headers=RESIDENT_SWATI_HEADERS,
        json=swati_payload,
    )
    assert res2.status_code == 409


# -----------------------------------------------------------------------------
# Staff Amenity Management & RBAC Tests
# -----------------------------------------------------------------------------


def test_resident_forbidden_from_staff_endpoints(client: TestClient, test_amenity: Amenity) -> None:
    # Resident cannot create amenity
    create_res = client.post(
        "/api/v1/amenities/staff",
        headers=RESIDENT_NEERAJ_HEADERS,
        json={"name": "Illegal Court", "amenity_type": "TENNIS_COURT"},
    )
    assert create_res.status_code == 403

    # Resident cannot toggle status
    status_res = client.post(
        f"/api/v1/amenities/staff/{test_amenity.id}/status",
        headers=RESIDENT_NEERAJ_HEADERS,
        json={"is_active": False},
    )
    assert status_res.status_code == 403

    # Resident cannot view staff bookings
    bookings_res = client.get(
        "/api/v1/amenities/staff/bookings",
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert bookings_res.status_code == 403


def test_staff_create_update_toggle_and_cancel_booking(
    client: TestClient, db_session: Session
) -> None:
    # 1. Staff creates community hall
    create_payload = {
        "name": "Community Grand Hall",
        "description": "Multi-purpose hall for cultural celebrations",
        "amenity_type": "COMMUNITY_HALL",
        "location": "Clubhouse 2nd Floor",
        "capacity": 1,
        "slot_duration_minutes": 180,
        "opening_time": "09:00",
        "closing_time": "21:00",
        "booking_fee_paise": 500000,  # 5,000.00 INR
        "advance_booking_days": 30,
        "min_advance_hours": 24,
        "max_slots_per_day_per_resident": 1,
        "cancellation_deadline_hours": 48,
        "refund_percentage": 50,
        "allowed_membership_types": ["OWNER", "TENANT"],
        "is_active": True,
        "rules_and_guidelines": "No loud music after 22:00.",
    }
    create_resp = client.post(
        "/api/v1/amenities/staff",
        headers=STAFF_HELPDESK_HEADERS,
        json=create_payload,
    )
    assert create_resp.status_code == 201
    amenity_id = create_resp.json()["id"]

    # 2. Staff updates amenity rules and fee
    update_resp = client.patch(
        f"/api/v1/amenities/staff/{amenity_id}",
        headers=STAFF_HELPDESK_HEADERS,
        json={"booking_fee_paise": 450000, "refund_percentage": 60},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["booking_fee_paise"] == 450000
    assert update_resp.json()["refund_percentage"] == 60

    # 3. Staff toggles active status
    status_resp = client.post(
        f"/api/v1/amenities/staff/{amenity_id}/status",
        headers=STAFF_HELPDESK_HEADERS,
        json={"is_active": True},
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["is_active"] is True

    # 4. Resident books the hall (3 days in advance)
    target_date = str(utc_now().date() + timedelta(days=3))
    book_resp = client.post(
        f"/api/v1/amenities/{amenity_id}/bookings",
        headers=RESIDENT_NEERAJ_HEADERS,
        json={
            "flat_id": FLAT_1203_ID,
            "booking_date": target_date,
            "start_time": "09:00",
            "end_time": "12:00",
            "booked_units": 1,
            "notes": "Birthday celebration",
        },
    )
    assert book_resp.status_code == 201
    booking_id = book_resp.json()["id"]

    # 5. Staff lists bookings
    staff_list = client.get(
        "/api/v1/amenities/staff/bookings",
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert staff_list.status_code == 200
    assert staff_list.json()["total"] >= 1

    # 6. Staff cancels booking with reason (e.g. electrical inspection emergency)
    cancel_resp = client.post(
        f"/api/v1/amenities/staff/bookings/{booking_id}/cancel",
        headers=STAFF_HELPDESK_HEADERS,
        json={"reason": "Emergency electrical conduit repairs in Clubhouse"},
    )
    assert cancel_resp.status_code == 200
    cancelled_data = cancel_resp.json()
    assert cancelled_data["status"] == "CANCELLED"
    # Staff cancellation gives 100% full refund
    assert cancelled_data["refund_status"] == "REFUNDED"
    assert cancelled_data["refund_amount_paise"] == 450000
    assert "electrical" in cancelled_data["cancellation_reason"].lower()


# -----------------------------------------------------------------------------
# Cross-Society Tenant Isolation
# -----------------------------------------------------------------------------


def test_cross_society_access_denied(client: TestClient, test_amenity: Amenity) -> None:
    # Resident attempts to specify an unauthorized society ID
    resp = client.get(
        f"/api/v1/amenities?society_id={OTHER_SOCIETY_ID}",
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert resp.status_code == 403
