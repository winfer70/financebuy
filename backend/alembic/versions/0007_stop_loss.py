"""Add stop_loss to portfolio_positions.

Revision ID: 0007_stop_loss
Revises: 0006_asset_types
Create Date: 2026-03-03
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_stop_loss"
down_revision = "0006_asset_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "portfolio_positions",
        sa.Column("stop_loss", sa.Numeric(18, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("portfolio_positions", "stop_loss")
