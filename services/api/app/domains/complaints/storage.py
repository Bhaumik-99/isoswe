"""Complaints Attachment Storage Abstraction

Provides private object storage capabilities for resident complaint attachments:
- StorageProvider interface
- MockStorageProvider for local development & automated test suites
- S3StorageProvider for production & staging AWS deployments
- Secure randomized key generation, metadata verification, and content validation

SECURITY INVARIANTS:
- Private bucket access only; never expose public S3 URLs
- Presigned upload & download URLs with limited expiration (1 hour)
- Strictly validate allowed MIME types (JPEG, PNG, WebP) and max size (5MB)
- Random UUID-based object keys to eliminate IDOR and key enumeration
- Fail closed in production: if S3 is unconfigured, do not silently fallback to mock
- Two-phase upload: Verify object existence, actual size, and content-type before completing attachment
"""

import abc
import os
import uuid
from typing import Any

from app.core.config import settings
from app.core.errors import ValidationError

ALLOWED_MIME_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


class StorageProvider(abc.ABC):
    @abc.abstractmethod
    def generate_upload_url(
        self,
        storage_key: str,
        content_type: str,
        expires_in_seconds: int = 3600,
        expected_size: int | None = None,
    ) -> str:
        """Generates a secure presigned upload URL for client-side direct upload."""
        ...

    @abc.abstractmethod
    def generate_download_url(self, storage_key: str, expires_in_seconds: int = 3600) -> str:
        """Generates a secure presigned download URL for authorized viewing."""
        ...

    @abc.abstractmethod
    def verify_object_exists(self, storage_key: str) -> bool:
        """Verifies that the object actually exists in the backing storage."""
        ...

    @abc.abstractmethod
    def verify_object_metadata(
        self, storage_key: str, expected_size: int, expected_content_type: str
    ) -> tuple[bool, str | None]:
        """Verifies that the object exists in storage and matches size and content type constraints."""
        ...

    @abc.abstractmethod
    def delete_object(self, storage_key: str) -> bool:
        """Deletes an object from storage."""
        ...

    @abc.abstractmethod
    def validate_image_bytes(self, storage_key: str, content_type: str) -> tuple[bool, str | None]:
        """Downloads the minimum leading bytes of the object and verifies that they match
        the magic signature for the declared content_type (JPEG, PNG, or WebP).

        Returns (True, None) on a valid match, (False, reason) on mismatch or error.
        In the MockStorageProvider this check is skipped (always passes when the key exists)
        because mock storage does not hold real byte payloads.
        """
        ...


class MockStorageProvider(StorageProvider):
    """Local mock storage provider for deterministic local testing."""

    def __init__(self) -> None:
        self._stored_keys: set[str] = set()
        self._stored_metadata: dict[str, dict[str, Any]] = {}

    def generate_upload_url(
        self,
        storage_key: str,
        content_type: str,
        expires_in_seconds: int = 3600,
        expected_size: int | None = None,
    ) -> str:
        self._stored_keys.add(storage_key)
        self._stored_metadata[storage_key] = {
            "size": expected_size,
            "content_type": content_type,
        }
        return f"https://mock-storage.local/upload/{storage_key}?expires={expires_in_seconds}&content_type={content_type}"

    def generate_download_url(self, storage_key: str, expires_in_seconds: int = 3600) -> str:
        return f"https://mock-storage.local/download/{storage_key}?expires={expires_in_seconds}"

    def verify_object_exists(self, storage_key: str) -> bool:
        return storage_key in self._stored_keys

    def verify_object_metadata(
        self, storage_key: str, expected_size: int, expected_content_type: str
    ) -> tuple[bool, str | None]:
        if storage_key not in self._stored_keys:
            return False, "Object not found in storage"
        meta = self._stored_metadata.get(storage_key)
        if meta:
            actual_size = meta.get("size")
            actual_type = meta.get("content_type")

            if actual_size is not None and actual_size <= 0:
                return False, "Uploaded file object is empty (0 bytes)"

            if actual_size is not None and actual_size > MAX_FILE_SIZE_BYTES:
                return (
                    False,
                    f"Uploaded file size ({actual_size} bytes) exceeds maximum limit of 5MB",
                )

            if (
                actual_size is not None
                and expected_size is not None
                and actual_size != expected_size
            ):
                return (
                    False,
                    f"Size mismatch: expected {expected_size} bytes, got {actual_size} bytes",
                )

            if not actual_type or not str(actual_type).strip():
                return False, "Storage object missing ContentType metadata"

            clean_actual = str(actual_type).split(";")[0].strip().lower()
            clean_expected = expected_content_type.strip().lower()
            if clean_actual != clean_expected and not (
                clean_actual == "image/jpeg" and clean_expected == "image/jpg"
            ):
                return (
                    False,
                    f"Content type mismatch: expected {expected_content_type}, got {actual_type}",
                )
        return True, None

    def delete_object(self, storage_key: str) -> bool:
        self._stored_keys.discard(storage_key)
        self._stored_metadata.pop(storage_key, None)
        return True

    def validate_image_bytes(self, storage_key: str, content_type: str) -> tuple[bool, str | None]:
        # Mock storage does not hold real byte payloads; skip byte-level check.
        # Validation passes as long as the key was registered (i.e. upload was initiated).
        if storage_key not in self._stored_keys:
            return False, "Object not found in mock storage"
        return True, None


_default_mock_storage = MockStorageProvider()


class S3StorageProvider(StorageProvider):
    """AWS S3 Storage Provider using boto3 presigned URLs."""

    def __init__(self, bucket_name: str | None = None) -> None:
        self.bucket_name = (
            bucket_name
            or getattr(settings, "S3_ATTACHMENTS_BUCKET_NAME", None)
            or os.environ.get("COMPLAINTS_BUCKET_NAME", "township-ops-complaints-attachments")
        )
        try:
            import boto3

            self.s3_client: Any = boto3.client("s3", region_name=settings.AWS_REGION)
        except Exception:
            self.s3_client = None

    def generate_upload_url(
        self,
        storage_key: str,
        content_type: str,
        expires_in_seconds: int = 3600,
        expected_size: int | None = None,
    ) -> str:
        if not self.s3_client:
            if settings.ENVIRONMENT in ("production", "staging"):
                raise RuntimeError(
                    "CRITICAL: S3 client is uninitialized in production/staging environment."
                )
            return _default_mock_storage.generate_upload_url(
                storage_key, content_type, expires_in_seconds, expected_size
            )
        return str(
            self.s3_client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": storage_key,
                    "ContentType": content_type,
                },
                ExpiresIn=expires_in_seconds,
            )
        )

    def generate_download_url(self, storage_key: str, expires_in_seconds: int = 3600) -> str:
        if not self.s3_client:
            if settings.ENVIRONMENT in ("production", "staging"):
                raise RuntimeError(
                    "CRITICAL: S3 client is uninitialized in production/staging environment."
                )
            return _default_mock_storage.generate_download_url(storage_key, expires_in_seconds)
        return str(
            self.s3_client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": storage_key,
                },
                ExpiresIn=expires_in_seconds,
            )
        )

    def verify_object_exists(self, storage_key: str) -> bool:
        if not self.s3_client:
            if settings.ENVIRONMENT in ("production", "staging"):
                raise RuntimeError(
                    "CRITICAL: S3 client is uninitialized in production/staging environment."
                )
            return True
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=storage_key)
            return True
        except Exception:
            return False

    def verify_object_metadata(
        self, storage_key: str, expected_size: int, expected_content_type: str
    ) -> tuple[bool, str | None]:
        if not self.s3_client:
            if settings.ENVIRONMENT in ("production", "staging"):
                raise RuntimeError(
                    "CRITICAL: S3 client is uninitialized in production/staging environment."
                )
            return True, None
        try:
            head = self.s3_client.head_object(Bucket=self.bucket_name, Key=storage_key)
            actual_size = head.get("ContentLength", 0)
            actual_type = head.get("ContentType", "")

            if actual_size <= 0:
                return False, "Uploaded file object is empty (0 bytes)"

            if actual_size > MAX_FILE_SIZE_BYTES:
                return (
                    False,
                    f"Uploaded file size ({actual_size} bytes) exceeds maximum limit of 5MB",
                )

            if expected_size is not None and actual_size != expected_size:
                return (
                    False,
                    f"Size mismatch: expected {expected_size} bytes, got {actual_size} bytes",
                )

            if not actual_type or not str(actual_type).strip():
                return False, "Storage object missing ContentType metadata"

            clean_actual = str(actual_type).split(";")[0].strip().lower()
            clean_expected = expected_content_type.strip().lower()
            if clean_actual != clean_expected and not (
                clean_actual == "image/jpeg" and clean_expected == "image/jpg"
            ):
                return (
                    False,
                    f"Content-Type mismatch: expected {clean_expected}, but storage object has {clean_actual}",
                )

            return True, None
        except Exception as e:
            return False, f"Storage object verification failed: {e}"

    def delete_object(self, storage_key: str) -> bool:
        if not self.s3_client:
            return True
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=storage_key)
            return True
        except Exception:
            return False

    def validate_image_bytes(self, storage_key: str, content_type: str) -> tuple[bool, str | None]:
        """Fetches the first 12 bytes of the S3 object and verifies magic byte signatures.

        JPEG: FF D8 FF (bytes 0-2)
        PNG:  89 50 4E 47 0D 0A 1A 0A (bytes 0-7)
        WebP: 52 49 46 46 __ __ __ __ 57 45 42 50 (RIFF....WEBP, bytes 0-3 and 8-11)
        """
        _MAGIC: dict[str, list[tuple[int, bytes]]] = {
            "image/jpeg": [(0, b"\xff\xd8\xff")],
            "image/jpg": [(0, b"\xff\xd8\xff")],
            "image/png": [(0, b"\x89PNG\r\n\x1a\n")],
            "image/webp": [(0, b"RIFF"), (8, b"WEBP")],
        }
        if not self.s3_client:
            if settings.ENVIRONMENT in ("production", "staging"):
                raise RuntimeError(
                    "CRITICAL: S3 client is uninitialized; cannot perform image byte validation."
                )
            # Non-production without S3 (e.g. fallback dev) — skip byte check
            return True, None
        try:
            resp = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=storage_key,
                Range="bytes=0-11",
            )
            header: bytes = resp["Body"].read(12)
        except Exception as exc:
            return False, f"Image byte fetch failed: {exc}"

        patterns = _MAGIC.get(content_type.lower(), [])
        if not patterns:
            # Unknown MIME type — cannot validate magic bytes; reject defensively
            return False, f"Unsupported content type for byte validation: {content_type}"

        for offset, magic in patterns:
            end = offset + len(magic)
            if header[offset:end] != magic:
                return (
                    False,
                    f"File bytes do not match declared content type {content_type} "
                    f"(expected {magic.hex()!r} at offset {offset}, "
                    f"got {header[offset:end].hex()!r})",
                )
        return True, None


def get_storage_provider() -> StorageProvider:
    if settings.ENVIRONMENT in ("production", "staging"):
        bucket = getattr(settings, "S3_ATTACHMENTS_BUCKET_NAME", None) or os.environ.get(
            "COMPLAINTS_BUCKET_NAME"
        )
        if not bucket:
            raise RuntimeError(
                "CRITICAL: S3_ATTACHMENTS_BUCKET_NAME must be explicitly configured in production/staging."
            )
        return S3StorageProvider(bucket_name=bucket)
    if settings.is_local_dev or os.environ.get("USE_MOCK_STORAGE", "true").lower() == "true":
        return _default_mock_storage
    return S3StorageProvider()


def validate_attachment_metadata(file_name: str, file_size_bytes: int, content_type: str) -> str:
    """Validates attachment constraints and returns the verified file extension."""
    if content_type not in ALLOWED_MIME_TYPES:
        raise ValidationError(
            f"Unsupported file format '{content_type}'. Allowed types: JPEG, PNG, WebP."
        )

    if file_size_bytes <= 0:
        raise ValidationError("Attachment file size must be greater than zero.")

    if file_size_bytes > MAX_FILE_SIZE_BYTES:
        raise ValidationError(
            f"File size {file_size_bytes / (1024 * 1024):.2f}MB exceeds the maximum 5MB limit."
        )

    expected_ext = ALLOWED_MIME_TYPES[content_type]
    file_ext = os.path.splitext(file_name)[1].lower()
    if file_ext not in [expected_ext, ".jpeg" if expected_ext == ".jpg" else expected_ext]:
        raise ValidationError(
            f"File extension '{file_ext}' does not match MIME type '{content_type}'."
        )

    return expected_ext


def generate_storage_key(society_id: uuid.UUID, complaint_id: uuid.UUID, extension: str) -> str:
    """Produces a secure, unpredictable object path."""
    clean_ext = extension.lstrip(".")
    unique_token = uuid.uuid4().hex
    return f"attachments/{society_id}/{complaint_id}/{unique_token}.{clean_ext}"
