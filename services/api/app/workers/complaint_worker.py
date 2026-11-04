"""Complaint Categorization & AI Job Worker

Consumes complaint AI jobs from QUEUE_COMPLAINT_AI_JOBS:
- complaint.classify
- complaint.assign_priority

Executes Gemini AI categorization and advisory triage asynchronously,
persisting AI suggestions, reasoning, confidence score, and model metadata.
"""

import uuid
from datetime import UTC, datetime

import requests
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.domains.complaints.ai_classifier import (
    AIClassifierProvider,
    PermanentWorkerError,
    RetryableWorkerError,
    get_ai_classifier_provider,
)
from app.domains.complaints.models import (
    Complaint,
    ComplaintActivity,
    ComplaintAIStatus,
)
from app.domains.reliability.models import AuditEvent
from app.messaging.consumer import MessageHandler, dispatcher
from app.messaging.envelope import EventEnvelope

PROCESSING_LEASE_SECONDS = 300
MAX_WORKER_RETRIES = 3


def is_retryable_error(exc: Exception) -> bool:
    """Distinguishes transient/retryable network and provider errors from permanent failures."""
    if isinstance(exc, RetryableWorkerError):
        return True
    if isinstance(exc, PermanentWorkerError):
        return False
    if isinstance(exc, (requests.RequestException, TimeoutError, ConnectionError, OSError)):
        return True
    status_code = getattr(exc, "status_code", None)
    if status_code in (429, 500, 502, 503, 504):
        return True
    err_str = str(exc).lower()
    return any(
        kw in err_str
        for kw in (
            "timeout",
            "connection",
            "rate limit",
            "429",
            "503",
            "502",
            "500",
            "temporary",
            "unavailable",
        )
    )


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

        now = datetime.now(UTC)

        # ---------------------------------------------------------------------
        # Phase 1: Atomically claim job with row-level lock (Short DB transaction)
        # ---------------------------------------------------------------------
        complaint = (
            db.query(Complaint).filter(Complaint.id == complaint_id).with_for_update().first()
        )
        if not complaint:
            logger.warning(
                f"[ComplaintAIWorker] Complaint {complaint_id} not found; skipping classification"
            )
            return

        # Idempotency guard: If complaint AI triage has already completed or used fallback, skip repeated work
        if complaint.ai_status in (ComplaintAIStatus.COMPLETED, ComplaintAIStatus.FALLBACK):
            logger.info(
                f"[ComplaintAIWorker] Complaint {complaint_id} already processed with status {complaint.ai_status}; skipping duplicate execution."
            )
            return

        # Lease / In-flight check: If currently PROCESSING, verify lease expiration
        if complaint.ai_status == ComplaintAIStatus.PROCESSING and complaint.ai_processed_at:
            proc_at = complaint.ai_processed_at
            if proc_at.tzinfo is None:
                proc_at = proc_at.replace(tzinfo=UTC)
            age_seconds = (now - proc_at).total_seconds()
            if age_seconds < PROCESSING_LEASE_SECONDS:
                logger.info(
                    f"[ComplaintAIWorker] Complaint {complaint_id} is actively being processed by another worker (lease age {int(age_seconds)}s < {PROCESSING_LEASE_SECONDS}s); skipping duplicate execution."
                )
                return
            logger.warning(
                f"[ComplaintAIWorker] Complaint {complaint_id} processing lease expired ({int(age_seconds)}s); reclaiming job."
            )

        # Bounded retries: check prior failure attempts
        failed_attempts = (
            db.query(ComplaintActivity)
            .filter(
                ComplaintActivity.complaint_id == complaint_id,
                ComplaintActivity.activity_type == "AI_TRIAGE_FAILED",
            )
            .count()
        )
        if failed_attempts >= MAX_WORKER_RETRIES:
            logger.warning(
                f"[ComplaintAIWorker] Complaint {complaint_id} exceeded maximum retries ({failed_attempts}/{MAX_WORKER_RETRIES}); acknowledging message as permanently FAILED."
            )
            complaint.ai_status = ComplaintAIStatus.FAILED
            complaint.ai_reasoning = (
                f"Exceeded maximum retry attempts ({failed_attempts}/{MAX_WORKER_RETRIES})"
            )
            complaint.ai_processed_at = now
            db.commit()
            return

        # Atomically claim the job — mint a unique token so Phase 3 can prove ownership
        claim_token = str(uuid.uuid4())
        complaint.ai_status = ComplaintAIStatus.PROCESSING
        complaint.ai_processed_at = now
        complaint.ai_claim_token = claim_token
        title = complaint.title
        description = complaint.description
        category = complaint.category
        society_id = complaint.society_id

        # Commit claim and release DB lock!
        db.commit()

        # ---------------------------------------------------------------------
        # Phase 2: Perform AI Classification outside DB transaction (No lock held)
        # ---------------------------------------------------------------------
        triage = None
        classify_error: Exception | None = None
        try:
            triage = self.ai_provider.classify(
                title=title,
                description=description,
                selected_category=category,
            )
        except Exception as exc:
            classify_error = exc
            logger.error(
                f"[ComplaintAIWorker] AI triage classification call failed for complaint {complaint_id}: {exc}",
                exc_info=True,
            )

        # ---------------------------------------------------------------------
        # Phase 3: Persist outcome in a new short DB transaction
        # ---------------------------------------------------------------------
        complaint_update = (
            db.query(Complaint).filter(Complaint.id == complaint_id).with_for_update().first()
        )
        if not complaint_update:
            return

        # Lease ownership fence: verify our claim token is still the active one.
        # If another worker completed the job while we were calling the AI provider,
        # its token will differ from ours. In that case, do not overwrite the result.
        if complaint_update.ai_claim_token != claim_token:
            logger.warning(
                f"[ComplaintAIWorker] Stale claim token for complaint {complaint_id} "
                f"(ours={claim_token!r}, stored={complaint_update.ai_claim_token!r}). "
                "Another worker already completed this job; skipping overwrite."
            )
            return

        now_final = datetime.now(UTC)

        if classify_error is not None:
            # Handle classification failure
            retryable = is_retryable_error(classify_error)
            current_attempt = failed_attempts + 1

            complaint_update.ai_status = ComplaintAIStatus.FAILED
            complaint_update.ai_reasoning = f"Classification processing failed: {classify_error}"[
                :1000
            ]
            complaint_update.ai_processed_at = now_final

            fail_activity = ComplaintActivity(
                society_id=society_id,
                complaint_id=complaint_id,
                actor_id=None,
                activity_type="AI_TRIAGE_FAILED",
                notes=f"Attempt {current_attempt} failed: {classify_error}"[:255],
                activity_metadata={
                    "error": str(classify_error),
                    "attempt": current_attempt,
                    "retryable": retryable,
                },
                created_at=now_final,
            )
            db.add(fail_activity)
            db.commit()

            if retryable and current_attempt < MAX_WORKER_RETRIES:
                logger.info(
                    f"[ComplaintAIWorker] Re-raising retryable error for complaint {complaint_id} to trigger queue redrive/retry (attempt {current_attempt}/{MAX_WORKER_RETRIES})"
                )
                raise RetryableWorkerError(
                    f"Retryable AI triage failure (attempt {current_attempt}/{MAX_WORKER_RETRIES}): {classify_error}"
                ) from classify_error
            else:
                logger.warning(
                    f"[ComplaintAIWorker] Non-retryable error or retries exhausted ({current_attempt}/{MAX_WORKER_RETRIES}) for complaint {complaint_id}; acknowledging message."
                )
                return

        # Classification succeeded
        assert triage is not None
        is_fallback = "fallback" in triage.provider

        complaint_update.ai_suggested_category = triage.suggested_category
        complaint_update.ai_suggested_priority = triage.suggested_priority
        complaint_update.ai_confidence_score = triage.confidence_score
        complaint_update.ai_summary = triage.summary
        complaint_update.ai_urgency_reason = triage.urgency_reason
        complaint_update.ai_reasoning = triage.reasoning
        complaint_update.ai_provider = triage.provider
        complaint_update.ai_model = triage.model
        complaint_update.ai_processed_at = now_final
        complaint_update.ai_status = (
            ComplaintAIStatus.FALLBACK if is_fallback else ComplaintAIStatus.COMPLETED
        )

        activity = ComplaintActivity(
            society_id=complaint_update.society_id,
            complaint_id=complaint_update.id,
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
            created_at=now_final,
        )
        db.add(activity)

        audit = AuditEvent(
            society_id=complaint_update.society_id,
            actor_id=None,
            action=f"{envelope.event_type}.processed",
            resource_type="Complaint",
            resource_id=str(complaint_update.id),
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
            f"[ComplaintAIWorker] Completed {envelope.event_type} for complaint {complaint_update.id} using {triage.provider} ({triage.model})"
        )


complaint_handler = ComplaintAIHandler()
dispatcher.register(complaint_handler)
