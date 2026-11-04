"""Complaint Categorization & AI Job Worker

Consumes complaint AI jobs from QUEUE_COMPLAINT_AI_JOBS:
- complaint.classify
- complaint.assign_priority

Executes Gemini AI categorization and advisory triage asynchronously,
persisting AI suggestions, reasoning, confidence score, and model metadata.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.logging import logger
from app.domains.complaints.ai_classifier import AIClassifierProvider, get_ai_classifier_provider
from app.domains.complaints.models import (
    Complaint,
    ComplaintActivity,
    ComplaintAIStatus,
)
from app.domains.reliability.models import AuditEvent
from app.messaging.consumer import MessageHandler, dispatcher
from app.messaging.envelope import EventEnvelope


class ComplaintAIHandler(MessageHandler):
    def __init__(self, ai_provider: AIClassifierProvider | None = None) -> None:
        self._ai_provider = ai_provider

    @property
    def ai_provider(self) -> AIClassifierProvider:
        if self._ai_provider is None:
            self._ai_provider = get_ai_classifier_provider()
        return self._ai_provider

    @property
    def consumer_name(self) -> str:
        return "complaint_ai_worker"

    @property
    def supported_event_types(self) -> list[str]:
        return [
            "complaint.classify",
            "complaint.assign_priority",
        ]

    def process(self, envelope: EventEnvelope, db: Session) -> None:
        logger.info(
            f"[ComplaintAIWorker] Processing complaint job {envelope.event_id} ({envelope.event_type}) for aggregate {envelope.aggregate_id}"
        )

        try:
            complaint_id = uuid.UUID(envelope.aggregate_id)
        except Exception:
            logger.error(f"[ComplaintAIWorker] Invalid complaint UUID: {envelope.aggregate_id}")
            return

        complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
        if not complaint:
            logger.warning(
                f"[ComplaintAIWorker] Complaint {complaint_id} not found; skipping classification"
            )
            return

        # Perform AI classification
        triage = self.ai_provider.classify(
            title=complaint.title,
            description=complaint.description,
            selected_category=complaint.category,
        )

        now = datetime.now(UTC)
        is_fallback = "fallback" in triage.provider

        complaint.ai_suggested_category = triage.suggested_category
        complaint.ai_suggested_priority = triage.suggested_priority
        complaint.ai_confidence_score = triage.confidence_score
        complaint.ai_summary = triage.summary
        complaint.ai_urgency_reason = triage.urgency_reason
        complaint.ai_reasoning = triage.reasoning
        complaint.ai_provider = triage.provider
        complaint.ai_model = triage.model
        complaint.ai_processed_at = now
        complaint.ai_status = (
            ComplaintAIStatus.FALLBACK if is_fallback else ComplaintAIStatus.COMPLETED
        )

        # Record activity timeline entry
        activity = ComplaintActivity(
            society_id=complaint.society_id,
            complaint_id=complaint.id,
            actor_id=None,
            activity_type="AI_TRIAGE_COMPLETED",
            new_value=f"{triage.suggested_category.value} / {triage.suggested_priority.value}",
            notes=f"AI model {triage.model} ({triage.provider}) confidence: {int(triage.confidence_score * 100)}%. {triage.summary}",
            activity_metadata={
                "model": triage.model,
                "provider": triage.provider,
                "confidence": triage.confidence_score,
                "requires_human_review": triage.requires_human_review,
            },
            created_at=now,
        )
        db.add(activity)

        audit = AuditEvent(
            society_id=complaint.society_id,
            actor_id=None,
            action=f"{envelope.event_type}.processed",
            resource_type="Complaint",
            resource_id=str(complaint.id),
            correlation_id=envelope.metadata.correlation_id,
            event_metadata={
                "event_id": str(envelope.event_id),
                "event_type": envelope.event_type,
                "consumer": self.consumer_name,
                "model": triage.model,
                "provider": triage.provider,
                "suggested_category": triage.suggested_category.value,
                "suggested_priority": triage.suggested_priority.value,
                "confidence_score": triage.confidence_score,
            },
        )
        db.add(audit)
        db.commit()

        logger.info(
            f"[ComplaintAIWorker] Completed {envelope.event_type} for complaint {complaint.id} using {triage.provider} ({triage.model})"
        )


complaint_handler = ComplaintAIHandler()
dispatcher.register(complaint_handler)
