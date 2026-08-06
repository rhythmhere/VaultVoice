"""Add emergency triage, NGO verification, referral statuses, and notes."""

from alembic import op
import sqlalchemy as sa


revision = "0007_emergency_ngo_operations"
down_revision = "0006_referrals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("emergency_requested", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_cases_emergency_requested", "cases", ["emergency_requested"])

    op.add_column("organizations", sa.Column("verification_status", sa.String(20), nullable=False, server_default="approved"))
    op.add_column("organizations", sa.Column("verification_note", sa.Text(), nullable=True))
    op.create_index("ix_organizations_verification_status", "organizations", ["verification_status"])
    op.create_check_constraint("ck_organizations_verification_status", "organizations", "verification_status IN ('pending', 'approved', 'rejected')")

    op.add_column("referrals", sa.Column("case_status", sa.String(20), nullable=False, server_default="pending"))
    op.create_index("ix_referrals_case_status", "referrals", ["case_status"])
    op.create_check_constraint("ck_referrals_case_status", "referrals", "case_status IN ('pending', 'processing', 'completed')")

    op.create_table(
        "case_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("referral_id", sa.String(36), sa.ForeignKey("referrals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ngo_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_case_notes_referral_id", "case_notes", ["referral_id"])
    op.create_index("ix_case_notes_ngo_id", "case_notes", ["ngo_id"])


def downgrade() -> None:
    op.drop_index("ix_case_notes_ngo_id", table_name="case_notes")
    op.drop_index("ix_case_notes_referral_id", table_name="case_notes")
    op.drop_table("case_notes")
    op.drop_constraint("ck_referrals_case_status", "referrals", type_="check")
    op.drop_index("ix_referrals_case_status", table_name="referrals")
    op.drop_column("referrals", "case_status")
    op.drop_constraint("ck_organizations_verification_status", "organizations", type_="check")
    op.drop_index("ix_organizations_verification_status", table_name="organizations")
    op.drop_column("organizations", "verification_note")
    op.drop_column("organizations", "verification_status")
    op.drop_index("ix_cases_emergency_requested", table_name="cases")
    op.drop_column("cases", "emergency_requested")
