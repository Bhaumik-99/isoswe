"""Correlation ID and Request Tracing Middleware

Ensures every inbound request is tagged with:
- X-Request-ID: Unique per HTTP invocation
- X-Correlation-ID: Propagated across distributed service hops or generated afresh

Attaches IDs to request state and injects them into response headers.
"""

import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Request ID: Always unique to this specific HTTP transaction
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        # Correlation ID: Preserves end-to-end distributed transaction tracing
        correlation_id = request.headers.get("X-Correlation-ID") or request_id
        request.state.correlation_id = correlation_id

        # Process the request
        response = await call_next(request)

        # Inject into response headers for observability
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = correlation_id

        return response
