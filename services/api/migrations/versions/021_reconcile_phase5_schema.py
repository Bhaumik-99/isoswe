"""021_reconcile_phase5_schema

Reconciles migration 011 (resident_upi_mappings and safety_alerts) with the
Phase 5 SQLAlchemy models so PostgreSQL queries match the ORM definitions.

Revision ID: 021_reconcile_phase5_schema
Revises: 020_notice_version_schedule
Create Date: 2026-11-08 18:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "021_reconcile_phase5_schema"
down_revision: str | None = "020_notice_version_schedule"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. resident_upi_mappings: add resident_id, account_holder_name, updated_at
    with op.batch_alter_table("resident_upi_mappings") as batch:
        batch.add_column(
            sa.Column(
                "resident_id",
                sa.Uuid(),
                sa.ForeignKey(
                    "users.id",
                    ondelete="CASCADE",
                    name="fk_resident_upi_mappings_resident_id",
                ),
                nullable=True,
            )
        )
        batch.add_column(sa.Column("account_holder_name", sa.String(length=255), nullable=True))
        batch.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            )
        )
        batch.create_index("ix_resident_upi_mappings_resident_id", ["resident_id"])

    op.execute("UPDATE resident_upi_mappings SET resident_id = user_id WHERE resident_id IS NULL")

    # 2. safety_alerts: add alert_title, alert_details, is_acknowledged,
    #    acknowledged_at, acknowledged_by, acknowledgement_notes, updated_at
    with op.batch_alter_table("safety_alerts") as batch:
        batch.add_column(
            sa.Column(
                "alert_title",
                sa.String(length=255),
                server_default="Safety Alert",
                nullable=False,
            )
        )
        batch.add_column(
            sa.Column(
                "alert_details",
                sa.Text(),
                server_default="",
                nullable=False,
            )
        )
        batch.add_column(
            sa.Column(
                "is_acknowledged",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
        batch.add_column(sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column(
                "acknowledged_by",
                sa.Uuid(),
                sa.ForeignKey(
                    "users.id",
                    ondelete="SET NULL",
                    name="fk_safety_alerts_acknowledged_by",
                ),
                nullable=True,
            )
        )
        batch.add_column(sa.Column("acknowledgement_notes", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            )
        )
        batch.create_index("ix_safety_alerts_society_status", ["society_id", "is_acknowledged"])

    op.execute(
        "UPDATE safety_alerts SET is_acknowledged = is_read, "
        "acknowledged_at = read_at, acknowledged_by = read_by"
    )


def downgrade() -> None:
    with op.batch_alter_table("safety_alerts") as batch:
        batch.drop_index("ix_safety_alerts_society_status")
        for col in (
            "updated_at",
            "acknowledgement_notes",
            "acknowledged_by",
            "acknowledged_at",
            "is_acknowledged",
            "alert_details",
            "alert_title",
        ):
            batch.drop_column(col)

    with op.batch_alter_table("resident_upi_mappings") as batch:
        batch.drop_index("ix_resident_upi_mappings_resident_id")
        for col in ("updated_at", "account_holder_name", "resident_id"):
            batch.drop_column(col)
