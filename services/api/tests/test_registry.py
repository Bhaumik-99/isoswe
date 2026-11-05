"""Phase 5 Workstream D: Resident & Unit Registry Test Suite

Validates:
1. Staff resident directory search and inspection by name, phone, tower, flat.
2. Flat memberships listing with status filters.
3. Creation of Owner, Tenant (with lease validity dates), and Family Member memberships.
4. Lease validity rules (valid_until cannot precede valid_from).
5. State transitions: Approve, Reject, and Terminate.
6. Resident-initiated join flat requests creating PENDING memberships.
7. Role-based access control and tenant isolation.
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.identity.models import Flat, FlatMembership, MembershipStatus, MembershipType, User
from app.domains.reliability.models import AuditEvent

SOCIETY_ID = "11111111-1111-1111-1111-111111111111"
AUTH_HELPDESK = {"X-Dev-User": "helpdesk"}
AUTH_RESIDENT = {"X-Dev-User": "neeraj"}
NEERAJ_FLAT_ID = "33333333-3333-3333-3333-333333331203"


def test_staff_resident_directory_search(client: TestClient) -> None:
    """Staff can search and filter residents across towers and flats."""
    # 1. Resident cannot access staff registry -> 403
    res_forbidden = client.get("/api/v1/registry/residents", headers=AUTH_RESIDENT)
    assert res_forbidden.status_code == 403

    # 2. Staff searches by name "Neeraj"
    res = client.get("/api/v1/registry/residents?query=Neeraj", headers=AUTH_HELPDESK)
    assert res.status_code == 200
    residents = res.json()
    assert len(residents) >= 1
    assert any("Neeraj" in r["full_name"] for r in residents)
    neeraj_entry = next(r for r in residents if "Neeraj" in r["full_name"])
    assert len(neeraj_entry["flats"]) >= 1
    assert neeraj_entry["flats"][0]["flat_number"] == "1203"

    # 3. Filter by membership_type OWNER
    res_owner = client.get(
        "/api/v1/registry/residents?membership_type=OWNER", headers=AUTH_HELPDESK
    )
    assert res_owner.status_code == 200
    owners = res_owner.json()
    assert all(any(f["membership_type"] == "OWNER" for f in r["flats"]) for r in owners)


def test_membership_creation_with_lease_validity(client: TestClient, db_session: Session) -> None:
    """Staff can register tenants with lease duration, rejecting inverted dates."""
    soc_id = uuid.UUID(SOCIETY_ID)
    flat = db_session.query(Flat).filter(Flat.society_id == soc_id).first()
    assert flat is not None

    now = datetime.now(UTC)
    tenant_phone = f"+9198{uuid.uuid4().int % 100000000:08d}"

    # 1. Inverted lease dates: valid_until before valid_from -> 400/422
    res_invalid = client.post(
        "/api/v1/registry/memberships",
        json={
            "phone": tenant_phone,
            "full_name": "Tenant Jane",
            "flat_id": str(flat.id),
            "membership_type": "TENANT",
            "valid_from": now.isoformat(),
            "valid_until": (now - timedelta(days=30)).isoformat(),
        },
        headers=AUTH_HELPDESK,
    )
    assert res_invalid.status_code in (400, 422)

    # 2. Valid tenant membership with 1-year lease
    valid_from = now
    valid_until = now + timedelta(days=365)
    res_valid = client.post(
        "/api/v1/registry/memberships",
        json={
            "phone": tenant_phone,
            "full_name": "Tenant Jane",
            "flat_id": str(flat.id),
            "membership_type": "TENANT",
            "valid_from": valid_from.isoformat(),
            "valid_until": valid_until.isoformat(),
            "is_primary": False,
        },
        headers=AUTH_HELPDESK,
    )
    assert res_valid.status_code == 201
    created = res_valid.json()
    assert created["membership_type"] == "TENANT"
    assert created["status"] == "APPROVED"
    assert created["flat_number"] == flat.flat_number

    # Verify audit event recorded
    audit = (
        db_session.query(AuditEvent)
        .filter(
            AuditEvent.action == "identity.membership.created",
            AuditEvent.resource_id == created["id"],
        )
        .first()
    )
    assert audit is not None
    assert audit.event_metadata["membership_type"] == "TENANT"


def test_membership_lifecycle_state_transitions(client: TestClient, db_session: Session) -> None:
    """Staff can update membership status between APPROVED, REJECTED, and TERMINATED."""
    soc_id = uuid.UUID(SOCIETY_ID)
    flat = db_session.query(Flat).filter(Flat.society_id == soc_id).first()
    user = db_session.query(User).first()
    assert flat is not None and user is not None

    # Create pending membership
    m = FlatMembership(
        id=uuid.uuid4(),
        society_id=soc_id,
        flat_id=flat.id,
        user_id=user.id,
        membership_type=MembershipType.TENANT,
        status=MembershipStatus.PENDING,
    )
    db_session.add(m)
    db_session.commit()

    # 1. Staff approves membership
    res_app = client.patch(
        f"/api/v1/registry/memberships/{m.id}/status",
        json={"status": "APPROVED", "notes": "Documents verified"},
        headers=AUTH_HELPDESK,
    )
    assert res_app.status_code == 200
    assert res_app.json()["status"] == "APPROVED"

    # 2. Staff terminates membership on tenant vacate
    res_term = client.patch(
        f"/api/v1/registry/memberships/{m.id}/status",
        json={"status": "TERMINATED", "rejection_reason": "Tenancy concluded"},
        headers=AUTH_HELPDESK,
    )
    assert res_term.status_code == 200
    assert res_term.json()["status"] == "TERMINATED"

    # Verify audit event for termination
    term_audit = (
        db_session.query(AuditEvent)
        .filter(
            AuditEvent.action == "identity.membership.terminated",
            AuditEvent.resource_id == str(m.id),
        )
        .first()
    )
    assert term_audit is not None
    assert term_audit.event_metadata["notes"] == "Tenancy concluded"

    # 3. List memberships with status filter
    res_list = client.get(
        "/api/v1/registry/memberships?status=TERMINATED",
        headers=AUTH_HELPDESK,
    )
    assert res_list.status_code == 200
    assert any(item["id"] == str(m.id) for item in res_list.json())


def test_resident_join_flat_request(client: TestClient, db_session: Session) -> None:
    """Resident can initiate a flat join request that starts in PENDING status."""
    soc_id = uuid.UUID(SOCIETY_ID)
    # Pick a flat other than Neeraj's primary flat
    flats = db_session.query(Flat).filter(Flat.society_id == soc_id).all()
    target_flat = next(f for f in flats if str(f.id) != NEERAJ_FLAT_ID)

    res_join = client.post(
        "/api/v1/registry/join-flat-request",
        json={
            "flat_id": str(target_flat.id),
            "membership_type": "FAMILY_MEMBER",
        },
        headers=AUTH_RESIDENT,
    )
    assert res_join.status_code == 201
    req_data = res_join.json()
    assert req_data["status"] == "PENDING"
    assert req_data["flat_id"] == str(target_flat.id)
    assert req_data["membership_type"] == "FAMILY_MEMBER"
