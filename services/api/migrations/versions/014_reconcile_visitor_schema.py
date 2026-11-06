"""014_reconcile_visitor_schema

Reconciles migration 013 with the Phase 6 SQLAlchemy models and hardens guest-pass security.

Why a forward migration (not an edit of 013): migration 013 may already have been applied to
shared databases, so the fix must be additive and idempotent in effect.

Schema reconciliation (migration 013 -> ORM models)
1. Renames ``visitor_records`` -> ``visitors`` (the ORM table name; FKs and indexes follow).
2. visitors: adds ``photo_storage_key``, ``photo_deleted_at``, ``approved_at``,
   ``rejection_reason``, ``payload_hash``, ``created_by_user_id`` and ``photo_sha256``;
   backfills the paired legacy columns.
3. guest_passes: adds ``flat_id``, ``pass_code_prefix`` and ``revocation_reason``.
4. guest_pass_redemptions: adds ``visitor_id`` and ``redeemed_by_user_id``.
5. offline_sync_events: adds ``visitor_id``.
6. gates.gate_name becomes nullable to match the model (display name falls back to ``name``).

Security hardening
7. Creates ``guest_pass_failed_attempts`` - durable store for the distributed brute-force limiter.
8. Guest-pass codes move from unsalted-style SHA-256 to keyed HMAC-SHA256 over 12 random
   characters. Plaintext codes were never stored, so existing ACTIVE passes cannot be re-hashed;
   they are revoked with an explicit reason and residents must issue new passes.

Revision ID: 014_reconcile_visitor_schema
Revises: 013_gate_visitor_management
Create Date: 2026-11-06 21:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "014_reconcile_visitor_schema"
down_revision: str | None = "013_gate_visitor_management"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_HASH_REVOCATION_REASON = "Revoked: guest pass hashing upgraded to keyed HMAC; please reissue"


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
    op.execute(f"GRANT SELECT ON {table} TO authenticated;")
    op.execute(f"GRANT ALL ON {table} TO service_role;")
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE tablename = '{table}' AND policyname = '{table}_service_role_policy'
            ) THEN
                CREATE POLICY {table}_service_role_policy ON {table}
                FOR ALL TO service_role
                USING (true) WITH CHECK (true);
            END IF;
        END $$;
        """
    )


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 1. Table rename: visitor_records -> visitors
    op.rename_table("visitor_records", "visitors")
    if is_postgres:
        op.execute(
            "ALTER POLICY visitor_records_service_role_policy ON visitors "
            "RENAME TO visitors_service_role_policy;"
        )

    # 2. visitors: missing columns
    with op.batch_alter_table("visitors") as batch:
        batch.add_column(sa.Column("photo_storage_key", sa.String(length=512), nullable=True))
        batch.add_column(sa.Column("photo_deleted_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("rejection_reason", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("payload_hash", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("photo_sha256", sa.String(length=64), nullable=True))
        batch.add_column(
            sa.Column(
                "created_by_user_id",
                sa.Uuid(),
                sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_visitors_created_by_user"),
                nullable=True,
            )
        )
    op.execute(
        "UPDATE visitors SET photo_storage_key = photo_s3_key, "
        "photo_deleted_at = photo_purged_at, approved_at = approval_action_at, "
        "rejection_reason = approval_rejection_reason"
    )
    op.execute(
        "UPDATE visitors SET created_by_user_id = entry_guard_user_id "
        "WHERE created_by_user_id IS NULL"
    )

    # 3. guest_passes: missing columns (+ legacy hash revocation)
    with op.batch_alter_table("guest_passes") as batch:
        batch.add_column(
            sa.Column(
                "flat_id",
                sa.Uuid(),
                sa.ForeignKey("flats.id", ondelete="CASCADE", name="fk_guest_passes_flat"),
                nullable=True,
            )
        )
        batch.add_column(sa.Column("pass_code_prefix", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("revocation_reason", sa.String(length=255), nullable=True))
        batch.create_index("ix_guest_passes_flat_id", ["flat_id"])
    op.execute("UPDATE guest_passes SET flat_id = destination_flat_id, pass_code_prefix = 'GP-'")
    op.execute(
        sa.text(
            "UPDATE guest_passes SET status = 'REVOKED', revoked_at = CURRENT_TIMESTAMP, "
            "revocation_reason = :reason WHERE status = 'ACTIVE'"
        ).bindparams(reason=LEGACY_HASH_REVOCATION_REASON)
    )

    # 4. guest_pass_redemptions: missing columns
    with op.batch_alter_table("guest_pass_redemptions") as batch:
        batch.add_column(
            sa.Column(
                "visitor_id",
                sa.Uuid(),
                sa.ForeignKey("visitors.id", ondelete="SET NULL", name="fk_redemptions_visitor"),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "redeemed_by_user_id",
                sa.Uuid(),
                sa.ForeignKey(
                    "users.id", ondelete="RESTRICT", name="fk_redemptions_redeemed_by_user"
                ),
                nullable=True,
            )
        )
        batch.create_index("ix_guest_pass_redemptions_visitor_id", ["visitor_id"])
        batch.create_index("ix_guest_pass_redemptions_redeemed_by_user_id", ["redeemed_by_user_id"])
    op.execute(
        "UPDATE guest_pass_redemptions SET visitor_id = visitor_record_id, "
        "redeemed_by_user_id = redeemed_by_guard_id"
    )

    # 5. offline_sync_events: missing column
    with op.batch_alter_table("offline_sync_events") as batch:
        batch.add_column(
            sa.Column(
                "visitor_id",
                sa.Uuid(),
                sa.ForeignKey("visitors.id", ondelete="SET NULL", name="fk_offline_sync_visitor"),
                nullable=True,
            )
        )
        batch.create_index("ix_offline_sync_events_visitor_id", ["visitor_id"])
    op.execute("UPDATE offline_sync_events SET visitor_id = visitor_record_id")

    # 6. gates.gate_name nullable (model falls back to `name`)
    with op.batch_alter_table("gates") as batch:
        batch.alter_column("gate_name", existing_type=sa.String(length=128), nullable=True)

    # 7. Durable brute-force limiter storage
    op.create_table(
        "guest_pass_failed_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "society_id",
            sa.Uuid(),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "gate_id", sa.Uuid(), sa.ForeignKey("gates.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "guard_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column(
            "attempted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_pass_failed_gate_time", "guest_pass_failed_attempts", ["gate_id", "attempted_at"]
    )
    op.create_index(
        "ix_pass_failed_guard_time", "guest_pass_failed_attempts", ["guard_user_id", "attempted_at"]
    )
    if is_postgres:
        _enable_rls("guest_pass_failed_attempts")


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute(
            "DROP POLICY IF EXISTS guest_pass_failed_attempts_service_role_policy "
            "ON guest_pass_failed_attempts;"
        )
    op.drop_index("ix_pass_failed_guard_time", table_name="guest_pass_failed_attempts")
    op.drop_index("ix_pass_failed_gate_time", table_name="guest_pass_failed_attempts")
    op.drop_table("guest_pass_failed_attempts")

    with op.batch_alter_table("gates") as batch:
        batch.alter_column("gate_name", existing_type=sa.String(length=128), nullable=False)

    with op.batch_alter_table("offline_sync_events") as batch:
        batch.drop_index("ix_offline_sync_events_visitor_id")
        batch.drop_column("visitor_id")

    with op.batch_alter_table("guest_pass_redemptions") as batch:
        batch.drop_index("ix_guest_pass_redemptions_redeemed_by_user_id")
        batch.drop_index("ix_guest_pass_redemptions_visitor_id")
        batch.drop_column("redeemed_by_user_id")
        batch.drop_column("visitor_id")

    with op.batch_alter_table("guest_passes") as batch:
        batch.drop_index("ix_guest_passes_flat_id")
        batch.drop_column("revocation_reason")
        batch.drop_column("pass_code_prefix")
        batch.drop_column("flat_id")

    with op.batch_alter_table("visitors") as batch:
        for col in (
            "created_by_user_id",
            "photo_sha256",
            "payload_hash",
            "rejection_reason",
            "approved_at",
            "photo_deleted_at",
            "photo_storage_key",
        ):
            batch.drop_column(col)

    if is_postgres:
        op.execute(
            "ALTER POLICY visitors_service_role_policy ON visitors "
            "RENAME TO visitor_records_service_role_policy;"
        )
    op.rename_table("visitors", "visitor_records")
