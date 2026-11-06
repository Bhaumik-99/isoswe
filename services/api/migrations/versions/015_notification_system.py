"""015_notification_system

Phase 7: Event-Driven Notifications & Resident Communication.
Provisions:
1. notifications: In-app resident & staff notification store with fast unread/read querying.
2. notification_deliveries: Multi-channel delivery lifecycle, idempotency, backoff retries.
3. notification_delivery_attempts: Auditable history of external delivery attempts.
4. notification_preferences: Tenant-aware resident channel preferences.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "015_notification_system"
down_revision: str | None = "014_reconcile_visitor_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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
    json_col_type = JSONB if is_postgres else sa.JSON()

    # 1. notifications table
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "recipient_user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False, server_default="IN_APP"),
        sa.Column("priority", sa.String(32), nullable=False, server_default="NORMAL"),
        sa.Column("aggregate_type", sa.String(64), nullable=True),
        sa.Column("aggregate_id", sa.String(128), nullable=True),
        sa.Column("action_url", sa.String(512), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_metadata", json_col_type, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_notifications_recipient_unread",
        "notifications",
        ["recipient_user_id", "read_at"],
    )
    op.create_index(
        "ix_notifications_recipient_created",
        "notifications",
        ["recipient_user_id", "created_at"],
    )
    op.create_index(
        "ix_notifications_society_created",
        "notifications",
        ["society_id", "created_at"],
    )
    op.create_index(
        "ix_notifications_aggregate",
        "notifications",
        ["aggregate_type", "aggregate_id"],
    )

    # 2. notification_deliveries table
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "notification_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("notifications.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "society_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "recipient_user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column(
            "idempotency_key",
            sa.String(255),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column("provider_message_id", sa.String(255), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_deliveries_status_next_attempt",
        "notification_deliveries",
        ["status", "next_attempt_at"],
    )
    op.create_index(
        "ix_deliveries_society_recipient",
        "notification_deliveries",
        ["society_id", "recipient_user_id"],
    )

    # 3. notification_delivery_attempts table
    op.create_table(
        "notification_delivery_attempts",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "delivery_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("notification_deliveries.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("provider_reference", sa.String(255), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_details", sa.Text(), nullable=True),
        sa.Column(
            "attempted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # 4. notification_preferences table
    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "email_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "sms_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "in_app_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "billing_email",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "billing_sms",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "complaints_email",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "complaints_sms",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "visitor_sms",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "society_id", "user_id", name="uq_notification_preference_user_society"
        ),
    )

    if is_postgres:
        _enable_rls("notifications")
        _enable_rls("notification_deliveries")
        _enable_rls("notification_delivery_attempts")
        _enable_rls("notification_preferences")

        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_policies
                    WHERE tablename = 'notifications' AND policyname = 'notifications_resident_read_policy'
                ) THEN
                    CREATE POLICY notifications_resident_read_policy ON notifications
                    FOR SELECT TO authenticated
                    USING (recipient_user_id IN (SELECT id FROM users WHERE supabase_uid = auth.uid()));
                END IF;

                IF NOT EXISTS (
                    SELECT 1 FROM pg_policies
                    WHERE tablename = 'notification_preferences' AND policyname = 'notification_preferences_user_policy'
                ) THEN
                    CREATE POLICY notification_preferences_user_policy ON notification_preferences
                    FOR ALL TO authenticated
                    USING (user_id IN (SELECT id FROM users WHERE supabase_uid = auth.uid()))
                    WITH CHECK (user_id IN (SELECT id FROM users WHERE supabase_uid = auth.uid()));
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    op.drop_table("notification_delivery_attempts")
    op.drop_table("notification_deliveries")
    op.drop_table("notifications")
    op.drop_table("notification_preferences")
