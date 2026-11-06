"""Tier 2: Boundary Value Analysis (BVA), Limits & Corner Cases Test Suite.

Covers:
- Input String Boundaries (empty, whitespace, min/max length, extreme sizes)
- Phone Number Normalization & E.164 Adherence (+91, digits, invalid symbols)
- Vehicle Registration Formats & Maximum Length Limits
- Destination Flat Validity & Society Boundary Enforcements
- Guest Pass Limits (max_uses 0, negative, >10, valid_until <= valid_from)
- 90-Day Retention Timestamp Boundaries (Day 89 vs Day 90+1s)
- Batch Synchronization Boundaries (empty arrays, missing client_event_id, size limits)
- Pagination Limits (limit=0, limit>50, negative offset)
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from services.api.tests.e2e.conftest import (
    FLAT_1203_ID,
    FLAT_OTHER_ID,
    GATE_1_ID,
    GATE_GUARD_HEADERS,
    NEERAJ_HEADERS,
    SOCIETY_PUNE_ID,
)
from sqlalchemy import text
from sqlalchemy.orm import Session

# =============================================================================
# 1. Visitor Name & String Boundaries
# =============================================================================


def test_tier2_visitor_name_empty_rejection(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """Verifies that empty string for visitor_name is rejected."""
    payload = {
        "visitor_name": "",
        "phone_number": "+919876543210",
        "purpose": "GUEST",
        "destination_flat_id": str(FLAT_1203_ID),
        "privacy_notice_version": "v1.0",
    }
    response = client.post(
        "/api/v1/gate/visitors/register", json=payload, headers=GATE_GUARD_HEADERS
    )
    assert response.status_code in (400, 422)


def test_tier2_visitor_name_whitespace_only_rejection(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """Verifies that whitespace-only visitor name is rejected."""
    payload = {
        "visitor_name": "     ",
        "phone_number": "+919876543210",
        "purpose": "GUEST",
        "destination_flat_id": str(FLAT_1203_ID),
        "privacy_notice_version": "v1.0",
    }
    response = client.post(
        "/api/v1/gate/visitors/register", json=payload, headers=GATE_GUARD_HEADERS
    )
    assert response.status_code in (400, 422)


def test_tier2_visitor_name_minimum_length_boundary(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """Verifies that 1-character name is rejected (minimum 2 characters required)."""
    payload = {
        "visitor_name": "A",
        "phone_number": "+919876543210",
        "purpose": "GUEST",
        "destination_flat_id": str(FLAT_1203_ID),
        "privacy_notice_version": "v1.0",
    }
    response = client.post(
        "/api/v1/gate/visitors/register", json=payload, headers=GATE_GUARD_HEADERS
    )
    assert response.status_code in (400, 422)


def test_tier2_visitor_name_maximum_length_boundary(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """Verifies that visitor names exceeding 255 characters are rejected."""
    oversized_name = "A" * 256
    payload = {
        "visitor_name": oversized_name,
        "phone_number": "+919876543210",
        "purpose": "GUEST",
        "destination_flat_id": str(FLAT_1203_ID),
        "privacy_notice_version": "v1.0",
    }
    response = client.post(
        "/api/v1/gate/visitors/register", json=payload, headers=GATE_GUARD_HEADERS
    )
    assert response.status_code in (400, 422)


# =============================================================================
# 2. Phone Number E.164 Normalization Boundaries
# =============================================================================


def test_tier2_phone_number_missing_country_code(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """Verifies that phone numbers without +91 country prefix are rejected."""
    payload = {
        "visitor_name": "Valid Name",
        "phone_number": "9876543210",  # Missing +91
        "purpose": "GUEST",
        "destination_flat_id": str(FLAT_1203_ID),
        "privacy_notice_version": "v1.0",
    }
    response = client.post(
        "/api/v1/gate/visitors/register", json=payload, headers=GATE_GUARD_HEADERS
    )
    assert response.status_code in (400, 422)


def test_tier2_phone_number_with_alpha_characters(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """Verifies that phone numbers with letters are rejected."""
    payload = {
        "visitor_name": "Valid Name",
        "phone_number": "+9198ABC43210",
        "purpose": "GUEST",
        "destination_flat_id": str(FLAT_1203_ID),
        "privacy_notice_version": "v1.0",
    }
    response = client.post(
        "/api/v1/gate/visitors/register", json=payload, headers=GATE_GUARD_HEADERS
    )
    assert response.status_code in (400, 422)


def test_tier2_phone_number_invalid_length(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """Verifies that phone numbers with too few or too many digits are rejected."""
    # Too short
    payload_short = {
        "visitor_name": "Valid Name",
        "phone_number": "+9198765",
        "purpose": "GUEST",
        "destination_flat_id": str(FLAT_1203_ID),
        "privacy_notice_version": "v1.0",
    }
    res_short = client.post(
        "/api/v1/gate/visitors/register", json=payload_short, headers=GATE_GUARD_HEADERS
    )
    assert res_short.status_code in (400, 422)

    # Too long
    payload_long = {
        "visitor_name": "Valid Name",
        "phone_number": "+919876543210123456",
        "purpose": "GUEST",
        "destination_flat_id": str(FLAT_1203_ID),
        "privacy_notice_version": "v1.0",
    }
    res_long = client.post(
        "/api/v1/gate/visitors/register", json=payload_long, headers=GATE_GUARD_HEADERS
    )
    assert res_long.status_code in (400, 422)


# =============================================================================
# 3. Vehicle Number Boundaries
# =============================================================================


def test_tier2_vehicle_number_maximum_length_boundary(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """Verifies that vehicle registrations exceeding 20 characters are rejected."""
    payload = {
        "visitor_name": "Valid Name",
        "phone_number": "+919876543210",
        "vehicle_number": "MH12AB1234567890123456789",  # >20 chars
        "purpose": "GUEST",
        "destination_flat_id": str(FLAT_1203_ID),
        "privacy_notice_version": "v1.0",
    }
    response = client.post(
        "/api/v1/gate/visitors/register", json=payload, headers=GATE_GUARD_HEADERS
    )
    assert response.status_code in (400, 422)


# =============================================================================
# 4. Destination Flat Boundaries & Cross-Society Isolation
# =============================================================================


def test_tier2_destination_flat_non_existent_uuid(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """Verifies that non-existent destination flat UUID is rejected."""
    non_existent_flat = str(uuid.uuid4())
    payload = {
        "visitor_name": "Valid Name",
        "phone_number": "+919876543210",
        "purpose": "GUEST",
        "destination_flat_id": non_existent_flat,
        "privacy_notice_version": "v1.0",
    }
    response = client.post(
        "/api/v1/gate/visitors/register", json=payload, headers=GATE_GUARD_HEADERS
    )
    assert response.status_code in (400, 404, 422)


def test_tier2_destination_flat_cross_society_rejection(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """Verifies that destination flat belonging to another society is rejected."""
    payload = {
        "visitor_name": "Cross Society Guest",
        "phone_number": "+919876543210",
        "purpose": "GUEST",
        "destination_flat_id": str(FLAT_OTHER_ID),
        "privacy_notice_version": "v1.0",
    }
    response = client.post(
        "/api/v1/gate/visitors/register", json=payload, headers=GATE_GUARD_HEADERS
    )
    assert response.status_code in (400, 403)


# =============================================================================
# 5. Guest Pass Boundaries (Uses, Validity Window)
# =============================================================================


def test_tier2_guest_pass_invalid_dates_valid_until_before_valid_from(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """Verifies that pass creation with valid_until < valid_from is rejected."""
    now = datetime.now(UTC)
    payload = {
        "destination_flat_id": str(FLAT_1203_ID),
        "guest_name": "Time Traveler",
        "pass_type": "SINGLE_USE",
        "max_uses": 1,
        "valid_from": now.isoformat(),
        "valid_until": (now - timedelta(hours=1)).isoformat(),  # In the past
        "purpose": "Guest",
    }
    response = client.post("/api/v1/resident/passes", json=payload, headers=NEERAJ_HEADERS)
    assert response.status_code in (400, 422)


def test_tier2_guest_pass_single_use_max_uses_boundary(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """Verifies that single-use pass with max_uses != 1 is rejected or normalized."""
    now = datetime.now(UTC)
    payload = {
        "destination_flat_id": str(FLAT_1203_ID),
        "guest_name": "Invalid Single",
        "pass_type": "SINGLE_USE",
        "max_uses": 5,  # Invalid for SINGLE_USE
        "valid_from": now.isoformat(),
        "valid_until": (now + timedelta(days=1)).isoformat(),
        "purpose": "Guest",
    }
    response = client.post("/api/v1/resident/passes", json=payload, headers=NEERAJ_HEADERS)
    # Either rejected 400/422 or forced to 1
    if response.status_code == 201:
        assert response.json()["max_uses"] == 1
    else:
        assert response.status_code in (400, 422)


def test_tier2_guest_pass_multi_use_bounds_2_to_10(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """Verifies that multi-use pass max_uses must be between 2 and 10."""
    now = datetime.now(UTC)
    # max_uses = 1 (too few for multi-use)
    res_under = client.post(
        "/api/v1/resident/passes",
        json={
            "destination_flat_id": str(FLAT_1203_ID),
            "guest_name": "Under Bound",
            "pass_type": "MULTI_USE",
            "max_uses": 1,
            "valid_from": now.isoformat(),
            "valid_until": (now + timedelta(days=1)).isoformat(),
            "purpose": "Guest",
        },
        headers=NEERAJ_HEADERS,
    )
    assert res_under.status_code in (400, 422)

    # max_uses = 11 (exceeds 10 limit)
    res_over = client.post(
        "/api/v1/resident/passes",
        json={
            "destination_flat_id": str(FLAT_1203_ID),
            "guest_name": "Over Bound",
            "pass_type": "MULTI_USE",
            "max_uses": 11,
            "valid_from": now.isoformat(),
            "valid_until": (now + timedelta(days=1)).isoformat(),
            "purpose": "Guest",
        },
        headers=NEERAJ_HEADERS,
    )
    assert res_over.status_code in (400, 422)


# =============================================================================
# 6. 90-Day Retention Timestamp Boundaries
# =============================================================================


def test_tier2_photo_retention_boundary_day_89_vs_day_91(
    client: TestClient,
    gate_environment: dict,
    db_session: Session,
) -> None:
    """Verifies that photos at day 89 are accessible, but photos at day 91 return 410 PhotoExpired."""
    now = datetime.now(UTC)

    # 1. Day 89 visitor (still valid)
    day_89_id = str(uuid.uuid4())
    db_session.execute(
        text(
            """
            INSERT INTO visitors (
                id, society_id, gate_id, visitor_name, phone_number, purpose,
                destination_tower_id, destination_flat_id, created_by_user_id,
                photo_storage_key, approval_status, entry_status, created_at, updated_at
            ) VALUES (
                :id, :sid, :gid, 'Day 89 Guest', '+919876543201', 'GUEST',
                :tid, :fid, :uid, 'visitor-photos/valid.jpg', 'APPROVED', 'CHECKED_IN',
                :created_at, :created_at
            )
            """
        ),
        {
            "id": day_89_id,
            "sid": str(SOCIETY_PUNE_ID),
            "gid": str(GATE_1_ID),
            "tid": str(gate_environment["tower_t07_id"]),
            "fid": str(FLAT_1203_ID),
            "uid": str(gate_environment["user_helpdesk_id"]),
            "created_at": now - timedelta(days=89),
        },
    )

    # 2. Day 91 visitor (expired)
    day_91_id = str(uuid.uuid4())
    db_session.execute(
        text(
            """
            INSERT INTO visitors (
                id, society_id, gate_id, visitor_name, phone_number, purpose,
                destination_tower_id, destination_flat_id, created_by_user_id,
                photo_storage_key, approval_status, entry_status, created_at, updated_at
            ) VALUES (
                :id, :sid, :gid, 'Day 91 Guest', '+919876543202', 'GUEST',
                :tid, :fid, :uid, 'visitor-photos/expired.jpg', 'APPROVED', 'CHECKED_IN',
                :created_at, :created_at
            )
            """
        ),
        {
            "id": day_91_id,
            "sid": str(SOCIETY_PUNE_ID),
            "gid": str(GATE_1_ID),
            "tid": str(gate_environment["tower_t07_id"]),
            "fid": str(FLAT_1203_ID),
            "uid": str(gate_environment["user_helpdesk_id"]),
            "created_at": now - timedelta(days=91),
        },
    )
    db_session.commit()

    # Request Day 89 photo -> 200 OK
    res_89 = client.get(f"/api/v1/gate/visitors/{day_89_id}/photo", headers=GATE_GUARD_HEADERS)
    assert res_89.status_code in (200, 307)

    # Request Day 91 photo -> 410 Gone (PhotoExpired)
    res_91 = client.get(f"/api/v1/gate/visitors/{day_91_id}/photo", headers=GATE_GUARD_HEADERS)
    assert res_91.status_code == 410


# =============================================================================
# 7. Batch Synchronization Boundaries
# =============================================================================


def test_tier2_offline_batch_sync_empty_events(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """Verifies that batch sync with empty events list returns processed_count: 0."""
    payload = {
        "gate_id": str(GATE_1_ID),
        "events": [],
    }
    response = client.post("/api/v1/gate/sync", json=payload, headers=GATE_GUARD_HEADERS)
    assert response.status_code in (200, 400)
    if response.status_code == 200:
        assert response.json()["processed_count"] == 0


def test_tier2_offline_batch_sync_missing_client_event_id(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """Verifies that offline event missing client_event_id is rejected."""
    payload = {
        "gate_id": str(GATE_1_ID),
        "events": [
            {
                # Missing client_event_id
                "timestamp": datetime.now(UTC).isoformat(),
                "payload": {
                    "visitor_name": "No Event ID",
                    "phone_number": "+919876543210",
                    "purpose": "GUEST",
                    "destination_flat_id": str(FLAT_1203_ID),
                },
            }
        ],
    }
    response = client.post("/api/v1/gate/sync", json=payload, headers=GATE_GUARD_HEADERS)
    assert response.status_code in (400, 422)


# =============================================================================
# 8. Pagination Boundaries
# =============================================================================


def test_tier2_pagination_limit_boundaries(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """Verifies pagination limits: limit=0 or limit>50 clamped or rejected."""
    # limit = 0
    res_zero = client.get("/api/v1/gate/visitors?limit=0", headers=GATE_GUARD_HEADERS)
    assert res_zero.status_code in (200, 400, 422)

    # limit > 50 (should clamp to 50 or reject)
    res_excess = client.get("/api/v1/gate/visitors?limit=100", headers=GATE_GUARD_HEADERS)
    if res_excess.status_code == 200:
        data = res_excess.json()
        if isinstance(data, list):
            assert len(data) <= 50
    else:
        assert res_excess.status_code in (400, 422)
