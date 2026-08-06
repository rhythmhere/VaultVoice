"""Add funding, crowdfunding, NGO verification history, and case messaging."""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007_emergency_ngo_operations"
branch_labels = None
depends_on = None


def timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.drop_constraint("ck_organizations_verification_status", "organizations", type_="check")
    op.create_check_constraint("ck_organizations_verification_status", "organizations", "verification_status IN ('pending', 'approved', 'rejected', 'resend_requested')")
    op.drop_constraint("ck_referrals_case_status", "referrals", type_="check")
    op.create_check_constraint("ck_referrals_case_status", "referrals", "case_status IN ('pending', 'in_progress', 'resolved', 'on_hold')")
    op.add_column("referrals", sa.Column("includes_evidence", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("referrals", sa.Column("evidence_refs", sa.JSON(), nullable=False, server_default="[]"))

    op.create_table("ngo_verification_logs",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("ngo_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=False), sa.Column("action", sa.String(40), nullable=False), sa.Column("note", sa.Text()), *timestamps())
    op.create_index("ix_ngo_verification_logs_ngo_id", "ngo_verification_logs", ["ngo_id"])
    op.create_table("ngo_documents",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("ngo_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("object_key", sa.String(255), unique=True, nullable=False), sa.Column("original_name", sa.String(255), nullable=False), sa.Column("doc_type", sa.String(80), nullable=False, server_default="registration"), sa.Column("status", sa.String(20), nullable=False, server_default="pending"), sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), *timestamps())
    op.create_index("ix_ngo_documents_ngo_id", "ngo_documents", ["ngo_id"])
    op.create_table("platform_donations",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("donor_name", sa.String(200)), sa.Column("donor_email", sa.String(160)), sa.Column("is_anonymous", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("amount", sa.Numeric(12, 2), nullable=False), sa.Column("currency", sa.String(3), nullable=False, server_default="NPR"), sa.Column("message", sa.Text()), sa.Column("payment_status", sa.String(20), nullable=False, server_default="pending"), sa.Column("payment_reference", sa.String(255)), *timestamps())
    op.create_index("ix_platform_donations_payment_status", "platform_donations", ["payment_status"])
    op.create_table("crowdfunding_requests",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("case_id", sa.String(12), sa.ForeignKey("cases.case_id", ondelete="CASCADE"), nullable=False), sa.Column("category", sa.String(30), nullable=False), sa.Column("explanation", sa.Text(), nullable=False), sa.Column("requested_amount", sa.Numeric(12, 2), nullable=False), sa.Column("target_date", sa.Date()), sa.Column("consent_public_display", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("status", sa.String(25), nullable=False, server_default="pending_review"), sa.Column("review_note", sa.Text()), *timestamps())
    op.create_index("ix_crowdfunding_requests_case_id", "crowdfunding_requests", ["case_id"])
    op.create_index("ix_crowdfunding_requests_status", "crowdfunding_requests", ["status"])
    op.create_table("crowdfunding_campaigns",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("case_id", sa.String(12), sa.ForeignKey("cases.case_id", ondelete="CASCADE"), nullable=False), sa.Column("display_name", sa.String(200)), sa.Column("category", sa.String(30), nullable=False), sa.Column("description", sa.Text(), nullable=False), sa.Column("requested_amount", sa.Numeric(12, 2), nullable=False), sa.Column("amount_raised", sa.Numeric(12, 2), nullable=False, server_default="0"), sa.Column("status", sa.String(20), nullable=False, server_default="draft"), sa.Column("approved_by", sa.String(100)), sa.Column("approved_at", sa.DateTime(timezone=True)), *timestamps())
    op.create_index("ix_crowdfunding_campaigns_status", "crowdfunding_campaigns", ["status"])
    op.create_table("crowdfunding_donations",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("campaign_id", sa.String(36), sa.ForeignKey("crowdfunding_campaigns.id", ondelete="CASCADE"), nullable=False), sa.Column("donor_name", sa.String(200)), sa.Column("is_anonymous", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("amount", sa.Numeric(12, 2), nullable=False), sa.Column("currency", sa.String(3), nullable=False, server_default="NPR"), sa.Column("message", sa.Text()), sa.Column("payment_status", sa.String(20), nullable=False, server_default="pending"), sa.Column("payment_reference", sa.String(255)), *timestamps())
    op.create_index("ix_crowdfunding_donations_campaign_id", "crowdfunding_donations", ["campaign_id"])
    op.create_table("case_messages",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("case_id", sa.String(12), sa.ForeignKey("cases.case_id", ondelete="CASCADE"), nullable=False), sa.Column("ngo_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False), sa.Column("sender_type", sa.String(20), nullable=False), sa.Column("message", sa.Text(), nullable=False), sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("read_at", sa.DateTime(timezone=True)), *timestamps())
    op.create_index("ix_case_messages_case_id", "case_messages", ["case_id"])
    op.create_table("case_status_logs",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("referral_id", sa.String(36), sa.ForeignKey("referrals.id", ondelete="CASCADE"), nullable=False), sa.Column("status", sa.String(20), nullable=False), sa.Column("note", sa.Text()), sa.Column("actor_id", sa.String(100), nullable=False), *timestamps())
    op.create_index("ix_case_status_logs_referral_id", "case_status_logs", ["referral_id"])


def downgrade() -> None:
    for index, table in [("ix_case_status_logs_referral_id", "case_status_logs"), ("ix_case_messages_case_id", "case_messages"), ("ix_crowdfunding_donations_campaign_id", "crowdfunding_donations"), ("ix_crowdfunding_campaigns_status", "crowdfunding_campaigns"), ("ix_crowdfunding_requests_status", "crowdfunding_requests"), ("ix_crowdfunding_requests_case_id", "crowdfunding_requests"), ("ix_ngo_documents_ngo_id", "ngo_documents"), ("ix_ngo_verification_logs_ngo_id", "ngo_verification_logs")]:
        op.drop_index(index, table_name=table)
    for table in ["case_status_logs", "case_messages", "crowdfunding_donations", "crowdfunding_campaigns", "crowdfunding_requests", "platform_donations", "ngo_documents", "ngo_verification_logs"]:
        op.drop_table(table)
    op.drop_column("referrals", "evidence_refs")
    op.drop_column("referrals", "includes_evidence")
