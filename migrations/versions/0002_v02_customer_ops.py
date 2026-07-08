"""v0.2 customer operations schema

Revision ID: 0002_v02_customer_ops
Revises: 0001_baseline_current
Create Date: 2026-07-08 00:10:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_v02_customer_ops"
down_revision = "0001_baseline_current"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("customer_stage", sa.String(length=32), nullable=False, server_default="new"))
        batch_op.add_column(sa.Column("source_channel", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("owner_name", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index("ix_users_customer_stage", "users", ["customer_stage"])
    op.create_index("ix_users_last_event_at", "users", ["last_event_at"])

    op.create_table(
        "customer_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("actor", sa.String(length=64), nullable=False, server_default="system"),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("related_message_id", sa.Integer(), nullable=True),
        sa.Column("event_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["related_message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_customer_events_type_created", "customer_events", ["event_type", "created_at"])
    op.create_index("ix_customer_events_user_created", "customer_events", ["user_id", "created_at"])

    op.create_table(
        "routing_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("from_stage", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("conditions", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_routing_rules_name"),
    )
    op.create_index("ix_routing_rules_stage_enabled", "routing_rules", ["from_stage", "enabled"])


def downgrade() -> None:
    op.drop_index("ix_routing_rules_stage_enabled", table_name="routing_rules")
    op.drop_table("routing_rules")
    op.drop_index("ix_customer_events_user_created", table_name="customer_events")
    op.drop_index("ix_customer_events_type_created", table_name="customer_events")
    op.drop_table("customer_events")
    op.drop_index("ix_users_last_event_at", table_name="users")
    op.drop_index("ix_users_customer_stage", table_name="users")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("last_event_at")
        batch_op.drop_column("owner_name")
        batch_op.drop_column("source_channel")
        batch_op.drop_column("customer_stage")

