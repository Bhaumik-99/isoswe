"""Main FastAPI Application Entrypoint

Configures:
- Correlation and Request ID tracking
- Central standardized exception handlers
- Health probes (/health/live, /health/ready)
- Versioned API routing (/api/v1)
- CORS and security policies
"""

import time
import uuid
from typing import Any

from fastapi import Depends, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import AppException, create_error_response
from app.core.logging import logger
from app.middleware.correlation import CorrelationIdMiddleware

START_TIME = time.time()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Multi-tenant Society Operations Platform API - Gated Township, Pune",
    docs_url="/docs" if settings.is_local_dev else None,
    redoc_url="/redoc" if settings.is_local_dev else None,
    openapi_url="/openapi.json" if settings.is_local_dev else None,
)

# 1. Correlation & Tracing Middleware
app.add_middleware(CorrelationIdMiddleware)

# 2. CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Correlation-ID"],
)


# ------------------------------------------------------------------------------
# Central Exception Handlers (Never expose stack traces or raw SQL)
# ------------------------------------------------------------------------------


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    logger.warning(
        f"Handled application exception [{exc.code}] on {request.method} {request.url.path}: {exc.message}"
    )
    return create_error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        request_id=request_id,
        details=exc.details,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    clean_errors = []
    for err in exc.errors():
        clean_errors.append(
            {
                "field": ".".join(str(loc) for loc in err.get("loc", [])),
                "issue": err.get("msg", "Invalid value"),
            }
        )
    logger.info(f"Validation error on {request.method} {request.url.path}: {clean_errors}")
    return create_error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="VALIDATION_ERROR",
        message="The request payload failed structural validation",
        request_id=request_id,
        details={"validation_errors": clean_errors},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    correlation_id = getattr(request.state, "correlation_id", request_id)
    # Log internal error with full traceback on server side
    logger.error(
        f"Unhandled server error on {request.method} {request.url.path} [ReqID: {request_id}, CorrID: {correlation_id}]: {exc}",
        exc_info=True,
    )
    # Never leak stack trace or SQL query details to external client
    return create_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected server error occurred. Please quote the request ID to support.",
        request_id=request_id,
    )


# ------------------------------------------------------------------------------
# Health Check Probes
# ------------------------------------------------------------------------------


@app.get("/health/live", tags=["Health"], status_code=status.HTTP_200_OK)
def liveness_probe(request: Request) -> dict[str, Any]:
    """Checks that the application process is running and accepting HTTP traffic."""
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - START_TIME, 2),
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/health/ready", tags=["Health"], status_code=status.HTTP_200_OK)
def readiness_probe(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    """Checks critical runtime dependencies such as the PostgreSQL database."""
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    db_healthy = False
    try:
        db.execute(text("SELECT 1"))
        db_healthy = True
    except Exception as exc:
        logger.error(f"Readiness check failed database probe: {exc}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": {
                    "code": "SERVICE_UNAVAILABLE",
                    "message": "Database health check failed",
                    "request_id": request_id,
                }
            },
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "ready",
            "database": "healthy" if db_healthy else "unhealthy",
            "version": settings.APP_VERSION,
        },
    )


# ------------------------------------------------------------------------------
# Versioned API Routing
# ------------------------------------------------------------------------------
app.include_router(api_v1_router)
