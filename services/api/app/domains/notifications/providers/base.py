"""Notification Provider Abstract Interfaces and Result Types"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.domains.notifications.models import DeliveryStatus


def mask_email(email: str | None) -> str:
    """Sanitizes email for logs: user@example.com -> u***r@example.com"""
    if not email or "@" not in email:
        return "***@***"
    user_part, domain = email.split("@", 1)
    if len(user_part) <= 2:
        masked_user = user_part[0] + "*"
    else:
        masked_user = user_part[0] + "*" * (len(user_part) - 2) + user_part[-1]
    return f"{masked_user}@{domain}"


def mask_phone(phone: str | None) -> str:
    """Sanitizes phone for logs: +919876543210 -> +91-XXXXX-XX210"""
    if not phone:
        return "+XX-XXXXX-XXXXX"
    clean = phone.strip()
    if len(clean) >= 10:
        prefix = clean[:3]
        suffix = clean[-3:]
        return f"{prefix}-XXXXX-XX{suffix}"
    return "+XX-XXXXX-XXXXX"


@dataclass
class NotificationResult:
    """Outcome of an external provider dispatch attempt."""

    status: DeliveryStatus
    provider: str
    provider_message_id: str | None = None
    provider_reference: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    is_transient: bool = False


class EmailProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @abstractmethod
    def send_email(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
        idempotency_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> NotificationResult:
        """Dispatches a transactional email to recipient."""
        pass


class SMSProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @abstractmethod
    def send_sms(
        self,
        to_phone: str,
        message: str,
        idempotency_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> NotificationResult:
        """Dispatches a transactional SMS to recipient."""
        pass
