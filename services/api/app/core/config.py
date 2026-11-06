"""Application Configuration

Loaded from environment variables with strong validation and fail-closed security rules.
"""

import json
import os
from typing import Any, Literal

from pydantic import Field, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment (supports dev/prod aliases and normalizes to canonical names)
    ENVIRONMENT: Literal["development", "staging", "production", "test"] = "development"
    LOG_LEVEL: str = "INFO"
    APP_NAME: str = "Township Operations Platform"
    APP_VERSION: str = "0.1.0"

    @field_validator("ENVIRONMENT", mode="before")
    @classmethod
    def normalize_environment(cls, v: str) -> str:
        if isinstance(v, str):
            mapping = {
                "dev": "development",
                "development": "development",
                "staging": "staging",
                "stage": "staging",
                "prod": "production",
                "production": "production",
                "test": "test",
            }
            return mapping.get(v.lower().strip(), v.lower().strip())
        return v

    # Security & CORS
    SECRET_KEY: str = Field(default="dev-secret-key-change-in-production-must-be-32-bytes-long!")
    # Server-side secret (pepper) keying the HMAC-SHA256 digest of guest pass codes. Required (>= 32
    # characters) in staging/production; supplied via Secrets Manager alongside DATABASE_URL.
    # Development/test fall back to SECRET_KEY so local setups work without extra configuration.
    GUEST_PASS_HMAC_SECRET: str = ""
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

    # Database Connection & Pooling (PgBouncer Transaction Pooler compatible)
    DATABASE_URL: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/township_ops",
        description="SQLAlchemy-compatible PostgreSQL connection URL",
    )
    TEST_DATABASE_URL: str | None = None
    DB_POOL_SIZE: int = 1
    DB_MAX_OVERFLOW: int = 0
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    # Supabase Configuration
    SUPABASE_URL: str = ""
    SUPABASE_JWKS_URL: str = ""
    SUPABASE_JWT_ISSUER: str = ""
    SUPABASE_JWT_AUDIENCE: str = "authenticated"

    # AWS
    AWS_REGION: str = "ap-south-1"
    AWS_ACCOUNT_ID: str = ""
    DATABASE_SECRET_NAME: str = ""
    DATABASE_SECRET_ARN: str = ""

    @model_validator(mode="before")
    @classmethod
    def hydrate_aws_secrets(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        env_raw = data.get("ENVIRONMENT") or os.environ.get("ENVIRONMENT", "development")
        env = cls.normalize_environment(env_raw)

        # Check for Secrets Manager secret ID from data or environment
        secret_id = (
            data.get("DATABASE_SECRET_NAME")
            or data.get("DATABASE_SECRET_ARN")
            or os.environ.get("DATABASE_SECRET_NAME")
            or os.environ.get("DATABASE_SECRET_ARN")
        )
        region = data.get("AWS_REGION") or os.environ.get("AWS_REGION", "ap-south-1")

        if secret_id:
            try:
                import boto3

                client = boto3.client("secretsmanager", region_name=region)
                res = client.get_secret_value(SecretId=secret_id)
                secret_str = res.get("SecretString")
                if secret_str:
                    secret_dict = json.loads(secret_str)
                    for k, val in secret_dict.items():
                        current_val = data.get(k)
                        if val and (
                            not current_val
                            or current_val
                            == "postgresql+psycopg://postgres:postgres@localhost:5432/township_ops"
                        ):
                            data[k] = val
            except Exception as exc:
                if env in ("staging", "production"):
                    raise RuntimeError(
                        f"CRITICAL: Failed to retrieve required secret '{secret_id}' from AWS Secrets Manager in '{env}': {exc}"
                    ) from exc

        # Derive JWKS URL and JWT Issuer if SUPABASE_URL is provided and they are empty
        supabase_url = data.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL", "")
        if supabase_url:
            cleaned_url = supabase_url.rstrip("/")
            if not data.get("SUPABASE_JWKS_URL"):
                data["SUPABASE_JWKS_URL"] = f"{cleaned_url}/auth/v1/.well-known/jwks.json"
            if not data.get("SUPABASE_JWT_ISSUER"):
                data["SUPABASE_JWT_ISSUER"] = f"{cleaned_url}/auth/v1"

        return data

    # SQS Queue URLs
    SQS_BILLING_JOBS_QUEUE_URL: str = ""
    SQS_PAYMENT_EVENTS_QUEUE_URL: str = ""
    SQS_RECONCILIATION_JOBS_QUEUE_URL: str = ""
    SQS_COMPLAINT_AI_JOBS_QUEUE_URL: str = ""
    SQS_NOTIFICATION_JOBS_QUEUE_URL: str = ""

    # Payment Integration (Behind backend adapters)
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""

    # Messaging Provider: "local" (in-memory/file/db for dev) or "aws" (real SQS)
    MESSAGING_PROVIDER: Literal["local", "aws"] = "local"

    # Outbox Worker Configuration
    OUTBOX_POLL_INTERVAL_SECONDS: float = 2.0
    OUTBOX_BATCH_SIZE: int = 50
    OUTBOX_MAX_RETRIES: int = 5

    # AI Triage & Gemini Integration
    AI_PROVIDER: str = "deterministic"
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    AI_TIMEOUT_SECONDS: int = 10
    AI_MAX_RETRIES: int = 1
    AI_ENABLED: bool = True

    # Attachment S3 Storage Configuration
    S3_ATTACHMENTS_BUCKET_NAME: str = ""
    S3_ATTACHMENTS_REGION: str = "ap-south-1"

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

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str, info: ValidationInfo) -> str:
        """Fail-closed check: DATABASE_URL must not point to localhost in staging or production."""
        env = info.data.get("ENVIRONMENT", "development")
        if env in ("staging", "production"):
            if not v or not v.strip():
                raise ValueError(
                    f"SECURITY VIOLATION: DATABASE_URL must be explicitly configured in '{env}'."
                )
            v_lower = v.lower()
            if "localhost" in v_lower or "127.0.0.1" in v_lower:
                raise ValueError(
                    f"SECURITY VIOLATION: DATABASE_URL in '{env}' must point to a production PostgreSQL database (e.g. Supabase pooler), not localhost."
                )
        return v

    @field_validator("SUPABASE_URL")
    @classmethod
    def validate_supabase_url(cls, v: str, info: ValidationInfo) -> str:
        """Fail-closed check: SUPABASE_URL must be a valid HTTPS URL in staging or production."""
        env = info.data.get("ENVIRONMENT", "development")
        if env in ("staging", "production"):
            if not v or not v.strip():
                raise ValueError(
                    f"SECURITY VIOLATION: SUPABASE_URL must be explicitly configured in '{env}'."
                )
            if not v.startswith("https://"):
                raise ValueError(
                    f"SECURITY VIOLATION: SUPABASE_URL in '{env}' must be a secure HTTPS URL, got '{v}'."
                )
        return v

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def is_local_dev(self) -> bool:
        return self.ENVIRONMENT in ("development", "test")


settings = Settings()
