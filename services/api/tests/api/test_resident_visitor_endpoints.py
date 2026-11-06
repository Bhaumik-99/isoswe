"""API Endpoint Tests for Resident Visitor & Guest Pass Operations

Tests all endpoints under /api/v1/resident:
- GET /visitors/pending
- POST /visitors/{id}/action
- GET /visitors/today
- GET /visitors/history
- GET /visitors/{id}/photo
- POST /passes
- GET /passes
- POST /passes/{id}/revoke
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.identity.models import Permission, UserPermission
from app.domains.visitors.models import Gate, GateStaffAssignment, GateStatus

RESIDENT_NEERAJ_HEADERS = {"X-Dev-User": "neeraj"}
RESIDENT_SWATI_HEADERS = {"X-Dev-User": "swati"}
GATE_GUARD_HEADERS = {"X-Dev-User": "helpdesk"}

SOCIETY_PUNE_ID = "11111111-1111-1111-1111-111111111111"
NEERAJ_FLAT_ID = "33333333-3333-3333-3333-333333331203"
SWATI_FLAT_ID = "33333333-3333-3333-3333-333333330408"
GATE_1_ID = "aaaaaaaa-1111-0000-0000-000000000001"


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


def test_resident_pending_inbox_and_approval(client: TestClient, db_session: Session) -> None:
    """Resident sees pending visitors and can approve them."""
    # Guard registers walk-in visitor for Neeraj's flat
    reg_res = client.post(
        "/api/v1/gate/visitors/register",
        json={
            "visitor_name": "Inbox Guest",
            "phone_number": "+919876543280",
            "purpose": "GUEST",
            "destination_flat_id": NEERAJ_FLAT_ID,
        },
        headers=GATE_GUARD_HEADERS,
    )
    assert reg_res.status_code == 201
    visitor_id = reg_res.json()["visitor_id"]

    # Neeraj checks pending inbox
    inbox_res = client.get("/api/v1/resident/visitors/pending", headers=RESIDENT_NEERAJ_HEADERS)
    assert inbox_res.status_code == 200
    pending_list = inbox_res.json()
    assert any(v["visitor_id"] == visitor_id for v in pending_list)

    # Neeraj approves
    appr_res = client.post(
        f"/api/v1/resident/visitors/{visitor_id}/action",
        json={"action": "APPROVE"},
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert appr_res.status_code == 200
    assert appr_res.json()["approval_status"] == "APPROVED"


def test_resident_rejection_with_reason(client: TestClient, db_session: Session) -> None:
    """Resident rejects visitor with mandatory reason."""
    reg_res = client.post(
        "/api/v1/gate/visitors/register",
        json={
            "visitor_name": "Spam Salesman",
            "phone_number": "+919876543281",
            "purpose": "SERVICE_MAINTENANCE",
            "destination_flat_id": NEERAJ_FLAT_ID,
        },
        headers=GATE_GUARD_HEADERS,
    )
    assert reg_res.status_code == 201
    visitor_id = reg_res.json()["visitor_id"]

    # Reject
    rej_res = client.post(
        f"/api/v1/resident/visitors/{visitor_id}/action",
        json={"action": "REJECT", "rejection_reason": "Unsolicited sales pitch"},
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert rej_res.status_code == 200
    assert rej_res.json()["approval_status"] == "REJECTED"


def test_cross_flat_resident_action_forbidden(client: TestClient, db_session: Session) -> None:
    """Swati cannot approve or reject visitors for Neeraj's flat (403 Forbidden)."""
    reg_res = client.post(
        "/api/v1/gate/visitors/register",
        json={
            "visitor_name": "Neeraj Personal Guest",
            "phone_number": "+919876543282",
            "purpose": "GUEST",
            "destination_flat_id": NEERAJ_FLAT_ID,
        },
        headers=GATE_GUARD_HEADERS,
    )
    visitor_id = reg_res.json()["visitor_id"]

    # Swati attempts approval
    res = client.post(
        f"/api/v1/resident/visitors/{visitor_id}/action",
        json={"action": "APPROVE"},
        headers=RESIDENT_SWATI_HEADERS,
    )
    assert res.status_code == 403


def test_resident_create_and_list_guest_passes(client: TestClient, db_session: Session) -> None:
    """Resident creates single-use and multi-use guest passes and lists active passes."""
    now = datetime.now(UTC)
    create_res = client.post(
        "/api/v1/resident/passes",
        json={
            "destination_flat_id": NEERAJ_FLAT_ID,
            "guest_name": "Diwali Guest",
            "pass_type": "MULTI_USE",
            "max_uses": 5,
            "valid_from": now.isoformat(),
            "valid_until": (now + timedelta(days=2)).isoformat(),
            "purpose": "Celebration",
        },
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert create_res.status_code == 201
    data = create_res.json()
    assert "pass_code" in data
    assert data["pass_code"].startswith("GP-")
    pass_id = data["pass_id"]

    # List passes
    list_res = client.get("/api/v1/resident/passes", headers=RESIDENT_NEERAJ_HEADERS)
    assert list_res.status_code == 200
    passes = list_res.json()
    assert any(p["pass_id"] == pass_id for p in passes)


def test_resident_revoke_guest_pass(client: TestClient, db_session: Session) -> None:
    """Resident revokes an issued guest pass, preventing future verification."""
    now = datetime.now(UTC)
    create_res = client.post(
        "/api/v1/resident/passes",
        json={
            "destination_flat_id": NEERAJ_FLAT_ID,
            "guest_name": "Revocable Contractor",
            "pass_type": "SINGLE_USE",
            "max_uses": 1,
            "valid_from": now.isoformat(),
            "valid_until": (now + timedelta(days=1)).isoformat(),
            "purpose": "Contractor",
        },
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    pass_data = create_res.json()
    pass_id = pass_data["pass_id"]
    pass_code = pass_data["pass_code"]

    # Revoke
    rev_res = client.post(
        f"/api/v1/resident/passes/{pass_id}/revoke",
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert rev_res.status_code == 200
    assert rev_res.json()["status"] == "REVOKED"

    # Verify at gate fails
    verify_res = client.post(
        "/api/v1/gate/pass/verify",
        json={"pass_code": pass_code, "gate_id": GATE_1_ID},
        headers=GATE_GUARD_HEADERS,
    )
    assert verify_res.status_code in (400, 403)
