"""Initial PostgreSQL schema.

Revision ID: 0001_initial
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("cases",
        sa.Column("case_id", sa.String(12), primary_key=True),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("district", sa.String(100), nullable=False),
        sa.Column("initial_report", sa.Text(), nullable=False),
        sa.Column("clarifying_qa", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("ai_legal_summary", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="open"),
        sa.Column("timeline", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_cases_category", "cases", ["category"])
    op.create_index("ix_cases_district", "cases", ["district"])
    op.create_index("ix_cases_severity", "cases", ["severity"])
    op.create_index("ix_cases_status", "cases", ["status"])
    op.create_table("organizations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False, unique=True),
        sa.Column("categories", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("districts", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("contact_phone", sa.String(40), nullable=False),
        sa.Column("contact_email", sa.String(160)),
        sa.Column("website", sa.String(255)),
        sa.Column("description", sa.Text(), nullable=False),
    )
    op.create_table("evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("case_id", sa.String(12), sa.ForeignKey("cases.case_id", ondelete="CASCADE"), nullable=False),
        sa.Column("object_key", sa.String(255), nullable=False, unique=True),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(120), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("integrity_hash", sa.String(64), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("incident_date", sa.Date()),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_evidence_case_id", "evidence", ["case_id"])
    op.create_index("ix_evidence_case_incident_date", "evidence", ["case_id", "incident_date"])
    op.create_table("case_matches",
        sa.Column("case_id", sa.String(12), sa.ForeignKey("cases.case_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("match_reason", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("case_matches")
    op.drop_index("ix_evidence_case_incident_date", table_name="evidence")
    op.drop_index("ix_evidence_case_id", table_name="evidence")
    op.drop_table("evidence")
    for name in ["ix_cases_status", "ix_cases_severity", "ix_cases_district", "ix_cases_category"]:
        op.drop_index(name, table_name="cases")
    op.drop_table("organizations")
    op.drop_table("cases")
