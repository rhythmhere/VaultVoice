"""Add NGO accounts and commission audit records.

Revision ID: 0002_ngo_billing
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa


revision = "0002_ngo_billing"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ngo_accounts",
        sa.Column("ngo_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("subscription_tier", sa.String(10), nullable=False, server_default="free"),
        sa.Column("billing_status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("commission_agreement", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("api_token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("subscription_tier IN ('free', 'paid')", name="ck_ngo_accounts_subscription_tier"),
    )
    op.create_table(
        "commission_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(12), sa.ForeignKey("cases.case_id", ondelete="CASCADE"), nullable=False),
        sa.Column("ngo_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("self_reported_outcome", sa.Text(), nullable=False),
        sa.Column("commission_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="NPR"),
        sa.Column("status", sa.String(12), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("currency = 'NPR'", name="ck_commission_records_currency"),
        sa.CheckConstraint("status IN ('pending', 'confirmed', 'invoiced', 'paid')", name="ck_commission_records_status"),
    )
    op.create_index("ix_commission_records_case_id", "commission_records", ["case_id"])
    op.create_index("ix_commission_records_ngo_id", "commission_records", ["ngo_id"])
    op.create_index("ix_commission_records_status", "commission_records", ["status"])
    op.create_index("ix_commission_records_ngo_status", "commission_records", ["ngo_id", "status"])
    op.create_table(
        "commission_audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("commission_id", sa.String(36), sa.ForeignKey("commission_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("from_status", sa.String(12)),
        sa.Column("to_status", sa.String(12), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_commission_audit_log_commission_id", "commission_audit_log", ["commission_id"])


def downgrade() -> None:
    op.drop_index("ix_commission_audit_log_commission_id", table_name="commission_audit_log")
    op.drop_table("commission_audit_log")
    op.drop_index("ix_commission_records_ngo_status", table_name="commission_records")
    op.drop_index("ix_commission_records_status", table_name="commission_records")
    op.drop_index("ix_commission_records_ngo_id", table_name="commission_records")
    op.drop_index("ix_commission_records_case_id", table_name="commission_records")
    op.drop_table("commission_records")
    op.drop_table("ngo_accounts")
