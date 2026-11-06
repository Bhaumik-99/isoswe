"""E2E Test Configuration, Shared Fixtures and Seed Helpers for Phase 6.

Provides:
- Fixed deterministic IDs for Society, Towers, Flats, Gates, and Users.
- Auth headers for Resident (Neeraj, Swati, Aamir) and Gate Staff (Helpdesk).
- Realistic sample photos (raw JPEG bytes and base64 data URLs).
- `gate_environment` fixture that initializes gates, staff assignments, and permissions.
"""

import base64
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domains.identity.models import (
    FlatMembership,
    MembershipStatus,
    MembershipType,
    Permission,
    RoleType,
    User,
    UserRole,
    UserStatus,
)

# -----------------------------------------------------------------------------
# Deterministic Identifiers
# -----------------------------------------------------------------------------
SOCIETY_PUNE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
OTHER_SOCIETY_ID = uuid.UUID("99999999-9999-9999-9999-999999999999")

TOWER_T07_ID = uuid.UUID("22222222-2222-2222-2222-222222222207")
TOWER_T12_ID = uuid.UUID("22222222-2222-2222-2222-222222222212")
TOWER_T21_ID = uuid.UUID("22222222-2222-2222-2222-222222222221")

FLAT_1203_ID = uuid.UUID("33333333-3333-3333-3333-333333331203")
FLAT_0408_ID = uuid.UUID("33333333-3333-3333-3333-333333330408")
FLAT_1601_ID = uuid.UUID("33333333-3333-3333-3333-333333331601")
FLAT_OTHER_ID = uuid.UUID("33333333-3333-3333-3333-333333339999")

USER_NEERAJ_ID = uuid.UUID("44444444-4444-4444-4444-444444440001")
USER_SWATI_ID = uuid.UUID("44444444-4444-4444-4444-444444440002")
USER_AAMIR_ID = uuid.UUID("44444444-4444-4444-4444-444444440003")
USER_HELPDESK_ID = uuid.UUID("44444444-4444-4444-4444-444444440004")
USER_HELPDESK_2_ID = uuid.UUID("44444444-4444-4444-4444-444444440005")

# 4 Gates for Marvel Greenfield Residences
GATE_1_ID = uuid.UUID("aaaaaaaa-1111-0000-0000-000000000001")
GATE_2_ID = uuid.UUID("aaaaaaaa-2222-0000-0000-000000000002")
GATE_3_ID = uuid.UUID("aaaaaaaa-3333-0000-0000-000000000003")
GATE_4_ID = uuid.UUID("aaaaaaaa-4444-0000-0000-000000000004")

# External Society Gate for Cross-Tenant Testing
OTHER_GATE_ID = uuid.UUID("bbbbbbbb-9999-0000-0000-000000000099")

# -----------------------------------------------------------------------------
# Auth Headers
# -----------------------------------------------------------------------------
NEERAJ_HEADERS = {"X-Dev-User": "neeraj"}
SWATI_HEADERS = {"X-Dev-User": "swati"}
AAMIR_HEADERS = {"X-Dev-User": "aamir"}
GATE_GUARD_HEADERS = {"X-Dev-User": "helpdesk"}
GATE_GUARD_2_HEADERS = {"X-Dev-User": "helpdesk-2"}

# -----------------------------------------------------------------------------
# Realistic Mock Photo Assets
# -----------------------------------------------------------------------------
# Minimal valid 1x1 pixel JPEG binary
TINY_JPEG_BYTES = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00"
    b"\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19"
    b"\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f"
    b"'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f"
    b"\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02"
    b"\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00"
    b"\xff\xd9"
)
TINY_JPEG_BASE64 = f"data:image/jpeg;base64,{base64.b64encode(TINY_JPEG_BYTES).decode('ascii')}"


# Safe permission resolver attribute
GATE_OPERATIONS_PERM = getattr(Permission, "GATE_OPERATIONS", "GATE_OPERATIONS")


@pytest.fixture(scope="function")
def gate_environment(db_session: Session) -> dict:
    """Configures the complete gate environment in the test database.

    Creates/verifies gates, gate assignments, and grants the GATE_OPERATIONS permission
    to user_helpdesk for Marvel Greenfield Residences.
    """
    now = datetime.now(UTC)

    # 1. Ensure tables exist (compatible with pre-migration and post-migration SQLite test DB)
    db_session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS gates (
                id VARCHAR(36) PRIMARY KEY,
                society_id VARCHAR(36) NOT NULL,
                gate_number VARCHAR(32) NOT NULL,
                name VARCHAR(128) NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
    )
    db_session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS gate_assignments (
                id VARCHAR(36) PRIMARY KEY,
                society_id VARCHAR(36) NOT NULL,
                gate_id VARCHAR(36) NOT NULL,
                user_id VARCHAR(36) NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                assigned_from TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                assigned_until TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
    )
    db_session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS visitors (
                id VARCHAR(36) PRIMARY KEY,
                society_id VARCHAR(36) NOT NULL,
                gate_id VARCHAR(36) NOT NULL,
                exit_gate_id VARCHAR(36),
                visitor_name VARCHAR(255) NOT NULL,
                phone_number VARCHAR(32) NOT NULL,
                vehicle_number VARCHAR(32),
                purpose VARCHAR(64) NOT NULL,
                destination_tower_id VARCHAR(36) NOT NULL,
                destination_flat_id VARCHAR(36) NOT NULL,
                guest_pass_id VARCHAR(36),
                created_by_user_id VARCHAR(36) NOT NULL,
                photo_storage_key VARCHAR(255),
                photo_captured_at TIMESTAMP,
                photo_deleted_at TIMESTAMP,
                privacy_notice_version VARCHAR(32) NOT NULL DEFAULT 'v1.0',
                client_event_id VARCHAR(128),
                payload_hash VARCHAR(64),
                approval_status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
                approved_by_user_id VARCHAR(36),
                approved_at TIMESTAMP,
                rejection_reason VARCHAR(255),
                entry_status VARCHAR(32) NOT NULL DEFAULT 'EXPECTED',
                entry_time TIMESTAMP,
                exit_time TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
    )
    db_session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS guest_passes (
                id VARCHAR(36) PRIMARY KEY,
                society_id VARCHAR(36) NOT NULL,
                flat_id VARCHAR(36) NOT NULL,
                created_by_user_id VARCHAR(36) NOT NULL,
                pass_type VARCHAR(32) NOT NULL,
                guest_name VARCHAR(255) NOT NULL,
                guest_phone VARCHAR(32),
                pass_code_prefix VARCHAR(16) NOT NULL,
                pass_code_hash VARCHAR(128) NOT NULL,
                valid_from TIMESTAMP NOT NULL,
                valid_until TIMESTAMP NOT NULL,
                max_uses INT NOT NULL DEFAULT 1,
                used_count INT NOT NULL DEFAULT 0,
                status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
                purpose VARCHAR(128) NOT NULL DEFAULT 'Guest',
                revoked_at TIMESTAMP,
                revoked_by_user_id VARCHAR(36),
                revocation_reason VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
    )
    db_session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS guest_pass_redemptions (
                id VARCHAR(36) PRIMARY KEY,
                society_id VARCHAR(36) NOT NULL,
                guest_pass_id VARCHAR(36) NOT NULL,
                visitor_id VARCHAR(36) NOT NULL,
                gate_id VARCHAR(36) NOT NULL,
                redeemed_by_user_id VARCHAR(36) NOT NULL,
                redeemed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
    )

    # 2. Seed 4 Gates for Marvel Greenfield
    gates_data = [
        (str(GATE_1_ID), str(SOCIETY_PUNE_ID), "1", "Gate 1 - North Main", "ACTIVE"),
        (str(GATE_2_ID), str(SOCIETY_PUNE_ID), "2", "Gate 2 - South Commercial", "ACTIVE"),
        (str(GATE_3_ID), str(SOCIETY_PUNE_ID), "3", "Gate 3 - East Service", "ACTIVE"),
        (str(GATE_4_ID), str(SOCIETY_PUNE_ID), "4", "Gate 4 - West Resident", "ACTIVE"),
        (str(OTHER_GATE_ID), str(OTHER_SOCIETY_ID), "1", "Other Society Main Gate", "ACTIVE"),
    ]
    for gid, soc_id, gnum, gname, status in gates_data:
        db_session.execute(
            text(
                """
                INSERT OR REPLACE INTO gates (id, society_id, gate_number, name, status, created_at, updated_at)
                VALUES (:id, :society_id, :gate_number, :name, :status, :created_at, :updated_at)
                """
            ),
            {
                "id": gid,
                "society_id": soc_id,
                "gate_number": gnum,
                "name": gname,
                "status": status,
                "created_at": now,
                "updated_at": now,
            },
        )

    # 3. Seed active Gate Assignments:
    # user_helpdesk assigned to Gate 1 (active)
    db_session.execute(
        text(
            """
            INSERT OR REPLACE INTO gate_assignments (id, society_id, gate_id, user_id, is_active, assigned_from, created_at, updated_at)
            VALUES (:id, :society_id, :gate_id, :user_id, 1, :assigned_from, :created_at, :updated_at)
            """
        ),
        {
            "id": str(uuid.UUID("77777777-1111-0000-0000-000000000001")),
            "society_id": str(SOCIETY_PUNE_ID),
            "gate_id": str(GATE_1_ID),
            "user_id": str(USER_HELPDESK_ID),
            "assigned_from": now - timedelta(days=1),
            "created_at": now,
            "updated_at": now,
        },
    )

    # 4. Scope user_helpdesk strictly to GATE_OPERATIONS in gate_environment so GATE_GUARD_HEADERS
    # represents a true gate-only operator without billing/reconciliation privileges.
    perm_val = (
        GATE_OPERATIONS_PERM.value
        if hasattr(GATE_OPERATIONS_PERM, "value")
        else str(GATE_OPERATIONS_PERM)
    )
    db_session.execute(
        text(
            "DELETE FROM user_permissions WHERE (user_id = :u1 OR user_id = :u2) AND permission != :perm"
        ),
        {
            "u1": str(USER_HELPDESK_ID),
            "u2": USER_HELPDESK_ID.hex,
            "perm": perm_val,
        },
    )
    existing_perm = db_session.execute(
        text(
            "SELECT id FROM user_permissions WHERE (user_id = :u1 OR user_id = :u2) AND society_id = :sid AND permission = :perm"
        ),
        {
            "u1": str(USER_HELPDESK_ID),
            "u2": USER_HELPDESK_ID.hex,
            "sid": str(SOCIETY_PUNE_ID),
            "perm": perm_val,
        },
    ).fetchone()

    if not existing_perm:
        db_session.execute(
            text(
                """
                INSERT INTO user_permissions (id, user_id, society_id, permission, created_at)
                VALUES (:id, :uid, :sid, :perm, :created_at)
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "uid": str(USER_HELPDESK_ID),
                "sid": str(SOCIETY_PUNE_ID),
                "perm": perm_val,
                "created_at": now,
            },
        )

    # 5. Create an expired tenant membership for adversarial lease-expiry testing
    expired_tenant_user_id = uuid.UUID("44444444-4444-4444-4444-444444440099")
    existing_expired_user = db_session.get(User, expired_tenant_user_id)
    if not existing_expired_user:
        expired_user = User(
            id=expired_tenant_user_id,
            supabase_uid=uuid.UUID("00000000-0000-0000-0000-000000000099"),
            phone="+91-98000-00099",
            email="expired.tenant@example.com",
            full_name="Kiran Expired",
            status=UserStatus.ACTIVE,
        )
        db_session.add(expired_user)
        db_session.flush()

        db_session.add(
            UserRole(
                user_id=expired_tenant_user_id,
                society_id=SOCIETY_PUNE_ID,
                role=RoleType.RESIDENT,
            )
        )
        db_session.add(
            FlatMembership(
                id=uuid.UUID("55555555-5555-5555-5555-555555550099"),
                society_id=SOCIETY_PUNE_ID,
                user_id=expired_tenant_user_id,
                flat_id=FLAT_1203_ID,
                membership_type=MembershipType.TENANT,
                valid_from=now - timedelta(days=400),
                valid_until=now - timedelta(days=1),  # Expired yesterday
                is_primary=False,
                status=MembershipStatus.EXPIRED,
            )
        )

    db_session.commit()

    return {
        "society_id": SOCIETY_PUNE_ID,
        "other_society_id": OTHER_SOCIETY_ID,
        "gate_1_id": GATE_1_ID,
        "gate_2_id": GATE_2_ID,
        "gate_3_id": GATE_3_ID,
        "gate_4_id": GATE_4_ID,
        "other_gate_id": OTHER_GATE_ID,
        "tower_t07_id": TOWER_T07_ID,
        "flat_1203_id": FLAT_1203_ID,
        "flat_0408_id": FLAT_0408_ID,
        "flat_1601_id": FLAT_1601_ID,
        "user_neeraj_id": USER_NEERAJ_ID,
        "user_swati_id": USER_SWATI_ID,
        "user_helpdesk_id": USER_HELPDESK_ID,
        "expired_tenant_user_id": expired_tenant_user_id,
    }
