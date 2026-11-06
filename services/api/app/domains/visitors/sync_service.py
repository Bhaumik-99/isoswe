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
import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import AuthorizationError, ValidationError
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

        canonical_repr = f"name:{name}|phone:{phone}|vehicle:{vehicle}|purpose:{purpose}|flat:{flat_id}|notice:{notice_ver}"
        return hashlib.sha256(canonical_repr.encode()).hexdigest()

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
            try:
                dest_flat_id_raw = payload.get("destination_flat_id")
                dest_flat_id = uuid.UUID(str(dest_flat_id_raw)) if dest_flat_id_raw else None

                flat = self.db.get(Flat, dest_flat_id) if dest_flat_id else None
                if not flat or flat.society_id != society_id:
                    results.append(
                        {
                            "client_event_id": str(client_event_id),
                            "status": "ERROR",
                            "error_message": f"Destination flat {dest_flat_id} not found in society.",
                        }
                    )
                    continue

                # Handle offline photo upload
                photo_s3_key: str | None = None
                photo_base64 = payload.get("photo_base64")
                visitor_id = uuid.uuid4()

                if photo_base64:
                    try:
                        raw_b64 = photo_base64
                        if "," in raw_b64:
                            raw_b64 = raw_b64.split(",", 1)[1]
                        photo_bytes = base64.b64decode(raw_b64)
                        photo_s3_key = self.retention_service.save_photo_bytes(
                            society_id=society_id,
                            visitor_id=visitor_id,
                            photo_bytes=photo_bytes,
                        )
                    except Exception:
                        pass

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
                    photo_captured_at=now if photo_s3_key else None,
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
                results.append(
                    {
                        "client_event_id": str(client_event_id),
                        "status": "ERROR",
                        "error_message": str(e),
                    }
                )

        self.db.commit()
        return {
            "gate_id": str(gate_id),
            "processed_count": processed_count,
            "results": results,
        }
