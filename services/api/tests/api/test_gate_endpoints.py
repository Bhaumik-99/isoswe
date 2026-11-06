"""API Endpoint Tests for Perimeter Gate Operations

Tests all endpoints under /api/v1/gate:
- GET /session
- GET /overview
- POST /visitors/register
- POST /visitors/{id}/check-in
- POST /visitors/{id}/check-out
- GET /visitors
- GET /visitors/active
- GET /visitors/history
- GET /visitors/{id}
- GET /visitors/{id}/photo
- POST /pass/verify
- POST /sync
- GET /privacy-notice
"""

import base64
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.identity.models import Permission, UserPermission
from app.domains.visitors.models import Gate, GateStaffAssignment, GateStatus

# Standard Dev Auth Headers
GATE_GUARD_HEADERS = {"X-Dev-User": "helpdesk"}
RESIDENT_NEERAJ_HEADERS = {"X-Dev-User": "neeraj"}

SOCIETY_PUNE_ID = "11111111-1111-1111-1111-111111111111"
GATE_1_ID = "aaaaaaaa-1111-0000-0000-000000000001"
FLAT_1203_ID = "33333333-3333-3333-3333-333333331203"

TINY_JPEG_BYTES = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00"
    b"\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19"
    b"\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9"
    b"=\x382<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f"
    b"\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02"
    b"\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
)


@pytest.fixture(autouse=True)
def setup_gate_test_data(db_session: Session) -> None:
    """Configures gate, guard assignment, and GATE_OPERATIONS permission for helpdesk user."""
    now = datetime.now(UTC)
    user_helpdesk_id = uuid.UUID("44444444-4444-4444-4444-444444440004")
    society_id = uuid.UUID(SOCIETY_PUNE_ID)
    gate_id = uuid.UUID(GATE_1_ID)

    # Seed Gate
    gate = db_session.get(Gate, gate_id)
    if not gate:
        gate = Gate(
            id=gate_id,
            society_id=society_id,
            gate_number="1",
            gate_name="Gate 1 - North Main",
            name="Gate 1 - North Main",
            status=GateStatus.ACTIVE,
        )
        db_session.add(gate)

    # Grant GATE_OPERATIONS permission
    perm = db_session.execute(
        select(UserPermission).where(
            UserPermission.user_id == user_helpdesk_id,
            UserPermission.permission == Permission.GATE_OPERATIONS,
        )
    ).scalar_one_or_none()
    if not perm:
        db_session.add(
            UserPermission(
                id=uuid.uuid4(),
                user_id=user_helpdesk_id,
                society_id=society_id,
                permission=Permission.GATE_OPERATIONS,
            )
        )

    # Seed GateStaffAssignment
    existing_assignment = db_session.execute(
        select(GateStaffAssignment).where(
            GateStaffAssignment.gate_id == gate_id,
            GateStaffAssignment.user_id == user_helpdesk_id,
        )
    ).scalar_one_or_none()

    if not existing_assignment:
        assignment = GateStaffAssignment(
            id=uuid.uuid4(),
            society_id=society_id,
            gate_id=gate_id,
            user_id=user_helpdesk_id,
            is_active=True,
            assigned_from=now - timedelta(days=1),
            assigned_until=now + timedelta(days=30),
        )
        db_session.add(assignment)

    db_session.commit()


def test_gate_session_success(client: TestClient, db_session: Session) -> None:
    """Verifies that an authenticated guard tablet retrieves active gate session."""
    res = client.get("/api/v1/gate/session", headers=GATE_GUARD_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["society_id"] == SOCIETY_PUNE_ID
    assert data["assigned_gate"]["gate_id"] == GATE_1_ID
    assert len(data["available_gates"]) >= 1


def test_gate_session_forbidden_for_residents(client: TestClient, db_session: Session) -> None:
    """Residents cannot access gate tablet session endpoints."""
    res = client.get("/api/v1/gate/session", headers=RESIDENT_NEERAJ_HEADERS)
    assert res.status_code == 403


def test_gate_overview_metrics(client: TestClient, db_session: Session) -> None:
    """Gate tablet overview returns high-contrast status and counters."""
    res = client.get("/api/v1/gate/overview", headers=GATE_GUARD_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert "active_checked_in_count" in data
    assert "pending_approvals_count" in data
    assert data["offline_queue_supported"] is True


def test_register_walkin_visitor_json(client: TestClient, db_session: Session) -> None:
    """Registers walk-in visitor with JSON and base64 photo."""
    b64_photo = base64.b64encode(TINY_JPEG_BYTES).decode()
    payload = {
        "visitor_name": "Ramesh Kulkarni",
        "phone_number": "+919876543290",
        "purpose": "GUEST",
        "destination_flat_id": FLAT_1203_ID,
        "photo_base64": b64_photo,
        "privacy_notice_version": "v1.0-2026-pune",
    }
    res = client.post("/api/v1/gate/visitors/register", json=payload, headers=GATE_GUARD_HEADERS)
    assert res.status_code == 201
    data = res.json()
    assert data["visitor_name"] == "Ramesh Kulkarni"
    assert data["approval_status"] == "PENDING"
    assert data["entry_status"] == "EXPECTED"
    assert "visitor_id" in data


def test_register_walkin_visitor_multipart(client: TestClient, db_session: Session) -> None:
    """Registers walk-in visitor with multipart/form-data upload."""
    form_data = {
        "visitor_name": "Suresh Delivery",
        "phone_number": "+919876543291",
        "purpose": "DELIVERY",
        "destination_flat_id": FLAT_1203_ID,
        "privacy_notice_version": "v1.0-2026-pune",
    }
    files = {"photo": ("face.jpg", TINY_JPEG_BYTES, "image/jpeg")}
    res = client.post(
        "/api/v1/gate/visitors/register",
        data=form_data,
        files=files,
        headers=GATE_GUARD_HEADERS,
    )
    assert res.status_code == 201
    assert res.json()["purpose"] == "DELIVERY"


def test_visitor_checkin_and_checkout_lifecycle(client: TestClient, db_session: Session) -> None:
    """Full lifecycle from walk-in -> resident approve -> check-in -> check-out."""
    # 1. Register
    reg_res = client.post(
        "/api/v1/gate/visitors/register",
        json={
            "visitor_name": "Lifecycle Guest",
            "phone_number": "+919876543292",
            "purpose": "GUEST",
            "destination_flat_id": FLAT_1203_ID,
        },
        headers=GATE_GUARD_HEADERS,
    )
    assert reg_res.status_code == 201
    visitor_id = reg_res.json()["visitor_id"]

    # 2. Resident approves
    appr_res = client.post(
        f"/api/v1/resident/visitors/{visitor_id}/action",
        json={"action": "APPROVE"},
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert appr_res.status_code == 200

    # 3. Guard checks in
    in_res = client.post(f"/api/v1/gate/visitors/{visitor_id}/check-in", headers=GATE_GUARD_HEADERS)
    assert in_res.status_code == 200
    assert in_res.json()["entry_status"] == "CHECKED_IN"

    # 4. Guard checks out
    out_res = client.post(
        f"/api/v1/gate/visitors/{visitor_id}/check-out",
        json={"exit_gate_id": GATE_1_ID},
        headers=GATE_GUARD_HEADERS,
    )
    assert out_res.status_code == 200
    assert out_res.json()["entry_status"] == "CHECKED_OUT"


def test_gate_active_visitors_feed(client: TestClient, db_session: Session) -> None:
    """Queries currently checked-in campus visitors."""
    res = client.get("/api/v1/gate/visitors/active", headers=GATE_GUARD_HEADERS)
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_gate_visitor_history_pagination(client: TestClient, db_session: Session) -> None:
    """Queries paginated visitor log history."""
    res = client.get("/api/v1/gate/visitors/history?limit=10&offset=0", headers=GATE_GUARD_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)


def test_privacy_notice_tri_lingual(client: TestClient) -> None:
    """Verifies statutory tri-lingual privacy notice in en, hi, mr."""
    for lang in ("en", "hi", "mr"):
        res = client.get(f"/api/v1/gate/privacy-notice?lang={lang}", headers=GATE_GUARD_HEADERS)
        assert res.status_code == 200
        data = res.json()
        assert data["language"] == lang
        assert data["retention_days"] == 90
        assert len(data["content"]) > 20
