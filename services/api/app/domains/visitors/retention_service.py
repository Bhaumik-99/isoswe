"""Visitor Photo Retention & Storage Service

Manages visitor photo storage, presigned download URLs with 15-minute expiration,
IDOR access checks, 90-day logical cutoff enforcement, and automated cleanup.
"""

import contextlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import String, cast, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppException, AuthorizationError, ResourceNotFoundError
from app.domains.complaints.storage import (
    get_storage_provider,
    validate_photo_bytes,
)
from app.domains.identity.models import FlatMembership, MembershipStatus
from app.domains.reliability.models import AuditEvent
from app.domains.visitors.models import (
    GateStaffAssignment,
    VisitorRecord,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_utc(dt: datetime | None) -> datetime:
    if dt is None:
        return datetime.now(UTC)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


class PhotoExpiredError(AppException):
    """Raised when a photo is requested for a visitor record older than 90 days (HTTP 410 Gone)."""

    def __init__(
        self,
        message: str = "Photo expired after 90 days retention period",
        code: str = "PHOTO_EXPIRED",
    ) -> None:
        super().__init__(status_code=410, code=code, message=message)


class PhotoRetentionService:
    """Service managing private S3 storage, presigned URLs, and 90-day retention policies."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.storage_provider = get_storage_provider()

    @staticmethod
    def generate_photo_storage_key(
        society_id: uuid.UUID, visitor_id: uuid.UUID, ext: str = "jpg"
    ) -> str:
        """Returns standard partition key: visitor-photos/{society_id}/{year}/{month}/{uuid}.jpg"""
        now = utc_now()
        clean_ext = ext.lstrip(".")
        return f"visitor-photos/{society_id}/{now.year}/{now.month:02d}/{visitor_id}.{clean_ext}"

    def save_photo_bytes(
        self,
        society_id: uuid.UUID,
        visitor_id: uuid.UUID,
        photo_bytes: bytes,
        content_type: str = "image/jpeg",
    ) -> str:
        """Validates magic bytes and uploads photo bytes to private storage."""
        is_valid, reason = validate_photo_bytes(photo_bytes, content_type)
        if not is_valid:
            from app.core.errors import ValidationError

            raise ValidationError(
                code="INVALID_PHOTO_BYTES",
                message=reason or "Invalid image payload",
            )

        ext = "jpg"
        if "png" in content_type.lower():
            ext = "png"
        elif "webp" in content_type.lower():
            ext = "webp"

        storage_key = self.generate_photo_storage_key(society_id, visitor_id, ext=ext)
        self.storage_provider.put_object_bytes(
            storage_key=storage_key,
            data=photo_bytes,
            content_type=content_type,
        )
        return storage_key

    def get_visitor_photo_presigned_url(
        self,
        visitor_id: uuid.UUID,
        requester_user_id: uuid.UUID,
        society_id: uuid.UUID,
        is_guard: bool = False,
        active_flat_ids: list[uuid.UUID] | None = None,
    ) -> dict[str, Any]:
        """Generates a secure presigned download URL (15-min expiration) after verifying
        90-day retention validity and strict tenant/flat authorization.
        """
        now = utc_now()

        # 1. Fetch visitor record
        id_cond = or_(
            cast(VisitorRecord.id, String) == str(visitor_id),
            cast(VisitorRecord.id, String) == visitor_id.hex,
        )
        society_cond = or_(
            cast(VisitorRecord.society_id, String) == str(society_id),
            cast(VisitorRecord.society_id, String) == society_id.hex,
        )
        stmt = select(VisitorRecord).where(id_cond, society_cond)
        visitor = self.db.scalars(stmt).first()
        if not visitor:
            raise ResourceNotFoundError(
                code="VISITOR_NOT_FOUND",
                message=f"Visitor record {visitor_id} not found",
            )

        # 2. Strict 90-Day Logical Cutoff Check (CHAL-16 & Tier 2 boundary)
        # Even if the file physically exists, if age > 90 days, return 410 immediately!
        c_at = ensure_utc(visitor.created_at)
        if (now - c_at) > timedelta(days=90) or visitor.is_photo_expired:
            raise PhotoExpiredError(
                message=f"Visitor photo for {visitor_id} expired after 90 days retention period",
                code="PHOTO_EXPIRED",
            )

        # 3. Authorization Check
        if is_guard:
            # Guard must have an active shift assignment in the society
            user_cond = or_(
                cast(GateStaffAssignment.user_id, String) == str(requester_user_id),
                cast(GateStaffAssignment.user_id, String) == requester_user_id.hex,
            )
            society_cond = or_(
                cast(GateStaffAssignment.society_id, String) == str(society_id),
                cast(GateStaffAssignment.society_id, String) == society_id.hex,
            )
            guard_stmt = select(GateStaffAssignment).where(
                society_cond,
                user_cond,
                GateStaffAssignment.is_active.is_(True),
            )
            assignments = list(self.db.scalars(guard_stmt).all())
            valid_assignment = None
            for a in assignments:
                a_from = ensure_utc(a.assigned_from)
                if a_from > now:
                    continue
                if a.assigned_until is not None and ensure_utc(a.assigned_until) < now:
                    continue
                valid_assignment = a
                break

            if not valid_assignment:
                raise AuthorizationError(
                    code="GATE_ACCESS_DENIED",
                    message="Gate guard does not have an active assignment to access visitor photos.",
                )
        else:
            # Resident: IDOR prevention (CHAL-17)
            # Resident must have an active, non-expired membership for visitor's destination flat
            if active_flat_ids is not None:
                if visitor.destination_flat_id not in active_flat_ids:
                    raise AuthorizationError(
                        code="FLAT_ACCESS_DENIED",
                        message="Residents can only access visitor photographs for flats where they hold active membership.",
                    )
            else:
                mem_stmt = select(FlatMembership).where(
                    FlatMembership.user_id == requester_user_id,
                    FlatMembership.society_id == society_id,
                    FlatMembership.flat_id == visitor.destination_flat_id,
                    FlatMembership.status == MembershipStatus.APPROVED,
                    FlatMembership.valid_from <= now,
                    or_(
                        FlatMembership.valid_until.is_(None),
                        FlatMembership.valid_until >= now,
                    ),
                )
                membership = self.db.scalars(mem_stmt).first()
                if not membership:
                    raise AuthorizationError(
                        code="FLAT_ACCESS_DENIED",
                        message="Residents can only access visitor photographs for flats where they hold active membership.",
                    )

        # 4. Verify photo key exists
        photo_key = visitor.photo_key
        if not photo_key:
            raise ResourceNotFoundError(
                code="PHOTO_NOT_FOUND",
                message="No photo registered for this visitor record",
            )

        # 5. Generate presigned URL with 15-minute expiration (900 seconds)
        presigned_url = self.storage_provider.generate_download_url(
            storage_key=photo_key,
            expires_in_seconds=900,
        )

        return {
            "photo_url": presigned_url,
            "url": presigned_url,
            "expires_in": 900,
            "visitor_id": str(visitor.id),
        }

    def purge_expired_photos(self, batch_size: int = 100) -> int:
        """Physical deletion worker for photos older than 90 days.
        Deletes S3 objects, nullifies database keys, and records audit events.
        """
        now = utc_now()
        cutoff_date = now - timedelta(days=90)

        stmt = (
            select(VisitorRecord)
            .where(
                VisitorRecord.created_at < cutoff_date,
                or_(
                    VisitorRecord.photo_s3_key.is_not(None),
                    VisitorRecord.photo_storage_key.is_not(None),
                ),
            )
            .limit(batch_size)
        )
        expired_records = list(self.db.scalars(stmt).all())
        if not expired_records:
            return 0

        purged_count = 0
        for record in expired_records:
            key_to_delete = record.photo_key
            if key_to_delete:
                with contextlib.suppress(Exception):
                    self.storage_provider.delete_file(key_to_delete)

            record.photo_purged_at = now
            record.photo_deleted_at = now
            record.photo_s3_key = None
            record.photo_storage_key = None

            audit = AuditEvent(
                id=uuid.uuid4(),
                society_id=record.society_id,
                actor_id=None,
                action="PHOTO_RETENTION_PURGED",
                resource_type="visitor_record",
                resource_id=str(record.id),
                correlation_id=str(uuid.uuid4()),
                event_metadata={
                    "visitor_id": str(record.id),
                    "created_at": record.created_at.isoformat(),
                    "purged_at": now.isoformat(),
                    "reason": "90_day_statutory_retention_limit",
                },
            )
            self.db.add(audit)
            purged_count += 1

        self.db.commit()
        return purged_count
