"""Notification Domain Service

Coordinates:
- Multi-channel notification creation (In-App, Email, SMS)
- Domain event to notification payload mapping
- Active flat resident and operational staff recipient resolution
- User communication channel preference evaluation (with emergency bypass)
- Delivery state machine progression, backoff retries, and idempotency
- In-app inbox querying, unread counts, and mark-as-read transitions
"""

import math
import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ResourceNotFoundError
from app.core.logging import logger
from app.domains.identity.models import (
    Flat,
    FlatMembership,
    MembershipStatus,
    RoleType,
    User,
    UserRole,
    UserStatus,
)
from app.domains.notifications.models import (
    DeliveryStatus,
    Notice,
    NoticePriority,
    NoticeTargetType,
    Notification,
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryAttempt,
    NotificationPreference,
    NotificationPriority,
)
from app.domains.notifications.providers.base import (
    EmailProvider,
    SMSProvider,
)
from app.domains.notifications.providers.registry import provider_registry
from app.domains.notifications.schemas import (
    NotificationPreferenceSchema,
    NotificationResponseSchema,
    PaginatedNotificationsResponse,
    StaffDeliveryOverviewItem,
    StaffNotificationOverviewResponse,
    UpdateNotificationPreferenceRequest,
)
from app.messaging.envelope import EventEnvelope


def utc_now() -> datetime:
    return datetime.now(UTC)


class NotificationService:
    def __init__(
        self,
        db: Session,
        email_provider: EmailProvider | None = None,
        sms_provider: SMSProvider | None = None,
    ) -> None:
        self.db = db
        self.email_provider = email_provider or provider_registry.get_email_provider()
        self.sms_provider = sms_provider or provider_registry.get_sms_provider()

    # -------------------------------------------------------------------------
    # 1. Recipient Resolution
    # -------------------------------------------------------------------------

    def get_active_flat_residents(self, society_id: uuid.UUID, flat_id: uuid.UUID) -> list[User]:
        """Resolves all active, approved residents of the specified flat in the society."""
        now = utc_now()
        stmt = (
            select(User)
            .join(FlatMembership, FlatMembership.user_id == User.id)
            .where(
                FlatMembership.society_id == society_id,
                FlatMembership.flat_id == flat_id,
                FlatMembership.status == MembershipStatus.APPROVED,
                FlatMembership.valid_from <= now,
                or_(
                    FlatMembership.valid_until.is_(None),
                    FlatMembership.valid_until >= now,
                ),
                User.status == UserStatus.ACTIVE,
            )
        )
        return list(self.db.scalars(stmt).all())

    def get_staff_recipients(
        self,
        society_id: uuid.UUID,
        required_role: RoleType = RoleType.HELPDESK,
    ) -> list[User]:
        """Resolves active staff members for operational alerts within the society."""
        stmt = (
            select(User)
            .join(UserRole, UserRole.user_id == User.id)
            .where(
                UserRole.society_id == society_id,
                UserRole.role == required_role,
                User.status == UserStatus.ACTIVE,
            )
        )
        return list(self.db.scalars(stmt).all())

    def get_user_by_id(self, society_id: uuid.UUID, user_id: uuid.UUID) -> User | None:
        """Resolves single active user strictly verified within society context."""
        stmt = select(User).where(
            User.id == user_id,
            User.status == UserStatus.ACTIVE,
        )
        return self.db.scalars(stmt).first()

    def get_active_society_residents(self, society_id: uuid.UUID) -> list[User]:
        """Resolves all active, approved residents across the entire society."""
        now = utc_now()
        stmt = (
            select(User)
            .join(FlatMembership, FlatMembership.user_id == User.id)
            .where(
                FlatMembership.society_id == society_id,
                FlatMembership.status == MembershipStatus.APPROVED,
                or_(FlatMembership.valid_from.is_(None), FlatMembership.valid_from <= now),
                or_(FlatMembership.valid_until.is_(None), FlatMembership.valid_until >= now),
                User.status == UserStatus.ACTIVE,
            )
            .distinct()
        )
        return list(self.db.scalars(stmt).all())

    def get_notice_target_residents(self, notice: Notice) -> list[User]:
        """Resolves all active, approved residents within the notice's targeted scope."""
        now = utc_now()
        base_query = (
            select(User)
            .join(FlatMembership, FlatMembership.user_id == User.id)
            .where(
                FlatMembership.society_id == notice.society_id,
                FlatMembership.status == MembershipStatus.APPROVED,
                User.status == UserStatus.ACTIVE,
                or_(FlatMembership.valid_from.is_(None), FlatMembership.valid_from <= now),
                or_(FlatMembership.valid_until.is_(None), FlatMembership.valid_until >= now),
            )
        )

        if notice.target_type == NoticeTargetType.TOWER:
            tower_uuids: list[uuid.UUID] = []
            for t in notice.target_tower_ids or []:
                try:
                    tower_uuids.append(uuid.UUID(str(t)))
                except (ValueError, TypeError):
                    continue
            if not tower_uuids and notice.target_tower_id:
                tower_uuids.append(notice.target_tower_id)
            if not tower_uuids and hasattr(notice, "targets") and notice.targets:
                tower_uuids = [
                    t.target_id for t in notice.targets if t.target_type == NoticeTargetType.TOWER
                ]
            if not tower_uuids:
                return []
            base_query = base_query.join(Flat, Flat.id == FlatMembership.flat_id).where(
                Flat.tower_id.in_(tower_uuids)
            )
        elif notice.target_type == NoticeTargetType.FLAT:
            flat_uuids: list[uuid.UUID] = []
            for f in notice.target_flat_ids or []:
                try:
                    flat_uuids.append(uuid.UUID(str(f)))
                except (ValueError, TypeError):
                    continue
            if not flat_uuids and notice.target_flat_id:
                flat_uuids.append(notice.target_flat_id)
            if not flat_uuids and hasattr(notice, "targets") and notice.targets:
                flat_uuids = [
                    t.target_id for t in notice.targets if t.target_type == NoticeTargetType.FLAT
                ]
            if not flat_uuids:
                return []
            base_query = base_query.where(FlatMembership.flat_id.in_(flat_uuids))

        return list(self.db.scalars(base_query.distinct()).all())

    # -------------------------------------------------------------------------
    # 2. Preference Resolution & Enforcement
    # -------------------------------------------------------------------------

    def get_or_create_preferences(
        self, society_id: uuid.UUID, user_id: uuid.UUID
    ) -> NotificationPreference:
        stmt = select(NotificationPreference).where(
            NotificationPreference.society_id == society_id,
            NotificationPreference.user_id == user_id,
        )
        pref = self.db.scalars(stmt).first()
        if not pref:
            pref = NotificationPreference(
                id=uuid.uuid4(),
                society_id=society_id,
                user_id=user_id,
                email_enabled=True,
                sms_enabled=True,
                in_app_enabled=True,
                billing_email=True,
                billing_sms=True,
                complaints_email=True,
                complaints_sms=True,
                visitor_sms=True,
            )
            self.db.add(pref)
            self.db.flush()
        return pref

    def is_channel_permitted(
        self,
        pref: NotificationPreference,
        channel: NotificationChannel,
        event_type: str,
        priority: NotificationPriority,
    ) -> tuple[bool, str]:
        """Evaluates whether channel is permitted by preferences.

        CRITICAL SECURITY INVARIANT: Mandatory emergency alerts (URGENT priority or safety escalations)
        cannot be suppressed by user channel preferences.
        """
        if (
            priority == NotificationPriority.URGENT
            or "safety_escalated" in event_type
            or "emergency" in event_type
        ):
            return True, "MANDATORY_EMERGENCY_OVERRIDE"

        domain = event_type.split(".")[0].lower()

        if channel == NotificationChannel.IN_APP:
            if not pref.in_app_enabled:
                return False, "PREFERENCE_IN_APP_DISABLED"
            return True, "PERMITTED"

        if channel == NotificationChannel.EMAIL:
            if not pref.email_enabled:
                return False, "PREFERENCE_EMAIL_DISABLED"
            if domain == "billing" and not pref.billing_email:
                return False, "PREFERENCE_BILLING_EMAIL_DISABLED"
            if domain == "complaint" and not pref.complaints_email:
                return False, "PREFERENCE_COMPLAINTS_EMAIL_DISABLED"
            return True, "PERMITTED"

        if channel == NotificationChannel.SMS:
            if not pref.sms_enabled:
                return False, "PREFERENCE_SMS_DISABLED"
            if domain == "billing" and not pref.billing_sms:
                return False, "PREFERENCE_BILLING_SMS_DISABLED"
            if domain == "complaint" and not pref.complaints_sms:
                return False, "PREFERENCE_COMPLAINTS_SMS_DISABLED"
            if domain == "visitor" and not pref.visitor_sms:
                return False, "PREFERENCE_VISITOR_SMS_DISABLED"
            return True, "PERMITTED"

        return True, "PERMITTED"

    # -------------------------------------------------------------------------
    # 3. Notification Dispatch & Delivery State Machine
    # -------------------------------------------------------------------------

    def create_in_app_notification(
        self,
        society_id: uuid.UUID,
        recipient: User,
        event_type: str,
        title: str,
        body: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        aggregate_type: str | None = None,
        aggregate_id: str | None = None,
        action_url: str | None = None,
        event_metadata: dict[str, Any] | None = None,
        base_event_id: uuid.UUID | None = None,
    ) -> Notification:
        """Persists durable in-app notification in database inbox with idempotency."""
        now = utc_now()
        delivery_key = (
            f"in_app:{base_event_id}:{recipient.id}"
            if base_event_id
            else f"in_app:{uuid.uuid4()}:{recipient.id}"
        )

        if base_event_id:
            existing_deliv = self.db.scalars(
                select(NotificationDelivery).where(
                    NotificationDelivery.idempotency_key == delivery_key
                )
            ).first()
            if existing_deliv and existing_deliv.notification_id:
                existing_notif = self.db.get(Notification, existing_deliv.notification_id)
                if existing_notif:
                    return existing_notif

        notification = Notification(
            id=uuid.uuid4(),
            society_id=society_id,
            recipient_user_id=recipient.id,
            event_type=event_type,
            title=title,
            body=body,
            channel=NotificationChannel.IN_APP,
            priority=priority,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            action_url=action_url,
            event_metadata=event_metadata or {},
            created_at=now,
            updated_at=now,
        )
        self.db.add(notification)
        self.db.flush()

        # In-app delivery record is immediately marked DELIVERED upon database persistence
        delivery = NotificationDelivery(
            id=uuid.uuid4(),
            notification_id=notification.id,
            society_id=society_id,
            recipient_user_id=recipient.id,
            channel=NotificationChannel.IN_APP,
            provider="in_app",
            status=DeliveryStatus.DELIVERED,
            idempotency_key=delivery_key,
            delivered_at=now,
            created_at=now,
            updated_at=now,
        )
        self.db.add(delivery)
        self.db.flush()
        return notification

    def dispatch_email_delivery(
        self,
        notification: Notification,
        recipient: User,
        subject: str,
        body_text: str,
        body_html: str | None = None,
        base_event_id: uuid.UUID | None = None,
        is_suppressed: bool = False,
        suppression_reason: str | None = None,
        custom_idempotency_key: str | None = None,
    ) -> NotificationDelivery:
        """Dispatches external transactional email with idempotency and state machine tracking."""
        now = utc_now()
        event_ref = base_event_id or notification.id
        idempotency_key = custom_idempotency_key or f"email:{event_ref}:{recipient.id}"

        # 1. Idempotency Check
        existing = self.db.scalars(
            select(NotificationDelivery).where(
                NotificationDelivery.idempotency_key == idempotency_key
            )
        ).first()
        if existing:
            logger.info(
                f"[NotificationService] Email delivery for idempotency_key '{idempotency_key}' already exists; skipping duplicate"
            )
            return existing

        delivery = NotificationDelivery(
            id=uuid.uuid4(),
            notification_id=notification.id,
            society_id=notification.society_id,
            recipient_user_id=recipient.id,
            channel=NotificationChannel.EMAIL,
            provider=self.email_provider.provider_name,
            status=DeliveryStatus.PENDING,
            idempotency_key=idempotency_key,
            created_at=now,
            updated_at=now,
        )
        self.db.add(delivery)
        self.db.flush()

        if is_suppressed:
            delivery.status = DeliveryStatus.SUPPRESSED
            delivery.last_error_code = suppression_reason or "SUPPRESSED_BY_PREFERENCE"
            delivery.last_error_message = "Delivery suppressed per user preference or policy"
            self._record_delivery_attempt(
                delivery=delivery,
                status=DeliveryStatus.SUPPRESSED,
                error_code=delivery.last_error_code,
                error_details=delivery.last_error_message,
            )
            return delivery

        if not recipient.email:
            delivery.status = DeliveryStatus.SUPPRESSED
            delivery.last_error_code = "NO_RECIPIENT_EMAIL"
            delivery.last_error_message = "Recipient user record has no email address configured"
            self._record_delivery_attempt(
                delivery=delivery,
                status=DeliveryStatus.SUPPRESSED,
                error_code=delivery.last_error_code,
                error_details=delivery.last_error_message,
            )
            return delivery

        # 2. Dispatch to provider
        delivery.status = DeliveryStatus.PROCESSING
        self.db.flush()

        result = self.email_provider.send_email(
            to_email=recipient.email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            idempotency_key=idempotency_key,
        )

        delivery.attempt_count += 1
        delivery.status = result.status
        delivery.provider_message_id = result.provider_message_id
        delivery.last_error_code = result.error_code
        delivery.last_error_message = result.error_message
        if result.status in (DeliveryStatus.SENT, DeliveryStatus.DELIVERED):
            delivery.sent_at = now
            if result.status == DeliveryStatus.DELIVERED:
                delivery.delivered_at = now
        elif result.status == DeliveryStatus.FAILED and result.is_transient:
            delivery.status = DeliveryStatus.RETRYING
            backoff_sec = (2**delivery.attempt_count) * 10 + random.randint(1, 5)
            delivery.next_attempt_at = now + timedelta(seconds=backoff_sec)

        self._record_delivery_attempt(
            delivery=delivery,
            status=result.status,
            provider_reference=result.provider_reference or result.provider_message_id,
            error_code=result.error_code,
            error_details=result.error_message,
        )
        return delivery

    def dispatch_sms_delivery(
        self,
        notification: Notification,
        recipient: User,
        message: str,
        base_event_id: uuid.UUID | None = None,
        is_suppressed: bool = False,
        suppression_reason: str | None = None,
        custom_idempotency_key: str | None = None,
    ) -> NotificationDelivery:
        """Dispatches external transactional SMS with idempotency and state machine tracking."""
        now = utc_now()
        event_ref = base_event_id or notification.id
        idempotency_key = custom_idempotency_key or f"sms:{event_ref}:{recipient.id}"

        existing = self.db.scalars(
            select(NotificationDelivery).where(
                NotificationDelivery.idempotency_key == idempotency_key
            )
        ).first()
        if existing:
            logger.info(
                f"[NotificationService] SMS delivery for idempotency_key '{idempotency_key}' already exists; skipping duplicate"
            )
            return existing

        delivery = NotificationDelivery(
            id=uuid.uuid4(),
            notification_id=notification.id,
            society_id=notification.society_id,
            recipient_user_id=recipient.id,
            channel=NotificationChannel.SMS,
            provider=self.sms_provider.provider_name,
            status=DeliveryStatus.PENDING,
            idempotency_key=idempotency_key,
            created_at=now,
            updated_at=now,
        )
        self.db.add(delivery)
        self.db.flush()

        if is_suppressed:
            delivery.status = DeliveryStatus.SUPPRESSED
            delivery.last_error_code = suppression_reason or "SUPPRESSED_BY_PREFERENCE"
            delivery.last_error_message = "Delivery suppressed per user preference or policy"
            self._record_delivery_attempt(
                delivery=delivery,
                status=DeliveryStatus.SUPPRESSED,
                error_code=delivery.last_error_code,
                error_details=delivery.last_error_message,
            )
            return delivery

        if not recipient.phone:
            delivery.status = DeliveryStatus.SUPPRESSED
            delivery.last_error_code = "NO_RECIPIENT_PHONE"
            delivery.last_error_message = "Recipient user record has no phone number configured"
            self._record_delivery_attempt(
                delivery=delivery,
                status=DeliveryStatus.SUPPRESSED,
                error_code=delivery.last_error_code,
                error_details=delivery.last_error_message,
            )
            return delivery

        delivery.status = DeliveryStatus.PROCESSING
        self.db.flush()

        result = self.sms_provider.send_sms(
            to_phone=recipient.phone,
            message=message,
            idempotency_key=idempotency_key,
        )

        delivery.attempt_count += 1
        delivery.status = result.status
        delivery.provider_message_id = result.provider_message_id
        delivery.last_error_code = result.error_code
        delivery.last_error_message = result.error_message
        if result.status in (DeliveryStatus.SENT, DeliveryStatus.DELIVERED):
            delivery.sent_at = now
            if result.status == DeliveryStatus.DELIVERED:
                delivery.delivered_at = now
        elif result.status == DeliveryStatus.FAILED and result.is_transient:
            delivery.status = DeliveryStatus.RETRYING
            backoff_sec = (2**delivery.attempt_count) * 10 + random.randint(1, 5)
            delivery.next_attempt_at = now + timedelta(seconds=backoff_sec)

        self._record_delivery_attempt(
            delivery=delivery,
            status=result.status,
            provider_reference=result.provider_reference or result.provider_message_id,
            error_code=result.error_code,
            error_details=result.error_message,
        )
        return delivery

    def _record_delivery_attempt(
        self,
        delivery: NotificationDelivery,
        status: DeliveryStatus,
        provider_reference: str | None = None,
        error_code: str | None = None,
        error_details: str | None = None,
    ) -> NotificationDeliveryAttempt:
        attempt = NotificationDeliveryAttempt(
            id=uuid.uuid4(),
            delivery_id=delivery.id,
            attempt_number=delivery.attempt_count or 1,
            provider=delivery.provider,
            status=status,
            provider_reference=provider_reference,
            error_code=error_code,
            error_details=error_details[:500] if error_details else None,
            attempted_at=utc_now(),
        )
        self.db.add(attempt)
        self.db.flush()
        return attempt

    # -------------------------------------------------------------------------
    # 4. Centralized Domain Event Processing & Mapping
    # -------------------------------------------------------------------------

    def process_domain_event(self, envelope: EventEnvelope) -> int:
        """Central event dispatcher turning domain events into multi-channel notifications.

        Returns total count of notifications created.
        """
        payload = envelope.payload if isinstance(envelope.payload, dict) else {}
        society_id_raw = payload.get("society_id")
        if not society_id_raw:
            logger.warning(
                f"[NotificationService] Event {envelope.event_id} ({envelope.event_type}) has no society_id; cannot process"
            )
            return 0

        society_id = uuid.UUID(str(society_id_raw))
        event_type = envelope.event_type
        created_count = 0

        # --- A. BILLING EVENTS ---
        if event_type == "billing.invoice_generated":
            flat_id = uuid.UUID(str(payload["flat_id"]))
            invoice_number = payload.get("invoice_number", "INV-UNKNOWN")
            amount_paise = payload.get("total_amount_paise", 0)
            amount_str = f"₹{amount_paise / 100:,.2f}"
            due_date = payload.get("due_date", "Due upon receipt")

            residents = self.get_active_flat_residents(society_id, flat_id)
            for resident in residents:
                pref = self.get_or_create_preferences(society_id, resident.id)
                perm_in_app, _ = self.is_channel_permitted(
                    pref, NotificationChannel.IN_APP, event_type, NotificationPriority.NORMAL
                )
                if perm_in_app:
                    notif = self.create_in_app_notification(
                        society_id=society_id,
                        recipient=resident,
                        event_type=event_type,
                        title="New Maintenance Invoice Generated",
                        body=f"Maintenance invoice #{invoice_number} of {amount_str} is now available for your unit. Due date: {due_date}.",
                        priority=NotificationPriority.NORMAL,
                        aggregate_type="billing_invoice",
                        aggregate_id=str(envelope.aggregate_id),
                        action_url="/resident/billing",
                        base_event_id=envelope.event_id,
                    )
                    created_count += 1

                    # Email channel
                    perm_email, reason_email = self.is_channel_permitted(
                        pref, NotificationChannel.EMAIL, event_type, NotificationPriority.NORMAL
                    )
                    self.dispatch_email_delivery(
                        notification=notif,
                        recipient=resident,
                        subject=f"Maintenance Invoice #{invoice_number} - Marvel Greenfield",
                        body_text=f"Dear Resident,\n\nYour maintenance invoice #{invoice_number} for {amount_str} has been generated.\nDue date: {due_date}.\n\nPlease log in to the resident portal to complete payment.\n\nTownship Management",
                        base_event_id=envelope.event_id,
                        is_suppressed=not perm_email,
                        suppression_reason=reason_email,
                    )

        elif event_type == "billing.run_completed":
            period = payload.get("period", "Monthly")
            count = payload.get("invoices_count", 0)
            total_paise = payload.get("total_amount_paise", 0)
            total_str = f"₹{total_paise / 100:,.2f}"

            staff_list = self.get_staff_recipients(society_id, RoleType.HELPDESK)
            for staff in staff_list:
                pref = self.get_or_create_preferences(society_id, staff.id)
                perm_in_app, _ = self.is_channel_permitted(
                    pref, NotificationChannel.IN_APP, event_type, NotificationPriority.NORMAL
                )
                if perm_in_app:
                    self.create_in_app_notification(
                        society_id=society_id,
                        recipient=staff,
                        event_type=event_type,
                        title="Billing Run Completed",
                        body=f"Maintenance billing run completed for period {period}. Generated {count} invoices totaling {total_str}.",
                        priority=NotificationPriority.NORMAL,
                        aggregate_type="billing_run",
                        aggregate_id=str(envelope.aggregate_id),
                        action_url="/staff/overview",
                        base_event_id=envelope.event_id,
                    )
                    created_count += 1

        elif event_type in ("billing.payment_succeeded", "payment.succeeded"):
            amount_paise = payload.get("amount_paise", 0)
            amount_str = f"₹{amount_paise / 100:,.2f}"
            ref_no = (
                payload.get("payment_reference")
                or payload.get("provider_reference")
                or payload.get("reference_number", "N/A")
            )
            invoice_num = payload.get("invoice_number", "")

            user_id_raw = payload.get("user_id") or payload.get("created_by")
            recipients: list[User] = []
            if user_id_raw:
                u = self.get_user_by_id(society_id, uuid.UUID(str(user_id_raw)))
                if u:
                    recipients.append(u)
            if not recipients and payload.get("flat_id"):
                recipients = self.get_active_flat_residents(
                    society_id, uuid.UUID(str(payload["flat_id"]))
                )

            for resident in recipients:
                pref = self.get_or_create_preferences(society_id, resident.id)
                notif = self.create_in_app_notification(
                    society_id=society_id,
                    recipient=resident,
                    event_type=event_type,
                    title="Payment Received Successfully",
                    body=f"Your payment of {amount_str} (Ref: {ref_no}) has been confirmed and credited toward invoice #{invoice_num}."
                    if invoice_num
                    else f"Your payment of {amount_str} (Ref: {ref_no}) has been received successfully.",
                    priority=NotificationPriority.NORMAL,
                    aggregate_type="payment",
                    aggregate_id=str(envelope.aggregate_id),
                    action_url="/resident/payments",
                    base_event_id=envelope.event_id,
                )
                created_count += 1

                # Email
                perm_email, reason_email = self.is_channel_permitted(
                    pref, NotificationChannel.EMAIL, event_type, NotificationPriority.NORMAL
                )
                self.dispatch_email_delivery(
                    notification=notif,
                    recipient=resident,
                    subject=f"Payment Receipt: {amount_str} - Marvel Greenfield",
                    body_text=f"Dear Resident,\n\nWe have successfully received your payment of {amount_str}.\nPayment Reference: {ref_no}.\n\nThank you,\nTownship Finance Office",
                    base_event_id=envelope.event_id,
                    is_suppressed=not perm_email,
                    suppression_reason=reason_email,
                )

                # SMS
                perm_sms, reason_sms = self.is_channel_permitted(
                    pref, NotificationChannel.SMS, event_type, NotificationPriority.NORMAL
                )
                self.dispatch_sms_delivery(
                    notification=notif,
                    recipient=resident,
                    message=f"Marvel Greenfield: Payment of {amount_str} received successfully. Ref: {ref_no}. Thank you.",
                    base_event_id=envelope.event_id,
                    is_suppressed=not perm_sms,
                    suppression_reason=reason_sms,
                )

        elif event_type in ("billing.payment_failed", "payment.failed"):
            amount_paise = payload.get("amount_paise", 0)
            amount_str = f"₹{amount_paise / 100:,.2f}"
            reason = payload.get("failure_reason", "Bank transaction declined or timed out")

            user_id_raw = payload.get("user_id") or payload.get("created_by")
            recipients = []
            if user_id_raw:
                u = self.get_user_by_id(society_id, uuid.UUID(str(user_id_raw)))
                if u:
                    recipients.append(u)

            for resident in recipients:
                pref = self.get_or_create_preferences(society_id, resident.id)
                notif = self.create_in_app_notification(
                    society_id=society_id,
                    recipient=resident,
                    event_type=event_type,
                    title="Payment Failed",
                    body=f"Your online payment attempt of {amount_str} was unsuccessful: {reason}.",
                    priority=NotificationPriority.HIGH,
                    aggregate_type="payment",
                    aggregate_id=str(envelope.aggregate_id),
                    action_url="/resident/billing",
                    base_event_id=envelope.event_id,
                )
                created_count += 1

                perm_email, reason_email = self.is_channel_permitted(
                    pref, NotificationChannel.EMAIL, event_type, NotificationPriority.HIGH
                )
                self.dispatch_email_delivery(
                    notification=notif,
                    recipient=resident,
                    subject="Payment Unsuccessful - Marvel Greenfield",
                    body_text=f"Dear Resident,\n\nYour payment attempt of {amount_str} failed with error: {reason}.\nPlease retry through the portal or contact management if the amount was debited.\n\nTownship Office",
                    base_event_id=envelope.event_id,
                    is_suppressed=not perm_email,
                    suppression_reason=reason_email,
                )

        elif event_type == "billing.invoice_paid":
            invoice_num = payload.get("invoice_number", "INV-UNKNOWN")
            if payload.get("flat_id"):
                residents = self.get_active_flat_residents(
                    society_id, uuid.UUID(str(payload["flat_id"]))
                )
                for resident in residents:
                    self.create_in_app_notification(
                        society_id=society_id,
                        recipient=resident,
                        event_type=event_type,
                        title="Invoice Settled",
                        body=f"Maintenance invoice #{invoice_num} has been fully settled and paid.",
                        priority=NotificationPriority.LOW,
                        aggregate_type="billing_invoice",
                        aggregate_id=str(envelope.aggregate_id),
                        action_url="/resident/billing",
                        base_event_id=envelope.event_id,
                    )
                    created_count += 1

        # --- B. COMPLAINTS & HELPDESK EVENTS ---
        elif event_type == "complaint.created":
            complaint_num = payload.get("complaint_number", "TICKET-UNKNOWN")
            title = payload.get("title", "Service Request")
            creator_id_raw = payload.get("resident_user_id") or payload.get("created_by")

            if creator_id_raw:
                creator = self.get_user_by_id(society_id, uuid.UUID(str(creator_id_raw)))
                if creator:
                    pref = self.get_or_create_preferences(society_id, creator.id)
                    notif = self.create_in_app_notification(
                        society_id=society_id,
                        recipient=creator,
                        event_type=event_type,
                        title="Complaint Ticket Logged",
                        body=f"Your complaint ticket #{complaint_num} ('{title}') has been logged and assigned to facility triage.",
                        priority=NotificationPriority.NORMAL,
                        aggregate_type="complaint",
                        aggregate_id=str(envelope.aggregate_id),
                        action_url="/resident/complaints",
                        base_event_id=envelope.event_id,
                    )
                    created_count += 1

                    perm_email, reason_email = self.is_channel_permitted(
                        pref, NotificationChannel.EMAIL, event_type, NotificationPriority.NORMAL
                    )
                    self.dispatch_email_delivery(
                        notification=notif,
                        recipient=creator,
                        subject=f"Complaint Logged: #{complaint_num} - {title}",
                        body_text=f"Dear Resident,\n\nYour complaint #{complaint_num} ('{title}') has been received.\nOur facility team has been notified and will investigate according to SLA guidelines.\n\nTownship Helpdesk",
                        base_event_id=envelope.event_id,
                        is_suppressed=not perm_email,
                        suppression_reason=reason_email,
                    )

        elif event_type == "complaint.safety_escalated":
            complaint_num = payload.get("complaint_number", "EMERGENCY")
            reason = payload.get(
                "escalation_reason", "Critical safety or hazardous situation detected"
            )
            creator_id_raw = payload.get("resident_user_id")

            # 1. Alert all operational helpdesk staff immediately (Mandatory)
            staff_list = self.get_staff_recipients(society_id, RoleType.HELPDESK)
            for staff in staff_list:
                notif = self.create_in_app_notification(
                    society_id=society_id,
                    recipient=staff,
                    event_type=event_type,
                    title="CRITICAL SAFETY ESCALATION",
                    body=f"URGENT: Ticket #{complaint_num} escalated as critical safety hazard: {reason}. Immediate response required.",
                    priority=NotificationPriority.URGENT,
                    aggregate_type="complaint",
                    aggregate_id=str(envelope.aggregate_id),
                    action_url="/staff/helpdesk",
                    base_event_id=envelope.event_id,
                )
                created_count += 1

                # Send SMS and Email to staff (Bypasses preference opt-outs)
                self.dispatch_sms_delivery(
                    notification=notif,
                    recipient=staff,
                    message=f"SAFETY ALERT: Ticket #{complaint_num} escalated: {reason}. Immediate on-site response required.",
                    base_event_id=envelope.event_id,
                )
                self.dispatch_email_delivery(
                    notification=notif,
                    recipient=staff,
                    subject=f"URGENT SAFETY ALERT: Ticket #{complaint_num}",
                    body_text=f"EMERGENCY RESPONSE REQUIRED:\n\nTicket: #{complaint_num}\nReason: {reason}\n\nPlease mobilize facility emergency team immediately.",
                    base_event_id=envelope.event_id,
                )

            # 2. Inform resident that safety escalation has been triggered
            if creator_id_raw:
                creator = self.get_user_by_id(society_id, uuid.UUID(str(creator_id_raw)))
                if creator:
                    notif = self.create_in_app_notification(
                        society_id=society_id,
                        recipient=creator,
                        event_type=event_type,
                        title="Safety Alert Dispatched to Emergency Team",
                        body=f"Your ticket #{complaint_num} has been escalated for priority safety response. Facility management is mobilized.",
                        priority=NotificationPriority.URGENT,
                        aggregate_type="complaint",
                        aggregate_id=str(envelope.aggregate_id),
                        action_url="/resident/complaints",
                        base_event_id=envelope.event_id,
                    )
                    created_count += 1

        elif event_type == "complaint.assigned":
            complaint_num = payload.get("complaint_number", "TICKET-UNKNOWN")
            title = payload.get("title", "Assigned Task")
            assigned_to_raw = payload.get("assigned_to_user_id") or payload.get("assigned_to")

            if assigned_to_raw:
                assigned_user = self.get_user_by_id(society_id, uuid.UUID(str(assigned_to_raw)))
                if assigned_user:
                    notif = self.create_in_app_notification(
                        society_id=society_id,
                        recipient=assigned_user,
                        event_type=event_type,
                        title="New Ticket Assigned to You",
                        body=f"Ticket #{complaint_num} ('{title}') has been assigned to you for resolution.",
                        priority=NotificationPriority.NORMAL,
                        aggregate_type="complaint",
                        aggregate_id=str(envelope.aggregate_id),
                        action_url="/staff/helpdesk",
                        base_event_id=envelope.event_id,
                    )
                    created_count += 1

                    self.dispatch_email_delivery(
                        notification=notif,
                        recipient=assigned_user,
                        subject=f"Ticket Assigned: #{complaint_num} - {title}",
                        body_text=f"Hello {assigned_user.full_name},\n\nYou have been assigned complaint ticket #{complaint_num}: '{title}'.\nPlease log in to the staff console to review details and begin resolution.",
                        base_event_id=envelope.event_id,
                    )

        elif event_type in (
            "complaint.status_changed",
            "complaint.resolved",
            "complaint.reopened",
        ):
            complaint_num = payload.get("complaint_number", "TICKET-UNKNOWN")
            status = payload.get("new_status") or payload.get("status", "UPDATED")
            # CRITICAL SECURITY RULE: Private internal helpdesk notes are strictly excluded from resident messages
            public_comment = (
                payload.get("public_message") or f"Ticket status transitioned to {status}."
            )

            creator_id_raw = payload.get("resident_user_id") or payload.get("created_by")
            if creator_id_raw:
                creator = self.get_user_by_id(society_id, uuid.UUID(str(creator_id_raw)))
                if creator:
                    pref = self.get_or_create_preferences(society_id, creator.id)
                    notif = self.create_in_app_notification(
                        society_id=society_id,
                        recipient=creator,
                        event_type=event_type,
                        title=f"Complaint Status: {status}",
                        body=f"Ticket #{complaint_num}: {public_comment}",
                        priority=NotificationPriority.NORMAL,
                        aggregate_type="complaint",
                        aggregate_id=str(envelope.aggregate_id),
                        action_url="/resident/complaints",
                        base_event_id=envelope.event_id,
                    )
                    created_count += 1

                    perm_email, reason_email = self.is_channel_permitted(
                        pref, NotificationChannel.EMAIL, event_type, NotificationPriority.NORMAL
                    )
                    self.dispatch_email_delivery(
                        notification=notif,
                        recipient=creator,
                        subject=f"Complaint #{complaint_num} Update: {status}",
                        body_text=f"Dear Resident,\n\nYour complaint #{complaint_num} status has been updated to: {status}.\nDetails: {public_comment}\n\nTownship Helpdesk",
                        base_event_id=envelope.event_id,
                        is_suppressed=not perm_email,
                        suppression_reason=reason_email,
                    )

        # --- C. GATE VISITOR & PASS EVENTS ---
        elif event_type == "visitor.approval_requested":
            visitor_name = payload.get("visitor_name", "Visitor")
            purpose = payload.get("purpose", "Visit")
            gate_name = payload.get("gate_name", "Main Gate")
            flat_id = uuid.UUID(str(payload["destination_flat_id"]))

            residents = self.get_active_flat_residents(society_id, flat_id)
            for resident in residents:
                pref = self.get_or_create_preferences(society_id, resident.id)
                notif = self.create_in_app_notification(
                    society_id=society_id,
                    recipient=resident,
                    event_type=event_type,
                    title="Visitor Awaiting Approval at Gate",
                    body=f"{visitor_name} is at {gate_name} requesting entry for purpose: {purpose}. Please approve or reject.",
                    priority=NotificationPriority.HIGH,
                    aggregate_type="visitor",
                    aggregate_id=str(envelope.aggregate_id),
                    action_url="/resident/visitors",
                    base_event_id=envelope.event_id,
                )
                created_count += 1

                # SMS for visitor approvals
                perm_sms, reason_sms = self.is_channel_permitted(
                    pref, NotificationChannel.SMS, event_type, NotificationPriority.HIGH
                )
                self.dispatch_sms_delivery(
                    notification=notif,
                    recipient=resident,
                    message=f"Gate Alert: {visitor_name} is at {gate_name} for {purpose}. Approve/reject in portal: https://marvelgreenfield.com/resident/visitors",
                    base_event_id=envelope.event_id,
                    is_suppressed=not perm_sms,
                    suppression_reason=reason_sms,
                )

        elif event_type in ("visitor.approved", "visitor.rejected"):
            visitor_name = payload.get("visitor_name", "Visitor")
            action_status = "Approved" if event_type.endswith("approved") else "Rejected"
            flat_id = uuid.UUID(str(payload["destination_flat_id"]))

            residents = self.get_active_flat_residents(society_id, flat_id)
            for resident in residents:
                self.create_in_app_notification(
                    society_id=society_id,
                    recipient=resident,
                    event_type=event_type,
                    title=f"Visitor {action_status}",
                    body=f"Visitor registration for {visitor_name} was {action_status.lower()}.",
                    priority=NotificationPriority.NORMAL,
                    aggregate_type="visitor",
                    aggregate_id=str(envelope.aggregate_id),
                    action_url="/resident/visitors",
                    base_event_id=envelope.event_id,
                )
                created_count += 1

        elif event_type == "visitor.checked_in":
            visitor_name = payload.get("visitor_name", "Visitor")
            gate_name = payload.get("gate_name", "Gate")
            flat_id = uuid.UUID(str(payload["destination_flat_id"]))

            residents = self.get_active_flat_residents(society_id, flat_id)
            for resident in residents:
                self.create_in_app_notification(
                    society_id=society_id,
                    recipient=resident,
                    event_type=event_type,
                    title="Visitor Checked In",
                    body=f"{visitor_name} entered premises via {gate_name}.",
                    priority=NotificationPriority.LOW,
                    aggregate_type="visitor",
                    aggregate_id=str(envelope.aggregate_id),
                    action_url="/resident/visitors",
                    base_event_id=envelope.event_id,
                )
                created_count += 1

        elif event_type == "pass.revoked":
            pass_code = payload.get("pass_code_prefix", "Guest Pass")
            flat_id_raw = payload.get("flat_id") or payload.get("destination_flat_id")
            if flat_id_raw:
                residents = self.get_active_flat_residents(society_id, uuid.UUID(str(flat_id_raw)))
                for resident in residents:
                    self.create_in_app_notification(
                        society_id=society_id,
                        recipient=resident,
                        event_type=event_type,
                        title="Guest Pass Revoked",
                        body=f"Guest pass ({pass_code}...) has been revoked and can no longer be used for entry.",
                        priority=NotificationPriority.NORMAL,
                        aggregate_type="guest_pass",
                        aggregate_id=str(envelope.aggregate_id),
                        action_url="/resident/visitors",
                        base_event_id=envelope.event_id,
                    )
                    created_count += 1

        # --- E. AMENITY BOOKING EVENTS ---
        elif event_type == "amenity.booking_created":
            user_id_raw = payload.get("user_id")
            amenity_name = payload.get("amenity_name", "Amenity")
            b_date = payload.get("booking_date", "")
            s_time = payload.get("start_time", "")
            e_time = payload.get("end_time", "")
            fee_paise = payload.get("booking_fee_paise", 0)
            fee_str = f"₹{fee_paise / 100:,.2f}"
            if user_id_raw:
                user = self.get_user_by_id(society_id, uuid.UUID(str(user_id_raw)))
                if user:
                    self.create_in_app_notification(
                        society_id=society_id,
                        recipient=user,
                        event_type=event_type,
                        title="Amenity Booking Reserved (Pending Payment)",
                        body=f"Your booking for {amenity_name} on {b_date} ({s_time}-{e_time}) is reserved pending payment of {fee_str}.",
                        priority=NotificationPriority.NORMAL,
                        aggregate_type="amenity_booking",
                        aggregate_id=str(envelope.aggregate_id),
                        action_url="/resident/amenities",
                        base_event_id=envelope.event_id,
                    )
                    created_count += 1

        elif event_type == "amenity.booking_confirmed":
            user_id_raw = payload.get("user_id")
            amenity_name = payload.get("amenity_name", "Amenity")
            b_date = payload.get("booking_date", "")
            s_time = payload.get("start_time", "")
            e_time = payload.get("end_time", "")
            fee_paise = payload.get("booking_fee_paise", 0)
            fee_str = f" (Fee: ₹{fee_paise / 100:,.2f})" if fee_paise > 0 else " (Free)"
            if user_id_raw:
                user = self.get_user_by_id(society_id, uuid.UUID(str(user_id_raw)))
                if user:
                    self.create_in_app_notification(
                        society_id=society_id,
                        recipient=user,
                        event_type=event_type,
                        title="Amenity Booking Confirmed",
                        body=f"Your booking for {amenity_name} on {b_date} ({s_time}-{e_time}) has been confirmed{fee_str}.",
                        priority=NotificationPriority.NORMAL,
                        aggregate_type="amenity_booking",
                        aggregate_id=str(envelope.aggregate_id),
                        action_url="/resident/amenities",
                        base_event_id=envelope.event_id,
                    )
                    created_count += 1

        elif event_type == "amenity.booking_payment_failed":
            user_id_raw = payload.get("user_id")
            amenity_name = payload.get("amenity_name", "Amenity")
            err = payload.get("error_message", "Payment transaction declined or timed out.")
            if user_id_raw:
                user = self.get_user_by_id(society_id, uuid.UUID(str(user_id_raw)))
                if user:
                    self.create_in_app_notification(
                        society_id=society_id,
                        recipient=user,
                        event_type=event_type,
                        title="Amenity Booking Payment Failed",
                        body=f"Payment for your booking of {amenity_name} failed: {err}. Please retry your booking.",
                        priority=NotificationPriority.HIGH,
                        aggregate_type="amenity_booking",
                        aggregate_id=str(envelope.aggregate_id),
                        action_url="/resident/amenities",
                        base_event_id=envelope.event_id,
                    )
                    created_count += 1

        elif event_type == "amenity.booking_cancelled":
            user_id_raw = payload.get("user_id")
            amenity_name = payload.get("amenity_name", "Amenity")
            refund_amount = payload.get("refund_amount_paise", 0)
            refund_status = payload.get("refund_status", "NOT_APPLICABLE")
            refund_msg = (
                f" Refund: ₹{refund_amount / 100:,.2f} ({refund_status})."
                if refund_amount > 0
                else ""
            )
            cancelled_by = payload.get("cancelled_by", "RESIDENT")
            by_str = "management" if cancelled_by == "STAFF" else "you"
            if user_id_raw:
                user = self.get_user_by_id(society_id, uuid.UUID(str(user_id_raw)))
                if user:
                    self.create_in_app_notification(
                        society_id=society_id,
                        recipient=user,
                        event_type=event_type,
                        title="Amenity Booking Cancelled",
                        body=f"Your booking for {amenity_name} was cancelled by {by_str}.{refund_msg}",
                        priority=NotificationPriority.NORMAL,
                        aggregate_type="amenity_booking",
                        aggregate_id=str(envelope.aggregate_id),
                        action_url="/resident/amenities",
                        base_event_id=envelope.event_id,
                    )
                    created_count += 1

        # --- F. OFFICIAL TOWNSHIP NOTICES & EMERGENCY BROADCASTS ---
        elif event_type in ("notice.published", "notice.emergency_broadcast"):
            notice_id_raw = payload.get("notice_id") or envelope.aggregate_id
            if not notice_id_raw:
                logger.warning(
                    f"[NotificationService] Notice event {envelope.event_id} has no notice_id; skipping"
                )
                return 0

            notice_id = uuid.UUID(str(notice_id_raw))
            notice = self.db.get(Notice, notice_id)
            version_val = int(payload.get("version") or (notice.version if notice else 1))

            is_emergency = (
                event_type == "notice.emergency_broadcast"
                or bool(payload.get("deliver_emergency"))
                or (notice is not None and getattr(notice, "deliver_emergency", False))
            )

            priority = (
                NotificationPriority.URGENT
                if is_emergency
                else (
                    NotificationPriority.HIGH
                    if (notice and notice.priority in (NoticePriority.HIGH, NoticePriority.URGENT))
                    or payload.get("priority")
                    in (NoticePriority.HIGH.value, NoticePriority.URGENT.value)
                    else (
                        NotificationPriority.LOW
                        if (notice and notice.priority == NoticePriority.LOW)
                        or payload.get("priority") == NoticePriority.LOW.value
                        else NotificationPriority.NORMAL
                    )
                )
            )

            title_val: str = str(
                notice.title if notice else payload.get("title", "Official Notice")
            )
            body_val: str = str(notice.body if notice else payload.get("body", title_val))
            category_val: str = str(
                notice.category.value if notice else payload.get("category", "GENERAL")
            )

            # Resolve recipients based on targeting scope
            if notice:
                recipients = self.get_notice_target_residents(notice)
            else:
                target_type = payload.get("target_type")
                if target_type == "FLAT" and payload.get("target_flat_id"):
                    recipients = self.get_active_flat_residents(
                        society_id, uuid.UUID(str(payload["target_flat_id"]))
                    )
                elif target_type == "TOWER" and payload.get("target_tower_id"):
                    tower_id = uuid.UUID(str(payload["target_tower_id"]))
                    now = utc_now()
                    recipients = list(
                        self.db.scalars(
                            select(User)
                            .join(FlatMembership, FlatMembership.user_id == User.id)
                            .join(Flat, Flat.id == FlatMembership.flat_id)
                            .where(
                                FlatMembership.society_id == society_id,
                                Flat.tower_id == tower_id,
                                FlatMembership.status == MembershipStatus.APPROVED,
                                User.status == UserStatus.ACTIVE,
                                or_(
                                    FlatMembership.valid_from.is_(None),
                                    FlatMembership.valid_from <= now,
                                ),
                                or_(
                                    FlatMembership.valid_until.is_(None),
                                    FlatMembership.valid_until >= now,
                                ),
                            )
                            .distinct()
                        ).all()
                    )
                else:
                    recipients = self.get_active_society_residents(society_id)

            notif_title = f"🚨 EMERGENCY: {title_val}" if is_emergency else title_val
            notif_body = body_val[:350] + ("..." if len(body_val) > 350 else "")

            for resident in recipients:
                pref = self.get_or_create_preferences(society_id, resident.id)

                perm_in_app, reason_in_app = self.is_channel_permitted(
                    pref, NotificationChannel.IN_APP, event_type, priority
                )
                perm_email, reason_email = self.is_channel_permitted(
                    pref, NotificationChannel.EMAIL, event_type, priority
                )
                perm_sms, reason_sms = self.is_channel_permitted(
                    pref, NotificationChannel.SMS, event_type, priority
                )

                # Check if in-app notification already exists (e.g. from _deliver_emergency_notice or prior attempt)
                existing_notif = self.db.scalars(
                    select(Notification).where(
                        Notification.society_id == society_id,
                        Notification.recipient_user_id == resident.id,
                        Notification.aggregate_type == "notice",
                        Notification.aggregate_id == str(notice_id),
                    )
                ).first()

                notice_notif: Notification | None = existing_notif

                if not notice_notif and perm_in_app:
                    notice_notif = self.create_in_app_notification(
                        society_id=society_id,
                        recipient=resident,
                        event_type=event_type,
                        title=notif_title,
                        body=notif_body,
                        priority=priority,
                        aggregate_type="notice",
                        aggregate_id=str(notice_id),
                        action_url="/resident/notices",
                        event_metadata={
                            "notice_id": str(notice_id),
                            "version": version_val,
                            "category": category_val,
                            "is_emergency": is_emergency,
                        },
                        base_event_id=notice_id,
                    )
                    created_count += 1
                elif notice_notif:
                    # In-app notification exists; ensure versioned in-app delivery record exists
                    version_deliv_key = f"in_app:{notice_id}:v{version_val}:{resident.id}"
                    deliv_cond = (
                        or_(
                            NotificationDelivery.idempotency_key == version_deliv_key,
                            and_(
                                NotificationDelivery.notification_id == notice_notif.id,
                                NotificationDelivery.channel == NotificationChannel.IN_APP,
                            ),
                        )
                        if version_val == 1
                        else (NotificationDelivery.idempotency_key == version_deliv_key)
                    )
                    existing_deliv = self.db.scalars(
                        select(NotificationDelivery).where(deliv_cond)
                    ).first()
                    if not existing_deliv:
                        notice_notif.title = notif_title
                        notice_notif.body = notif_body
                        notice_notif.priority = priority
                        notice_notif.read_at = None
                        notice_notif.updated_at = utc_now()
                        deliv = NotificationDelivery(
                            id=uuid.uuid4(),
                            notification_id=notice_notif.id,
                            society_id=society_id,
                            recipient_user_id=resident.id,
                            channel=NotificationChannel.IN_APP,
                            provider="in_app",
                            status=DeliveryStatus.DELIVERED,
                            idempotency_key=version_deliv_key,
                            delivered_at=utc_now(),
                            created_at=utc_now(),
                            updated_at=utc_now(),
                        )
                        self.db.add(deliv)
                        self.db.flush()
                    created_count += 1

                if notice_notif:
                    # 1. External Email delivery
                    email_subject = (
                        f"🚨 URGENT NOTICE: {title_val} - Marvel Greenfield"
                        if is_emergency
                        else f"Township Notice: {title_val} - Marvel Greenfield"
                    )
                    email_body_text = (
                        f"Dear Resident,\n\n{body_val}\n\n"
                        "Please view full details on the resident notices portal:\n"
                        "https://marvelgreenfield.com/resident/notices\n\n"
                        "Township Management"
                    )
                    email_key = f"email:{notice_id}:v{version_val}:{resident.id}"
                    self.dispatch_email_delivery(
                        notification=notice_notif,
                        recipient=resident,
                        subject=email_subject,
                        body_text=email_body_text,
                        base_event_id=notice_id,
                        is_suppressed=not perm_email,
                        suppression_reason=reason_email,
                        custom_idempotency_key=email_key,
                    )

                    # 2. External SMS delivery
                    sms_message = (
                        f"🚨 EMERGENCY: {title_val}. {body_val[:100]}... Check portal: https://marvelgreenfield.com/resident/notices"
                        if is_emergency
                        else f"Notice: {title_val}. Details: https://marvelgreenfield.com/resident/notices"
                    )
                    sms_key = f"sms:{notice_id}:v{version_val}:{resident.id}"
                    self.dispatch_sms_delivery(
                        notification=notice_notif,
                        recipient=resident,
                        message=sms_message,
                        base_event_id=notice_id,
                        is_suppressed=not perm_sms,
                        suppression_reason=reason_sms,
                        custom_idempotency_key=sms_key,
                    )

        return created_count

    # -------------------------------------------------------------------------
    # 5. Resident & Staff Query Methods
    # -------------------------------------------------------------------------

    def get_user_notifications(
        self,
        society_id: uuid.UUID,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        unread_only: bool = False,
    ) -> PaginatedNotificationsResponse:
        """Retrieves paginated notifications for the user within their society."""
        page = max(1, page)
        page_size = max(1, min(100, page_size))
        offset = (page - 1) * page_size

        base_filter = [
            Notification.society_id == society_id,
            Notification.recipient_user_id == user_id,
        ]
        if unread_only:
            base_filter.append(Notification.read_at.is_(None))

        # Count total items
        total = self.db.scalar(select(func.count(Notification.id)).where(and_(*base_filter))) or 0

        # Unread count
        unread_count = (
            self.db.scalar(
                select(func.count(Notification.id)).where(
                    Notification.society_id == society_id,
                    Notification.recipient_user_id == user_id,
                    Notification.read_at.is_(None),
                )
            )
            or 0
        )

        # Items
        stmt = (
            select(Notification)
            .where(and_(*base_filter))
            .order_by(desc(Notification.created_at))
            .offset(offset)
            .limit(page_size)
        )
        notifications = list(self.db.scalars(stmt).all())

        items = [
            NotificationResponseSchema(
                id=n.id,
                society_id=n.society_id,
                recipient_user_id=n.recipient_user_id,
                event_type=n.event_type,
                title=n.title,
                body=n.body,
                channel=n.channel,
                priority=n.priority,
                aggregate_type=n.aggregate_type,
                aggregate_id=n.aggregate_id,
                action_url=n.action_url,
                read_at=n.read_at,
                is_read=n.read_at is not None,
                created_at=n.created_at,
            )
            for n in notifications
        ]

        total_pages = math.ceil(total / page_size) if total > 0 else 1
        return PaginatedNotificationsResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            unread_count=unread_count,
        )

    def get_unread_count(self, society_id: uuid.UUID, user_id: uuid.UUID) -> int:
        return (
            self.db.scalar(
                select(func.count(Notification.id)).where(
                    Notification.society_id == society_id,
                    Notification.recipient_user_id == user_id,
                    Notification.read_at.is_(None),
                )
            )
            or 0
        )

    def mark_notification_as_read(
        self, society_id: uuid.UUID, user_id: uuid.UUID, notification_id: uuid.UUID
    ) -> Notification:
        notif = self.db.get(Notification, notification_id)
        if not notif or notif.society_id != society_id or notif.recipient_user_id != user_id:
            raise ResourceNotFoundError(
                code="NOTIFICATION_NOT_FOUND",
                message=f"Notification {notification_id} not found",
            )

        if notif.read_at is None:
            notif.read_at = utc_now()
            notif.updated_at = utc_now()
            self.db.commit()
            self.db.refresh(notif)
        return notif

    def mark_all_notifications_as_read(self, society_id: uuid.UUID, user_id: uuid.UUID) -> int:
        now = utc_now()
        stmt = select(Notification).where(
            Notification.society_id == society_id,
            Notification.recipient_user_id == user_id,
            Notification.read_at.is_(None),
        )
        unread_notifications = list(self.db.scalars(stmt).all())
        for n in unread_notifications:
            n.read_at = now
            n.updated_at = now

        self.db.commit()
        return len(unread_notifications)

    def get_user_preferences_schema(
        self, society_id: uuid.UUID, user_id: uuid.UUID
    ) -> NotificationPreferenceSchema:
        pref = self.get_or_create_preferences(society_id, user_id)
        return NotificationPreferenceSchema(
            society_id=pref.society_id,
            user_id=pref.user_id,
            email_enabled=pref.email_enabled,
            sms_enabled=pref.sms_enabled,
            in_app_enabled=pref.in_app_enabled,
            billing_email=pref.billing_email,
            billing_sms=pref.billing_sms,
            complaints_email=pref.complaints_email,
            complaints_sms=pref.complaints_sms,
            visitor_sms=pref.visitor_sms,
            emergency_alerts_mandatory=True,
        )

    def update_user_preferences(
        self,
        society_id: uuid.UUID,
        user_id: uuid.UUID,
        req: UpdateNotificationPreferenceRequest,
    ) -> NotificationPreferenceSchema:
        pref = self.get_or_create_preferences(society_id, user_id)
        if req.email_enabled is not None:
            pref.email_enabled = req.email_enabled
        if req.sms_enabled is not None:
            pref.sms_enabled = req.sms_enabled
        if req.in_app_enabled is not None:
            pref.in_app_enabled = req.in_app_enabled
        if req.billing_email is not None:
            pref.billing_email = req.billing_email
        if req.billing_sms is not None:
            pref.billing_sms = req.billing_sms
        if req.complaints_email is not None:
            pref.complaints_email = req.complaints_email
        if req.complaints_sms is not None:
            pref.complaints_sms = req.complaints_sms
        if req.visitor_sms is not None:
            pref.visitor_sms = req.visitor_sms

        pref.updated_at = utc_now()
        self.db.commit()
        return self.get_user_preferences_schema(society_id, user_id)

    def get_staff_overview(
        self,
        society_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> StaffNotificationOverviewResponse:
        page = max(1, page)
        page_size = max(1, min(100, page_size))
        offset = (page - 1) * page_size

        total = (
            self.db.scalar(
                select(func.count(NotificationDelivery.id)).where(
                    NotificationDelivery.society_id == society_id
                )
            )
            or 0
        )

        def count_by_status(s: DeliveryStatus) -> int:
            return (
                self.db.scalar(
                    select(func.count(NotificationDelivery.id)).where(
                        NotificationDelivery.society_id == society_id,
                        NotificationDelivery.status == s,
                    )
                )
                or 0
            )

        stmt = (
            select(NotificationDelivery)
            .where(NotificationDelivery.society_id == society_id)
            .order_by(desc(NotificationDelivery.created_at))
            .offset(offset)
            .limit(page_size)
        )
        deliveries = list(self.db.scalars(stmt).all())

        items = [
            StaffDeliveryOverviewItem(
                id=d.id,
                notification_id=d.notification_id,
                society_id=d.society_id,
                recipient_user_id=d.recipient_user_id,
                channel=d.channel,
                provider=d.provider,
                status=d.status,
                attempt_count=d.attempt_count,
                next_attempt_at=d.next_attempt_at,
                last_error_code=d.last_error_code,
                sent_at=d.sent_at,
                delivered_at=d.delivered_at,
                created_at=d.created_at,
            )
            for d in deliveries
        ]

        total_pages = math.ceil(total / page_size) if total > 0 else 1
        return StaffNotificationOverviewResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            pending_count=count_by_status(DeliveryStatus.PENDING)
            + count_by_status(DeliveryStatus.PROCESSING),
            failed_count=count_by_status(DeliveryStatus.FAILED),
            sent_count=count_by_status(DeliveryStatus.SENT),
            delivered_count=count_by_status(DeliveryStatus.DELIVERED),
            suppressed_count=count_by_status(DeliveryStatus.SUPPRESSED),
        )
