"""Allow cases to exist when AI analysis is unavailable."""
from alembic import op
import sqlalchemy as sa

revision = "0003_analysis_status"
down_revision = "0002_ngo_billing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("analysis_status", sa.String(20), nullable=False, server_default="pending"))
    op.alter_column("cases", "ai_legal_summary", existing_type=sa.Text(), nullable=True)
    op.alter_column("cases", "severity", existing_type=sa.String(20), nullable=True)
    op.create_index("ix_cases_analysis_status", "cases", ["analysis_status"])


def downgrade() -> None:
    op.drop_index("ix_cases_analysis_status", table_name="cases")
    op.alter_column("cases", "severity", existing_type=sa.String(20), nullable=False)
    op.alter_column("cases", "ai_legal_summary", existing_type=sa.Text(), nullable=False)
    op.drop_column("cases", "analysis_status")
