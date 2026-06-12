"""Add cost_basis to portfolio_trades for realized P&L tracking

Records the average cost per unit at the time of a SELL trade.
Allows computing realized P&L = (price - cost_basis) * quantity
without needing the original position (which is deleted on full sell).

Revision ID: 0021
Revises: 0020
Create Date: 2026-04-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add nullable cost_basis column; NULL on existing rows (BUY trades) is correct
    op.add_column(
        "portfolio_trades",
        sa.Column("cost_basis", sa.Numeric(18, 4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("portfolio_trades", "cost_basis")
