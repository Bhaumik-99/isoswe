"""Domain Unit and Integration Tests for Notifications System.

Tests cover:
- Recipient resolution (active residents vs expired leases, helpdesk staff).
- User preference evaluation and mandatory emergency overrides.
- In-app notification creation and multi-channel delivery lifecycle.
- All mapped domain event types across Billing, Complaints, and Gate.
- Idempotency guarantees (duplicate events do not create duplicates).
- Provider dispatch state machine (mock suppression, transient retry backoff, permanent failure).
- PII masking rules for emails and phone numbers.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.identity.models import (
    FlatMembership,
    MembershipStatus,
    MembershipType,
    User,
    UserStatus,
)
from app.domains.notifications.models import (
    DeliveryStatus,
    Notice,
    NoticeCategory,
    NoticePriority,
    NoticeStatus,
    NoticeTargetType,
    Notification,
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryAttempt,
    NotificationPriority,
)
from app.domains.notifications.providers.base import (
    EmailProvider,
    NotificationResult,
    mask_email,
    mask_phone,
)
from app.domains.notifications.providers.mock import MockEmailProvider, MockSMSProvider
from app.domains.notifications.providers.registry import provider_registry
from app.domains.notifications.service import NotificationService
from app.messaging.consumer import dispatcher
from app.messaging.envelope import EventEnvelope, EventMetadata
from app.workers.notification_worker import NotificationHandler


# PII Masking Tests
def test_pii_masking_rules() -> None:
    masked_email = mask_email("neeraj.kulkarni@example.com")
    assert masked_email.startswith("n")
    assert masked_email.endswith("i@example.com")
    assert "*" in masked_email

    assert mask_email("") == "***@***"
    assert mask_email("invalid") == "***@***"

    masked_phone = mask_phone("+919876543210")
    assert masked_phone.startswith("+91-XXXXX-XX")
    assert masked_phone.endswith("210")

    assert mask_phone("") == "+XX-XXXXX-XXXXX"


# Mock Provider Behavior Tests
def test_mock_providers_fail_closed_with_suppressed() -> None:
    mock_email = MockEmailProvider()
    res_email = mock_email.send_email(
        to_email="test@example.com",
        subject="Test Invoice",
        body_text="Your invoice is ready",
    )
    assert res_email.status == DeliveryStatus.SUPPRESSED
    assert res_email.provider == "mock_email"
    assert res_email.error_code == "MOCK_PROVIDER_EXTERNAL_DELIVERY_DISABLED"
    assert (res_email.provider_reference or res_email.provider_message_id) is not None

    mock_sms = MockSMSProvider()
    res_sms = mock_sms.send_sms(
        to_phone="+919876543210",
        message="Visitor arrived at Main Gate",
    )
    assert res_sms.status == DeliveryStatus.SUPPRESSED
    assert res_sms.provider == "mock_sms"
    assert res_sms.error_code == "MOCK_PROVIDER_EXTERNAL_DELIVERY_DISABLED"


# Recipient Resolution Tests
def test_resolve_flat_recipients_excludes_expired_leases(db_session: Session) -> None:
    society_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    flat_id = uuid.UUID("33333333-3333-3333-3333-333333331203")
    service = NotificationService(db_session)

    # In conftest, neeraj is active tenant in flat_1203
    recipients = service.get_active_flat_residents(society_id, flat_id)
    assert len(recipients) >= 1
    recipient_ids = [u.id for u in recipients]
    neeraj_id = uuid.UUID("44444444-4444-4444-4444-444444440001")
    assert neeraj_id in recipient_ids

    # Add an expired lease tenant
    expired_user = User(
        id=uuid.uuid4(),
        supabase_uid=uuid.uuid4(),
        phone="+91-98000-09999",
        email="expired.resident@example.com",
        full_name="Expired Resident",
        status=UserStatus.ACTIVE,
    )
    db_session.add(expired_user)
    db_session.flush()

    past = datetime.now(UTC) - timedelta(days=30)
    expired_membership = FlatMembership(
        id=uuid.uuid4(),
        society_id=society_id,
        flat_id=flat_id,
        user_id=expired_user.id,
        membership_type=MembershipType.TENANT,
        status=MembershipStatus.APPROVED,
        valid_from=past - timedelta(days=365),
        valid_until=past,
    )
    db_session.add(expired_membership)
    db_session.commit()

    # Re-resolve: expired tenant MUST NOT be returned
    updated_recipients = service.get_active_flat_residents(society_id, flat_id)
    updated_ids = [u.id for u in updated_recipients]
    assert expired_user.id not in updated_ids


def test_resolve_staff_recipients(db_session: Session) -> None:
    society_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    service = NotificationService(db_session)

    staff = service.get_staff_recipients(society_id)
    assert len(staff) >= 1
    helpdesk_id = uuid.UUID("44444444-4444-4444-4444-444444440004")
    assert any(u.id == helpdesk_id for u in staff)


# Preferences and Emergency Override Tests
def test_channel_preferences_and_emergency_bypass(db_session: Session) -> None:
    society_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    user_id = uuid.UUID("44444444-4444-4444-4444-444444440001")
    service = NotificationService(db_session)

    # Set user preference opting out of email for complaints
    pref = service.get_or_create_preferences(society_id, user_id)
    pref.complaints_email = False
    pref.complaints_sms = False
    db_session.commit()

    # Normal complaint event: email and sms should be disabled per preference
    permitted, reason = service.is_channel_permitted(
        pref, NotificationChannel.EMAIL, "complaint.created", NotificationPriority.NORMAL
    )
    assert not permitted
    assert reason == "PREFERENCE_COMPLAINTS_EMAIL_DISABLED"

    permitted, reason = service.is_channel_permitted(
        pref, NotificationChannel.SMS, "complaint.created", NotificationPriority.NORMAL
    )
    assert not permitted
    assert reason == "PREFERENCE_COMPLAINTS_SMS_DISABLED"

    permitted, reason = service.is_channel_permitted(
        pref, NotificationChannel.IN_APP, "complaint.created", NotificationPriority.NORMAL
    )
    assert permitted

    # Emergency safety escalation: MUST OVERRIDE user opt-out!
    permitted, reason = service.is_channel_permitted(
        pref, NotificationChannel.EMAIL, "complaint.safety_escalated", NotificationPriority.URGENT
    )
    assert permitted
    assert reason == "MANDATORY_EMERGENCY_OVERRIDE"

    permitted, reason = service.is_channel_permitted(
        pref, NotificationChannel.SMS, "complaint.safety_escalated", NotificationPriority.URGENT
    )
    assert permitted
    assert reason == "MANDATORY_EMERGENCY_OVERRIDE"


# Notification Dispatch and Event Handling Tests
def test_process_billing_invoice_generated(db_session: Session) -> None:
    society_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    flat_id = uuid.UUID("33333333-3333-3333-3333-333333331203")
    invoice_id = str(uuid.uuid4())
    service = NotificationService(db_session)

    envelope = EventEnvelope(
        event_id=uuid.uuid4(),
        event_type="billing.invoice_generated",
        aggregate_type="invoice",
        aggregate_id=invoice_id,
        metadata=EventMetadata(correlation_id=str(uuid.uuid4())),
        payload={
            "society_id": str(society_id),
            "invoice_id": invoice_id,
            "invoice_number": "INV-2026-001",
            "flat_id": str(flat_id),
            "amount_due": "5500.00",
            "due_date": "2026-11-20",
        },
    )

    created_count = service.process_domain_event(envelope)
    assert created_count >= 1

    # Verify In-App Notification was created for flat 1203 resident (Neeraj)
    notifs = db_session.scalars(
        select(Notification).where(
            Notification.aggregate_id == invoice_id,
            Notification.aggregate_type == "billing_invoice",
        )
    ).all()
    assert len(notifs) >= 1
    notif = notifs[0]
    assert "INV-2026-001" in notif.title or "INV-2026-001" in notif.body
    assert notif.priority == NotificationPriority.NORMAL

    # Verify delivery records exist
    delivs = db_session.scalars(
        select(NotificationDelivery).where(NotificationDelivery.notification_id == notif.id)
    ).all()
    channels = {d.channel for d in delivs}
    assert NotificationChannel.IN_APP in channels
    assert NotificationChannel.EMAIL in channels

    # In test environment, mock email delivery should be SUPPRESSED (never falsely claiming SENT)
    email_deliv = next(d for d in delivs if d.channel == NotificationChannel.EMAIL)
    assert email_deliv.status == DeliveryStatus.SUPPRESSED
    assert email_deliv.last_error_code == "MOCK_PROVIDER_EXTERNAL_DELIVERY_DISABLED"


def test_process_complaint_safety_escalated(db_session: Session) -> None:
    society_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    complaint_id = str(uuid.uuid4())
    service = NotificationService(db_session)

    envelope = EventEnvelope(
        event_id=uuid.uuid4(),
        event_type="complaint.safety_escalated",
        aggregate_type="complaint",
        aggregate_id=complaint_id,
        metadata=EventMetadata(correlation_id=str(uuid.uuid4())),
        payload={
            "society_id": str(society_id),
            "complaint_id": complaint_id,
            "complaint_number": "CMP-2026-999",
            "category": "ELEVATOR_HAZARD",
            "safety_concern": "Elevator door sensor trapped passenger",
            "resident_user_id": str(uuid.UUID("44444444-4444-4444-4444-444444440001")),
        },
    )

    created_count = service.process_domain_event(envelope)
    assert created_count >= 1

    # Must notify resident AND helpdesk staff with URGENT priority
    urgent_notifs = db_session.scalars(
        select(Notification).where(
            Notification.aggregate_id == complaint_id,
            Notification.priority == NotificationPriority.URGENT,
        )
    ).all()
    assert len(urgent_notifs) >= 1
    recipient_ids = {n.recipient_user_id for n in urgent_notifs}
    assert uuid.UUID("44444444-4444-4444-4444-444444440001") in recipient_ids
    assert uuid.UUID("44444444-4444-4444-4444-444444440004") in recipient_ids


def test_process_visitor_approval_requested(db_session: Session) -> None:
    society_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    flat_id = uuid.UUID("33333333-3333-3333-3333-333333331203")
    visitor_id = str(uuid.uuid4())
    service = NotificationService(db_session)

    envelope = EventEnvelope(
        event_id=uuid.uuid4(),
        event_type="visitor.approval_requested",
        aggregate_type="visitor",
        aggregate_id=visitor_id,
        metadata=EventMetadata(correlation_id=str(uuid.uuid4())),
        payload={
            "society_id": str(society_id),
            "visitor_id": visitor_id,
            "visitor_name": "Delivery Person (Swiggy)",
            "phone_number": "+919876543210",
            "destination_flat_id": str(flat_id),
            "gate_id": str(uuid.uuid4()),
        },
    )

    created_count = service.process_domain_event(envelope)
    assert created_count >= 1

    notifs = db_session.scalars(
        select(Notification).where(
            Notification.aggregate_id == visitor_id,
        )
    ).all()
    assert len(notifs) >= 1
    notif = notifs[0]
    assert "Approval" in notif.title
    assert "Delivery Person (Swiggy)" in notif.body
    assert notif.action_url == "/resident/visitors"


def test_idempotency_prevents_duplicate_deliveries(db_session: Session) -> None:
    society_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    flat_id = uuid.UUID("33333333-3333-3333-3333-333333331203")
    invoice_id = str(uuid.uuid4())
    service = NotificationService(db_session)

    event_id = uuid.uuid4()
    envelope = EventEnvelope(
        event_id=event_id,
        event_type="billing.invoice_paid",
        aggregate_type="invoice",
        aggregate_id=invoice_id,
        metadata=EventMetadata(correlation_id=str(uuid.uuid4())),
        payload={
            "society_id": str(society_id),
            "invoice_id": invoice_id,
            "invoice_number": "INV-2026-PAID",
            "flat_id": str(flat_id),
            "amount_paid": "5500.00",
        },
    )

    # First dispatch
    count_first = service.process_domain_event(envelope)
    assert count_first >= 1

    # Second dispatch with identical event_id
    service.process_domain_event(envelope)
    # Deliveries should be matched or recognized as existing, not duplicated
    notif_count = db_session.scalars(
        select(Notification).where(Notification.aggregate_id == invoice_id)
    ).all()
    assert len(notif_count) == 1


# Provider Retry and Backoff State Machine Tests
class SimulatedTransientEmailProvider(EmailProvider):
    @property
    def provider_name(self) -> str:
        return "simulated_transient_ses"

    def send_email(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
        idempotency_key: str | None = None,
        metadata: dict | None = None,
    ) -> NotificationResult:
        return NotificationResult(
            status=DeliveryStatus.FAILED,
            provider="simulated_transient_ses",
            error_code="ThrottlingException",
            error_message="Daily sending quota exceeded; backoff required",
            is_transient=True,
        )


def test_transient_delivery_failure_schedules_backoff(db_session: Session) -> None:
    society_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    user_id = uuid.UUID("44444444-4444-4444-4444-444444440001")

    # Override email provider with transient error provider
    transient_provider = SimulatedTransientEmailProvider()
    provider_registry.set_email_provider(transient_provider)

    try:
        service = NotificationService(db_session)
        user = db_session.get(User, user_id)
        assert user is not None

        notif = service.create_in_app_notification(
            society_id=society_id,
            recipient=user,
            event_type="billing.payment_failed",
            title="Payment Failed",
            body="Your maintenance payment failed.",
            priority=NotificationPriority.HIGH,
            aggregate_type="payment",
            aggregate_id=str(uuid.uuid4()),
        )
        db_session.flush()

        deliv = service.dispatch_email_delivery(
            notification=notif,
            recipient=user,
            subject="Payment Failed",
            body_text="Your maintenance payment failed.",
        )

        assert deliv is not None
        assert deliv.status == DeliveryStatus.RETRYING
        assert deliv.attempt_count == 1
        assert deliv.next_attempt_at is not None
        assert deliv.last_error_code == "ThrottlingException"

        # Check attempt history record
        attempts = db_session.scalars(
            select(NotificationDeliveryAttempt).where(
                NotificationDeliveryAttempt.delivery_id == deliv.id
            )
        ).all()
        assert len(attempts) == 1
        assert attempts[0].error_code == "ThrottlingException"
    finally:
        # Reset provider registry
        provider_registry.reset()


# =============================================================================
# Official Notice Worker & Fan-Out Tests
# =============================================================================


def test_notification_handler_subscribes_to_notice_events() -> None:
    """Verifies notification worker subscribes to notice.published and notice.emergency_broadcast."""
    handler = NotificationHandler()
    assert "notice.published" in handler.supported_event_types
    assert "notice.emergency_broadcast" in handler.supported_event_types


def test_process_notice_published_fan_out(db_session: Session) -> None:
    """Verifies notice.published fans out to In-App, Email, and SMS deliveries."""
    society_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    flat_id = uuid.UUID("33333333-3333-3333-3333-333333331203")
    staff_id = uuid.UUID("44444444-4444-4444-4444-444444440004")

    # Create published notice targeted to flat 1203
    notice_id = uuid.uuid4()
    notice = Notice(
        id=notice_id,
        society_id=society_id,
        author_id=staff_id,
        title="Scheduled Water Tank Cleaning",
        body="Water supply will be suspended tomorrow from 10 AM to 2 PM.",
        category=NoticeCategory.MAINTENANCE,
        priority=NoticePriority.NORMAL,
        status=NoticeStatus.PUBLISHED,
        target_type=NoticeTargetType.FLAT,
        target_flat_id=flat_id,
        published_at=datetime.now(UTC),
    )
    db_session.add(notice)
    db_session.commit()

    envelope = EventEnvelope(
        event_id=uuid.uuid4(),
        event_type="notice.published",
        aggregate_type="notice",
        aggregate_id=str(notice_id),
        metadata=EventMetadata(correlation_id=str(uuid.uuid4())),
        payload={
            "notice_id": str(notice_id),
            "society_id": str(society_id),
            "title": notice.title,
            "category": notice.category.value,
            "priority": notice.priority.value,
            "target_type": notice.target_type.value,
        },
    )

    success = dispatcher.dispatch_envelope(envelope, db_session)
    assert success is True

    # 1. Verify In-App Notification created for resident (Neeraj)
    notif = db_session.scalars(
        select(Notification).where(
            Notification.aggregate_id == str(notice_id),
            Notification.aggregate_type == "notice",
        )
    ).first()
    assert notif is not None
    assert notif.title == "Scheduled Water Tank Cleaning"
    assert notif.priority == NotificationPriority.NORMAL

    # 2. Verify all 3 channels delivered
    delivs = db_session.scalars(
        select(NotificationDelivery).where(NotificationDelivery.notification_id == notif.id)
    ).all()
    channels = {d.channel for d in delivs}
    assert NotificationChannel.IN_APP in channels
    assert NotificationChannel.EMAIL in channels
    assert NotificationChannel.SMS in channels

    # In test environment, mock providers execute and record delivery attempts
    in_app_deliv = next(d for d in delivs if d.channel == NotificationChannel.IN_APP)
    assert in_app_deliv.status == DeliveryStatus.DELIVERED

    email_deliv = next(d for d in delivs if d.channel == NotificationChannel.EMAIL)
    assert email_deliv.status == DeliveryStatus.SUPPRESSED
    assert email_deliv.last_error_code == "MOCK_PROVIDER_EXTERNAL_DELIVERY_DISABLED"

    sms_deliv = next(d for d in delivs if d.channel == NotificationChannel.SMS)
    assert sms_deliv.status == DeliveryStatus.SUPPRESSED
    assert sms_deliv.last_error_code == "MOCK_PROVIDER_EXTERNAL_DELIVERY_DISABLED"


def test_process_notice_published_respects_user_preferences(db_session: Session) -> None:
    """Verifies that non-emergency published notices respect resident opt-outs."""
    society_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    flat_id = uuid.UUID("33333333-3333-3333-3333-333333331203")
    staff_id = uuid.UUID("44444444-4444-4444-4444-444444440004")
    resident_id = uuid.UUID("44444444-4444-4444-4444-444444440001")

    # Disable email and SMS for resident
    svc = NotificationService(db_session)
    pref = svc.get_or_create_preferences(society_id, resident_id)
    pref.email_enabled = False
    pref.sms_enabled = False
    db_session.flush()

    notice_id = uuid.uuid4()
    notice = Notice(
        id=notice_id,
        society_id=society_id,
        author_id=staff_id,
        title="General Society Newsletter",
        body="Monthly gardening update and recycling reminders.",
        category=NoticeCategory.GENERAL,
        priority=NoticePriority.NORMAL,
        status=NoticeStatus.PUBLISHED,
        target_type=NoticeTargetType.FLAT,
        target_flat_id=flat_id,
        published_at=datetime.now(UTC),
    )
    db_session.add(notice)
    db_session.commit()

    envelope = EventEnvelope(
        event_id=uuid.uuid4(),
        event_type="notice.published",
        aggregate_type="notice",
        aggregate_id=str(notice_id),
        metadata=EventMetadata(correlation_id=str(uuid.uuid4())),
        payload={
            "notice_id": str(notice_id),
            "society_id": str(society_id),
            "title": notice.title,
            "category": notice.category.value,
        },
    )

    dispatcher.dispatch_envelope(envelope, db_session)

    # Deliveries for email and SMS should be suppressed by user preference
    delivs = db_session.scalars(
        select(NotificationDelivery).where(
            NotificationDelivery.society_id == society_id,
            NotificationDelivery.recipient_user_id == resident_id,
            NotificationDelivery.idempotency_key.like(f"%:{notice_id}:%"),
        )
    ).all()

    email_deliv = next(d for d in delivs if d.channel == NotificationChannel.EMAIL)
    assert email_deliv.status == DeliveryStatus.SUPPRESSED
    assert email_deliv.last_error_code == "PREFERENCE_EMAIL_DISABLED"

    sms_deliv = next(d for d in delivs if d.channel == NotificationChannel.SMS)
    assert sms_deliv.status == DeliveryStatus.SUPPRESSED
    assert sms_deliv.last_error_code == "PREFERENCE_SMS_DISABLED"


def test_process_emergency_broadcast_overrides_preferences_and_fans_out(
    db_session: Session,
) -> None:
    """CRITICAL SECURITY INVARIANT: Emergency broadcasts override resident channel opt-outs.

    Fans out across In-App, Email, and SMS with URGENT priority.
    """
    society_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    flat_id = uuid.UUID("33333333-3333-3333-3333-333333331203")
    staff_id = uuid.UUID("44444444-4444-4444-4444-444444440004")
    resident_id = uuid.UUID("44444444-4444-4444-4444-444444440001")

    # Disable all communication channels for resident
    svc = NotificationService(db_session)
    pref = svc.get_or_create_preferences(society_id, resident_id)
    pref.email_enabled = False
    pref.sms_enabled = False
    pref.in_app_enabled = False
    db_session.flush()

    notice_id = uuid.uuid4()
    notice = Notice(
        id=notice_id,
        society_id=society_id,
        author_id=staff_id,
        title="FIRE EVACUATION ALERT",
        body="Fire detected in Basement 1. Please evacuate via emergency stairs.",
        category=NoticeCategory.EMERGENCY,
        priority=NoticePriority.URGENT,
        status=NoticeStatus.PUBLISHED,
        target_type=NoticeTargetType.FLAT,
        target_flat_id=flat_id,
        published_at=datetime.now(UTC),
    )
    db_session.add(notice)
    db_session.commit()

    envelope = EventEnvelope(
        event_id=uuid.uuid4(),
        event_type="notice.emergency_broadcast",
        aggregate_type="notice",
        aggregate_id=str(notice_id),
        metadata=EventMetadata(correlation_id=str(uuid.uuid4())),
        payload={
            "notice_id": str(notice_id),
            "society_id": str(society_id),
            "title": notice.title,
            "category": notice.category.value,
            "priority": notice.priority.value,
            "target_type": notice.target_type.value,
        },
    )

    success = dispatcher.dispatch_envelope(envelope, db_session)
    assert success is True

    # 1. Verify In-App Notification exists with URGENT priority
    notif = db_session.scalars(
        select(Notification).where(
            Notification.aggregate_id == str(notice_id),
            Notification.aggregate_type == "notice",
        )
    ).first()
    assert notif is not None
    assert "FIRE EVACUATION ALERT" in notif.title
    assert notif.priority == NotificationPriority.URGENT

    # 2. Verify all channels were delivered (NOT suppressed by user preferences)
    delivs = db_session.scalars(
        select(NotificationDelivery).where(NotificationDelivery.notification_id == notif.id)
    ).all()
    channels = {d.channel for d in delivs}
    assert NotificationChannel.IN_APP in channels
    assert NotificationChannel.EMAIL in channels
    assert NotificationChannel.SMS in channels

    email_deliv = next(d for d in delivs if d.channel == NotificationChannel.EMAIL)
    # Must NOT be PREFERENCE_EMAIL_DISABLED
    assert email_deliv.last_error_code != "PREFERENCE_EMAIL_DISABLED"
    assert email_deliv.last_error_code == "MOCK_PROVIDER_EXTERNAL_DELIVERY_DISABLED"

    sms_deliv = next(d for d in delivs if d.channel == NotificationChannel.SMS)
    # Must NOT be PREFERENCE_SMS_DISABLED
    assert sms_deliv.last_error_code != "PREFERENCE_SMS_DISABLED"
    assert sms_deliv.last_error_code == "MOCK_PROVIDER_EXTERNAL_DELIVERY_DISABLED"


def test_notice_event_idempotency_prevents_duplicate_dispatches(db_session: Session) -> None:
    """Verifies that redelivered or duplicate notice events do not duplicate deliveries."""
    society_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    flat_id = uuid.UUID("33333333-3333-3333-3333-333333331203")
    staff_id = uuid.UUID("44444444-4444-4444-4444-444444440004")

    notice_id = uuid.uuid4()
    notice = Notice(
        id=notice_id,
        society_id=society_id,
        author_id=staff_id,
        title="Lift Maintenance Notice",
        body="Passenger elevator will be under maintenance from 3 PM to 5 PM.",
        category=NoticeCategory.MAINTENANCE,
        priority=NoticePriority.HIGH,
        status=NoticeStatus.PUBLISHED,
        target_type=NoticeTargetType.FLAT,
        target_flat_id=flat_id,
        published_at=datetime.now(UTC),
    )
    db_session.add(notice)
    db_session.commit()

    envelope = EventEnvelope(
        event_id=uuid.uuid4(),
        event_type="notice.published",
        aggregate_type="notice",
        aggregate_id=str(notice_id),
        metadata=EventMetadata(correlation_id=str(uuid.uuid4())),
        payload={
            "notice_id": str(notice_id),
            "society_id": str(society_id),
            "title": notice.title,
            "category": notice.category.value,
        },
    )

    # First dispatch
    dispatcher.dispatch_envelope(envelope, db_session)
    count_1 = len(
        list(
            db_session.scalars(
                select(NotificationDelivery).where(
                    NotificationDelivery.idempotency_key.like(f"%:{notice_id}:%")
                )
            ).all()
        )
    )
    assert count_1 == 3  # IN_APP, EMAIL, SMS

    # Second dispatch with identical notice
    dispatcher.dispatch_envelope(envelope, db_session)
    count_2 = len(
        list(
            db_session.scalars(
                select(NotificationDelivery).where(
                    NotificationDelivery.idempotency_key.like(f"%:{notice_id}:%")
                )
            ).all()
        )
    )
    # Deliveries MUST NOT duplicate
    assert count_2 == count_1


def test_notice_emergency_broadcast_transient_failure_retries(db_session: Session) -> None:
    """Verifies that transient errors during emergency broadcast dispatch trigger RETRYING state."""
    society_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    flat_id = uuid.UUID("33333333-3333-3333-3333-333333331203")
    staff_id = uuid.UUID("44444444-4444-4444-4444-444444440004")

    # Inject transient email provider
    transient_provider = SimulatedTransientEmailProvider()
    provider_registry.set_email_provider(transient_provider)

    try:
        notice_id = uuid.uuid4()
        notice = Notice(
            id=notice_id,
            society_id=society_id,
            author_id=staff_id,
            title="STORM ADVISORY",
            body="High winds expected. Secure all balcony items immediately.",
            category=NoticeCategory.EMERGENCY,
            priority=NoticePriority.URGENT,
            status=NoticeStatus.PUBLISHED,
            target_type=NoticeTargetType.FLAT,
            target_flat_id=flat_id,
            published_at=datetime.now(UTC),
        )
        db_session.add(notice)
        db_session.commit()

        envelope = EventEnvelope(
            event_id=uuid.uuid4(),
            event_type="notice.emergency_broadcast",
            aggregate_type="notice",
            aggregate_id=str(notice_id),
            metadata=EventMetadata(correlation_id=str(uuid.uuid4())),
            payload={
                "notice_id": str(notice_id),
                "society_id": str(society_id),
                "title": notice.title,
                "category": notice.category.value,
            },
        )

        dispatcher.dispatch_envelope(envelope, db_session)

        # Check that email delivery entered RETRYING state with backoff
        email_deliv = db_session.scalars(
            select(NotificationDelivery).where(
                NotificationDelivery.channel == NotificationChannel.EMAIL,
                NotificationDelivery.idempotency_key.like(f"%:{notice_id}:%"),
            )
        ).first()

        assert email_deliv is not None
        assert email_deliv.status == DeliveryStatus.RETRYING
        assert email_deliv.attempt_count == 1
        assert email_deliv.next_attempt_at is not None
        assert email_deliv.last_error_code == "ThrottlingException"

        # Check delivery attempt record
        attempts = db_session.scalars(
            select(NotificationDeliveryAttempt).where(
                NotificationDeliveryAttempt.delivery_id == email_deliv.id
            )
        ).all()
        assert len(attempts) == 1
        assert attempts[0].error_code == "ThrottlingException"
    finally:
        provider_registry.reset()
