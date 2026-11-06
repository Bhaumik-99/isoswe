"""API Tests for Notifications and Resident Communication

Tests all endpoints under /api/v1/notifications:
- GET /me
- GET /me/unread-count
- PATCH /me/{id}/read
- PATCH /me/read-all
- GET /me/preferences
- PUT /me/preferences
- GET /staff/overview
- IDOR isolation between users
- Role-based authorization for staff overview
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.notifications.models import (
    Notification,
    NotificationChannel,
    NotificationPriority,
)

RESIDENT_NEERAJ_HEADERS = {"X-Dev-User": "neeraj"}
RESIDENT_SWATI_HEADERS = {"X-Dev-User": "swati"}
STAFF_HELPDESK_HEADERS = {"X-Dev-User": "helpdesk"}

SOCIETY_PUNE_ID = "11111111-1111-1111-1111-111111111111"
NEERAJ_USER_ID = "44444444-4444-4444-4444-444444440001"
SWATI_USER_ID = "44444444-4444-4444-4444-444444440002"


def test_get_my_notifications_empty(client: TestClient) -> None:
    resp = client.get("/api/v1/notifications/me", headers=RESIDENT_NEERAJ_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["unread_count"] == 0


def test_notification_inbox_pagination_and_unread_filter(
    client: TestClient, db_session: Session
) -> None:
    society_id = uuid.UUID(SOCIETY_PUNE_ID)
    user_id = uuid.UUID(NEERAJ_USER_ID)
    now = datetime.now(UTC)

    # Seed 3 notifications: 2 unread, 1 read
    n1 = Notification(
        id=uuid.uuid4(),
        society_id=society_id,
        recipient_user_id=user_id,
        event_type="billing.invoice_generated",
        title="Invoice #1",
        body="Invoice 1 is ready",
        channel=NotificationChannel.IN_APP,
        priority=NotificationPriority.NORMAL,
        read_at=None,
        created_at=now - timedelta(minutes=10),
        updated_at=now - timedelta(minutes=10),
    )
    n2 = Notification(
        id=uuid.uuid4(),
        society_id=society_id,
        recipient_user_id=user_id,
        event_type="visitor.approval_requested",
        title="Visitor Arrived",
        body="Delivery person at gate",
        channel=NotificationChannel.IN_APP,
        priority=NotificationPriority.HIGH,
        read_at=None,
        created_at=now - timedelta(minutes=5),
        updated_at=now - timedelta(minutes=5),
    )
    n3 = Notification(
        id=uuid.uuid4(),
        society_id=society_id,
        recipient_user_id=user_id,
        event_type="complaint.resolved",
        title="Ticket Resolved",
        body="Plumbing issue fixed",
        channel=NotificationChannel.IN_APP,
        priority=NotificationPriority.LOW,
        read_at=now - timedelta(minutes=1),
        created_at=now - timedelta(minutes=2),
        updated_at=now - timedelta(minutes=1),
    )
    db_session.add_all([n1, n2, n3])
    db_session.commit()

    # 1. Fetch all items (newest first)
    resp = client.get("/api/v1/notifications/me", headers=RESIDENT_NEERAJ_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert data["unread_count"] == 2
    # Verify newest first: n3, then n2, then n1
    assert data["items"][0]["title"] == "Ticket Resolved"
    assert data["items"][1]["title"] == "Visitor Arrived"
    assert data["items"][2]["title"] == "Invoice #1"

    # 2. Filter unread only
    resp_unread = client.get(
        "/api/v1/notifications/me?unread_only=true", headers=RESIDENT_NEERAJ_HEADERS
    )
    assert resp_unread.status_code == 200
    unread_data = resp_unread.json()
    assert len(unread_data["items"]) == 2
    titles = [item["title"] for item in unread_data["items"]]
    assert "Ticket Resolved" not in titles
    assert "Visitor Arrived" in titles
    assert "Invoice #1" in titles

    # 3. Check unread count endpoint
    resp_count = client.get(
        "/api/v1/notifications/me/unread-count", headers=RESIDENT_NEERAJ_HEADERS
    )
    assert resp_count.status_code == 200
    assert resp_count.json()["unread_count"] == 2


def test_mark_single_notification_read_and_idor_protection(
    client: TestClient, db_session: Session
) -> None:
    society_id = uuid.UUID(SOCIETY_PUNE_ID)
    neeraj_id = uuid.UUID(NEERAJ_USER_ID)
    now = datetime.now(UTC)

    # Seed notification belonging to Neeraj
    neeraj_notif = Notification(
        id=uuid.uuid4(),
        society_id=society_id,
        recipient_user_id=neeraj_id,
        event_type="billing.invoice_generated",
        title="Neeraj Private Invoice",
        body="Private invoice details",
        channel=NotificationChannel.IN_APP,
        priority=NotificationPriority.NORMAL,
        read_at=None,
        created_at=now,
        updated_at=now,
    )
    db_session.add(neeraj_notif)
    db_session.commit()

    # IDOR Security Check: Swati attempts to mark Neeraj's notification as read
    idor_resp = client.patch(
        f"/api/v1/notifications/me/{neeraj_notif.id}/read",
        headers=RESIDENT_SWATI_HEADERS,
    )
    assert idor_resp.status_code in (404, 403)

    # Verify Neeraj's notification is still unread
    db_session.refresh(neeraj_notif)
    assert neeraj_notif.read_at is None

    # Legitimate owner marks it read
    valid_resp = client.patch(
        f"/api/v1/notifications/me/{neeraj_notif.id}/read",
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert valid_resp.status_code == 200
    assert valid_resp.json()["status"] == "success"
    assert valid_resp.json()["read_at"] is not None

    db_session.refresh(neeraj_notif)
    assert neeraj_notif.read_at is not None


def test_mark_all_notifications_as_read(client: TestClient, db_session: Session) -> None:
    society_id = uuid.UUID(SOCIETY_PUNE_ID)
    user_id = uuid.UUID(NEERAJ_USER_ID)
    now = datetime.now(UTC)

    n1 = Notification(
        id=uuid.uuid4(),
        society_id=society_id,
        recipient_user_id=user_id,
        event_type="billing.run_completed",
        title="Billing 1",
        body="Body 1",
        channel=NotificationChannel.IN_APP,
        priority=NotificationPriority.NORMAL,
        read_at=None,
        created_at=now,
        updated_at=now,
    )
    n2 = Notification(
        id=uuid.uuid4(),
        society_id=society_id,
        recipient_user_id=user_id,
        event_type="billing.run_completed",
        title="Billing 2",
        body="Body 2",
        channel=NotificationChannel.IN_APP,
        priority=NotificationPriority.NORMAL,
        read_at=None,
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([n1, n2])
    db_session.commit()

    resp = client.patch("/api/v1/notifications/me/read-all", headers=RESIDENT_NEERAJ_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["marked_count"] >= 2
    assert resp.json()["status"] == "success"

    # Verify unread count is now 0
    resp_count = client.get(
        "/api/v1/notifications/me/unread-count", headers=RESIDENT_NEERAJ_HEADERS
    )
    assert resp_count.status_code == 200
    assert resp_count.json()["unread_count"] == 0


def test_notification_preferences_get_and_update(client: TestClient) -> None:
    # 1. Get default preferences
    get_resp = client.get("/api/v1/notifications/me/preferences", headers=RESIDENT_NEERAJ_HEADERS)
    assert get_resp.status_code == 200
    prefs = get_resp.json()
    assert prefs["email_enabled"] is True
    assert prefs["sms_enabled"] is True
    assert prefs["in_app_enabled"] is True

    # 2. Update preferences
    update_payload = {
        "email_enabled": True,
        "sms_enabled": False,
        "in_app_enabled": True,
        "billing_email": True,
        "billing_sms": False,
        "complaints_email": False,
        "complaints_sms": False,
        "visitor_sms": False,
    }
    put_resp = client.put(
        "/api/v1/notifications/me/preferences",
        json=update_payload,
        headers=RESIDENT_NEERAJ_HEADERS,
    )
    assert put_resp.status_code == 200
    updated = put_resp.json()
    assert updated["sms_enabled"] is False
    assert updated["complaints_email"] is False
    assert updated["visitor_sms"] is False

    # 3. Fetch again to verify persistence
    get_again = client.get("/api/v1/notifications/me/preferences", headers=RESIDENT_NEERAJ_HEADERS)
    assert get_again.status_code == 200
    assert get_again.json()["sms_enabled"] is False
    assert get_again.json()["complaints_email"] is False


def test_staff_notification_overview_rbac(client: TestClient, db_session: Session) -> None:
    # 1. Resident Neeraj attempts to access staff delivery overview -> Forbidden 403
    forbidden_resp = client.get(
        "/api/v1/notifications/staff/overview", headers=RESIDENT_NEERAJ_HEADERS
    )
    assert forbidden_resp.status_code == 403

    # 2. Helpdesk staff Rajesh accesses staff delivery overview -> Allowed 200
    allowed_resp = client.get(
        "/api/v1/notifications/staff/overview", headers=STAFF_HELPDESK_HEADERS
    )
    assert allowed_resp.status_code == 200
    data = allowed_resp.json()
    assert "total" in data
    assert "items" in data
    assert "failed_count" in data
    assert "delivered_count" in data
