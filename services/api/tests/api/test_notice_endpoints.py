"""API Integration Tests for Official Township Notices & Circulars Endpoints

Validates:
- Staff notice creation, editing, publishing, and archiving endpoints
- Resident notice feed, filtering, and detail endpoints
- Read and mark-all-read transitions for residents
- Emergency notice broadcast generating notifications for targeted residents
- RBAC enforcement (residents cannot create or manage notices)
- Cross-society isolation
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from scripts.seed import (
    FLAT_0408_ID,
    FLAT_1203_ID,
    TOWER_T07_ID,
    TOWER_T12_ID,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import CurrentUserClaims, get_current_user
from app.domains.identity.models import (
    Permission,
    RoleType,
)
from app.main import app

STAFF_HELPDESK_HEADERS = {"X-Dev-User": "helpdesk"}
RESIDENT_NEERAJ_HEADERS = {"X-Dev-User": "neeraj"}
RESIDENT_SWATI_HEADERS = {"X-Dev-User": "swati"}

SOCIETY_PUNE_ID = "11111111-1111-1111-1111-111111111111"
OTHER_SOCIETY_ID = "99999999-9999-9999-9999-999999999999"


def test_staff_create_edit_publish_and_archive_notice_api(
    client: TestClient, db_session: Session
) -> None:
    # 1. Staff creates draft circular
    create_payload = {
        "title": "Water Tank Cleaning Notice",
        "body": "Overhead water tanks in Tower 7 and Tower 12 will be cleaned this Saturday.",
        "category": "MAINTENANCE",
        "priority": "HIGH",
        "status": "DRAFT",
        "target_type": "SOCIETY",
        "is_pinned": True,
    }
    create_res = client.post(
        "/api/v1/notifications/staff/notices",
        json=create_payload,
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert create_res.status_code == 201
    notice_data = create_res.json()
    notice_id = notice_data["id"]
    assert notice_data["title"] == "Water Tank Cleaning Notice"
    assert notice_data["status"] == "DRAFT"
    assert notice_data["is_pinned"] is True

    # 2. Staff views notice detail
    detail_res = client.get(
        f"/api/v1/notifications/staff/notices/{notice_id}",
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert detail_res.status_code == 200
    assert detail_res.json()["id"] == notice_id

    # 3. Staff updates draft
    update_res = client.put(
        f"/api/v1/notifications/staff/notices/{notice_id}",
        json={"title": "Water Tank Cleaning Notice - Rescheduled to Sunday"},
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert update_res.status_code == 200
    assert update_res.json()["title"] == "Water Tank Cleaning Notice - Rescheduled to Sunday"

    # 4. Staff publishes notice
    pub_res = client.post(
        f"/api/v1/notifications/staff/notices/{notice_id}/publish",
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert pub_res.status_code == 200
    assert pub_res.json()["status"] == "PUBLISHED"
    assert pub_res.json()["published_at"] is not None

    # 5. Staff archives notice
    arch_res = client.post(
        f"/api/v1/notifications/staff/notices/{notice_id}/archive",
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert arch_res.status_code == 200
    assert arch_res.json()["status"] == "ARCHIVED"


def test_resident_notices_feed_read_and_read_all_api(
    client: TestClient, db_session: Session
) -> None:
    # Staff creates and publishes two notices
    n1_res = client.post(
        "/api/v1/notifications/staff/notices",
        json={
            "title": "Township Diwali Celebration",
            "body": "Join us at the central amphitheatre on Sunday.",
            "category": "EVENT",
            "priority": "NORMAL",
            "status": "PUBLISHED",
            "target_type": "SOCIETY",
            "is_pinned": False,
        },
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert n1_res.status_code == 201
    n1_id = n1_res.json()["id"]

    n2_res = client.post(
        "/api/v1/notifications/staff/notices",
        json={
            "title": "Elevator Maintenance Protocol",
            "body": "Strict elevator safety rules.",
            "category": "CIRCULAR",
            "priority": "HIGH",
            "status": "PUBLISHED",
            "target_type": "SOCIETY",
            "is_pinned": True,
        },
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert n2_res.status_code == 201
    n2_id = n2_res.json()["id"]

    # Resident lists notices
    feed_res = client.get(
        "/api/v1/notifications/resident/notices",
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert feed_res.status_code == 200
    feed_data = feed_res.json()
    items = feed_data["items"]
    item_ids = [it["id"] for it in items]
    assert n1_id in item_ids
    assert n2_id in item_ids
    # Pinned notice should be ordered first
    assert items[0]["id"] == n2_id
    assert items[0]["is_pinned"] is True

    # Mark notice 1 as read
    read_res = client.patch(
        f"/api/v1/notifications/resident/notices/{n1_id}/read",
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert read_res.status_code == 200
    assert read_res.json()["status"] == "success"

    # Resident gets single notice detail
    single_res = client.get(
        f"/api/v1/notifications/resident/notices/{n1_id}",
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert single_res.status_code == 200
    assert single_res.json()["is_read"] is True

    # Resident marks all notices read
    all_read_res = client.patch(
        "/api/v1/notifications/resident/notices/read-all",
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert all_read_res.status_code == 200

    # Verify unread count is 0
    feed_res_after = client.get(
        "/api/v1/notifications/resident/notices",
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert feed_res_after.json()["unread_count"] == 0


def test_emergency_notice_broadcast_integration_api(
    client: TestClient, db_session: Session
) -> None:
    # Staff publishes emergency notice
    emg_res = client.post(
        "/api/v1/notifications/staff/notices",
        json={
            "title": "FIRE ALARM TESTING",
            "body": "Fire alarms will sound between 11:00 AM and 11:30 AM. No evacuation needed.",
            "category": "EMERGENCY",
            "priority": "URGENT",
            "status": "PUBLISHED",
            "target_type": "SOCIETY",
            "deliver_emergency": True,
            "confirm_emergency_broadcast": True,
        },
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert emg_res.status_code == 201

    # Resident checks their personal notification inbox (/api/v1/notifications/me)
    inbox_res = client.get(
        "/api/v1/notifications/me",
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert inbox_res.status_code == 200
    inbox_items = inbox_res.json()["items"]
    emergency_notifs = [it for it in inbox_items if "FIRE ALARM" in it["title"]]
    assert len(emergency_notifs) >= 1
    assert emergency_notifs[0]["priority"] == "URGENT"
    assert emergency_notifs[0]["action_url"] == "/resident/notices"


def test_resident_forbidden_from_staff_endpoints(client: TestClient, db_session: Session) -> None:
    # Resident attempts to create notice
    create_res = client.post(
        "/api/v1/notifications/staff/notices",
        json={
            "title": "Unauthorized Notice",
            "body": "Should fail.",
            "category": "GENERAL",
            "status": "DRAFT",
        },
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert create_res.status_code == 403

    # Resident attempts to list staff notices
    list_res = client.get(
        "/api/v1/notifications/staff/notices",
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert list_res.status_code == 403


def test_cross_society_access_denied(client: TestClient, db_session: Session) -> None:
    fake_society = str(uuid.uuid4())
    # Helpdesk cannot query a society they are not authorized for
    res = client.get(
        f"/api/v1/notifications/staff/notices?society_id={fake_society}",
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert res.status_code == 403


def test_resident_notice_access_control_idor_and_status_enforcement_api(
    client: TestClient, db_session: Session
) -> None:
    now = datetime.now(UTC)
    tower_12_id = "22222222-2222-2222-2222-222222222212"  # Swati's tower
    flat_0408_id = "33333333-3333-3333-3333-333333330408"  # Swati's flat

    # 1. Staff creates draft notice
    r_draft = client.post(
        "/api/v1/notifications/staff/notices",
        json={
            "title": "Secret Committee Draft Notice",
            "body": "Draft circular body.",
            "category": "GENERAL",
            "status": "DRAFT",
            "target_type": "SOCIETY",
        },
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert r_draft.status_code == 201
    draft_id = r_draft.json()["id"]

    # 2. Staff creates and archives a notice
    r_arch = client.post(
        "/api/v1/notifications/staff/notices",
        json={
            "title": "Past Archived Circular",
            "body": "Archived circular body.",
            "category": "GENERAL",
            "status": "PUBLISHED",
            "target_type": "SOCIETY",
        },
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert r_arch.status_code == 201
    arch_id = r_arch.json()["id"]
    client.post(
        f"/api/v1/notifications/staff/notices/{arch_id}/archive",
        headers=STAFF_HELPDESK_HEADERS,
    )

    # 3. Staff creates future scheduled notice
    r_sched = client.post(
        "/api/v1/notifications/staff/notices",
        json={
            "title": "Future Scheduled Notice",
            "body": "Scheduled for future publication.",
            "category": "MAINTENANCE",
            "status": "PUBLISHED",
            "published_at": (now + timedelta(days=2)).isoformat(),
            "target_type": "SOCIETY",
        },
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert r_sched.status_code == 201
    sched_id = r_sched.json()["id"]

    # 4. Staff creates expired notice
    r_exp = client.post(
        "/api/v1/notifications/staff/notices",
        json={
            "title": "Expired Maintenance Notice",
            "body": "Expired yesterday.",
            "category": "MAINTENANCE",
            "status": "PUBLISHED",
            "published_at": (now - timedelta(days=3)).isoformat(),
            "expires_at": (now - timedelta(days=1)).isoformat(),
            "target_type": "SOCIETY",
        },
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert r_exp.status_code == 201
    exp_id = r_exp.json()["id"]

    # 5. Staff creates notice targeted specifically to Tower 12 (Swati only, not Neeraj)
    r_tow12 = client.post(
        "/api/v1/notifications/staff/notices",
        json={
            "title": "Tower 12 Generator Test Notice",
            "body": "Power disruption in Tower 12 only.",
            "category": "MAINTENANCE",
            "status": "PUBLISHED",
            "target_type": "TOWER",
            "target_tower_id": tower_12_id,
        },
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert r_tow12.status_code == 201
    tow12_id = r_tow12.json()["id"]

    # 6. Staff creates notice targeted specifically to Flat 0408 (Swati only, not Neeraj)
    r_flat0408 = client.post(
        "/api/v1/notifications/staff/notices",
        json={
            "title": "Flat 0408 Balcony Repair Advisory",
            "body": "Private to Flat 0408 resident.",
            "category": "GENERAL",
            "status": "PUBLISHED",
            "target_type": "FLAT",
            "target_flat_id": flat_0408_id,
        },
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert r_flat0408.status_code == 201
    flat0408_id = r_flat0408.json()["id"]

    # --- IDOR & Status Access Control: Neeraj Attempts Access ---
    # Neeraj belongs to Tower 7, Flat 1203. None of these 6 notices should be accessible.
    forbidden_ids = [draft_id, arch_id, sched_id, exp_id, tow12_id, flat0408_id]

    for n_id in forbidden_ids:
        # GET /resident/notices/{id} must reject with 404
        get_res = client.get(
            f"/api/v1/notifications/resident/notices/{n_id}",
            headers=RESIDENT_NEERAJ_HEADERS,
        )
        assert get_res.status_code == 404, f"Neeraj must not access notice {n_id}"

        # PATCH /resident/notices/{id}/read must reject with 404
        read_res = client.patch(
            f"/api/v1/notifications/resident/notices/{n_id}/read",
            headers=RESIDENT_NEERAJ_HEADERS,
        )
        assert read_res.status_code == 404, f"Neeraj must not mark notice {n_id} as read"

    # --- Swati Access: Belongs to Tower 12, Flat 0408 ---
    # Swati MUST be able to access Tower 12 and Flat 0408 notices
    swati_tow_res = client.get(
        f"/api/v1/notifications/resident/notices/{tow12_id}",
        headers=RESIDENT_SWATI_HEADERS,
    )
    assert swati_tow_res.status_code == 200
    assert swati_tow_res.json()["title"] == "Tower 12 Generator Test Notice"

    swati_flat_res = client.get(
        f"/api/v1/notifications/resident/notices/{flat0408_id}",
        headers=RESIDENT_SWATI_HEADERS,
    )
    assert swati_flat_res.status_code == 200
    assert swati_flat_res.json()["title"] == "Flat 0408 Balcony Repair Advisory"

    swati_read_res = client.patch(
        f"/api/v1/notifications/resident/notices/{flat0408_id}/read",
        headers=RESIDENT_SWATI_HEADERS,
    )
    assert swati_read_res.status_code == 200
    assert swati_read_res.json()["status"] == "success"

    # But Swati still CANNOT access draft, archived, scheduled, or expired notices
    for n_id in [draft_id, arch_id, sched_id, exp_id]:
        assert (
            client.get(
                f"/api/v1/notifications/resident/notices/{n_id}",
                headers=RESIDENT_SWATI_HEADERS,
            ).status_code
            == 404
        )

    # --- Staff Can Still View All Society Notices via Staff Endpoint ---
    assert (
        client.get(
            f"/api/v1/notifications/staff/notices/{draft_id}",
            headers=STAFF_HELPDESK_HEADERS,
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/notifications/staff/notices/{arch_id}",
            headers=STAFF_HELPDESK_HEADERS,
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/notifications/staff/notices/{sched_id}",
            headers=STAFF_HELPDESK_HEADERS,
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/notifications/staff/notices/{tow12_id}",
            headers=STAFF_HELPDESK_HEADERS,
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/notifications/staff/notices/{flat0408_id}",
            headers=STAFF_HELPDESK_HEADERS,
        ).status_code
        == 200
    )


def test_gate_only_staff_forbidden_from_notice_mutations_api(
    client: TestClient, db_session: Session
) -> None:
    # 1. First, create a notice using authorized helpdesk (possesses COMMUNICATIONS_MANAGE)
    create_res = client.post(
        "/api/v1/notifications/staff/notices",
        json={
            "title": "Township Circular for Granular Auth Test",
            "body": "Official circular body text.",
            "category": "GENERAL",
            "status": "DRAFT",
            "target_type": "SOCIETY",
        },
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert create_res.status_code == 201
    notice_id = create_res.json()["id"]

    # 2. Configure a gate operator who has RoleType.HELPDESK and ONLY Permission.GATE_OPERATIONS
    gate_guard_id = uuid.uuid4()
    gate_claims = CurrentUserClaims(
        user_id=gate_guard_id,
        supabase_uid=uuid.uuid4(),
        email="gate.security.guard@example.com",
        phone="+91-98765-99999",
        full_name="Gate Security Guard",
        roles=[RoleType.HELPDESK],
        permissions=[Permission.GATE_OPERATIONS],
        society_ids=[uuid.UUID(SOCIETY_PUNE_ID)],
        active_flat_ids=[],
        is_mock=True,
    )

    app.dependency_overrides[get_current_user] = lambda: gate_claims
    try:
        # A. Gate operator attempts to CREATE a notice -> must receive HTTP 403 Forbidden
        post_res = client.post(
            f"/api/v1/notifications/staff/notices?society_id={SOCIETY_PUNE_ID}",
            json={
                "title": "Unauthorized Guard Notice",
                "body": "Guards must not publish circulars.",
                "category": "GENERAL",
                "status": "DRAFT",
            },
        )
        assert post_res.status_code == 403
        assert (
            post_res.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"
            or "COMMUNICATIONS_MANAGE" in post_res.text
        )

        # B. Gate operator attempts to EDIT a notice -> must receive HTTP 403 Forbidden
        put_res = client.put(
            f"/api/v1/notifications/staff/notices/{notice_id}?society_id={SOCIETY_PUNE_ID}",
            json={"title": "Rogue Edit by Guard"},
        )
        assert put_res.status_code == 403

        # C. Gate operator attempts to PUBLISH a notice -> must receive HTTP 403 Forbidden
        pub_res = client.post(
            f"/api/v1/notifications/staff/notices/{notice_id}/publish?society_id={SOCIETY_PUNE_ID}"
        )
        assert pub_res.status_code == 403

        # D. Gate operator attempts to ARCHIVE a notice -> must receive HTTP 403 Forbidden
        arch_res = client.post(
            f"/api/v1/notifications/staff/notices/{notice_id}/archive?society_id={SOCIETY_PUNE_ID}"
        )
        assert arch_res.status_code == 403

        # E. Gate operator WITHOUT COMMUNICATIONS_MANAGE receives 403 on staff notice inspection
        list_res = client.get(f"/api/v1/notifications/staff/notices?society_id={SOCIETY_PUNE_ID}")
        assert list_res.status_code == 403

        detail_res = client.get(
            f"/api/v1/notifications/staff/notices/{notice_id}?society_id={SOCIETY_PUNE_ID}"
        )
        assert detail_res.status_code == 403

        overview_res = client.get(
            f"/api/v1/notifications/staff/notices/overview?society_id={SOCIETY_PUNE_ID}"
        )
        assert overview_res.status_code == 403

        targeting_res = client.get(
            f"/api/v1/notifications/staff/targeting-options?society_id={SOCIETY_PUNE_ID}"
        )
        assert targeting_res.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    # 3. Verify that authorized helpdesk operator CAN publish and archive the notice
    auth_pub_res = client.post(
        f"/api/v1/notifications/staff/notices/{notice_id}/publish?society_id={SOCIETY_PUNE_ID}",
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert auth_pub_res.status_code == 200
    assert auth_pub_res.json()["status"] == "PUBLISHED"

    auth_arch_res = client.post(
        f"/api/v1/notifications/staff/notices/{notice_id}/archive?society_id={SOCIETY_PUNE_ID}",
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert auth_arch_res.status_code == 200
    assert auth_arch_res.json()["status"] == "ARCHIVED"


def test_future_scheduled_emergency_notice_api_not_delivered_early(
    client: TestClient, db_session: Session
) -> None:
    """API Verification: Future scheduled emergency notices must NOT be delivered to resident inboxes early."""
    future_time = (datetime.now(UTC) + timedelta(days=2)).isoformat()

    # Staff creates a scheduled emergency notice for 2 days in the future
    create_res = client.post(
        "/api/v1/notifications/staff/notices",
        json={
            "title": "SCHEDULED SUBSTATION OVERHAUL",
            "body": "Substation maintenance in 2 days. Power will be on backup generators.",
            "category": "EMERGENCY",
            "priority": "URGENT",
            "status": "PUBLISHED",
            "published_at": future_time,
            "target_type": "SOCIETY",
            "deliver_emergency": True,
            "confirm_emergency_broadcast": True,
        },
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert create_res.status_code == 201
    notice_id = create_res.json()["id"]

    # 1. Resident notices feed MUST NOT display future notice
    feed_res = client.get(
        "/api/v1/notifications/resident/notices",
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert feed_res.status_code == 200
    feed_ids = [n["id"] for n in feed_res.json()["items"]]
    assert notice_id not in feed_ids

    # 2. Resident personal notification inbox MUST NOT have early emergency notification
    inbox_res = client.get(
        "/api/v1/notifications/me",
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert inbox_res.status_code == 200
    inbox_items = inbox_res.json()["items"]
    early_items = [it for it in inbox_items if "SCHEDULED SUBSTATION OVERHAUL" in it["title"]]
    assert len(early_items) == 0, "Future scheduled emergency notice must not be delivered early"


def test_repeated_publish_requests_api_idempotency(client: TestClient, db_session: Session) -> None:
    """API Verification: Repeated publish requests on an already published notice are idempotent."""
    from app.domains.reliability.models import OutboxEvent

    # 1. Staff creates draft notice
    create_res = client.post(
        "/api/v1/notifications/staff/notices",
        json={
            "title": "Township General Circular",
            "body": "Upcoming society garden cleaning drive.",
            "category": "CIRCULAR",
            "priority": "NORMAL",
            "status": "DRAFT",
            "target_type": "SOCIETY",
        },
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert create_res.status_code == 201
    notice_id = create_res.json()["id"]

    # 2. First publish call
    pub_1 = client.post(
        f"/api/v1/notifications/staff/notices/{notice_id}/publish?society_id={SOCIETY_PUNE_ID}",
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert pub_1.status_code == 200
    assert pub_1.json()["status"] == "PUBLISHED"

    outbox_count_1 = len(
        list(
            db_session.scalars(
                select(OutboxEvent).where(
                    OutboxEvent.aggregate_id == notice_id,
                    OutboxEvent.event_type == "notice.published",
                )
            ).all()
        )
    )
    assert outbox_count_1 == 1

    # 3. Second publish call (repeated request / double-click)
    pub_2 = client.post(
        f"/api/v1/notifications/staff/notices/{notice_id}/publish?society_id={SOCIETY_PUNE_ID}",
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert pub_2.status_code == 200
    assert pub_2.json()["status"] == "PUBLISHED"

    # Outbox count MUST NOT increase
    outbox_count_2 = len(
        list(
            db_session.scalars(
                select(OutboxEvent).where(
                    OutboxEvent.aggregate_id == notice_id,
                    OutboxEvent.event_type == "notice.published",
                )
            ).all()
        )
    )
    assert outbox_count_2 == 1, "Repeated publish request must NOT create additional outbox events"

    # 4. Attempting to publish an ARCHIVED notice should fail with 400
    arch_res = client.post(
        f"/api/v1/notifications/staff/notices/{notice_id}/archive?society_id={SOCIETY_PUNE_ID}",
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert arch_res.status_code == 200

    pub_arch = client.post(
        f"/api/v1/notifications/staff/notices/{notice_id}/publish?society_id={SOCIETY_PUNE_ID}",
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert pub_arch.status_code == 400
    assert pub_arch.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


def test_dynamic_targeting_options_endpoints(client: TestClient, db_session: Session) -> None:
    """Verifies that staff can dynamically query society towers and flats for notice targeting."""
    # 1. Combined targeting options
    res_opts = client.get(
        f"/api/v1/notifications/staff/targeting-options?society_id={SOCIETY_PUNE_ID}",
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert res_opts.status_code == 200
    data = res_opts.json()
    assert "towers" in data and "flats" in data
    assert len(data["towers"]) >= 3
    assert any(t["id"] == str(TOWER_T07_ID) for t in data["towers"])
    assert any(t["id"] == str(TOWER_T12_ID) for t in data["towers"])

    # 2. Towers list endpoint
    res_towers = client.get(
        f"/api/v1/notifications/staff/towers?society_id={SOCIETY_PUNE_ID}",
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert res_towers.status_code == 200
    towers = res_towers.json()
    assert isinstance(towers, list)
    tower_nums = [t["tower_number"] for t in towers]
    assert "T07" in tower_nums

    # 3. Flats list endpoint
    res_flats = client.get(
        f"/api/v1/notifications/staff/flats?society_id={SOCIETY_PUNE_ID}",
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert res_flats.status_code == 200
    flats = res_flats.json()
    assert isinstance(flats, list)
    assert any(f["id"] == str(FLAT_1203_ID) for f in flats)


def test_multi_tower_and_multi_flat_targeting_api_and_society_validation(
    client: TestClient, db_session: Session
) -> None:
    """Verifies multi-tower / multi-flat creation via REST API and validates society membership of targets."""
    # 1. Foreign tower validation
    foreign_tower_uuid = str(uuid.uuid4())
    res_bad_tower = client.post(
        f"/api/v1/notifications/staff/notices?society_id={SOCIETY_PUNE_ID}",
        json={
            "title": "Invalid Tower Notice",
            "body": "Should fail because tower does not belong to society.",
            "category": "MAINTENANCE",
            "priority": "NORMAL",
            "status": "PUBLISHED",
            "target_type": "TOWER",
            "target_tower_ids": [str(TOWER_T07_ID), foreign_tower_uuid],
        },
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert res_bad_tower.status_code == 404
    assert "not found in this society" in res_bad_tower.json()["error"]["message"]

    # 2. Valid multi-tower notice (T07 and T12)
    res_multi_tower = client.post(
        f"/api/v1/notifications/staff/notices?society_id={SOCIETY_PUNE_ID}",
        json={
            "title": "Water Tank Cleaning: Towers 7 and 12",
            "body": "Water supply suspended from 10 AM to 2 PM.",
            "category": "MAINTENANCE",
            "priority": "HIGH",
            "status": "PUBLISHED",
            "target_type": "TOWER",
            "target_tower_ids": [str(TOWER_T07_ID), str(TOWER_T12_ID)],
        },
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert res_multi_tower.status_code == 201
    notice_data = res_multi_tower.json()
    assert len(notice_data["target_tower_ids"]) == 2
    assert str(TOWER_T07_ID) in notice_data["target_tower_ids"]
    assert str(TOWER_T12_ID) in notice_data["target_tower_ids"]
    assert len(notice_data["target_tower_names"]) == 2

    # Resident Neeraj in Tower 7 (Flat 1203) can see this notice
    res_feed = client.get(
        f"/api/v1/notifications/resident/notices?society_id={SOCIETY_PUNE_ID}",
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert res_feed.status_code == 200
    feed_items = res_feed.json()["items"]
    assert any(n["id"] == notice_data["id"] for n in feed_items)

    # 3. Valid multi-flat notice (Flat 1203 and Flat 0408)
    res_multi_flat = client.post(
        f"/api/v1/notifications/staff/notices?society_id={SOCIETY_PUNE_ID}",
        json={
            "title": "Balcony Grouting Advisory for Selected Flats",
            "body": "Technicians will visit Flats 1203 and 0408 tomorrow.",
            "category": "MAINTENANCE",
            "priority": "NORMAL",
            "status": "PUBLISHED",
            "target_type": "FLAT",
            "target_flat_ids": [str(FLAT_1203_ID), str(FLAT_0408_ID)],
        },
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert res_multi_flat.status_code == 201
    flat_notice_data = res_multi_flat.json()
    assert len(flat_notice_data["target_flat_ids"]) == 2
    assert str(FLAT_1203_ID) in flat_notice_data["target_flat_ids"]
    assert str(FLAT_0408_ID) in flat_notice_data["target_flat_ids"]
    assert "1203" in flat_notice_data["target_flat_numbers"]
    assert "0408" in flat_notice_data["target_flat_numbers"]


def test_staff_overview_and_publish_scheduled_endpoints(client: TestClient) -> None:
    """Verifies GET /staff/notices/overview and POST /staff/notices/publish-scheduled."""
    # 1. Overview metrics
    res_overview = client.get(
        f"/api/v1/notifications/staff/notices/overview?society_id={SOCIETY_PUNE_ID}",
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert res_overview.status_code == 200
    data = res_overview.json()
    assert "total" in data
    assert "published" in data
    assert "scheduled" in data
    assert "draft" in data
    assert "archived" in data
    assert "emergency" in data
    assert isinstance(data["total"], int)

    # 2. Publish scheduled notices
    res_publish_sched = client.post(
        f"/api/v1/notifications/staff/notices/publish-scheduled?society_id={SOCIETY_PUNE_ID}",
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert res_publish_sched.status_code == 200
    assert isinstance(res_publish_sched.json(), list)


def test_resident_unread_count_endpoint(client: TestClient) -> None:
    """Verifies GET /resident/notices/unread-count."""
    res = client.get(
        f"/api/v1/notifications/resident/notices/unread-count?society_id={SOCIETY_PUNE_ID}",
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert res.status_code == 200
    data = res.json()
    assert "unread_count" in data
    assert isinstance(data["unread_count"], int)
    assert data["unread_count"] >= 0


def test_scheduled_status_and_version_api(client: TestClient) -> None:
    """Verifies notice versioning and SCHEDULED status creation through REST API."""
    future_time = (datetime.now(UTC) + timedelta(days=3)).isoformat()

    res = client.post(
        f"/api/v1/notifications/staff/notices?society_id={SOCIETY_PUNE_ID}",
        json={
            "title": "Township Independence Day Celebration",
            "body": "Flag hoisting ceremony and sports day at clubhouse.",
            "category": "EVENT",
            "priority": "NORMAL",
            "status": "SCHEDULED",
            "published_at": future_time,
            "target_type": "SOCIETY",
        },
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert res.status_code == 201
    notice = res.json()
    assert notice["status"] == "SCHEDULED"
    assert notice["version"] == 1

    # Update increments version
    update_res = client.put(
        f"/api/v1/notifications/staff/notices/{notice['id']}?society_id={SOCIETY_PUNE_ID}",
        json={
            "title": "Township Independence Day Celebration (Updated Schedule)",
            "body": "Updated: Flag hoisting ceremony starts at 8:30 AM.",
        },
        headers=STAFF_HELPDESK_HEADERS,
    )
    assert update_res.status_code == 200
    assert update_res.json()["version"] == 2


def test_expanded_categories_api(client: TestClient) -> None:
    """Verifies that WATER, ELECTRICITY, and SECURITY categories are supported by API."""
    for category in ["WATER", "ELECTRICITY", "SECURITY"]:
        res = client.post(
            f"/api/v1/notifications/staff/notices?society_id={SOCIETY_PUNE_ID}",
            json={
                "title": f"API Test for {category}",
                "body": f"Testing expanded notice category {category}.",
                "category": category,
                "priority": "NORMAL",
                "status": "DRAFT",
                "target_type": "SOCIETY",
            },
            headers=STAFF_HELPDESK_HEADERS,
        )
        assert res.status_code == 201
        assert res.json()["category"] == category
