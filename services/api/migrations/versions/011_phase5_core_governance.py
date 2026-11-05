"""011_phase5_core_governance

Phase 5: Financial Governance, UPI-Aware Bank Reconciliation, Complaints Governance,
and Persistent Safety Alert Infrastructure.

Creates:
1. late_fee_policies: Configurable maintenance surcharge policies following society bye-laws
2. late_fee_applications: Idempotent records of late fees assessed against specific invoices
3. resident_upi_mappings: Authorized resident VPA/UPI ID mappings for transparent statement reconciliation
4. safety_alerts: Persistent duty-manager in-app emergency alerts with unassigned queue support
5. Updates complaints table with original_category and category_corrected_by tracking
6. Updates bank_transactions table with payer_vpa column
7. Secures public.is_reconciliation_helpdesk() with fixed search_path = public, pg_temp

Revision ID: 011_phase5_core_governance
Revises: 010_bank_txn_unique_fp
Create Date: 2026-11-05 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "011_phase5_core_governance"
down_revision: str | None = "010_bank_txn_unique_fp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 1. Late Fee Policies Table
    op.create_table(
        "late_fee_policies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "society_id",
            sa.Uuid(),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("policy_name", sa.String(128), nullable=False),
        sa.Column(
            "calculation_method", sa.String(32), nullable=False
        ),  # FLAT_FEE, PERCENTAGE_PER_MONTH, DAILY_INTEREST_PAISE
        sa.Column("amount_or_rate_bps", sa.BigInteger(), nullable=False),
        sa.Column("grace_period_days", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("min_charge_paise", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("max_charge_paise", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "society_id",
            "policy_name",
            "effective_from",
            name="uq_late_fee_policy_society_name_from",
        ),
    )
    op.create_index(
        "ix_late_fee_policies_society_active",
        "late_fee_policies",
        ["society_id", "is_active"],
    )

    # 2. Late Fee Applications Table (Idempotent tracking per invoice & billing period)
    op.create_table(
        "late_fee_applications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "society_id",
            sa.Uuid(),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "invoice_id",
            sa.Uuid(),
            sa.ForeignKey("invoices.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "policy_id",
            sa.Uuid(),
            sa.ForeignKey("late_fee_policies.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column("billing_period", sa.String(7), nullable=False),
        sa.Column("applied_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("days_overdue", sa.Integer(), nullable=False),
        sa.Column("unpaid_principal_paise", sa.BigInteger(), nullable=False),
        sa.Column("fee_paise", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "invoice_id", "billing_period", name="uq_late_fee_invoice_billing_period"
        ),
    )
    op.create_index(
        "ix_late_fee_apps_society_period",
        "late_fee_applications",
        ["society_id", "billing_period"],
    )

    # 3. Resident UPI Mappings Table (Authorized resident VPA/UPI addresses)
    op.create_table(
        "resident_upi_mappings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "society_id",
            sa.Uuid(),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "flat_id",
            sa.Uuid(),
            sa.ForeignKey("flats.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("vpa", sa.String(128), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("notes", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("society_id", "vpa", name="uq_resident_upi_society_vpa"),
    )
    op.create_index(
        "ix_resident_upi_society_vpa",
        "resident_upi_mappings",
        ["society_id", "vpa"],
    )
    op.create_index(
        "ix_resident_upi_flat",
        "resident_upi_mappings",
        ["flat_id"],
    )

    # 4. Safety Alerts Table (Persistent duty-manager emergency alerts)
    op.create_table(
        "safety_alerts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "society_id",
            sa.Uuid(),
            sa.ForeignKey("societies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "complaint_id",
            sa.Uuid(),
            sa.ForeignKey("complaints.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("hazard_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False, server_default="CRITICAL"),
        sa.Column(
            "assigned_staff_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "read_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("idempotency_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idempotency_hash", name="uq_safety_alert_idempotency"),
    )
    op.create_index(
        "ix_safety_alerts_society_unread",
        "safety_alerts",
        ["society_id", "is_read"],
    )

    # 5. Add columns to complaints
    op.add_column("complaints", sa.Column("original_category", sa.String(32), nullable=True))
    op.add_column(
        "complaints", sa.Column("category_corrected_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("complaints", sa.Column("category_corrected_by", sa.Uuid(), nullable=True))

    # 6. Add payer_vpa column to bank_transactions
    op.add_column("bank_transactions", sa.Column("payer_vpa", sa.String(128), nullable=True))
    op.create_index("ix_bank_transactions_payer_vpa", "bank_transactions", ["payer_vpa"])

    # 7. PostgreSQL-Specific Hardening & Row-Level Security
    if is_postgres:
        # Secure is_helpdesk_for_society() with fixed search_path = public, pg_temp
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_proc p
                    JOIN pg_namespace n ON p.pronamespace = n.oid
                    WHERE n.nspname = 'public' AND p.proname = 'is_helpdesk_for_society'
                ) THEN
                    ALTER FUNCTION public.is_helpdesk_for_society(UUID) SET search_path = public, pg_temp;
                    REVOKE ALL ON FUNCTION public.is_helpdesk_for_society(UUID) FROM PUBLIC;
                    GRANT EXECUTE ON FUNCTION public.is_helpdesk_for_society(UUID) TO authenticated, service_role;
                END IF;
            END $$;
            """
        )

        # Enable RLS on newly created tables
        phase5_tables = [
            "late_fee_policies",
            "late_fee_applications",
            "resident_upi_mappings",
            "safety_alerts",
        ]

        for tbl in phase5_tables:
            op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;")

            # Service role & Postgres superuser full bypass policies
            op.execute(
                f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = '{tbl}' AND policyname = '{tbl}_service_role_all') THEN
                        CREATE POLICY {tbl}_service_role_all ON {tbl}
                        FOR ALL TO service_role
                        USING (true) WITH CHECK (true);
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = '{tbl}' AND policyname = '{tbl}_postgres_all') THEN
                        CREATE POLICY {tbl}_postgres_all ON {tbl}
                        FOR ALL TO postgres
                        USING (true) WITH CHECK (true);
                    END IF;
                END $$;
                """
            )

            # Helpdesk role access policy for society
            op.execute(
                f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = '{tbl}' AND policyname = '{tbl}_helpdesk_access') THEN
                        CREATE POLICY {tbl}_helpdesk_access ON {tbl}
                        FOR ALL TO authenticated
                        USING (public.is_helpdesk_for_society(society_id))
                        WITH CHECK (public.is_helpdesk_for_society(society_id));
                    END IF;
                END $$;
                """
            )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # Drop added columns
    if is_postgres:
        op.execute("DROP INDEX IF EXISTS ix_bank_transactions_payer_vpa;")
    else:
        op.drop_index("ix_bank_transactions_payer_vpa", table_name="bank_transactions")
    op.drop_column("bank_transactions", "payer_vpa")
    op.drop_column("complaints", "category_corrected_by")
    op.drop_column("complaints", "category_corrected_at")
    op.drop_column("complaints", "original_category")

    # Drop tables
    op.drop_table("safety_alerts")
    op.drop_table("resident_upi_mappings")
    op.drop_table("late_fee_applications")
    op.drop_table("late_fee_policies")
