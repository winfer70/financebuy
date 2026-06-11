"""Add isin and degiro_product_id to portfolio_positions

Revision ID: 0026
Revises: 0025
Create Date: 2026-06-11
"""

from alembic import op
import sqlalchemy as sa

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "portfolio_positions",
        sa.Column("isin", sa.String(12), nullable=True),
    )
    op.add_column(
        "portfolio_positions",
        sa.Column("degiro_product_id", sa.Integer, nullable=True),
    )
    op.create_index(
        "ix_portfolio_positions_portfolio_isin",
        "portfolio_positions",
        ["portfolio_id", "isin"],
    )


def downgrade() -> None:
    op.drop_index("ix_portfolio_positions_portfolio_isin", table_name="portfolio_positions")
    op.drop_column("portfolio_positions", "degiro_product_id")
    op.drop_column("portfolio_positions", "isin")
