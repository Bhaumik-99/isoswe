"""004_billing_integrity_remediation

Phase 2 Remediation: Financial correctness and database integrity fixes.

1. Unique constraint on billing_configurations (society_id, effective_from)
2. Composite unique constraint on flats (society_id, id) to support cross-society FK enforcement
3. Composite foreign keys with ON DELETE RESTRICT ensuring financial records (invoices, payments, ledger)
   are never dropped when a flat is modified/deleted.
4. Append-only trigger on financial_ledger_entries (prevent UPDATE / DELETE at DB level)
5. Database trigger on payment_allocations enforcing that payment and invoice belong to the same flat and society.

Revision ID: 004_billing_integrity
Revises: 003_maintenance_billing
Create Date: 2026-11-03 18:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "004_billing_integrity"
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
    # 3. Composite FKs with ON DELETE RESTRICT & Invariant Triggers
    # ------------------------------------------------------------------
    if bind.dialect.name == "postgresql":
        # Drop legacy single-column CASCADE foreign keys from migration 003 to ensure
        # historical financial records cannot be deleted with a flat.
        op.execute(
            """
            DO $$
            DECLARE
                r RECORD;
            BEGIN
                FOR r IN (
                    SELECT conname, conrelid::regclass AS table_name
                    FROM pg_constraint
                    WHERE contype = 'f'
                      AND conrelid::regclass::text IN ('invoices', 'payments', 'financial_ledger_entries')
                      AND confrelid::regclass::text = 'flats'
                      AND array_length(conkey, 1) = 1
                ) LOOP
                    EXECUTE 'ALTER TABLE ' || r.table_name || ' DROP CONSTRAINT IF EXISTS ' || quote_ident(r.conname) || ' CASCADE';
                END LOOP;
            END $$;
            """
        )

        # Enforce cross-society foreign keys at database level with ON DELETE RESTRICT
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
                    ON DELETE RESTRICT;
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
                    ON DELETE RESTRICT;
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
            DROP TRIGGER IF EXISTS financial_ledger_immutable ON financial_ledger_entries;
            CREATE TRIGGER financial_ledger_immutable
            BEFORE UPDATE OR DELETE ON financial_ledger_entries
            FOR EACH ROW EXECUTE FUNCTION prevent_ledger_mutation();
            """
        )

        # Database-enforced invariant: payment_allocations must connect payment and invoice of the same flat and society
        op.execute(
            """
            CREATE OR REPLACE FUNCTION validate_payment_allocation_flat_match()
            RETURNS TRIGGER AS $$
            DECLARE
                pay_society UUID;
                pay_flat UUID;
                inv_society UUID;
                inv_flat UUID;
            BEGIN
                SELECT society_id, flat_id INTO pay_society, pay_flat FROM payments WHERE id = NEW.payment_id;
                SELECT society_id, flat_id INTO inv_society, inv_flat FROM invoices WHERE id = NEW.invoice_id;

                IF pay_society IS DISTINCT FROM inv_society THEN
                    RAISE EXCEPTION
                        'Cross-society payment allocation rejected: payment belongs to society %, but invoice belongs to society %',
                        pay_society, inv_society;
                END IF;

                IF pay_flat IS DISTINCT FROM inv_flat THEN
                    RAISE EXCEPTION
                        'Cross-flat payment allocation rejected: payment belongs to flat %, but invoice belongs to flat %',
                        pay_flat, inv_flat;
                END IF;

                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )

        op.execute(
            """
            DROP TRIGGER IF EXISTS trg_payment_allocation_flat_match ON payment_allocations;
            CREATE TRIGGER trg_payment_allocation_flat_match
            BEFORE INSERT OR UPDATE ON payment_allocations
            FOR EACH ROW EXECUTE FUNCTION validate_payment_allocation_flat_match();
            """
        )
    else:
        # SQLite dialect support for cross-flat allocation check
        op.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_payment_allocations_flat_match
            BEFORE INSERT ON payment_allocations
            BEGIN
                SELECT CASE
                    WHEN (SELECT flat_id FROM payments WHERE id = NEW.payment_id) != (SELECT flat_id FROM invoices WHERE id = NEW.invoice_id)
                    THEN RAISE(ABORT, 'Cross-flat payment allocation rejected: payment and invoice flat_id do not match')
                    WHEN (SELECT society_id FROM payments WHERE id = NEW.payment_id) != (SELECT society_id FROM invoices WHERE id = NEW.invoice_id)
                    THEN RAISE(ABORT, 'Cross-society payment allocation rejected: payment and invoice society_id do not match')
                END;
            END;
            """
        )


def downgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS trg_payment_allocation_flat_match ON payment_allocations;"
        )
        op.execute("DROP FUNCTION IF EXISTS validate_payment_allocation_flat_match();")
        op.execute("DROP TRIGGER IF EXISTS financial_ledger_immutable ON financial_ledger_entries;")
        op.execute("DROP FUNCTION IF EXISTS prevent_ledger_mutation();")
        op.execute(
            "ALTER TABLE financial_ledger_entries DROP CONSTRAINT IF EXISTS fk_ledger_flats_composite;"
        )
        op.execute("ALTER TABLE payments DROP CONSTRAINT IF EXISTS fk_payments_flats_composite;")
        op.execute("ALTER TABLE invoices DROP CONSTRAINT IF EXISTS fk_invoices_flats_composite;")
        op.execute("ALTER TABLE flats DROP CONSTRAINT IF EXISTS uq_flats_society_id CASCADE;")
        op.execute(
            "ALTER TABLE billing_configurations DROP CONSTRAINT IF EXISTS uq_billing_config_society_effective_from CASCADE;"
        )
    else:
        op.execute("DROP TRIGGER IF EXISTS trg_payment_allocations_flat_match;")
        with op.batch_alter_table("flats") as batch_op:
            batch_op.drop_constraint("uq_flats_society_id", type_="unique")

        with op.batch_alter_table("billing_configurations") as batch_op:
            batch_op.drop_constraint("uq_billing_config_society_effective_from", type_="unique")
