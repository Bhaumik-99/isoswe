"""005_complaints_domain

Phase 3: Complaints Management, Helpdesk Operations, and AI-Assisted Triage.

Creates:
1. complaints: Resident tickets with category, priority, status, SLA deadlines, AI triage, and safety escalation
2. complaint_attachments: Metadata for uploaded photos/attachments with private storage keys
3. complaint_comments: Public resident comments and internal helpdesk notes
4. complaint_activities: Immutable audit timeline of ticket state transitions and actions

Revision ID: 005_complaints_domain
Revises: 004_billing_integrity
Create Date: 2026-11-04 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005_complaints_domain"
down_revision: str | None = "004_billing_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Complaints Table
    op.create_table(
        "complaints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("society_id", sa.Uuid(), nullable=False),
        sa.Column("flat_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("assigned_to", sa.Uuid(), nullable=True),
        sa.Column("complaint_number", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("subcategory", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("ai_suggested_category", sa.String(length=32), nullable=True),
        sa.Column("ai_suggested_priority", sa.String(length=16), nullable=True),
        sa.Column("ai_confidence_score", sa.Float(), nullable=True),
        sa.Column("ai_summary", sa.String(length=255), nullable=True),
        sa.Column("ai_urgency_reason", sa.String(length=255), nullable=True),
        sa.Column("duplicate_of_id", sa.Uuid(), nullable=True),
        sa.Column("safety_escalated", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("safety_escalation_reason", sa.String(length=255), nullable=True),
        sa.Column("first_response_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_response_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reopened_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["society_id"], ["societies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["flat_id"], ["flats.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["duplicate_of_id"], ["complaints.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("society_id", "complaint_number", name="uq_complaint_society_number"),
        sa.CheckConstraint(
            "rating IS NULL OR (rating >= 1 AND rating <= 5)", name="chk_complaint_rating_range"
        ),
    )
    op.create_index("ix_complaints_society_status", "complaints", ["society_id", "status"])
    op.create_index("ix_complaints_society_priority", "complaints", ["society_id", "priority"])
    op.create_index("ix_complaints_society_flat", "complaints", ["society_id", "flat_id"])
    op.create_index("ix_complaints_society_assigned", "complaints", ["society_id", "assigned_to"])
    op.create_index("ix_complaints_society_created", "complaints", ["society_id", "created_at"])
    op.create_index("ix_complaints_resolution_deadline", "complaints", ["resolution_deadline"])

    # 2. Complaint Attachments Table
    op.create_table(
        "complaint_attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("society_id", sa.Uuid(), nullable=False),
        sa.Column("complaint_id", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["society_id"], ["societies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["complaint_id"], ["complaints.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key", name="uq_complaint_attachment_storage_key"),
        sa.CheckConstraint("file_size_bytes > 0", name="chk_attachment_size_positive"),
    )
    op.create_index("ix_complaint_attachments_complaint", "complaint_attachments", ["complaint_id"])

    # 3. Complaint Comments Table
    op.create_table(
        "complaint_comments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("society_id", sa.Uuid(), nullable=False),
        sa.Column("complaint_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("is_internal", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["society_id"], ["societies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["complaint_id"], ["complaints.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_complaint_comments_complaint", "complaint_comments", ["complaint_id", "created_at"]
    )

    # 4. Complaint Activities Table
    op.create_table(
        "complaint_activities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("society_id", sa.Uuid(), nullable=False),
        sa.Column("complaint_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("activity_type", sa.String(length=64), nullable=False),
        sa.Column("old_value", sa.String(length=128), nullable=True),
        sa.Column("new_value", sa.String(length=128), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False)
        if op.get_bind().dialect.name == "postgresql"
        else sa.Column("metadata", sa.JSON(), nullable=False, default=dict),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["society_id"], ["societies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["complaint_id"], ["complaints.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_complaint_activities_complaint", "complaint_activities", ["complaint_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_table("complaint_activities")
    op.drop_table("complaint_comments")
    op.drop_table("complaint_attachments")
    op.drop_table("complaints")
