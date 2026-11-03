"""004_billing_integrity_remediation

Phase 2 Remediation: Financial correctness and database integrity fixes.

1. Unique constraint on billing_configurations (society_id, effective_from)
2. Composite unique constraint on flats (society_id, id) to support cross-society FK enforcement
3. Composite foreign keys ensuring invoices, payments, and ledger entries belong to the flat's society
4. Append-only trigger on financial_ledger_entries (prevent UPDATE / DELETE at DB level)

Revision ID: 004_billing_integrity_remediation
Revises: 003_maintenance_billing
Create Date: 2026-11-03 18:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "004_billing_integrity_remediation"
down_revision: str | None = "003_maintenance_billing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    # ------------------------------------------------------------------
    # 1. Unique constraint on billing_configurations (society_id, effective_from)
    #    Prevents ambiguous configuration look-ups when selecting by period.
    # ------------------------------------------------------------------
    with op.batch_alter_table("billing_configurations") as batch_op:
        batch_op.create_unique_constraint(
            "uq_billing_config_society_effective_from",
            ["society_id", "effective_from"],
        )

    # ------------------------------------------------------------------
    # 2. Composite unique constraint on flats (society_id, id)
    #    Guarantees flat ownership can be validated via composite FKs.
    # ------------------------------------------------------------------
    with op.batch_alter_table("flats") as batch_op:
        batch_op.create_unique_constraint(
            "uq_flats_society_id",
            ["society_id", "id"],
        )

    # ------------------------------------------------------------------
    # 3. Composite FKs & Append-Only Trigger for PostgreSQL
    # ------------------------------------------------------------------
    if bind.dialect.name == "postgresql":
        # Enforce cross-society foreign keys at database level
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'fk_invoices_flats_composite'
                ) THEN
                    ALTER TABLE invoices
                    ADD CONSTRAINT fk_invoices_flats_composite
                    FOREIGN KEY (society_id, flat_id) REFERENCES flats (society_id, id)
                    ON DELETE CASCADE;
                END IF;
            END $$;
            """
        )

        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'fk_payments_flats_composite'
                ) THEN
                    ALTER TABLE payments
                    ADD CONSTRAINT fk_payments_flats_composite
                    FOREIGN KEY (society_id, flat_id) REFERENCES flats (society_id, id)
                    ON DELETE CASCADE;
                END IF;
            END $$;
            """
        )

        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'fk_ledger_flats_composite'
                ) THEN
                    ALTER TABLE financial_ledger_entries
                    ADD CONSTRAINT fk_ledger_flats_composite
                    FOREIGN KEY (society_id, flat_id) REFERENCES flats (society_id, id)
                    ON DELETE RESTRICT;
                END IF;
            END $$;
            """
        )

        # Append-only ledger trigger: rejects UPDATE and DELETE
        op.execute(
            """
            CREATE OR REPLACE FUNCTION prevent_ledger_mutation()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION
                    'Financial ledger entries are immutable. '
                    'Corrections must use compensating REVERSAL or ADJUSTMENT entries. '
                    'Attempted operation: % on row id=%', TG_OP, OLD.id;
            END;
            $$ LANGUAGE plpgsql;
            """
        )

        op.execute(
            """
            CREATE TRIGGER financial_ledger_immutable
            BEFORE UPDATE OR DELETE ON financial_ledger_entries
            FOR EACH ROW EXECUTE FUNCTION prevent_ledger_mutation();
            """
        )


def downgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS financial_ledger_immutable ON financial_ledger_entries;")
        op.execute("DROP FUNCTION IF EXISTS prevent_ledger_mutation();")
        op.execute(
            "ALTER TABLE financial_ledger_entries DROP CONSTRAINT IF EXISTS fk_ledger_flats_composite;"
        )
        op.execute("ALTER TABLE payments DROP CONSTRAINT IF EXISTS fk_payments_flats_composite;")
        op.execute("ALTER TABLE invoices DROP CONSTRAINT IF EXISTS fk_invoices_flats_composite;")

    with op.batch_alter_table("flats") as batch_op:
        batch_op.drop_constraint("uq_flats_society_id", type_="unique")

    with op.batch_alter_table("billing_configurations") as batch_op:
        batch_op.drop_constraint("uq_billing_config_society_effective_from", type_="unique")
