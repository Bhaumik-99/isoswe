"""AWS SNS Production-Capable SMS Provider Adapter"""

from typing import Any

from app.core.config import settings
from app.core.logging import logger
from app.domains.notifications.models import DeliveryStatus
from app.domains.notifications.providers.base import (
    NotificationResult,
    SMSProvider,
    mask_phone,
)


class SNSSMSProvider(SMSProvider):
    """Production AWS Simple Notification Service (SNS) transactional SMS adapter."""

    def __init__(self, region_name: str | None = None) -> None:
        self.region_name = region_name or getattr(settings, "AWS_REGION", "ap-south-1")
        self._client = None

    @property
    def provider_name(self) -> str:
        return "aws_sns"

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("sns", region_name=self.region_name)
        return self._client

    def send_sms(
        self,
        to_phone: str,
        message: str,
        idempotency_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> NotificationResult:
        clean_phone = to_phone.strip()
        if not clean_phone.startswith("+"):
            clean_phone = f"+91{clean_phone}"

        masked = mask_phone(clean_phone)
        try:
            client = self._get_client()
            response = client.publish(
                PhoneNumber=clean_phone,
                Message=message,
                MessageAttributes={
                    "AWS.SNS.SMS.SMSType": {
                        "DataType": "String",
                        "StringValue": "Transactional",
                    }
                },
            )
            msg_id = response.get("MessageId", "unknown-sns-id")
            logger.info(f"[SNSProvider] SMS accepted by AWS SNS for {masked}. MessageId: {msg_id}")
            return NotificationResult(
                status=DeliveryStatus.SENT,
                provider=self.provider_name,
                provider_message_id=msg_id,
                provider_reference=msg_id,
            )

        except Exception as exc:
            error_str = str(exc)
            error_code = "SNS_DISPATCH_ERROR"
            is_transient = True

            resp = getattr(exc, "response", None)
            if isinstance(resp, dict):
                error_code = resp.get("Error", {}).get("Code", "SNS_CLIENT_ERROR")
                if error_code in (
                    "InvalidParameter",
                    "InvalidParameterValue",
                    "OptedOut",
                    "AuthorizationError",
                ):
                    is_transient = False

            logger.error(
                f"[SNSProvider] Failed to dispatch SMS to {masked}: [{error_code}] {error_str}"
            )
            return NotificationResult(
                status=DeliveryStatus.FAILED,
                provider=self.provider_name,
                error_code=error_code,
                error_message=error_str[:500],
                is_transient=is_transient,
            )
