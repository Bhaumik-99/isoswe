"""Guest Pass Security & Cryptographic Redemption Service

Implements:
- CSPRNG code generation with 60 bits of entropy (``GP-XXXX-XXXX-XXXX``)
- Keyed HMAC-SHA256 digest persistence (server-side pepper; plaintext is never stored)
- Row-level locking concurrency protection (SELECT ... FOR UPDATE) (CHAL-09)
- Durable, database-backed sliding-window brute-force limiter that is coordinated across AWS
  Lambda instances (5 failed attempts / 10 minutes per gate, and per guard) (CHAL-12)
- State validations for expired, revoked, and exhausted passes (CHAL-10, CHAL-11)
- Automatic entry record creation and check-in upon redemption
"""

import hashlib
import hmac
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import String, cast, delete, func, or_, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import (
    AppException,
    AuthorizationError,
    ConflictError,
    ResourceNotFoundError,
    ValidationError,
)
from app.domains.identity.models import Flat, FlatMembership, MembershipStatus
from app.domains.reliability.models import AuditEvent
from app.domains.visitors.models import (
    ApprovalStatus,
    EntryStatus,
    GateStaffAssignment,
    GuestPass,
    GuestPassFailedAttempt,
    GuestPassRedemption,
    PassStatus,
    PassType,
    VisitorPurpose,
    VisitorRecord,
)

# 31-symbol alphabet without visually ambiguous characters (no 0/O, 1/I/L).
PASS_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
PASS_CODE_PREFIX = "GP-"
PASS_CODE_GROUPS = 3
PASS_CODE_GROUP_LENGTH = 4
PASS_CODE_BODY_LENGTH = PASS_CODE_GROUPS * PASS_CODE_GROUP_LENGTH  # 12 symbols ~ 59.4 bits
MIN_PRODUCTION_SECRET_LENGTH = 32
FAILED_ATTEMPT_RETENTION = timedelta(days=1)

_BODY_PATTERN = re.compile(rf"^[{PASS_CODE_ALPHABET}]{{{PASS_CODE_BODY_LENGTH}}}$")


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_utc(dt: datetime | None) -> datetime:
    if dt is None:
        return datetime.now(UTC)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


class PassRateLimiter:
    """Durable sliding-window brute-force limiter for guest pass verification.

    Failures are persisted in ``guest_pass_failed_attempts`` so every Lambda container sees the
    same counters. A gate is locked after ``max_failures`` failed attempts inside
    ``window_seconds``; the same budget is applied per guard so that a guard cannot rotate between
    assigned gates to multiply their guess budget.
    """

    def __init__(self, max_failures: int = 5, window_seconds: int = 600) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds

    def _window_start(self) -> datetime:
        return utc_now() - timedelta(seconds=self.window_seconds)

    def check_rate_limit(self, db: Session, gate_id: uuid.UUID, guard_user_id: uuid.UUID) -> None:
        """Raises 429 when the gate or guard exhausted its failure budget."""
        if db.get_bind().dialect.name == "postgresql":
            # Serialises concurrent verifications for a gate across instances (released at commit).
            db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": f"guest-pass-gate:{gate_id}"},
            )

        window_start = self._window_start()
        gate_failures = db.scalar(
            select(func.count(GuestPassFailedAttempt.id)).where(
                GuestPassFailedAttempt.gate_id == gate_id,
                GuestPassFailedAttempt.attempted_at >= window_start,
            )
        )
        guard_failures = db.scalar(
            select(func.count(GuestPassFailedAttempt.id)).where(
                GuestPassFailedAttempt.guard_user_id == guard_user_id,
                GuestPassFailedAttempt.attempted_at >= window_start,
            )
        )
        if (gate_failures or 0) >= self.max_failures or (guard_failures or 0) >= self.max_failures:
            raise AppException(
                code="RATE_LIMIT_EXCEEDED",
                status_code=429,
                message="Too many failed passcode attempts at this gate. Access temporarily locked for 10 minutes.",
            )

    def record_failure(
        self,
        db: Session,
        society_id: uuid.UUID,
        gate_id: uuid.UUID,
        guard_user_id: uuid.UUID,
        reason: str,
    ) -> None:
        """Persists a failed attempt and commits immediately so it survives the request rollback."""
        now = utc_now()
        db.execute(
            delete(GuestPassFailedAttempt).where(
                GuestPassFailedAttempt.attempted_at < now - FAILED_ATTEMPT_RETENTION
            )
        )
        db.add(
            GuestPassFailedAttempt(
                id=uuid.uuid4(),
                society_id=society_id,
                gate_id=gate_id,
                guard_user_id=guard_user_id,
                reason=reason[:32],
                attempted_at=now,
            )
        )
        db.commit()

    def reset(self, db: Session, gate_id: uuid.UUID | None = None) -> None:
        """Clears recorded failures (operational unlock and test isolation)."""
        stmt = delete(GuestPassFailedAttempt)
        if gate_id is not None:
            stmt = stmt.where(GuestPassFailedAttempt.gate_id == gate_id)
        db.execute(stmt)
        db.commit()


pass_rate_limiter = PassRateLimiter()


class GuestPassService:
    """Core domain service for resident pre-approved guest passes."""

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def generate_pass_code(prefix: str = PASS_CODE_PREFIX) -> str:
        """Generates an unpredictable CSPRNG code, e.g. ``GP-K7M2-9QXA-V4RB`` (~59 bits)."""
        groups = [
            "".join(secrets.choice(PASS_CODE_ALPHABET) for _ in range(PASS_CODE_GROUP_LENGTH))
            for _ in range(PASS_CODE_GROUPS)
        ]
        return f"{prefix}{'-'.join(groups)}"

    @staticmethod
    def normalize_pass_code(pass_code: str) -> str | None:
        """Canonicalises user input and returns the 12-symbol body, or None when malformed."""
        cleaned = re.sub(r"[\s-]+", "", pass_code or "").upper()
        if not cleaned.startswith("GP"):
            return None
        body = cleaned[2:]
        return body if _BODY_PATTERN.fullmatch(body) else None

    @staticmethod
    def _hmac_key() -> bytes:
        secret = settings.GUEST_PASS_HMAC_SECRET
        if settings.ENVIRONMENT in ("staging", "production"):
            if len(secret) < MIN_PRODUCTION_SECRET_LENGTH:
                raise AppException(
                    code="GUEST_PASS_SECRET_NOT_CONFIGURED",
                    status_code=500,
                    message="Guest pass HMAC secret is not configured for this environment.",
                )
        elif not secret:
            secret = settings.SECRET_KEY
        return secret.encode("utf-8")

    @classmethod
    def hash_pass_code(cls, pass_code: str, society_id: uuid.UUID) -> str:
        """Keyed HMAC-SHA256 digest of the canonical code, bound to the society.

        The digest is deterministic (needed for indexed lookup) but cannot be recomputed or
        brute-forced offline without the server-side secret, unlike an unkeyed/fixed-salt hash.
        """
        body = cls.normalize_pass_code(pass_code)
        if body is None:
            raise ValueError("Malformed guest pass code")
        message = f"guest-pass:v2:{society_id}:{body}".encode()
        return hmac.new(cls._hmac_key(), message, hashlib.sha256).hexdigest()

    def create_guest_pass(
        self,
        society_id: uuid.UUID,
        resident_user_id: uuid.UUID,
        destination_flat_id: uuid.UUID,
        guest_name: str,
        purpose: str,
        pass_type: PassType,
        valid_from: datetime,
        valid_until: datetime,
        max_uses: int = 1,
        guest_phone: str | None = None,
        active_flat_ids: list[uuid.UUID] | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Creates a guest pass with salted SHA-256 hash storage and returns plaintext code once."""
        now = utc_now()

        # 1. Membership / Active flat check
        if active_flat_ids is not None:
            if destination_flat_id not in active_flat_ids:
                raise AuthorizationError(
                    code="FLAT_ACCESS_DENIED",
                    message="Residents can only issue guest passes for their active flat memberships.",
                )
        else:
            mem_stmt = select(FlatMembership).where(
                FlatMembership.user_id == resident_user_id,
                FlatMembership.society_id == society_id,
                FlatMembership.flat_id == destination_flat_id,
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
                    message="Residents can only issue guest passes for their active flat memberships.",
                )

        # 2. Date validation (valid_until >= valid_from)
        if valid_until < valid_from:
            raise ValidationError(
                code="INVALID_DATE_RANGE",
                message="Pass valid_until cannot be earlier than valid_from.",
            )

        # 3. Usage bounds validation
        if pass_type == PassType.SINGLE_USE:
            if max_uses != 1:
                # Normalize or reject if invalid
                max_uses = 1
        elif pass_type == PassType.MULTI_USE and (max_uses < 2 or max_uses > 10):
            raise ValidationError(
                code="INVALID_MAX_USES",
                message="Multi-use pass max_uses must be between 2 and 10.",
            )

        # 4. Generate CSPRNG code & Salted Hash
        pass_code = self.generate_pass_code()
        pass_hash = self.hash_pass_code(pass_code, society_id)

        # 5. Persist pass
        guest_pass = GuestPass(
            id=uuid.uuid4(),
            society_id=society_id,
            destination_flat_id=destination_flat_id,
            flat_id=destination_flat_id,
            created_by_user_id=resident_user_id,
            guest_name=guest_name.strip(),
            guest_phone=guest_phone.strip() if guest_phone else None,
            purpose=purpose.strip(),
            pass_type=pass_type,
            pass_code_prefix="GP-",
            pass_code_hash=pass_hash,
            status=PassStatus.ACTIVE,
            max_uses=max_uses,
            used_count=0,
            valid_from=valid_from,
            valid_until=valid_until,
            created_at=now,
            updated_at=now,
        )
        self.db.add(guest_pass)
        self.db.flush()

        # Audit Event
        audit = AuditEvent(
            id=uuid.uuid4(),
            society_id=society_id,
            actor_id=resident_user_id,
            action="GUEST_PASS_CREATED",
            resource_type="guest_pass",
            resource_id=str(guest_pass.id),
            correlation_id=correlation_id or str(uuid.uuid4()),
            event_metadata={
                "pass_type": pass_type.value,
                "max_uses": max_uses,
                "destination_flat_id": str(destination_flat_id),
                "guest_name": guest_pass.guest_name,
                "valid_from": valid_from.isoformat(),
                "valid_until": valid_until.isoformat(),
            },
        )
        self.db.add(audit)
        self.db.commit()

        return {
            "pass_id": str(guest_pass.id),
            "pass_code": pass_code,  # Returned only once!
            "pass_type": guest_pass.pass_type.value,
            "max_uses": guest_pass.max_uses,
            "used_count": guest_pass.used_count,
            "valid_from": guest_pass.valid_from.isoformat(),
            "valid_until": guest_pass.valid_until.isoformat(),
            "status": guest_pass.status.value,
            "destination_flat_id": str(guest_pass.destination_flat_id),
            "guest_name": guest_pass.guest_name,
            "purpose": guest_pass.purpose,
        }

    def revoke_guest_pass(
        self,
        pass_id: uuid.UUID,
        resident_user_id: uuid.UUID,
        reason: str | None = None,
        active_flat_ids: list[uuid.UUID] | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Revokes an active guest pass."""
        now = utc_now()
        guest_pass = self.db.get(GuestPass, pass_id)
        if not guest_pass:
            raise ResourceNotFoundError(
                code="PASS_NOT_FOUND",
                message=f"Guest pass {pass_id} not found.",
            )

        # Enforce flat membership
        target_flat = guest_pass.destination_flat_id or guest_pass.flat_id
        if active_flat_ids is not None and target_flat not in active_flat_ids:
            raise AuthorizationError(
                code="FLAT_ACCESS_DENIED",
                message="Residents can only revoke guest passes for flats where they hold active membership.",
            )

        if guest_pass.status == PassStatus.REVOKED:
            return {
                "pass_id": str(guest_pass.id),
                "status": guest_pass.status.value,
                "revoked_at": guest_pass.revoked_at.isoformat() if guest_pass.revoked_at else None,
            }

        guest_pass.status = PassStatus.REVOKED
        guest_pass.revoked_at = now
        guest_pass.revoked_by_user_id = resident_user_id
        guest_pass.revocation_reason = reason
        guest_pass.updated_at = now

        audit = AuditEvent(
            id=uuid.uuid4(),
            society_id=guest_pass.society_id,
            actor_id=resident_user_id,
            action="GUEST_PASS_REVOKED",
            resource_type="guest_pass",
            resource_id=str(guest_pass.id),
            correlation_id=correlation_id or str(uuid.uuid4()),
            event_metadata={
                "pass_id": str(guest_pass.id),
                "revoked_at": now.isoformat(),
                "reason": reason or "No reason provided",
            },
        )
        self.db.add(audit)
        self.db.commit()

        return {
            "pass_id": str(guest_pass.id),
            "status": guest_pass.status.value,
            "revoked_at": now.isoformat(),
        }

    def verify_and_redeem_pass(
        self,
        pass_code: str,
        gate_id: uuid.UUID,
        guard_user_id: uuid.UUID,
        society_id: uuid.UUID,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Validates and redeems a guest pass with row locking and brute-force protection."""
        # 1. Durable, distributed rate limiter check (CHAL-12)
        pass_rate_limiter.check_rate_limit(self.db, gate_id, guard_user_id)

        now = utc_now()

        def fail(reason: str, error: Exception) -> Exception:
            """Persist the failed attempt (committed, so it survives rollback) and return error."""
            pass_rate_limiter.record_failure(self.db, society_id, gate_id, guard_user_id, reason)
            return error

        # 2. Derive the keyed digest and look up with concurrency locking (FOR UPDATE) (CHAL-09)
        guest_pass: GuestPass | None = None
        if self.normalize_pass_code(pass_code) is not None:
            target_hash = self.hash_pass_code(pass_code, society_id)
            society_cond_pass = or_(
                cast(GuestPass.society_id, String) == str(society_id),
                cast(GuestPass.society_id, String) == society_id.hex,
            )
            stmt = (
                select(GuestPass)
                .where(
                    society_cond_pass,
                    GuestPass.pass_code_hash == target_hash,
                )
                .with_for_update()
            )
            guest_pass = self.db.scalars(stmt).first()

        # Check guard assignment to gate
        user_cond = or_(
            cast(GateStaffAssignment.user_id, String) == str(guard_user_id),
            cast(GateStaffAssignment.user_id, String) == guard_user_id.hex,
        )
        society_cond = or_(
            cast(GateStaffAssignment.society_id, String) == str(society_id),
            cast(GateStaffAssignment.society_id, String) == society_id.hex,
        )
        gate_cond = or_(
            cast(GateStaffAssignment.gate_id, String) == str(gate_id),
            cast(GateStaffAssignment.gate_id, String) == gate_id.hex,
        )
        guard_stmt = select(GateStaffAssignment).where(
            society_cond,
            user_cond,
            gate_cond,
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

        # Pass status checks take precedence if pass is already exhausted/revoked/expired (CHAL-09)
        if guest_pass:
            if (
                guest_pass.status == PassStatus.EXHAUSTED
                or guest_pass.used_count >= guest_pass.max_uses
            ):
                raise fail(
                    "PASS_EXHAUSTED",
                    ConflictError(
                        code="PASS_EXHAUSTED",
                        message="Guest pass has already reached its maximum allowed redemptions.",
                    ),
                )
            if guest_pass.status == PassStatus.REVOKED:
                raise fail(
                    "PASS_REVOKED",
                    ValidationError(
                        code="PASS_REVOKED",
                        message="Guest pass has been revoked by the resident.",
                    ),
                )
            valid_until = ensure_utc(guest_pass.valid_until)
            valid_from = ensure_utc(guest_pass.valid_from)
            if guest_pass.status == PassStatus.EXPIRED or now > valid_until:
                raise fail(
                    "PASS_EXPIRED",
                    ValidationError(
                        code="PASS_EXPIRED",
                        message="Guest pass has expired and is no longer valid.",
                    ),
                )
            if now < valid_from:
                raise fail(
                    "PASS_NOT_YET_VALID",
                    ValidationError(
                        code="PASS_NOT_YET_VALID",
                        message=f"Guest pass is not valid until {guest_pass.valid_from.isoformat()}.",
                    ),
                )
        # Enforce guard assignment (CHAL-01, CHAL-02)
        if not valid_assignment:
            raise fail(
                "GATE_ACCESS_DENIED",
                AuthorizationError(
                    code="GATE_ACCESS_DENIED",
                    message=f"Guard {guard_user_id} is not actively assigned to Gate {gate_id} in society {society_id}.",
                ),
            )

        # Handle Not Found (also covers malformed codes without revealing the format)
        if not guest_pass:
            raise fail(
                "PASS_NOT_FOUND",
                ResourceNotFoundError(
                    code="PASS_NOT_FOUND",
                    message="Invalid or unknown guest pass code.",
                ),
            )

        # 7. Execute Transactional Redemption
        guest_pass.used_count += 1
        if guest_pass.used_count >= guest_pass.max_uses:
            guest_pass.status = PassStatus.EXHAUSTED
        guest_pass.updated_at = now

        target_flat_id = guest_pass.target_flat_id
        flat = self.db.get(Flat, target_flat_id) if target_flat_id else None

        # Automatically create VisitorRecord and check-in
        visitor = VisitorRecord(
            id=uuid.uuid4(),
            society_id=society_id,
            gate_id=gate_id,
            destination_flat_id=target_flat_id,
            destination_tower_id=flat.tower_id if flat else None,
            visitor_name=guest_pass.guest_name,
            phone_number=guest_pass.guest_phone or "+919999999999",
            purpose=VisitorPurpose.GUEST,
            approval_status=ApprovalStatus.AUTO_APPROVED,
            entry_status=EntryStatus.CHECKED_IN,
            entry_time=now,
            entry_gate_id=gate_id,
            entry_guard_user_id=guard_user_id,
            guest_pass_id=guest_pass.id,
            privacy_notice_version="v1.0-2026-pune",
            created_at=now,
            updated_at=now,
        )
        self.db.add(visitor)
        self.db.flush()

        redemption = GuestPassRedemption(
            id=uuid.uuid4(),
            society_id=society_id,
            guest_pass_id=guest_pass.id,
            visitor_record_id=visitor.id,
            visitor_id=visitor.id,
            gate_id=gate_id,
            redeemed_by_guard_id=guard_user_id,
            redeemed_by_user_id=guard_user_id,
            redemption_sequence=guest_pass.used_count,
            redeemed_at=now,
            created_at=now,
        )
        self.db.add(redemption)

        # Audit Event
        audit = AuditEvent(
            id=uuid.uuid4(),
            society_id=society_id,
            actor_id=guard_user_id,
            action="GUEST_PASS_REDEEMED",
            resource_type="guest_pass",
            resource_id=str(guest_pass.id),
            correlation_id=correlation_id or str(uuid.uuid4()),
            event_metadata={
                "pass_id": str(guest_pass.id),
                "visitor_id": str(visitor.id),
                "gate_id": str(gate_id),
                "used_count": guest_pass.used_count,
                "max_uses": guest_pass.max_uses,
                "remaining_uses": guest_pass.max_uses - guest_pass.used_count,
            },
        )
        self.db.add(audit)
        self.db.commit()

        remaining_uses = max(0, guest_pass.max_uses - guest_pass.used_count)
        return {
            "verified": True,
            "pass_id": str(guest_pass.id),
            "visitor_id": str(visitor.id),
            "guest_name": guest_pass.guest_name,
            "pass_type": guest_pass.pass_type.value,
            "remaining_uses": remaining_uses,
            "approval_status": "AUTO_APPROVED",
            "entry_status": "CHECKED_IN",
            "destination_flat": {
                "flat_id": str(flat.id) if flat else str(target_flat_id),
                "flat_number": flat.flat_number if flat else "",
                "tower_name": flat.tower.name if flat and flat.tower else "",
            }
            if flat
            else None,
        }
