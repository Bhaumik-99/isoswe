"""Unit & Integration Tests for Hardened Visitor Photo Retention Service

Validates:
1. Deletion verification & failure retry preservation (when S3 delete returns False or raises).
2. True capture-time retention evaluation (photo_captured_at vs created_at).
3. Scheduled Lambda retention handler execution.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domains.complaints.storage import S3StorageProvider
from app.domains.visitors.models import (
    ApprovalStatus,
    EntryStatus,
    VisitorPurpose,
    VisitorRecord,
)
from app.domains.visitors.retention_service import (
    PhotoExpiredError,
    PhotoRetentionService,
)
from app.handlers.lambda_retention import handler as retention_handler


def test_purge_preserves_record_for_retry_when_storage_delete_fails(
    db_session: Session,
    gate_environment: dict,
) -> None:
    """When S3 deletion fails (returns False), DB keys MUST NOT be wiped and record MUST remain for retry."""
    now = datetime.now(UTC)
    service = PhotoRetentionService(db_session)

    vid = uuid.uuid4()
    storage_key = service.save_photo_bytes(
        society_id=gate_environment["society_id"],
        visitor_id=vid,
        photo_bytes=b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\xff\xd9",
    )

    record = VisitorRecord(
        id=vid,
        society_id=gate_environment["society_id"],
        gate_id=gate_environment["gate_1_id"],
        visitor_name="Retry Test Visitor",
        phone_number="+919876543210",
        purpose=VisitorPurpose.GUEST,
        destination_tower_id=gate_environment["tower_t07_id"],
        destination_flat_id=gate_environment["flat_1203_id"],
        created_by_user_id=gate_environment["user_neeraj_id"],
        photo_storage_key=storage_key,
        photo_s3_key=storage_key,
        approval_status=ApprovalStatus.APPROVED,
        entry_status=EntryStatus.CHECKED_IN,
        created_at=now - timedelta(days=95),
        updated_at=now - timedelta(days=95),
    )
    db_session.add(record)
    db_session.commit()

    # Mock storage_provider.delete_file to simulate S3 failure (returns False)
    mock_provider = MagicMock()
    mock_provider.delete_file.return_value = False
    service.storage_provider = mock_provider

    purged = service.purge_expired_photos(batch_size=10)
    assert purged == 0

    db_session.expire_all()
    reloaded = db_session.get(VisitorRecord, vid)
    assert reloaded is not None
    assert reloaded.photo_storage_key == storage_key
    assert reloaded.photo_s3_key == storage_key
    assert reloaded.photo_purged_at is None
    assert reloaded.photo_deleted_at is None

    # Now simulate S3 deletion succeeding on next retry cycle
    mock_provider.delete_file.return_value = True
    purged_retry = service.purge_expired_photos(batch_size=10)
    assert purged_retry == 1

    db_session.expire_all()
    reloaded_after_success = db_session.get(VisitorRecord, vid)
    assert reloaded_after_success is not None
    assert reloaded_after_success.photo_storage_key is None
    assert reloaded_after_success.photo_s3_key is None
    assert reloaded_after_success.photo_purged_at is not None
    assert reloaded_after_success.photo_deleted_at is not None


def test_purge_preserves_record_when_storage_delete_raises_exception(
    db_session: Session,
    gate_environment: dict,
) -> None:
    """When S3 deletion raises an unexpected network exception, keys MUST NOT be wiped."""
    now = datetime.now(UTC)
    service = PhotoRetentionService(db_session)

    vid = uuid.uuid4()
    storage_key = f"visitor-photos/{gate_environment['society_id']}/test/{vid}.jpg"
    record = VisitorRecord(
        id=vid,
        society_id=gate_environment["society_id"],
        gate_id=gate_environment["gate_1_id"],
        visitor_name="Exception Test Visitor",
        phone_number="+919876543211",
        purpose=VisitorPurpose.GUEST,
        destination_tower_id=gate_environment["tower_t07_id"],
        destination_flat_id=gate_environment["flat_1203_id"],
        created_by_user_id=gate_environment["user_neeraj_id"],
        photo_storage_key=storage_key,
        photo_s3_key=storage_key,
        approval_status=ApprovalStatus.APPROVED,
        entry_status=EntryStatus.CHECKED_IN,
        created_at=now - timedelta(days=100),
        updated_at=now - timedelta(days=100),
    )
    db_session.add(record)
    db_session.commit()

    mock_provider = MagicMock()
    mock_provider.delete_file.side_effect = RuntimeError("AWS Connection Timeout")
    service.storage_provider = mock_provider

    purged = service.purge_expired_photos(batch_size=10)
    assert purged == 0

    db_session.expire_all()
    reloaded = db_session.get(VisitorRecord, vid)
    assert reloaded is not None
    assert reloaded.photo_storage_key == storage_key
    assert reloaded.photo_purged_at is None


def test_retention_cutoff_respects_actual_photo_capture_time(
    db_session: Session,
    gate_environment: dict,
) -> None:
    """Verifies that retention age is evaluated based on actual capture timestamp (photo_captured_at)."""
    now = datetime.now(UTC)
    service = PhotoRetentionService(db_session)

    # Visitor synchronized 5 days ago, but photograph was captured 95 days ago on an offline tablet
    vid = uuid.uuid4()
    storage_key = f"visitor-photos/{gate_environment['society_id']}/test/{vid}.jpg"
    record = VisitorRecord(
        id=vid,
        society_id=gate_environment["society_id"],
        gate_id=gate_environment["gate_1_id"],
        visitor_name="Delayed Sync Visitor",
        phone_number="+919876543212",
        purpose=VisitorPurpose.GUEST,
        destination_tower_id=gate_environment["tower_t07_id"],
        destination_flat_id=gate_environment["flat_1203_id"],
        created_by_user_id=gate_environment["user_neeraj_id"],
        photo_storage_key=storage_key,
        photo_s3_key=storage_key,
        approval_status=ApprovalStatus.APPROVED,
        entry_status=EntryStatus.CHECKED_IN,
        created_at=now - timedelta(days=5),  # Server sync time is recent
        photo_captured_at=now - timedelta(days=95),  # Actual photo capture time > 90 days
        updated_at=now - timedelta(days=5),
    )
    db_session.add(record)
    db_session.commit()

    # 1. Attempting to get presigned URL should raise PhotoExpiredError (410)
    with pytest.raises(PhotoExpiredError) as exc_info:
        service.get_visitor_photo_presigned_url(
            visitor_id=vid,
            requester_user_id=gate_environment["user_neeraj_id"],
            society_id=gate_environment["society_id"],
            active_flat_ids=[gate_environment["flat_1203_id"]],
        )
    assert exc_info.value.status_code == 410

    # 2. Purge worker should delete based on photo_captured_at
    purged = service.purge_expired_photos(batch_size=10)
    assert purged >= 1

    db_session.expire_all()
    reloaded = db_session.get(VisitorRecord, vid)
    assert reloaded is not None
    assert reloaded.photo_purged_at is not None
    assert reloaded.photo_storage_key is None


def test_lambda_retention_handler_execution(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies that the scheduled AWS Lambda retention handler executes and returns 200 with purgedCount."""
    from contextlib import contextmanager

    @contextmanager
    def mock_session():
        yield db_session

    monkeypatch.setattr("app.handlers.lambda_retention.SessionLocal", mock_session)
    result = retention_handler({}, None)
    assert result["statusCode"] == 200
    assert "purgedCount" in result
    assert isinstance(result["purgedCount"], int)


def test_missing_s3_client_fails_closed_in_production(
    db_session: Session,
    gate_environment: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proves that a missing S3 client in production raises RuntimeError and never results in a successful purge."""
    now = datetime.now(UTC)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "S3_ATTACHMENTS_BUCKET_NAME", "test-production-bucket")

    provider = S3StorageProvider(bucket_name="test-production-bucket")
    provider.s3_client = None

    # Direct call to delete_object must raise RuntimeError (fail-closed)
    with pytest.raises(RuntimeError) as exc_info:
        provider.delete_object("visitor-photos/test/photo.jpg")
    assert "CRITICAL: S3 client is uninitialized in production/staging environment" in str(
        exc_info.value
    )

    # Now verify inside PhotoRetentionService:
    # Expired photo record (>90 days old)
    vid = uuid.uuid4()
    storage_key = f"visitor-photos/{gate_environment['society_id']}/test/{vid}.jpg"
    record = VisitorRecord(
        id=vid,
        society_id=gate_environment["society_id"],
        gate_id=gate_environment["gate_1_id"],
        visitor_name="Unpurged Prod Visitor",
        phone_number="+919876543299",
        purpose=VisitorPurpose.GUEST,
        destination_tower_id=gate_environment["tower_t07_id"],
        destination_flat_id=gate_environment["flat_1203_id"],
        created_by_user_id=gate_environment["user_neeraj_id"],
        photo_storage_key=storage_key,
        photo_s3_key=storage_key,
        approval_status=ApprovalStatus.APPROVED,
        entry_status=EntryStatus.CHECKED_IN,
        created_at=now - timedelta(days=95),
        updated_at=now - timedelta(days=95),
    )
    db_session.add(record)
    db_session.commit()

    service = PhotoRetentionService(db_session)
    service.storage_provider = provider

    # Purge must fail closed: 0 purged, DB keys preserved
    purged = service.purge_expired_photos(batch_size=10)
    assert purged == 0

    db_session.expire_all()
    reloaded = db_session.get(VisitorRecord, vid)
    assert reloaded is not None
    assert reloaded.photo_storage_key == storage_key
    assert reloaded.photo_s3_key == storage_key
    assert reloaded.photo_purged_at is None
    assert reloaded.photo_deleted_at is None


def test_missing_s3_client_returns_false_and_preserves_record_in_non_production(
    db_session: Session,
    gate_environment: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proves that a missing S3 client in non-production returns False and never results in a successful purge."""
    now = datetime.now(UTC)
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")

    provider = S3StorageProvider(bucket_name="test-dev-bucket")
    provider.s3_client = None

    # Direct call to delete_object must return False (fail-closed, no deletion happened)
    res = provider.delete_object("visitor-photos/test/photo.jpg")
    assert res is False

    vid = uuid.uuid4()
    storage_key = f"visitor-photos/{gate_environment['society_id']}/test/{vid}.jpg"
    record = VisitorRecord(
        id=vid,
        society_id=gate_environment["society_id"],
        gate_id=gate_environment["gate_1_id"],
        visitor_name="Unpurged Dev Visitor",
        phone_number="+919876543298",
        purpose=VisitorPurpose.GUEST,
        destination_tower_id=gate_environment["tower_t07_id"],
        destination_flat_id=gate_environment["flat_1203_id"],
        created_by_user_id=gate_environment["user_neeraj_id"],
        photo_storage_key=storage_key,
        photo_s3_key=storage_key,
        approval_status=ApprovalStatus.APPROVED,
        entry_status=EntryStatus.CHECKED_IN,
        created_at=now - timedelta(days=95),
        updated_at=now - timedelta(days=95),
    )
    db_session.add(record)
    db_session.commit()

    service = PhotoRetentionService(db_session)
    service.storage_provider = provider

    purged = service.purge_expired_photos(batch_size=10)
    assert purged == 0

    db_session.expire_all()
    reloaded = db_session.get(VisitorRecord, vid)
    assert reloaded is not None
    assert reloaded.photo_storage_key == storage_key
    assert reloaded.photo_s3_key == storage_key
    assert reloaded.photo_purged_at is None
    assert reloaded.photo_deleted_at is None
