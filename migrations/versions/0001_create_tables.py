"""Initial database schema for products, alerts, snapshots, and user preferences."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("desired_price", sa.Float(), nullable=True),
        sa.Column("current_price", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("product_id", sa.String(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("threshold_price", sa.Float(), nullable=False),
        sa.Column("active", sa.Boolean(), default=True),
        sa.Column("channel", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "price_snapshots",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("product_id", sa.String(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("current_price", sa.Float(), nullable=True),
        sa.Column("list_price", sa.Float(), nullable=True),
        sa.Column("availability", sa.String(), nullable=True),
        sa.Column("collected_at", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("extreme_discount", sa.Boolean(), nullable=False, default=False),
        sa.Column("improbable_price", sa.Boolean(), nullable=False, default=False),
    )

    op.create_table(
        "user_preferences",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("smtp_host", sa.String(), nullable=True),
        sa.Column("smtp_username", sa.String(), nullable=True),
        sa.Column("smtp_password", sa.String(), nullable=True),
        sa.Column("webhook_url", sa.String(), nullable=True),
        sa.Column("slack_webhook_url", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("user_preferences")
    op.drop_table("price_snapshots")
    op.drop_table("alerts")
    op.drop_table("products")
