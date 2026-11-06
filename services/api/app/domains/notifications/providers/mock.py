"""Deterministic Mock Notification Providers

Used in local development, testing, and unconfigured environments.
CRITICAL INVARIANT: The mock provider records dispatch attempts in memory for testing,
but never represents a successful external delivery (returns SUPPRESSED or FAILED).
"""

from typing import Any

from app.core.logging import logger
from app.domains.notifications.models import DeliveryStatus
from app.domains.notifications.providers.base import (
    EmailProvider,
    NotificationResult,
    SMSProvider,
    mask_email,
    mask_phone,
)


class MockEmailProvider(EmailProvider):
    """Deterministic in-memory mock email provider."""

    def __init__(self) -> None:
        self.dispatches: list[dict[str, Any]] = []
        self.simulate_failure: bool = False
        self.simulated_error_code: str = "SIMULATED_TRANSIENT_ERROR"
        self.simulated_is_transient: bool = True

    @property
    def provider_name(self) -> str:
        return "mock_email"

    def reset(self) -> None:
        self.dispatches.clear()
        self.simulate_failure = False

    def send_email(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
        idempotency_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> NotificationResult:
        masked = mask_email(to_email)
        record = {
            "to_email": to_email,
            "masked_email": masked,
            "subject": subject,
            "body_text": body_text,
            "body_html": body_html,
            "idempotency_key": idempotency_key,
            "metadata": metadata or {},
        }
        self.dispatches.append(record)

        if self.simulate_failure:
            logger.warning(
                f"[MockEmail] Simulating external failure for {masked}: {self.simulated_error_code}"
            )
            return NotificationResult(
                status=DeliveryStatus.FAILED,
                provider=self.provider_name,
                error_code=self.simulated_error_code,
                error_message="Simulated mock email failure",
                is_transient=self.simulated_is_transient,
            )

        logger.info(
            f"[MockEmail] Recorded mock email dispatch to {masked} (subject='{subject[:30]}...'). Status: SUPPRESSED (external delivery disabled)"
        )
        return NotificationResult(
            status=DeliveryStatus.SUPPRESSED,
            provider=self.provider_name,
            provider_reference=f"mock-email-{len(self.dispatches)}",
            error_code="MOCK_PROVIDER_EXTERNAL_DELIVERY_DISABLED",
            error_message="Mock provider recorded dispatch but external delivery is intentionally not executed",
            is_transient=False,
        )


class MockSMSProvider(SMSProvider):
    """Deterministic in-memory mock SMS provider."""

    def __init__(self) -> None:
        self.dispatches: list[dict[str, Any]] = []
        self.simulate_failure: bool = False
        self.simulated_error_code: str = "SIMULATED_TRANSIENT_ERROR"
        self.simulated_is_transient: bool = True

    @property
    def provider_name(self) -> str:
        return "mock_sms"

    def reset(self) -> None:
        self.dispatches.clear()
        self.simulate_failure = False

    def send_sms(
        self,
        to_phone: str,
        message: str,
        idempotency_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> NotificationResult:
        masked = mask_phone(to_phone)
        record = {
            "to_phone": to_phone,
            "masked_phone": masked,
            "message": message,
            "idempotency_key": idempotency_key,
            "metadata": metadata or {},
        }
        self.dispatches.append(record)

        if self.simulate_failure:
            logger.warning(
                f"[MockSMS] Simulating external failure for {masked}: {self.simulated_error_code}"
            )
            return NotificationResult(
                status=DeliveryStatus.FAILED,
                provider=self.provider_name,
                error_code=self.simulated_error_code,
                error_message="Simulated mock SMS failure",
                is_transient=self.simulated_is_transient,
            )

        logger.info(
            f"[MockSMS] Recorded mock SMS dispatch to {masked} (len={len(message)} chars). Status: SUPPRESSED (external delivery disabled)"
        )
        return NotificationResult(
            status=DeliveryStatus.SUPPRESSED,
            provider=self.provider_name,
            provider_reference=f"mock-sms-{len(self.dispatches)}",
            error_code="MOCK_PROVIDER_EXTERNAL_DELIVERY_DISABLED",
            error_message="Mock provider recorded dispatch but external delivery is intentionally not executed",
            is_transient=False,
        )
