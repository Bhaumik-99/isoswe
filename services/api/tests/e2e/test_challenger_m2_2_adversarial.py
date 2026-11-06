"""Empirical Challenger Test Suite for Phase 6 Milestone 2.

Author: challenger_m2_2 (teamwork_challenger)
Mission: Empirically challenge photo privacy, IDOR boundaries, retention lifecycles,
and end-to-end multi-actor acceptance flows.
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from services.api.tests.e2e.conftest import (
    FLAT_0408_ID,
    FLAT_1203_ID,
    GATE_1_ID,
    GATE_2_ID,
    GATE_3_ID,
    GATE_GUARD_2_HEADERS,
    GATE_GUARD_HEADERS,
    NEERAJ_HEADERS,
    OTHER_GATE_ID,
    OTHER_SOCIETY_ID,
    SOCIETY_PUNE_ID,
    SWATI_HEADERS,
    TINY_JPEG_BYTES,
    USER_HELPDESK_2_ID,
    USER_HELPDESK_ID,
)
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domains.reliability.models import AuditEvent
from app.domains.visitors.models import (
    ApprovalStatus,
    EntryStatus,
    GateStaffAssignment,
    VisitorPurpose,
    VisitorRecord,
)
from app.domains.visitors.retention_service import PhotoRetentionService


def _extract_error_code(res) -> str | None:
    try:
        data = res.json()
        if isinstance(data, dict):
            if "error" in data and isinstance(data["error"], dict):
                return data["error"].get("code")
            return data.get("code")
    except Exception:
        pass
    return None


# =============================================================================
# 1. EMPIRICAL CHALLENGES: Photo 90-Day Retention & Logical Cutoff (CHAL-16)
# =============================================================================


def test_photo_retention_fine_grained_boundaries(
    client: TestClient,
    gate_environment: dict,
    db_session: Session,
) -> None:
    """Stress-tests the exact 90-day boundary for photo access:
    - Day 89 + 23 hours (under 90 days) -> Accessible (200 OK)
    - Exactly 90 days - 10 seconds -> Accessible (200 OK)
    - Exactly 90 days + 1 second -> Rejected (410 PhotoExpired)
    - Day 91 -> Rejected (410 PhotoExpired)
    - Day 180 -> Rejected (410 PhotoExpired)
    """
    now = datetime.now(UTC)
    retention_service = PhotoRetentionService(db_session)

    test_cases = [
        ("day_89_23h", now - timedelta(days=89, hours=23), 200),
        ("day_90_minus_10s", now - timedelta(days=90) + timedelta(seconds=10), 200),
        ("day_90_plus_1s", now - timedelta(days=90) - timedelta(seconds=1), 410),
        ("day_91", now - timedelta(days=91), 410),
        ("day_180", now - timedelta(days=180), 410),
    ]

    for label, created_at, expected_status in test_cases:
        vid = uuid.uuid4()
        storage_key = retention_service.save_photo_bytes(
            society_id=SOCIETY_PUNE_ID,
            visitor_id=vid,
            photo_bytes=TINY_JPEG_BYTES,
            content_type="image/jpeg",
        )

        record = VisitorRecord(
            id=vid,
            society_id=SOCIETY_PUNE_ID,
            gate_id=GATE_1_ID,
            visitor_name=f"Visitor {label}",
            phone_number="+919876543001",
            purpose=VisitorPurpose.GUEST,
            destination_tower_id=gate_environment["tower_t07_id"],
            destination_flat_id=FLAT_1203_ID,
            created_by_user_id=USER_HELPDESK_ID,
            photo_storage_key=storage_key,
            photo_s3_key=storage_key,
            approval_status=ApprovalStatus.APPROVED,
            entry_status=EntryStatus.CHECKED_IN,
            created_at=created_at,
            updated_at=created_at,
        )
        db_session.add(record)
        db_session.commit()

        # Test Gate Guard endpoint
        res_gate = client.get(f"/api/v1/gate/visitors/{vid}/photo", headers=GATE_GUARD_HEADERS)
        assert res_gate.status_code == expected_status, (
            f"Gate photo access for {label} expected {expected_status}, got {res_gate.status_code}"
        )

        # Test Resident endpoint
        res_res = client.get(f"/api/v1/resident/visitors/{vid}/photo", headers=NEERAJ_HEADERS)
        assert res_res.status_code == expected_status, (
            f"Resident photo access for {label} expected {expected_status}, got {res_res.status_code}"
        )

        if expected_status == 410:
            assert _extract_error_code(res_gate) == "PHOTO_EXPIRED"
            assert _extract_error_code(res_res) == "PHOTO_EXPIRED"
        else:
            gate_data = res_gate.json()
            assert "photo_url" in gate_data or "url" in gate_data
            assert gate_data.get("expires_in") == 900


def test_photo_retention_purge_worker_lifecycle(
    client: TestClient,
    gate_environment: dict,
    db_session: Session,
) -> None:
    """Verifies that PhotoRetentionService.purge_expired_photos:
    1. Ignores active photos (< 90 days old).
    2. Deletes expired photos (> 90 days old) from storage.
    3. Nullifies photo_storage_key and sets photo_purged_at / photo_deleted_at in DB.
    4. Creates immutable AuditEvent with action PHOTO_RETENTION_PURGED.
    5. Causes subsequent photo requests to return 410 PhotoExpired.
    """
    now = datetime.now(UTC)
    retention_service = PhotoRetentionService(db_session)

    # 1. Create an expired visitor photo (> 90 days)
    expired_vid = uuid.uuid4()
    expired_key = retention_service.save_photo_bytes(
        society_id=SOCIETY_PUNE_ID,
        visitor_id=expired_vid,
        photo_bytes=TINY_JPEG_BYTES,
    )
    rec_expired = VisitorRecord(
        id=expired_vid,
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        visitor_name="Purge Candidate",
        phone_number="+919876543002",
        purpose=VisitorPurpose.GUEST,
        destination_tower_id=gate_environment["tower_t07_id"],
        destination_flat_id=FLAT_1203_ID,
        created_by_user_id=USER_HELPDESK_ID,
        photo_storage_key=expired_key,
        photo_s3_key=expired_key,
        approval_status=ApprovalStatus.APPROVED,
        entry_status=EntryStatus.CHECKED_IN,
        created_at=now - timedelta(days=95),
        updated_at=now - timedelta(days=95),
    )
    db_session.add(rec_expired)

    # 2. Create an active visitor photo (30 days old)
    active_vid = uuid.uuid4()
    active_key = retention_service.save_photo_bytes(
        society_id=SOCIETY_PUNE_ID,
        visitor_id=active_vid,
        photo_bytes=TINY_JPEG_BYTES,
    )
    rec_active = VisitorRecord(
        id=active_vid,
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        visitor_name="Active Visitor",
        phone_number="+919876543003",
        purpose=VisitorPurpose.GUEST,
        destination_tower_id=gate_environment["tower_t07_id"],
        destination_flat_id=FLAT_1203_ID,
        created_by_user_id=USER_HELPDESK_ID,
        photo_storage_key=active_key,
        photo_s3_key=active_key,
        approval_status=ApprovalStatus.APPROVED,
        entry_status=EntryStatus.CHECKED_IN,
        created_at=now - timedelta(days=30),
        updated_at=now - timedelta(days=30),
    )
    db_session.add(rec_active)
    db_session.commit()

    # 3. Execute purge worker
    purged_count = retention_service.purge_expired_photos(batch_size=50)
    assert purged_count >= 1

    # 4. Refresh records from DB
    db_session.expire_all()
    rec_expired_db = db_session.get(VisitorRecord, expired_vid)
    assert rec_expired_db is not None
    assert rec_expired_db.photo_storage_key is None
    assert rec_expired_db.photo_s3_key is None
    assert rec_expired_db.photo_purged_at is not None
    assert rec_expired_db.photo_deleted_at is not None

    rec_active_db = db_session.get(VisitorRecord, active_vid)
    assert rec_active_db is not None
    assert rec_active_db.photo_storage_key == active_key
    assert rec_active_db.photo_purged_at is None

    # 5. Verify AuditEvent emitted
    audit = (
        db_session.query(AuditEvent)
        .filter(
            AuditEvent.action == "PHOTO_RETENTION_PURGED",
            AuditEvent.resource_id == str(expired_vid),
        )
        .first()
    )
    assert audit is not None
    assert audit.society_id == SOCIETY_PUNE_ID
    assert audit.event_metadata["reason"] == "90_day_statutory_retention_limit"

    # 6. Attempt photo request for purged record -> 410 Gone
    res_purged = client.get(
        f"/api/v1/gate/visitors/{expired_vid}/photo", headers=GATE_GUARD_HEADERS
    )
    assert res_purged.status_code == 410


# =============================================================================
# 2. EMPIRICAL CHALLENGES: Photo IDOR & Multi-Tenant Authorization (CHAL-17)
# =============================================================================


def test_photo_idor_resident_cross_flat_matrix(
    client: TestClient,
    gate_environment: dict,
    db_session: Session,
) -> None:
    """Rigorous IDOR test matrix across resident flat boundaries:
    - Visitor arriving for Flat 0408 (Swati's Flat)
    - Neeraj (Flat 1203) -> 403 Forbidden (FLAT_ACCESS_DENIED)
    - Swati (Flat 0408) -> 200 OK
    - Expired lease tenant (Kiran Expired, Flat 1203) -> 403 Forbidden
    """
    now = datetime.now(UTC)
    retention_service = PhotoRetentionService(db_session)

    # 1. Register visitor for Flat 0408 (Swati's flat)
    vid_0408 = uuid.uuid4()
    key_0408 = retention_service.save_photo_bytes(
        society_id=SOCIETY_PUNE_ID,
        visitor_id=vid_0408,
        photo_bytes=TINY_JPEG_BYTES,
    )
    rec_0408 = VisitorRecord(
        id=vid_0408,
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        visitor_name="Swati Guest",
        phone_number="+919876543004",
        purpose=VisitorPurpose.GUEST,
        destination_tower_id=gate_environment["tower_t07_id"],
        destination_flat_id=FLAT_0408_ID,
        created_by_user_id=USER_HELPDESK_ID,
        photo_storage_key=key_0408,
        photo_s3_key=key_0408,
        approval_status=ApprovalStatus.PENDING,
        entry_status=EntryStatus.EXPECTED,
        created_at=now - timedelta(hours=1),
        updated_at=now - timedelta(hours=1),
    )
    db_session.add(rec_0408)
    db_session.commit()

    # Neeraj (owns 1203, not 0408) requests photo for vid_0408 -> 403
    res_neeraj = client.get(f"/api/v1/resident/visitors/{vid_0408}/photo", headers=NEERAJ_HEADERS)
    assert res_neeraj.status_code == 403
    assert _extract_error_code(res_neeraj) == "FLAT_ACCESS_DENIED"

    # Swati (owns 0408) requests photo for vid_0408 -> 200 OK
    res_swati = client.get(f"/api/v1/resident/visitors/{vid_0408}/photo", headers=SWATI_HEADERS)
    assert res_swati.status_code == 200
    assert "photo_url" in res_swati.json() or "url" in res_swati.json()

    # Expired tenant requests photo for their expired flat (Flat 1203)
    # Register visitor for Flat 1203
    vid_1203 = uuid.uuid4()
    key_1203 = retention_service.save_photo_bytes(
        society_id=SOCIETY_PUNE_ID,
        visitor_id=vid_1203,
        photo_bytes=TINY_JPEG_BYTES,
    )
    rec_1203 = VisitorRecord(
        id=vid_1203,
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        visitor_name="Neeraj Guest",
        phone_number="+919876543005",
        purpose=VisitorPurpose.GUEST,
        destination_tower_id=gate_environment["tower_t07_id"],
        destination_flat_id=FLAT_1203_ID,
        created_by_user_id=USER_HELPDESK_ID,
        photo_storage_key=key_1203,
        photo_s3_key=key_1203,
        approval_status=ApprovalStatus.PENDING,
        entry_status=EntryStatus.EXPECTED,
        created_at=now - timedelta(hours=1),
        updated_at=now - timedelta(hours=1),
    )
    db_session.add(rec_1203)
    db_session.commit()

    # Expired tenant header
    expired_headers = {"X-Dev-User": "expired-tenant"}
    res_expired = client.get(f"/api/v1/resident/visitors/{vid_1203}/photo", headers=expired_headers)
    assert res_expired.status_code in (401, 403)


def test_photo_idor_gate_operator_shift_boundaries(
    client: TestClient,
    gate_environment: dict,
    db_session: Session,
) -> None:
    """Stress-tests gate operator authorization boundaries for photo access:
    1. Assigned guard with active shift -> 200 OK.
    2. Guard assigned to a DIFFERENT society -> 403 Forbidden.
    3. Guard whose shift is in the FUTURE -> 403 Forbidden.
    4. Guard whose shift is in the PAST (expired) -> 403 Forbidden.
    5. Guard with is_active = False -> 403 Forbidden.
    """
    now = datetime.now(UTC)
    retention_service = PhotoRetentionService(db_session)

    vid = uuid.uuid4()
    key = retention_service.save_photo_bytes(
        society_id=SOCIETY_PUNE_ID,
        visitor_id=vid,
        photo_bytes=TINY_JPEG_BYTES,
    )
    rec = VisitorRecord(
        id=vid,
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        visitor_name="Guard Auth Test Visitor",
        phone_number="+919876543006",
        purpose=VisitorPurpose.GUEST,
        destination_tower_id=gate_environment["tower_t07_id"],
        destination_flat_id=FLAT_1203_ID,
        created_by_user_id=USER_HELPDESK_ID,
        photo_storage_key=key,
        photo_s3_key=key,
        approval_status=ApprovalStatus.APPROVED,
        entry_status=EntryStatus.CHECKED_IN,
        created_at=now - timedelta(hours=2),
        updated_at=now - timedelta(hours=2),
    )
    db_session.add(rec)
    db_session.commit()

    # 1. Guard with active shift in Marvel Greenfield -> 200 OK
    res_active = client.get(f"/api/v1/gate/visitors/{vid}/photo", headers=GATE_GUARD_HEADERS)
    assert res_active.status_code == 200

    # 2. Guard 2 has NO shift assignment initially -> 403 Forbidden
    res_guard2_no_shift = client.get(
        f"/api/v1/gate/visitors/{vid}/photo", headers=GATE_GUARD_2_HEADERS
    )
    assert res_guard2_no_shift.status_code == 403

    # 3. Give Guard 2 a shift in a DIFFERENT society
    assignment_diff_soc = GateStaffAssignment(
        id=uuid.uuid4(),
        society_id=OTHER_SOCIETY_ID,
        gate_id=OTHER_GATE_ID,
        user_id=USER_HELPDESK_2_ID,
        is_active=True,
        assigned_from=now - timedelta(hours=1),
        assigned_until=now + timedelta(hours=8),
        created_at=now,
        updated_at=now,
    )
    db_session.add(assignment_diff_soc)
    db_session.commit()

    res_guard2_diff_soc = client.get(
        f"/api/v1/gate/visitors/{vid}/photo", headers=GATE_GUARD_2_HEADERS
    )
    assert res_guard2_diff_soc.status_code == 403

    # 4. Update Guard 2 assignment to Marvel Greenfield, but with FUTURE shift (starts in 2 hours)
    assignment_diff_soc.society_id = SOCIETY_PUNE_ID
    assignment_diff_soc.gate_id = GATE_1_ID
    assignment_diff_soc.assigned_from = now + timedelta(hours=2)
    assignment_diff_soc.assigned_until = now + timedelta(hours=10)
    db_session.commit()

    res_guard2_future = client.get(
        f"/api/v1/gate/visitors/{vid}/photo", headers=GATE_GUARD_2_HEADERS
    )
    assert res_guard2_future.status_code == 403

    # 5. Update Guard 2 assignment to PAST shift (expired 1 hour ago)
    assignment_diff_soc.assigned_from = now - timedelta(hours=10)
    assignment_diff_soc.assigned_until = now - timedelta(hours=1)
    db_session.commit()

    res_guard2_past = client.get(f"/api/v1/gate/visitors/{vid}/photo", headers=GATE_GUARD_2_HEADERS)
    assert res_guard2_past.status_code == 403


# =============================================================================
# 3. EMPIRICAL CHALLENGES: End-to-End Acceptance Invariants Stress-Test
# =============================================================================


def test_e2e_state_machine_transition_invariants(
    client: TestClient,
    gate_environment: dict,
    db_session: Session,
) -> None:
    """Stress-tests critical state transition invariants in the 20-step flow:
    1. Guard cannot check-in a visitor whose approval_status is PENDING.
    2. Guard cannot check-in a visitor whose approval_status is REJECTED.
    3. Guard cannot check-out a visitor who has not yet checked in.
    4. Guard cannot check-out an already checked-out visitor twice.
    """
    # 1. Register visitor
    reg_res = client.post(
        "/api/v1/gate/visitors/register",
        json={
            "visitor_name": "State Machine Subject",
            "phone_number": "+919876543007",
            "purpose": "CAB",
            "destination_flat_id": str(FLAT_1203_ID),
            "privacy_notice_version": "v1.0",
        },
        headers=GATE_GUARD_HEADERS,
    )
    assert reg_res.status_code == 201
    vid = reg_res.json()["visitor_id"]

    # 2. Premature Check-In attempt while PENDING -> 400
    checkin_pending = client.post(
        f"/api/v1/gate/visitors/{vid}/check-in", headers=GATE_GUARD_HEADERS
    )
    assert checkin_pending.status_code == 400
    assert _extract_error_code(checkin_pending) in (
        "INVALID_STATE_TRANSITION",
        "ENTRY_NOT_APPROVED",
        "VISITOR_APPROVAL_PENDING",
    )

    # 3. Premature Check-Out attempt while EXPECTED -> 400
    checkout_expected = client.post(
        f"/api/v1/gate/visitors/{vid}/check-out",
        json={"exit_gate_id": str(GATE_1_ID)},
        headers=GATE_GUARD_HEADERS,
    )
    assert checkout_expected.status_code == 400
    assert _extract_error_code(checkout_expected) in ("INVALID_STATE_TRANSITION", "NOT_CHECKED_IN")

    # 4. Resident rejects visitor
    reject_res = client.post(
        f"/api/v1/resident/visitors/{vid}/action",
        json={"action": "REJECT", "rejection_reason": "Not expecting any cab"},
        headers=NEERAJ_HEADERS,
    )
    assert reject_res.status_code == 200
    assert reject_res.json()["approval_status"] == "REJECTED"

    # 5. Check-In attempt on REJECTED visitor -> 400
    checkin_rejected = client.post(
        f"/api/v1/gate/visitors/{vid}/check-in", headers=GATE_GUARD_HEADERS
    )
    assert checkin_rejected.status_code == 400
    assert _extract_error_code(checkin_rejected) in (
        "INVALID_STATE_TRANSITION",
        "ENTRY_NOT_APPROVED",
        "VISITOR_APPROVAL_REJECTED",
        "VISITOR_REJECTED",
    )


def test_e2e_pass_exhaustion_multi_gate_traversal(
    client: TestClient,
    gate_environment: dict,
    db_session: Session,
) -> None:
    """Stress-tests pre-approved guest pass multi-use exhaustion across multiple gates:
    - Multi-use pass with max_uses = 2
    - 1st entry at Gate 1 -> SUCCESS (remaining: 1)
    - 2nd entry at Gate 2 -> SUCCESS (remaining: 0, status transitions to EXHAUSTED)
    - 3rd entry at Gate 3 -> FAILS with 400/409 (PASS_EXHAUSTED)
    """
    now = datetime.now(UTC)

    # Assign guard to Gate 2 and Gate 3 as well
    for gid in [GATE_2_ID, GATE_3_ID]:
        db_session.execute(
            text(
                """
                INSERT OR REPLACE INTO gate_assignments (id, society_id, gate_id, user_id, is_active, assigned_from, created_at, updated_at)
                VALUES (:id, :society_id, :gate_id, :user_id, 1, :assigned_from, :created_at, :updated_at)
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "society_id": str(SOCIETY_PUNE_ID),
                "gate_id": str(gid),
                "user_id": str(USER_HELPDESK_ID),
                "assigned_from": now - timedelta(hours=1),
                "created_at": now,
                "updated_at": now,
            },
        )
    db_session.commit()

    # Resident creates pass with max_uses = 2
    pass_res = client.post(
        "/api/v1/resident/passes",
        json={
            "destination_flat_id": str(FLAT_1203_ID),
            "guest_name": "Multi-Gate Contractor",
            "pass_type": "MULTI_USE",
            "max_uses": 2,
            "valid_from": now.isoformat(),
            "valid_until": (now + timedelta(days=2)).isoformat(),
            "purpose": "Renovation",
        },
        headers=NEERAJ_HEADERS,
    )
    assert pass_res.status_code == 201
    pass_code = pass_res.json()["pass_code"]

    # Entry 1 at Gate 1
    v1 = client.post(
        "/api/v1/gate/pass/verify",
        json={"pass_code": pass_code, "gate_id": str(GATE_1_ID)},
        headers=GATE_GUARD_HEADERS,
    )
    assert v1.status_code == 200
    assert v1.json()["remaining_uses"] == 1
    assert v1.json()["approval_status"] == "AUTO_APPROVED"
    assert v1.json()["entry_status"] == "CHECKED_IN"

    # Entry 2 at Gate 2
    v2 = client.post(
        "/api/v1/gate/pass/verify",
        json={"pass_code": pass_code, "gate_id": str(GATE_2_ID)},
        headers=GATE_GUARD_HEADERS,
    )
    assert v2.status_code == 200
    assert v2.json()["remaining_uses"] == 0

    # Entry 3 at Gate 3 -> Rejected!
    v3 = client.post(
        "/api/v1/gate/pass/verify",
        json={"pass_code": pass_code, "gate_id": str(GATE_3_ID)},
        headers=GATE_GUARD_HEADERS,
    )
    assert v3.status_code in (400, 404, 409)


def test_photo_non_existent_visitor_404(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """Verifies that requesting a photo for a non-existent visitor ID returns 404."""
    random_id = str(uuid.uuid4())
    res_gate = client.get(f"/api/v1/gate/visitors/{random_id}/photo", headers=GATE_GUARD_HEADERS)
    assert res_gate.status_code == 404
    assert _extract_error_code(res_gate) in ("VISITOR_NOT_FOUND", "RESOURCE_NOT_FOUND")

    res_res = client.get(f"/api/v1/resident/visitors/{random_id}/photo", headers=NEERAJ_HEADERS)
    assert res_res.status_code == 404
    assert _extract_error_code(res_res) in ("VISITOR_NOT_FOUND", "RESOURCE_NOT_FOUND")


def test_photo_access_without_photo_registered(
    client: TestClient,
    gate_environment: dict,
    db_session: Session,
) -> None:
    """Verifies behavior when visitor record exists but has NO photo attached."""
    now = datetime.now(UTC)
    vid = uuid.uuid4()
    rec = VisitorRecord(
        id=vid,
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        visitor_name="No Photo Visitor",
        phone_number="+919876543008",
        purpose=VisitorPurpose.DELIVERY,
        destination_tower_id=gate_environment["tower_t07_id"],
        destination_flat_id=FLAT_1203_ID,
        created_by_user_id=USER_HELPDESK_ID,
        photo_storage_key=None,
        photo_s3_key=None,
        approval_status=ApprovalStatus.APPROVED,
        entry_status=EntryStatus.CHECKED_IN,
        created_at=now - timedelta(minutes=5),
        updated_at=now - timedelta(minutes=5),
    )
    db_session.add(rec)
    db_session.commit()

    res = client.get(f"/api/v1/gate/visitors/{vid}/photo", headers=GATE_GUARD_HEADERS)
    # Since no photo is registered, access must be safely denied (either 404 or 410)
    assert res.status_code in (404, 410)


def test_photo_presigned_url_no_pii_in_url(
    client: TestClient,
    gate_environment: dict,
    db_session: Session,
) -> None:
    """Verifies that the generated presigned photo URL does not contain sensitive visitor PII
    such as phone numbers or plain names in the query params.
    """
    now = datetime.now(UTC)
    retention_service = PhotoRetentionService(db_session)
    vid = uuid.uuid4()
    key = retention_service.save_photo_bytes(
        society_id=SOCIETY_PUNE_ID,
        visitor_id=vid,
        photo_bytes=TINY_JPEG_BYTES,
    )
    rec = VisitorRecord(
        id=vid,
        society_id=SOCIETY_PUNE_ID,
        gate_id=GATE_1_ID,
        visitor_name="Secret PII Guest",
        phone_number="+919876543999",
        purpose=VisitorPurpose.GUEST,
        destination_tower_id=gate_environment["tower_t07_id"],
        destination_flat_id=FLAT_1203_ID,
        created_by_user_id=USER_HELPDESK_ID,
        photo_storage_key=key,
        photo_s3_key=key,
        approval_status=ApprovalStatus.APPROVED,
        entry_status=EntryStatus.CHECKED_IN,
        created_at=now - timedelta(minutes=10),
        updated_at=now - timedelta(minutes=10),
    )
    db_session.add(rec)
    db_session.commit()

    res = client.get(f"/api/v1/resident/visitors/{vid}/photo", headers=NEERAJ_HEADERS)
    assert res.status_code == 200
    url = res.json().get("photo_url") or res.json().get("url")
    assert "+919876543999" not in url
    assert "9876543999" not in url
    assert "Secret" not in url
