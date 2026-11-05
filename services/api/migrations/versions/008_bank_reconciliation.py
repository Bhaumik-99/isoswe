"""008_bank_reconciliation

Phase 4: Bank Statement Reconciliation System.

Creates:
1. bank_statement_imports: Bank statement upload files, checksums, parsing status and row statistics
2. bank_transactions: Normalized bank credit/debit transaction line items with UTR and fingerprint
3. reconciliation_matches: Deterministic candidate matches with confidence scores and evidence factors
4. reconciliation_reviews: Immutable audit trail of helpdesk review notes and triage actions
5. reconciliation_allocations: Explicit mapping between bank credit funds and invoice payment allocations

Revision ID: 008_bank_reconciliation
Revises: 007_worker_claim_token
Create Date: 2026-11-05 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "008_bank_reconciliation"
down_revision: str | None = "007_worker_claim_token"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Bank Statement Imports Table
    op.create_table(
        "bank_statement_imports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("society_id", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_checksum", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="UPLOADED", nullable=False),
        sa.Column("bank_name", sa.String(length=64), nullable=True),
        sa.Column("account_number_mask", sa.String(length=32), nullable=True),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        sa.Column("total_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("valid_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rejected_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("duplicate_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("imported_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_summary", sa.JSON(), server_default="{}", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["society_id"], ["societies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "society_id", "file_checksum", name="uq_statement_import_society_checksum"
        ),
    )
    op.create_index(
        "ix_statement_imports_society_status",
        "bank_statement_imports",
        ["society_id", "status"],
    )
    op.create_index(
        "ix_statement_imports_society_created",
        "bank_statement_imports",
        ["society_id", "created_at"],
    )

    # 2. Bank Transactions Table
    op.create_table(
        "bank_transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("society_id", sa.Uuid(), nullable=False),
        sa.Column("import_id", sa.Uuid(), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("transaction_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("normalized_description", sa.Text(), nullable=False),
        sa.Column("reference_number", sa.String(length=128), nullable=True),
        sa.Column("utr_number", sa.String(length=128), nullable=True),
        sa.Column(
            "transaction_type", sa.String(length=32), server_default="CREDIT", nullable=False
        ),
        sa.Column("debit_paise", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("credit_paise", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("balance_paise", sa.BigInteger(), nullable=True),
        sa.Column("allocated_paise", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "reconciliation_status",
            sa.String(length=32),
            server_default="UNMATCHED",
            nullable=False,
        ),
        sa.Column("transaction_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("is_duplicate", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("duplicate_of_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("debit_paise >= 0", name="chk_bank_txn_debit_non_negative"),
        sa.CheckConstraint("credit_paise >= 0", name="chk_bank_txn_credit_non_negative"),
        sa.CheckConstraint("allocated_paise >= 0", name="chk_bank_txn_allocated_non_negative"),
        sa.CheckConstraint(
            "allocated_paise <= credit_paise", name="chk_bank_txn_allocated_lte_credit"
        ),
        sa.ForeignKeyConstraint(["society_id"], ["societies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["import_id"], ["bank_statement_imports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["duplicate_of_id"], ["bank_transactions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_bank_txns_society_status",
        "bank_transactions",
        ["society_id", "reconciliation_status"],
    )
    op.create_index(
        "ix_bank_txns_society_date",
        "bank_transactions",
        ["society_id", "transaction_date"],
    )
    op.create_index(
        "ix_bank_txns_society_fingerprint",
        "bank_transactions",
        ["society_id", "transaction_fingerprint"],
    )
    op.create_index(
        "ix_bank_txns_society_utr",
        "bank_transactions",
        ["society_id", "utr_number"],
    )

    # 3. Reconciliation Matches Table
    op.create_table(
        "reconciliation_matches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("society_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("flat_id", sa.Uuid(), nullable=True),
        sa.Column("resident_id", sa.Uuid(), nullable=True),
        sa.Column("invoice_id", sa.Uuid(), nullable=True),
        sa.Column("existing_payment_id", sa.Uuid(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("confidence_tier", sa.String(length=16), server_default="LOW", nullable=False),
        sa.Column("matching_level", sa.String(length=32), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("is_selected", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence_score >= 0.0 AND confidence_score <= 100.0",
            name="chk_match_confidence_range",
        ),
        sa.ForeignKeyConstraint(["society_id"], ["societies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["transaction_id"], ["bank_transactions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["flat_id"], ["flats.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["resident_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["existing_payment_id"], ["payments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_reconciliation_matches_txn",
        "reconciliation_matches",
        ["transaction_id", "confidence_score"],
    )
    op.create_index(
        "ix_reconciliation_matches_invoice",
        "reconciliation_matches",
        ["invoice_id"],
    )
    op.create_index(
        "ix_reconciliation_matches_payment",
        "reconciliation_matches",
        ["existing_payment_id"],
    )

    # 4. Reconciliation Reviews Table
    op.create_table(
        "reconciliation_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("society_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("proposed_allocations", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("metadata", sa.JSON(), server_default="{}", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["society_id"], ["societies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["transaction_id"], ["bank_transactions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_reconciliation_reviews_txn",
        "reconciliation_reviews",
        ["transaction_id", "created_at"],
    )

    # 5. Reconciliation Allocations Table
    op.create_table(
        "reconciliation_allocations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("society_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=True),
        sa.Column("payment_allocation_id", sa.Uuid(), nullable=True),
        sa.Column("allocated_paise", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("allocated_paise > 0", name="chk_recon_allocation_positive"),
        sa.ForeignKeyConstraint(["society_id"], ["societies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["transaction_id"], ["bank_transactions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["payment_allocation_id"], ["payment_allocations.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_recon_allocations_txn",
        "reconciliation_allocations",
        ["transaction_id"],
    )
    op.create_index(
        "ix_recon_allocations_invoice",
        "reconciliation_allocations",
        ["invoice_id"],
    )
    op.create_index(
        "ix_recon_allocations_payment",
        "reconciliation_allocations",
        ["payment_id"],
    )


def downgrade() -> None:
    op.drop_table("reconciliation_allocations")
    op.drop_table("reconciliation_reviews")
    op.drop_table("reconciliation_matches")
    op.drop_table("bank_transactions")
    op.drop_table("bank_statement_imports")
