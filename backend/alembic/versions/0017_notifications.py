"""
0017_notifications — Notification and webhook tables.

Creates:
  - notifications   — In-app notifications for trading events
  - user_webhooks   — User-configured webhook endpoints

Revision: 0017
Revises:  0016
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    # -- notifications table --------------------------------------------------
    op.create_table(
        "notifications",
        sa.Column("notification_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text, nullable=True),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.Column("is_read", sa.Boolean, server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Partial index for unread notifications (most common query)
    op.create_index(
        "idx_notifications_user_unread",
        "notifications",
        ["user_id", "created_at"],
        postgresql_where=sa.text("is_read = false"),
    )

    # -- user_webhooks table --------------------------------------------------
    op.create_table(
        "user_webhooks",
        sa.Column("webhook_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("events", JSONB, nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index(
        "idx_user_webhooks_user",
        "user_webhooks",
        ["user_id"],
    )


def downgrade():
    op.drop_table("user_webhooks")
    op.drop_table("notifications")
