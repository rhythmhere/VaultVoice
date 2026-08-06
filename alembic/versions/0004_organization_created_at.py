"""Add deterministic organization creation timestamp.

Revision ID: 0004_organization_created_at
Revises: 0003_analysis_status
"""
from alembic import op
import sqlalchemy as sa


revision = "0004_organization_created_at"
down_revision = "0003_analysis_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade() -> None:
    op.drop_column("organizations", "created_at")
