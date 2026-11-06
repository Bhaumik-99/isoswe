"""Target-Scale Load & Aggregation Tests (28 Towers, 2,400 Apartments, 180 Staff).

Verifies that the platform handles the full township scale specified in the
product requirements (2,400 apartments across 28 towers and 180 facility staff)
including SQL-level committee aggregations, tower-filtered directory search,
complaint round-robin staff assignment, and /api/v1/me permission hydration.
"""

import time
import uuid

from fastapi.testclient import TestClient
from scripts.generate_sample_data import generate_extended_sample_data
from scripts.seed import (
    FLAT_1203_ID,
    SOCIETY_PUNE_ID,
    TOWER_T07_ID,
    USER_HELPDESK_ID,
    USER_NEERAJ_ID,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.domains.identity.models import (
    Flat,
    Permission,
    RoleType,
    Tower,
    UserRole,
)
from app.domains.identity.schemas import CurrentUserClaims
from app.main import app


def test_target_scale_population_and_committee_aggregation(
    client: TestClient,
    db_session: Session,
) -> None:
    """Populates 28 towers, 2,400 flats, and 180 staff and validates SQL aggregations."""
    # 1. Populate full target scale dataset
    counts = generate_extended_sample_data(
        num_towers=28,
        total_flats=2400,
        total_staff=180,
        db=db_session,
    )
    assert counts["towers"] == 28
    assert counts["flats"] == 2400
    assert counts["staff"] == 180

    # Verify idempotency when run a second time
    counts_repeat = generate_extended_sample_data(
        num_towers=28,
        total_flats=2400,
        total_staff=180,
        db=db_session,
    )
    assert counts_repeat == {"towers": 28, "flats": 2400, "staff": 180}

    # Verify DB counts directly
    tower_count = db_session.scalar(
        select(func.count(Tower.id)).where(Tower.society_id == SOCIETY_PUNE_ID)
    )
    flat_count = db_session.scalar(
        select(func.count(Flat.id)).where(Flat.society_id == SOCIETY_PUNE_ID)
    )
    staff_count = db_session.scalar(
        select(func.count(UserRole.id)).where(
            UserRole.society_id == SOCIETY_PUNE_ID,
            UserRole.role == RoleType.HELPDESK,
        )
    )
    assert tower_count == 28
    assert flat_count == 2400
    assert staff_count == 180

    # 2. Validate Committee Overview SQL aggregation at 2,400-flat scale
    committee_claims = CurrentUserClaims(
        user_id=USER_HELPDESK_ID,
        supabase_uid=uuid.UUID("00000000-0000-0000-0000-000000000004"),
        email="helpdesk@example.com",
        phone="+91-98000-00004",
        full_name="Rajesh Shinde",
        roles=[RoleType.HELPDESK],
        permissions=[
            Permission.COMPLAINT_MANAGE,
            Permission.BANK_IMPORT,
            Permission.RECONCILIATION_REVIEW,
            Permission.BILLING_MANAGE,
            Permission.COMMITTEE_REPORT_READ,
        ],
        society_ids=[SOCIETY_PUNE_ID],
        active_flat_ids=[],
        is_mock=True,
    )
    app.dependency_overrides[get_current_user] = lambda: committee_claims
    try:
        start_ts = time.perf_counter()
        resp = client.get("/api/v1/committee/overview")
        elapsed_ms = (time.perf_counter() - start_ts) * 1000.0
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["towers"]) == 28
        assert sum(t["total_flats"] for t in body["towers"]) == 2400
        assert elapsed_ms < 2000.0

        # 3. Validate Resident Directory tower_id filter at scale
        dir_resp = client.get(f"/api/v1/registry/residents?tower_id={TOWER_T07_ID}")
        assert dir_resp.status_code == 200
        dir_items = dir_resp.json()
        assert len(dir_items) >= 1
        assert all(any(f["tower_number"] == "T07" for f in item["flats"]) for item in dir_items)

        # 4. Validate /api/v1/me returns COMMITTEE_REPORT_READ in permissions for committee user
        me_resp = client.get("/api/v1/me")
        assert me_resp.status_code == 200
        me_data = me_resp.json()
        assert "COMMITTEE_REPORT_READ" in me_data["permissions"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    # 5. Validate that a generated staff account without COMMITTEE_REPORT_READ does NOT
    # receive COMMITTEE_REPORT_READ in /api/v1/me permissions
    staff_1_id = uuid.uuid5(SOCIETY_PUNE_ID, "staff-user-001")
    staff_1_claims = CurrentUserClaims(
        user_id=staff_1_id,
        supabase_uid=uuid.uuid5(SOCIETY_PUNE_ID, "staff-supa-001"),
        email="staff.001@example.com",
        phone="+91-98111-00001",
        full_name="Facility Staff 001",
        roles=[RoleType.HELPDESK],
        permissions=[
            Permission.COMPLAINT_MANAGE,
            Permission.BANK_IMPORT,
            Permission.RECONCILIATION_REVIEW,
            Permission.BILLING_MANAGE,
        ],
        society_ids=[SOCIETY_PUNE_ID],
        active_flat_ids=[],
        is_mock=True,
    )
    app.dependency_overrides[get_current_user] = lambda: staff_1_claims
    try:
        me_staff_resp = client.get("/api/v1/me")
        assert me_staff_resp.status_code == 200
        me_staff_data = me_staff_resp.json()
        assert "COMPLAINT_MANAGE" in me_staff_data["permissions"]
        assert "COMMITTEE_REPORT_READ" not in me_staff_data["permissions"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    # 6. Validate complaint auto-assignment works with 180 staff members
    resident_claims = CurrentUserClaims(
        user_id=USER_NEERAJ_ID,
        supabase_uid=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        email="neeraj.kulkarni@example.com",
        phone="+91-98000-00001",
        full_name="Neeraj Kulkarni",
        roles=[RoleType.RESIDENT],
        permissions=[],
        society_ids=[SOCIETY_PUNE_ID],
        active_flat_ids=[FLAT_1203_ID],
        is_mock=True,
    )
    app.dependency_overrides[get_current_user] = lambda: resident_claims
    try:
        comp_resp = client.post(
            "/api/v1/complaints",
            json={
                "flat_id": str(FLAT_1203_ID),
                "category": "PLUMBING",
                "title": "Scale test plumbing leak",
                "description": "Testing complaint auto-assignment across 180 staff members",
                "severity": "MEDIUM",
            },
            headers={"Idempotency-Key": f"scale-comp-{uuid.uuid4()}"},
        )
        assert comp_resp.status_code == 201
        comp_data = comp_resp.json()
        assert comp_data["assigned_to"] is not None
    finally:
        app.dependency_overrides.pop(get_current_user, None)
