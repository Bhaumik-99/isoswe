"""Unit & Integration Tests for Official Township Notices Domain Service"""

import uuid
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.identity.models import (
    Flat,
    FlatMembership,
    FlatStatus,
    MembershipStatus,
    MembershipType,
    Society,
    SocietyStatus,
    Tower,
    User,
    UserStatus,
)
from app.domains.notifications.models import (
    NoticeCategory,
    NoticePriority,
    NoticeStatus,
    NoticeTargetType,
    Notification,
)
from app.domains.notifications.notice_service import NoticeService, utc_now
from app.domains.notifications.schemas import (
    CreateNoticeRequest,
    UpdateNoticeRequest,
)
from app.domains.reliability.models import AuditEvent, OutboxEvent


@pytest.fixture
def notice_test_setup(db_session: Session) -> dict[str, Any]:
    soc_id = uuid.uuid4()
    soc = Society(id=soc_id, name="Notice Test Society", status=SocietyStatus.ACTIVE)
    db_session.add(soc)

    tow1_id = uuid.uuid4()
    tow1 = Tower(id=tow1_id, society_id=soc_id, tower_number="T1", name="Tower 1")
    tow2_id = uuid.uuid4()
    tow2 = Tower(id=tow2_id, society_id=soc_id, tower_number="T2", name="Tower 2")
    db_session.add_all([tow1, tow2])

    flat1_id = uuid.uuid4()
    flat1 = Flat(
        id=flat1_id,
        society_id=soc_id,
        tower_id=tow1_id,
        flat_number="101",
        area_sqft=1200,
        status=FlatStatus.OCCUPIED,
    )
    flat2_id = uuid.uuid4()
    flat2 = Flat(
        id=flat2_id,
        society_id=soc_id,
        tower_id=tow2_id,
        flat_number="201",
        area_sqft=1200,
        status=FlatStatus.OCCUPIED,
    )
    db_session.add_all([flat1, flat2])

    # Staff user
    staff_id = uuid.uuid4()
    staff = User(
        id=staff_id,
        supabase_uid=uuid.uuid4(),
        email="staff@notices.example.com",
        phone="+919800000001",
        full_name="Staff Operator",
        status=UserStatus.ACTIVE,
    )

    # Resident 1 (Flat 101, Tower 1)
    res1_id = uuid.uuid4()
    res1 = User(
        id=res1_id,
        supabase_uid=uuid.uuid4(),
        email="res1@notices.example.com",
        phone="+919800000002",
        full_name="Resident One",
        status=UserStatus.ACTIVE,
    )

    # Resident 2 (Flat 201, Tower 2)
    res2_id = uuid.uuid4()
    res2 = User(
        id=res2_id,
        supabase_uid=uuid.uuid4(),
        email="res2@notices.example.com",
        phone="+919800000003",
        full_name="Resident Two",
        status=UserStatus.ACTIVE,
    )
    db_session.add_all([staff, res1, res2])

    now = utc_now()
    mem1 = FlatMembership(
        id=uuid.uuid4(),
        society_id=soc_id,
        flat_id=flat1_id,
        user_id=res1_id,
        membership_type=MembershipType.OWNER,
        status=MembershipStatus.APPROVED,
        valid_from=now - timedelta(days=1),
    )
    mem2 = FlatMembership(
        id=uuid.uuid4(),
        society_id=soc_id,
        flat_id=flat2_id,
        user_id=res2_id,
        membership_type=MembershipType.TENANT,
        status=MembershipStatus.APPROVED,
        valid_from=now - timedelta(days=1),
    )
    db_session.add_all([mem1, mem2])
    db_session.commit()

    return {
        "society_id": soc_id,
        "tow1_id": tow1_id,
        "tow2_id": tow2_id,
        "flat1_id": flat1_id,
        "flat2_id": flat2_id,
        "staff_id": staff_id,
        "res1_id": res1_id,
        "res2_id": res2_id,
    }


def test_staff_create_and_publish_notice(
    db_session: Session, notice_test_setup: dict[str, Any]
) -> None:
    svc = NoticeService(db_session)
    soc_id = notice_test_setup["society_id"]
    staff_id = notice_test_setup["staff_id"]

    # 1. Create Draft
    create_req = CreateNoticeRequest(
        title="Annual General Meeting Circular",
        body="Notice is hereby given that the AGM will be held on the 25th of this month.",
        category=NoticeCategory.CIRCULAR,
        priority=NoticePriority.HIGH,
        status=NoticeStatus.DRAFT,
        target_type=NoticeTargetType.SOCIETY,
        is_pinned=True,
    )
    notice = svc.create_notice(society_id=soc_id, author_id=staff_id, req=create_req)
    assert notice.title == "Annual General Meeting Circular"
    assert notice.status == NoticeStatus.DRAFT
    assert notice.is_pinned is True
    assert notice.category == NoticeCategory.CIRCULAR

    # Check Audit log
    audit = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.resource_id == str(notice.id),
            AuditEvent.action == "NOTICE_CREATED",
        )
    ).first()
    assert audit is not None
    assert audit.event_metadata["title"] == "Annual General Meeting Circular"

    # 2. Publish Notice
    published = svc.publish_notice(society_id=soc_id, actor_id=staff_id, notice_id=notice.id)
    assert published.status == NoticeStatus.PUBLISHED
    assert published.published_at is not None

    # Check Publish Audit log & Outbox event
    pub_audit = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.resource_id == str(notice.id),
            AuditEvent.action == "NOTICE_PUBLISHED",
        )
    ).first()
    assert pub_audit is not None

    outbox = db_session.scalars(
        select(OutboxEvent).where(
            OutboxEvent.aggregate_id == str(notice.id),
            OutboxEvent.event_type == "notice.published",
        )
    ).first()
    assert outbox is not None


def test_staff_edit_and_archive_notice(
    db_session: Session, notice_test_setup: dict[str, Any]
) -> None:
    svc = NoticeService(db_session)
    soc_id = notice_test_setup["society_id"]
    staff_id = notice_test_setup["staff_id"]

    created = svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="Scheduled Power Cut",
            body="Power cut between 2 PM and 4 PM.",
            category=NoticeCategory.MAINTENANCE,
            priority=NoticePriority.NORMAL,
            status=NoticeStatus.PUBLISHED,
            target_type=NoticeTargetType.SOCIETY,
        ),
    )
    assert created.status == NoticeStatus.PUBLISHED

    # Edit notice
    updated = svc.update_notice(
        society_id=soc_id,
        actor_id=staff_id,
        notice_id=created.id,
        req=UpdateNoticeRequest(
            title="Scheduled Power Cut - Rescheduled",
            body="Power cut rescheduled to 4 PM - 6 PM.",
            priority=NoticePriority.HIGH,
        ),
    )
    assert updated.title == "Scheduled Power Cut - Rescheduled"
    assert updated.priority == NoticePriority.HIGH

    # Archive notice
    archived = svc.archive_notice(society_id=soc_id, actor_id=staff_id, notice_id=created.id)
    assert archived.status == NoticeStatus.ARCHIVED

    arch_audit = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.resource_id == str(created.id),
            AuditEvent.action == "NOTICE_ARCHIVED",
        )
    ).first()
    assert arch_audit is not None


def test_targeting_by_tower_and_flat(
    db_session: Session, notice_test_setup: dict[str, Any]
) -> None:
    svc = NoticeService(db_session)
    soc_id = notice_test_setup["society_id"]
    staff_id = notice_test_setup["staff_id"]
    tow1_id = notice_test_setup["tow1_id"]
    flat2_id = notice_test_setup["flat2_id"]
    res1_id = notice_test_setup["res1_id"]
    res2_id = notice_test_setup["res2_id"]

    # Notice 1: Society-wide
    n_soc = svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="Society Garden Maintenance",
            body="Garden will be closed.",
            status=NoticeStatus.PUBLISHED,
            target_type=NoticeTargetType.SOCIETY,
        ),
    )

    # Notice 2: Tower 1 only
    n_tow1 = svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="Tower 1 Lift Modernization",
            body="Lift 1 will be serviced.",
            status=NoticeStatus.PUBLISHED,
            target_type=NoticeTargetType.TOWER,
            target_tower_id=tow1_id,
        ),
    )

    # Notice 3: Flat 201 (Resident 2) only
    n_flat2 = svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="Water Meter Inspection for 201",
            body="Plumber visit tomorrow.",
            status=NoticeStatus.PUBLISHED,
            target_type=NoticeTargetType.FLAT,
            target_flat_id=flat2_id,
        ),
    )

    # Resident 1 feed (in Tower 1, Flat 101)
    res1_feed = svc.list_resident_notices(society_id=soc_id, user_id=res1_id)
    res1_ids = [n.id for n in res1_feed.items]
    assert n_soc.id in res1_ids
    assert n_tow1.id in res1_ids
    assert n_flat2.id not in res1_ids, "Resident 1 must NOT see Flat 201 private notice"

    # Resident 2 feed (in Tower 2, Flat 201)
    res2_feed = svc.list_resident_notices(society_id=soc_id, user_id=res2_id)
    res2_ids = [n.id for n in res2_feed.items]
    assert n_soc.id in res2_ids
    assert n_tow1.id not in res2_ids, "Resident 2 must NOT see Tower 1 notice"
    assert n_flat2.id in res2_ids, "Resident 2 must see Flat 201 notice"


def test_scheduled_publishing_expiry_and_pinning(
    db_session: Session, notice_test_setup: dict[str, Any]
) -> None:
    svc = NoticeService(db_session)
    soc_id = notice_test_setup["society_id"]
    staff_id = notice_test_setup["staff_id"]
    res1_id = notice_test_setup["res1_id"]

    now = utc_now()

    # 1. Scheduled notice for future
    svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="Future Maintenance Alert",
            body="Will happen next week.",
            status=NoticeStatus.PUBLISHED,
            published_at=now + timedelta(days=2),
            target_type=NoticeTargetType.SOCIETY,
        ),
    )

    # 2. Expired notice
    svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="Old Past Notice",
            body="Expired yesterday.",
            status=NoticeStatus.PUBLISHED,
            published_at=now - timedelta(days=5),
            expires_at=now - timedelta(days=1),
            target_type=NoticeTargetType.SOCIETY,
        ),
    )

    # 3. Normal Active notice
    n_normal = svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="Regular Society Update",
            body="Regular update.",
            status=NoticeStatus.PUBLISHED,
            published_at=now - timedelta(hours=2),
            is_pinned=False,
            target_type=NoticeTargetType.SOCIETY,
        ),
    )

    # 4. Pinned Notice (created earlier but pinned)
    n_pinned = svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="CRITICAL: Clubhouse Rules",
            body="Always wear shoes.",
            status=NoticeStatus.PUBLISHED,
            published_at=now - timedelta(hours=5),
            is_pinned=True,
            target_type=NoticeTargetType.SOCIETY,
        ),
    )

    feed = svc.list_resident_notices(society_id=soc_id, user_id=res1_id)
    titles = [n.title for n in feed.items]

    # Future scheduled notice and expired notice must NOT be present
    assert "Future Maintenance Alert" not in titles
    assert "Old Past Notice" not in titles

    # Pinned notice must appear first
    assert titles[0] == "CRITICAL: Clubhouse Rules"
    assert feed.items[0].id == n_pinned.id
    assert feed.items[1].id == n_normal.id


def test_resident_read_unread_tracking_and_mark_all_read(
    db_session: Session, notice_test_setup: dict[str, Any]
) -> None:
    svc = NoticeService(db_session)
    soc_id = notice_test_setup["society_id"]
    staff_id = notice_test_setup["staff_id"]
    res1_id = notice_test_setup["res1_id"]

    n1 = svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="Notice 1",
            body="Body 1",
            status=NoticeStatus.PUBLISHED,
            target_type=NoticeTargetType.SOCIETY,
        ),
    )
    n2 = svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="Notice 2",
            body="Body 2",
            status=NoticeStatus.PUBLISHED,
            target_type=NoticeTargetType.SOCIETY,
        ),
    )

    # Initially both are unread
    feed = svc.list_resident_notices(society_id=soc_id, user_id=res1_id)
    assert feed.unread_count == 2
    assert all(not item.is_read for item in feed.items)

    # Mark notice 1 as read
    res = svc.mark_notice_read(society_id=soc_id, user_id=res1_id, notice_id=n1.id)
    assert res.status == "success"

    # Now unread count is 1
    feed_after = svc.list_resident_notices(society_id=soc_id, user_id=res1_id)
    assert feed_after.unread_count == 1
    item_map = {item.id: item for item in feed_after.items}
    assert item_map[n1.id].is_read is True
    assert item_map[n2.id].is_read is False

    # Filter by unread_only
    unread_feed = svc.list_resident_notices(society_id=soc_id, user_id=res1_id, unread_only=True)
    assert len(unread_feed.items) == 1
    assert unread_feed.items[0].id == n2.id

    # Mark all notices read
    all_read_res = svc.mark_all_notices_read(society_id=soc_id, user_id=res1_id)
    assert all_read_res.marked_count == 1

    feed_all = svc.list_resident_notices(society_id=soc_id, user_id=res1_id)
    assert feed_all.unread_count == 0
    assert all(item.is_read for item in feed_all.items)


def test_emergency_notice_delivery_via_existing_infrastructure(
    db_session: Session, notice_test_setup: dict[str, Any]
) -> None:
    svc = NoticeService(db_session)
    soc_id = notice_test_setup["society_id"]
    staff_id = notice_test_setup["staff_id"]
    tow1_id = notice_test_setup["tow1_id"]
    res1_id = notice_test_setup["res1_id"]
    res2_id = notice_test_setup["res2_id"]

    # Create emergency announcement targeted to Tower 1
    emergency_req = CreateNoticeRequest(
        title="GAS LEAK ALERT IN TOWER 1",
        body="Immediate evacuation of Tower 1 required. Emergency services dispatched.",
        category=NoticeCategory.EMERGENCY,
        priority=NoticePriority.URGENT,
        status=NoticeStatus.PUBLISHED,
        target_type=NoticeTargetType.TOWER,
        target_tower_id=tow1_id,
        deliver_emergency=True,
    )
    notice = svc.create_notice(society_id=soc_id, author_id=staff_id, req=emergency_req)

    # Check that in-app notification was generated for Resident 1 (Tower 1)
    notifs_r1 = list(
        db_session.scalars(
            select(Notification).where(
                Notification.recipient_user_id == res1_id,
                Notification.event_type == "notice.emergency",
            )
        ).all()
    )
    assert len(notifs_r1) == 1
    assert "GAS LEAK ALERT" in notifs_r1[0].title
    assert notifs_r1[0].action_url == "/resident/notices"

    # Check that Resident 2 (Tower 2) did NOT receive the notification
    notifs_r2 = list(
        db_session.scalars(
            select(Notification).where(
                Notification.recipient_user_id == res2_id,
                Notification.event_type == "notice.emergency",
            )
        ).all()
    )
    assert len(notifs_r2) == 0

    # Check Outbox Event for emergency broadcast
    outbox = db_session.scalars(
        select(OutboxEvent).where(
            OutboxEvent.aggregate_id == str(notice.id),
            OutboxEvent.event_type == "notice.emergency_broadcast",
        )
    ).first()
    assert outbox is not None
    assert outbox.payload["recipients_count"] == 1
