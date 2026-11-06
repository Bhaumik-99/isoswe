"""013_gate_visitor_management

Phase 6: Gate Visitor Management, Pre-Approved Passes, and Offline Operations.

Creates:
1. gates: Physical gate configuration bound to society (Gates 1-4)
2. gate_assignments: Gate security staff assignments with temporal shifts
3. guest_passes: Resident pre-approved passes with salted SHA-256 hash codes
4. visitor_records: Visitor logs with decoupled physical and approval state machines
5. guest_pass_redemptions: Immutable audit usage records for guest pass redemptions
6. offline_sync_events: Replay-protected offline client synchronization event registry
7. Backfills legacy HELPDESK staff in user_permissions to guarantee zero regressions

Revision ID: 013_gate_visitor_management
Revises: 012_user_permissions
Create Date: 2026-11-06 17:00:00.000000
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "013_gate_visitor_management"
down_revision: str | None = "012_user_permissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 1. Gates
    op.create_table(
        "gates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "society_id",
            sa.Uuid(),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("gate_number", sa.Integer(), nullable=False),
        sa.Column("gate_name", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="ACTIVE", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint("society_id", "gate_number", name="uq_gate_society_number"),
        sa.CheckConstraint("gate_number >= 1", name="chk_gate_number_positive"),
    )
    op.create_index("ix_gates_society_status", "gates", ["society_id", "status"])

    # 2. Gate Staff Assignments
    op.create_table(
        "gate_assignments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "society_id",
            sa.Uuid(),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "gate_id",
            sa.Uuid(),
            sa.ForeignKey("gates.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "assigned_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("assigned_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "assigned_until IS NULL OR assigned_until >= assigned_from",
            name="chk_gate_assignment_dates",
        ),
    )
    op.create_index("ix_gate_assignments_user_active", "gate_assignments", ["user_id", "is_active"])
    op.create_index("ix_gate_assignments_gate_active", "gate_assignments", ["gate_id", "is_active"])
    op.create_index(
        "ix_gate_assignments_society_gate", "gate_assignments", ["society_id", "gate_id"]
    )
    op.create_index(
        "ix_gate_assignments_auth_lookup",
        "gate_assignments",
        ["user_id", "society_id", "gate_id", "is_active"],
    )

    # 3. Guest Passes
    op.create_table(
        "guest_passes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "society_id",
            sa.Uuid(),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "destination_flat_id",
            sa.Uuid(),
            sa.ForeignKey("flats.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "created_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("guest_name", sa.String(length=255), nullable=False),
        sa.Column("guest_phone", sa.String(length=32), nullable=True),
        sa.Column("purpose", sa.String(length=255), nullable=False),
        sa.Column("pass_type", sa.String(length=32), nullable=False),
        sa.Column("pass_code_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="ACTIVE", nullable=False),
        sa.Column("max_uses", sa.Integer(), server_default="1", nullable=False),
        sa.Column("used_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "revoked_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint("society_id", "pass_code_hash", name="uq_guest_pass_society_hash"),
        sa.CheckConstraint("max_uses >= 1", name="chk_guest_pass_max_uses"),
        sa.CheckConstraint(
            "used_count >= 0 AND used_count <= max_uses", name="chk_guest_pass_used_count"
        ),
        sa.CheckConstraint("valid_until >= valid_from", name="chk_guest_pass_validity"),
    )
    op.create_index(
        "ix_guest_passes_hash_lookup",
        "guest_passes",
        ["society_id", "pass_code_hash", "status"],
    )
    op.create_index(
        "ix_guest_passes_flat_status",
        "guest_passes",
        ["destination_flat_id", "status", "valid_until"],
    )
    op.create_index(
        "ix_guest_passes_creator_created",
        "guest_passes",
        ["created_by_user_id", "created_at"],
    )
    op.create_index(
        "ix_guest_passes_society_created",
        "guest_passes",
        ["society_id", "created_at"],
    )

    # 4. Visitor Records
    op.create_table(
        "visitor_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "society_id",
            sa.Uuid(),
            sa.ForeignKey("societies.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "gate_id",
            sa.Uuid(),
            sa.ForeignKey("gates.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "destination_flat_id",
            sa.Uuid(),
            sa.ForeignKey("flats.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "destination_tower_id",
            sa.Uuid(),
            sa.ForeignKey("towers.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("visitor_name", sa.String(length=255), nullable=False),
        sa.Column("phone_number", sa.String(length=32), nullable=False),
        sa.Column("vehicle_number", sa.String(length=20), nullable=True),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column(
            "approval_status", sa.String(length=32), server_default="PENDING", nullable=False
        ),
        sa.Column("entry_status", sa.String(length=32), server_default="EXPECTED", nullable=False),
        sa.Column(
            "approved_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approval_action_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_rejection_reason", sa.String(length=255), nullable=True),
        sa.Column(
            "entry_gate_id",
            sa.Uuid(),
            sa.ForeignKey("gates.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("entry_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "entry_guard_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "exit_gate_id",
            sa.Uuid(),
            sa.ForeignKey("gates.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("exit_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "exit_guard_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("photo_s3_key", sa.String(length=512), nullable=True),
        sa.Column("photo_captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("photo_purged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "privacy_notice_version",
            sa.String(length=64),
            server_default="v1.0-2026-pune",
            nullable=False,
        ),
        sa.Column(
            "guest_pass_id",
            sa.Uuid(),
            sa.ForeignKey("guest_passes.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("client_event_id", sa.Uuid(), nullable=True),
        sa.Column("is_offline_creation", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "exit_time IS NULL OR entry_time IS NULL OR exit_time >= entry_time",
            name="chk_visitor_entry_exit_time",
        ),
    )
    op.create_index(
        "ix_visitor_records_society_flat_created",
        "visitor_records",
        ["society_id", "destination_flat_id", "created_at"],
    )
    op.create_index(
        "ix_visitor_records_flat_pending",
        "visitor_records",
        ["destination_flat_id", "approval_status", "created_at"],
    )
    op.create_index(
        "ix_visitor_records_society_checked_in",
        "visitor_records",
        ["society_id", "entry_status", "entry_time"],
    )
    op.create_index("ix_visitor_records_gate_date", "visitor_records", ["gate_id", "created_at"])
    op.create_index(
        "ix_visitor_records_society_phone", "visitor_records", ["society_id", "phone_number"]
    )
    op.create_index(
        "ix_visitor_records_society_vehicle", "visitor_records", ["society_id", "vehicle_number"]
    )
    op.create_index(
        "ix_visitor_records_retention", "visitor_records", ["created_at", "photo_s3_key"]
    )
    op.create_index("ix_visitor_records_client_event", "visitor_records", ["client_event_id"])

    # 5. Guest Pass Redemptions
    op.create_table(
        "guest_pass_redemptions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "society_id",
            sa.Uuid(),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "guest_pass_id",
            sa.Uuid(),
            sa.ForeignKey("guest_passes.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "visitor_record_id",
            sa.Uuid(),
            sa.ForeignKey("visitor_records.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "gate_id",
            sa.Uuid(),
            sa.ForeignKey("gates.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "redeemed_by_guard_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column("redemption_sequence", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "redeemed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_guest_pass_redemptions_pass",
        "guest_pass_redemptions",
        ["guest_pass_id", "redemption_sequence"],
    )
    op.create_index(
        "ix_guest_pass_redemptions_society_gate",
        "guest_pass_redemptions",
        ["society_id", "gate_id", "redeemed_at"],
    )

    # 6. Offline Sync Events
    op.create_table(
        "offline_sync_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "society_id",
            sa.Uuid(),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "gate_id",
            sa.Uuid(),
            sa.ForeignKey("gates.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("client_event_id", sa.Uuid(), nullable=False),
        sa.Column(
            "event_type",
            sa.String(length=64),
            server_default="VISITOR_REGISTRATION",
            nullable=False,
        ),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("sync_status", sa.String(length=32), nullable=False),
        sa.Column(
            "visitor_record_id",
            sa.Uuid(),
            sa.ForeignKey("visitor_records.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint("society_id", "client_event_id", name="uq_offline_sync_client_event"),
    )
    op.create_index(
        "ix_offline_sync_client_event",
        "offline_sync_events",
        ["society_id", "client_event_id"],
    )
    op.create_index(
        "ix_offline_sync_gate_processed",
        "offline_sync_events",
        ["gate_id", "processed_at"],
    )

    # 7. PostgreSQL RLS Configuration
    if is_postgres:
        new_tables = [
            "gates",
            "gate_assignments",
            "guest_passes",
            "visitor_records",
            "guest_pass_redemptions",
            "offline_sync_events",
        ]
        for tbl in new_tables:
            op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;")
            op.execute(f"GRANT SELECT ON {tbl} TO authenticated;")
            op.execute(f"GRANT ALL ON {tbl} TO service_role;")
            op.execute(
                f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_policies WHERE tablename = '{tbl}' AND policyname = '{tbl}_service_role_policy'
                    ) THEN
                        CREATE POLICY {tbl}_service_role_policy ON {tbl}
                        FOR ALL TO service_role
                        USING (true) WITH CHECK (true);
                    END IF;
                END $$;
                """
            )

    # 8. Legacy HELPDESK Staff Permission Backfill
    # Guarantees zero regression on Phases 1–5 test suites by granting explicit permissions
    user_roles_t = sa.table(
        "user_roles",
        sa.column("user_id", sa.Uuid()),
        sa.column("society_id", sa.Uuid()),
        sa.column("role", sa.String()),
    )
    user_permissions_t = sa.table(
        "user_permissions",
        sa.column("id", sa.Uuid()),
        sa.column("user_id", sa.Uuid()),
        sa.column("society_id", sa.Uuid()),
        sa.column("permission", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )

    helpdesk_rows = bind.execute(
        sa.select(user_roles_t.c.user_id, user_roles_t.c.society_id).where(
            user_roles_t.c.role == "HELPDESK"
        )
    ).fetchall()

    operational_perms = [
        "COMPLAINT_MANAGE",
        "BANK_IMPORT",
        "RECONCILIATION_REVIEW",
        "BILLING_MANAGE",
    ]
    now = datetime.now(UTC)
    for row in helpdesk_rows:
        for perm in operational_perms:
            existing = bind.execute(
                sa.select(user_permissions_t.c.id).where(
                    user_permissions_t.c.user_id == row.user_id,
                    user_permissions_t.c.society_id == row.society_id,
                    user_permissions_t.c.permission == perm,
                )
            ).first()
            if not existing:
                bind.execute(
                    user_permissions_t.insert().values(
                        id=uuid.uuid4(),
                        user_id=row.user_id,
                        society_id=row.society_id,
                        permission=perm,
                        created_at=now,
                    )
                )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    new_tables = [
        "offline_sync_events",
        "guest_pass_redemptions",
        "visitor_records",
        "guest_passes",
        "gate_assignments",
        "gates",
    ]

    if is_postgres:
        for tbl in new_tables:
            op.execute(f"DROP POLICY IF EXISTS {tbl}_service_role_policy ON {tbl};")
            op.execute(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY;")

    # Drop in strict reverse dependency order
    for tbl in new_tables:
        op.drop_table(tbl)
