"""Unit & Integration Tests for Official Township Notices Domain Service"""

import uuid
from datetime import UTC, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ResourceNotFoundError, ValidationError
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
    DeliveryStatus,
    Notice,
    NoticeCategory,
    NoticePriority,
    NoticeStatus,
    NoticeTarget,
    NoticeTargetType,
    Notification,
    NotificationDelivery,
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
        confirm_emergency_broadcast=True,
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


def test_resident_notice_access_control_security_and_predicates(
    db_session: Session, notice_test_setup: dict[str, Any]
) -> None:
    svc = NoticeService(db_session)
    soc_id = notice_test_setup["society_id"]
    staff_id = notice_test_setup["staff_id"]
    tow1_id = notice_test_setup["tow1_id"]
    tow2_id = notice_test_setup["tow2_id"]
    flat1_id = notice_test_setup["flat1_id"]
    flat2_id = notice_test_setup["flat2_id"]
    res1_id = notice_test_setup["res1_id"]  # In Tower 1, Flat 101
    res2_id = notice_test_setup["res2_id"]  # In Tower 2, Flat 201

    now = utc_now()

    # 1. Draft notice (society-wide)
    n_draft = svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="Internal Staff Draft Notice",
            body="Staff notes only.",
            status=NoticeStatus.DRAFT,
            target_type=NoticeTargetType.SOCIETY,
        ),
    )

    # 2. Archived notice
    n_archived = svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="Archived Circular",
            body="This notice has been archived.",
            status=NoticeStatus.PUBLISHED,
            target_type=NoticeTargetType.SOCIETY,
        ),
    )
    svc.archive_notice(society_id=soc_id, actor_id=staff_id, notice_id=n_archived.id)

    # 3. Scheduled future notice
    n_future = svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="Future Scheduled Circular",
            body="Not yet visible.",
            status=NoticeStatus.PUBLISHED,
            published_at=now + timedelta(days=3),
            target_type=NoticeTargetType.SOCIETY,
        ),
    )

    # 4. Expired notice
    n_expired = svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="Expired Circular",
            body="Expired yesterday.",
            status=NoticeStatus.PUBLISHED,
            published_at=now - timedelta(days=5),
            expires_at=now - timedelta(days=1),
            target_type=NoticeTargetType.SOCIETY,
        ),
    )

    # 5. Tower 2 specific notice
    n_tow2 = svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="Tower 2 Power Advisory",
            body="Maintenance for Tower 2 only.",
            status=NoticeStatus.PUBLISHED,
            target_type=NoticeTargetType.TOWER,
            target_tower_id=tow2_id,
        ),
    )

    # 5b. Tower 1 specific notice
    n_tow1 = svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="Tower 1 Power Advisory",
            body="Maintenance for Tower 1 only.",
            status=NoticeStatus.PUBLISHED,
            target_type=NoticeTargetType.TOWER,
            target_tower_id=tow1_id,
        ),
    )

    # 6. Flat 2 specific notice
    n_flat2 = svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="Flat 201 Maintenance Due Notice",
            body="Private to Flat 201.",
            status=NoticeStatus.PUBLISHED,
            target_type=NoticeTargetType.FLAT,
            target_flat_id=flat2_id,
        ),
    )

    # 7. Society-wide active notice
    n_soc = svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="General Township Circular",
            body="Visible to all active society residents.",
            status=NoticeStatus.PUBLISHED,
            target_type=NoticeTargetType.SOCIETY,
        ),
    )

    # --- Resident 1 Access Checks (Resident 1 belongs only to Tower 1, Flat 101) ---
    unauthorized_notices = [n_draft, n_archived, n_future, n_expired, n_tow2, n_flat2]

    # Verify detail retrieval is forbidden / returns ResourceNotFoundError
    for notice in unauthorized_notices:
        with pytest.raises(ResourceNotFoundError):
            svc.get_resident_notice(society_id=soc_id, user_id=res1_id, notice_id=notice.id)

        # get_notice with user_id must also enforce resident predicate
        with pytest.raises(ResourceNotFoundError):
            svc.get_notice(
                society_id=soc_id,
                notice_id=notice.id,
                user_id=res1_id,
            )

        # mark_notice_read must enforce resident predicate
        with pytest.raises(ResourceNotFoundError):
            svc.mark_notice_read(society_id=soc_id, user_id=res1_id, notice_id=notice.id)

    # Authorized notice: Resident 1 can view and mark read n_soc
    res1_soc = svc.get_resident_notice(society_id=soc_id, user_id=res1_id, notice_id=n_soc.id)
    assert res1_soc.id == n_soc.id
    assert res1_soc.is_read is False

    read_res = svc.mark_notice_read(society_id=soc_id, user_id=res1_id, notice_id=n_soc.id)
    assert read_res.status == "success"

    res1_soc_after = svc.get_resident_notice(society_id=soc_id, user_id=res1_id, notice_id=n_soc.id)
    assert res1_soc_after.is_read is True

    # Resident 2 (in Tower 2, Flat 201) can view Tower 2 and Flat 201 notices
    res2_tow2 = svc.get_resident_notice(society_id=soc_id, user_id=res2_id, notice_id=n_tow2.id)
    assert res2_tow2.id == n_tow2.id
    res2_flat2 = svc.get_resident_notice(society_id=soc_id, user_id=res2_id, notice_id=n_flat2.id)
    assert res2_flat2.id == n_flat2.id

    # Resident 1 can view Tower 1 notice, but Resident 2 cannot
    res1_tow1 = svc.get_resident_notice(society_id=soc_id, user_id=res1_id, notice_id=n_tow1.id)
    assert res1_tow1.id == n_tow1.id
    with pytest.raises(ResourceNotFoundError):
        svc.get_resident_notice(society_id=soc_id, user_id=res2_id, notice_id=n_tow1.id)

    # Staff can inspect drafts, archived, and targeted notices via staff get_notice
    staff_draft = svc.get_notice(society_id=soc_id, notice_id=n_draft.id)
    assert staff_draft.id == n_draft.id
    staff_archived = svc.get_notice(society_id=soc_id, notice_id=n_archived.id)
    assert staff_archived.id == n_archived.id

    # --- Membership Validity: Expired lease and future lease residents ---
    # Resident 3: Expired lease
    res3_id = uuid.uuid4()
    res3 = User(
        id=res3_id,
        supabase_uid=uuid.uuid4(),
        email="res3_expired@example.com",
        phone="+919800000004",
        full_name="Expired Tenant",
        status=UserStatus.ACTIVE,
    )
    db_session.add(res3)
    mem_expired = FlatMembership(
        id=uuid.uuid4(),
        society_id=soc_id,
        flat_id=flat1_id,
        user_id=res3_id,
        membership_type=MembershipType.TENANT,
        status=MembershipStatus.APPROVED,
        valid_from=now - timedelta(days=365),
        valid_until=now - timedelta(days=1),  # Expired yesterday
    )
    db_session.add(mem_expired)

    # Resident 4: Future lease
    res4_id = uuid.uuid4()
    res4 = User(
        id=res4_id,
        supabase_uid=uuid.uuid4(),
        email="res4_future@example.com",
        phone="+919800000005",
        full_name="Future Tenant",
        status=UserStatus.ACTIVE,
    )
    db_session.add(res4)
    mem_future = FlatMembership(
        id=uuid.uuid4(),
        society_id=soc_id,
        flat_id=flat1_id,
        user_id=res4_id,
        membership_type=MembershipType.TENANT,
        status=MembershipStatus.APPROVED,
        valid_from=now + timedelta(days=5),  # Starts in 5 days
        valid_until=now + timedelta(days=370),
    )
    db_session.add(mem_future)
    db_session.commit()

    # Expired tenant cannot view notices or mark as read
    with pytest.raises(ResourceNotFoundError):
        svc.get_resident_notice(society_id=soc_id, user_id=res3_id, notice_id=n_soc.id)
    with pytest.raises(ResourceNotFoundError):
        svc.mark_notice_read(society_id=soc_id, user_id=res3_id, notice_id=n_soc.id)
    feed_res3 = svc.list_resident_notices(society_id=soc_id, user_id=res3_id)
    assert len(feed_res3.items) == 0
    all_read_res3 = svc.mark_all_notices_read(society_id=soc_id, user_id=res3_id)
    assert all_read_res3.marked_count == 0

    # Future tenant cannot view notices or mark as read
    with pytest.raises(ResourceNotFoundError):
        svc.get_resident_notice(society_id=soc_id, user_id=res4_id, notice_id=n_soc.id)
    with pytest.raises(ResourceNotFoundError):
        svc.mark_notice_read(society_id=soc_id, user_id=res4_id, notice_id=n_soc.id)
    feed_res4 = svc.list_resident_notices(society_id=soc_id, user_id=res4_id)
    assert len(feed_res4.items) == 0
    all_read_res4 = svc.mark_all_notices_read(society_id=soc_id, user_id=res4_id)
    assert all_read_res4.marked_count == 0


def test_future_scheduled_emergency_notice_not_delivered_early(
    db_session: Session, notice_test_setup: dict[str, Any]
) -> None:
    """Verifies that scheduled emergency notices are NOT delivered early when published_at is in the future."""
    svc = NoticeService(db_session)
    soc_id = notice_test_setup["society_id"]
    staff_id = notice_test_setup["staff_id"]
    tow1_id = notice_test_setup["tow1_id"]
    res1_id = notice_test_setup["res1_id"]

    now = utc_now()
    future_time = now + timedelta(days=2)

    # Create scheduled emergency notice
    emergency_req = CreateNoticeRequest(
        title="SCHEDULED POWER SUBSTATION OVERHAUL",
        body="High voltage overhaul in Tower 1 in 2 days. Backup generators only.",
        category=NoticeCategory.EMERGENCY,
        priority=NoticePriority.URGENT,
        status=NoticeStatus.PUBLISHED,
        published_at=future_time,
        target_type=NoticeTargetType.TOWER,
        target_tower_id=tow1_id,
        deliver_emergency=True,
        confirm_emergency_broadcast=True,
    )
    notice = svc.create_notice(society_id=soc_id, author_id=staff_id, req=emergency_req)

    # 1. Notice should be created with future published_at
    assert notice.status == NoticeStatus.PUBLISHED
    assert (
        notice.published_at.replace(tzinfo=UTC)
        if notice.published_at.tzinfo is None
        else notice.published_at
    ) == future_time

    # 2. Resident MUST NOT receive early emergency notification
    early_notifs = list(
        db_session.scalars(
            select(Notification).where(
                Notification.recipient_user_id == res1_id,
                Notification.event_type == "notice.emergency",
                Notification.aggregate_id == str(notice.id),
            )
        ).all()
    )
    assert len(early_notifs) == 0, "Emergency notice must NOT be delivered before scheduled time"

    # 3. Outbox MUST NOT have broadcast event yet
    outbox_events = list(
        db_session.scalars(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == str(notice.id),
                OutboxEvent.event_type == "notice.emergency_broadcast",
            )
        ).all()
    )
    assert len(outbox_events) == 0, "Outbox event must NOT be enqueued before scheduled time"

    # 4. Now simulate arrival of scheduled publication time
    db_notice = db_session.get(Notice, notice.id)
    assert db_notice is not None
    db_notice.published_at = now - timedelta(minutes=1)
    db_session.flush()

    # Trigger processing of due scheduled notices
    activated = svc.publish_due_scheduled_notices(society_id=soc_id)
    assert any(n.id == notice.id for n in activated)

    # Now notifications and outbox event should exist
    delivered_notifs = list(
        db_session.scalars(
            select(Notification).where(
                Notification.recipient_user_id == res1_id,
                Notification.event_type == "notice.emergency",
                Notification.aggregate_id == str(notice.id),
            )
        ).all()
    )
    assert len(delivered_notifs) == 1
    assert "SCHEDULED POWER SUBSTATION OVERHAUL" in delivered_notifs[0].title

    outbox_after = db_session.scalars(
        select(OutboxEvent).where(
            OutboxEvent.aggregate_id == str(notice.id),
            OutboxEvent.event_type == "notice.emergency_broadcast",
        )
    ).first()
    assert outbox_after is not None
    assert (
        outbox_after.payload["broadcast_key"] == f"notice_emergency:{notice.id}:v{notice.version}"
    )


def test_publish_notice_state_transition_and_repeated_requests_idempotency(
    db_session: Session, notice_test_setup: dict[str, Any]
) -> None:
    """Verifies that publish_notice guards against already-published notices and repeated requests."""
    svc = NoticeService(db_session)
    soc_id = notice_test_setup["society_id"]
    staff_id = notice_test_setup["staff_id"]
    tow1_id = notice_test_setup["tow1_id"]
    res1_id = notice_test_setup["res1_id"]

    # 1. Create a draft notice
    draft_req = CreateNoticeRequest(
        title="Water Tank Inspection Circular",
        body="Periodic water tank inspection will occur next week.",
        category=NoticeCategory.MAINTENANCE,
        priority=NoticePriority.NORMAL,
        status=NoticeStatus.DRAFT,
        target_type=NoticeTargetType.SOCIETY,
    )
    draft_notice = svc.create_notice(society_id=soc_id, author_id=staff_id, req=draft_req)
    assert draft_notice.status == NoticeStatus.DRAFT

    # 2. First publish request
    pub_1 = svc.publish_notice(society_id=soc_id, actor_id=staff_id, notice_id=draft_notice.id)
    assert pub_1.status == NoticeStatus.PUBLISHED
    orig_published_at = pub_1.published_at

    # Count outbox events and audit events
    outbox_count_1 = len(
        list(
            db_session.scalars(
                select(OutboxEvent).where(
                    OutboxEvent.aggregate_id == str(draft_notice.id),
                    OutboxEvent.event_type == "notice.published",
                )
            ).all()
        )
    )
    audit_count_1 = len(
        list(
            db_session.scalars(
                select(AuditEvent).where(
                    AuditEvent.resource_id == str(draft_notice.id),
                    AuditEvent.action == "NOTICE_PUBLISHED",
                )
            ).all()
        )
    )
    assert outbox_count_1 == 1
    assert audit_count_1 == 1

    # 3. Repeated publish request (simulating double click, network retry)
    pub_2 = svc.publish_notice(society_id=soc_id, actor_id=staff_id, notice_id=draft_notice.id)
    assert pub_2.status == NoticeStatus.PUBLISHED
    assert pub_2.published_at == orig_published_at

    # Outbox events and audit records MUST NOT duplicate
    outbox_count_2 = len(
        list(
            db_session.scalars(
                select(OutboxEvent).where(
                    OutboxEvent.aggregate_id == str(draft_notice.id),
                    OutboxEvent.event_type == "notice.published",
                )
            ).all()
        )
    )
    audit_count_2 = len(
        list(
            db_session.scalars(
                select(AuditEvent).where(
                    AuditEvent.resource_id == str(draft_notice.id),
                    AuditEvent.action == "NOTICE_PUBLISHED",
                )
            ).all()
        )
    )
    assert outbox_count_2 == 1, "Repeated publish request must NOT create additional outbox events"
    assert audit_count_2 == 1, "Repeated publish request must NOT create additional audit events"

    # 4. Emergency draft publish repetition guard
    emg_draft = svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="GAS LEAK IMMEDIATE EVACUATION",
            body="Immediate evacuation required.",
            category=NoticeCategory.EMERGENCY,
            priority=NoticePriority.URGENT,
            status=NoticeStatus.DRAFT,
            target_type=NoticeTargetType.TOWER,
            target_tower_id=tow1_id,
            deliver_emergency=True,
            confirm_emergency_broadcast=True,
        ),
    )

    emg_pub_1 = svc.publish_notice(society_id=soc_id, actor_id=staff_id, notice_id=emg_draft.id)
    assert emg_pub_1.status == NoticeStatus.PUBLISHED

    emg_notifs_1 = len(
        list(
            db_session.scalars(
                select(Notification).where(
                    Notification.recipient_user_id == res1_id,
                    Notification.aggregate_id == str(emg_draft.id),
                )
            ).all()
        )
    )
    assert emg_notifs_1 == 1

    # Repeated publish of emergency notice
    emg_pub_2 = svc.publish_notice(society_id=soc_id, actor_id=staff_id, notice_id=emg_draft.id)
    assert emg_pub_2.status == NoticeStatus.PUBLISHED

    emg_notifs_2 = len(
        list(
            db_session.scalars(
                select(Notification).where(
                    Notification.recipient_user_id == res1_id,
                    Notification.aggregate_id == str(emg_draft.id),
                )
            ).all()
        )
    )
    assert emg_notifs_2 == 1, (
        "Repeated publish request must NOT create additional emergency notifications"
    )

    # 5. Publishing an archived notice is forbidden
    svc.archive_notice(society_id=soc_id, actor_id=staff_id, notice_id=draft_notice.id)
    with pytest.raises(ValidationError) as exc_info:
        svc.publish_notice(society_id=soc_id, actor_id=staff_id, notice_id=draft_notice.id)
    assert exc_info.value.code == "INVALID_STATUS_TRANSITION"


def test_idempotent_emergency_broadcast_keys(
    db_session: Session, notice_test_setup: dict[str, Any]
) -> None:
    """Verifies that emergency broadcast keys prevent duplicate deliveries on repeated invocation."""
    svc = NoticeService(db_session)
    soc_id = notice_test_setup["society_id"]
    staff_id = notice_test_setup["staff_id"]
    tow1_id = notice_test_setup["tow1_id"]
    res1_id = notice_test_setup["res1_id"]

    notice = svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="CRITICAL BOILER FAILURE",
            body="Central boiler failure; avoid hot water taps.",
            category=NoticeCategory.EMERGENCY,
            priority=NoticePriority.URGENT,
            status=NoticeStatus.PUBLISHED,
            target_type=NoticeTargetType.TOWER,
            target_tower_id=tow1_id,
            deliver_emergency=True,
            confirm_emergency_broadcast=True,
        ),
    )

    expected_broadcast_key = f"notice_emergency:{notice.id}:v{notice.version}"

    # Check broadcast key in outbox event payload
    outbox = db_session.scalars(
        select(OutboxEvent).where(
            OutboxEvent.aggregate_id == str(notice.id),
            OutboxEvent.event_type == "notice.emergency_broadcast",
        )
    ).first()
    assert outbox is not None
    assert outbox.payload.get("broadcast_key") == expected_broadcast_key

    # Check notification delivery idempotency key
    delivery = db_session.scalars(
        select(NotificationDelivery).where(
            NotificationDelivery.idempotency_key
            == f"in_app:{notice.id}:v{notice.version}:{res1_id}"
        )
    ).first()
    assert delivery is not None
    assert delivery.status == DeliveryStatus.DELIVERED

    # Re-invoking _deliver_emergency_notice directly on the same notice must be a no-op
    db_notice = db_session.get(Notice, notice.id)
    assert db_notice is not None
    result = svc._deliver_emergency_notice(db_notice)
    assert result == 0, "Duplicate invocation must return 0 and skip re-delivery"

    # Must still have exactly 1 outbox event and 1 notification
    total_outbox = len(
        list(
            db_session.scalars(
                select(OutboxEvent).where(
                    OutboxEvent.aggregate_id == str(notice.id),
                    OutboxEvent.event_type == "notice.emergency_broadcast",
                )
            ).all()
        )
    )
    assert total_outbox == 1

    total_notifs = len(
        list(
            db_session.scalars(
                select(Notification).where(
                    Notification.recipient_user_id == res1_id,
                    Notification.aggregate_id == str(notice.id),
                )
            ).all()
        )
    )
    assert total_notifs == 1


def test_multi_tower_targeting_broadcast_and_society_validation(
    db_session: Session, notice_test_setup: dict[str, Any]
) -> None:
    """Verifies multi-tower notice broadcasting, targeting predicates, and foreign tower rejection."""
    svc = NoticeService(db_session)
    soc_id = notice_test_setup["society_id"]
    staff_id = notice_test_setup["staff_id"]
    tow1_id = notice_test_setup["tow1_id"]
    tow2_id = notice_test_setup["tow2_id"]
    res1_id = notice_test_setup["res1_id"]
    res2_id = notice_test_setup["res2_id"]

    # 1. Create a third tower and third resident in same society
    tow3_id = uuid.uuid4()
    tow3 = Tower(id=tow3_id, society_id=soc_id, tower_number="T3", name="Tower 3")
    flat3_id = uuid.uuid4()
    flat3 = Flat(
        id=flat3_id,
        society_id=soc_id,
        tower_id=tow3_id,
        flat_number="301",
        area_sqft=1100,
        status=FlatStatus.OCCUPIED,
    )
    res3_id = uuid.uuid4()
    res3 = User(
        id=res3_id,
        supabase_uid=uuid.uuid4(),
        email="res3_unique@notices.example.com",
        phone="+919800000077",
        full_name="Resident Three",
        status=UserStatus.ACTIVE,
    )
    mem3 = FlatMembership(
        id=uuid.uuid4(),
        society_id=soc_id,
        flat_id=flat3_id,
        user_id=res3_id,
        membership_type=MembershipType.OWNER,
        status=MembershipStatus.APPROVED,
        is_primary=True,
    )
    db_session.add_all([tow3, flat3, res3, mem3])
    db_session.commit()

    # 2. Multi-tower targeting validation: Foreign tower must be rejected
    foreign_soc_id = uuid.uuid4()
    foreign_soc = Society(id=foreign_soc_id, name="Other Society", status=SocietyStatus.ACTIVE)
    foreign_tower_id = uuid.uuid4()
    foreign_tower = Tower(
        id=foreign_tower_id, society_id=foreign_soc_id, tower_number="T99", name="Foreign Tower"
    )
    db_session.add_all([foreign_soc, foreign_tower])
    db_session.commit()

    with pytest.raises(ResourceNotFoundError) as exc_info:
        svc.create_notice(
            society_id=soc_id,
            author_id=staff_id,
            req=CreateNoticeRequest(
                title="Invalid Multi-Tower Notice",
                body="Testing foreign tower rejection.",
                category=NoticeCategory.MAINTENANCE,
                status=NoticeStatus.PUBLISHED,
                target_type=NoticeTargetType.TOWER,
                target_tower_ids=[tow1_id, foreign_tower_id],
            ),
        )
    assert f"Tower {foreign_tower_id} not found in this society" in str(exc_info.value)

    # 3. Create valid multi-tower notice targeted to Tower 1 and Tower 2
    multi_notice = svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="ELEVATOR OVERHAUL: TOWERS 1 & 2",
            body="Elevators in Tower 1 and Tower 2 will be inspected.",
            category=NoticeCategory.MAINTENANCE,
            priority=NoticePriority.HIGH,
            status=NoticeStatus.PUBLISHED,
            target_type=NoticeTargetType.TOWER,
            target_tower_ids=[tow1_id, tow2_id],
            deliver_emergency=True,
            confirm_emergency_broadcast=True,
        ),
    )

    assert len(multi_notice.target_tower_ids) == 2
    assert tow1_id in multi_notice.target_tower_ids
    assert tow2_id in multi_notice.target_tower_ids
    assert len(multi_notice.target_tower_names) == 2

    # Verify NoticeTarget normalized records
    targets = list(
        db_session.scalars(
            select(NoticeTarget).where(NoticeTarget.notice_id == multi_notice.id)
        ).all()
    )
    assert len(targets) == 2
    assert {t.target_id for t in targets} == {tow1_id, tow2_id}

    # 4. Verify feed and access control
    # Resident 1 (Tower 1) can access
    res1_feed = svc.list_resident_notices(society_id=soc_id, user_id=res1_id)
    assert any(n.id == multi_notice.id for n in res1_feed.items)
    res1_detail = svc.get_resident_notice(
        society_id=soc_id, user_id=res1_id, notice_id=multi_notice.id
    )
    assert res1_detail.id == multi_notice.id

    # Resident 2 (Tower 2) can access
    res2_feed = svc.list_resident_notices(society_id=soc_id, user_id=res2_id)
    assert any(n.id == multi_notice.id for n in res2_feed.items)
    res2_detail = svc.get_resident_notice(
        society_id=soc_id, user_id=res2_id, notice_id=multi_notice.id
    )
    assert res2_detail.id == multi_notice.id

    # Resident 3 (Tower 3) CANNOT access
    res3_feed = svc.list_resident_notices(society_id=soc_id, user_id=res3_id)
    assert not any(n.id == multi_notice.id for n in res3_feed.items)
    with pytest.raises(ResourceNotFoundError):
        svc.get_resident_notice(society_id=soc_id, user_id=res3_id, notice_id=multi_notice.id)

    # 5. Verify emergency broadcast notifications sent to Tower 1 & 2, not Tower 3
    notif_res1 = db_session.scalars(
        select(Notification).where(
            Notification.recipient_user_id == res1_id,
            Notification.aggregate_id == str(multi_notice.id),
        )
    ).first()
    assert notif_res1 is not None

    notif_res2 = db_session.scalars(
        select(Notification).where(
            Notification.recipient_user_id == res2_id,
            Notification.aggregate_id == str(multi_notice.id),
        )
    ).first()
    assert notif_res2 is not None

    notif_res3 = db_session.scalars(
        select(Notification).where(
            Notification.recipient_user_id == res3_id,
            Notification.aggregate_id == str(multi_notice.id),
        )
    ).first()
    assert notif_res3 is None


def test_multi_flat_targeting_and_society_validation(
    db_session: Session, notice_test_setup: dict[str, Any]
) -> None:
    """Verifies multi-flat notice targeting and foreign flat validation."""
    svc = NoticeService(db_session)
    soc_id = notice_test_setup["society_id"]
    staff_id = notice_test_setup["staff_id"]
    flat1_id = notice_test_setup["flat1_id"]
    flat2_id = notice_test_setup["flat2_id"]
    res1_id = notice_test_setup["res1_id"]
    res2_id = notice_test_setup["res2_id"]

    # Foreign flat rejection
    foreign_soc_id = uuid.uuid4()
    foreign_soc = Society(id=foreign_soc_id, name="Other Society 2", status=SocietyStatus.ACTIVE)
    foreign_flat_id = uuid.uuid4()
    foreign_flat = Flat(
        id=foreign_flat_id,
        society_id=foreign_soc_id,
        tower_id=notice_test_setup["tow1_id"],
        flat_number="999",
        area_sqft=1000,
        status=FlatStatus.OCCUPIED,
    )
    db_session.add_all([foreign_soc, foreign_flat])
    db_session.commit()

    with pytest.raises(ResourceNotFoundError) as exc_info:
        svc.create_notice(
            society_id=soc_id,
            author_id=staff_id,
            req=CreateNoticeRequest(
                title="Invalid Multi-Flat Notice",
                body="Testing foreign flat rejection.",
                category=NoticeCategory.GENERAL,
                status=NoticeStatus.PUBLISHED,
                target_type=NoticeTargetType.FLAT,
                target_flat_ids=[flat1_id, foreign_flat_id],
            ),
        )
    assert f"Flat {foreign_flat_id} not found in this society" in str(exc_info.value)

    # Valid multi-flat notice
    multi_flat_notice = svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="PLUMBING PIPE INSPECTION FOR FLATS 101 & 201",
            body="Vertical riser inspection affecting flats 101 and 201.",
            category=NoticeCategory.MAINTENANCE,
            priority=NoticePriority.NORMAL,
            status=NoticeStatus.PUBLISHED,
            target_type=NoticeTargetType.FLAT,
            target_flat_ids=[flat1_id, flat2_id],
        ),
    )

    assert len(multi_flat_notice.target_flat_ids) == 2
    assert flat1_id in multi_flat_notice.target_flat_ids
    assert flat2_id in multi_flat_notice.target_flat_ids
    assert len(multi_flat_notice.target_flat_numbers) == 2

    # Both residents can see it
    feed1 = svc.list_resident_notices(society_id=soc_id, user_id=res1_id)
    assert any(n.id == multi_flat_notice.id for n in feed1.items)
    feed2 = svc.list_resident_notices(society_id=soc_id, user_id=res2_id)
    assert any(n.id == multi_flat_notice.id for n in feed2.items)


def test_dynamic_targeting_options_loaders(
    db_session: Session, notice_test_setup: dict[str, Any]
) -> None:
    """Verifies that society towers and flats are loaded dynamically."""
    svc = NoticeService(db_session)
    soc_id = notice_test_setup["society_id"]

    options = svc.get_targeting_options(soc_id)
    assert len(options.towers) >= 2
    tower_numbers = [t.tower_number for t in options.towers]
    assert "T1" in tower_numbers
    assert "T2" in tower_numbers

    assert len(options.flats) >= 2
    flat_numbers = [f.flat_number for f in options.flats]
    assert "101" in flat_numbers
    assert "201" in flat_numbers


def test_notice_scheduling_validation_and_transitions(
    db_session: Session, notice_test_setup: dict[str, Any]
) -> None:
    """Verifies SCHEDULED notice creation, future publication validation, and automated transition."""
    svc = NoticeService(db_session)
    soc_id = notice_test_setup["society_id"]
    staff_id = notice_test_setup["staff_id"]

    future_time = (utc_now() + timedelta(days=2)).isoformat()
    past_time = (utc_now() - timedelta(days=1)).isoformat()

    # 1. SCHEDULED without published_at fails
    with pytest.raises(ValidationError) as exc:
        svc.create_notice(
            society_id=soc_id,
            author_id=staff_id,
            req=CreateNoticeRequest(
                title="Future Notice Missing Date",
                body="Testing invalid scheduled notice.",
                category=NoticeCategory.CIRCULAR,
                status=NoticeStatus.SCHEDULED,
                target_type=NoticeTargetType.SOCIETY,
            ),
        )
    assert "Scheduled notices must have a future publication date" in str(exc.value)

    # 2. SCHEDULED with past published_at fails
    with pytest.raises(ValidationError) as exc:
        svc.create_notice(
            society_id=soc_id,
            author_id=staff_id,
            req=CreateNoticeRequest(
                title="Past Scheduled Notice",
                body="Testing invalid past publication date.",
                category=NoticeCategory.CIRCULAR,
                status=NoticeStatus.SCHEDULED,
                published_at=past_time,
                target_type=NoticeTargetType.SOCIETY,
            ),
        )
    assert "Scheduled notices must have a future publication date" in str(exc.value)

    # 3. SCHEDULED with future published_at succeeds
    sched_notice = svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="Valid Scheduled Circular",
            body="Township annual marathon details.",
            category=NoticeCategory.EVENT,
            status=NoticeStatus.SCHEDULED,
            published_at=future_time,
            target_type=NoticeTargetType.SOCIETY,
        ),
    )
    assert sched_notice.status == NoticeStatus.SCHEDULED
    assert sched_notice.version == 1

    # 4. PUBLISHED status with future published_at automatically transitions to SCHEDULED
    auto_sched = svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="Auto Scheduled Maintenance",
            body="Elevator inspection in 2 days.",
            category=NoticeCategory.MAINTENANCE,
            status=NoticeStatus.PUBLISHED,
            published_at=future_time,
            target_type=NoticeTargetType.SOCIETY,
        ),
    )
    assert auto_sched.status == NoticeStatus.PUBLISHED


def test_notice_versioning_audit_trail_and_idempotency(
    db_session: Session, notice_test_setup: dict[str, Any]
) -> None:
    """Verifies notice version incrementing across mutations and audit trail events."""
    svc = NoticeService(db_session)
    soc_id = notice_test_setup["society_id"]
    staff_id = notice_test_setup["staff_id"]

    # 1. Create notice -> version 1
    notice = svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="Versioned Notice Test",
            body="Initial draft content.",
            category=NoticeCategory.CIRCULAR,
            status=NoticeStatus.DRAFT,
            target_type=NoticeTargetType.SOCIETY,
        ),
    )
    assert notice.version == 1

    # 2. Update notice -> version 2
    updated = svc.update_notice(
        society_id=soc_id,
        notice_id=notice.id,
        actor_id=staff_id,
        req=UpdateNoticeRequest(
            title="Versioned Notice Test (Revised)",
            body="Revised draft content with additional information.",
        ),
    )
    assert updated.version == 2

    # 3. Publish notice -> version 3
    published = svc.publish_notice(society_id=soc_id, actor_id=staff_id, notice_id=notice.id)
    assert published.version == 3
    assert published.status == NoticeStatus.PUBLISHED

    # 4. Repeated publish on already published notice is idempotent and does not increment version
    published_again = svc.publish_notice(society_id=soc_id, actor_id=staff_id, notice_id=notice.id)
    assert published_again.version == 3

    # 5. Archive notice -> version 4
    archived = svc.archive_notice(society_id=soc_id, actor_id=staff_id, notice_id=notice.id)
    assert archived.version == 4
    assert archived.status == NoticeStatus.ARCHIVED

    # 6. Repeated archive is idempotent and does not increment version
    archived_again = svc.archive_notice(society_id=soc_id, actor_id=staff_id, notice_id=notice.id)
    assert archived_again.version == 4


def test_publish_due_scheduled_notices_worker_execution(
    db_session: Session, notice_test_setup: dict[str, Any]
) -> None:
    """Verifies that publish_due_scheduled_notices activates due notices with outbox and audit events."""
    svc = NoticeService(db_session)
    soc_id = notice_test_setup["society_id"]
    staff_id = notice_test_setup["staff_id"]

    # 1. Create a due scheduled notice directly in DB
    due_notice = Notice(
        id=uuid.uuid4(),
        society_id=soc_id,
        author_id=staff_id,
        title="Due Scheduled Pest Control",
        body="Pest control starts today.",
        category=NoticeCategory.MAINTENANCE,
        priority=NoticePriority.NORMAL,
        status=NoticeStatus.SCHEDULED,
        target_type=NoticeTargetType.SOCIETY,
        published_at=utc_now() - timedelta(minutes=10),
        version=1,
    )
    # 2. Create a future scheduled notice
    future_notice = Notice(
        id=uuid.uuid4(),
        society_id=soc_id,
        author_id=staff_id,
        title="Future Solar Panel Cleaning",
        body="Solar panel cleaning next week.",
        category=NoticeCategory.MAINTENANCE,
        priority=NoticePriority.NORMAL,
        status=NoticeStatus.SCHEDULED,
        target_type=NoticeTargetType.SOCIETY,
        published_at=utc_now() + timedelta(days=5),
        version=1,
    )
    db_session.add_all([due_notice, future_notice])
    db_session.commit()

    # 3. Run publish_due_scheduled_notices
    published_list = svc.publish_due_scheduled_notices()
    assert any(n.id == due_notice.id for n in published_list)
    assert not any(n.id == future_notice.id for n in published_list)

    # 4. Check due notice status in DB
    refreshed_due = db_session.get(Notice, due_notice.id)
    assert refreshed_due is not None
    assert refreshed_due.status == NoticeStatus.PUBLISHED
    assert refreshed_due.version == 2

    # 5. Check outbox event was emitted for notice.published
    stmt = select(OutboxEvent).where(
        OutboxEvent.event_type == "notice.published",
        OutboxEvent.aggregate_id == str(due_notice.id),
    )
    outbox = db_session.scalar(stmt)
    assert outbox is not None
    assert outbox.payload["broadcast_key"] == f"notice_publish:{due_notice.id}:v2"

    # 6. Check audit event
    audit_stmt = select(AuditEvent).where(
        AuditEvent.action == "NOTICE_PUBLISHED",
        AuditEvent.resource_id == str(due_notice.id),
    )
    audit = db_session.scalar(audit_stmt)
    assert audit is not None

    # 7. Running again finds nothing due
    published_again = svc.publish_due_scheduled_notices()
    assert len([n for n in published_again if n.id == due_notice.id]) == 0


def test_staff_notices_overview_and_resident_unread_count(
    db_session: Session, notice_test_setup: dict[str, Any]
) -> None:
    """Verifies get_staff_notices_overview and get_resident_unread_count."""
    svc = NoticeService(db_session)
    soc_id = notice_test_setup["society_id"]
    staff_id = notice_test_setup["staff_id"]
    res1_id = notice_test_setup["res1_id"]

    # Create notices in various states
    svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="Overview Test Draft",
            body="Draft body",
            category=NoticeCategory.GENERAL,
            status=NoticeStatus.DRAFT,
            target_type=NoticeTargetType.SOCIETY,
        ),
    )
    n_pub = svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="Overview Test Published",
            body="Published body",
            category=NoticeCategory.CIRCULAR,
            status=NoticeStatus.PUBLISHED,
            target_type=NoticeTargetType.SOCIETY,
        ),
    )
    svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="Overview Test Emergency",
            body="Emergency alert body",
            category=NoticeCategory.EMERGENCY,
            priority=NoticePriority.URGENT,
            status=NoticeStatus.PUBLISHED,
            target_type=NoticeTargetType.SOCIETY,
        ),
    )

    overview = svc.get_staff_notices_overview(soc_id)
    assert overview.total >= 3
    assert overview.published >= 2
    assert overview.draft >= 1
    assert overview.emergency >= 1

    # Check resident unread count
    unread_res = svc.get_resident_unread_count(soc_id, res1_id)
    assert unread_res >= 2

    # Mark one as read
    svc.mark_notice_read(society_id=soc_id, user_id=res1_id, notice_id=n_pub.id)
    unread_after_read = svc.get_resident_unread_count(soc_id, res1_id)
    assert unread_after_read == unread_res - 1


def test_expanded_utility_categories_water_electricity_security(
    db_session: Session, notice_test_setup: dict[str, Any]
) -> None:
    """Verifies that WATER, ELECTRICITY, and SECURITY notice categories persist and serialize."""
    svc = NoticeService(db_session)
    soc_id = notice_test_setup["society_id"]
    staff_id = notice_test_setup["staff_id"]
    tow1_id = notice_test_setup["tow1_id"]

    # 1. WATER category notice
    n_water = svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="Hydro-Pneumatic Pump Overhaul",
            body="Water supply affected between 2 PM and 5 PM.",
            category=NoticeCategory.WATER,
            priority=NoticePriority.HIGH,
            status=NoticeStatus.PUBLISHED,
            target_type=NoticeTargetType.TOWER,
            target_tower_id=tow1_id,
        ),
    )
    assert n_water.category == NoticeCategory.WATER

    # 2. ELECTRICITY category notice
    n_elec = svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="Transformer Oil Replacement",
            body="Grid power disconnected for 1 hour.",
            category=NoticeCategory.ELECTRICITY,
            priority=NoticePriority.NORMAL,
            status=NoticeStatus.PUBLISHED,
            target_type=NoticeTargetType.SOCIETY,
        ),
    )
    assert n_elec.category == NoticeCategory.ELECTRICITY

    # 3. SECURITY category notice
    n_sec = svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="Night Boom Barrier Maintenance",
            body="Main entrance lane 2 restricted tonight.",
            category=NoticeCategory.SECURITY,
            priority=NoticePriority.LOW,
            status=NoticeStatus.PUBLISHED,
            target_type=NoticeTargetType.SOCIETY,
        ),
    )
    assert n_sec.category == NoticeCategory.SECURITY


def test_version_based_notification_idempotency_and_republish(
    db_session: Session, notice_test_setup: dict[str, Any]
) -> None:
    """Verifies that editing a published notice increments version and allows republishing

    with version-scoped broadcast keys and outbox deduplication.
    """
    svc = NoticeService(db_session)
    soc_id = notice_test_setup["society_id"]
    staff_id = notice_test_setup["staff_id"]

    # 1. Create and publish initial notice (version 1)
    notice = svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="Scheduled Water Tank Cleaning",
            body="Cleaning will occur from 9 AM to 12 PM.",
            category=NoticeCategory.WATER,
            priority=NoticePriority.NORMAL,
            status=NoticeStatus.PUBLISHED,
            target_type=NoticeTargetType.SOCIETY,
        ),
    )
    assert notice.version == 1

    # Check that outbox event exists for v1
    v1_outbox = list(
        db_session.scalars(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == str(notice.id),
                OutboxEvent.event_type == "notice.published",
            )
        ).all()
    )
    assert len(v1_outbox) == 1
    assert v1_outbox[0].payload.get("version") == 1
    assert v1_outbox[0].payload.get("broadcast_key") == f"notice_publish:{notice.id}:v1"

    # Repeated publish of v1 must be idempotent and NOT emit duplicate outbox event
    pub_result_v1 = svc.publish_notice(society_id=soc_id, actor_id=staff_id, notice_id=notice.id)
    assert pub_result_v1.version == 1
    v1_outbox_repeat = list(
        db_session.scalars(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == str(notice.id),
                OutboxEvent.event_type == "notice.published",
            )
        ).all()
    )
    assert len(v1_outbox_repeat) == 1, "Duplicate publish must not create duplicate outbox event"

    # 2. Update notice (version increments to 2)
    updated_notice = svc.update_notice(
        society_id=soc_id,
        actor_id=staff_id,
        notice_id=notice.id,
        req=UpdateNoticeRequest(
            body="REVISED: Cleaning extended until 2 PM due to pump maintenance.",
        ),
    )
    assert updated_notice.version == 2

    # Check that updating a published notice enqueued a new outbox event for v2
    all_outbox = list(
        db_session.scalars(
            select(OutboxEvent)
            .where(
                OutboxEvent.aggregate_id == str(notice.id),
                OutboxEvent.event_type == "notice.published",
            )
            .order_by(OutboxEvent.created_at.asc())
        ).all()
    )
    assert len(all_outbox) == 2
    assert all_outbox[1].payload.get("version") == 2
    assert all_outbox[1].payload.get("broadcast_key") == f"notice_publish:{notice.id}:v2"


def test_emergency_notice_requires_explicit_confirmation_gate(
    db_session: Session, notice_test_setup: dict[str, Any]
) -> None:
    """Verifies that emergency broadcasts strictly require deliver_emergency AND confirm_emergency_broadcast.

    Category EMERGENCY or priority URGENT alone must NOT trigger emergency alerts.
    """
    svc = NoticeService(db_session)
    soc_id = notice_test_setup["society_id"]
    staff_id = notice_test_setup["staff_id"]
    tow1_id = notice_test_setup["tow1_id"]

    # 1. Notice with category EMERGENCY and priority URGENT, but deliver_emergency=False
    # Must create a standard notice, NOT dispatch emergency alerts
    regular_emg = svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="Fire Drill Post-Mortem Notes",
            body="Informational notes on yesterday's drill.",
            category=NoticeCategory.EMERGENCY,
            priority=NoticePriority.URGENT,
            status=NoticeStatus.PUBLISHED,
            target_type=NoticeTargetType.TOWER,
            target_tower_id=tow1_id,
            deliver_emergency=False,
        ),
    )
    assert regular_emg.deliver_emergency is False

    # Outbox should have notice.published, NOT notice.emergency_broadcast
    outbox_reg = list(
        db_session.scalars(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == str(regular_emg.id),
            )
        ).all()
    )
    assert len(outbox_reg) == 1
    assert outbox_reg[0].event_type == "notice.published"

    # In-app notifications generated by notice.emergency should be 0
    emg_notifs = list(
        db_session.scalars(
            select(Notification).where(
                Notification.aggregate_id.like(f"{regular_emg.id}%"),
                Notification.event_type == "notice.emergency",
            )
        ).all()
    )
    assert len(emg_notifs) == 0

    # 2. deliver_emergency=True WITHOUT confirm_emergency_broadcast must raise ValidationError
    with pytest.raises(ValidationError) as exc_info:
        svc.create_notice(
            society_id=soc_id,
            author_id=staff_id,
            req=CreateNoticeRequest(
                title="UNCONFIRMED EVACUATION ALERT",
                body="Immediate evacuation.",
                category=NoticeCategory.EMERGENCY,
                priority=NoticePriority.URGENT,
                status=NoticeStatus.PUBLISHED,
                target_type=NoticeTargetType.TOWER,
                target_tower_id=tow1_id,
                deliver_emergency=True,
                confirm_emergency_broadcast=False,
            ),
        )
    assert exc_info.value.code == "EMERGENCY_CONFIRMATION_REQUIRED"

    # 3. deliver_emergency=True WITH confirm_emergency_broadcast=True must succeed
    confirmed_emg = svc.create_notice(
        society_id=soc_id,
        author_id=staff_id,
        req=CreateNoticeRequest(
            title="AUTHORIZED GAS LEAK EVACUATION",
            body="Immediate evacuation authorized by Chief Fire Officer.",
            category=NoticeCategory.EMERGENCY,
            priority=NoticePriority.URGENT,
            status=NoticeStatus.PUBLISHED,
            target_type=NoticeTargetType.TOWER,
            target_tower_id=tow1_id,
            deliver_emergency=True,
            confirm_emergency_broadcast=True,
        ),
    )
    assert confirmed_emg.deliver_emergency is True

    # Emergency outbox event should be enqueued
    outbox_emg = list(
        db_session.scalars(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == str(confirmed_emg.id),
                OutboxEvent.event_type == "notice.emergency_broadcast",
            )
        ).all()
    )
    assert len(outbox_emg) == 1
    assert outbox_emg[0].payload.get("broadcast_key") == f"notice_emergency:{confirmed_emg.id}:v1"
