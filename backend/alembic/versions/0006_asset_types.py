"""Add asset_type and physical_type to portfolio_positions.

Revision ID: 0006_asset_types
Revises: 0005_portfolio_manager
Create Date: 2026-03-03
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_asset_types"
down_revision = "0005_portfolio_manager"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "portfolio_positions",
        sa.Column("asset_type", sa.String(20), server_default="stock", nullable=False),
    )
    op.add_column(
        "portfolio_positions",
        sa.Column("physical_type", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("portfolio_positions", "physical_type")
    op.drop_column("portfolio_positions", "asset_type")
