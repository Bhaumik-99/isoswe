"""Complaints Domain Service Layer

Orchestrates authoritative business logic, safety rules, SLA tracking, and auditability for:
1. Resident complaint submission and validation
2. Deterministic multilingual safety escalation before AI triage
3. AI-assisted categorization and duplicate candidate detection
4. Workload-based auto-assignment to active helpdesk staff
5. Server-authoritative lifecycle state transitions
6. Public conversations vs. private internal helpdesk notes
7. Secure presigned attachment URLs (S3 / mock)
8. Transactional audit log & outbox event publishing
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import AuthorizationError, NotFoundError, TenantIsolationError, ValidationError
from app.domains.complaints.ai_classifier import (
    AIClassifierProvider,
    DeterministicAIClassifierProvider,
)
from app.domains.complaints.assignment import find_least_loaded_staff
from app.domains.complaints.duplicate_detector import find_duplicate_candidates
from app.domains.complaints.models import (
    Complaint,
    ComplaintActivity,
    ComplaintAttachment,
    ComplaintCategory,
    ComplaintComment,
    ComplaintPriority,
    ComplaintStatus,
)
from app.domains.complaints.repository import ComplaintRepository
from app.domains.complaints.safety import check_safety_escalation
from app.domains.complaints.schemas import (
    ActivityResponse,
    AssignComplaintRequest,
    AttachmentResponse,
    CommentResponse,
    ComplaintResponse,
    CreateCommentRequest,
    CreateComplaintRequest,
    HelpdeskDashboardMetricsResponse,
    InitiateAttachmentUploadRequest,
    PresignedUploadResponse,
    RateComplaintRequest,
    ReopenComplaintRequest,
    UpdateComplaintPriorityRequest,
    UpdateComplaintStatusRequest,
)
from app.domains.complaints.sla import calculate_sla_deadlines, is_sla_breached
from app.domains.complaints.storage import (
    ALLOWED_MIME_TYPES,
    MAX_FILE_SIZE_BYTES,
    MockStorageProvider,
    StorageProvider,
)
from app.domains.identity.models import Flat, RoleType, User, UserRole, UserStatus
from app.domains.identity.schemas import CurrentUserClaims
from app.domains.reliability.models import AuditEvent, OutboxEvent, OutboxStatus


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def utc_now() -> datetime:
    return datetime.now(UTC)


ALLOWED_STATUS_TRANSITIONS: dict[ComplaintStatus, set[ComplaintStatus]] = {
    ComplaintStatus.SUBMITTED: {
        ComplaintStatus.TRIAGED,
        ComplaintStatus.ASSIGNED,
        ComplaintStatus.IN_PROGRESS,
        ComplaintStatus.CANCELLED,
    },
    ComplaintStatus.TRIAGED: {
        ComplaintStatus.ASSIGNED,
        ComplaintStatus.IN_PROGRESS,
        ComplaintStatus.CANCELLED,
    },
    ComplaintStatus.ASSIGNED: {
        ComplaintStatus.IN_PROGRESS,
        ComplaintStatus.AWAITING_RESIDENT,
        ComplaintStatus.CANCELLED,
    },
    ComplaintStatus.IN_PROGRESS: {
        ComplaintStatus.AWAITING_RESIDENT,
        ComplaintStatus.RESOLVED,
        ComplaintStatus.CANCELLED,
    },
    ComplaintStatus.AWAITING_RESIDENT: {
        ComplaintStatus.IN_PROGRESS,
        ComplaintStatus.RESOLVED,
        ComplaintStatus.CANCELLED,
    },
    ComplaintStatus.RESOLVED: {
        ComplaintStatus.CLOSED,
        ComplaintStatus.REOPENED,
    },
    ComplaintStatus.REOPENED: {
        ComplaintStatus.ASSIGNED,
        ComplaintStatus.IN_PROGRESS,
        ComplaintStatus.CANCELLED,
    },
    ComplaintStatus.CLOSED: set(),
    ComplaintStatus.CANCELLED: set(),
}


class ComplaintService:
    def __init__(
        self,
        db: Session,
        storage_provider: StorageProvider | None = None,
        ai_classifier: AIClassifierProvider | None = None,
    ) -> None:
        self.db = db
        self.repo = ComplaintRepository(db)
        self.storage_provider = storage_provider or MockStorageProvider()
        self.ai_classifier = ai_classifier or DeterministicAIClassifierProvider()

    def _resolve_society_id(
        self, claims: CurrentUserClaims, society_id: UUID | None = None
    ) -> UUID:
        if society_id and society_id in claims.society_ids:
            return society_id
        if claims.society_ids:
            return claims.society_ids[0]
        raise AuthorizationError("No authorized society found for user")

    def _emit_outbox(
        self, event_type: str, aggregate_id: str, payload: dict[str, Any]
    ) -> OutboxEvent:
        event = OutboxEvent(
            event_type=event_type,
            aggregate_type="complaint",
            aggregate_id=aggregate_id,
            payload=payload,
            status=OutboxStatus.PENDING,
        )
        self.db.add(event)
        return event

    def _emit_audit(
        self,
        society_id: UUID,
        actor_id: UUID | None,
        action: str,
        resource_id: str,
        metadata: dict[str, Any],
    ) -> AuditEvent:
        audit = AuditEvent(
            society_id=society_id,
            actor_id=actor_id,
            action=action,
            resource_type="complaint",
            resource_id=resource_id,
            correlation_id=str(uuid.uuid4()),
            event_metadata=metadata,
        )
        self.db.add(audit)
        return audit

    def _record_activity(
        self,
        complaint: Complaint,
        actor_id: UUID | None,
        activity_type: str,
        old_value: str | None = None,
        new_value: str | None = None,
        notes: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ComplaintActivity:
        activity = ComplaintActivity(
            society_id=complaint.society_id,
            complaint_id=complaint.id,
            actor_id=actor_id,
            activity_type=activity_type,
            old_value=old_value,
            new_value=new_value,
            notes=notes,
            activity_metadata=metadata or {},
        )
        return self.repo.add_activity(activity)

    def _enrich_complaint_response(
        self,
        complaint: Complaint,
        include_internal_comments: bool = False,
        duplicate_candidates: list[UUID] | None = None,
    ) -> ComplaintResponse:
        user_ids: set[UUID] = {complaint.created_by}
        if complaint.assigned_to:
            user_ids.add(complaint.assigned_to)
        for att in complaint.attachments:
            user_ids.add(att.uploaded_by)
        for comm in complaint.comments:
            user_ids.add(comm.user_id)
        for act in complaint.activities:
            if act.actor_id:
                user_ids.add(act.actor_id)

        user_map = self.repo.get_users_by_ids(list(user_ids))

        flat_tower = self.repo.get_flat_with_tower(complaint.flat_id, complaint.society_id)
        tower_num = flat_tower[1].tower_number if flat_tower else None
        flat_num = flat_tower[0].flat_number if flat_tower else None

        def _name(uid: UUID | None) -> str | None:
            if not uid:
                return None
            u = user_map.get(uid)
            return u.full_name if u else None

        attachments_res = [
            AttachmentResponse(
                id=att.id,
                complaint_id=att.complaint_id,
                file_name=att.file_name,
                file_size_bytes=att.file_size_bytes,
                content_type=att.content_type,
                download_url=self.storage_provider.generate_download_url(att.storage_key),
                uploaded_by=att.uploaded_by,
                uploader_name=_name(att.uploaded_by),
                created_at=att.created_at,
            )
            for att in complaint.attachments
        ]

        visible_comments = (
            complaint.comments
            if include_internal_comments
            else [c for c in complaint.comments if not c.is_internal]
        )
        comments_res = [
            CommentResponse(
                id=c.id,
                complaint_id=c.complaint_id,
                user_id=c.user_id,
                user_name=_name(c.user_id),
                user_role="HELPDESK" if c.is_internal else None,
                comment=c.comment,
                is_internal=c.is_internal,
                created_at=c.created_at,
            )
            for c in visible_comments
        ]

        activities_res = [
            ActivityResponse(
                id=act.id,
                complaint_id=act.complaint_id,
                actor_id=act.actor_id,
                actor_name=_name(act.actor_id),
                activity_type=act.activity_type,
                old_value=act.old_value,
                new_value=act.new_value,
                notes=act.notes,
                created_at=act.created_at,
            )
            for act in complaint.activities
        ]

        creator_name = _name(complaint.created_by)
        assignee_name = _name(complaint.assigned_to)
        sla_breached = is_sla_breached(complaint)

        return ComplaintResponse(
            id=complaint.id,
            society_id=complaint.society_id,
            flat_id=complaint.flat_id,
            tower_number=tower_num,
            flat_number=flat_num,
            created_by=complaint.created_by,
            creator_name=creator_name,
            assigned_to=complaint.assigned_to,
            assignee_name=assignee_name,
            complaint_number=complaint.complaint_number,
            category=complaint.category,
            subcategory=complaint.subcategory,
            title=complaint.title,
            description=complaint.description,
            priority=complaint.priority,
            status=complaint.status,
            ai_suggested_category=complaint.ai_suggested_category,
            ai_suggested_priority=complaint.ai_suggested_priority,
            ai_confidence_score=complaint.ai_confidence_score,
            ai_summary=complaint.ai_summary,
            ai_urgency_reason=complaint.ai_urgency_reason,
            safety_escalated=complaint.safety_escalated,
            safety_escalation_reason=complaint.safety_escalation_reason,
            duplicate_of_id=complaint.duplicate_of_id,
            duplicate_candidates=duplicate_candidates or [],
            first_response_deadline=complaint.first_response_deadline,
            resolution_deadline=complaint.resolution_deadline,
            first_response_at=complaint.first_response_at,
            resolved_at=complaint.resolved_at,
            closed_at=complaint.closed_at,
            reopened_at=complaint.reopened_at,
            reopened_count=complaint.reopened_count,
            is_sla_breached=sla_breached,
            rating=complaint.rating,
            feedback=complaint.feedback,
            attachments=attachments_res,
            comments=comments_res,
            activities=activities_res,
            created_at=complaint.created_at,
            updated_at=complaint.updated_at,
        )

    # =========================================================================
    # Resident Operations
    # =========================================================================

    def create_complaint(
        self, claims: CurrentUserClaims, request: CreateComplaintRequest
    ) -> ComplaintResponse:
        # 1. Authorize flat ownership in resident claims
        if request.flat_id not in claims.active_flat_ids:
            raise TenantIsolationError(
                f"You do not have an active membership for flat {request.flat_id}"
            )

        flat = self.db.query(Flat).filter(Flat.id == request.flat_id).first()
        if not flat:
            raise NotFoundError(f"Flat {request.flat_id} not found")

        society_id = flat.society_id
        if society_id not in claims.society_ids:
            raise TenantIsolationError("Flat belongs to a society you are not authorized to access")

        now = utc_now()
        complaint_num = self.repo.generate_complaint_number(society_id)

        # 2. Deterministic Multilingual Safety Escalation Engine
        safety_check = check_safety_escalation(request.title, request.description)
        is_safety = safety_check.is_safety_escalated
        safety_reason = safety_check.reason

        # 3. AI Triage & Advisory Suggestions
        ai_triage = self.ai_classifier.classify(
            request.title, request.description, request.category
        )

        # 4. Final priority calculation (Deterministic safety MUST be CRITICAL)
        if is_safety:
            final_priority = ComplaintPriority.CRITICAL
            final_category = (
                request.category
                if request.category != ComplaintCategory.OTHER
                else ai_triage.suggested_category
            )
        else:
            final_priority = ai_triage.suggested_priority
            final_category = (
                request.category
                if request.category != ComplaintCategory.OTHER
                else ai_triage.suggested_category
            )

        # 5. SLA Calculation
        first_resp_dl, res_dl = calculate_sla_deadlines(final_priority, now)

        # 6. Workload-based Helpdesk Auto-Assignment
        assigned_staff_id = find_least_loaded_staff(self.db, society_id)
        initial_status = ComplaintStatus.ASSIGNED if assigned_staff_id else ComplaintStatus.TRIAGED

        # 7. Duplicate Candidate Detection
        active_complaints = self.repo.get_active_complaints_for_society(society_id)
        duplicate_candidate_ids = find_duplicate_candidates(
            request.title,
            request.description,
            request.flat_id,
            active_complaints,
        )

        # 8. Create Complaint Model
        complaint = Complaint(
            society_id=society_id,
            flat_id=request.flat_id,
            created_by=claims.user_id,
            assigned_to=assigned_staff_id,
            complaint_number=complaint_num,
            category=final_category,
            subcategory=request.subcategory,
            title=request.title.strip(),
            description=request.description.strip(),
            priority=final_priority,
            status=initial_status,
            ai_suggested_category=ai_triage.suggested_category,
            ai_suggested_priority=ai_triage.suggested_priority,
            ai_confidence_score=ai_triage.confidence_score,
            ai_summary=ai_triage.summary,
            ai_urgency_reason=ai_triage.urgency_reason,
            safety_escalated=is_safety,
            safety_escalation_reason=safety_reason,
            first_response_deadline=first_resp_dl,
            resolution_deadline=res_dl,
            created_at=now,
            updated_at=now,
        )
        self.repo.create_complaint(complaint)

        # 9. Record Activities
        self._record_activity(
            complaint,
            actor_id=claims.user_id,
            activity_type="CREATED",
            notes="Complaint submitted by resident",
        )

        if is_safety:
            self._record_activity(
                complaint,
                actor_id=None,
                activity_type="SAFETY_ESCALATED",
                notes=f"Forced CRITICAL priority: {safety_reason}",
            )

        if assigned_staff_id:
            self._record_activity(
                complaint,
                actor_id=None,
                activity_type="ASSIGNED",
                old_value=None,
                new_value=str(assigned_staff_id),
                notes="Auto-assigned based on staff active workload",
            )

        # 10. Audit & Outbox Events
        self._emit_audit(
            society_id=society_id,
            actor_id=claims.user_id,
            action="complaint.created",
            resource_id=str(complaint.id),
            metadata={
                "complaint_number": complaint_num,
                "priority": final_priority.value,
                "safety_escalated": is_safety,
                "assigned_to": str(assigned_staff_id) if assigned_staff_id else None,
            },
        )

        self._emit_outbox(
            event_type="complaint.created",
            aggregate_id=str(complaint.id),
            payload={
                "complaint_id": str(complaint.id),
                "society_id": str(society_id),
                "flat_id": str(request.flat_id),
                "complaint_number": complaint_num,
                "priority": final_priority.value,
                "safety_escalated": is_safety,
            },
        )

        if is_safety:
            self._emit_outbox(
                event_type="complaint.safety_escalated",
                aggregate_id=str(complaint.id),
                payload={
                    "complaint_id": str(complaint.id),
                    "society_id": str(society_id),
                    "reason": safety_reason,
                    "priority": final_priority.value,
                },
            )

        self.db.commit()
        self.db.refresh(complaint)

        return self._enrich_complaint_response(
            complaint,
            include_internal_comments=False,
            duplicate_candidates=duplicate_candidate_ids,
        )

    def get_resident_complaint(
        self, claims: CurrentUserClaims, complaint_id: UUID
    ) -> ComplaintResponse:
        complaint = self.db.query(Complaint).filter(Complaint.id == complaint_id).first()
        if not complaint or complaint.society_id not in claims.society_ids:
            raise NotFoundError(f"Complaint {complaint_id} not found")

        # Must belong to resident's flat or created by resident
        if (
            complaint.flat_id not in claims.active_flat_ids
            and complaint.created_by != claims.user_id
        ):
            raise AuthorizationError("Access denied: You do not own this complaint")

        return self._enrich_complaint_response(complaint, include_internal_comments=False)

    def list_resident_complaints(
        self,
        claims: CurrentUserClaims,
        *,
        status: ComplaintStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ComplaintResponse]:
        society_id = self._resolve_society_id(claims)
        statuses = [status] if status else None
        complaints, _ = self.repo.list_complaints(
            society_id,
            flat_ids=claims.active_flat_ids,
            statuses=statuses,
            limit=limit,
            offset=offset,
        )
        return [
            self._enrich_complaint_response(c, include_internal_comments=False) for c in complaints
        ]

    # =========================================================================
    # Helpdesk Staff Operations
    # =========================================================================

    def get_helpdesk_complaint(
        self, claims: CurrentUserClaims, complaint_id: UUID
    ) -> ComplaintResponse:
        complaint = self.db.query(Complaint).filter(Complaint.id == complaint_id).first()
        if not complaint or complaint.society_id not in claims.society_ids:
            raise NotFoundError(f"Complaint {complaint_id} not found in this society")

        active = self.repo.get_active_complaints_for_society(complaint.society_id)
        candidates = find_duplicate_candidates(
            complaint.title,
            complaint.description,
            complaint.flat_id,
            active,
            current_complaint_id=complaint.id,
        )

        return self._enrich_complaint_response(
            complaint, include_internal_comments=True, duplicate_candidates=candidates
        )

    def list_helpdesk_complaints(
        self,
        claims: CurrentUserClaims,
        *,
        society_id: UUID | None = None,
        assigned_to: UUID | None = None,
        unassigned_only: bool = False,
        statuses: list[ComplaintStatus] | None = None,
        priority: ComplaintPriority | None = None,
        category: ComplaintCategory | None = None,
        tower_id: UUID | None = None,
        search: str | None = None,
        is_sla_breached_only: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[ComplaintResponse], int]:
        target_society_id = self._resolve_society_id(claims, society_id)
        complaints, total = self.repo.list_complaints(
            target_society_id,
            assigned_to=assigned_to,
            unassigned_only=unassigned_only,
            statuses=statuses,
            priority=priority,
            category=category,
            tower_id=tower_id,
            search=search,
            is_sla_breached_only=is_sla_breached_only,
            offset=offset,
            limit=limit,
        )
        return [
            self._enrich_complaint_response(c, include_internal_comments=True) for c in complaints
        ], total

    def update_status(
        self,
        claims: CurrentUserClaims,
        complaint_id: UUID,
        request: UpdateComplaintStatusRequest,
    ) -> ComplaintResponse:
        complaint = self.db.query(Complaint).filter(Complaint.id == complaint_id).first()
        if not complaint or complaint.society_id not in claims.society_ids:
            raise NotFoundError(f"Complaint {complaint_id} not found in this society")

        current_status = complaint.status
        target_status = request.status

        if target_status == current_status:
            return self._enrich_complaint_response(complaint, include_internal_comments=True)

        allowed = ALLOWED_STATUS_TRANSITIONS.get(current_status, set())
        if target_status not in allowed:
            raise ValidationError(
                f"Invalid transition from {current_status.value} to {target_status.value}"
            )

        now = utc_now()
        complaint.status = target_status
        complaint.updated_at = now

        if complaint.first_response_at is None and target_status in (
            ComplaintStatus.IN_PROGRESS,
            ComplaintStatus.AWAITING_RESIDENT,
            ComplaintStatus.RESOLVED,
        ):
            complaint.first_response_at = now
            self._record_activity(
                complaint,
                actor_id=claims.user_id,
                activity_type="FIRST_RESPONSE_RECORDED",
                notes="First staff response recorded upon status transition",
            )

        if target_status == ComplaintStatus.RESOLVED:
            complaint.resolved_at = now
        elif target_status == ComplaintStatus.CLOSED:
            complaint.closed_at = now

        self._record_activity(
            complaint,
            actor_id=claims.user_id,
            activity_type="STATUS_CHANGED",
            old_value=current_status.value,
            new_value=target_status.value,
            notes=request.notes,
        )

        self._emit_audit(
            society_id=complaint.society_id,
            actor_id=claims.user_id,
            action="complaint.status_updated",
            resource_id=str(complaint.id),
            metadata={"old_status": current_status.value, "new_status": target_status.value},
        )

        self._emit_outbox(
            event_type="complaint.status_changed",
            aggregate_id=str(complaint.id),
            payload={
                "complaint_id": str(complaint.id),
                "society_id": str(complaint.society_id),
                "old_status": current_status.value,
                "new_status": target_status.value,
            },
        )

        if target_status == ComplaintStatus.RESOLVED:
            self._emit_outbox(
                event_type="complaint.resolved",
                aggregate_id=str(complaint.id),
                payload={
                    "complaint_id": str(complaint.id),
                    "society_id": str(complaint.society_id),
                    "resolved_at": now.isoformat(),
                },
            )

        self.db.commit()
        self.db.refresh(complaint)
        return self._enrich_complaint_response(complaint, include_internal_comments=True)

    def assign_complaint(
        self,
        claims: CurrentUserClaims,
        complaint_id: UUID,
        request: AssignComplaintRequest,
    ) -> ComplaintResponse:
        complaint = self.db.query(Complaint).filter(Complaint.id == complaint_id).first()
        if not complaint or complaint.society_id not in claims.society_ids:
            raise NotFoundError(f"Complaint {complaint_id} not found in this society")

        staff_check = (
            self.db.query(User)
            .join(UserRole, UserRole.user_id == User.id)
            .filter(
                User.id == request.assigned_to,
                UserRole.society_id == complaint.society_id,
                UserRole.role == RoleType.HELPDESK,
                User.status == UserStatus.ACTIVE,
            )
            .first()
        )
        if not staff_check:
            raise ValidationError(
                "Target staff member is not an active helpdesk user in this society"
            )

        old_assignee = str(complaint.assigned_to) if complaint.assigned_to else None
        complaint.assigned_to = request.assigned_to

        if complaint.status in (ComplaintStatus.SUBMITTED, ComplaintStatus.TRIAGED):
            complaint.status = ComplaintStatus.ASSIGNED

        now = utc_now()
        complaint.updated_at = now

        self._record_activity(
            complaint,
            actor_id=claims.user_id,
            activity_type="ASSIGNED",
            old_value=old_assignee,
            new_value=str(request.assigned_to),
            notes=request.notes,
        )

        self._emit_audit(
            society_id=complaint.society_id,
            actor_id=claims.user_id,
            action="complaint.assigned",
            resource_id=str(complaint.id),
            metadata={"assigned_to": str(request.assigned_to), "previous": old_assignee},
        )

        self._emit_outbox(
            event_type="complaint.assigned",
            aggregate_id=str(complaint.id),
            payload={
                "complaint_id": str(complaint.id),
                "society_id": str(complaint.society_id),
                "assigned_to": str(request.assigned_to),
            },
        )

        self.db.commit()
        self.db.refresh(complaint)
        return self._enrich_complaint_response(complaint, include_internal_comments=True)

    def update_priority(
        self,
        claims: CurrentUserClaims,
        complaint_id: UUID,
        request: UpdateComplaintPriorityRequest,
    ) -> ComplaintResponse:
        complaint = self.db.query(Complaint).filter(Complaint.id == complaint_id).first()
        if not complaint or complaint.society_id not in claims.society_ids:
            raise NotFoundError(f"Complaint {complaint_id} not found in this society")

        old_priority = complaint.priority
        new_priority = request.priority

        if old_priority == new_priority:
            return self._enrich_complaint_response(complaint, include_internal_comments=True)

        complaint.priority = new_priority
        first_resp_dl, res_dl = calculate_sla_deadlines(new_priority, complaint.created_at)
        complaint.first_response_deadline = first_resp_dl
        complaint.resolution_deadline = res_dl
        complaint.updated_at = utc_now()

        self._record_activity(
            complaint,
            actor_id=claims.user_id,
            activity_type="PRIORITY_CHANGED",
            old_value=old_priority.value,
            new_value=new_priority.value,
            notes=request.reason,
        )

        self.db.commit()
        self.db.refresh(complaint)
        return self._enrich_complaint_response(complaint, include_internal_comments=True)

    # =========================================================================
    # Reopen & Rating Operations
    # =========================================================================

    def reopen_complaint(
        self, claims: CurrentUserClaims, complaint_id: UUID, request: ReopenComplaintRequest
    ) -> ComplaintResponse:
        complaint = self.db.query(Complaint).filter(Complaint.id == complaint_id).first()
        if not complaint or complaint.society_id not in claims.society_ids:
            raise NotFoundError(f"Complaint {complaint_id} not found")

        if (
            complaint.flat_id not in claims.active_flat_ids
            and complaint.created_by != claims.user_id
        ):
            raise AuthorizationError("Access denied: You do not own this complaint")

        if complaint.status not in (ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED):
            raise ValidationError(
                f"Complaint cannot be reopened from {complaint.status.value} status. Only RESOLVED or CLOSED tickets can be reopened."
            )

        now = utc_now()
        ref_time = _ensure_utc(complaint.resolved_at or complaint.closed_at or complaint.updated_at)
        if ref_time and (now - ref_time) > timedelta(days=7):
            raise ValidationError(
                "The 7-day reopening window for this complaint has expired. Please submit a new complaint."
            )

        old_status = complaint.status
        complaint.status = ComplaintStatus.REOPENED
        complaint.reopened_at = now
        complaint.reopened_count += 1
        complaint.resolved_at = None
        complaint.closed_at = None
        complaint.updated_at = now

        _, new_res_dl = calculate_sla_deadlines(complaint.priority, now)
        complaint.resolution_deadline = new_res_dl

        self._record_activity(
            complaint,
            actor_id=claims.user_id,
            activity_type="REOPENED",
            old_value=old_status.value,
            new_value=ComplaintStatus.REOPENED.value,
            notes=request.reason,
        )

        self._emit_outbox(
            event_type="complaint.reopened",
            aggregate_id=str(complaint.id),
            payload={
                "complaint_id": str(complaint.id),
                "society_id": str(complaint.society_id),
                "reason": request.reason,
            },
        )

        self.db.commit()
        self.db.refresh(complaint)
        return self._enrich_complaint_response(complaint, include_internal_comments=False)

    def rate_complaint(
        self, claims: CurrentUserClaims, complaint_id: UUID, request: RateComplaintRequest
    ) -> ComplaintResponse:
        complaint = self.db.query(Complaint).filter(Complaint.id == complaint_id).first()
        if not complaint or complaint.society_id not in claims.society_ids:
            raise NotFoundError(f"Complaint {complaint_id} not found")

        if (
            complaint.flat_id not in claims.active_flat_ids
            and complaint.created_by != claims.user_id
        ):
            raise AuthorizationError("Access denied: You do not own this complaint")

        if complaint.status not in (ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED):
            raise ValidationError(
                "Feedback and rating can only be provided for resolved complaints"
            )

        complaint.rating = request.rating
        complaint.feedback = request.feedback
        complaint.updated_at = utc_now()

        self._record_activity(
            complaint,
            actor_id=claims.user_id,
            activity_type="RATED",
            new_value=str(request.rating),
            notes=request.feedback,
        )

        self.db.commit()
        self.db.refresh(complaint)
        return self._enrich_complaint_response(complaint, include_internal_comments=False)

    # =========================================================================
    # Comments & Attachments
    # =========================================================================

    def add_comment(
        self,
        claims: CurrentUserClaims,
        complaint_id: UUID,
        request: CreateCommentRequest,
        is_staff: bool = False,
    ) -> CommentResponse:
        complaint = self.db.query(Complaint).filter(Complaint.id == complaint_id).first()
        if not complaint or complaint.society_id not in claims.society_ids:
            raise NotFoundError(f"Complaint {complaint_id} not found")

        if not is_staff and (
            complaint.flat_id not in claims.active_flat_ids
            and complaint.created_by != claims.user_id
        ):
            raise AuthorizationError("Access denied: You do not own this complaint")
            is_internal = False
        else:
            is_internal = request.is_internal

        now = utc_now()
        comment = ComplaintComment(
            society_id=complaint.society_id,
            complaint_id=complaint.id,
            user_id=claims.user_id,
            comment=request.comment.strip(),
            is_internal=is_internal,
            created_at=now,
        )
        self.repo.add_comment(comment)

        if is_staff and complaint.first_response_at is None:
            complaint.first_response_at = now
            self._record_activity(
                complaint,
                actor_id=claims.user_id,
                activity_type="FIRST_RESPONSE_RECORDED",
                notes="First helpdesk comment response recorded",
            )

        self._record_activity(
            complaint,
            actor_id=claims.user_id,
            activity_type="COMMENT_ADDED",
            notes="Internal note added" if is_internal else "Public comment added",
        )

        self.db.commit()
        self.db.refresh(comment)

        user_map = self.repo.get_users_by_ids([claims.user_id])
        user = user_map.get(claims.user_id)

        return CommentResponse(
            id=comment.id,
            complaint_id=comment.complaint_id,
            user_id=comment.user_id,
            user_name=user.full_name if user else None,
            user_role="HELPDESK" if is_internal else None,
            comment=comment.comment,
            is_internal=comment.is_internal,
            created_at=comment.created_at,
        )

    def initiate_attachment_upload(
        self,
        claims: CurrentUserClaims,
        complaint_id: UUID,
        request: InitiateAttachmentUploadRequest,
        is_staff: bool = False,
    ) -> PresignedUploadResponse:
        complaint = self.db.query(Complaint).filter(Complaint.id == complaint_id).first()
        if not complaint or complaint.society_id not in claims.society_ids:
            raise NotFoundError(f"Complaint {complaint_id} not found")

        if not is_staff and (
            complaint.flat_id not in claims.active_flat_ids
            and complaint.created_by != claims.user_id
        ):
            raise AuthorizationError("Access denied: You do not own this complaint")

        if request.content_type not in ALLOWED_MIME_TYPES:
            raise ValidationError(
                f"Unsupported content type '{request.content_type}'. Allowed types: {list(ALLOWED_MIME_TYPES.keys())}"
            )

        if request.file_size_bytes > MAX_FILE_SIZE_BYTES:
            raise ValidationError(
                f"File size {request.file_size_bytes} bytes exceeds maximum limit of 5MB"
            )

        ext = ALLOWED_MIME_TYPES[request.content_type]
        attachment_id = uuid.uuid4()
        storage_key = f"complaints/{complaint.society_id}/{complaint.id}/{attachment_id}{ext}"

        upload_url = self.storage_provider.generate_upload_url(
            storage_key, request.content_type, expires_in_seconds=3600
        )

        attachment = ComplaintAttachment(
            id=attachment_id,
            society_id=complaint.society_id,
            complaint_id=complaint.id,
            file_name=request.file_name,
            file_size_bytes=request.file_size_bytes,
            content_type=request.content_type,
            storage_key=storage_key,
            uploaded_by=claims.user_id,
            created_at=utc_now(),
        )
        self.repo.add_attachment(attachment)

        self._record_activity(
            complaint,
            actor_id=claims.user_id,
            activity_type="ATTACHMENT_UPLOADED",
            notes=f"Attachment registered: {request.file_name}",
        )

        self.db.commit()

        return PresignedUploadResponse(
            attachment_id=attachment_id,
            upload_url=upload_url,
            storage_key=storage_key,
            expires_in_seconds=3600,
        )

    def get_dashboard_metrics(
        self, claims: CurrentUserClaims, society_id: UUID | None = None
    ) -> HelpdeskDashboardMetricsResponse:
        target_society_id = self._resolve_society_id(claims, society_id)
        metrics = self.repo.get_dashboard_metrics(target_society_id)
        return HelpdeskDashboardMetricsResponse(**metrics)
