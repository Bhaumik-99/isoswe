"""Application Configuration

Loaded from environment variables with strong validation and fail-closed security rules.
"""

from typing import Literal

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment
    ENVIRONMENT: Literal["development", "staging", "production", "test"] = "development"
    LOG_LEVEL: str = "INFO"
    APP_NAME: str = "Township Operations Platform"
    APP_VERSION: str = "0.1.0"

    # Security & CORS
    SECRET_KEY: str = Field(default="dev-secret-key-change-in-production-must-be-32-bytes-long!")
    CORS_ALLOWED_ORIGINS: list[str] | str = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ]

    @field_validator("CORS_ALLOWED_ORIGINS", mode="after")
    @classmethod
    def assemble_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            if v.startswith("[") and v.endswith("]"):
                import json

                try:
                    loaded = json.loads(v)
                    if isinstance(loaded, list):
                        return [str(x) for x in loaded]
                except Exception:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        elif isinstance(v, list):
            return [str(x) for x in v]
        return []

    # Local Auth Bypass - strictly prohibited in staging and production
    ENABLE_LOCAL_AUTH_BYPASS: bool = False

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/township_ops",
        description="SQLAlchemy-compatible PostgreSQL connection URL",
    )
    TEST_DATABASE_URL: str | None = None
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    # AWS
    AWS_REGION: str = "ap-south-1"
    AWS_ACCOUNT_ID: str = ""

    # Amazon Cognito
    COGNITO_USER_POOL_ID: str = ""
    COGNITO_APP_CLIENT_ID: str = ""
    COGNITO_JWKS_URL: str = ""

    # SQS Queue URLs
    SQS_BILLING_JOBS_QUEUE_URL: str = ""
    SQS_PAYMENT_EVENTS_QUEUE_URL: str = ""
    SQS_RECONCILIATION_JOBS_QUEUE_URL: str = ""
    SQS_COMPLAINT_AI_JOBS_QUEUE_URL: str = ""
    SQS_NOTIFICATION_JOBS_QUEUE_URL: str = ""

    # Messaging Provider: "local" (in-memory/file/db for dev) or "aws" (real SQS)
    MESSAGING_PROVIDER: Literal["local", "aws"] = "local"

    # Outbox Worker Configuration
    OUTBOX_POLL_INTERVAL_SECONDS: float = 2.0
    OUTBOX_BATCH_SIZE: int = 50
    OUTBOX_MAX_RETRIES: int = 5

    @field_validator("ENABLE_LOCAL_AUTH_BYPASS")
    @classmethod
    def validate_local_auth_bypass(cls, v: bool, info: ValidationInfo) -> bool:
        """Fail-closed check: Local auth bypass MUST NEVER be enabled in staging or production."""
        env = info.data.get("ENVIRONMENT", "development")
        if v and env in ("staging", "production"):
            raise ValueError(
                f"SECURITY VIOLATION: ENABLE_LOCAL_AUTH_BYPASS cannot be True in '{env}' environment."
            )
        return v

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def is_local_dev(self) -> bool:
        return self.ENVIRONMENT in ("development", "test")


settings = Settings()
