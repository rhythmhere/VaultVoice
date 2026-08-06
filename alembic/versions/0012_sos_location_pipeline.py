"""Make SOS location capture status explicit and align persisted field names."""

from alembic import op
import sqlalchemy as sa


revision = "0012_sos_location_pipeline"
down_revision = "0011_sos_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("sos_alerts", "accuracy_meters", new_column_name="accuracy", existing_type=sa.Float())
    op.alter_column("sos_alerts", "location_captured_at", new_column_name="captured_at", existing_type=sa.DateTime(timezone=True))
    op.add_column("sos_alerts", sa.Column("location_status", sa.String(40), nullable=False, server_default="not_requested"))
    op.add_column("sos_alerts", sa.Column("location_source", sa.String(20), nullable=False, server_default="unknown"))
    op.create_index("ix_sos_alerts_location_status", "sos_alerts", ["location_status"])


def downgrade() -> None:
    op.drop_index("ix_sos_alerts_location_status", table_name="sos_alerts")
    op.drop_column("sos_alerts", "location_source")
    op.drop_column("sos_alerts", "location_status")
    op.alter_column("sos_alerts", "captured_at", new_column_name="location_captured_at", existing_type=sa.DateTime(timezone=True))
    op.alter_column("sos_alerts", "accuracy", new_column_name="accuracy_meters", existing_type=sa.Float())
