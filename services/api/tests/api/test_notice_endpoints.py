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
from sqlalchemy.orm import Session

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
