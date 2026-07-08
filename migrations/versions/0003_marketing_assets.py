"""add marketing assets

Revision ID: 0003_marketing_assets
Revises: 0002_v02_customer_ops
Create Date: 2026-07-08 00:20:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_marketing_assets"
down_revision = "0002_v02_customer_ops"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "marketing_assets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("channel", sa.String(length=64), nullable=False, server_default="xiaohongshu"),
        sa.Column("topic", sa.String(length=256), nullable=False),
        sa.Column("audience", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("goal", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("tone", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("source_context", sa.Text(), nullable=False, server_default=""),
        sa.Column("result", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="generated"),
        sa.Column("created_by", sa.String(length=64), nullable=False, server_default="agent"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_marketing_assets_channel_created", "marketing_assets", ["channel", "created_at"])
    op.create_index("ix_marketing_assets_topic", "marketing_assets", ["topic"])


def downgrade() -> None:
    op.drop_index("ix_marketing_assets_topic", table_name="marketing_assets")
    op.drop_index("ix_marketing_assets_channel_created", table_name="marketing_assets")
    op.drop_table("marketing_assets")

