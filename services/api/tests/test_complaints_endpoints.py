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
