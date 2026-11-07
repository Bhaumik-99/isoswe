"""Official Township Notices Domain Service

Coordinates:
- Staff notice creation, editing, draft, publish, and archive lifecycles.
- Multi-tier targeting (Society-wide, Tower-specific, Flat-specific).
- Scheduled publishing, pinning, and expiry evaluation.
- Resident notice feeds with personalized read/unread status.
- Emergency notice broadcasting through the existing Notification & Outbox infrastructure.
- Audit event logging for all notice lifecycle transitions.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ResourceNotFoundError, ValidationError
from app.core.logging import logger
from app.domains.identity.models import (
    Flat,
    FlatMembership,
    MembershipStatus,
    Tower,
    User,
    UserStatus,
)
from app.domains.notifications.models import (
    DeliveryStatus,
    Notice,
    NoticeCategory,
    NoticePriority,
    NoticeRead,
    NoticeStatus,
    NoticeTargetType,
    Notification,
    NotificationChannel,
    NotificationDelivery,
    NotificationPriority,
)
from app.domains.notifications.schemas import (
    CreateNoticeRequest,
    MarkAllNoticesReadResponse,
    MarkNoticeReadResponse,
    NoticeResponseSchema,
    PaginatedNoticesResponse,
    UpdateNoticeRequest,
)
from app.domains.notifications.service import NotificationService
from app.domains.reliability.models import AuditEvent, OutboxEvent, OutboxStatus


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class NoticeService:
    def __init__(
        self, db: Session, notification_service: NotificationService | None = None
    ) -> None:
        self.db = db
        self.notification_service = notification_service or NotificationService(db)

    # -------------------------------------------------------------------------
    # Helper: Audit Logging
    # -------------------------------------------------------------------------

    def _record_audit(
        self,
        society_id: uuid.UUID,
        actor_id: uuid.UUID,
        action: str,
        resource_id: str,
        metadata: dict[str, Any],
    ) -> None:
        audit = AuditEvent(
            id=uuid.uuid4(),
            society_id=society_id,
            actor_id=actor_id,
            action=action,
            resource_type="notice",
            resource_id=resource_id,
            correlation_id=str(uuid.uuid4()),
            event_metadata=metadata,
        )
        self.db.add(audit)

    # -------------------------------------------------------------------------
    # Helper: Enqueue Outbox Event
    # -------------------------------------------------------------------------

    def _enqueue_outbox(
        self,
        event_type: str,
        aggregate_id: str,
        payload: dict[str, Any],
    ) -> OutboxEvent:
        existing = self.db.scalars(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == aggregate_id,
                OutboxEvent.event_type == event_type,
            )
        ).first()
        if existing:
            logger.info(
                "[NoticeService] Outbox event %s for aggregate %s already exists; skipping duplicate",
                event_type,
                aggregate_id,
            )
            return existing

        outbox = OutboxEvent(
            id=uuid.uuid4(),
            event_type=event_type,
            aggregate_type="notice",
            aggregate_id=aggregate_id,
            payload=payload,
            status=OutboxStatus.PENDING,
        )
        self.db.add(outbox)
        return outbox

    # -------------------------------------------------------------------------
    # Helper: Targeting Validation
    # -------------------------------------------------------------------------

    def _validate_targeting(
        self,
        society_id: uuid.UUID,
        target_type: NoticeTargetType,
        target_tower_id: uuid.UUID | None,
        target_flat_id: uuid.UUID | None,
    ) -> None:
        if target_type == NoticeTargetType.TOWER:
            if not target_tower_id:
                raise ValidationError(
                    code="TARGET_TOWER_REQUIRED",
                    message="Target tower must be specified for TOWER targeted notice.",
                )
            tower = self.db.scalars(
                select(Tower).where(Tower.id == target_tower_id, Tower.society_id == society_id)
            ).first()
            if not tower:
                raise ResourceNotFoundError(f"Tower {target_tower_id} not found in this society.")

        elif target_type == NoticeTargetType.FLAT:
            if not target_flat_id:
                raise ValidationError(
                    code="TARGET_FLAT_REQUIRED",
                    message="Target flat must be specified for FLAT targeted notice.",
                )
            flat = self.db.scalars(
                select(Flat).where(Flat.id == target_flat_id, Flat.society_id == society_id)
            ).first()
            if not flat:
                raise ResourceNotFoundError(f"Flat {target_flat_id} not found in this society.")

    # -------------------------------------------------------------------------
    # Helper: Resolve Recipients for Emergency Notice
    # -------------------------------------------------------------------------

    def _resolve_target_residents(self, notice: Notice) -> list[User]:
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
            if not notice.target_tower_id:
                return []
            base_query = base_query.join(Flat, Flat.id == FlatMembership.flat_id).where(
                Flat.tower_id == notice.target_tower_id
            )
        elif notice.target_type == NoticeTargetType.FLAT:
            if not notice.target_flat_id:
                return []
            base_query = base_query.where(FlatMembership.flat_id == notice.target_flat_id)

        residents = list(self.db.scalars(base_query.distinct()).all())
        return residents

    # -------------------------------------------------------------------------
    # Helper: Emergency Delivery Broadcast
    # -------------------------------------------------------------------------

    def _deliver_emergency_notice(self, notice: Notice) -> int:
        """Broadcasts emergency notice directly through the existing notification infrastructure with idempotency."""
        broadcast_key = f"emergency_broadcast:{notice.id}"
        # Idempotency guard: prevent duplicate emergency broadcast for the same notice
        existing_outbox = self.db.scalars(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == str(notice.id),
                OutboxEvent.event_type == "notice.emergency_broadcast",
            )
        ).first()
        if existing_outbox:
            logger.info(
                "Emergency notice %s has already been broadcast (key: %s); skipping duplicate delivery",
                notice.id,
                broadcast_key,
            )
            return 0

        residents = self._resolve_target_residents(notice)
        now = utc_now()
        delivered_count = 0

        for resident in residents:
            delivery_key = f"in_app:{notice.id}:{resident.id}"

            # Check if delivery record already exists for this resident and notice
            existing_deliv = self.db.scalars(
                select(NotificationDelivery).where(
                    NotificationDelivery.idempotency_key == delivery_key
                )
            ).first()
            if existing_deliv:
                continue

            existing_notif = self.db.scalars(
                select(Notification).where(
                    Notification.society_id == notice.society_id,
                    Notification.recipient_user_id == resident.id,
                    Notification.aggregate_type == "notice",
                    Notification.aggregate_id == str(notice.id),
                )
            ).first()

            in_app_notif = existing_notif
            if not in_app_notif:
                in_app_notif = Notification(
                    id=uuid.uuid4(),
                    society_id=notice.society_id,
                    recipient_user_id=resident.id,
                    event_type="notice.emergency",
                    title=f"🚨 EMERGENCY: {notice.title}",
                    body=notice.body[:350] + ("..." if len(notice.body) > 350 else ""),
                    channel=NotificationChannel.IN_APP,
                    priority=NotificationPriority.URGENT,
                    aggregate_type="notice",
                    aggregate_id=str(notice.id),
                    action_url="/resident/notices",
                    event_metadata={
                        "notice_id": str(notice.id),
                        "category": notice.category.value,
                        "target_type": notice.target_type.value,
                        "is_emergency": True,
                        "broadcast_key": broadcast_key,
                    },
                    created_at=now,
                    updated_at=now,
                )
                self.db.add(in_app_notif)
                self.db.flush()

            deliv = NotificationDelivery(
                id=uuid.uuid4(),
                notification_id=in_app_notif.id,
                society_id=notice.society_id,
                recipient_user_id=resident.id,
                channel=NotificationChannel.IN_APP,
                provider="in_app",
                status=DeliveryStatus.DELIVERED,
                idempotency_key=delivery_key,
                delivered_at=now,
                created_at=now,
                updated_at=now,
            )
            self.db.add(deliv)
            delivered_count += 1

        self._enqueue_outbox(
            event_type="notice.emergency_broadcast",
            aggregate_id=str(notice.id),
            payload={
                "notice_id": str(notice.id),
                "society_id": str(notice.society_id),
                "title": notice.title,
                "category": notice.category.value,
                "priority": notice.priority.value,
                "target_type": notice.target_type.value,
                "recipients_count": len(residents),
                "broadcast_key": broadcast_key,
                "published_at": notice.published_at.isoformat()
                if notice.published_at
                else now.isoformat(),
            },
        )
        logger.info(
            "Delivered emergency notice %s to %d resident(s) with broadcast key %s",
            notice.id,
            delivered_count,
            broadcast_key,
        )
        return delivered_count

    # -------------------------------------------------------------------------
    # Staff Notice Management
    # -------------------------------------------------------------------------

    def create_notice(
        self,
        society_id: uuid.UUID,
        author_id: uuid.UUID,
        req: CreateNoticeRequest,
    ) -> NoticeResponseSchema:
        now = utc_now()
        self._validate_targeting(
            society_id=society_id,
            target_type=req.target_type,
            target_tower_id=req.target_tower_id,
            target_flat_id=req.target_flat_id,
        )

        published_at = req.published_at
        if req.status == NoticeStatus.PUBLISHED and published_at is None:
            published_at = now

        if req.expires_at and published_at and req.expires_at <= published_at:
            raise ValidationError(
                code="INVALID_EXPIRY_DATE",
                message="Notice expiry date must be strictly after the publication date.",
            )

        notice = Notice(
            id=uuid.uuid4(),
            society_id=society_id,
            title=req.title.strip(),
            body=req.body.strip(),
            category=req.category,
            priority=req.priority,
            status=req.status,
            target_type=req.target_type,
            target_tower_id=req.target_tower_id,
            target_flat_id=req.target_flat_id,
            is_pinned=req.is_pinned,
            published_at=published_at,
            expires_at=req.expires_at,
            author_id=author_id,
            created_at=now,
            updated_at=now,
        )
        self.db.add(notice)
        self.db.flush()

        self._record_audit(
            society_id=society_id,
            actor_id=author_id,
            action="NOTICE_CREATED",
            resource_id=str(notice.id),
            metadata={
                "title": notice.title,
                "status": notice.status.value,
                "category": notice.category.value,
                "target_type": notice.target_type.value,
                "is_pinned": notice.is_pinned,
            },
        )

        is_emergency = (
            req.deliver_emergency
            or notice.category == NoticeCategory.EMERGENCY
            or notice.priority == NoticePriority.URGENT
        )

        # Effective-time scheduling: only deliver/broadcast if publication is effective now
        pub_at = ensure_utc(notice.published_at)
        is_effective = pub_at is None or pub_at <= now

        if notice.status == NoticeStatus.PUBLISHED and is_effective:
            if is_emergency:
                self._deliver_emergency_notice(notice)
            else:
                self._enqueue_outbox(
                    event_type="notice.published",
                    aggregate_id=str(notice.id),
                    payload={
                        "notice_id": str(notice.id),
                        "society_id": str(society_id),
                        "title": notice.title,
                        "category": notice.category.value,
                        "priority": notice.priority.value,
                        "target_type": notice.target_type.value,
                        "status": notice.status.value,
                        "broadcast_key": f"notice_publish:{notice.id}",
                    },
                )

        self.db.commit()
        self.db.refresh(notice)
        return self._to_schema(notice, is_read=False, read_at=None)

    def update_notice(
        self,
        society_id: uuid.UUID,
        actor_id: uuid.UUID,
        notice_id: uuid.UUID,
        req: UpdateNoticeRequest,
    ) -> NoticeResponseSchema:
        notice = self.db.scalars(
            select(Notice).where(Notice.id == notice_id, Notice.society_id == society_id)
        ).first()
        if not notice:
            raise ResourceNotFoundError(f"Notice {notice_id} not found.")

        now = utc_now()
        target_type = req.target_type if req.target_type is not None else notice.target_type
        target_tower_id = (
            req.target_tower_id if req.target_tower_id is not None else notice.target_tower_id
        )
        target_flat_id = (
            req.target_flat_id if req.target_flat_id is not None else notice.target_flat_id
        )

        self._validate_targeting(
            society_id=society_id,
            target_type=target_type,
            target_tower_id=target_tower_id,
            target_flat_id=target_flat_id,
        )

        prev_status = notice.status

        if req.title is not None:
            notice.title = req.title.strip()
        if req.body is not None:
            notice.body = req.body.strip()
        if req.category is not None:
            notice.category = req.category
        if req.priority is not None:
            notice.priority = req.priority
        if req.status is not None:
            notice.status = req.status
        if req.target_type is not None:
            notice.target_type = req.target_type
            notice.target_tower_id = req.target_tower_id
            notice.target_flat_id = req.target_flat_id
        if req.is_pinned is not None:
            notice.is_pinned = req.is_pinned
        if req.published_at is not None:
            notice.published_at = req.published_at
        if req.expires_at is not None:
            notice.expires_at = req.expires_at

        # Transitioning to published
        if notice.status == NoticeStatus.PUBLISHED and not notice.published_at:
            notice.published_at = now

        if notice.expires_at and notice.published_at and notice.expires_at <= notice.published_at:
            raise ValidationError(
                code="INVALID_EXPIRY_DATE",
                message="Notice expiry date must be strictly after the publication date.",
            )

        notice.updated_at = now
        self.db.flush()

        self._record_audit(
            society_id=society_id,
            actor_id=actor_id,
            action="NOTICE_UPDATED",
            resource_id=str(notice.id),
            metadata={
                "title": notice.title,
                "status": notice.status.value,
                "category": notice.category.value,
                "is_pinned": notice.is_pinned,
            },
        )

        # If transitioned from DRAFT to PUBLISHED or explicitly triggered emergency
        is_emergency = (
            req.deliver_emergency
            or notice.category == NoticeCategory.EMERGENCY
            or notice.priority == NoticePriority.URGENT
        )

        pub_at = ensure_utc(notice.published_at)
        is_effective = pub_at is None or pub_at <= now

        if notice.status == NoticeStatus.PUBLISHED and prev_status != NoticeStatus.PUBLISHED:
            self._record_audit(
                society_id=society_id,
                actor_id=actor_id,
                action="NOTICE_PUBLISHED",
                resource_id=str(notice.id),
                metadata={"title": notice.title, "published_at": str(notice.published_at)},
            )
            if is_effective:
                if is_emergency:
                    self._deliver_emergency_notice(notice)
                else:
                    self._enqueue_outbox(
                        event_type="notice.published",
                        aggregate_id=str(notice.id),
                        payload={
                            "notice_id": str(notice.id),
                            "society_id": str(society_id),
                            "title": notice.title,
                            "category": notice.category.value,
                            "priority": notice.priority.value,
                            "target_type": notice.target_type.value,
                            "broadcast_key": f"notice_publish:{notice.id}",
                        },
                    )
        elif is_emergency and req.deliver_emergency and is_effective:
            self._deliver_emergency_notice(notice)

        self.db.commit()
        self.db.refresh(notice)
        return self._to_schema(notice, is_read=False, read_at=None)

    def publish_notice(
        self,
        society_id: uuid.UUID,
        actor_id: uuid.UUID,
        notice_id: uuid.UUID,
    ) -> NoticeResponseSchema:
        notice = self.db.scalars(
            select(Notice).where(Notice.id == notice_id, Notice.society_id == society_id)
        ).first()
        if not notice:
            raise ResourceNotFoundError(f"Notice {notice_id} not found.")

        # Publish-state transition checks: Guard against already-published notices
        if notice.status == NoticeStatus.PUBLISHED:
            logger.info(
                "Notice %s is already published (published_at=%s); skipping duplicate publish",
                notice_id,
                notice.published_at,
            )
            return self._to_schema(notice, is_read=False, read_at=None)

        if notice.status == NoticeStatus.ARCHIVED:
            raise ValidationError(
                code="INVALID_STATUS_TRANSITION",
                message="Cannot publish an archived notice.",
            )

        now = utc_now()
        notice.status = NoticeStatus.PUBLISHED
        pub_at = ensure_utc(notice.published_at)
        if not pub_at or pub_at <= now:
            notice.published_at = now
            pub_at = now
        notice.updated_at = now
        self.db.flush()

        self._record_audit(
            society_id=society_id,
            actor_id=actor_id,
            action="NOTICE_PUBLISHED",
            resource_id=str(notice.id),
            metadata={"title": notice.title, "published_at": str(notice.published_at)},
        )

        is_emergency = (
            notice.category == NoticeCategory.EMERGENCY or notice.priority == NoticePriority.URGENT
        )
        is_effective = pub_at is None or pub_at <= now

        if is_effective:
            if is_emergency:
                self._deliver_emergency_notice(notice)
            else:
                self._enqueue_outbox(
                    event_type="notice.published",
                    aggregate_id=str(notice.id),
                    payload={
                        "notice_id": str(notice.id),
                        "society_id": str(society_id),
                        "title": notice.title,
                        "category": notice.category.value,
                        "priority": notice.priority.value,
                        "target_type": notice.target_type.value,
                        "broadcast_key": f"notice_publish:{notice.id}",
                    },
                )

        self.db.commit()
        self.db.refresh(notice)
        return self._to_schema(notice, is_read=False, read_at=None)

    def publish_due_scheduled_notices(
        self, society_id: uuid.UUID | None = None
    ) -> list[NoticeResponseSchema]:
        """Activates and broadcasts scheduled notices whose published_at effective time has arrived."""
        now = utc_now()
        stmt = select(Notice).where(
            Notice.status == NoticeStatus.PUBLISHED,
            Notice.published_at.is_not(None),
        )
        if society_id:
            stmt = stmt.where(Notice.society_id == society_id)

        all_pub = list(self.db.scalars(stmt).all())
        notices: list[Notice] = []
        for n in all_pub:
            pub = ensure_utc(n.published_at)
            if pub is not None and pub <= now:
                notices.append(n)
        activated: list[NoticeResponseSchema] = []
        for notice in notices:
            is_emergency = (
                notice.category == NoticeCategory.EMERGENCY
                or notice.priority == NoticePriority.URGENT
            )
            outbox_type = "notice.emergency_broadcast" if is_emergency else "notice.published"
            existing_outbox = self.db.scalars(
                select(OutboxEvent).where(
                    OutboxEvent.aggregate_id == str(notice.id),
                    OutboxEvent.event_type == outbox_type,
                )
            ).first()

            if not existing_outbox:
                if is_emergency:
                    self._deliver_emergency_notice(notice)
                else:
                    self._enqueue_outbox(
                        event_type="notice.published",
                        aggregate_id=str(notice.id),
                        payload={
                            "notice_id": str(notice.id),
                            "society_id": str(notice.society_id),
                            "title": notice.title,
                            "category": notice.category.value,
                            "priority": notice.priority.value,
                            "target_type": notice.target_type.value,
                            "status": notice.status.value,
                            "broadcast_key": f"notice_publish:{notice.id}",
                        },
                    )
                activated.append(self._to_schema(notice, is_read=False, read_at=None))

        if activated:
            self.db.commit()
        return activated

    def archive_notice(
        self,
        society_id: uuid.UUID,
        actor_id: uuid.UUID,
        notice_id: uuid.UUID,
    ) -> NoticeResponseSchema:
        notice = self.db.scalars(
            select(Notice).where(Notice.id == notice_id, Notice.society_id == society_id)
        ).first()
        if not notice:
            raise ResourceNotFoundError(f"Notice {notice_id} not found.")

        notice.status = NoticeStatus.ARCHIVED
        notice.updated_at = utc_now()
        self.db.flush()

        self._record_audit(
            society_id=society_id,
            actor_id=actor_id,
            action="NOTICE_ARCHIVED",
            resource_id=str(notice.id),
            metadata={"title": notice.title},
        )

        self._enqueue_outbox(
            event_type="notice.archived",
            aggregate_id=str(notice.id),
            payload={"notice_id": str(notice.id), "society_id": str(society_id)},
        )

        self.db.commit()
        self.db.refresh(notice)
        return self._to_schema(notice, is_read=False, read_at=None)

    def get_notice(
        self,
        society_id: uuid.UUID,
        notice_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> NoticeResponseSchema:
        """Retrieves a single notice.

        When user_id is provided, resident access controls, membership validity,
        and target-scope predicates are strictly enforced.
        """
        if user_id is not None:
            return self.get_resident_notice(
                society_id=society_id,
                user_id=user_id,
                notice_id=notice_id,
            )

        notice = self.db.scalars(
            select(Notice).where(Notice.id == notice_id, Notice.society_id == society_id)
        ).first()
        if not notice:
            raise ResourceNotFoundError(f"Notice {notice_id} not found.")

        return self._to_schema(notice, is_read=False, read_at=None)

    def list_staff_notices(
        self,
        society_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        status: NoticeStatus | None = None,
        category: NoticeCategory | None = None,
        target_type: NoticeTargetType | None = None,
        search: str | None = None,
    ) -> PaginatedNoticesResponse:
        stmt = select(Notice).where(Notice.society_id == society_id)

        if status:
            stmt = stmt.where(Notice.status == status)
        if category:
            stmt = stmt.where(Notice.category == category)
        if target_type:
            stmt = stmt.where(Notice.target_type == target_type)
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(or_(Notice.title.ilike(pattern), Notice.body.ilike(pattern)))

        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        total_pages = max(1, (total + page_size - 1) // page_size)

        stmt = (
            stmt.order_by(Notice.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        notices = list(self.db.scalars(stmt).all())

        return PaginatedNoticesResponse(
            items=[self._to_schema(n, is_read=False, read_at=None) for n in notices],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            unread_count=0,
        )

    # -------------------------------------------------------------------------
    # Resident Notice Feed & Read Tracking
    # -------------------------------------------------------------------------

    def _build_resident_notice_predicate(
        self,
        society_id: uuid.UUID,
        user_id: uuid.UUID,
        now: datetime,
    ) -> tuple[bool, Any]:
        """Builds the security and targeting predicate for a resident in a society.

        Enforces:
        - Resident has an approved, active flat membership in the society.
        - Membership validity window (valid_from <= now, valid_until >= now).
        - Notice society_id boundary.
        - Notice status == PUBLISHED (draft and archived notices are completely inaccessible).
        - Publication schedule (published_at is not null and <= now).
        - Expiry date (expires_at is null or > now).
        - Target scope (SOCIETY, or TOWER in resident's towers, or FLAT in resident's flats).

        Returns:
            (has_active_membership, sql_predicate)
        """
        memberships_stmt = (
            select(FlatMembership, Flat)
            .join(Flat, Flat.id == FlatMembership.flat_id)
            .where(
                FlatMembership.society_id == society_id,
                FlatMembership.user_id == user_id,
                FlatMembership.status == MembershipStatus.APPROVED,
                or_(FlatMembership.valid_from.is_(None), FlatMembership.valid_from <= now),
                or_(FlatMembership.valid_until.is_(None), FlatMembership.valid_until >= now),
            )
        )
        rows = self.db.execute(memberships_stmt).all()
        if not rows:
            return False, None

        flat_ids = [m.flat_id for m, _ in rows]
        tower_ids = [f.tower_id for _, f in rows if f.tower_id is not None]

        target_conditions = [Notice.target_type == NoticeTargetType.SOCIETY]
        if tower_ids:
            target_conditions.append(
                and_(
                    Notice.target_type == NoticeTargetType.TOWER,
                    Notice.target_tower_id.in_(tower_ids),
                )
            )
        if flat_ids:
            target_conditions.append(
                and_(
                    Notice.target_type == NoticeTargetType.FLAT,
                    Notice.target_flat_id.in_(flat_ids),
                )
            )

        predicate = and_(
            Notice.society_id == society_id,
            Notice.status == NoticeStatus.PUBLISHED,
            Notice.published_at.is_not(None),
            Notice.published_at <= now,
            or_(Notice.expires_at.is_(None), Notice.expires_at > now),
            or_(*target_conditions),
        )
        return True, predicate

    def get_resident_notice(
        self,
        society_id: uuid.UUID,
        user_id: uuid.UUID,
        notice_id: uuid.UUID,
    ) -> NoticeResponseSchema:
        """Retrieves a single notice for a resident, strictly enforcing membership and targeting."""
        now = utc_now()
        has_access, predicate = self._build_resident_notice_predicate(society_id, user_id, now)
        if not has_access or predicate is None:
            raise ResourceNotFoundError(f"Notice {notice_id} not found.")

        stmt = select(Notice).where(Notice.id == notice_id, predicate)
        notice = self.db.scalars(stmt).first()
        if not notice:
            raise ResourceNotFoundError(f"Notice {notice_id} not found.")

        read_record = self.db.scalars(
            select(NoticeRead).where(
                NoticeRead.notice_id == notice_id,
                NoticeRead.user_id == user_id,
            )
        ).first()

        return self._to_schema(
            notice,
            is_read=(read_record is not None),
            read_at=read_record.read_at if read_record else None,
        )

    def list_resident_notices(
        self,
        society_id: uuid.UUID,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        category: NoticeCategory | None = None,
        unread_only: bool = False,
    ) -> PaginatedNoticesResponse:
        now = utc_now()
        has_access, predicate = self._build_resident_notice_predicate(society_id, user_id, now)
        if not has_access or predicate is None:
            return PaginatedNoticesResponse(
                items=[],
                total=0,
                page=page,
                page_size=page_size,
                total_pages=1,
                unread_count=0,
            )

        read_subq = (
            select(NoticeRead.notice_id, NoticeRead.read_at)
            .where(NoticeRead.user_id == user_id)
            .subquery()
        )

        joined_stmt = (
            select(Notice, read_subq.c.read_at)
            .outerjoin(read_subq, read_subq.c.notice_id == Notice.id)
            .where(predicate)
        )
        if category:
            joined_stmt = joined_stmt.where(Notice.category == category)

        if unread_only:
            joined_stmt = joined_stmt.where(read_subq.c.read_at.is_(None))

        unread_count_stmt = (
            select(func.count(Notice.id))
            .outerjoin(read_subq, read_subq.c.notice_id == Notice.id)
            .where(
                predicate,
                read_subq.c.read_at.is_(None),
            )
        )
        unread_count = self.db.scalar(unread_count_stmt) or 0

        total = self.db.scalar(select(func.count()).select_from(joined_stmt.subquery())) or 0
        total_pages = max(1, (total + page_size - 1) // page_size)

        joined_stmt = (
            joined_stmt.order_by(Notice.is_pinned.desc(), desc(Notice.published_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        results = self.db.execute(joined_stmt).all()

        items = [
            self._to_schema(notice, is_read=(read_at is not None), read_at=read_at)
            for notice, read_at in results
        ]

        return PaginatedNoticesResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            unread_count=unread_count,
        )

    def mark_notice_read(
        self,
        society_id: uuid.UUID,
        user_id: uuid.UUID,
        notice_id: uuid.UUID,
    ) -> MarkNoticeReadResponse:
        now = utc_now()
        has_access, predicate = self._build_resident_notice_predicate(society_id, user_id, now)
        if not has_access or predicate is None:
            raise ResourceNotFoundError(f"Notice {notice_id} not found.")

        stmt = select(Notice).where(Notice.id == notice_id, predicate)
        notice = self.db.scalars(stmt).first()
        if not notice:
            raise ResourceNotFoundError(f"Notice {notice_id} not found.")

        read_record = self.db.scalars(
            select(NoticeRead).where(
                NoticeRead.notice_id == notice_id,
                NoticeRead.user_id == user_id,
            )
        ).first()

        if not read_record:
            read_record = NoticeRead(
                id=uuid.uuid4(),
                notice_id=notice_id,
                user_id=user_id,
                read_at=now,
            )
            self.db.add(read_record)
            self.db.commit()

        return MarkNoticeReadResponse(
            notice_id=notice_id,
            read_at=read_record.read_at,
            status="success",
        )

    def mark_all_notices_read(
        self,
        society_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> MarkAllNoticesReadResponse:
        now = utc_now()
        has_access, predicate = self._build_resident_notice_predicate(society_id, user_id, now)
        if not has_access or predicate is None:
            return MarkAllNoticesReadResponse(marked_count=0, status="success")

        read_subq = select(NoticeRead.notice_id).where(NoticeRead.user_id == user_id).subquery()

        unread_notices_stmt = select(Notice.id).where(
            predicate,
            Notice.id.not_in(select(read_subq.c.notice_id)),
        )
        unread_ids = list(self.db.scalars(unread_notices_stmt).all())

        for n_id in unread_ids:
            self.db.add(
                NoticeRead(
                    id=uuid.uuid4(),
                    notice_id=n_id,
                    user_id=user_id,
                    read_at=now,
                )
            )

        self.db.commit()
        return MarkAllNoticesReadResponse(marked_count=len(unread_ids), status="success")

    # -------------------------------------------------------------------------
    # Helper: Serialization
    # -------------------------------------------------------------------------

    def _to_schema(
        self,
        notice: Notice,
        is_read: bool = False,
        read_at: datetime | None = None,
    ) -> NoticeResponseSchema:
        author_name = None
        if notice.author:
            author_name = notice.author.full_name

        tower_name = None
        if notice.target_tower:
            tower_name = notice.target_tower.name or notice.target_tower.tower_number

        flat_number = None
        if notice.target_flat:
            flat_number = notice.target_flat.flat_number

        return NoticeResponseSchema(
            id=notice.id,
            society_id=notice.society_id,
            title=notice.title,
            body=notice.body,
            category=notice.category,
            priority=notice.priority,
            status=notice.status,
            target_type=notice.target_type,
            target_tower_id=notice.target_tower_id,
            target_tower_name=tower_name,
            target_flat_id=notice.target_flat_id,
            target_flat_number=flat_number,
            is_pinned=notice.is_pinned,
            published_at=notice.published_at,
            expires_at=notice.expires_at,
            author_id=notice.author_id,
            author_name=author_name,
            is_read=is_read,
            read_at=read_at,
            created_at=notice.created_at,
            updated_at=notice.updated_at,
        )
