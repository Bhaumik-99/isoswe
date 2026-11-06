"""Notification Provider Registry and Factory"""

import os

from app.core.config import settings
from app.domains.notifications.providers.base import EmailProvider, SMSProvider
from app.domains.notifications.providers.mock import MockEmailProvider, MockSMSProvider
from app.domains.notifications.providers.ses import SESEmailProvider
from app.domains.notifications.providers.sns import SNSSMSProvider


class NotificationProviderRegistry:
    def __init__(self) -> None:
        self._email_provider: EmailProvider | None = None
        self._sms_provider: SMSProvider | None = None

    def get_email_provider(self) -> EmailProvider:
        if self._email_provider is not None:
            return self._email_provider

        provider_type = (
            getattr(settings, "NOTIFICATION_EMAIL_PROVIDER", None)
            or os.environ.get("NOTIFICATION_EMAIL_PROVIDER", "mock")
        ).lower()

        if provider_type in ("ses", "aws_ses"):
            self._email_provider = SESEmailProvider()
        else:
            self._email_provider = MockEmailProvider()

        return self._email_provider

    def set_email_provider(self, provider: EmailProvider) -> None:
        self._email_provider = provider

    def get_sms_provider(self) -> SMSProvider:
        if self._sms_provider is not None:
            return self._sms_provider

        provider_type = (
            getattr(settings, "NOTIFICATION_SMS_PROVIDER", None)
            or os.environ.get("NOTIFICATION_SMS_PROVIDER", "mock")
        ).lower()

        if provider_type in ("sns", "aws_sns"):
            self._sms_provider = SNSSMSProvider()
        else:
            self._sms_provider = MockSMSProvider()

        return self._sms_provider

    def set_sms_provider(self, provider: SMSProvider) -> None:
        self._sms_provider = provider

    def reset(self) -> None:
        self._email_provider = None
        self._sms_provider = None


provider_registry = NotificationProviderRegistry()
