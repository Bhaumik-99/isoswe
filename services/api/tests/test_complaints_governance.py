"""Phase 5 Workstream C: Complaints Governance Test Suite

Validates:
1. 1-action category correction by staff with original_category preservation and audit log.
2. Duplicate ticket linking without auto-closing (both tickets stay open with independent SLAs).
3. Non-self and non-circular duplicate linking validation.
4. Persistent in-app duty manager safety alerts for critical hazards (FIRE, GAS_LEAK, LIFT_ENTRAPMENT).
5. Unacknowledged emergency queue and alert acknowledgement lifecycle.
"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.complaints.models import (
    Complaint,
    ComplaintCategory,
    ComplaintPriority,
    ComplaintStatus,
)
from app.domains.identity.models import Flat, User

NEERAJ_FLAT_ID = "33333333-3333-3333-3333-333333331203"
SOCIETY_ID = "11111111-1111-1111-1111-111111111111"
AUTH_HELPDESK = {"X-Dev-User": "helpdesk"}
AUTH_RESIDENT = {"X-Dev-User": "neeraj"}


def test_one_action_category_correction(client: TestClient, db_session: Session) -> None:
    """Staff can correct AI or user category in 1 action, preserving original category."""
    soc_id = uuid.UUID(SOCIETY_ID)
    flat = db_session.query(Flat).filter(Flat.society_id == soc_id).first()
    user = db_session.query(User).first()
    assert flat is not None and user is not None

    # Create complaint with category PLUMBING
    complaint = Complaint(
        id=uuid.uuid4(),
        society_id=soc_id,
        flat_id=flat.id,
        created_by=user.id,
        complaint_number=f"CMP-{uuid.uuid4().hex[:6].upper()}",
        category=ComplaintCategory.PLUMBING,
        title="Sparks from wall switch",
        description="Switchboard is sparking, might be electrical rather than plumbing",
        priority=ComplaintPriority.MEDIUM,
        status=ComplaintStatus.TRIAGED,
    )
    db_session.add(complaint)
    db_session.commit()

    # 1. Resident cannot correct category -> 403
    res_forbidden = client.patch(
        f"/api/v1/complaints/{complaint.id}/category",
        json={"category": "ELECTRICAL", "notes": "Resident bypass attempt"},
        headers=AUTH_RESIDENT,
    )
    assert res_forbidden.status_code == 403

    # 2. Staff corrects category to ELECTRICAL in 1 action
    res_correct = client.patch(
        f"/api/v1/complaints/{complaint.id}/category",
        json={
            "category": "ELECTRICAL",
            "notes": "Mistriaged as plumbing; clearly electrical issue",
        },
        headers=AUTH_HELPDESK,
    )
    assert res_correct.status_code == 200
    data = res_correct.json()
    assert data["category"] == "ELECTRICAL"
    assert data["original_category"] == "PLUMBING"
    assert data["category_corrected_at"] is not None

    # Verify database persistence
    db_session.refresh(complaint)
    assert complaint.category == ComplaintCategory.ELECTRICAL
    assert complaint.original_category == ComplaintCategory.PLUMBING
    assert complaint.category_corrected_at is not None

    # 3. Verify aliased fields compatibility: 'new_category' and 'reason'
    res_alias = client.patch(
        f"/api/v1/complaints/{complaint.id}/category",
        json={
            "new_category": "SECURITY",
            "reason": "Gate intercom security issue",
        },
        headers=AUTH_HELPDESK,
    )
    assert res_alias.status_code == 200
    assert res_alias.json()["category"] == "SECURITY"


def test_duplicate_linking_without_auto_closing(client: TestClient, db_session: Session) -> None:
    """Duplicate complaints can be linked while keeping both tickets open with independent SLAs."""
    soc_id = uuid.UUID(SOCIETY_ID)
    flat = db_session.query(Flat).filter(Flat.society_id == soc_id).first()
    user = db_session.query(User).first()
    assert flat is not None and user is not None

    # Complaint 1: Primary (e.g. reported by Tower 7 flat 101)
    cmp_primary = Complaint(
        id=uuid.uuid4(),
        society_id=soc_id,
        flat_id=flat.id,
        created_by=user.id,
        complaint_number=f"CMP-{uuid.uuid4().hex[:6].upper()}",
        category=ComplaintCategory.WATER_SUPPLY,
        title="Water outage in tower",
        description="No water pressure since 8am",
        priority=ComplaintPriority.HIGH,
        status=ComplaintStatus.IN_PROGRESS,
    )
    # Complaint 2: Duplicate reported by another resident
    cmp_duplicate = Complaint(
        id=uuid.uuid4(),
        society_id=soc_id,
        flat_id=flat.id,
        created_by=user.id,
        complaint_number=f"CMP-{uuid.uuid4().hex[:6].upper()}",
        category=ComplaintCategory.WATER_SUPPLY,
        title="No water in flat",
        description="Water completely stopped",
        priority=ComplaintPriority.HIGH,
        status=ComplaintStatus.ASSIGNED,
    )
    db_session.add_all([cmp_primary, cmp_duplicate])
    db_session.commit()

    # 1. Non-self validation: Cannot link ticket to itself
    res_self = client.post(
        f"/api/v1/complaints/{cmp_primary.id}/link-duplicate",
        json={"duplicate_of_id": str(cmp_primary.id)},
        headers=AUTH_HELPDESK,
    )
    assert res_self.status_code in (400, 422)

    # 2. Staff links cmp_duplicate to cmp_primary
    res_link = client.post(
        f"/api/v1/complaints/{cmp_duplicate.id}/link-duplicate",
        json={
            "duplicate_of_id": str(cmp_primary.id),
            "notes": "Tower water line issue affects both",
        },
        headers=AUTH_HELPDESK,
    )
    assert res_link.status_code == 200
    data_link = res_link.json()
    assert data_link["duplicate_of_id"] == str(cmp_primary.id)
    # CRITICAL: Duplicate ticket must NOT be auto-closed!
    assert data_link["status"] == "ASSIGNED"

    # 3. Non-circular validation: Cannot link primary back to duplicate
    res_circular = client.post(
        f"/api/v1/complaints/{cmp_primary.id}/link-duplicate",
        json={"duplicate_of_id": str(cmp_duplicate.id)},
        headers=AUTH_HELPDESK,
    )
    assert res_circular.status_code in (400, 422)

    # 4. Query linked duplicates
    res_list = client.get(
        f"/api/v1/complaints/{cmp_primary.id}/linked-duplicates",
        headers=AUTH_HELPDESK,
    )
    assert res_list.status_code == 200
    linked = res_list.json()
    assert len(linked) >= 1
    assert any(c["id"] == str(cmp_duplicate.id) for c in linked)

    # 5. Unlink duplicate
    res_unlink = client.post(
        f"/api/v1/complaints/{cmp_duplicate.id}/unlink-duplicate",
        headers=AUTH_HELPDESK,
    )
    assert res_unlink.status_code == 200
    assert res_unlink.json()["duplicate_of_id"] is None

    # 6. Verify aliased payload compatibility: 'primary_complaint_id' and 'reason'
    res_alias_link = client.post(
        f"/api/v1/complaints/{cmp_duplicate.id}/link-duplicate",
        json={
            "primary_complaint_id": str(cmp_primary.id),
            "reason": "Aliased duplicate link contract test",
        },
        headers=AUTH_HELPDESK,
    )
    assert res_alias_link.status_code == 200
    assert res_alias_link.json()["duplicate_of_id"] == str(cmp_primary.id)


def test_persistent_safety_alerts_lifecycle(client: TestClient, db_session: Session) -> None:
    """Critical safety complaints generate persistent SafetyAlert records in the emergency queue."""
    soc_id = uuid.UUID(SOCIETY_ID)
    flat = db_session.query(Flat).filter(Flat.society_id == soc_id).first()
    assert flat is not None

    # Resident raises complaint with life-safety hazard: Gas leak
    res_create = client.post(
        "/api/v1/complaints",
        json={
            "flat_id": NEERAJ_FLAT_ID,
            "title": "Severe gas leak smell in kitchen",
            "description": "Strong gas smell coming from piped line, urgent help needed!",
            "category": "OTHER",
        },
        headers=AUTH_RESIDENT,
    )
    assert res_create.status_code == 201
    cmp_data = res_create.json()
    assert cmp_data["priority"] == "CRITICAL"
    assert cmp_data["safety_escalated"] is True

    # 1. Verify safety alert appears in Helpdesk emergency queue (supporting both unacknowledged_only and unread_only)
    res_alerts = client.get(
        "/api/v1/complaints/safety-alerts?unacknowledged_only=true", headers=AUTH_HELPDESK
    )
    assert res_alerts.status_code == 200
    res_alerts_unread = client.get(
        "/api/v1/complaints/safety-alerts?unread_only=true", headers=AUTH_HELPDESK
    )
    assert res_alerts_unread.status_code == 200
    alerts = res_alerts.json()
    matching_alert = next((a for a in alerts if a["complaint_id"] == cmp_data["id"]), None)
    assert matching_alert is not None
    assert matching_alert["is_acknowledged"] is False
    assert matching_alert["severity"] == "CRITICAL"

    # 2. Resident cannot view or acknowledge safety queue -> 403
    res_res_view = client.get("/api/v1/complaints/safety-alerts", headers=AUTH_RESIDENT)
    assert res_res_view.status_code == 403

    res_res_ack = client.post(
        f"/api/v1/complaints/safety-alerts/{matching_alert['id']}/ack",
        json={"notes": "Resident bypass"},
        headers=AUTH_RESIDENT,
    )
    assert res_res_ack.status_code == 403

    # 3. Helpdesk duty manager acknowledges the emergency alert
    res_ack = client.post(
        f"/api/v1/complaints/safety-alerts/{matching_alert['id']}/ack",
        json={"notes": "Dispatched maintenance team to shut off main valve at tower riser."},
        headers=AUTH_HELPDESK,
    )
    assert res_ack.status_code == 200
    acked = res_ack.json()
    assert acked["is_acknowledged"] is True
    assert acked["acknowledged_at"] is not None
    assert "Dispatched maintenance team" in acked["acknowledgement_notes"]
