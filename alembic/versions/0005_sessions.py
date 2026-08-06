"""Add short-lived anonymous case sessions.

Revision ID: 0005_sessions
Revises: 0004_organization_created_at
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_sessions"
down_revision = "0004_organization_created_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("session_token", sa.String(64), primary_key=True),
        sa.Column("case_id", sa.String(12), sa.ForeignKey("cases.case_id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_accessed", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("user_agent", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_sessions_case_id", "sessions", ["case_id"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])
    op.create_index("ix_sessions_is_active", "sessions", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_sessions_is_active", table_name="sessions")
    op.drop_index("ix_sessions_expires_at", table_name="sessions")
    op.drop_index("ix_sessions_case_id", table_name="sessions")
    op.drop_table("sessions")
