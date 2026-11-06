"""017_amenity_blocks_and_payments

Phase 8 Part 3: Amenity Payments and Staff Booking Management.
Provisions:
1. amenity_blocks table for temporary date and slot maintenance closures.
2. payment_id and payment_expires_at on amenity_bookings.
3. booking_id on payments table linking simulated payments to amenity bookings.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "017_amenity_blocks_and_payments"
down_revision: str | None = "016_amenities_foundation"
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

    # 1. amenity_blocks table
    op.create_table(
        "amenity_blocks",
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
        sa.Column("block_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.String(8), nullable=True),
        sa.Column("end_time", sa.String(8), nullable=True),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column(
            "blocked_by_user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
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
    )
    op.create_index(
        "ix_amenity_blocks_society_amenity_date",
        "amenity_blocks",
        ["society_id", "amenity_id", "block_date"],
    )

    if is_postgres:
        _enable_rls("amenity_blocks")

        # 2. Add payment_id and payment_expires_at to amenity_bookings
        op.add_column(
            "amenity_bookings",
            sa.Column(
                "payment_id",
                sa.Uuid(as_uuid=True),
                sa.ForeignKey(
                    "payments.id",
                    name="fk_amenity_bookings_payment_id",
                    ondelete="SET NULL",
                ),
                nullable=True,
            ),
        )
        op.add_column(
            "amenity_bookings",
            sa.Column("payment_expires_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_amenity_bookings_payment_id", "amenity_bookings", ["payment_id"])

        # 3. Add booking_id to payments
        op.add_column(
            "payments",
            sa.Column(
                "booking_id",
                sa.Uuid(as_uuid=True),
                sa.ForeignKey(
                    "amenity_bookings.id",
                    name="fk_payments_booking_id",
                    ondelete="SET NULL",
                ),
                nullable=True,
            ),
        )
        op.create_index("ix_payments_booking_id", "payments", ["booking_id"])
    else:
        # SQLite dialect: add columns directly without batch recreation
        # to avoid breaking existing triggers on payments
        op.add_column(
            "amenity_bookings",
            sa.Column("payment_id", sa.Uuid(as_uuid=True), nullable=True),
        )
        op.add_column(
            "amenity_bookings",
            sa.Column("payment_expires_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_amenity_bookings_payment_id", "amenity_bookings", ["payment_id"])

        op.add_column(
            "payments",
            sa.Column("booking_id", sa.Uuid(as_uuid=True), nullable=True),
        )
        op.create_index("ix_payments_booking_id", "payments", ["booking_id"])


def downgrade() -> None:
    op.drop_index("ix_payments_booking_id", table_name="payments")
    op.drop_column("payments", "booking_id")

    op.drop_column("amenity_bookings", "payment_expires_at")
    op.drop_index("ix_amenity_bookings_payment_id", table_name="amenity_bookings")
    op.drop_column("amenity_bookings", "payment_id")

    op.drop_index("ix_amenity_blocks_society_amenity_date", table_name="amenity_blocks")
    op.drop_table("amenity_blocks")
