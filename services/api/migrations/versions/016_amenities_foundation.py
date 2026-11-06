"""016_amenities_foundation

Phase 8 Part 1: Amenity Booking Backend Foundation.
Provisions:
1. amenities: Facilities, courts, halls, gyms, operating hours, capacity, rules and fee configuration.
2. amenity_bookings: Concurrency-protected slot reservations, payment tracking, cancellation and refund status.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "016_amenities_foundation"
down_revision: str | None = "015_notification_system"
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
    bigint_col_type = sa.BigInteger() if is_postgres else sa.Integer()

    # 1. amenities table
    op.create_table(
        "amenities",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("amenity_type", sa.String(32), nullable=False),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column(
            "tower_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("towers.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("capacity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("slot_duration_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("opening_time", sa.String(8), nullable=False, server_default="06:00"),
        sa.Column("closing_time", sa.String(8), nullable=False, server_default="22:00"),
        sa.Column("booking_fee_paise", bigint_col_type, nullable=False, server_default="0"),
        sa.Column("advance_booking_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("min_advance_hours", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "max_slots_per_day_per_resident", sa.Integer(), nullable=False, server_default="2"
        ),
        sa.Column("cancellation_deadline_hours", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("refund_percentage", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("allowed_membership_types", json_col_type, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("rules_and_guidelines", sa.Text(), nullable=True),
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
        sa.CheckConstraint("capacity > 0", name="chk_amenity_capacity_positive"),
        sa.CheckConstraint("slot_duration_minutes > 0", name="chk_amenity_slot_duration_positive"),
        sa.CheckConstraint("booking_fee_paise >= 0", name="chk_amenity_fee_non_negative"),
        sa.CheckConstraint(
            "advance_booking_days >= 0", name="chk_amenity_advance_days_non_negative"
        ),
        sa.CheckConstraint(
            "refund_percentage >= 0 AND refund_percentage <= 100",
            name="chk_amenity_refund_pct_range",
        ),
    )
    op.create_index(
        "ix_amenities_society_active",
        "amenities",
        ["society_id", "is_active"],
    )

    # 2. amenity_bookings table
    op.create_table(
        "amenity_bookings",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "society_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "amenity_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("amenities.id", ondelete="CASCADE"),
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
            "flat_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("flats.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("booking_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.String(8), nullable=False),
        sa.Column("end_time", sa.String(8), nullable=False),
        sa.Column("booked_units", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(32), nullable=False, server_default="CONFIRMED"),
        sa.Column("booking_fee_paise", bigint_col_type, nullable=False, server_default="0"),
        sa.Column("payment_status", sa.String(32), nullable=False, server_default="FREE"),
        sa.Column("payment_reference", sa.String(128), nullable=True),
        sa.Column("refund_status", sa.String(32), nullable=False, server_default="NOT_APPLICABLE"),
        sa.Column("refund_amount_paise", bigint_col_type, nullable=False, server_default="0"),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "cancelled_by_user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("booking_metadata", json_col_type, nullable=False),
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
        sa.CheckConstraint("booked_units > 0", name="chk_booking_units_positive"),
        sa.CheckConstraint("booking_fee_paise >= 0", name="chk_booking_fee_non_negative"),
        sa.CheckConstraint("refund_amount_paise >= 0", name="chk_booking_refund_non_negative"),
        sa.CheckConstraint("end_time > start_time", name="chk_booking_time_order"),
    )
    op.create_index(
        "ix_amenity_bookings_amenity_date",
        "amenity_bookings",
        ["amenity_id", "booking_date", "status"],
    )
    op.create_index(
        "ix_amenity_bookings_user_date",
        "amenity_bookings",
        ["user_id", "booking_date"],
    )
    op.create_index(
        "ix_amenity_bookings_society_created",
        "amenity_bookings",
        ["society_id", "created_at"],
    )
    op.create_index(
        "ix_amenity_bookings_flat",
        "amenity_bookings",
        ["flat_id"],
    )

    if is_postgres:
        _enable_rls("amenities")
        _enable_rls("amenity_bookings")

        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_policies
                    WHERE tablename = 'amenities' AND policyname = 'amenities_authenticated_read_policy'
                ) THEN
                    CREATE POLICY amenities_authenticated_read_policy ON amenities
                    FOR SELECT TO authenticated
                    USING (true);
                END IF;

                IF NOT EXISTS (
                    SELECT 1 FROM pg_policies
                    WHERE tablename = 'amenity_bookings' AND policyname = 'amenity_bookings_resident_read_policy'
                ) THEN
                    CREATE POLICY amenity_bookings_resident_read_policy ON amenity_bookings
                    FOR SELECT TO authenticated
                    USING (user_id IN (SELECT id FROM users WHERE supabase_uid = auth.uid()));
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    op.drop_table("amenity_bookings")
    op.drop_table("amenities")
