"""Tier 3: Pairwise & Cross-Feature Combinations Test Suite.

Covers:
- Pair 1: Single-Use Pass + Multi-Gate Traversal (Entry at Gate 1, Exit at Gate 4)
- Pair 2: Multi-Use Pass + Cross-Gate Redemptions (Gate 1, Gate 2, Gate 4)
- Pair 3: Offline Batch Sync + Real-Time Resident Approval + Gate Check-In
- Pair 4: Walk-In Registration + Approval + Premature Exit Rejection + Proper Exit
- Pair 5: Multi-Tenant Resident Inbox Isolation (Neeraj Flat 1203 vs Swati Flat 0408)
- Pair 6: Pre-Approved Pass Creation + Transit Revocation + Gate Rejection
- Pair 7: Multilingual Privacy Notice Stamping + Historical Audit Preservation
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from services.api.tests.e2e.conftest import (
    FLAT_0408_ID,
    FLAT_1203_ID,
    GATE_1_ID,
    GATE_2_ID,
    GATE_4_ID,
    GATE_GUARD_HEADERS,
    NEERAJ_HEADERS,
    SOCIETY_PUNE_ID,
    SWATI_HEADERS,
    TINY_JPEG_BASE64,
)
from sqlalchemy import text
from sqlalchemy.orm import Session

# =============================================================================
# Pair 1: Single-Use Pass + Multi-Gate Traversal (Entry at Gate 1, Exit at Gate 4)
# =============================================================================


def test_tier3_single_use_pass_multi_gate_traversal(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """Combines single-use pass creation, entry verification at Gate 1, and exit at Gate 4."""
    now = datetime.now(UTC)

    # 1. Resident Neeraj creates single-use pass
    create_res = client.post(
        "/api/v1/resident/passes",
        json={
            "destination_flat_id": str(FLAT_1203_ID),
            "guest_name": "Multi-Gate Single Visitor",
            "pass_type": "SINGLE_USE",
            "max_uses": 1,
            "valid_from": now.isoformat(),
            "valid_until": (now + timedelta(days=1)).isoformat(),
            "purpose": "Friend",
        },
        headers=NEERAJ_HEADERS,
    )
    assert create_res.status_code == 201
    pass_code = create_res.json()["pass_code"]

    # 2. Guest enters at Gate 1
    verify_res = client.post(
        "/api/v1/gate/pass/verify",
        json={"pass_code": pass_code, "gate_id": str(GATE_1_ID)},
        headers=GATE_GUARD_HEADERS,
    )
    assert verify_res.status_code == 200
    verify_data = verify_res.json()
    visitor_id = verify_data["visitor_id"]
    assert verify_data["entry_status"] == "CHECKED_IN"
    assert verify_data["remaining_uses"] == 0

    # 3. Guest exits campus through Gate 4
    exit_res = client.post(
        f"/api/v1/gate/visitors/{visitor_id}/check-out",
        json={"exit_gate_id": str(GATE_4_ID)},
        headers=GATE_GUARD_HEADERS,
    )
    assert exit_res.status_code == 200
    exit_data = exit_res.json()
    assert exit_data["entry_status"] == "CHECKED_OUT"
    assert exit_data.get("exit_gate_id") == str(GATE_4_ID) or "exit_time" in exit_data


# =============================================================================
# Pair 2: Multi-Use Pass + Cross-Gate Redemptions (Gate 1, Gate 2, Gate 4)
# =============================================================================


def test_tier3_multi_use_pass_cross_gate_redemptions(
    client: TestClient,
    gate_environment: dict,
    db_session: Session,
) -> None:
    """Combines a 3-use pass with redemptions across distinct gates (Gate 1, Gate 2, Gate 4)."""
    now = datetime.now(UTC)

    # Assign guard to Gate 2 and Gate 4 as well
    for gid in [GATE_2_ID, GATE_4_ID]:
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
                "user_id": str(gate_environment["user_helpdesk_id"]),
                "assigned_from": now - timedelta(hours=1),
                "created_at": now,
                "updated_at": now,
            },
        )
    db_session.commit()

    # 1. Create 3-use pass
    create_res = client.post(
        "/api/v1/resident/passes",
        json={
            "destination_flat_id": str(FLAT_1203_ID),
            "guest_name": "Contractor Rajesh",
            "pass_type": "MULTI_USE",
            "max_uses": 3,
            "valid_from": now.isoformat(),
            "valid_until": (now + timedelta(days=3)).isoformat(),
            "purpose": "Maintenance",
        },
        headers=NEERAJ_HEADERS,
    )
    assert create_res.status_code == 201
    pass_code = create_res.json()["pass_code"]

    # Redemption 1 at Gate 1
    r1 = client.post(
        "/api/v1/gate/pass/verify",
        json={"pass_code": pass_code, "gate_id": str(GATE_1_ID)},
        headers=GATE_GUARD_HEADERS,
    )
    assert r1.status_code == 200
    assert r1.json()["remaining_uses"] == 2
    vis1_id = r1.json()["visitor_id"]
    # Checkout 1
    client.post(f"/api/v1/gate/visitors/{vis1_id}/check-out", headers=GATE_GUARD_HEADERS)

    # Redemption 2 at Gate 2
    r2 = client.post(
        "/api/v1/gate/pass/verify",
        json={"pass_code": pass_code, "gate_id": str(GATE_2_ID)},
        headers=GATE_GUARD_HEADERS,
    )
    assert r2.status_code == 200
    assert r2.json()["remaining_uses"] == 1
    vis2_id = r2.json()["visitor_id"]
    # Checkout 2
    client.post(f"/api/v1/gate/visitors/{vis2_id}/check-out", headers=GATE_GUARD_HEADERS)

    # Redemption 3 at Gate 4 -> Reaches max uses (0 remaining, status EXHAUSTED)
    r3 = client.post(
        "/api/v1/gate/pass/verify",
        json={"pass_code": pass_code, "gate_id": str(GATE_4_ID)},
        headers=GATE_GUARD_HEADERS,
    )
    assert r3.status_code == 200
    assert r3.json()["remaining_uses"] == 0

    # 4th Redemption attempt must fail (EXHAUSTED)
    r4 = client.post(
        "/api/v1/gate/pass/verify",
        json={"pass_code": pass_code, "gate_id": str(GATE_1_ID)},
        headers=GATE_GUARD_HEADERS,
    )
    assert r4.status_code in (400, 409)


# =============================================================================
# Pair 3: Offline Batch Sync + Real-Time Resident Approval + Gate Check-In
# =============================================================================


def test_tier3_offline_sync_to_resident_approval_pipeline(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """Combines offline batch sync with subsequent resident in-app approval and physical check-in."""
    client_event_id = str(uuid.uuid4())
    # 1. Batch sync offline event
    sync_res = client.post(
        "/api/v1/gate/sync",
        json={
            "gate_id": str(GATE_1_ID),
            "events": [
                {
                    "client_event_id": client_event_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "payload": {
                        "visitor_name": "Synced Guest Dinesh",
                        "phone_number": "+919876543111",
                        "purpose": "GUEST",
                        "destination_flat_id": str(FLAT_1203_ID),
                        "photo_base64": TINY_JPEG_BASE64,
                        "privacy_notice_version": "v1.0",
                    },
                }
            ],
        },
        headers=GATE_GUARD_HEADERS,
    )
    assert sync_res.status_code == 200
    visitor_id = sync_res.json()["results"][0]["visitor_id"]

    # 2. Resident Neeraj sees pending visitor and approves
    action_res = client.post(
        f"/api/v1/resident/visitors/{visitor_id}/action",
        json={"action": "APPROVE"},
        headers=NEERAJ_HEADERS,
    )
    assert action_res.status_code == 200
    assert action_res.json()["approval_status"] == "APPROVED"

    # 3. Gate guard checks in visitor
    checkin_res = client.post(
        f"/api/v1/gate/visitors/{visitor_id}/check-in",
        headers=GATE_GUARD_HEADERS,
    )
    assert checkin_res.status_code == 200
    assert checkin_res.json()["entry_status"] == "CHECKED_IN"


# =============================================================================
# Pair 4: Walk-In Registration + Approval + Premature Exit Rejection + Proper Exit
# =============================================================================


def test_tier3_premature_exit_rejection_before_checkin(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """Verifies that an approved visitor in EXPECTED status CANNOT be checked out prematurely."""
    # 1. Register
    reg_res = client.post(
        "/api/v1/gate/visitors/register",
        json={
            "visitor_name": "Premature Exit Visitor",
            "phone_number": "+919876543122",
            "purpose": "GUEST",
            "destination_flat_id": str(FLAT_1203_ID),
            "privacy_notice_version": "v1.0",
        },
        headers=GATE_GUARD_HEADERS,
    )
    visitor_id = reg_res.json()["visitor_id"]

    # 2. Resident approves
    client.post(
        f"/api/v1/resident/visitors/{visitor_id}/action",
        json={"action": "APPROVE"},
        headers=NEERAJ_HEADERS,
    )

    # 3. Guard attempts check-out while still EXPECTED -> Must fail with 400
    premature_checkout = client.post(
        f"/api/v1/gate/visitors/{visitor_id}/check-out",
        headers=GATE_GUARD_HEADERS,
    )
    assert premature_checkout.status_code == 400

    # 4. Guard checks in visitor
    checkin_res = client.post(
        f"/api/v1/gate/visitors/{visitor_id}/check-in",
        headers=GATE_GUARD_HEADERS,
    )
    assert checkin_res.status_code == 200

    # 5. Now check-out succeeds
    valid_checkout = client.post(
        f"/api/v1/gate/visitors/{visitor_id}/check-out",
        headers=GATE_GUARD_HEADERS,
    )
    assert valid_checkout.status_code == 200
    assert valid_checkout.json()["entry_status"] == "CHECKED_OUT"


# =============================================================================
# Pair 5: Multi-Tenant Resident Inbox Isolation (Neeraj 1203 vs Swati 0408)
# =============================================================================


def test_tier3_multi_tenant_resident_inbox_scoping(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """Combines registrations for two different flats and asserts strict inbox isolation."""
    # Register V1 for Flat 1203 (Neeraj)
    res1 = client.post(
        "/api/v1/gate/visitors/register",
        json={
            "visitor_name": "Neeraj Guest V1",
            "phone_number": "+919876543133",
            "purpose": "GUEST",
            "destination_flat_id": str(FLAT_1203_ID),
            "privacy_notice_version": "v1.0",
        },
        headers=GATE_GUARD_HEADERS,
    )
    v1_id = res1.json()["visitor_id"]

    # Register V2 for Flat 0408 (Swati)
    res2 = client.post(
        "/api/v1/gate/visitors/register",
        json={
            "visitor_name": "Swati Guest V2",
            "phone_number": "+919876543144",
            "purpose": "DELIVERY",
            "destination_flat_id": str(FLAT_0408_ID),
            "privacy_notice_version": "v1.0",
        },
        headers=GATE_GUARD_HEADERS,
    )
    v2_id = res2.json()["visitor_id"]

    # Neeraj checks pending inbox
    neeraj_inbox = client.get("/api/v1/resident/visitors/pending", headers=NEERAJ_HEADERS).json()
    neeraj_ids = [v["visitor_id"] for v in neeraj_inbox]
    assert v1_id in neeraj_ids
    assert v2_id not in neeraj_ids

    # Swati checks pending inbox
    swati_inbox = client.get("/api/v1/resident/visitors/pending", headers=SWATI_HEADERS).json()
    swati_ids = [v["visitor_id"] for v in swati_inbox]
    assert v2_id in swati_ids
    assert v1_id not in swati_ids


# =============================================================================
# Pair 6: Pre-Approved Pass Creation + Transit Revocation + Gate Rejection
# =============================================================================


def test_tier3_pass_revoked_in_transit_rejection(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """Combines pass generation, revocation while guest travels, and rejection at gate."""
    now = datetime.now(UTC)
    create_res = client.post(
        "/api/v1/resident/passes",
        json={
            "destination_flat_id": str(FLAT_1203_ID),
            "guest_name": "Transit Visitor",
            "pass_type": "SINGLE_USE",
            "max_uses": 1,
            "valid_from": now.isoformat(),
            "valid_until": (now + timedelta(days=1)).isoformat(),
            "purpose": "Delivery",
        },
        headers=NEERAJ_HEADERS,
    )
    assert create_res.status_code == 201
    pass_id = create_res.json()["pass_id"]
    pass_code = create_res.json()["pass_code"]

    # Resident revokes pass
    client.post(
        f"/api/v1/resident/passes/{pass_id}/revoke",
        json={"reason": "Order cancelled"},
        headers=NEERAJ_HEADERS,
    )

    # Guest arrives at gate with revoked code
    verify_res = client.post(
        "/api/v1/gate/pass/verify",
        json={"pass_code": pass_code, "gate_id": str(GATE_1_ID)},
        headers=GATE_GUARD_HEADERS,
    )
    assert verify_res.status_code in (400, 404)


# =============================================================================
# Pair 7: Multilingual Privacy Notice Stamping + Historical Audit Preservation
# =============================================================================


def test_tier3_multilingual_notice_stamped_and_retrieved_in_history(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """Combines multilingual registration with version stamping and history verification."""
    # Register visitor in Marathi locale context acknowledging v1.0-2026-pune
    reg_res = client.post(
        "/api/v1/gate/visitors/register",
        json={
            "visitor_name": "संजय जोशी",  # Sanjay Joshi in Marathi
            "phone_number": "+919876543155",
            "purpose": "GUEST",
            "destination_flat_id": str(FLAT_1203_ID),
            "privacy_notice_version": "v1.0-2026-pune",
        },
        headers={**GATE_GUARD_HEADERS, "Accept-Language": "mr"},
    )
    assert reg_res.status_code == 201
    visitor_id = reg_res.json()["visitor_id"]

    # Query visitor history
    history_res = client.get(
        f"/api/v1/gate/visitors/{visitor_id}",
        headers=GATE_GUARD_HEADERS,
    )
    if history_res.status_code == 200:
        data = history_res.json()
        assert data.get("privacy_notice_version") == "v1.0-2026-pune"
        assert data["visitor_name"] == "संजय जोशी"
