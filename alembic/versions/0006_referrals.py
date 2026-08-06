"""Add consented referral workflow and audit history."""
from alembic import op
import sqlalchemy as sa

revision = "0006_referrals"
down_revision = "0005_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "referrals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(12), sa.ForeignKey("cases.case_id", ondelete="CASCADE"), nullable=False),
        sa.Column("ngo_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("consent_scope", sa.String(40), nullable=False),
        sa.Column("submitted_message", sa.Text()),
        sa.Column("consent_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("rejection_reason", sa.Text()),
        sa.Column("support_status", sa.String(40)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("consent_scope IN ('full_case', 'contact_details_evidence_summary')", name="ck_referrals_consent_scope"),
        sa.CheckConstraint("status IN ('draft', 'requested', 'admin_review', 'forwarded', 'acknowledged', 'closed')", name="ck_referrals_status"),
    )
    op.create_index("ix_referrals_case_id", "referrals", ["case_id"])
    op.create_index("ix_referrals_ngo_id", "referrals", ["ngo_id"])
    op.create_index("ix_referrals_status", "referrals", ["status"])
    op.create_index("ix_referrals_ngo_status", "referrals", ["ngo_id", "status"])
    op.create_table(
        "referral_audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("referral_id", sa.String(36), sa.ForeignKey("referrals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("from_status", sa.String(20)),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_referral_audit_log_referral_id", "referral_audit_log", ["referral_id"])


def downgrade() -> None:
    op.drop_index("ix_referral_audit_log_referral_id", table_name="referral_audit_log")
    op.drop_table("referral_audit_log")
    op.drop_index("ix_referrals_ngo_status", table_name="referrals")
    op.drop_index("ix_referrals_status", table_name="referrals")
    op.drop_index("ix_referrals_ngo_id", table_name="referrals")
    op.drop_index("ix_referrals_case_id", table_name="referrals")
    op.drop_table("referrals")
