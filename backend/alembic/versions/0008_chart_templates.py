"""Create chart_templates table.

Revision ID: 0008_chart_templates
Revises: 0007_stop_loss
Create Date: 2026-03-03
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0008_chart_templates"
down_revision = "0007_stop_loss"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chart_templates",
        sa.Column("template_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=True),
        sa.Column("interval", sa.String(10), nullable=True),
        sa.Column(
            "drawings_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("overlays_json", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_chart_templates_user_id", "chart_templates", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("idx_chart_templates_user_id", table_name="chart_templates")
    op.drop_table("chart_templates")
