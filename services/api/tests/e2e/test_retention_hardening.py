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


def test_lambda_retention_processes_multi_batch_backlog(
    db_session: Session,
    gate_environment: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies that the retention handler loops through multiple successive batches

    when the number of expired records exceeds the individual batch size (e.g. 25 records with batch_size=10).
    """
    from contextlib import contextmanager

    @contextmanager
    def mock_session():
        yield db_session

    monkeypatch.setattr("app.handlers.lambda_retention.SessionLocal", mock_session)

    now = datetime.now(UTC)
    service = PhotoRetentionService(db_session)
    dummy_jpg = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\xff\xd9"
    )

    # Seed 25 expired records (>90 days old)
    seeded_ids = []
    for i in range(25):
        vid = uuid.uuid4()
        seeded_ids.append(vid)
        storage_key = service.save_photo_bytes(
            society_id=gate_environment["society_id"],
            visitor_id=vid,
            photo_bytes=dummy_jpg,
        )
        record = VisitorRecord(
            id=vid,
            society_id=gate_environment["society_id"],
            gate_id=gate_environment["gate_1_id"],
            visitor_name=f"Multi Batch Visitor {i}",
            phone_number=f"+91987654{i:04d}",
            purpose=VisitorPurpose.GUEST,
            destination_tower_id=gate_environment["tower_t07_id"],
            destination_flat_id=gate_environment["flat_1203_id"],
            created_by_user_id=gate_environment["user_neeraj_id"],
            photo_storage_key=storage_key,
            photo_s3_key=storage_key,
            photo_captured_at=now - timedelta(days=95 + i),
            approval_status=ApprovalStatus.APPROVED,
            entry_status=EntryStatus.CHECKED_IN,
            created_at=now - timedelta(days=95 + i),
            updated_at=now - timedelta(days=95 + i),
        )
        db_session.add(record)
    db_session.commit()

    # Invoke retention handler with batch_size=10
    result = retention_handler({"batch_size": 10, "max_batches": 10}, None)

    assert result["statusCode"] == 200
    assert result["purgedCount"] == 25
    assert result["batchesExecuted"] == 3  # 10 + 10 + 5
    assert result["remainingCount"] == 0
    assert result["failedCount"] == 0
    assert result["exitReason"] == "all_eligible_purged"

    db_session.expire_all()
    for vid in seeded_ids:
        rec = db_session.get(VisitorRecord, vid)
        assert rec is not None
        assert rec.photo_purged_at is not None
        assert rec.photo_storage_key is None
        assert rec.photo_s3_key is None


def test_retention_deterministic_fifo_ordering(
    db_session: Session,
    gate_environment: dict,
) -> None:
    """Verifies that photo retention purges records in strict FIFO order (oldest photos first)."""
    now = datetime.now(UTC)
    service = PhotoRetentionService(db_session)
    dummy_jpg = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\xff\xd9"
    )

    # Create 3 records with different capture ages:
    # A: 130 days old (oldest)
    # B: 110 days old (middle)
    # C: 95 days old (newest expired)
    vid_a = uuid.uuid4()
    vid_b = uuid.uuid4()
    vid_c = uuid.uuid4()

    key_a = service.save_photo_bytes(gate_environment["society_id"], vid_a, dummy_jpg)
    key_b = service.save_photo_bytes(gate_environment["society_id"], vid_b, dummy_jpg)
    key_c = service.save_photo_bytes(gate_environment["society_id"], vid_c, dummy_jpg)

    for vid, key, days_ago in [
        (vid_c, key_c, 95),  # Insert newest first into DB
        (vid_b, key_b, 110),
        (vid_a, key_a, 130),
    ]:
        rec = VisitorRecord(
            id=vid,
            society_id=gate_environment["society_id"],
            gate_id=gate_environment["gate_1_id"],
            visitor_name=f"Order Test {days_ago}",
            phone_number="+919876543200",
            purpose=VisitorPurpose.GUEST,
            destination_tower_id=gate_environment["tower_t07_id"],
            destination_flat_id=gate_environment["flat_1203_id"],
            created_by_user_id=gate_environment["user_neeraj_id"],
            photo_storage_key=key,
            photo_s3_key=key,
            photo_captured_at=now - timedelta(days=days_ago),
            approval_status=ApprovalStatus.APPROVED,
            entry_status=EntryStatus.CHECKED_IN,
            created_at=now - timedelta(days=days_ago),
            updated_at=now - timedelta(days=days_ago),
        )
        db_session.add(rec)
    db_session.commit()

    # Batch 1 with batch_size=1 -> Must purge record A (130 days old)
    batch_1 = service.purge_batch(batch_size=1)
    assert batch_1.purged == 1
    db_session.expire_all()
    rec_a = db_session.get(VisitorRecord, vid_a)
    assert rec_a is not None and rec_a.photo_purged_at is not None
    rec_b = db_session.get(VisitorRecord, vid_b)
    assert rec_b is not None and rec_b.photo_purged_at is None
    rec_c = db_session.get(VisitorRecord, vid_c)
    assert rec_c is not None and rec_c.photo_purged_at is None

    # Batch 2 with batch_size=1 -> Must purge record B (110 days old)
    batch_2 = service.purge_batch(batch_size=1)
    assert batch_2.purged == 1
    db_session.expire_all()
    rec_b = db_session.get(VisitorRecord, vid_b)
    assert rec_b is not None and rec_b.photo_purged_at is not None
    rec_c = db_session.get(VisitorRecord, vid_c)
    assert rec_c is not None and rec_c.photo_purged_at is None

    # Batch 3 with batch_size=1 -> Must purge record C (95 days old)
    batch_3 = service.purge_batch(batch_size=1)
    assert batch_3.purged == 1
    db_session.expire_all()
    rec_c = db_session.get(VisitorRecord, vid_c)
    assert rec_c is not None and rec_c.photo_purged_at is not None


def test_lambda_retention_head_of_line_blocking_and_retry_isolation(
    db_session: Session,
    gate_environment: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies that if an S3 deletion fails on a record, it does NOT cause head-of-line blocking:

    the failed record is skipped in subsequent batches, allowing other batches and records to be purged.
    """
    from contextlib import contextmanager

    @contextmanager
    def mock_session():
        yield db_session

    monkeypatch.setattr("app.handlers.lambda_retention.SessionLocal", mock_session)

    now = datetime.now(UTC)
    service = PhotoRetentionService(db_session)
    dummy_jpg = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\xff\xd9"
    )

    records = []
    for i in range(5):
        vid = uuid.uuid4()
        key = service.save_photo_bytes(gate_environment["society_id"], vid, dummy_jpg)
        rec = VisitorRecord(
            id=vid,
            society_id=gate_environment["society_id"],
            gate_id=gate_environment["gate_1_id"],
            visitor_name=f"Failing Batch Visitor {i}",
            phone_number=f"+91987654320{i}",
            purpose=VisitorPurpose.GUEST,
            destination_tower_id=gate_environment["tower_t07_id"],
            destination_flat_id=gate_environment["flat_1203_id"],
            created_by_user_id=gate_environment["user_neeraj_id"],
            photo_storage_key=key,
            photo_s3_key=key,
            photo_captured_at=now - timedelta(days=120 - i),
            approval_status=ApprovalStatus.APPROVED,
            entry_status=EntryStatus.CHECKED_IN,
            created_at=now - timedelta(days=120 - i),
            updated_at=now - timedelta(days=120 - i),
        )
        db_session.add(rec)
        records.append(rec)
    db_session.commit()

    failing_record = records[1]  # Second record will fail S3 deletion
    failing_key = failing_record.photo_storage_key

    # Mock storage delete_file to fail only for failing_key
    from app.domains.complaints import storage as storage_mod

    real_storage_provider = storage_mod.get_storage_provider()
    real_delete_file = real_storage_provider.delete_file

    def selective_delete_file(key: str) -> bool:
        if key == failing_key:
            return False
        return real_delete_file(key)

    monkeypatch.setattr(real_storage_provider, "delete_file", selective_delete_file)

    # Run with batch_size=2.
    # Batch 1 (size 2): rec[0] succeeds, rec[1] fails.
    # rec[1] is added to failed_ids.
    # Batch 2 (size 2): rec[2], rec[3] succeed (rec[1] excluded!).
    # Batch 3 (size 2): rec[4] succeeds.
    result = retention_handler({"batch_size": 2, "max_batches": 5}, None)

    assert result["statusCode"] == 200
    assert result["purgedCount"] == 4
    assert result["failedCount"] == 1
    assert str(failing_record.id) in result["failedIds"]
    assert result["remainingCount"] == 0

    db_session.expire_all()
    # Failing record must be preserved for retry
    reloaded_failing = db_session.get(VisitorRecord, failing_record.id)
    assert reloaded_failing is not None
    assert reloaded_failing.photo_purged_at is None
    assert reloaded_failing.photo_storage_key == failing_key

    # Other 4 records must be successfully purged
    for rec in [records[0], records[2], records[3], records[4]]:
        reloaded = db_session.get(VisitorRecord, rec.id)
        assert reloaded is not None
        assert reloaded.photo_purged_at is not None
        assert reloaded.photo_storage_key is None


def test_lambda_retention_respects_execution_deadline(
    db_session: Session,
    gate_environment: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies that the retention handler terminates gracefully before Lambda timeout

    when context.get_remaining_time_in_millis() falls below min_remaining_time_ms.
    """
    from contextlib import contextmanager

    @contextmanager
    def mock_session():
        yield db_session

    monkeypatch.setattr("app.handlers.lambda_retention.SessionLocal", mock_session)

    now = datetime.now(UTC)
    service = PhotoRetentionService(db_session)
    dummy_jpg = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\xff\xd9"
    )

    # Seed 20 expired records
    for i in range(20):
        vid = uuid.uuid4()
        key = service.save_photo_bytes(gate_environment["society_id"], vid, dummy_jpg)
        rec = VisitorRecord(
            id=vid,
            society_id=gate_environment["society_id"],
            gate_id=gate_environment["gate_1_id"],
            visitor_name=f"Deadline Test Visitor {i}",
            phone_number=f"+9198765431{i:02d}",
            purpose=VisitorPurpose.GUEST,
            destination_tower_id=gate_environment["tower_t07_id"],
            destination_flat_id=gate_environment["flat_1203_id"],
            created_by_user_id=gate_environment["user_neeraj_id"],
            photo_storage_key=key,
            photo_s3_key=key,
            photo_captured_at=now - timedelta(days=100 + i),
            approval_status=ApprovalStatus.APPROVED,
            entry_status=EntryStatus.CHECKED_IN,
            created_at=now - timedelta(days=100 + i),
            updated_at=now - timedelta(days=100 + i),
        )
        db_session.add(rec)
    db_session.commit()

    # Mock AWS Lambda context with countdown
    # Call 1: 45,000ms (> 30,000ms buffer -> batch 1 executes)
    # Call 2: 25,000ms (<= 30,000ms buffer -> loop halts safely)
    remaining_times = [45000, 25000]

    class MockLambdaContext:
        def get_remaining_time_in_millis(self) -> int:
            if remaining_times:
                return remaining_times.pop(0)
            return 10000

    context = MockLambdaContext()

    result = retention_handler(
        {"batch_size": 10, "max_batches": 10, "min_remaining_time_ms": 30000},
        context,
    )

    assert result["statusCode"] == 200
    assert result["batchesExecuted"] == 1
    assert result["purgedCount"] == 10
    assert result["remainingCount"] == 10
    assert result["exitReason"] == "lambda_timeout_buffer_reached"
