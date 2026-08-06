"""Add mobile-ready SOS alerts and their immutable response audit trail."""

from alembic import op
import sqlalchemy as sa


revision = "0011_sos_alerts"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sos_alerts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(12), sa.ForeignKey("cases.case_id", ondelete="SET NULL"), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("accuracy_meters", sa.Float(), nullable=True),
        sa.Column("location_captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("location_sharing_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("access_token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="triggered"),
        sa.Column("assigned_ngo_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("police_escalation_status", sa.String(30), nullable=False, server_default="not_requested"),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.CheckConstraint("status IN ('triggered', 'acknowledged', 'assigned', 'responder_en_route', 'survivor_contacted', 'resolved', 'cancelled')", name="ck_sos_alerts_status"),
        sa.CheckConstraint("police_escalation_status IN ('not_requested', 'review_requested', 'contacted', 'not_needed')", name="ck_sos_alerts_police_escalation_status"),
    )
    op.create_index("ix_sos_alerts_case_id", "sos_alerts", ["case_id"])
    op.create_index("ix_sos_alerts_status", "sos_alerts", ["status"])
    op.create_index("ix_sos_alerts_assigned_ngo_id", "sos_alerts", ["assigned_ngo_id"])
    op.create_index("ix_sos_alerts_police_escalation_status", "sos_alerts", ["police_escalation_status"])
    op.create_table(
        "sos_audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sos_id", sa.String(36), sa.ForeignKey("sos_alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("from_status", sa.String(30), nullable=True),
        sa.Column("to_status", sa.String(30), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_sos_audit_log_sos_id", "sos_audit_log", ["sos_id"])


def downgrade() -> None:
    op.drop_index("ix_sos_audit_log_sos_id", table_name="sos_audit_log")
    op.drop_table("sos_audit_log")
    for name in ("ix_sos_alerts_police_escalation_status", "ix_sos_alerts_assigned_ngo_id", "ix_sos_alerts_status", "ix_sos_alerts_case_id"):
        op.drop_index(name, table_name="sos_alerts")
    op.drop_table("sos_alerts")
