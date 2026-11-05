"""009_reconciliation_allocation_tenant_integrity

Phase 4 Integrity Fix: Reconciliation Allocation Tenant and Payment Integrity.

1. In PostgreSQL:
   - Composite unique constraints:
     - invoices (society_id, id)
     - payments (society_id, id)
     - bank_transactions (society_id, id)
   - Composite foreign keys on reconciliation_allocations:
     - (society_id, transaction_id) -> bank_transactions (society_id, id)
     - (society_id, invoice_id) -> invoices (society_id, id)
     - (society_id, payment_id) -> payments (society_id, id)
   - Database trigger on reconciliation_allocations enforcing:
     - Transaction, invoice, and payment belong to the exact same society
     - Payment and invoice belong to the exact same flat (zero cross-flat link)
     - Payment allocation belongs to the exact payment and invoice

2. In SQLite:
   - Database triggers on reconciliation_allocations enforcing:
     - Transaction, invoice, and payment belong to the exact same society
     - Payment and invoice belong to the exact same flat (zero cross-flat link)
     - Payment allocation belongs to the exact payment and invoice

Revision ID: 009_recon_tenant_integrity
Revises: 008_bank_reconciliation
Create Date: 2026-11-05 18:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "009_recon_tenant_integrity"
down_revision: str | None = "008_bank_reconciliation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        # 1. Composite unique constraints on parent entities in PostgreSQL
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'uq_invoices_society_id'
                ) THEN
                    ALTER TABLE invoices ADD CONSTRAINT uq_invoices_society_id UNIQUE (society_id, id);
                END IF;

                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'uq_payments_society_id'
                ) THEN
                    ALTER TABLE payments ADD CONSTRAINT uq_payments_society_id UNIQUE (society_id, id);
                END IF;

                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'uq_bank_transactions_society_id'
                ) THEN
                    ALTER TABLE bank_transactions ADD CONSTRAINT uq_bank_transactions_society_id UNIQUE (society_id, id);
                END IF;

                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'fk_recon_alloc_txn_composite'
                ) THEN
                    ALTER TABLE reconciliation_allocations
                    ADD CONSTRAINT fk_recon_alloc_txn_composite
                    FOREIGN KEY (society_id, transaction_id) REFERENCES bank_transactions (society_id, id)
                    ON DELETE RESTRICT;
                END IF;

                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'fk_recon_alloc_inv_composite'
                ) THEN
                    ALTER TABLE reconciliation_allocations
                    ADD CONSTRAINT fk_recon_alloc_inv_composite
                    FOREIGN KEY (society_id, invoice_id) REFERENCES invoices (society_id, id)
                    ON DELETE RESTRICT;
                END IF;

                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'fk_recon_alloc_pay_composite'
                ) THEN
                    ALTER TABLE reconciliation_allocations
                    ADD CONSTRAINT fk_recon_alloc_pay_composite
                    FOREIGN KEY (society_id, payment_id) REFERENCES payments (society_id, id)
                    ON DELETE RESTRICT;
                END IF;
            END $$;
            """
        )

        op.execute(
            """
            CREATE OR REPLACE FUNCTION validate_reconciliation_allocation_tenant_integrity()
            RETURNS TRIGGER AS $$
            DECLARE
                txn_soc UUID;
                inv_soc UUID;
                inv_flt UUID;
                pay_soc UUID;
                pay_flt UUID;
                pa_pay UUID;
                pa_inv UUID;
            BEGIN
                -- 1. Validate transaction society
                SELECT society_id INTO txn_soc FROM bank_transactions WHERE id = NEW.transaction_id;
                IF txn_soc IS DISTINCT FROM NEW.society_id THEN
                    RAISE EXCEPTION
                        'Cross-society reconciliation allocation rejected: transaction belongs to society %, but allocation is for society %',
                        txn_soc, NEW.society_id;
                END IF;

                -- 2. Validate invoice society
                SELECT society_id, flat_id INTO inv_soc, inv_flt FROM invoices WHERE id = NEW.invoice_id;
                IF inv_soc IS DISTINCT FROM NEW.society_id THEN
                    RAISE EXCEPTION
                        'Cross-society reconciliation allocation rejected: invoice belongs to society %, but allocation is for society %',
                        inv_soc, NEW.society_id;
                END IF;

                -- 3. If payment_id is provided, validate payment society & flat match with invoice
                IF NEW.payment_id IS NOT NULL THEN
                    SELECT society_id, flat_id INTO pay_soc, pay_flt FROM payments WHERE id = NEW.payment_id;
                    IF pay_soc IS DISTINCT FROM NEW.society_id THEN
                        RAISE EXCEPTION
                            'Cross-society reconciliation allocation rejected: payment belongs to society %, but allocation is for society %',
                            pay_soc, NEW.society_id;
                    END IF;
                    IF pay_flt IS DISTINCT FROM inv_flt THEN
                        RAISE EXCEPTION
                            'Cross-flat reconciliation allocation rejected: payment belongs to flat %, but invoice belongs to flat %',
                            pay_flt, inv_flt;
                    END IF;
                END IF;

                -- 4. If payment_allocation_id is provided, validate payment_id and invoice_id consistency
                IF NEW.payment_allocation_id IS NOT NULL THEN
                    SELECT payment_id, invoice_id INTO pa_pay, pa_inv FROM payment_allocations WHERE id = NEW.payment_allocation_id;
                    IF pa_pay IS DISTINCT FROM NEW.payment_id THEN
                        RAISE EXCEPTION
                            'Mismatched payment allocation rejected: allocation belongs to payment %, but record specifies payment %',
                            pa_pay, NEW.payment_id;
                    END IF;
                    IF pa_inv IS DISTINCT FROM NEW.invoice_id THEN
                        RAISE EXCEPTION
                            'Mismatched payment allocation invoice rejected: allocation is for invoice %, but record specifies invoice %',
                            pa_inv, NEW.invoice_id;
                    END IF;
                END IF;

                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )

        op.execute(
            """
            DROP TRIGGER IF EXISTS trg_reconciliation_allocation_tenant_integrity ON reconciliation_allocations;
            CREATE TRIGGER trg_reconciliation_allocation_tenant_integrity
            BEFORE INSERT OR UPDATE ON reconciliation_allocations
            FOR EACH ROW EXECUTE FUNCTION validate_reconciliation_allocation_tenant_integrity();
            """
        )
    else:
        # SQLite triggers for cross-tenant and payment allocation integrity
        op.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_recon_allocations_tenant_integrity_insert
            BEFORE INSERT ON reconciliation_allocations
            BEGIN
                SELECT CASE
                    WHEN (SELECT society_id FROM bank_transactions WHERE id = NEW.transaction_id) != NEW.society_id
                    THEN RAISE(ABORT, 'Cross-society reconciliation allocation rejected: transaction and allocation society_id do not match')
                    WHEN (SELECT society_id FROM invoices WHERE id = NEW.invoice_id) != NEW.society_id
                    THEN RAISE(ABORT, 'Cross-society reconciliation allocation rejected: invoice and allocation society_id do not match')
                    WHEN NEW.payment_id IS NOT NULL AND (SELECT society_id FROM payments WHERE id = NEW.payment_id) != NEW.society_id
                    THEN RAISE(ABORT, 'Cross-society reconciliation allocation rejected: payment and allocation society_id do not match')
                    WHEN NEW.payment_id IS NOT NULL AND (SELECT flat_id FROM payments WHERE id = NEW.payment_id) != (SELECT flat_id FROM invoices WHERE id = NEW.invoice_id)
                    THEN RAISE(ABORT, 'Cross-flat reconciliation allocation rejected: payment and invoice flat_id do not match')
                    WHEN NEW.payment_allocation_id IS NOT NULL AND (SELECT payment_id FROM payment_allocations WHERE id = NEW.payment_allocation_id) != NEW.payment_id
                    THEN RAISE(ABORT, 'Mismatched payment allocation rejected: allocation does not belong to specified payment')
                    WHEN NEW.payment_allocation_id IS NOT NULL AND (SELECT invoice_id FROM payment_allocations WHERE id = NEW.payment_allocation_id) != NEW.invoice_id
                    THEN RAISE(ABORT, 'Mismatched payment allocation rejected: allocation does not belong to specified invoice')
                END;
            END;
            """
        )
        op.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_recon_allocations_tenant_integrity_update
            BEFORE UPDATE ON reconciliation_allocations
            BEGIN
                SELECT CASE
                    WHEN (SELECT society_id FROM bank_transactions WHERE id = NEW.transaction_id) != NEW.society_id
                    THEN RAISE(ABORT, 'Cross-society reconciliation allocation rejected: transaction and allocation society_id do not match')
                    WHEN (SELECT society_id FROM invoices WHERE id = NEW.invoice_id) != NEW.society_id
                    THEN RAISE(ABORT, 'Cross-society reconciliation allocation rejected: invoice and allocation society_id do not match')
                    WHEN NEW.payment_id IS NOT NULL AND (SELECT society_id FROM payments WHERE id = NEW.payment_id) != NEW.society_id
                    THEN RAISE(ABORT, 'Cross-society reconciliation allocation rejected: payment and allocation society_id do not match')
                    WHEN NEW.payment_id IS NOT NULL AND (SELECT flat_id FROM payments WHERE id = NEW.payment_id) != (SELECT flat_id FROM invoices WHERE id = NEW.invoice_id)
                    THEN RAISE(ABORT, 'Cross-flat reconciliation allocation rejected: payment and invoice flat_id do not match')
                    WHEN NEW.payment_allocation_id IS NOT NULL AND (SELECT payment_id FROM payment_allocations WHERE id = NEW.payment_allocation_id) != NEW.payment_id
                    THEN RAISE(ABORT, 'Mismatched payment allocation rejected: allocation does not belong to specified payment')
                    WHEN NEW.payment_allocation_id IS NOT NULL AND (SELECT invoice_id FROM payment_allocations WHERE id = NEW.payment_allocation_id) != NEW.invoice_id
                    THEN RAISE(ABORT, 'Mismatched payment allocation rejected: allocation does not belong to specified invoice')
                END;
            END;
            """
        )


def downgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS trg_reconciliation_allocation_tenant_integrity ON reconciliation_allocations;"
        )
        op.execute("DROP FUNCTION IF EXISTS validate_reconciliation_allocation_tenant_integrity();")
        op.execute(
            "ALTER TABLE reconciliation_allocations DROP CONSTRAINT IF EXISTS fk_recon_alloc_pay_composite;"
        )
        op.execute(
            "ALTER TABLE reconciliation_allocations DROP CONSTRAINT IF EXISTS fk_recon_alloc_inv_composite;"
        )
        op.execute(
            "ALTER TABLE reconciliation_allocations DROP CONSTRAINT IF EXISTS fk_recon_alloc_txn_composite;"
        )
        op.execute(
            "ALTER TABLE bank_transactions DROP CONSTRAINT IF EXISTS uq_bank_transactions_society_id CASCADE;"
        )
        op.execute("ALTER TABLE payments DROP CONSTRAINT IF EXISTS uq_payments_society_id CASCADE;")
        op.execute("ALTER TABLE invoices DROP CONSTRAINT IF EXISTS uq_invoices_society_id CASCADE;")
    else:
        op.execute("DROP TRIGGER IF EXISTS trg_recon_allocations_tenant_integrity_update;")
        op.execute("DROP TRIGGER IF EXISTS trg_recon_allocations_tenant_integrity_insert;")
