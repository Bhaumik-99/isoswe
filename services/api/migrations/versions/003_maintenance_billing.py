"""003_maintenance_billing

Creates tables for Phase 2 Maintenance Billing & Payment Foundation:
1. billing_configurations (Society rate and due date settings)
2. invoices (Monthly maintenance bills)
3. invoice_line_items (Itemized invoice charges)
4. payments (Simulated payments and records)
5. payment_allocations (Mapping payments to invoices)
6. financial_ledger_entries (Append-only immutable financial audit ledger)
7. billing_runs (Batch monthly billing logs)

Also establishes PostgreSQL Row Level Security (RLS) policies and forces RLS.

Revision ID: 003_maintenance_billing
Revises: 002_supabase_auth_and_rls
Create Date: 2026-11-03 03:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003_maintenance_billing"
down_revision: str | None = "002_supabase_auth_and_rls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. billing_configurations
    op.create_table(
        "billing_configurations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("society_id", sa.Uuid(), nullable=False),
        sa.Column("rate_paise_per_sqft", sa.BigInteger(), nullable=False, server_default="650"),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="INR"),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_day", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["society_id"], ["societies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("rate_paise_per_sqft > 0", name="chk_billing_config_rate_positive"),
        sa.CheckConstraint("due_day >= 1 AND due_day <= 28", name="chk_billing_config_due_day"),
    )
    op.create_index(
        "ix_billing_configurations_society_id", "billing_configurations", ["society_id"]
    )
    op.create_index(
        "ix_billing_config_society_effective",
        "billing_configurations",
        ["society_id", "effective_from"],
    )

    # 2. invoices
    op.create_table(
        "invoices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("society_id", sa.Uuid(), nullable=False),
        sa.Column("flat_id", sa.Uuid(), nullable=False),
        sa.Column("billing_period", sa.String(length=7), nullable=False),
        sa.Column("invoice_number", sa.String(length=64), nullable=False),
        sa.Column("area_sqft_snapshot", sa.Integer(), nullable=False),
        sa.Column("rate_paise_per_sqft_snapshot", sa.BigInteger(), nullable=False),
        sa.Column("subtotal_paise", sa.BigInteger(), nullable=False),
        sa.Column("total_paise", sa.BigInteger(), nullable=False),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="UNPAID"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["society_id"], ["societies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["flat_id"], ["flats.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "society_id", "flat_id", "billing_period", name="uq_invoice_society_flat_period"
        ),
        sa.UniqueConstraint("society_id", "invoice_number", name="uq_invoice_society_number"),
        sa.CheckConstraint("total_paise >= 0", name="chk_invoice_total_positive"),
        sa.CheckConstraint("subtotal_paise >= 0", name="chk_invoice_subtotal_positive"),
        sa.CheckConstraint("area_sqft_snapshot > 0", name="chk_invoice_area_positive"),
        sa.CheckConstraint("rate_paise_per_sqft_snapshot > 0", name="chk_invoice_rate_positive"),
    )
    op.create_index("ix_invoices_society_id", "invoices", ["society_id"])
    op.create_index("ix_invoices_flat_id", "invoices", ["flat_id"])
    op.create_index("ix_invoices_status", "invoices", ["status"])
    op.create_index("ix_invoices_society_period", "invoices", ["society_id", "billing_period"])
    op.create_index("ix_invoices_flat_period", "invoices", ["flat_id", "billing_period"])
    op.create_index("ix_invoices_flat_status", "invoices", ["flat_id", "status"])

    # 3. invoice_line_items
    op.create_table(
        "invoice_line_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unit_rate_paise", sa.BigInteger(), nullable=False),
        sa.Column("amount_paise", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("amount_paise >= 0", name="chk_line_item_amount_positive"),
        sa.CheckConstraint("quantity > 0", name="chk_line_item_quantity_positive"),
    )
    op.create_index("ix_invoice_line_items_invoice_id", "invoice_line_items", ["invoice_id"])

    # 4. payments
    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("society_id", sa.Uuid(), nullable=False),
        sa.Column("flat_id", sa.Uuid(), nullable=False),
        sa.Column("amount_paise", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="INR"),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="SIMULATED"),
        sa.Column("provider_reference", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("initiated_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["society_id"], ["societies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["flat_id"], ["flats.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["initiated_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_reference", name="uq_payment_provider_reference"),
        sa.CheckConstraint("amount_paise > 0", name="chk_payment_amount_positive"),
    )
    op.create_index("ix_payments_society_id", "payments", ["society_id"])
    op.create_index("ix_payments_flat_id", "payments", ["flat_id"])
    op.create_index("ix_payments_status", "payments", ["status"])
    op.create_index("ix_payments_initiated_by", "payments", ["initiated_by"])
    op.create_index("ix_payments_society_flat", "payments", ["society_id", "flat_id"])

    # 5. payment_allocations
    op.create_table(
        "payment_allocations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("allocated_paise", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_id", "invoice_id", name="uq_payment_invoice_allocation"),
        sa.CheckConstraint("allocated_paise > 0", name="chk_allocation_amount_positive"),
    )
    op.create_index("ix_payment_allocations_payment_id", "payment_allocations", ["payment_id"])
    op.create_index("ix_payment_allocations_invoice_id", "payment_allocations", ["invoice_id"])

    # 6. financial_ledger_entries
    op.create_table(
        "financial_ledger_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("society_id", sa.Uuid(), nullable=False),
        sa.Column("flat_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=True),
        sa.Column("payment_id", sa.Uuid(), nullable=True),
        sa.Column("entry_type", sa.String(length=32), nullable=False),
        sa.Column("amount_paise", sa.BigInteger(), nullable=False),
        sa.Column("reference_id", sa.String(length=128), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["society_id"], ["societies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["flat_id"], ["flats.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("amount_paise > 0", name="chk_ledger_amount_positive"),
    )
    op.create_index(
        "ix_financial_ledger_entries_society_id", "financial_ledger_entries", ["society_id"]
    )
    op.create_index("ix_financial_ledger_entries_flat_id", "financial_ledger_entries", ["flat_id"])
    op.create_index(
        "ix_financial_ledger_entries_invoice_id", "financial_ledger_entries", ["invoice_id"]
    )
    op.create_index(
        "ix_financial_ledger_entries_payment_id", "financial_ledger_entries", ["payment_id"]
    )
    op.create_index(
        "ix_financial_ledger_entries_entry_type", "financial_ledger_entries", ["entry_type"]
    )
    op.create_index("ix_ledger_society_flat", "financial_ledger_entries", ["society_id", "flat_id"])
    op.create_index(
        "ix_ledger_society_type", "financial_ledger_entries", ["society_id", "entry_type"]
    )

    # 7. billing_runs
    op.create_table(
        "billing_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("society_id", sa.Uuid(), nullable=False),
        sa.Column("billing_period", sa.String(length=7), nullable=False),
        sa.Column("total_eligible_flats", sa.Integer(), nullable=False),
        sa.Column("total_invoiced_flats", sa.Integer(), nullable=False),
        sa.Column("total_skipped_flats", sa.Integer(), nullable=False),
        sa.Column("total_charges_paise", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="COMPLETED"),
        sa.Column("initiated_by", sa.Uuid(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["society_id"], ["societies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["initiated_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_billing_runs_society_id", "billing_runs", ["society_id"])
    op.create_index(
        "ix_billing_runs_society_period", "billing_runs", ["society_id", "billing_period"]
    )

    # PostgreSQL Row Level Security (RLS)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        billing_tables = [
            "billing_configurations",
            "invoices",
            "invoice_line_items",
            "payments",
            "payment_allocations",
            "financial_ledger_entries",
            "billing_runs",
        ]
        for tbl in billing_tables:
            op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;")

        # Service role bypass / full access
        for tbl in billing_tables:
            op.execute(
                f"""
                CREATE POLICY {tbl}_service_role_all ON {tbl}
                FOR ALL TO service_role
                USING (true) WITH CHECK (true);
                """
            )
            op.execute(
                f"""
                CREATE POLICY {tbl}_postgres_all ON {tbl}
                FOR ALL TO postgres
                USING (true) WITH CHECK (true);
                """
            )

        # Authenticated Resident Policies
        # 1. Invoices
        op.execute(
            """
            CREATE POLICY invoices_resident_select ON invoices
            FOR SELECT TO authenticated
            USING (
                flat_id IN (
                    SELECT fm.flat_id FROM flat_memberships fm
                    JOIN users u ON u.id = fm.user_id
                    WHERE u.supabase_uid = auth.uid()
                    AND fm.status = 'APPROVED'
                    AND fm.valid_from <= CURRENT_TIMESTAMP
                    AND (fm.valid_until IS NULL OR fm.valid_until >= CURRENT_TIMESTAMP)
                )
            );
            """
        )

        # 2. Invoice Line Items
        op.execute(
            """
            CREATE POLICY invoice_line_items_resident_select ON invoice_line_items
            FOR SELECT TO authenticated
            USING (
                invoice_id IN (
                    SELECT inv.id FROM invoices inv
                    JOIN flat_memberships fm ON fm.flat_id = inv.flat_id
                    JOIN users u ON u.id = fm.user_id
                    WHERE u.supabase_uid = auth.uid()
                    AND fm.status = 'APPROVED'
                    AND fm.valid_from <= CURRENT_TIMESTAMP
                    AND (fm.valid_until IS NULL OR fm.valid_until >= CURRENT_TIMESTAMP)
                )
            );
            """
        )

        # 3. Payments
        op.execute(
            """
            CREATE POLICY payments_resident_select ON payments
            FOR SELECT TO authenticated
            USING (
                flat_id IN (
                    SELECT fm.flat_id FROM flat_memberships fm
                    JOIN users u ON u.id = fm.user_id
                    WHERE u.supabase_uid = auth.uid()
                    AND fm.status = 'APPROVED'
                    AND fm.valid_from <= CURRENT_TIMESTAMP
                    AND (fm.valid_until IS NULL OR fm.valid_until >= CURRENT_TIMESTAMP)
                )
            );
            """
        )

        # 4. Payment Allocations
        op.execute(
            """
            CREATE POLICY payment_allocations_resident_select ON payment_allocations
            FOR SELECT TO authenticated
            USING (
                invoice_id IN (
                    SELECT inv.id FROM invoices inv
                    JOIN flat_memberships fm ON fm.flat_id = inv.flat_id
                    JOIN users u ON u.id = fm.user_id
                    WHERE u.supabase_uid = auth.uid()
                    AND fm.status = 'APPROVED'
                    AND fm.valid_from <= CURRENT_TIMESTAMP
                    AND (fm.valid_until IS NULL OR fm.valid_until >= CURRENT_TIMESTAMP)
                )
            );
            """
        )

        # 5. Financial Ledger Entries
        op.execute(
            """
            CREATE POLICY financial_ledger_resident_select ON financial_ledger_entries
            FOR SELECT TO authenticated
            USING (
                flat_id IN (
                    SELECT fm.flat_id FROM flat_memberships fm
                    JOIN users u ON u.id = fm.user_id
                    WHERE u.supabase_uid = auth.uid()
                    AND fm.status = 'APPROVED'
                    AND fm.valid_from <= CURRENT_TIMESTAMP
                    AND (fm.valid_until IS NULL OR fm.valid_until >= CURRENT_TIMESTAMP)
                )
            );
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    billing_tables = [
        "billing_runs",
        "financial_ledger_entries",
        "payment_allocations",
        "payments",
        "invoice_line_items",
        "invoices",
        "billing_configurations",
    ]

    if bind.dialect.name == "postgresql":
        for tbl in billing_tables:
            op.execute(f"DROP POLICY IF EXISTS {tbl}_service_role_all ON {tbl};")
            op.execute(f"DROP POLICY IF EXISTS {tbl}_postgres_all ON {tbl};")

        op.execute("DROP POLICY IF EXISTS invoices_resident_select ON invoices;")
        op.execute(
            "DROP POLICY IF EXISTS invoice_line_items_resident_select ON invoice_line_items;"
        )
        op.execute("DROP POLICY IF EXISTS payments_resident_select ON payments;")
        op.execute(
            "DROP POLICY IF EXISTS payment_allocations_resident_select ON payment_allocations;"
        )
        op.execute(
            "DROP POLICY IF EXISTS financial_ledger_resident_select ON financial_ledger_entries;"
        )

        for tbl in billing_tables:
            op.execute(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY;")

    for tbl in billing_tables:
        op.drop_table(tbl)
