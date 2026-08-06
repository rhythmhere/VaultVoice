"""Unify case messaging across survivor, NGO, and admin participants."""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("case_messages", "ngo_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("case_messages", sa.Column("sender_id", sa.String(100), nullable=True))
    op.add_column("case_messages", sa.Column("is_internal_note", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_case_messages_sender_id", "case_messages", ["sender_id"])
    op.create_check_constraint("ck_case_messages_sender_type", "case_messages", "sender_type IN ('survivor', 'ngo', 'admin')")
    op.create_table(
        "case_message_reads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("case_messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", sa.String(12), sa.ForeignKey("cases.case_id", ondelete="CASCADE"), nullable=False),
        sa.Column("participant_type", sa.String(20), nullable=False),
        sa.Column("participant_id", sa.String(100), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("message_id", "participant_type", "participant_id", name="uq_case_message_read_participant"),
    )
    op.create_index("ix_case_message_reads_message_id", "case_message_reads", ["message_id"])
    op.create_index("ix_case_message_reads_case_id", "case_message_reads", ["case_id"])


def downgrade() -> None:
    op.drop_index("ix_case_message_reads_case_id", table_name="case_message_reads")
    op.drop_index("ix_case_message_reads_message_id", table_name="case_message_reads")
    op.drop_table("case_message_reads")
    op.drop_constraint("ck_case_messages_sender_type", "case_messages", type_="check")
    op.drop_index("ix_case_messages_sender_id", table_name="case_messages")
    op.drop_column("case_messages", "is_internal_note")
    op.drop_column("case_messages", "sender_id")
    op.alter_column("case_messages", "ngo_id", existing_type=sa.Integer(), nullable=False)
