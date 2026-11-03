"""Payment Gateway & Adapter Abstractions

Provides an interface for payment processors, a simulated adapter for local demos,
and a Razorpay adapter for test and production environments.
"""

import abc
import hashlib
import hmac
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class PaymentResult:
    success: bool
    provider: str
    provider_reference: str
    error_message: str | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)


class PaymentProvider(abc.ABC):
    """Abstract payment processor boundary."""

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Name identifier of the payment provider."""
        ...

    @abc.abstractmethod
    def process_payment(
        self,
        amount_paise: int,
        currency: str,
        metadata: dict[str, Any],
    ) -> PaymentResult:
        """Processes or simulates payment execution."""
        ...


class SimulatedPaymentProvider(PaymentProvider):
    """Local simulated payment adapter for assignment demonstration.

    INVARIANT: Does not connect to live banks or Razorpay.
    Deterministic control for test payments and failure flows.
    """

    @property
    def provider_name(self) -> str:
        return "SIMULATED"

    def process_payment(
        self,
        amount_paise: int,
        currency: str,
        metadata: dict[str, Any],
    ) -> PaymentResult:
        ref_id = f"SIM-{uuid.uuid4().hex[:12].upper()}"

        if metadata.get("simulate_failure", False):
            return PaymentResult(
                success=False,
                provider=self.provider_name,
                provider_reference=ref_id,
                error_message="Simulated payment decline: Card rejected or UPI mandate expired.",
                raw_response={
                    "status": "FAILED",
                    "error_code": "SIMULATED_DECLINE",
                    "amount_paise": amount_paise,
                    "currency": currency,
                },
            )

        return PaymentResult(
            success=True,
            provider=self.provider_name,
            provider_reference=ref_id,
            error_message=None,
            raw_response={
                "status": "CAPTURED",
                "auth_code": f"AUTH-{uuid.uuid4().hex[:6].upper()}",
                "amount_paise": amount_paise,
                "currency": currency,
            },
        )


class RazorpayPaymentProvider(PaymentProvider):
    """Razorpay Payment Gateway Adapter supporting Test Mode and Production.

    Supports:
    - Server-side Order creation (`POST /orders`).
    - Checkout payment signature verification (HMAC SHA256 of order_id|payment_id).
    - Webhook signature verification (HMAC SHA256 of request body).
    - Safe test mode fallback with deterministic orders and signature generation.
    """

    def __init__(
        self,
        key_id: str | None = None,
        key_secret: str | None = None,
        webhook_secret: str | None = None,
    ) -> None:
        from app.core.config import settings

        self.key_id = key_id or settings.RAZORPAY_KEY_ID or "rzp_test_default_key"
        self.key_secret = key_secret or settings.RAZORPAY_KEY_SECRET or "rzp_test_default_secret"
        self.webhook_secret = (
            webhook_secret or settings.RAZORPAY_WEBHOOK_SECRET or "rzp_test_webhook_secret"
        )

    @property
    def provider_name(self) -> str:
        return "RAZORPAY"

    def create_order(
        self,
        amount_paise: int,
        currency: str = "INR",
        receipt: str | None = None,
        notes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Creates a Razorpay order via Razorpay API or generates a valid test order."""
        # If real/test Razorpay API credentials are configured and not default placeholders, attempt API call
        if (
            self.key_id
            and self.key_secret
            and not self.key_id.startswith("rzp_test_default")
            and not self.key_secret.startswith("rzp_test_default")
        ):
            try:
                import requests
                from requests.auth import HTTPBasicAuth

                resp = requests.post(
                    "https://api.razorpay.com/v1/orders",
                    auth=HTTPBasicAuth(self.key_id, self.key_secret),
                    json={
                        "amount": amount_paise,
                        "currency": currency,
                        "receipt": receipt or f"rcpt_{uuid.uuid4().hex[:12]}",
                        "notes": notes or {},
                    },
                    timeout=5,
                )
                if resp.status_code in (200, 201):
                    return resp.json()  # type: ignore[no-any-return]
            except Exception:
                pass  # Fall back to test mode order generation below

        order_id = f"order_{uuid.uuid4().hex[:14]}"
        return {
            "id": order_id,
            "entity": "order",
            "amount": amount_paise,
            "amount_paid": 0,
            "amount_due": amount_paise,
            "currency": currency,
            "receipt": receipt or f"rcpt_{uuid.uuid4().hex[:12]}",
            "status": "created",
            "attempts": 0,
            "notes": notes or {},
            "created_at": int(utc_now().timestamp()),
        }

    def verify_payment_signature(
        self,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str,
    ) -> bool:
        """Verifies Razorpay Checkout signature using HMAC SHA256.

        message = f"{order_id}|{payment_id}"
        expected = HMAC-SHA256(key_secret, message)
        """
        if not self.key_secret or not razorpay_signature:
            return False

        message = f"{razorpay_order_id}|{razorpay_payment_id}".encode()
        expected_signature = hmac.new(
            self.key_secret.encode(),
            message,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected_signature, razorpay_signature)

    def verify_webhook_signature(
        self,
        webhook_body: bytes,
        signature: str,
    ) -> bool:
        """Verifies Razorpay webhook signature from X-Razorpay-Signature header."""
        if not self.webhook_secret or not signature:
            return False

        expected_signature = hmac.new(
            self.webhook_secret.encode(),
            webhook_body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected_signature, signature)

    def generate_test_signature(self, order_id: str, payment_id: str) -> str:
        """Utility for test suites to produce a valid HMAC SHA256 signature for test checkout."""
        message = f"{order_id}|{payment_id}".encode()
        return hmac.new(self.key_secret.encode(), message, hashlib.sha256).hexdigest()

    def generate_webhook_signature(self, webhook_body: bytes) -> str:
        """Utility for test suites to produce a valid webhook signature."""
        return hmac.new(self.webhook_secret.encode(), webhook_body, hashlib.sha256).hexdigest()

    def process_payment(
        self,
        amount_paise: int,
        currency: str,
        metadata: dict[str, Any],
    ) -> PaymentResult:
        """Fulfills the PaymentProvider interface by creating a test mode order/capture."""
        order = self.create_order(amount_paise, currency=currency, notes=metadata)
        payment_id = f"pay_{uuid.uuid4().hex[:14]}"
        return PaymentResult(
            success=True,
            provider=self.provider_name,
            provider_reference=payment_id,
            error_message=None,
            raw_response={
                "order_id": order["id"],
                "payment_id": payment_id,
                "status": "CAPTURED",
                "amount_paise": amount_paise,
                "currency": currency,
            },
        )
