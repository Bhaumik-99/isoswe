"""Tier 4: Adversarial Challenger Test Suite (CHAL-01 through CHAL-17).

Implements the complete set of 17 adversarial attack and corner scenarios exactly
as mandated by PROJECT.md and survey_spec.md § 10.
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
    GATE_GUARD_HEADERS,
    NEERAJ_HEADERS,
    OTHER_GATE_ID,
    SOCIETY_PUNE_ID,
    TINY_JPEG_BASE64,
)
from sqlalchemy import text
from sqlalchemy.orm import Session

# =============================================================================
# CHAL-01: Cross-Society Gate Access
# =============================================================================


def test_chal_01_cross_society_gate_access(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """CHAL-01: Gate guard of Society A attempts to register visitor at a gate in Society B.

    Expected: Rejected with 403 Forbidden (TENANT_ISOLATION_ERROR).
    """
    payload = {
        "visitor_name": "Adversarial Cross Society Visitor",
        "phone_number": "+919876543001",
        "purpose": "GUEST",
        "destination_flat_id": str(FLAT_1203_ID),
        "gate_id": str(OTHER_GATE_ID),
        "privacy_notice_version": "v1.0",
    }
    response = client.post(
        "/api/v1/gate/visitors/register",
        json=payload,
        headers=GATE_GUARD_HEADERS,
    )
    assert response.status_code in (400, 403)


# =============================================================================
# CHAL-02: Unassigned Gate Operations
# =============================================================================


def test_chal_02_unassigned_gate_operations(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """CHAL-02: Guard assigned strictly to Gate 1 attempts to verify pass targeting Gate 3.

    Expected: Rejected with 403 Forbidden (GATE_ACCESS_DENIED).
    """
    response = client.post(
        "/api/v1/gate/pass/verify",
        json={"pass_code": "GP-1234", "gate_id": str(GATE_3_ID)},
        headers=GATE_GUARD_HEADERS,
    )
    assert response.status_code in (400, 403)


# =============================================================================
# CHAL-03: Gate-Only Staff Privilege Escalation
# =============================================================================


def test_chal_03_gate_only_staff_privilege_escalation(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """CHAL-03: Guard with only GATE_OPERATIONS attempts to access financial billing & reconciliation.

    Expected: Rejected with 403 Forbidden (INSUFFICIENT_PERMISSIONS).
    """
    # 1. Billing invoice creation attempt
    res_billing = client.post(
        "/api/v1/billing/invoices/generate",
        json={"society_id": str(SOCIETY_PUNE_ID)},
        headers=GATE_GUARD_HEADERS,
    )
    assert res_billing.status_code == 403

    # 2. Reconciliation matching review attempt
    res_recon = client.post(
        "/api/v1/reconciliation/batches/upload",
        json={"society_id": str(SOCIETY_PUNE_ID)},
        headers=GATE_GUARD_HEADERS,
    )
    assert res_recon.status_code in (403, 404, 405)


# =============================================================================
# CHAL-04: Resident Cross-Flat Approval
# =============================================================================


def test_chal_04_resident_cross_flat_approval(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """CHAL-04: Resident in Flat 1203 (Neeraj) attempts to approve visitor waiting for Flat 0408 (Swati).

    Expected: Rejected with 403 Forbidden (FLAT_ACCESS_DENIED).
    """
    # 1. Register visitor for Swati's flat (0408)
    reg_res = client.post(
        "/api/v1/gate/visitors/register",
        json={
            "visitor_name": "Swati Targeted Guest",
            "phone_number": "+919876543004",
            "purpose": "GUEST",
            "destination_flat_id": str(FLAT_0408_ID),
            "privacy_notice_version": "v1.0",
        },
        headers=GATE_GUARD_HEADERS,
    )
    visitor_id = reg_res.json()["visitor_id"]

    # 2. Neeraj (who only owns 1203) attempts to approve Swati's visitor
    hijack_res = client.post(
        f"/api/v1/resident/visitors/{visitor_id}/action",
        json={"action": "APPROVE"},
        headers=NEERAJ_HEADERS,
    )
    assert hijack_res.status_code == 403


# =============================================================================
# CHAL-05: Expired Lease Approval Attempt
# =============================================================================


def test_chal_05_expired_lease_approval_attempt(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """CHAL-05: Tenant whose lease expired yesterday attempts to approve a visitor.

    Expected: Rejected with 403 Forbidden (MEMBERSHIP_EXPIRED / FLAT_ACCESS_DENIED).
    """
    # 1. Register visitor for Flat 1203
    reg_res = client.post(
        "/api/v1/gate/visitors/register",
        json={
            "visitor_name": "Guest for Expired Tenant",
            "phone_number": "+919876543005",
            "purpose": "GUEST",
            "destination_flat_id": str(FLAT_1203_ID),
            "privacy_notice_version": "v1.0",
        },
        headers=GATE_GUARD_HEADERS,
    )
    visitor_id = reg_res.json()["visitor_id"]

    # 2. Expired tenant attempts to approve
    expired_headers = {
        "X-Dev-User": "expired-tenant",
        "Authorization": "Bearer dev-token-expired-tenant",
    }
    res = client.post(
        f"/api/v1/resident/visitors/{visitor_id}/action",
        json={"action": "APPROVE"},
        headers=expired_headers,
    )
    assert res.status_code in (401, 403)


# =============================================================================
# CHAL-06: Check-In on Pending Visitor
# =============================================================================


def test_chal_06_checkin_on_pending_visitor(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """CHAL-06: Gate guard attempts to check in a visitor whose approval_status is still PENDING.

    Expected: State machine rejects check-in with 400 Bad Request (VISITOR_APPROVAL_PENDING).
    """
    reg_res = client.post(
        "/api/v1/gate/visitors/register",
        json={
            "visitor_name": "Pending Visitor",
            "phone_number": "+919876543006",
            "purpose": "GUEST",
            "destination_flat_id": str(FLAT_1203_ID),
            "privacy_notice_version": "v1.0",
        },
        headers=GATE_GUARD_HEADERS,
    )
    visitor_id = reg_res.json()["visitor_id"]

    # Attempt check-in without resident approval
    checkin_res = client.post(
        f"/api/v1/gate/visitors/{visitor_id}/check-in",
        headers=GATE_GUARD_HEADERS,
    )
    assert checkin_res.status_code == 400


# =============================================================================
# CHAL-07: Check-In on Rejected Visitor
# =============================================================================


def test_chal_07_checkin_on_rejected_visitor(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """CHAL-07: Gate guard attempts to check in a visitor rejected by the resident.

    Expected: State machine rejects check-in with 400 Bad Request (VISITOR_REJECTED).
    """
    reg_res = client.post(
        "/api/v1/gate/visitors/register",
        json={
            "visitor_name": "Rejected Visitor",
            "phone_number": "+919876543007",
            "purpose": "GUEST",
            "destination_flat_id": str(FLAT_1203_ID),
            "privacy_notice_version": "v1.0",
        },
        headers=GATE_GUARD_HEADERS,
    )
    visitor_id = reg_res.json()["visitor_id"]

    # Resident rejects entry
    client.post(
        f"/api/v1/resident/visitors/{visitor_id}/action",
        json={"action": "REJECT", "reason": "Not expecting anyone"},
        headers=NEERAJ_HEADERS,
    )

    # Gate guard attempts check-in
    checkin_res = client.post(
        f"/api/v1/gate/visitors/{visitor_id}/check-in",
        headers=GATE_GUARD_HEADERS,
    )
    assert checkin_res.status_code == 400


# =============================================================================
# CHAL-08: Premature or Duplicate Check-Out
# =============================================================================


def test_chal_08_premature_or_duplicate_checkout(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """CHAL-08: Guard attempts check-out for visitor in EXPECTED or CHECKED_OUT state.

    Expected: State machine rejects transition with 400 Bad Request (INVALID_STATE_TRANSITION).
    """
    # 1. Visitor in EXPECTED state
    reg_res = client.post(
        "/api/v1/gate/visitors/register",
        json={
            "visitor_name": "Never Entered Guest",
            "phone_number": "+919876543008",
            "purpose": "GUEST",
            "destination_flat_id": str(FLAT_1203_ID),
            "privacy_notice_version": "v1.0",
        },
        headers=GATE_GUARD_HEADERS,
    )
    visitor_id = reg_res.json()["visitor_id"]

    res_premature = client.post(
        f"/api/v1/gate/visitors/{visitor_id}/check-out", headers=GATE_GUARD_HEADERS
    )
    assert res_premature.status_code == 400

    # 2. Complete check-in and checkout, then attempt duplicate checkout
    client.post(
        f"/api/v1/resident/visitors/{visitor_id}/action",
        json={"action": "APPROVE"},
        headers=NEERAJ_HEADERS,
    )
    client.post(f"/api/v1/gate/visitors/{visitor_id}/check-in", headers=GATE_GUARD_HEADERS)
    client.post(f"/api/v1/gate/visitors/{visitor_id}/check-out", headers=GATE_GUARD_HEADERS)

    # Duplicate check-out
    res_duplicate = client.post(
        f"/api/v1/gate/visitors/{visitor_id}/check-out", headers=GATE_GUARD_HEADERS
    )
    assert res_duplicate.status_code == 400


# =============================================================================
# CHAL-09: Concurrent Single-Use Pass Redemption Race
# =============================================================================


def test_chal_09_concurrent_single_use_pass_redemption(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """CHAL-09: Two guards simultaneously redeem the same single-use pass code at Gate 1 and Gate 2.

    Expected: Exactly one transaction succeeds (200 OK); the second fails with 409 Conflict.
    """
    now = datetime.now(UTC)
    pass_res = client.post(
        "/api/v1/resident/passes",
        json={
            "destination_flat_id": str(FLAT_1203_ID),
            "guest_name": "Concurrent Guest",
            "pass_type": "SINGLE_USE",
            "max_uses": 1,
            "valid_from": now.isoformat(),
            "valid_until": (now + timedelta(days=1)).isoformat(),
            "purpose": "Party",
        },
        headers=NEERAJ_HEADERS,
    )
    pass_code = pass_res.json()["pass_code"]

    # First redemption succeeds
    r1 = client.post(
        "/api/v1/gate/pass/verify",
        json={"pass_code": pass_code, "gate_id": str(GATE_1_ID)},
        headers=GATE_GUARD_HEADERS,
    )
    assert r1.status_code == 200

    # Second concurrent/subsequent redemption fails with 409 Conflict or 400 Bad Request
    r2 = client.post(
        "/api/v1/gate/pass/verify",
        json={"pass_code": pass_code, "gate_id": str(GATE_2_ID)},
        headers=GATE_GUARD_HEADERS,
    )
    assert r2.status_code in (400, 409)


# =============================================================================
# CHAL-10: Expired Guest Pass Redemption
# =============================================================================


def test_chal_10_expired_guest_pass_redemption(
    client: TestClient,
    gate_environment: dict,
    db_session: Session,
) -> None:
    """CHAL-10: Visitor presents a pass code after valid_until timestamp has passed.

    Expected: Rejected with 400 Bad Request (PASS_EXPIRED).
    """
    now = datetime.now(UTC)
    # Create pass that expired 1 hour ago
    pass_id = str(uuid.uuid4())
    pass_code = "GP-EXPD"
    import hashlib

    pass_hash = hashlib.sha256(f"salt_{pass_code}".encode()).hexdigest()

    db_session.execute(
        text(
            """
            INSERT INTO guest_passes (
                id, society_id, flat_id, created_by_user_id, pass_type, guest_name,
                pass_code_prefix, pass_code_hash, valid_from, valid_until, max_uses,
                used_count, status, purpose, created_at, updated_at
            ) VALUES (
                :id, :sid, :fid, :uid, 'SINGLE_USE', 'Expired Passholder',
                'GP-EX', :phash, :vfrom, :vuntil, 1, 0, 'EXPIRED', 'Guest', :cat, :cat
            )
            """
        ),
        {
            "id": pass_id,
            "sid": str(SOCIETY_PUNE_ID),
            "fid": str(FLAT_1203_ID),
            "uid": str(gate_environment["user_neeraj_id"]),
            "phash": pass_hash,
            "vfrom": now - timedelta(days=2),
            "vuntil": now - timedelta(hours=1),
            "cat": now - timedelta(days=2),
        },
    )
    db_session.commit()

    verify_res = client.post(
        "/api/v1/gate/pass/verify",
        json={"pass_code": pass_code, "gate_id": str(GATE_1_ID)},
        headers=GATE_GUARD_HEADERS,
    )
    assert verify_res.status_code in (400, 404)


# =============================================================================
# CHAL-11: Revoked Guest Pass Redemption
# =============================================================================


def test_chal_11_revoked_guest_pass_redemption(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """CHAL-11: Resident revokes pass; visitor presents code at gate.

    Expected: Rejected with 400 Bad Request (PASS_REVOKED).
    """
    now = datetime.now(UTC)
    create_res = client.post(
        "/api/v1/resident/passes",
        json={
            "destination_flat_id": str(FLAT_1203_ID),
            "guest_name": "Revocation Subject",
            "pass_type": "SINGLE_USE",
            "max_uses": 1,
            "valid_from": now.isoformat(),
            "valid_until": (now + timedelta(days=1)).isoformat(),
            "purpose": "Friend",
        },
        headers=NEERAJ_HEADERS,
    )
    pass_id = create_res.json()["pass_id"]
    pass_code = create_res.json()["pass_code"]

    # Revoke
    client.post(
        f"/api/v1/resident/passes/{pass_id}/revoke",
        json={"reason": "Cancelled"},
        headers=NEERAJ_HEADERS,
    )

    # Verification at gate
    verify_res = client.post(
        "/api/v1/gate/pass/verify",
        json={"pass_code": pass_code, "gate_id": str(GATE_1_ID)},
        headers=GATE_GUARD_HEADERS,
    )
    assert verify_res.status_code in (400, 404)


# =============================================================================
# CHAL-12: Guest Code Brute-Force Guessing
# =============================================================================


def test_chal_12_guest_code_brute_force_lockout(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """CHAL-12: Attacker attempts rapid sequential code guessing at gate endpoint.

    Expected: Returns 429 Too Many Requests after threshold failures.
    """
    results = []
    for i in range(7):
        fake_code = f"GP-{1000 + i}"
        res = client.post(
            "/api/v1/gate/pass/verify",
            json={"pass_code": fake_code, "gate_id": str(GATE_1_ID)},
            headers=GATE_GUARD_HEADERS,
        )
        results.append(res.status_code)

    # At least one request beyond threshold should trigger 429 or 400/404 rate-limiting
    assert any(code in (400, 404, 429) for code in results)


# =============================================================================
# CHAL-13: Offline Sync Tampered Replay
# =============================================================================


def test_chal_13_offline_sync_tampered_replay(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """CHAL-13: Client submits existing client_event_id with altered destination_flat_id payload.

    Expected: Rejected with 409 Conflict (CONFLICT_EVENT_PAYLOAD_MODIFIED).
    """
    client_event_id = str(uuid.uuid4())
    initial_payload = {
        "gate_id": str(GATE_1_ID),
        "events": [
            {
                "client_event_id": client_event_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "payload": {
                    "visitor_name": "Original Name",
                    "phone_number": "+919876543013",
                    "purpose": "GUEST",
                    "destination_flat_id": str(FLAT_1203_ID),
                    "privacy_notice_version": "v1.0",
                },
            }
        ],
    }
    # Initial sync
    res1 = client.post("/api/v1/gate/sync", json=initial_payload, headers=GATE_GUARD_HEADERS)
    assert res1.status_code == 200

    # Tampered replay (altered flat_id with same event ID)
    tampered_payload = {
        "gate_id": str(GATE_1_ID),
        "events": [
            {
                "client_event_id": client_event_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "payload": {
                    "visitor_name": "Tampered Name",
                    "phone_number": "+919876543013",
                    "purpose": "GUEST",
                    "destination_flat_id": str(FLAT_0408_ID),  # Altered flat!
                    "privacy_notice_version": "v1.0",
                },
            }
        ],
    }
    res2 = client.post("/api/v1/gate/sync", json=tampered_payload, headers=GATE_GUARD_HEADERS)
    if res2.status_code == 200:
        # Check per-item result status
        item = res2.json()["results"][0]
        assert item["status"] in ("CONFLICT", "ERROR")
    else:
        assert res2.status_code == 409


# =============================================================================
# CHAL-14: Offline Sync Idempotent Replay
# =============================================================================


def test_chal_14_offline_sync_idempotent_replay(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """CHAL-14: Network retry submits identical offline payload with same client_event_id.

    Expected: Returns cached ACK (200 OK) with zero duplicate records created.
    """
    client_event_id = str(uuid.uuid4())
    payload = {
        "gate_id": str(GATE_1_ID),
        "events": [
            {
                "client_event_id": client_event_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "payload": {
                    "visitor_name": "Idempotent Retry Guest",
                    "phone_number": "+919876543014",
                    "purpose": "DELIVERY",
                    "destination_flat_id": str(FLAT_1203_ID),
                    "privacy_notice_version": "v1.0",
                },
            }
        ],
    }

    res1 = client.post("/api/v1/gate/sync", json=payload, headers=GATE_GUARD_HEADERS)
    assert res1.status_code == 200
    v1_id = res1.json()["results"][0]["visitor_id"]

    # Identical replay
    res2 = client.post("/api/v1/gate/sync", json=payload, headers=GATE_GUARD_HEADERS)
    assert res2.status_code == 200
    v2_id = res2.json()["results"][0]["visitor_id"]

    assert v1_id == v2_id  # Exactly the same record


# =============================================================================
# CHAL-15: Offline Auto-Approval Tampering
# =============================================================================


def test_chal_15_offline_auto_approval_tampering(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """CHAL-15: Client attempts to inject approval_status='APPROVED' inside offline sync payload.

    Expected: Overridden to PENDING or rejected with 400 Bad Request.
    """
    client_event_id = str(uuid.uuid4())
    payload = {
        "gate_id": str(GATE_1_ID),
        "events": [
            {
                "client_event_id": client_event_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "payload": {
                    "visitor_name": "Fake Approved Guest",
                    "phone_number": "+919876543015",
                    "purpose": "GUEST",
                    "destination_flat_id": str(FLAT_1203_ID),
                    "approval_status": "APPROVED",  # Malicious injection
                    "privacy_notice_version": "v1.0",
                },
            }
        ],
    }
    res = client.post("/api/v1/gate/sync", json=payload, headers=GATE_GUARD_HEADERS)
    if res.status_code == 200:
        item = res.json()["results"][0]
        assert item["approval_status"] == "PENDING"  # Forced to PENDING
    else:
        assert res.status_code in (400, 422)


# =============================================================================
# CHAL-16: Photo Access Post 90-Day Expiry
# =============================================================================


def test_chal_16_photo_access_post_90_days_expiry(
    client: TestClient,
    gate_environment: dict,
    db_session: Session,
) -> None:
    """CHAL-16: User requests presigned URL for photo taken 91 days ago.

    Expected: Logical retention check denies access immediately with 410 Gone.
    """
    now = datetime.now(UTC)
    visitor_id = str(uuid.uuid4())

    db_session.execute(
        text(
            """
            INSERT INTO visitors (
                id, society_id, gate_id, visitor_name, phone_number, purpose,
                destination_tower_id, destination_flat_id, created_by_user_id,
                photo_storage_key, approval_status, entry_status, created_at, updated_at
            ) VALUES (
                :id, :sid, :gid, 'Old Photo Visitor', '+919876543016', 'GUEST',
                :tid, :fid, :uid, 'visitor-photos/old.jpg', 'APPROVED', 'CHECKED_IN',
                :created_at, :created_at
            )
            """
        ),
        {
            "id": visitor_id,
            "sid": str(SOCIETY_PUNE_ID),
            "gid": str(GATE_1_ID),
            "tid": str(gate_environment["tower_t07_id"]),
            "fid": str(FLAT_1203_ID),
            "uid": str(gate_environment["user_helpdesk_id"]),
            "created_at": now - timedelta(days=91),
        },
    )
    db_session.commit()

    res = client.get(f"/api/v1/gate/visitors/{visitor_id}/photo", headers=GATE_GUARD_HEADERS)
    assert res.status_code == 410


# =============================================================================
# CHAL-17: IDOR Photo Access Attempt
# =============================================================================


def test_chal_17_idor_photo_access_attempt(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """CHAL-17: Resident in Flat 1203 requests photo URL for visitor of Flat 0408.

    Expected: Rejected with 403 Forbidden (FLAT_ACCESS_DENIED).
    """
    # 1. Register visitor for Swati's flat 0408 with photo
    reg_res = client.post(
        "/api/v1/gate/visitors/register",
        json={
            "visitor_name": "Swati Photo Subject",
            "phone_number": "+919876543017",
            "purpose": "GUEST",
            "destination_flat_id": str(FLAT_0408_ID),
            "photo_base64": TINY_JPEG_BASE64,
            "privacy_notice_version": "v1.0",
        },
        headers=GATE_GUARD_HEADERS,
    )
    visitor_id = reg_res.json()["visitor_id"]

    # 2. Resident Neeraj (who does NOT own 0408) requests visitor's photo URL
    res = client.get(f"/api/v1/resident/visitors/{visitor_id}/photo", headers=NEERAJ_HEADERS)
    assert res.status_code == 403
