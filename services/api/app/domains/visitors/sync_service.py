"""Offline-First Batch Synchronization Engine

Implements:
- Batch offline event processing with stable UUIDv4 client_event_id (Feature 33)
- Canonical SHA-256 payload checksum calculation
- Replay conflict detection on modified payloads (CHAL-13)
- Idempotent deduplication returning cached ACK on identical replay (CHAL-14)
- Enforced PENDING approval invariant regardless of client payload (CHAL-15, Feature 36)
- Partial batch isolation via transaction savepoints (Feature 35)
"""

import base64
import binascii
import contextlib
import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppException, AuthorizationError, ValidationError
from app.domains.identity.models import Flat
from app.domains.reliability.models import AuditEvent
from app.domains.visitors.models import (
    ApprovalStatus,
    EntryStatus,
    GateStaffAssignment,
    OfflineSyncEvent,
    SyncStatus,
    VisitorPurpose,
    VisitorRecord,
)
from app.domains.visitors.retention_service import PhotoRetentionService


def utc_now() -> datetime:
    return datetime.now(UTC)


class OfflineSyncService:
    """Service managing offline batch synchronization from gate tablet clients."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.retention_service = PhotoRetentionService(db)

    @staticmethod
    def compute_payload_hash(payload: dict[str, Any]) -> str:
        """Computes deterministic canonical SHA-256 hash of registration metadata."""
        name = str(payload.get("visitor_name", "")).strip()
        phone = str(payload.get("phone_number", "")).strip()
        vehicle = str(payload.get("vehicle_number", "") or "").strip()
        purpose = str(payload.get("purpose", "")).strip()
        flat_id = str(payload.get("destination_flat_id", "")).strip()
        notice_ver = str(payload.get("privacy_notice_version", "")).strip()
        # The photo is bound to the event by its SHA-256 digest (and capture time) so a replay
        # cannot swap or strip the photograph while keeping the same client_event_id.
        photo_digest = str(payload.get("photo_sha256") or "").strip().lower()
        if not photo_digest and payload.get("photo_base64"):
            try:
                raw_b64 = str(payload["photo_base64"])
                if raw_b64.startswith("data:") and "," in raw_b64:
                    raw_b64 = raw_b64.split(",", 1)[1]
                photo_bytes = base64.b64decode(raw_b64, validate=True)
                photo_digest = hashlib.sha256(photo_bytes).hexdigest()
            except Exception:
                pass

        captured_at = str(payload.get("photo_captured_at") or "").strip()

        canonical_repr = (
            f"name:{name}|phone:{phone}|vehicle:{vehicle}|purpose:{purpose}|flat:{flat_id}"
            f"|notice:{notice_ver}|photo:{photo_digest}|captured:{captured_at}"
        )
        return hashlib.sha256(canonical_repr.encode()).hexdigest()

    @staticmethod
    def _decode_photo(payload: dict[str, Any]) -> tuple[bytes | None, str, str]:
        """Validates the event photo and returns (bytes, content_type, sha256_hex).

        A photo is mandatory once the event declares one: a declared digest without bytes,
        undecodable base64 or a digest mismatch all reject the event.
        """
        declared_digest = str(payload.get("photo_sha256") or "").strip().lower()
        photo_b64 = payload.get("photo_base64")

        if not photo_b64:
            if declared_digest:
                raise ValidationError(
                    code="PHOTO_MISSING",
                    message="Event declares a photo digest but carries no photo data.",
                )
            return None, "image/jpeg", ""

        content_type = "image/jpeg"
        raw_b64 = str(photo_b64)
        if raw_b64.startswith("data:") and "," in raw_b64:
            header, raw_b64 = raw_b64.split(",", 1)
            mime = header[5:].split(";", 1)[0].strip().lower()
            if mime in ("image/jpeg", "image/png", "image/webp"):
                content_type = mime
        try:
            photo_bytes = base64.b64decode(raw_b64, validate=True)
        except (binascii.Error, ValueError):
            raise ValidationError(
                code="INVALID_PHOTO_BASE64", message="Photo is not valid base64 data."
            )

        actual_digest = hashlib.sha256(photo_bytes).hexdigest()
        if declared_digest and declared_digest != actual_digest:
            raise ValidationError(
                code="PHOTO_DIGEST_MISMATCH",
                message="Photo data does not match its declared SHA-256 digest.",
            )
        return photo_bytes, content_type, actual_digest

    @staticmethod
    def _parse_captured_at(payload: dict[str, Any], now: datetime) -> datetime:
        raw = str(payload.get("photo_captured_at") or "").strip()
        if not raw:
            return now
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return now
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return min(parsed, now)

    def process_sync_batch(
        self,
        gate_id: uuid.UUID,
        guard_user_id: uuid.UUID,
        society_id: uuid.UUID,
        events: list[dict[str, Any]],
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Processes a batch of offline events, returning per-event acknowledgements."""
        now = utc_now()

        # 1. Gate Guard Assignment Verification
        guard_stmt = select(GateStaffAssignment).where(
            GateStaffAssignment.society_id == society_id,
            GateStaffAssignment.user_id == guard_user_id,
            GateStaffAssignment.gate_id == gate_id,
            GateStaffAssignment.is_active.is_(True),
            GateStaffAssignment.assigned_from <= now,
            or_(
                GateStaffAssignment.assigned_until.is_(None),
                GateStaffAssignment.assigned_until >= now,
            ),
        )
        assignment = self.db.scalars(guard_stmt).first()
        if not assignment:
            raise AuthorizationError(
                code="GATE_ACCESS_DENIED",
                message=f"Guard {guard_user_id} is not actively assigned to Gate {gate_id} in society {society_id}.",
            )

        if not events:
            return {
                "gate_id": str(gate_id),
                "processed_count": 0,
                "results": [],
            }

        results: list[dict[str, Any]] = []
        processed_count = 0

        for raw_event in events:
            # Validate client_event_id is present
            raw_event_id = raw_event.get("client_event_id")
            if not raw_event_id:
                raise ValidationError(
                    code="MISSING_CLIENT_EVENT_ID",
                    message="Each offline event must supply a client_event_id.",
                )

            try:
                client_event_id = (
                    uuid.UUID(raw_event_id) if isinstance(raw_event_id, str) else raw_event_id
                )
            except Exception:
                raise ValidationError(
                    code="INVALID_CLIENT_EVENT_ID",
                    message="client_event_id must be a valid UUIDv4.",
                )

            payload = raw_event.get("payload", {})
            incoming_hash = self.compute_payload_hash(payload)

            # Check for existing sync event with same client_event_id in this society
            stmt = select(OfflineSyncEvent).where(
                OfflineSyncEvent.society_id == society_id,
                OfflineSyncEvent.client_event_id == client_event_id,
            )
            existing_sync = self.db.scalars(stmt).first()

            if existing_sync:
                # Replay Detection
                if existing_sync.payload_hash == incoming_hash:
                    # Idempotent replay: return cached ACK without duplicate record (CHAL-14)
                    results.append(
                        {
                            "client_event_id": str(client_event_id),
                            "status": "ACK",
                            "visitor_id": str(existing_sync.visitor_record_id),
                            "approval_status": "PENDING",
                        }
                    )
                    processed_count += 1
                else:
                    # Tampered payload replay: conflict detected (CHAL-13)
                    results.append(
                        {
                            "client_event_id": str(client_event_id),
                            "status": "CONFLICT",
                            "visitor_id": str(existing_sync.visitor_record_id)
                            if existing_sync.visitor_record_id
                            else None,
                            "error_message": "CONFLICT_EVENT_PAYLOAD_MODIFIED",
                        }
                    )
                continue

            # Process new offline event in isolated nested savepoint (Feature 35)
            savepoint = self.db.begin_nested()
            photo_s3_key: str | None = None
            try:
                dest_flat_id_raw = payload.get("destination_flat_id")
                dest_flat_id = uuid.UUID(str(dest_flat_id_raw)) if dest_flat_id_raw else None

                flat = self.db.get(Flat, dest_flat_id) if dest_flat_id else None
                if not flat or flat.society_id != society_id:
                    savepoint.rollback()
                    results.append(
                        {
                            "client_event_id": str(client_event_id),
                            "status": "ERROR",
                            "error_message": f"Destination flat {dest_flat_id} not found in society.",
                        }
                    )
                    continue

                # Mandatory photo handling: never ACK an event whose declared photo was not stored.
                photo_bytes, photo_content_type, photo_digest = self._decode_photo(payload)
                visitor_id = uuid.uuid4()
                if photo_bytes is not None:
                    try:
                        photo_s3_key = self.retention_service.save_photo_bytes(
                            society_id=society_id,
                            visitor_id=visitor_id,
                            photo_bytes=photo_bytes,
                            content_type=photo_content_type,
                        )
                    except ValidationError:
                        raise
                    except Exception as exc:
                        raise AppException(
                            code="PHOTO_UPLOAD_FAILED",
                            status_code=502,
                            message="Visitor photograph could not be stored; event not acknowledged.",
                        ) from exc

                purpose_val = payload.get("purpose", "GUEST")
                try:
                    purpose = VisitorPurpose(purpose_val)
                except Exception:
                    purpose = VisitorPurpose.GUEST

                # MANDATORY INVARIANT: Always force PENDING and EXPECTED (CHAL-15, Feature 36)
                visitor = VisitorRecord(
                    id=visitor_id,
                    society_id=society_id,
                    gate_id=gate_id,
                    destination_flat_id=dest_flat_id,
                    destination_tower_id=flat.tower_id if flat else None,
                    visitor_name=str(payload.get("visitor_name", "")).strip(),
                    phone_number=str(payload.get("phone_number", "")).strip(),
                    vehicle_number=payload.get("vehicle_number"),
                    purpose=purpose,
                    approval_status=ApprovalStatus.PENDING,
                    entry_status=EntryStatus.EXPECTED,
                    photo_s3_key=photo_s3_key,
                    photo_storage_key=photo_s3_key,
                    photo_sha256=photo_digest or None,
                    photo_captured_at=self._parse_captured_at(payload, now)
                    if photo_s3_key
                    else None,
                    privacy_notice_version=str(
                        payload.get("privacy_notice_version", "v1.0-2026-pune")
                    ),
                    client_event_id=client_event_id,
                    payload_hash=incoming_hash,
                    is_offline_creation=True,
                    created_at=now,
                    updated_at=now,
                )
                self.db.add(visitor)
                self.db.flush()

                sync_event = OfflineSyncEvent(
                    id=uuid.uuid4(),
                    society_id=society_id,
                    gate_id=gate_id,
                    client_event_id=client_event_id,
                    event_type="VISITOR_REGISTRATION",
                    payload_hash=incoming_hash,
                    sync_status=SyncStatus.ACK,
                    visitor_record_id=visitor.id,
                    visitor_id=visitor.id,
                    processed_at=now,
                    created_at=now,
                )
                self.db.add(sync_event)

                audit = AuditEvent(
                    id=uuid.uuid4(),
                    society_id=society_id,
                    actor_id=guard_user_id,
                    action="VISITOR_OFFLINE_SYNCED",
                    resource_type="visitor_record",
                    resource_id=str(visitor.id),
                    correlation_id=correlation_id or str(uuid.uuid4()),
                    event_metadata={
                        "client_event_id": str(client_event_id),
                        "visitor_id": str(visitor.id),
                        "approval_status": ApprovalStatus.PENDING.value,
                    },
                )
                self.db.add(audit)
                savepoint.commit()

                results.append(
                    {
                        "client_event_id": str(client_event_id),
                        "status": "ACK",
                        "visitor_id": str(visitor.id),
                        "approval_status": "PENDING",
                    }
                )
                processed_count += 1
            except Exception as e:
                savepoint.rollback()
                if photo_s3_key:
                    # Do not leave an orphaned object behind for an event that was not acknowledged.
                    with contextlib.suppress(Exception):
                        self.retention_service.storage_provider.delete_object(photo_s3_key)
                error_code = getattr(e, "code", None)
                results.append(
                    {
                        "client_event_id": str(client_event_id),
                        "status": "ERROR",
                        "error_message": f"{error_code}: {e}" if error_code else str(e),
                    }
                )

        self.db.commit()
        return {
            "gate_id": str(gate_id),
            "processed_count": processed_count,
            "results": results,
        }
