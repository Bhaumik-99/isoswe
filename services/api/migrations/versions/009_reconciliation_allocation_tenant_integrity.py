"""009_reconciliation_allocation_tenant_integrity

Phase 4 Security & Integrity Fix:
1. Row-Level Security (RLS) on all 5 Bank Reconciliation tables:
   - bank_statement_imports
   - bank_transactions
   - reconciliation_matches
   - reconciliation_reviews
   - reconciliation_allocations
   Enables and FORCES RLS, creates service_role and postgres bypass policies,
   and establishes tenant-scoped policies:
   - Helpdesk staff can select reconciliation records for their authorized societies
   - Residents can select reconciliation allocations for their own approved flat invoices
   - Direct writes by authenticated users without service_role are blocked

2. Composite Unique Constraints & Foreign Keys in PostgreSQL enforcing multi-tenant integrity:
   - invoices (society_id, id)
   - payments (society_id, id)
   - bank_statement_imports (society_id, id)
   - bank_transactions (society_id, id)
   - reconciliation_matches (society_id, id)
   - reconciliation_reviews (society_id, id)
   - bank_transactions (society_id, import_id) -> bank_statement_imports (society_id, id)
   - bank_transactions (society_id, duplicate_of_id) -> bank_transactions (society_id, id)
   - reconciliation_matches (society_id, transaction_id) -> bank_transactions (society_id, id)
   - reconciliation_matches (society_id, flat_id) -> flats (society_id, id)
   - reconciliation_matches (society_id, invoice_id) -> invoices (society_id, id)
   - reconciliation_matches (society_id, existing_payment_id) -> payments (society_id, id)
   - reconciliation_reviews (society_id, transaction_id) -> bank_transactions (society_id, id)
   - reconciliation_allocations (society_id, transaction_id) -> bank_transactions (society_id, id)
   - reconciliation_allocations (society_id, invoice_id) -> invoices (society_id, id)
   - reconciliation_allocations (society_id, payment_id) -> payments (society_id, id)

3. Database Triggers (PostgreSQL and SQLite) preventing cross-society and cross-flat allocation links.

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

RECON_TABLES = [
    "bank_statement_imports",
    "bank_transactions",
    "reconciliation_matches",
    "reconciliation_reviews",
    "reconciliation_allocations",
]


def upgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        # -----------------------------------------------------------------
        # 1. Composite Unique Constraints on Parent and Child Entities
        # -----------------------------------------------------------------
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_invoices_society_id') THEN
                    ALTER TABLE invoices ADD CONSTRAINT uq_invoices_society_id UNIQUE (society_id, id);
                END IF;

                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_payments_society_id') THEN
                    ALTER TABLE payments ADD CONSTRAINT uq_payments_society_id UNIQUE (society_id, id);
                END IF;

                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_bank_statement_imports_society_id') THEN
                    ALTER TABLE bank_statement_imports ADD CONSTRAINT uq_bank_statement_imports_society_id UNIQUE (society_id, id);
                END IF;

                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_bank_transactions_society_id') THEN
                    ALTER TABLE bank_transactions ADD CONSTRAINT uq_bank_transactions_society_id UNIQUE (society_id, id);
                END IF;

                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_reconciliation_matches_society_id') THEN
                    ALTER TABLE reconciliation_matches ADD CONSTRAINT uq_reconciliation_matches_society_id UNIQUE (society_id, id);
                END IF;

                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_reconciliation_reviews_society_id') THEN
                    ALTER TABLE reconciliation_reviews ADD CONSTRAINT uq_reconciliation_reviews_society_id UNIQUE (society_id, id);
                END IF;
            END $$;
            """
        )

        # -----------------------------------------------------------------
        # 2. Composite Foreign Keys Enforcing Multi-Tenant Cross-Table Isolation
        # -----------------------------------------------------------------
        op.execute(
            """
            DO $$
            BEGIN
                -- bank_transactions -> bank_statement_imports
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_bank_txns_import_composite') THEN
                    ALTER TABLE bank_transactions
                    ADD CONSTRAINT fk_bank_txns_import_composite
                    FOREIGN KEY (society_id, import_id) REFERENCES bank_statement_imports (society_id, id)
                    ON DELETE CASCADE;
                END IF;

                -- bank_transactions duplicate self-reference
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_bank_txns_duplicate_composite') THEN
                    ALTER TABLE bank_transactions
                    ADD CONSTRAINT fk_bank_txns_duplicate_composite
                    FOREIGN KEY (society_id, duplicate_of_id) REFERENCES bank_transactions (society_id, id)
                    ON DELETE SET NULL;
                END IF;

                -- reconciliation_matches -> bank_transactions
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_recon_matches_txn_composite') THEN
                    ALTER TABLE reconciliation_matches
                    ADD CONSTRAINT fk_recon_matches_txn_composite
                    FOREIGN KEY (society_id, transaction_id) REFERENCES bank_transactions (society_id, id)
                    ON DELETE CASCADE;
                END IF;

                -- reconciliation_matches -> flats
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_recon_matches_flat_composite') THEN
                    ALTER TABLE reconciliation_matches
                    ADD CONSTRAINT fk_recon_matches_flat_composite
                    FOREIGN KEY (society_id, flat_id) REFERENCES flats (society_id, id)
                    ON DELETE RESTRICT;
                END IF;

                -- reconciliation_matches -> invoices
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_recon_matches_invoice_composite') THEN
                    ALTER TABLE reconciliation_matches
                    ADD CONSTRAINT fk_recon_matches_invoice_composite
                    FOREIGN KEY (society_id, invoice_id) REFERENCES invoices (society_id, id)
                    ON DELETE SET NULL;
                END IF;

                -- reconciliation_matches -> payments
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_recon_matches_payment_composite') THEN
                    ALTER TABLE reconciliation_matches
                    ADD CONSTRAINT fk_recon_matches_payment_composite
                    FOREIGN KEY (society_id, existing_payment_id) REFERENCES payments (society_id, id)
                    ON DELETE SET NULL;
                END IF;

                -- reconciliation_reviews -> bank_transactions
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_recon_reviews_txn_composite') THEN
                    ALTER TABLE reconciliation_reviews
                    ADD CONSTRAINT fk_recon_reviews_txn_composite
                    FOREIGN KEY (society_id, transaction_id) REFERENCES bank_transactions (society_id, id)
                    ON DELETE CASCADE;
                END IF;

                -- reconciliation_allocations -> bank_transactions
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_recon_alloc_txn_composite') THEN
                    ALTER TABLE reconciliation_allocations
                    ADD CONSTRAINT fk_recon_alloc_txn_composite
                    FOREIGN KEY (society_id, transaction_id) REFERENCES bank_transactions (society_id, id)
                    ON DELETE RESTRICT;
                END IF;

                -- reconciliation_allocations -> invoices
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_recon_alloc_inv_composite') THEN
                    ALTER TABLE reconciliation_allocations
                    ADD CONSTRAINT fk_recon_alloc_inv_composite
                    FOREIGN KEY (society_id, invoice_id) REFERENCES invoices (society_id, id)
                    ON DELETE RESTRICT;
                END IF;

                -- reconciliation_allocations -> payments
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_recon_alloc_pay_composite') THEN
                    ALTER TABLE reconciliation_allocations
                    ADD CONSTRAINT fk_recon_alloc_pay_composite
                    FOREIGN KEY (society_id, payment_id) REFERENCES payments (society_id, id)
                    ON DELETE RESTRICT;
                END IF;
            END $$;
            """
        )

        # -----------------------------------------------------------------
        # 3. PostgreSQL Row Level Security (RLS) on all 5 Reconciliation Tables
        # -----------------------------------------------------------------
        # Grant table access in postgres if roles exist
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                    GRANT SELECT ON bank_statement_imports TO authenticated;
                    GRANT SELECT ON bank_transactions TO authenticated;
                    GRANT SELECT ON reconciliation_matches TO authenticated;
                    GRANT SELECT ON reconciliation_reviews TO authenticated;
                    GRANT SELECT ON reconciliation_allocations TO authenticated;
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
                    GRANT ALL ON bank_statement_imports TO service_role;
                    GRANT ALL ON bank_transactions TO service_role;
                    GRANT ALL ON reconciliation_matches TO service_role;
                    GRANT ALL ON reconciliation_reviews TO service_role;
                    GRANT ALL ON reconciliation_allocations TO service_role;
                END IF;
            END $$;
            """
        )

        for tbl in RECON_TABLES:
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

        # Tenant-scoped authenticated policies for Helpdesk Staff:
        # Helpdesk users can only view reconciliation records for societies where they possess the HELPDESK role
        for tbl in [
            "bank_statement_imports",
            "bank_transactions",
            "reconciliation_matches",
            "reconciliation_reviews",
            "reconciliation_allocations",
        ]:
            op.execute(
                f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = '{tbl}' AND policyname = '{tbl}_helpdesk_select') THEN
                        CREATE POLICY {tbl}_helpdesk_select ON {tbl}
                        FOR SELECT TO authenticated
                        USING (
                            society_id IN (
                                SELECT ur.society_id FROM user_roles ur
                                JOIN users u ON u.id = ur.user_id
                                WHERE u.supabase_uid = auth.uid()
                                AND ur.role = 'HELPDESK'
                            )
                        );
                    END IF;
                END $$;
                """
            )

        # Resident SELECT policy for reconciliation_allocations:
        # Residents can view allocations associated with their own approved flat invoices
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'reconciliation_allocations' AND policyname = 'reconciliation_allocations_resident_select') THEN
                    CREATE POLICY reconciliation_allocations_resident_select ON reconciliation_allocations
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
                END IF;
            END $$;
            """
        )

        # -----------------------------------------------------------------
        # 4. Database Trigger Function for Tenant and Allocation Integrity
        # -----------------------------------------------------------------
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
        # SQLite dialect support: database triggers for multi-tenant and allocation integrity
        op.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_bank_txns_tenant_integrity_insert
            BEFORE INSERT ON bank_transactions
            BEGIN
                SELECT CASE
                    WHEN (SELECT society_id FROM bank_statement_imports WHERE id = NEW.import_id) != NEW.society_id
                    THEN RAISE(ABORT, 'Cross-society bank transaction rejected: import and transaction society_id do not match')
                    WHEN NEW.duplicate_of_id IS NOT NULL AND (SELECT society_id FROM bank_transactions WHERE id = NEW.duplicate_of_id) != NEW.society_id
                    THEN RAISE(ABORT, 'Cross-society duplicate reference rejected: referenced transaction does not belong to same society')
                END;
            END;
            """
        )
        op.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_recon_matches_tenant_integrity_insert
            BEFORE INSERT ON reconciliation_matches
            BEGIN
                SELECT CASE
                    WHEN (SELECT society_id FROM bank_transactions WHERE id = NEW.transaction_id) != NEW.society_id
                    THEN RAISE(ABORT, 'Cross-society reconciliation match rejected: transaction and match society_id do not match')
                    WHEN NEW.flat_id IS NOT NULL AND (SELECT society_id FROM flats WHERE id = NEW.flat_id) != NEW.society_id
                    THEN RAISE(ABORT, 'Cross-society reconciliation match rejected: flat and match society_id do not match')
                    WHEN NEW.invoice_id IS NOT NULL AND (SELECT society_id FROM invoices WHERE id = NEW.invoice_id) != NEW.society_id
                    THEN RAISE(ABORT, 'Cross-society reconciliation match rejected: invoice and match society_id do not match')
                    WHEN NEW.existing_payment_id IS NOT NULL AND (SELECT society_id FROM payments WHERE id = NEW.existing_payment_id) != NEW.society_id
                    THEN RAISE(ABORT, 'Cross-society reconciliation match rejected: payment and match society_id do not match')
                    WHEN NEW.invoice_id IS NOT NULL AND NEW.flat_id IS NOT NULL AND (SELECT flat_id FROM invoices WHERE id = NEW.invoice_id) != NEW.flat_id
                    THEN RAISE(ABORT, 'Cross-flat reconciliation match rejected: invoice does not belong to specified flat')
                    WHEN NEW.existing_payment_id IS NOT NULL AND NEW.flat_id IS NOT NULL AND (SELECT flat_id FROM payments WHERE id = NEW.existing_payment_id) != NEW.flat_id
                    THEN RAISE(ABORT, 'Cross-flat reconciliation match rejected: payment does not belong to specified flat')
                END;
            END;
            """
        )
        op.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_recon_reviews_tenant_integrity_insert
            BEFORE INSERT ON reconciliation_reviews
            BEGIN
                SELECT CASE
                    WHEN (SELECT society_id FROM bank_transactions WHERE id = NEW.transaction_id) != NEW.society_id
                    THEN RAISE(ABORT, 'Cross-society reconciliation review rejected: transaction and review society_id do not match')
                END;
            END;
            """
        )
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
        # Drop policies and disable RLS on all 5 tables
        op.execute(
            "DROP POLICY IF EXISTS reconciliation_allocations_resident_select ON reconciliation_allocations;"
        )
        for tbl in RECON_TABLES:
            op.execute(f"DROP POLICY IF EXISTS {tbl}_helpdesk_select ON {tbl};")
            op.execute(f"DROP POLICY IF EXISTS {tbl}_postgres_all ON {tbl};")
            op.execute(f"DROP POLICY IF EXISTS {tbl}_service_role_all ON {tbl};")
            op.execute(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY;")

        # Drop trigger and function
        op.execute(
            "DROP TRIGGER IF EXISTS trg_reconciliation_allocation_tenant_integrity ON reconciliation_allocations;"
        )
        op.execute("DROP FUNCTION IF EXISTS validate_reconciliation_allocation_tenant_integrity();")

        # Drop composite foreign keys
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
            "ALTER TABLE reconciliation_reviews DROP CONSTRAINT IF EXISTS fk_recon_reviews_txn_composite;"
        )
        op.execute(
            "ALTER TABLE reconciliation_matches DROP CONSTRAINT IF EXISTS fk_recon_matches_payment_composite;"
        )
        op.execute(
            "ALTER TABLE reconciliation_matches DROP CONSTRAINT IF EXISTS fk_recon_matches_invoice_composite;"
        )
        op.execute(
            "ALTER TABLE reconciliation_matches DROP CONSTRAINT IF EXISTS fk_recon_matches_flat_composite;"
        )
        op.execute(
            "ALTER TABLE reconciliation_matches DROP CONSTRAINT IF EXISTS fk_recon_matches_txn_composite;"
        )
        op.execute(
            "ALTER TABLE bank_transactions DROP CONSTRAINT IF EXISTS fk_bank_txns_duplicate_composite;"
        )
        op.execute(
            "ALTER TABLE bank_transactions DROP CONSTRAINT IF EXISTS fk_bank_txns_import_composite;"
        )

        # Drop unique constraints
        op.execute(
            "ALTER TABLE reconciliation_reviews DROP CONSTRAINT IF EXISTS uq_reconciliation_reviews_society_id CASCADE;"
        )
        op.execute(
            "ALTER TABLE reconciliation_matches DROP CONSTRAINT IF EXISTS uq_reconciliation_matches_society_id CASCADE;"
        )
        op.execute(
            "ALTER TABLE bank_transactions DROP CONSTRAINT IF EXISTS uq_bank_transactions_society_id CASCADE;"
        )
        op.execute(
            "ALTER TABLE bank_statement_imports DROP CONSTRAINT IF EXISTS uq_bank_statement_imports_society_id CASCADE;"
        )
        op.execute("ALTER TABLE payments DROP CONSTRAINT IF EXISTS uq_payments_society_id CASCADE;")
        op.execute("ALTER TABLE invoices DROP CONSTRAINT IF EXISTS uq_invoices_society_id CASCADE;")
    else:
        op.execute("DROP TRIGGER IF EXISTS trg_recon_allocations_tenant_integrity_update;")
        op.execute("DROP TRIGGER IF EXISTS trg_recon_allocations_tenant_integrity_insert;")
        op.execute("DROP TRIGGER IF EXISTS trg_recon_reviews_tenant_integrity_insert;")
        op.execute("DROP TRIGGER IF EXISTS trg_recon_matches_tenant_integrity_insert;")
        op.execute("DROP TRIGGER IF EXISTS trg_bank_txns_tenant_integrity_insert;")
