"""AWS SES Production-Capable Email Provider Adapter"""

from typing import Any

from app.core.config import settings
from app.core.logging import logger
from app.domains.notifications.models import DeliveryStatus
from app.domains.notifications.providers.base import (
    EmailProvider,
    NotificationResult,
    mask_email,
)


class SESEmailProvider(EmailProvider):
    """Production AWS Simple Email Service (SES) provider adapter."""

    def __init__(
        self,
        sender_email: str | None = None,
        region_name: str | None = None,
    ) -> None:
        self.sender_email = sender_email or getattr(
            settings, "NOTIFICATION_SES_SENDER_EMAIL", "notifications@township-ops.internal"
        )
        self.region_name = region_name or getattr(settings, "AWS_REGION", "ap-south-1")
        self._client = None

    @property
    def provider_name(self) -> str:
        return "aws_ses"

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("ses", region_name=self.region_name)
        return self._client

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
        try:
            client = self._get_client()
            body_dict: dict[str, Any] = {"Text": {"Data": body_text, "Charset": "UTF-8"}}
            if body_html:
                body_dict["Html"] = {"Data": body_html, "Charset": "UTF-8"}

            response = client.send_email(
                Source=self.sender_email,
                Destination={"ToAddresses": [to_email]},
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": body_dict,
                },
            )
            msg_id = response.get("MessageId", "unknown-ses-id")
            logger.info(
                f"[SESProvider] Email accepted by AWS SES for {masked}. MessageId: {msg_id}"
            )
            return NotificationResult(
                status=DeliveryStatus.SENT,
                provider=self.provider_name,
                provider_message_id=msg_id,
                provider_reference=msg_id,
            )

        except Exception as exc:
            error_str = str(exc)
            error_code = "SES_DISPATCH_ERROR"
            is_transient = True

            resp = getattr(exc, "response", None)
            if isinstance(resp, dict):
                error_code = resp.get("Error", {}).get("Code", "SES_CLIENT_ERROR")
                # Permanent failure classification
                if error_code in (
                    "MessageRejected",
                    "InvalidParameterValue",
                    "MailFromDomainNotVerifiedException",
                    "AccountSendingPausedException",
                ):
                    is_transient = False

            logger.error(
                f"[SESProvider] Failed to dispatch email to {masked}: [{error_code}] {error_str}"
            )
            return NotificationResult(
                status=DeliveryStatus.FAILED,
                provider=self.provider_name,
                error_code=error_code,
                error_message=error_str[:500],
                is_transient=is_transient,
            )
