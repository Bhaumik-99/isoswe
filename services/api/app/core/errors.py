"""Standardized Error Responses and Domain Exceptions

Enforces uniform API error contracts:
{
  "error": {
    "code": "ERROR_CODE",
    "message": "User-friendly description",
    "request_id": "uuid"
  }
}
Never exposes stack traces, internal SQL statements, or sensitive credentials.
"""

from typing import Any

from fastapi import status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str = Field(description="Machine-readable uppercase error code")
    message: str = Field(description="Sanitized human-readable error description")
    request_id: str = Field(description="Traceable unique request identifier")
    details: dict[str, Any] | None = Field(
        default=None, description="Optional non-sensitive validation details"
    )


class StandardErrorResponse(BaseModel):
    error: ErrorDetail


class AppException(Exception):
    """Base exception for application and domain errors."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


class AuthenticationError(AppException):
    def __init__(
        self,
        message: str = "Authentication required or credentials invalid",
        code: str = "UNAUTHORIZED",
    ):
        super().__init__(code=code, message=message, status_code=status.HTTP_401_UNAUTHORIZED)


class AuthorizationError(AppException):
    def __init__(
        self,
        message: str = "You are not authorised to access this resource",
        code: str = "FORBIDDEN",
    ):
        super().__init__(code=code, message=message, status_code=status.HTTP_403_FORBIDDEN)


class ResourceNotFoundError(AppException):
    def __init__(
        self, message: str = "The requested resource was not found", code: str = "NOT_FOUND"
    ):
        super().__init__(code=code, message=message, status_code=status.HTTP_404_NOT_FOUND)


class ConflictError(AppException):
    def __init__(self, message: str = "Resource conflict occurred", code: str = "CONFLICT"):
        super().__init__(code=code, message=message, status_code=status.HTTP_409_CONFLICT)


class TenantIsolationError(AuthorizationError):
    def __init__(self, message: str = "Cross-society or cross-flat access violation"):
        super().__init__(message=message, code="CROSS_TENANT_ACCESS_DENIED")


def create_error_response(
    status_code: int,
    code: str,
    message: str,
    request_id: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    """Creates a standardized JSON error response."""
    error_content: dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": request_id,
    }
    if details:
        error_content["details"] = details
    return JSONResponse(status_code=status_code, content={"error": error_content})
