"""Complaints & Helpdesk Operations Endpoint Tests

Covers:
1. Resident complaint submission and validation
2. Tenant isolation and cross-flat authorization barriers (403)
3. Deterministic multilingual safety escalation (English, Hindi, Marathi)
4. AI suggestion isolation and safety override protection
5. Workload-based helpdesk auto-assignment
6. Duplicate candidate detection
7. Public comments vs. private internal helpdesk notes visibility
8. Attachment MIME type & 5MB size limit validation
9. Server-authoritative lifecycle state transitions
10. 7-day reopening window enforcement
11. Resident satisfaction rating & feedback
12. Helpdesk dashboard KPI metrics aggregation
13. Immutable audit timeline & transactional outbox event emission
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.complaints.models import (
    Complaint,
)
from app.domains.reliability.models import OutboxEvent

NEERAJ_HEADERS = {"X-Dev-User": "neeraj"}
SWATI_HEADERS = {"X-Dev-User": "swati"}
HELPDESK_HEADERS = {"X-Dev-User": "helpdesk"}

NEERAJ_FLAT_ID = "33333333-3333-3333-3333-333333331203"
SWATI_FLAT_ID = "33333333-3333-3333-3333-333333330408"
OTHER_SOCIETY_FLAT_ID = "33333333-3333-3333-3333-333333339999"


# =============================================================================
# 1. Resident Complaint Submission & Validation
# =============================================================================


def test_resident_create_complaint_success(client: TestClient, db_session: Session) -> None:
    payload = {
        "flat_id": NEERAJ_FLAT_ID,
        "title": "Kitchen faucet leaking constantly",
        "description": "The kitchen faucet has been dripping water for two days and needs washer replacement.",
        "category": "PLUMBING",
        "subcategory": "Faucet",
    }
    response = client.post("/api/v1/complaints", json=payload, headers=NEERAJ_HEADERS)
    assert response.status_code == 201
    data = response.json()

    assert data["complaint_number"].startswith("CMP-")
    assert data["flat_id"] == NEERAJ_FLAT_ID
    assert data["title"] == payload["title"]
    assert data["category"] == "PLUMBING"
    assert data["safety_escalated"] is False
    assert data["status"] in ("ASSIGNED", "TRIAGED")
    assert data["creator_name"] == "Neeraj Kulkarni"
    assert len(data["activities"]) >= 1

    # Verify database outbox event
    outbox = (
        db_session.query(OutboxEvent)
        .filter(
            OutboxEvent.aggregate_id == data["id"],
            OutboxEvent.event_type == "complaint.created",
        )
        .first()
    )
    assert outbox is not None


def test_resident_cross_flat_denial_forbidden(client: TestClient) -> None:
    # Neeraj attempts to raise a complaint for Swati's flat (0408)
    payload = {
        "flat_id": SWATI_FLAT_ID,
        "title": "Balcony door rattling",
        "description": "Strong wind makes the balcony door rattle at night.",
        "category": "OTHER",
    }
    response = client.post("/api/v1/complaints", json=payload, headers=NEERAJ_HEADERS)
    assert response.status_code == 403


def test_resident_cross_society_denial(client: TestClient) -> None:
    # Neeraj attempts to raise complaint for flat in another society
    payload = {
        "flat_id": OTHER_SOCIETY_FLAT_ID,
        "title": "Water tank leakage",
        "description": "Water leaking from overhead supply tank.",
        "category": "WATER_SUPPLY",
    }
    response = client.post("/api/v1/complaints", json=payload, headers=NEERAJ_HEADERS)
    assert response.status_code == 403


def test_validation_rejection_for_short_fields(client: TestClient) -> None:
    # Title < 3 chars, description < 5 chars
    payload = {
        "flat_id": NEERAJ_FLAT_ID,
        "title": "Hi",
        "description": "Fix",
        "category": "PLUMBING",
    }
    response = client.post("/api/v1/complaints", json=payload, headers=NEERAJ_HEADERS)
    assert response.status_code == 422


# =============================================================================
# 2. Deterministic Multilingual Safety Escalation Engine
# =============================================================================


def test_safety_escalation_english_gas_leak(client: TestClient, db_session: Session) -> None:
    payload = {
        "flat_id": NEERAJ_FLAT_ID,
        "title": "Strong gas smell in kitchen",
        "description": "I suspect an LPG gas leak near the cylinder pipe. Please send emergency help.",
        "category": "OTHER",
    }
    response = client.post("/api/v1/complaints", json=payload, headers=NEERAJ_HEADERS)
    assert response.status_code == 201
    data = response.json()

    assert data["safety_escalated"] is True
    assert data["priority"] == "CRITICAL"
    assert "Gas Leak Hazard" in (data["safety_escalation_reason"] or "")

    # SLA for critical: resolution within 2 hours
    res_deadline = datetime.fromisoformat(data["resolution_deadline"].replace("Z", "+00:00"))
    created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
    assert (res_deadline - created_at) <= timedelta(hours=2, minutes=1)

    # Verify safety outbox event
    outbox = (
        db_session.query(OutboxEvent)
        .filter(
            OutboxEvent.aggregate_id == data["id"],
            OutboxEvent.event_type == "complaint.safety_escalated",
        )
        .first()
    )
    assert outbox is not None


def test_safety_escalation_hindi_fire_hazard(client: TestClient) -> None:
    payload = {
        "flat_id": NEERAJ_FLAT_ID,
        "title": "आग लग गई है मीटर रूम में",
        "description": "धुआं निकल रहा है और आग की लपटें दिख रही हैं तुरंत फायर टीम भेजो",
        "category": "ELECTRICAL",
    }
    response = client.post("/api/v1/complaints", json=payload, headers=NEERAJ_HEADERS)
    assert response.status_code == 201
    data = response.json()

    assert data["safety_escalated"] is True
    assert data["priority"] == "CRITICAL"
    assert "Fire or Smoke Hazard" in (data["safety_escalation_reason"] or "")


def test_safety_escalation_marathi_lift_trapped(client: TestClient) -> None:
    payload = {
        "flat_id": NEERAJ_FLAT_ID,
        "title": "लिफ्ट अडकली आहे",
        "description": "लिफ्टमध्ये लहान मुले अडकली आहेत आणि वीज बंद झाली आहे तातडीने मदत हवी",
        "category": "LIFT",
    }
    response = client.post("/api/v1/complaints", json=payload, headers=NEERAJ_HEADERS)
    assert response.status_code == 201
    data = response.json()

    assert data["safety_escalated"] is True
    assert data["priority"] == "CRITICAL"


# =============================================================================
# 3. Workload-Based Helpdesk Assignment
# =============================================================================


def test_workload_based_auto_assignment(client: TestClient, db_session: Session) -> None:
    # Helpdesk user is Rajesh Shinde in seeded database
    payload = {
        "flat_id": NEERAJ_FLAT_ID,
        "title": "Main door lock jammed",
        "description": "The digital lock keypad is not responding and door is stuck.",
        "category": "SECURITY",
    }
    response = client.post("/api/v1/complaints", json=payload, headers=NEERAJ_HEADERS)
    assert response.status_code == 201
    data = response.json()

    assert data["assigned_to"] is not None
    assert data["assignee_name"] == "Rajesh Shinde"
    assert data["status"] == "ASSIGNED"


# =============================================================================
# 4. Public Comments vs. Private Internal Notes
# =============================================================================


def test_public_comments_and_internal_notes_isolation(
    client: TestClient, db_session: Session
) -> None:
    # 1. Neeraj creates complaint
    res = client.post(
        "/api/v1/complaints",
        json={
            "flat_id": NEERAJ_FLAT_ID,
            "title": "Intercom not working",
            "description": "Static noise on intercom handset, unable to speak with gate.",
            "category": "COMMON_AREA",
        },
        headers=NEERAJ_HEADERS,
    )
    complaint_id = res.json()["id"]

    # 2. Resident adds public comment
    comm_res = client.post(
        f"/api/v1/complaints/me/{complaint_id}/comments",
        json={"comment": "I will be home after 6 PM today.", "is_internal": False},
        headers=NEERAJ_HEADERS,
    )
    assert comm_res.status_code == 201
    assert comm_res.json()["is_internal"] is False

    # 3. Helpdesk adds internal note
    note_res = client.post(
        f"/api/v1/complaints/helpdesk/{complaint_id}/comments",
        json={
            "comment": "Vendor technician scheduled for 6:30 PM. Cost approved under AMC.",
            "is_internal": True,
        },
        headers=HELPDESK_HEADERS,
    )
    assert note_res.status_code == 201
    assert note_res.json()["is_internal"] is True

    # 4. Resident inspects complaint -> INTERNAL NOTE MUST BE HIDDEN!
    res_view = client.get(f"/api/v1/complaints/me/{complaint_id}", headers=NEERAJ_HEADERS)
    assert res_view.status_code == 200
    resident_comments = res_view.json()["comments"]
    assert len(resident_comments) == 1
    assert resident_comments[0]["comment"] == "I will be home after 6 PM today."
    assert all(c["is_internal"] is False for c in resident_comments)

    # 5. Helpdesk inspects complaint -> BOTH COMMENTS VISIBLE!
    staff_view = client.get(f"/api/v1/complaints/helpdesk/{complaint_id}", headers=HELPDESK_HEADERS)
    assert staff_view.status_code == 200
    staff_comments = staff_view.json()["comments"]
    assert len(staff_comments) == 2


# =============================================================================
# 5. Lifecycle State Transitions & First Response Tracking
# =============================================================================


def test_complaint_lifecycle_state_machine(client: TestClient) -> None:
    # 1. Create complaint
    create_res = client.post(
        "/api/v1/complaints",
        json={
            "flat_id": NEERAJ_FLAT_ID,
            "title": "Corridor light bulb flickering",
            "description": "Flickering LED tube in front of flat 1203.",
            "category": "ELECTRICAL",
        },
        headers=NEERAJ_HEADERS,
    )
    complaint_id = create_res.json()["id"]

    # 2. Staff moves to IN_PROGRESS
    progress_res = client.patch(
        f"/api/v1/complaints/helpdesk/{complaint_id}/status",
        json={"status": "IN_PROGRESS", "notes": "Electrician dispatched with spare bulb."},
        headers=HELPDESK_HEADERS,
    )
    assert progress_res.status_code == 200
    data = progress_res.json()
    assert data["status"] == "IN_PROGRESS"
    assert data["first_response_at"] is not None

    # 3. Staff resolves complaint
    resolve_res = client.patch(
        f"/api/v1/complaints/helpdesk/{complaint_id}/status",
        json={"status": "RESOLVED", "notes": "Bulb replaced successfully."},
        headers=HELPDESK_HEADERS,
    )
    assert resolve_res.status_code == 200
    assert resolve_res.json()["status"] == "RESOLVED"
    assert resolve_res.json()["resolved_at"] is not None

    # 4. Invalid transition from RESOLVED to SUBMITTED rejected with 400
    invalid_res = client.patch(
        f"/api/v1/complaints/helpdesk/{complaint_id}/status",
        json={"status": "SUBMITTED"},
        headers=HELPDESK_HEADERS,
    )
    assert invalid_res.status_code == 400


# =============================================================================
# 6. Reopening Window & Satisfaction Rating
# =============================================================================


def test_reopen_within_window_and_satisfaction_rating(client: TestClient) -> None:
    # 1. Create and resolve complaint
    c_res = client.post(
        "/api/v1/complaints",
        json={
            "flat_id": NEERAJ_FLAT_ID,
            "title": "Geyser MCB trip",
            "description": "Geyser trips MCB after 5 minutes.",
            "category": "ELECTRICAL",
        },
        headers=NEERAJ_HEADERS,
    )
    complaint_id = c_res.json()["id"]

    client.patch(
        f"/api/v1/complaints/helpdesk/{complaint_id}/status",
        json={"status": "IN_PROGRESS"},
        headers=HELPDESK_HEADERS,
    )
    client.patch(
        f"/api/v1/complaints/helpdesk/{complaint_id}/status",
        json={"status": "IN_PROGRESS"},
        headers=HELPDESK_HEADERS,
    )
    client.patch(
        f"/api/v1/complaints/helpdesk/{complaint_id}/status",
        json={"status": "RESOLVED"},
        headers=HELPDESK_HEADERS,
    )

    # 2. Resident rates complaint
    rate_res = client.post(
        f"/api/v1/complaints/me/{complaint_id}/rating",
        json={"rating": 4, "feedback": "Prompt service, thanks."},
        headers=NEERAJ_HEADERS,
    )
    assert rate_res.status_code == 200
    assert rate_res.json()["rating"] == 4

    # 3. Resident reopens complaint (issue recurred)
    reopen_res = client.post(
        f"/api/v1/complaints/me/{complaint_id}/reopen",
        json={"reason": "Geyser tripped again this morning, please check heating coil."},
        headers=NEERAJ_HEADERS,
    )
    assert reopen_res.status_code == 200
    reopen_data = reopen_res.json()
    assert reopen_data["status"] == "REOPENED"
    assert reopen_data["reopened_count"] == 1
    assert reopen_data["resolved_at"] is None


# =============================================================================
# 7. Attachment Validation
# =============================================================================


def test_attachment_upload_validation(client: TestClient) -> None:
    c_res = client.post(
        "/api/v1/complaints",
        json={
            "flat_id": NEERAJ_FLAT_ID,
            "title": "Wall seepage",
            "description": "Water stains on bedroom wall.",
            "category": "STRUCTURAL",
        },
        headers=NEERAJ_HEADERS,
    )
    complaint_id = c_res.json()["id"]

    # 1. Valid JPEG attachment
    valid_res = client.post(
        f"/api/v1/complaints/me/{complaint_id}/attachments",
        json={
            "file_name": "seepage.jpg",
            "file_size_bytes": 1024 * 500,
            "content_type": "image/jpeg",
        },
        headers=NEERAJ_HEADERS,
    )
    assert valid_res.status_code == 201
    assert "upload_url" in valid_res.json()

    # 2. Disallowed MIME type (application/pdf) -> 422
    invalid_mime = client.post(
        f"/api/v1/complaints/me/{complaint_id}/attachments",
        json={
            "file_name": "invoice.pdf",
            "file_size_bytes": 50000,
            "content_type": "application/pdf",
        },
        headers=NEERAJ_HEADERS,
    )
    assert invalid_mime.status_code == 422

    # 3. Exceeds 5MB size limit -> 422
    oversized = client.post(
        f"/api/v1/complaints/me/{complaint_id}/attachments",
        json={
            "file_name": "video.png",
            "file_size_bytes": 10 * 1024 * 1024,
            "content_type": "image/png",
        },
        headers=NEERAJ_HEADERS,
    )
    assert oversized.status_code == 422


# =============================================================================
# 8. Helpdesk Dashboard Metrics
# =============================================================================


def test_helpdesk_dashboard_metrics(client: TestClient) -> None:
    response = client.get("/api/v1/complaints/helpdesk/dashboard", headers=HELPDESK_HEADERS)
    assert response.status_code == 200
    metrics = response.json()

    assert "total_complaints" in metrics
    assert "unassigned_count" in metrics
    assert "in_progress_count" in metrics
    assert "critical_count" in metrics
    assert "overdue_count" in metrics
    assert "resolution_rate_percentage" in metrics


def test_reopen_expired_window_rejected(client: TestClient, db_session: Session) -> None:
    # 1. Create and resolve complaint
    c_res = client.post(
        "/api/v1/complaints",
        json={
            "flat_id": NEERAJ_FLAT_ID,
            "title": "Kitchen drain blocked",
            "description": "Drain pipe blocked with food waste.",
            "category": "PLUMBING",
        },
        headers=NEERAJ_HEADERS,
    )
    complaint_id = c_res.json()["id"]

    client.patch(
        f"/api/v1/complaints/helpdesk/{complaint_id}/status",
        json={"status": "IN_PROGRESS"},
        headers=HELPDESK_HEADERS,
    )
    client.patch(
        f"/api/v1/complaints/helpdesk/{complaint_id}/status",
        json={"status": "RESOLVED"},
        headers=HELPDESK_HEADERS,
    )

    # 2. Simulate resolved_at 10 days ago
    complaint = db_session.query(Complaint).filter(Complaint.id == uuid.UUID(complaint_id)).first()
    assert complaint is not None
    complaint.resolved_at = datetime.now(UTC) - timedelta(days=10)
    complaint.updated_at = complaint.resolved_at
    db_session.commit()

    # 3. Attempt to reopen -> MUST BE REJECTED (400)
    reopen_res = client.post(
        f"/api/v1/complaints/me/{complaint_id}/reopen",
        json={"reason": "Drain blocked again after 10 days"},
        headers=NEERAJ_HEADERS,
    )
    assert reopen_res.status_code == 400
    assert "expired" in reopen_res.json()["error"]["message"].lower()


def test_rate_unresolved_complaint_rejected(client: TestClient) -> None:
    # Create complaint in SUBMITTED/ASSIGNED status
    c_res = client.post(
        "/api/v1/complaints",
        json={
            "flat_id": NEERAJ_FLAT_ID,
            "title": "Loose switch plate",
            "description": "Living room switch plate is loose.",
            "category": "ELECTRICAL",
        },
        headers=NEERAJ_HEADERS,
    )
    complaint_id = c_res.json()["id"]

    # Attempt to rate -> MUST BE REJECTED (400)
    rate_res = client.post(
        f"/api/v1/complaints/me/{complaint_id}/rating",
        json={"rating": 5, "feedback": "Great"},
        headers=NEERAJ_HEADERS,
    )
    assert rate_res.status_code == 400


def test_helpdesk_list_with_filters_and_search(client: TestClient) -> None:
    # Raise a distinct plumbing complaint
    client.post(
        "/api/v1/complaints",
        json={
            "flat_id": NEERAJ_FLAT_ID,
            "title": "Terrace rainwater downpipe cracked",
            "description": "Heavy leak during rain from downpipe.",
            "category": "PLUMBING",
        },
        headers=NEERAJ_HEADERS,
    )

    # Filter by category PLUMBING
    res = client.get(
        "/api/v1/complaints/helpdesk?category=PLUMBING",
        headers=HELPDESK_HEADERS,
    )
    assert res.status_code == 200
    items = res.json()
    assert len(items) >= 1
    assert all(item["category"] == "PLUMBING" for item in items)

    # Search keyword
    search_res = client.get(
        "/api/v1/complaints/helpdesk?search=downpipe",
        headers=HELPDESK_HEADERS,
    )
    assert search_res.status_code == 200
    search_items = search_res.json()
    assert len(search_items) >= 1
    assert "downpipe" in search_items[0]["title"].lower()


# =============================================================================
# 9. Security & Data Integrity Remediation Tests (Phase 3 Checkpoints)
# =============================================================================


def test_safety_priority_downgrade_rejected(client: TestClient) -> None:
    """Security Invariant: Safety-escalated complaints can NEVER have their priority downgraded."""
    # 1. Create a safety-escalated complaint
    res = client.post(
        "/api/v1/complaints",
        json={
            "flat_id": NEERAJ_FLAT_ID,
            "title": "Gas leak smell in utility area",
            "description": "LPG cylinder hose pipe is leaking gas. Emergency situation.",
            "category": "OTHER",
        },
        headers=NEERAJ_HEADERS,
    )
    assert res.status_code == 201
    complaint_id = res.json()["id"]
    assert res.json()["safety_escalated"] is True
    assert res.json()["priority"] == "CRITICAL"

    # 2. Helpdesk staff attempts to downgrade priority to MEDIUM -> MUST BE REJECTED (400)
    downgrade_res = client.patch(
        f"/api/v1/complaints/helpdesk/{complaint_id}/priority",
        json={"priority": "MEDIUM", "reason": "Looks minor to me"},
        headers=HELPDESK_HEADERS,
    )
    assert downgrade_res.status_code == 400
    assert "cannot downgrade priority" in downgrade_res.json()["error"]["message"].lower()

    # 3. Setting priority to CRITICAL with reason is permitted
    ok_res = client.patch(
        f"/api/v1/complaints/helpdesk/{complaint_id}/priority",
        json={"priority": "CRITICAL", "reason": "Confirmed gas company on site"},
        headers=HELPDESK_HEADERS,
    )
    assert ok_res.status_code == 200


def test_resident_internal_note_override_prevented(client: TestClient) -> None:
    """Security Invariant: Residents can never mark comments as internal notes."""
    res = client.post(
        "/api/v1/complaints",
        json={
            "flat_id": NEERAJ_FLAT_ID,
            "title": "Water heater leaking",
            "description": "Slow drip from the geyser inlet valve.",
            "category": "PLUMBING",
        },
        headers=NEERAJ_HEADERS,
    )
    complaint_id = res.json()["id"]

    # Resident sends is_internal=True
    comm_res = client.post(
        f"/api/v1/complaints/me/{complaint_id}/comments",
        json={"comment": "Resident private thought", "is_internal": True},
        headers=NEERAJ_HEADERS,
    )
    assert comm_res.status_code == 201
    assert comm_res.json()["is_internal"] is False


def test_attachment_upload_lifecycle_verification(client: TestClient) -> None:
    """Attachment Lifecycle: Presigned initiate creates PENDING state; complete endpoint verifies and marks UPLOADED."""
    res = client.post(
        "/api/v1/complaints",
        json={
            "flat_id": NEERAJ_FLAT_ID,
            "title": "Kitchen tile cracked",
            "description": "Floor tile loose and cracked near refrigerator.",
            "category": "STRUCTURAL",
        },
        headers=NEERAJ_HEADERS,
    )
    complaint_id = res.json()["id"]

    # 1. Initiate upload
    init_res = client.post(
        f"/api/v1/complaints/me/{complaint_id}/attachments",
        json={
            "file_name": "cracked_tile.jpg",
            "file_size_bytes": 204800,
            "content_type": "image/jpeg",
        },
        headers=NEERAJ_HEADERS,
    )
    assert init_res.status_code == 201
    init_data = init_res.json()
    attachment_id = init_data["attachment_id"]
    assert "upload_url" in init_data

    # 2. Before completion, attachment is PENDING and hidden from complaint view
    view_res = client.get(f"/api/v1/complaints/me/{complaint_id}", headers=NEERAJ_HEADERS)
    assert view_res.status_code == 200
    assert len(view_res.json()["attachments"]) == 0

    # 3. Complete attachment upload
    complete_res = client.post(
        f"/api/v1/complaints/me/{complaint_id}/attachments/{attachment_id}/complete",
        headers=NEERAJ_HEADERS,
    )
    assert complete_res.status_code == 200
    complete_data = complete_res.json()
    assert complete_data["id"] == attachment_id
    assert complete_data["status"] == "UPLOADED"
    assert "download_url" in complete_data

    # 4. Now attachment is visible in complaint detail view
    view_after = client.get(f"/api/v1/complaints/me/{complaint_id}", headers=NEERAJ_HEADERS)
    assert len(view_after.json()["attachments"]) == 1
    assert view_after.json()["attachments"][0]["status"] == "UPLOADED"


def test_gemini_ai_classifier_with_mock_response() -> None:
    """AI Classifier: Tests Gemini provider parsing, confidence, and Pydantic validation."""
    from unittest.mock import MagicMock, patch

    from app.domains.complaints.ai_classifier import GeminiAIClassifierProvider
    from app.domains.complaints.models import ComplaintCategory, ComplaintPriority

    mock_gemini_json = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": (
                                '{"suggested_category": "ELECTRICAL", "suggested_priority": "HIGH", '
                                '"confidence_score": 0.94, "summary": "Main MCB tripping repeatedly", '
                                '"urgency_reason": "Power outage in flat", '
                                '"reasoning": "Repeated tripping indicates electrical overload or short circuit.", '
                                '"requires_human_review": false}'
                            )
                        }
                    ]
                }
            }
        ]
    }

    provider = GeminiAIClassifierProvider(api_key="mock-gemini-key")
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_gemini_json
        mock_post.return_value = mock_resp

        result = provider.classify(
            title="MCB trip",
            description="The main MCB switch trips whenever AC is turned on.",
            selected_category=ComplaintCategory.OTHER,
        )

        assert result.provider == "gemini"
        assert result.suggested_category == ComplaintCategory.ELECTRICAL
        assert result.suggested_priority == ComplaintPriority.HIGH
        assert result.confidence_score == 0.94
        assert result.requires_human_review is False
        assert "electrical overload" in result.reasoning.lower()


def test_gemini_ai_classifier_fallback_on_error() -> None:
    """AI Classifier: Tests resilient fallback to deterministic classifier on network error."""
    from unittest.mock import patch

    import requests

    from app.domains.complaints.ai_classifier import GeminiAIClassifierProvider
    from app.domains.complaints.models import ComplaintCategory, ComplaintPriority

    provider = GeminiAIClassifierProvider(api_key="mock-gemini-key", max_retries=0)
    with patch("requests.post", side_effect=requests.RequestException("Connection timeout")):
        result = provider.classify(
            title="Tap leaking in bathroom",
            description="Dripping tap needs washer replacement.",
            selected_category=ComplaintCategory.PLUMBING,
        )

        # Resilient fallback
        assert result.provider == "fallback-deterministic"
        assert result.suggested_category == ComplaintCategory.PLUMBING
        assert result.suggested_priority in (ComplaintPriority.LOW, ComplaintPriority.MEDIUM)
        assert result.requires_human_review is True


def test_outbox_queue_routing_discrimination() -> None:
    """Outbox Publisher: Validates strict routing between AI queue and notification queue."""
    from app.messaging.outbox_publisher import resolve_queue_for_event_type
    from app.messaging.publisher import QUEUE_COMPLAINT_AI_JOBS, QUEUE_NOTIFICATION_JOBS

    # AI events must go to AI jobs queue
    assert resolve_queue_for_event_type("complaint.classify") == QUEUE_COMPLAINT_AI_JOBS
    assert resolve_queue_for_event_type("complaint.assign_priority") == QUEUE_COMPLAINT_AI_JOBS

    # Operational events must route to notifications queue
    assert resolve_queue_for_event_type("complaint.created") == QUEUE_NOTIFICATION_JOBS
    assert resolve_queue_for_event_type("complaint.safety_escalated") == QUEUE_NOTIFICATION_JOBS
    assert resolve_queue_for_event_type("complaint.status_changed") == QUEUE_NOTIFICATION_JOBS
    assert resolve_queue_for_event_type("complaint.assigned") == QUEUE_NOTIFICATION_JOBS
    assert resolve_queue_for_event_type("complaint.resolved") == QUEUE_NOTIFICATION_JOBS
    assert resolve_queue_for_event_type("complaint.reopened") == QUEUE_NOTIFICATION_JOBS


def test_complaint_worker_async_ai_processing(db_session: Session) -> None:
    """Worker: Tests asynchronous AI job worker updating complaint model and activity log."""
    from app.domains.complaints.models import Complaint, ComplaintCategory, ComplaintPriority
    from app.domains.identity.models import Flat, User
    from app.messaging.envelope import EventEnvelope, EventMetadata
    from app.workers.complaint_worker import complaint_handler

    flat = db_session.query(Flat).first()
    user = db_session.query(User).first()
    assert flat is not None and user is not None

    complaint = Complaint(
        society_id=flat.society_id,
        flat_id=flat.id,
        created_by=user.id,
        complaint_number="CMP-TEST-9999",
        category=ComplaintCategory.OTHER,
        title="Elevator jerky and stopping between floors",
        description="Lift #2 in Tower A jerked violently and display was blank.",
        priority=ComplaintPriority.MEDIUM,
    )
    db_session.add(complaint)
    db_session.commit()
    db_session.refresh(complaint)

    envelope = EventEnvelope(
        event_id=uuid.uuid4(),
        event_type="complaint.classify",
        aggregate_type="complaint",
        aggregate_id=str(complaint.id),
        timestamp=datetime.now(UTC).isoformat(),
        metadata=EventMetadata(correlation_id=str(uuid.uuid4())),
        payload={"complaint_id": str(complaint.id)},
    )

    # Process job via worker
    complaint_handler.process(envelope, db_session)
    db_session.refresh(complaint)

    # Verify AI categorization populated
    assert complaint.ai_status.value in ("COMPLETED", "FALLBACK")
    assert complaint.ai_suggested_category == ComplaintCategory.LIFT
    assert complaint.ai_model is not None
    assert complaint.ai_processed_at is not None
    assert len(complaint.activities) >= 1
    assert any(a.activity_type == "AI_TRIAGE_COMPLETED" for a in complaint.activities)


def test_resident_create_complaint_async_ai_pending(
    client: TestClient, db_session: Session
) -> None:
    """Creation: Must return immediately with ai_status=PENDING and empty advisory fields."""
    payload = {
        "flat_id": NEERAJ_FLAT_ID,
        "title": "Water dripping from AC indoor unit",
        "description": "AC unit in master bedroom has condensate dripping on floor.",
        "category": "ELECTRICAL",
    }
    response = client.post("/api/v1/complaints", json=payload, headers=NEERAJ_HEADERS)
    assert response.status_code == 201
    data = response.json()

    assert data["ai_status"] == "PENDING"
    assert data["ai_suggested_category"] is None
    assert data["ai_suggested_priority"] is None
    assert data["ai_confidence_score"] is None
    assert data["ai_summary"] is None
    assert data["ai_urgency_reason"] is None
    assert data["ai_reasoning"] is None
    assert data["ai_provider"] is None
    assert data["ai_model"] is None
    assert data["ai_processed_at"] is None

    # Verify classification outbox event was queued to QUEUE_COMPLAINT_AI_JOBS
    outbox = (
        db_session.query(OutboxEvent)
        .filter(
            OutboxEvent.aggregate_id == data["id"],
            OutboxEvent.event_type == "complaint.classify",
        )
        .first()
    )
    from app.messaging.outbox_publisher import resolve_queue_for_event_type
    from app.messaging.publisher import QUEUE_COMPLAINT_AI_JOBS

    assert outbox is not None
    assert resolve_queue_for_event_type(outbox.event_type) == QUEUE_COMPLAINT_AI_JOBS


def test_complaint_worker_idempotency_duplicate_events(db_session: Session) -> None:
    """Worker Idempotency: Duplicate events for already processed complaints must be skipped."""
    from unittest.mock import MagicMock

    from app.domains.complaints.ai_classifier import AIClassifierProvider, AITriageResult
    from app.domains.complaints.models import (
        Complaint,
        ComplaintAIStatus,
        ComplaintCategory,
        ComplaintPriority,
    )
    from app.domains.identity.models import Flat, User
    from app.messaging.envelope import EventEnvelope, EventMetadata
    from app.workers.complaint_worker import ComplaintAIHandler

    flat = db_session.query(Flat).first()
    user = db_session.query(User).first()
    assert flat and user

    complaint = Complaint(
        society_id=flat.society_id,
        flat_id=flat.id,
        created_by=user.id,
        complaint_number="CMP-IDEMPOTENT-001",
        category=ComplaintCategory.PLUMBING,
        title="Bathroom tap leaking",
        description="Tap leaking constantly",
        priority=ComplaintPriority.MEDIUM,
        ai_status=ComplaintAIStatus.PENDING,
    )
    db_session.add(complaint)
    db_session.commit()
    db_session.refresh(complaint)

    mock_provider = MagicMock(spec=AIClassifierProvider)
    mock_provider.classify.return_value = AITriageResult(
        suggested_category=ComplaintCategory.PLUMBING,
        suggested_priority=ComplaintPriority.LOW,
        confidence_score=0.9,
        summary="Tap leaking",
        urgency_reason="Minor leak",
        reasoning="Matched leak keyword",
        provider="mock-ai",
        model="mock-model-v1",
    )

    handler = ComplaintAIHandler(ai_provider=mock_provider)
    envelope = EventEnvelope(
        event_id=uuid.uuid4(),
        event_type="complaint.classify",
        aggregate_type="complaint",
        aggregate_id=str(complaint.id),
        timestamp=datetime.now(UTC).isoformat(),
        metadata=EventMetadata(correlation_id=str(uuid.uuid4())),
        payload={"complaint_id": str(complaint.id)},
    )

    # First execution -> should classify
    handler.process(envelope, db_session)
    assert mock_provider.classify.call_count == 1
    db_session.refresh(complaint)
    assert complaint.ai_status == ComplaintAIStatus.COMPLETED

    # Second duplicate execution -> must skip without calling provider again
    handler.process(envelope, db_session)
    assert mock_provider.classify.call_count == 1


def test_ai_disabled_setting_enforcement(monkeypatch) -> None:
    """Configuration: When AI_ENABLED is False, provider falls back deterministically."""
    from app.core.config import settings
    from app.domains.complaints.ai_classifier import (
        DeterministicAIClassifierProvider,
        GeminiAIClassifierProvider,
        get_ai_classifier_provider,
    )
    from app.domains.complaints.models import ComplaintCategory

    # 1. Test get_ai_classifier_provider with AI_ENABLED=False
    monkeypatch.setattr(settings, "AI_ENABLED", False)
    monkeypatch.setattr(settings, "AI_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "some-live-key")

    provider = get_ai_classifier_provider()
    assert isinstance(provider, DeterministicAIClassifierProvider)

    # 2. Test GeminiAIClassifierProvider.classify when AI_ENABLED=False
    gemini_provider = GeminiAIClassifierProvider(api_key="mock-key")
    res = gemini_provider.classify(
        title="Lift stuck on floor 3",
        description="Lift trapped between 3 and 4",
        selected_category=ComplaintCategory.LIFT,
    )
    assert res.provider == "deterministic"
    assert res.suggested_category == ComplaintCategory.LIFT


def test_attachment_upload_complete_success(client: TestClient, db_session: Session) -> None:
    """Attachments: Successful upload completion updates status to UPLOADED."""
    from app.domains.complaints.models import AttachmentStatus, ComplaintAttachment

    c_res = client.post(
        "/api/v1/complaints",
        json={
            "flat_id": NEERAJ_FLAT_ID,
            "title": "Kitchen tile broken",
            "description": "Floor tile cracked.",
            "category": "STRUCTURAL",
        },
        headers=NEERAJ_HEADERS,
    )
    complaint_id = c_res.json()["id"]

    init_res = client.post(
        f"/api/v1/complaints/me/{complaint_id}/attachments",
        json={
            "file_name": "tile.jpg",
            "file_size_bytes": 2048,
            "content_type": "image/jpeg",
        },
        headers=NEERAJ_HEADERS,
    )
    assert init_res.status_code == 201
    attachment_id = init_res.json()["attachment_id"]

    comp_res = client.post(
        f"/api/v1/complaints/me/{complaint_id}/attachments/{attachment_id}/complete",
        headers=NEERAJ_HEADERS,
    )
    assert comp_res.status_code == 200
    comp_data = comp_res.json()
    assert comp_data["status"] == "UPLOADED"
    assert "download_url" in comp_data

    att = (
        db_session.query(ComplaintAttachment)
        .filter(ComplaintAttachment.id == uuid.UUID(attachment_id))
        .first()
    )
    assert att is not None
    assert att.status == AttachmentStatus.UPLOADED


def test_attachment_metadata_verification_rejection(
    client: TestClient, db_session: Session
) -> None:
    """Attachments: Metadata verification failure marks attachment FAILED and returns 400."""
    from app.domains.complaints.models import AttachmentStatus, ComplaintAttachment
    from app.domains.complaints.storage import _default_mock_storage

    # 1. Create complaint
    c_res = client.post(
        "/api/v1/complaints",
        json={
            "flat_id": NEERAJ_FLAT_ID,
            "title": "Balcony leak",
            "description": "Water dripping from upstairs balcony.",
            "category": "PLUMBING",
        },
        headers=NEERAJ_HEADERS,
    )
    complaint_id = c_res.json()["id"]

    # 2. Initiate attachment
    init_res = client.post(
        f"/api/v1/complaints/me/{complaint_id}/attachments",
        json={
            "file_name": "balcony.png",
            "file_size_bytes": 1024 * 50,
            "content_type": "image/png",
        },
        headers=NEERAJ_HEADERS,
    )
    assert init_res.status_code == 201
    init_data = init_res.json()
    attachment_id = init_data["attachment_id"]
    storage_key = init_data["storage_key"]

    # 3. Simulate storage metadata corruption (size mismatch)
    _default_mock_storage._stored_metadata[storage_key]["size"] = 999999

    # 4. Attempt complete attachment upload -> must fail verification
    comp_res = client.post(
        f"/api/v1/complaints/me/{complaint_id}/attachments/{attachment_id}/complete",
        headers=NEERAJ_HEADERS,
    )
    assert comp_res.status_code == 400
    assert "verification failed" in comp_res.json()["error"]["message"].lower()

    # Verify attachment marked FAILED in DB
    att = (
        db_session.query(ComplaintAttachment)
        .filter(ComplaintAttachment.id == uuid.UUID(attachment_id))
        .first()
    )
    assert att is not None
    assert att.status == AttachmentStatus.FAILED


def test_resident_pii_redaction() -> None:
    """Privacy: Verifies resident phone, email, flat number, and names are redacted."""
    from app.domains.complaints.ai_classifier import minimize_resident_data

    title = "Leak in flat 402, call 9876543210 urgently"
    desc = "My name is Ramesh Kumar, email ramesh.k@example.com. Password secret123 is not working."

    redacted_title, redacted_desc = minimize_resident_data(title, desc)

    assert "flat 402" not in redacted_title.lower()
    assert "[UNIT_REDACTED]" in redacted_title
    assert "9876543210" not in redacted_title
    assert "[PHONE_REDACTED]" in redacted_title

    assert "ramesh.k@example.com" not in redacted_desc
    assert "[EMAIL_REDACTED]" in redacted_desc
    assert "Ramesh Kumar" not in redacted_desc
    assert "[NAME_REDACTED]" in redacted_desc
    assert "secret123" not in redacted_desc
    assert "[REDACTED]" in redacted_desc


def test_complaint_worker_retryable_network_failure(db_session: Session) -> None:
    """Worker Reliability: Transient network failure re-raises error so message is NOT acknowledged."""
    from unittest.mock import MagicMock

    import pytest

    from app.domains.complaints.ai_classifier import AIClassifierProvider, RetryableWorkerError
    from app.domains.complaints.models import (
        Complaint,
        ComplaintActivity,
        ComplaintAIStatus,
        ComplaintCategory,
        ComplaintPriority,
    )
    from app.domains.identity.models import Flat, User
    from app.messaging.envelope import EventEnvelope, EventMetadata
    from app.workers.complaint_worker import ComplaintAIHandler

    flat = db_session.query(Flat).first()
    user = db_session.query(User).first()
    assert flat and user

    complaint = Complaint(
        society_id=flat.society_id,
        flat_id=flat.id,
        created_by=user.id,
        complaint_number="CMP-RETRY-001",
        category=ComplaintCategory.PLUMBING,
        title="Pipe burst",
        description="Main pipe burst",
        priority=ComplaintPriority.HIGH,
        ai_status=ComplaintAIStatus.PENDING,
    )
    db_session.add(complaint)
    db_session.commit()
    db_session.refresh(complaint)

    mock_provider = MagicMock(spec=AIClassifierProvider)
    mock_provider.classify.side_effect = RetryableWorkerError("Gemini API connection timeout")

    handler = ComplaintAIHandler(ai_provider=mock_provider)
    envelope = EventEnvelope(
        event_id=uuid.uuid4(),
        event_type="complaint.classify",
        aggregate_type="complaint",
        aggregate_id=str(complaint.id),
        timestamp=datetime.now(UTC).isoformat(),
        metadata=EventMetadata(correlation_id=str(uuid.uuid4())),
        payload={"complaint_id": str(complaint.id)},
    )

    with pytest.raises(RetryableWorkerError) as exc_info:
        handler.process(envelope, db_session)

    assert "connection timeout" in str(exc_info.value).lower()
    db_session.refresh(complaint)
    assert complaint.ai_status == ComplaintAIStatus.FAILED

    # Verify failure activity was recorded
    fail_act = (
        db_session.query(ComplaintActivity)
        .filter(
            ComplaintActivity.complaint_id == complaint.id,
            ComplaintActivity.activity_type == "AI_TRIAGE_FAILED",
        )
        .first()
    )
    assert fail_act is not None
    assert fail_act.activity_metadata["retryable"] is True


def test_complaint_worker_permanent_invalid_model_response(db_session: Session) -> None:
    """Worker Reliability: Permanent model parse failure marks FAILED without re-raising."""
    from unittest.mock import MagicMock

    from app.domains.complaints.ai_classifier import AIClassifierProvider, PermanentWorkerError
    from app.domains.complaints.models import (
        Complaint,
        ComplaintActivity,
        ComplaintAIStatus,
        ComplaintCategory,
        ComplaintPriority,
    )
    from app.domains.identity.models import Flat, User
    from app.messaging.envelope import EventEnvelope, EventMetadata
    from app.workers.complaint_worker import ComplaintAIHandler

    flat = db_session.query(Flat).first()
    user = db_session.query(User).first()
    assert flat and user

    complaint = Complaint(
        society_id=flat.society_id,
        flat_id=flat.id,
        created_by=user.id,
        complaint_number="CMP-PERM-001",
        category=ComplaintCategory.ELECTRICAL,
        title="Sparks from switchboard",
        description="Switchboard smoking",
        priority=ComplaintPriority.CRITICAL,
        ai_status=ComplaintAIStatus.PENDING,
    )
    db_session.add(complaint)
    db_session.commit()
    db_session.refresh(complaint)

    mock_provider = MagicMock(spec=AIClassifierProvider)
    mock_provider.classify.side_effect = PermanentWorkerError("Unparseable model JSON candidate")

    handler = ComplaintAIHandler(ai_provider=mock_provider)
    envelope = EventEnvelope(
        event_id=uuid.uuid4(),
        event_type="complaint.classify",
        aggregate_type="complaint",
        aggregate_id=str(complaint.id),
        timestamp=datetime.now(UTC).isoformat(),
        metadata=EventMetadata(correlation_id=str(uuid.uuid4())),
        payload={"complaint_id": str(complaint.id)},
    )

    # Permanent failure must not raise; returns cleanly so queue acknowledges message
    handler.process(envelope, db_session)

    db_session.refresh(complaint)
    assert complaint.ai_status == ComplaintAIStatus.FAILED
    assert "Unparseable model JSON" in (complaint.ai_reasoning or "")

    fail_act = (
        db_session.query(ComplaintActivity)
        .filter(
            ComplaintActivity.complaint_id == complaint.id,
            ComplaintActivity.activity_type == "AI_TRIAGE_FAILED",
        )
        .first()
    )
    assert fail_act is not None
    assert fail_act.activity_metadata["retryable"] is False


def test_failed_worker_message_not_acknowledged(db_session: Session) -> None:
    """Message Dispatcher: When handler re-raises retryable error, dispatch_envelope returns False."""
    from unittest.mock import MagicMock

    from app.domains.complaints.ai_classifier import AIClassifierProvider, RetryableWorkerError
    from app.domains.complaints.models import (
        Complaint,
        ComplaintAIStatus,
        ComplaintCategory,
        ComplaintPriority,
    )
    from app.domains.identity.models import Flat, User
    from app.messaging.consumer import dispatcher
    from app.messaging.envelope import EventEnvelope, EventMetadata
    from app.workers.complaint_worker import complaint_handler

    flat = db_session.query(Flat).first()
    user = db_session.query(User).first()
    assert flat and user

    complaint = Complaint(
        society_id=flat.society_id,
        flat_id=flat.id,
        created_by=user.id,
        complaint_number="CMP-NACK-001",
        category=ComplaintCategory.HOUSEKEEPING,
        title="Garbage in corridor",
        description="Trash bags left in corridor",
        priority=ComplaintPriority.LOW,
        ai_status=ComplaintAIStatus.PENDING,
    )
    db_session.add(complaint)
    db_session.commit()
    db_session.refresh(complaint)

    # Configure registered handler's provider to fail retryably
    mock_provider = MagicMock(spec=AIClassifierProvider)
    mock_provider.classify.side_effect = RetryableWorkerError("503 Service Unavailable")
    complaint_handler._ai_provider = mock_provider

    envelope = EventEnvelope(
        event_id=uuid.uuid4(),
        event_type="complaint.classify",
        aggregate_type="complaint",
        aggregate_id=str(complaint.id),
        timestamp=datetime.now(UTC).isoformat(),
        metadata=EventMetadata(correlation_id=str(uuid.uuid4())),
        payload={"complaint_id": str(complaint.id)},
    )

    success = dispatcher.dispatch_envelope(envelope, db_session)
    assert success is False  # Must be False so SQS does NOT delete the message!


def test_complaint_worker_successful_retry_recovery(db_session: Session) -> None:
    """Worker Reliability: A subsequent retry on a FAILED complaint successfully transitions to COMPLETED."""
    from unittest.mock import MagicMock

    from app.domains.complaints.ai_classifier import AIClassifierProvider, AITriageResult
    from app.domains.complaints.models import (
        Complaint,
        ComplaintAIStatus,
        ComplaintCategory,
        ComplaintPriority,
    )
    from app.domains.identity.models import Flat, User
    from app.messaging.envelope import EventEnvelope, EventMetadata
    from app.workers.complaint_worker import ComplaintAIHandler

    flat = db_session.query(Flat).first()
    user = db_session.query(User).first()
    assert flat and user

    complaint = Complaint(
        society_id=flat.society_id,
        flat_id=flat.id,
        created_by=user.id,
        complaint_number="CMP-RECOVER-001",
        category=ComplaintCategory.LIFT,
        title="Lift jerky in tower A",
        description="Lift stopped abruptly between floors",
        priority=ComplaintPriority.HIGH,
        ai_status=ComplaintAIStatus.FAILED,  # Initially in failed state from earlier timeout
        ai_reasoning="Earlier timeout attempt failed",
    )
    db_session.add(complaint)
    db_session.commit()
    db_session.refresh(complaint)

    mock_provider = MagicMock(spec=AIClassifierProvider)
    mock_provider.classify.return_value = AITriageResult(
        suggested_category=ComplaintCategory.LIFT,
        suggested_priority=ComplaintPriority.HIGH,
        confidence_score=0.96,
        summary="Lift jerking between floors",
        urgency_reason="Elevator mechanical issue",
        reasoning="Matched lift keywords",
        provider="gemini",
        model="gemini-2.5-flash",
    )

    handler = ComplaintAIHandler(ai_provider=mock_provider)
    envelope = EventEnvelope(
        event_id=uuid.uuid4(),
        event_type="complaint.classify",
        aggregate_type="complaint",
        aggregate_id=str(complaint.id),
        timestamp=datetime.now(UTC).isoformat(),
        metadata=EventMetadata(correlation_id=str(uuid.uuid4())),
        payload={"complaint_id": str(complaint.id)},
    )

    handler.process(envelope, db_session)
    db_session.refresh(complaint)

    assert complaint.ai_status == ComplaintAIStatus.COMPLETED
    assert complaint.ai_suggested_category == ComplaintCategory.LIFT
    assert complaint.ai_provider == "gemini"


def test_complaint_worker_concurrent_active_lease_skips(db_session: Session) -> None:
    """Worker Concurrency: Active PROCESSING lease prevents duplicate concurrent workers from running."""
    from unittest.mock import MagicMock

    from app.domains.complaints.ai_classifier import AIClassifierProvider
    from app.domains.complaints.models import (
        Complaint,
        ComplaintAIStatus,
        ComplaintCategory,
        ComplaintPriority,
    )
    from app.domains.identity.models import Flat, User
    from app.messaging.envelope import EventEnvelope, EventMetadata
    from app.workers.complaint_worker import ComplaintAIHandler

    flat = db_session.query(Flat).first()
    user = db_session.query(User).first()
    assert flat and user

    complaint = Complaint(
        society_id=flat.society_id,
        flat_id=flat.id,
        created_by=user.id,
        complaint_number="CMP-LEASE-001",
        category=ComplaintCategory.PLUMBING,
        title="Dripping shower",
        description="Shower head dripping",
        priority=ComplaintPriority.LOW,
        ai_status=ComplaintAIStatus.PROCESSING,
        ai_processed_at=datetime.now(UTC) - timedelta(seconds=25),  # 25 seconds ago (active lease)
    )
    db_session.add(complaint)
    db_session.commit()
    db_session.refresh(complaint)

    mock_provider = MagicMock(spec=AIClassifierProvider)
    handler = ComplaintAIHandler(ai_provider=mock_provider)

    envelope = EventEnvelope(
        event_id=uuid.uuid4(),
        event_type="complaint.classify",
        aggregate_type="complaint",
        aggregate_id=str(complaint.id),
        timestamp=datetime.now(UTC).isoformat(),
        metadata=EventMetadata(correlation_id=str(uuid.uuid4())),
        payload={"complaint_id": str(complaint.id)},
    )

    handler.process(envelope, db_session)
    # Must not invoke provider because active lease exists
    assert mock_provider.classify.call_count == 0


def test_complaint_worker_expired_lease_reclaims(db_session: Session) -> None:
    """Worker Reliability: Expired PROCESSING lease (>300s from crashed worker) is reclaimed and processed."""
    from unittest.mock import MagicMock

    from app.domains.complaints.ai_classifier import AIClassifierProvider, AITriageResult
    from app.domains.complaints.models import (
        Complaint,
        ComplaintAIStatus,
        ComplaintCategory,
        ComplaintPriority,
    )
    from app.domains.identity.models import Flat, User
    from app.messaging.envelope import EventEnvelope, EventMetadata
    from app.workers.complaint_worker import ComplaintAIHandler

    flat = db_session.query(Flat).first()
    user = db_session.query(User).first()
    assert flat and user

    complaint = Complaint(
        society_id=flat.society_id,
        flat_id=flat.id,
        created_by=user.id,
        complaint_number="CMP-EXPIRED-001",
        category=ComplaintCategory.COMMON_AREA,
        title="Clubhouse door broken",
        description="Handle fell off clubhouse entrance door",
        priority=ComplaintPriority.MEDIUM,
        ai_status=ComplaintAIStatus.PROCESSING,
        ai_processed_at=datetime.now(UTC) - timedelta(seconds=350),  # > 300s (expired lease)
    )
    db_session.add(complaint)
    db_session.commit()
    db_session.refresh(complaint)

    mock_provider = MagicMock(spec=AIClassifierProvider)
    mock_provider.classify.return_value = AITriageResult(
        suggested_category=ComplaintCategory.COMMON_AREA,
        suggested_priority=ComplaintPriority.MEDIUM,
        confidence_score=0.91,
        summary="Clubhouse door handle broken",
        urgency_reason="Amenity maintenance",
        reasoning="Matched clubhouse door keyword",
        provider="mock-ai",
        model="mock-v1",
    )

    handler = ComplaintAIHandler(ai_provider=mock_provider)
    envelope = EventEnvelope(
        event_id=uuid.uuid4(),
        event_type="complaint.classify",
        aggregate_type="complaint",
        aggregate_id=str(complaint.id),
        timestamp=datetime.now(UTC).isoformat(),
        metadata=EventMetadata(correlation_id=str(uuid.uuid4())),
        payload={"complaint_id": str(complaint.id)},
    )

    handler.process(envelope, db_session)
    assert mock_provider.classify.call_count == 1

    db_session.refresh(complaint)
    assert complaint.ai_status == ComplaintAIStatus.COMPLETED


def test_safety_priority_immutable_under_ai_worker(db_session: Session) -> None:
    """Safety Invariant: AI suggestions must NEVER downgrade or overwrite authoritative safety priority."""
    from unittest.mock import MagicMock

    from app.domains.complaints.ai_classifier import AIClassifierProvider, AITriageResult
    from app.domains.complaints.models import (
        Complaint,
        ComplaintAIStatus,
        ComplaintCategory,
        ComplaintPriority,
    )
    from app.domains.identity.models import Flat, User
    from app.messaging.envelope import EventEnvelope, EventMetadata
    from app.workers.complaint_worker import ComplaintAIHandler

    flat = db_session.query(Flat).first()
    user = db_session.query(User).first()
    assert flat and user

    complaint = Complaint(
        society_id=flat.society_id,
        flat_id=flat.id,
        created_by=user.id,
        complaint_number="CMP-SAFETY-IMMUTABLE",
        category=ComplaintCategory.OTHER,
        title="Gas cylinder leaking violently",
        description="LPG smell in kitchen, hissing noise from regulator",
        priority=ComplaintPriority.CRITICAL,
        safety_escalated=True,
        safety_escalation_reason="Gas leak detected",
        ai_status=ComplaintAIStatus.PENDING,
    )
    db_session.add(complaint)
    db_session.commit()
    db_session.refresh(complaint)

    # Mock an AI provider that erroneously suggests LOW priority
    mock_provider = MagicMock(spec=AIClassifierProvider)
    mock_provider.classify.return_value = AITriageResult(
        suggested_category=ComplaintCategory.PLUMBING,
        suggested_priority=ComplaintPriority.LOW,
        confidence_score=0.88,
        summary="Gas cylinder regulator",
        urgency_reason="Minor plumbing check",
        reasoning="Test reasoning",
        provider="gemini",
        model="gemini-2.5-flash",
    )

    handler = ComplaintAIHandler(ai_provider=mock_provider)
    envelope = EventEnvelope(
        event_id=uuid.uuid4(),
        event_type="complaint.classify",
        aggregate_type="complaint",
        aggregate_id=str(complaint.id),
        timestamp=datetime.now(UTC).isoformat(),
        metadata=EventMetadata(correlation_id=str(uuid.uuid4())),
        payload={"complaint_id": str(complaint.id)},
    )

    handler.process(envelope, db_session)
    db_session.refresh(complaint)

    # Authoritative priority MUST remain CRITICAL
    assert complaint.priority == ComplaintPriority.CRITICAL
    assert complaint.safety_escalated is True

    # AI recommendation is isolated to advisory columns
    assert complaint.ai_suggested_priority == ComplaintPriority.LOW
    assert complaint.ai_suggested_category == ComplaintCategory.PLUMBING


def test_pii_minimization_multilingual() -> None:
    """Privacy: Verifies resident minimization across English, Hindi, and Marathi."""
    from app.domains.complaints.ai_classifier import minimize_resident_data

    # 1. English with titles, unit, PIN code, phone
    en_title = "Water leakage in flat T07-1203, PIN 411028"
    en_desc = "Resident: Mr. Rajesh Shinde, call me on +91 98765 43210. Password mypass is locked."
    r_en_t, r_en_d = minimize_resident_data(en_title, en_desc)
    assert "[UNIT_REDACTED]" in r_en_t
    assert "[PINCODE_REDACTED]" in r_en_t
    assert "411028" not in r_en_t
    assert "[NAME_REDACTED]" in r_en_d
    assert "Rajesh Shinde" not in r_en_d
    assert "[PHONE_REDACTED]" in r_en_d
    assert "98765" not in r_en_d
    assert "[REDACTED]" in r_en_d
    assert "mypass" not in r_en_d

    # 2. Hindi with self-intro, Devnagari numerals, unit
    hi_title = "मकान नं 204 में लीकेज"
    hi_desc = "मेरा नाम अमित कुमार है। कृपया मोबाइल नंबर ९८७६५४३२१० पर कॉल करें।"
    r_hi_t, r_hi_d = minimize_resident_data(hi_title, hi_desc)
    assert "[UNIT_REDACTED]" in r_hi_t
    assert "204" not in r_hi_t
    assert "[NAME_REDACTED]" in r_hi_d
    assert "अमित कुमार" not in r_hi_d
    assert "[PHONE_REDACTED]" in r_hi_d
    assert "९८७६५४३२१०" not in r_hi_d

    # 3. Marathi with self-intro, unit, phone
    mr_title = "फ्लॅट क्र ५०२ मध्ये शॉर्ट सर्किट"
    mr_desc = "माझे नाव अमोल पाटील आहे. संपर्क ९८७६५४३२१०."
    r_mr_t, r_mr_d = minimize_resident_data(mr_title, mr_desc)
    assert "[UNIT_REDACTED]" in r_mr_t
    assert "५०२" not in r_mr_t
    assert "[NAME_REDACTED]" in r_mr_d
    assert "अमोल पाटील" not in r_mr_d
    assert "[PHONE_REDACTED]" in r_mr_d
    assert "९८७६५४३२१०" not in r_mr_d


def test_s3_storage_metadata_verification_edge_cases() -> None:
    """Attachments: S3 metadata verification rejects empty, oversized, size-mismatched, and missing-content-type files."""
    from unittest.mock import MagicMock

    from app.domains.complaints.storage import S3StorageProvider

    provider = S3StorageProvider(bucket_name="test-bucket")
    mock_s3 = MagicMock()
    provider.s3_client = mock_s3

    # Case 1: Empty file (0 bytes) -> must reject
    mock_s3.head_object.return_value = {"ContentLength": 0, "ContentType": "image/jpeg"}
    valid, err = provider.verify_object_metadata("key1", 0, "image/jpeg")
    assert valid is False
    assert "empty" in (err or "").lower()

    # Case 2: Oversized file (> 5MB) -> must reject
    mock_s3.head_object.return_value = {
        "ContentLength": 6 * 1024 * 1024,
        "ContentType": "image/jpeg",
    }
    valid, err = provider.verify_object_metadata("key2", 6 * 1024 * 1024, "image/jpeg")
    assert valid is False
    assert "exceeds maximum" in (err or "").lower()

    # Case 3: Size mismatch (declared 2000, actual 2050) -> must reject with zero tolerance
    mock_s3.head_object.return_value = {"ContentLength": 2050, "ContentType": "image/png"}
    valid, err = provider.verify_object_metadata("key3", 2000, "image/png")
    assert valid is False
    assert "size mismatch" in (err or "").lower()

    # Case 4: Missing ContentType metadata -> must reject
    mock_s3.head_object.return_value = {"ContentLength": 2000, "ContentType": ""}
    valid, err = provider.verify_object_metadata("key4", 2000, "image/png")
    assert valid is False
    assert "missing contenttype" in (err or "").lower()

    # Case 5: ContentType mismatch -> must reject
    mock_s3.head_object.return_value = {"ContentLength": 2000, "ContentType": "image/webp"}
    valid, err = provider.verify_object_metadata("key5", 2000, "image/png")
    assert valid is False
    assert "content-type mismatch" in (err or "").lower()

    # Case 6: Valid object -> must pass
    mock_s3.head_object.return_value = {"ContentLength": 2000, "ContentType": "image/png"}
    valid, err = provider.verify_object_metadata("key6", 2000, "image/png")
    assert valid is True
    assert err is None


def test_complaint_worker_bounded_retries_exhaustion(db_session: Session) -> None:
    """Worker Reliability: Retries are bounded to 3 attempts, after which the job is marked FAILED and acknowledged."""
    from unittest.mock import MagicMock

    from app.domains.complaints.ai_classifier import AIClassifierProvider, RetryableWorkerError
    from app.domains.complaints.models import (
        Complaint,
        ComplaintActivity,
        ComplaintAIStatus,
        ComplaintCategory,
        ComplaintPriority,
    )
    from app.domains.identity.models import Flat, User
    from app.messaging.envelope import EventEnvelope, EventMetadata
    from app.workers.complaint_worker import ComplaintAIHandler

    flat = db_session.query(Flat).first()
    user = db_session.query(User).first()
    assert flat and user

    complaint = Complaint(
        society_id=flat.society_id,
        flat_id=flat.id,
        created_by=user.id,
        complaint_number="CMP-EXHAUST-001",
        category=ComplaintCategory.PLUMBING,
        title="Broken flush valve",
        description="Flush valve leaking constantly",
        priority=ComplaintPriority.MEDIUM,
        ai_status=ComplaintAIStatus.FAILED,
    )
    db_session.add(complaint)
    db_session.flush()

    # Seed 3 prior failed activities
    for i in range(3):
        act = ComplaintActivity(
            society_id=complaint.society_id,
            complaint_id=complaint.id,
            actor_id=None,
            activity_type="AI_TRIAGE_FAILED",
            notes=f"Attempt {i + 1} timed out",
            activity_metadata={"attempt": i + 1, "retryable": True},
            created_at=datetime.now(UTC),
        )
        db_session.add(act)
    db_session.commit()
    db_session.refresh(complaint)

    mock_provider = MagicMock(spec=AIClassifierProvider)
    mock_provider.classify.side_effect = RetryableWorkerError("Timeout again")

    handler = ComplaintAIHandler(ai_provider=mock_provider)
    envelope = EventEnvelope(
        event_id=uuid.uuid4(),
        event_type="complaint.classify",
        aggregate_type="complaint",
        aggregate_id=str(complaint.id),
        timestamp=datetime.now(UTC).isoformat(),
        metadata=EventMetadata(correlation_id=str(uuid.uuid4())),
        payload={"complaint_id": str(complaint.id)},
    )

    # Bounded retries exhausted -> must NOT re-raise; acknowledges message cleanly
    handler.process(envelope, db_session)

    db_session.refresh(complaint)
    assert complaint.ai_status == ComplaintAIStatus.FAILED
    assert "Exceeded maximum retry attempts" in (complaint.ai_reasoning or "")


# =============================================================================
# Worker Lease Fencing & Image Byte Validation Regression Tests
# =============================================================================


def test_stale_worker_does_not_overwrite_completed_result(db_session: Session) -> None:
    """Worker Lease Fencing: A stale worker whose claim token was superseded must NOT
    overwrite the successful result written by a faster competing worker."""
    from unittest.mock import MagicMock

    from app.domains.complaints.ai_classifier import AIClassifierProvider, AITriageResult
    from app.domains.complaints.models import (
        Complaint,
        ComplaintAIStatus,
        ComplaintCategory,
        ComplaintPriority,
    )
    from app.domains.identity.models import Flat, User
    from app.messaging.envelope import EventEnvelope, EventMetadata
    from app.workers.complaint_worker import ComplaintAIHandler

    flat = db_session.query(Flat).first()
    user = db_session.query(User).first()
    assert flat and user

    # Create complaint initially claimed by Worker A (token-A)
    complaint = Complaint(
        society_id=flat.society_id,
        flat_id=flat.id,
        created_by=user.id,
        complaint_number="CMP-FENCE-001",
        category=ComplaintCategory.ELECTRICAL,
        title="Power socket sparking",
        description="Main hall power socket emitting sparks",
        priority=ComplaintPriority.HIGH,
        ai_status=ComplaintAIStatus.PROCESSING,
        ai_processed_at=datetime.now(UTC) - timedelta(seconds=10),
        ai_claim_token="stale-token-from-worker-A",
    )
    db_session.add(complaint)
    db_session.commit()
    db_session.refresh(complaint)

    # Simulate Worker B winning: sets COMPLETED with its own token before Worker A finishes
    complaint.ai_status = ComplaintAIStatus.COMPLETED
    complaint.ai_claim_token = "fresh-token-from-worker-B"
    complaint.ai_suggested_priority = ComplaintPriority.CRITICAL
    complaint.ai_suggested_category = ComplaintCategory.ELECTRICAL
    complaint.ai_confidence_score = 0.97
    complaint.ai_summary = "Electrical spark hazard"
    complaint.ai_provider = "gemini"
    complaint.ai_model = "gemini-2.5-flash"
    complaint.ai_processed_at = datetime.now(UTC)
    db_session.commit()

    # Worker A now tries to persist — it carries stale-token-from-worker-A
    # We simulate this by patching the handler so the Phase 1 claim token doesn't
    # match what's in the DB (Worker B already wrote fresh-token-from-worker-B).
    # We confirm the worker returns without overwriting by running process() with a
    # complaint that already has PROCESSING status and expired lease (reclaim path),
    # but then the token fence catches the mismatch in Phase 3.

    # To test the token fence directly: set ai_status back to PROCESSING with token-A
    # so the idempotency guard passes, let classify succeed, then verify Phase 3 no-ops.
    complaint.ai_status = ComplaintAIStatus.PROCESSING
    complaint.ai_claim_token = "stale-token-from-worker-A"
    complaint.ai_processed_at = datetime.now(UTC) - timedelta(seconds=400)  # expired lease
    db_session.commit()
    db_session.refresh(complaint)

    # Mock provider returns a valid result — but it should be discarded due to token mismatch
    mock_provider = MagicMock(spec=AIClassifierProvider)
    mock_provider.classify.return_value = AITriageResult(
        suggested_category=ComplaintCategory.PLUMBING,  # stale AI thinks it's plumbing
        suggested_priority=ComplaintPriority.LOW,
        confidence_score=0.60,
        summary="Stale worker bad result",
        urgency_reason="None",
        reasoning="Should be discarded",
        provider="gemini",
        model="gemini-2.5-flash",
    )

    # Monkeypatch: after claim, overwrite the token in DB to simulate Worker B completing
    original_classify = mock_provider.classify

    def classify_and_inject_winner(*args, **kwargs):
        # Simulate Worker B completing while Worker A is in Phase 2
        db_session.query(Complaint).filter(Complaint.id == complaint.id).update(
            {
                "ai_status": "COMPLETED",
                "ai_claim_token": "fresh-token-from-worker-B-round2",
                "ai_suggested_priority": "CRITICAL",
                "ai_confidence_score": 0.99,
            }
        )
        db_session.commit()
        return original_classify(*args, **kwargs)

    mock_provider.classify.side_effect = classify_and_inject_winner

    handler = ComplaintAIHandler(ai_provider=mock_provider)
    envelope = EventEnvelope(
        event_id=uuid.uuid4(),
        event_type="complaint.classify",
        aggregate_type="complaint",
        aggregate_id=str(complaint.id),
        timestamp=datetime.now(UTC).isoformat(),
        metadata=EventMetadata(correlation_id=str(uuid.uuid4())),
        payload={"complaint_id": str(complaint.id)},
    )

    # Must complete without raising (stale worker gracefully steps aside)
    handler.process(envelope, db_session)

    db_session.refresh(complaint)

    # Worker B's result must be preserved — not overwritten by Worker A's stale data
    assert complaint.ai_status == ComplaintAIStatus.COMPLETED
    assert complaint.ai_claim_token == "fresh-token-from-worker-B-round2"
    assert complaint.ai_confidence_score == 0.99  # Worker B's value preserved
    # Worker A's stale suggested_priority (LOW) must NOT have been written
    assert complaint.ai_suggested_priority == ComplaintPriority.CRITICAL


def test_attachment_invalid_image_bytes_rejected(client: TestClient, db_session: Session) -> None:
    """Image Byte Validation: Attachments whose bytes do not match their declared MIME type
    must be rejected with 400, marked FAILED, and deleted from storage."""
    from unittest.mock import patch

    from app.domains.complaints.models import AttachmentStatus, ComplaintAttachment

    # First create a complaint
    create_resp = client.post(
        "/api/v1/complaints",
        json={
            "flat_id": NEERAJ_FLAT_ID,
            "category": "PLUMBING",
            "title": "Bathroom tap broken",
            "description": "Bathroom tap not closing, water overflowing into drain",
            "priority": "LOW",
        },
        headers=NEERAJ_HEADERS,
    )
    assert create_resp.status_code == 201, create_resp.text
    complaint_id = create_resp.json()["id"]

    # Initiate attachment upload
    init_resp = client.post(
        f"/api/v1/complaints/me/{complaint_id}/attachments",
        json={
            "file_name": "photo.jpg",
            "file_size_bytes": 2048,
            "content_type": "image/jpeg",
        },
        headers=NEERAJ_HEADERS,
    )
    assert init_resp.status_code == 201, init_resp.text
    attachment_id = init_resp.json()["attachment_id"]

    # Patch validate_image_bytes to simulate an invalid JPEG (e.g. HTML file renamed to .jpg)
    with patch(
        "app.domains.complaints.storage.MockStorageProvider.validate_image_bytes",
        return_value=(False, "File bytes do not match JPEG signature"),
    ) as mock_validate:
        complete_resp = client.post(
            f"/api/v1/complaints/me/{complaint_id}/attachments/{attachment_id}/complete",
            headers=NEERAJ_HEADERS,
        )

    assert complete_resp.status_code == 400, complete_resp.text
    assert "image validation failed" in complete_resp.text.lower()

    # validate_image_bytes must have been called
    mock_validate.assert_called_once()

    # Attachment must be marked FAILED in DB
    att = (
        db_session.query(ComplaintAttachment)
        .filter(ComplaintAttachment.id == uuid.UUID(attachment_id))
        .first()
    )
    assert att is not None
    assert att.status == AttachmentStatus.FAILED


def test_attachment_valid_image_bytes_accepted(client: TestClient, db_session: Session) -> None:
    """Image Byte Validation: Attachments that pass both metadata and byte validation
    must be marked UPLOADED and return 200."""
    from unittest.mock import patch

    from app.domains.complaints.models import AttachmentStatus, ComplaintAttachment

    # Create a complaint
    create_resp = client.post(
        "/api/v1/complaints",
        json={
            "flat_id": NEERAJ_FLAT_ID,
            "category": "COMMON_AREA",
            "title": "Lobby light flickering badly",
            "description": "Main lobby ceiling light flickers every few seconds at night",
            "priority": "MEDIUM",
        },
        headers=NEERAJ_HEADERS,
    )
    assert create_resp.status_code == 201, create_resp.text
    complaint_id = create_resp.json()["id"]

    # Initiate attachment upload
    init_resp = client.post(
        f"/api/v1/complaints/me/{complaint_id}/attachments",
        json={
            "file_name": "lobby.png",
            "file_size_bytes": 4096,
            "content_type": "image/png",
        },
        headers=NEERAJ_HEADERS,
    )
    assert init_resp.status_code == 201, init_resp.text
    attachment_id = init_resp.json()["attachment_id"]

    # Patch validate_image_bytes to simulate a valid PNG
    with patch(
        "app.domains.complaints.storage.MockStorageProvider.validate_image_bytes",
        return_value=(True, None),
    ) as mock_validate:
        complete_resp = client.post(
            f"/api/v1/complaints/me/{complaint_id}/attachments/{attachment_id}/complete",
            headers=NEERAJ_HEADERS,
        )

    assert complete_resp.status_code == 200, complete_resp.text
    assert complete_resp.json()["status"] == "UPLOADED"

    # validate_image_bytes must have been called once
    mock_validate.assert_called_once()

    # Attachment must be UPLOADED in DB
    att = (
        db_session.query(ComplaintAttachment)
        .filter(ComplaintAttachment.id == uuid.UUID(attachment_id))
        .first()
    )
    assert att is not None
    assert att.status == AttachmentStatus.UPLOADED
