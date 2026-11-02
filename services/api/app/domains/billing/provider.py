"""Payment Gateway & Adapter Abstractions

Provides an interface for payment processors and a simulated adapter for local demos.
Enables pluggable integration of Razorpay/UPI in future phases without altering domain logic.
"""

import abc
import uuid
from dataclasses import dataclass, field
from typing import Any


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
