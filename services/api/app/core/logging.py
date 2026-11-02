"""Structured JSON Logging Configuration

Ensures consistent log structures across container and Lambda environments with
contextual correlation IDs and request tracing.
"""

import json
import logging
import sys
from typing import Any

from app.core.config import settings


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter producing machine-readable structured log records."""

    def format(self, record: logging.LogRecord) -> str:
        log_payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "environment": settings.ENVIRONMENT,
        }

        # Contextual tracing attributes
        if hasattr(record, "correlation_id"):
            log_payload["correlation_id"] = record.correlation_id
        if hasattr(record, "request_id"):
            log_payload["request_id"] = record.request_id
        if hasattr(record, "user_id"):
            log_payload["user_id"] = record.user_id
        if hasattr(record, "society_id"):
            log_payload["society_id"] = record.society_id

        # Exception details
        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)

        # Extra data passed in record
        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            log_payload.update(record.extra_data)

        return json.dumps(log_payload, default=str)


def setup_logging() -> logging.Logger:
    """Configures the root and application logger with JSON output."""
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.LOG_LEVEL.upper())

    # Clear existing handlers to avoid duplicates
    root_logger.handlers = []

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root_logger.addHandler(handler)

    # Suppress overly chatty third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    return logging.getLogger("township_ops")


logger = setup_logging()
