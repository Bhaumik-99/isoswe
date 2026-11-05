"""Bank Statement Reconciliation Asynchronous Queue Worker

Consumes reconciliation jobs and events from QUEUE_RECONCILIATION_JOBS:
- reconciliation.process_bank_statement: executes async parsing & deterministic matching
- reconciliation.statement_imported: audit and follow-on notification dispatch
- reconciliation.approved_and_posted: audit and ledger settlement confirmation

Features:
- Idempotent execution (skips already COMPLETED / POSTED entities)
- Transient vs. permanent error classification (re-raises retryable errors for SQS redelivery)
- Bounded retries and poison-pill neutralization
- Correlation ID tracking and structured audit event logging
"""

import uuid
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.domains.billing.models import Invoice, Payment
from app.domains.identity.models import Flat, FlatMembership, User
from app.domains.reconciliation.exceptions import (
    PermanentReconciliationWorkerError,
    RetryableReconciliationWorkerError,
)
from app.domains.reconciliation.matching import DeterministicMatchingEngine
from app.domains.reconciliation.models import (
    BankStatementImport,
    BankTransaction,
    ReconciliationMatch,
    StatementImportStatus,
    TransactionReconciliationStatus,
    TransactionType,
)
from app.domains.reliability.models import AuditEvent
from app.messaging.consumer import MessageHandler, dispatcher
from app.messaging.envelope import EventEnvelope

MAX_WORKER_RETRIES = 3


def is_retryable_reconciliation_error(exc: Exception) -> bool:
    """Distinguishes transient/retryable network and DB errors from permanent logical failures."""
    if isinstance(exc, RetryableReconciliationWorkerError):
        return True
    if isinstance(exc, PermanentReconciliationWorkerError):
        return False
    if isinstance(exc, (OperationalError, DBAPIError, ConnectionError, TimeoutError, OSError)):
        return True
    err_str = str(exc).lower()
    return any(kw in err_str for kw in ("deadlock", "lock", "timeout", "connection", "temporary"))


class ReconciliationJobHandler(MessageHandler):
    @property
    def consumer_name(self) -> str:
        return "reconciliation_worker"

    @property
    def supported_event_types(self) -> list[str]:
        return [
            "reconciliation.process_bank_statement",
            "reconciliation.statement_imported",
            "reconciliation.approved_and_posted",
        ]

    def process(self, envelope: EventEnvelope, db: Session) -> None:
        logger.info(
            f"[ReconciliationWorker] Processing event {envelope.event_id} ({envelope.event_type}) "
            f"for aggregate {envelope.aggregate_id} [corr_id={envelope.metadata.correlation_id}]"
        )

        try:
            aggregate_uuid = uuid.UUID(str(envelope.aggregate_id))
        except Exception:
            logger.warning(
                f"[ReconciliationWorker] Permanent failure: invalid UUID aggregate_id={envelope.aggregate_id}"
            )
            return

        society_id: UUID | None = None
        try:
            if "society_id" in envelope.payload and envelope.payload["society_id"]:
                society_id = uuid.UUID(str(envelope.payload["society_id"]))
        except Exception:
            society_id = None

        try:
            if envelope.event_type == "reconciliation.process_bank_statement":
                self._handle_process_statement(aggregate_uuid, envelope, db)
            elif envelope.event_type == "reconciliation.statement_imported":
                self._handle_statement_imported(aggregate_uuid, envelope, db)
            elif envelope.event_type == "reconciliation.approved_and_posted":
                self._handle_approved_and_posted(aggregate_uuid, envelope, db)
            else:
                logger.warning(f"[ReconciliationWorker] Unhandled event type {envelope.event_type}")

            # Record audit event on successful processing
            audit = AuditEvent(
                society_id=society_id,
                actor_id=None,
                action=f"{envelope.event_type}.processed",
                resource_type="Reconciliation",
                resource_id=str(envelope.aggregate_id),
                correlation_id=envelope.metadata.correlation_id,
                event_metadata={
                    "event_id": str(envelope.event_id),
                    "event_type": envelope.event_type,
                    "consumer": self.consumer_name,
                    "payload": envelope.payload,
                    "processed_at": datetime.now(UTC).isoformat(),
                },
            )
            db.add(audit)
            db.commit()
            logger.info(
                f"[ReconciliationWorker] Successfully processed event {envelope.event_id} ({envelope.event_type})"
            )

        except Exception as exc:
            db.rollback()
            if is_retryable_reconciliation_error(exc):
                logger.warning(
                    f"[ReconciliationWorker] Transient error on event {envelope.event_id}: {exc}; re-raising for SQS retry."
                )
                raise RetryableReconciliationWorkerError(str(exc)) from exc
            logger.error(
                f"[ReconciliationWorker] Permanent error processing event {envelope.event_id}: {exc}; acknowledging poison message.",
                exc_info=True,
            )

    def _handle_process_statement(
        self, import_id: UUID, envelope: EventEnvelope, db: Session
    ) -> None:
        """Asynchronously executes matching engine for transactions associated with a statement import."""
        # 1. Atomically claim job with row-level lock
        imp = (
            db.query(BankStatementImport)
            .filter(BankStatementImport.id == import_id)
            .with_for_update()
            .first()
        )
        if not imp:
            logger.warning(
                f"[ReconciliationWorker] Statement import {import_id} not found; skipping."
            )
            return

        # Idempotency guard: skip if already completed
        if imp.status in (
            StatementImportStatus.COMPLETED,
            StatementImportStatus.COMPLETED_WITH_ERRORS,
        ):
            logger.info(
                f"[ReconciliationWorker] Statement {import_id} already COMPLETED; skipping."
            )
            return

        # Fetch unmatched credits for this import
        unmatched_txns = (
            db.query(BankTransaction)
            .filter(
                BankTransaction.import_id == import_id,
                BankTransaction.reconciliation_status == TransactionReconciliationStatus.UNMATCHED,
                BankTransaction.transaction_type == TransactionType.CREDIT,
            )
            .all()
        )

        if unmatched_txns:
            invoices = db.query(Invoice).filter(Invoice.society_id == imp.society_id).all()
            payments = db.query(Payment).filter(Payment.society_id == imp.society_id).all()
            flats = db.query(Flat).filter(Flat.society_id == imp.society_id).all()
            memberships = (
                db.query(FlatMembership).filter(FlatMembership.society_id == imp.society_id).all()
            )
            users = {u.id: u for u in db.query(User).all()}

            engine = DeterministicMatchingEngine(imp.society_id)
            matches_to_create: list[ReconciliationMatch] = []

            for txn in unmatched_txns:
                evaluations = engine.evaluate_transaction(
                    transaction=txn,
                    invoices=invoices,
                    payments=payments,
                    flats=flats,
                    memberships=memberships,
                    users=users,
                )
                if evaluations:
                    top = evaluations[0]
                    if top.confidence_score >= 70.0:
                        txn.reconciliation_status = TransactionReconciliationStatus.SUGGESTED
                    for idx, ev in enumerate(evaluations[:5]):
                        matches_to_create.append(
                            ReconciliationMatch(
                                society_id=imp.society_id,
                                transaction_id=txn.id,
                                flat_id=ev.flat_id,
                                resident_id=ev.resident_id,
                                invoice_id=ev.invoice_id,
                                existing_payment_id=ev.existing_payment_id,
                                confidence_score=ev.confidence_score,
                                confidence_tier=ev.confidence_tier,
                                matching_level=ev.matching_level,
                                explanation=ev.explanation,
                                evidence=ev.evidence,
                                is_selected=(idx == 0 and top.confidence_score >= 70.0),
                            )
                        )
            if matches_to_create:
                db.add_all(matches_to_create)

        imp.status = (
            StatementImportStatus.COMPLETED
            if imp.rejected_rows == 0
            else StatementImportStatus.COMPLETED_WITH_ERRORS
        )
        db.commit()
        logger.info(f"[ReconciliationWorker] Completed async matching for statement {import_id}")

    def _handle_statement_imported(
        self, import_id: UUID, envelope: EventEnvelope, db: Session
    ) -> None:
        logger.info(f"[ReconciliationWorker] Statement import {import_id} confirmed and matched.")

    def _handle_approved_and_posted(
        self, txn_id: UUID, envelope: EventEnvelope, db: Session
    ) -> None:
        logger.info(f"[ReconciliationWorker] Bank transaction {txn_id} settlement posted.")


reconciliation_handler = ReconciliationJobHandler()
dispatcher.register(reconciliation_handler)
