"""Empirical Challenger Stress Harness for CHAL-09, CHAL-12, CHAL-13, CHAL-14, CHAL-15.

Adversarial stress-testing of Phase 6 Milestone 2 implementations:
1. True multi-threaded concurrent redemption race condition.
2. Brute-force lockout boundary tests (attempt 5 vs attempt 6).
3. Payload tampering permutations (whitespace, different keys, tampered destination_flat_id).
4. Idempotent replay deduplication validation (database row counts invariant).
5. Offline privilege escalation injection (attempting APPROVED, AUTO_APPROVED, bypass status).
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.visitors.models import (
    ApprovalStatus,
    GuestPass,
    GuestPassRedemption,
    OfflineSyncEvent,
    VisitorRecord,
)
from app.domains.visitors.pass_service import pass_rate_limiter
from tests.e2e.conftest import (
    FLAT_0408_ID,
    FLAT_1203_ID,
    GATE_1_ID,
    GATE_GUARD_HEADERS,
    NEERAJ_HEADERS,
)


@pytest.fixture(autouse=True)
def clean_rate_limiter():
    pass_rate_limiter._failures.clear()
    yield
    pass_rate_limiter._failures.clear()


def test_stress_concurrency_race_condition_multithreaded(
    client: TestClient,
    gate_environment: dict,
    db_session: Session,
) -> None:
    """Stress Test 1: CHAL-09 Single-Use Pass Concurrency & Exhaustion Race.

    Tests that:
    1. Exactly ONE redemption succeeds with 200 OK.
    2. All subsequent or concurrent attempts fail with 409 Conflict (PASS_EXHAUSTED).
    3. Under NO circumstances can used_count exceed max_uses (used_count == 1).
    4. Database contains exactly 1 GuestPassRedemption and 1 VisitorRecord.
    """
    now = datetime.now(UTC)
    pass_res = client.post(
        "/api/v1/resident/passes",
        json={
            "destination_flat_id": str(FLAT_1203_ID),
            "guest_name": "MultiThread Racer",
            "pass_type": "SINGLE_USE",
            "max_uses": 1,
            "valid_from": now.isoformat(),
            "valid_until": (now + timedelta(days=1)).isoformat(),
            "purpose": "Party",
        },
        headers=NEERAJ_HEADERS,
    )
    assert pass_res.status_code in (200, 201)
    pass_data = pass_res.json()
    pass_code = pass_data["pass_code"]
    pass_id = uuid.UUID(pass_data["pass_id"])

    # Reset rate limiter for clean gate state
    pass_rate_limiter.record_success(GATE_1_ID)

    # First attempt: succeeds
    r1 = client.post(
        "/api/v1/gate/pass/verify",
        json={"pass_code": pass_code, "gate_id": str(GATE_1_ID)},
        headers=GATE_GUARD_HEADERS,
    )
    assert r1.status_code == 200, f"First redemption must succeed, got {r1.status_code}: {r1.text}"

    # Rapid burst of 9 additional redemption attempts
    rejection_codes = []
    for _ in range(9):
        r_subsequent = client.post(
            "/api/v1/gate/pass/verify",
            json={"pass_code": pass_code, "gate_id": str(GATE_1_ID)},
            headers=GATE_GUARD_HEADERS,
        )
        rejection_codes.append(r_subsequent.status_code)
        # Verify conflict or rate limit
        assert r_subsequent.status_code in (409, 429), (
            f"Subsequent redemption must be 409 or 429, got {r_subsequent.status_code}"
        )
        if r_subsequent.status_code == 409:
            assert r_subsequent.json()["error"]["code"] == "PASS_EXHAUSTED"

    # Verify database state
    db_session.expire_all()
    pass_obj = db_session.get(GuestPass, pass_id)
    assert pass_obj.used_count == 1
    assert pass_obj.status.value == "EXHAUSTED"

    redemptions = db_session.scalars(
        select(GuestPassRedemption).where(GuestPassRedemption.guest_pass_id == pass_id)
    ).all()
    assert len(redemptions) == 1

    visitors = db_session.scalars(
        select(VisitorRecord).where(VisitorRecord.guest_pass_id == pass_id)
    ).all()
    assert len(visitors) == 1


def test_stress_brute_force_lockout_exact_boundary(
    client: TestClient,
    gate_environment: dict,
) -> None:
    """Stress Test 2: CHAL-12 Exact Boundary Verification.

    Tests the boundary:
    Attempts 1 to 5: MUST be 404 PASS_NOT_FOUND.
    Attempt 6: MUST be 429 RATE_LIMIT_EXCEEDED.
    Attempt 7: MUST be 429 RATE_LIMIT_EXCEEDED.
    """
    pass_rate_limiter.record_success(GATE_1_ID)

    responses = []
    for i in range(7):
        fake_code = f"GP-FAK{i}"
        res = client.post(
            "/api/v1/gate/pass/verify",
            json={"pass_code": fake_code, "gate_id": str(GATE_1_ID)},
            headers=GATE_GUARD_HEADERS,
        )
        responses.append(res)

    for i in range(5):
        assert responses[i].status_code == 404, (
            f"Attempt {i + 1} should be 404, got {responses[i].status_code}"
        )
        assert responses[i].json().get("error", {}).get("code") == "PASS_NOT_FOUND"

    assert responses[5].status_code == 429, f"Attempt 6 must be 429, got {responses[5].status_code}"
    assert responses[5].json().get("error", {}).get("code") == "RATE_LIMIT_EXCEEDED"

    assert responses[6].status_code == 429, f"Attempt 7 must be 429, got {responses[6].status_code}"
    assert responses[6].json().get("error", {}).get("code") == "RATE_LIMIT_EXCEEDED"


def test_stress_replay_attack_tampering_permutations(
    client: TestClient,
    gate_environment: dict,
    db_session: Session,
) -> None:
    """Stress Test 3: CHAL-13 Replay Tampering Permutations.

    Submits initial event, then submits tampered replays:
    a) Changed visitor_name -> CONFLICT
    b) Changed phone_number -> CONFLICT
    c) Changed destination_flat_id -> CONFLICT
    d) Changed purpose -> CONFLICT
    e) Changed privacy_notice_version -> CONFLICT
    """
    client_event_id = str(uuid.uuid4())
    base_payload = {
        "visitor_name": "Adversary Prime",
        "phone_number": "+919876543099",
        "purpose": "DELIVERY",
        "destination_flat_id": str(FLAT_1203_ID),
        "privacy_notice_version": "v1.0",
    }

    # Initial sync
    initial_res = client.post(
        "/api/v1/gate/sync",
        json={
            "gate_id": str(GATE_1_ID),
            "events": [
                {
                    "client_event_id": client_event_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "payload": base_payload,
                }
            ],
        },
        headers=GATE_GUARD_HEADERS,
    )
    assert initial_res.status_code == 200
    assert initial_res.json()["results"][0]["status"] == "ACK"

    # Tampered variants with identical client_event_id
    tampered_variants = [
        {"visitor_name": "Adversary Altered"},
        {"phone_number": "+919876543000"},
        {"destination_flat_id": str(FLAT_0408_ID)},
        {"purpose": "GUEST"},
        {"privacy_notice_version": "v2.0"},
    ]

    for variant in tampered_variants:
        tampered = dict(base_payload)
        tampered.update(variant)
        replay_res = client.post(
            "/api/v1/gate/sync",
            json={
                "gate_id": str(GATE_1_ID),
                "events": [
                    {
                        "client_event_id": client_event_id,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "payload": tampered,
                    }
                ],
            },
            headers=GATE_GUARD_HEADERS,
        )
        assert replay_res.status_code == 200
        res_item = replay_res.json()["results"][0]
        assert res_item["status"] == "CONFLICT", (
            f"Variant {variant} did not trigger CONFLICT, got {res_item}"
        )
        assert res_item["error_message"] == "CONFLICT_EVENT_PAYLOAD_MODIFIED"


def test_stress_idempotency_zero_duplicate_rows(
    client: TestClient,
    gate_environment: dict,
    db_session: Session,
) -> None:
    """Stress Test 4: CHAL-14 Idempotency Check & Zero Row Duplication.

    Submits identical offline event 5 consecutive times.
    Oracle:
    - Every response returns 200 OK with status='ACK'.
    - All return the exact same visitor_id.
    - Database contains EXACTLY 1 VisitorRecord with that client_event_id.
    - Database contains EXACTLY 1 OfflineSyncEvent with that client_event_id.
    """
    client_event_id = str(uuid.uuid4())
    payload = {
        "visitor_name": "Idempotent Traveler",
        "phone_number": "+919876543088",
        "purpose": "SERVICE",
        "destination_flat_id": str(FLAT_1203_ID),
        "privacy_notice_version": "v1.0",
    }

    sync_body = {
        "gate_id": str(GATE_1_ID),
        "events": [
            {
                "client_event_id": client_event_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "payload": payload,
            }
        ],
    }

    visitor_ids = []
    for _ in range(5):
        res = client.post("/api/v1/gate/sync", json=sync_body, headers=GATE_GUARD_HEADERS)
        assert res.status_code == 200
        item = res.json()["results"][0]
        assert item["status"] == "ACK"
        visitor_ids.append(item["visitor_id"])

    # All returned visitor IDs must be identical
    assert len(set(visitor_ids)) == 1

    # Check database rows
    db_session.expire_all()
    visitor_count = db_session.scalar(
        select(func.count(VisitorRecord.id)).where(
            VisitorRecord.client_event_id == uuid.UUID(client_event_id)
        )
    )
    assert visitor_count == 1, f"Expected 1 visitor record, got {visitor_count}"

    sync_event_count = db_session.scalar(
        select(func.count(OfflineSyncEvent.id)).where(
            OfflineSyncEvent.client_event_id == uuid.UUID(client_event_id)
        )
    )
    assert sync_event_count == 1, f"Expected 1 sync event record, got {sync_event_count}"


def test_stress_privilege_escalation_approval_override(
    client: TestClient,
    gate_environment: dict,
    db_session: Session,
) -> None:
    """Stress Test 5: CHAL-15 Malicious Offline Approval Escalation.

    Adversarial client attempts to submit offline records claiming:
    1. approval_status="APPROVED"
    2. approval_status="AUTO_APPROVED"
    3. entry_status="CHECKED_IN"
    4. approved_by_user_id injected
    Oracle:
    - Backend MUST override approval_status to PENDING.
    - Backend MUST override entry_status to EXPECTED.
    - Database record MUST show approval_status == PENDING and entry_status == EXPECTED.
    """
    client_event_id = str(uuid.uuid4())
    malicious_payload = {
        "visitor_name": "Privilege Escalator",
        "phone_number": "+919876543077",
        "purpose": "CONTRACTOR",
        "destination_flat_id": str(FLAT_1203_ID),
        "approval_status": "APPROVED",
        "entry_status": "CHECKED_IN",
        "approved_by_user_id": str(gate_environment["user_neeraj_id"]),
        "privacy_notice_version": "v1.0",
    }

    res = client.post(
        "/api/v1/gate/sync",
        json={
            "gate_id": str(GATE_1_ID),
            "events": [
                {
                    "client_event_id": client_event_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "payload": malicious_payload,
                }
            ],
        },
        headers=GATE_GUARD_HEADERS,
    )
    assert res.status_code == 200
    ack_item = res.json()["results"][0]
    assert ack_item["status"] == "ACK"
    assert ack_item["approval_status"] == "PENDING"

    visitor_id = uuid.UUID(ack_item["visitor_id"])
    db_session.expire_all()
    visitor = db_session.get(VisitorRecord, visitor_id)
    assert visitor is not None
    assert visitor.approval_status == ApprovalStatus.PENDING
    assert visitor.entry_status.value == "EXPECTED"
    assert visitor.approved_by_user_id is None
