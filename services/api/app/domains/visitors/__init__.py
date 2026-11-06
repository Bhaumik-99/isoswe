"""Visitor Domain Package

Provides domain models, schemas, and core services for ISOSWE Phase 6
Perimeter Security, Gate Tablet Operations, and Guest Passes.
"""

from app.domains.visitors.models import (
    ApprovalStatus,
    EntryStatus,
    Gate,
    GateStaffAssignment,
    GateStatus,
    GuestPass,
    GuestPassRedemption,
    OfflineSyncEvent,
    PassStatus,
    PassType,
    SyncStatus,
    VisitorPurpose,
    VisitorRecord,
)
from app.domains.visitors.schemas import (
    GateSchema,
    GateSessionResponse,
    GateStaffAssignmentSchema,
    GuestPassCreateRequest,
    GuestPassResponse,
    GuestPassVerifyRequest,
    GuestPassVerifyResponse,
    OfflineSyncBatchItem,
    OfflineSyncBatchRequest,
    OfflineSyncBatchResponse,
    OfflineSyncEventPayload,
    OfflineSyncEventResult,
    ResidentVisitorActionRequest,
    VisitorRegisterRequest,
    VisitorResponse,
)
from app.domains.visitors.service import VisitorService, mask_phone_number

__all__ = [
    "ApprovalStatus",
    "EntryStatus",
    "Gate",
    "GateSchema",
    "GateSessionResponse",
    "GateStaffAssignment",
    "GateStaffAssignmentSchema",
    "GateStatus",
    "GuestPass",
    "GuestPassCreateRequest",
    "GuestPassRedemption",
    "GuestPassResponse",
    "GuestPassVerifyRequest",
    "GuestPassVerifyResponse",
    "OfflineSyncBatchItem",
    "OfflineSyncBatchRequest",
    "OfflineSyncBatchResponse",
    "OfflineSyncEvent",
    "OfflineSyncEventPayload",
    "OfflineSyncEventResult",
    "PassStatus",
    "PassType",
    "ResidentVisitorActionRequest",
    "SyncStatus",
    "VisitorPurpose",
    "VisitorRecord",
    "VisitorRegisterRequest",
    "VisitorResponse",
    "VisitorService",
    "mask_phone_number",
]
