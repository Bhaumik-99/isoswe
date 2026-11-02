"""Event Envelope Schema

Standardized event envelope ensuring strict typing, schema evolution, and auditability.
Sensitive resident or financial credentials must NEVER be placed directly in the payload.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class EventMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    correlation_id: str
    producer: str = "township-ops-api"
    schema_version: str = "1.0"
    environment: str = "development"


class EventEnvelope(BaseModel):
    """Standardized asynchronous event envelope dispatched via Transactional Outbox and SQS."""

    model_config = ConfigDict(extra="ignore")

    event_id: UUID = Field(default_factory=uuid4)
    event_type: str = Field(
        description="Domain dot-notation event type, e.g. platform.health_check"
    )
    aggregate_type: str = Field(description="Aggregate root name, e.g. Society, Flat, Platform")
    aggregate_id: str = Field(description="Identifier of the aggregate")
    timestamp: str = Field(default_factory=utc_now_iso)
    metadata: EventMetadata
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Non-sensitive payload references (IDs, status codes, timestamps)",
    )
