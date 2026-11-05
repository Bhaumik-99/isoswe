"""010_bank_transaction_fingerprint_unique

Phase 4 Security & Integrity Fix:
1. Replaces non-unique index 'ix_bank_txns_society_fingerprint' with unique constraint
   'uq_bank_transactions_society_fingerprint' on (society_id, transaction_fingerprint)
   in PostgreSQL and a UNIQUE index in SQLite.
2. Prevents concurrent statement confirmation race conditions from inserting duplicate
   bank transactions across or within statement imports at the database level.

Revision ID: 010_bank_txn_unique_fp
Revises: 009_recon_tenant_integrity
Create Date: 2026-11-05 18:30:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "010_bank_txn_unique_fp"
down_revision: str | None = "009_recon_tenant_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_bank_txns_society_fingerprint;")
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'uq_bank_transactions_society_fingerprint'
                ) THEN
                    ALTER TABLE bank_transactions
                    ADD CONSTRAINT uq_bank_transactions_society_fingerprint
                    UNIQUE (society_id, transaction_fingerprint);
                END IF;
            END $$;
            """
        )
    else:
        op.execute("DROP INDEX IF EXISTS ix_bank_txns_society_fingerprint;")
        op.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_bank_transactions_society_fingerprint
            ON bank_transactions (society_id, transaction_fingerprint);
            """
        )


def downgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE bank_transactions DROP CONSTRAINT IF EXISTS uq_bank_transactions_society_fingerprint;"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_bank_txns_society_fingerprint ON bank_transactions (society_id, transaction_fingerprint);"
        )
    else:
        op.execute("DROP INDEX IF EXISTS uq_bank_transactions_society_fingerprint;")
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_bank_txns_society_fingerprint ON bank_transactions (society_id, transaction_fingerprint);"
        )
