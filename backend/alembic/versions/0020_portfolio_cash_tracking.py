"""Portfolio cash tracking

Adds a cash_balance column to the portfolios table and creates a
portfolio_trades table to record buy/sell trade history with optional
cash-deduction/credit integration.

Revision ID: 0020
Revises: 0019
Create Date: 2026-04-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    # -- Add cash_balance column to portfolios --------------------------------
    op.add_column(
        "portfolios",
        sa.Column(
            "cash_balance",
            sa.Numeric(precision=18, scale=4),
            nullable=False,
            server_default="0",
        ),
    )

    # -- portfolio_trades table -----------------------------------------------
    op.create_table(
        "portfolio_trades",
        sa.Column(
            "trade_id",
            UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "portfolio_id",
            UUID(as_uuid=True),
            sa.ForeignKey("portfolios.portfolio_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("trade_type", sa.String(10), nullable=False),   # BUY or SELL
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("price", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("total_value", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_portfolio_trades_portfolio_id",
        "portfolio_trades",
        ["portfolio_id"],
    )


def downgrade():
    op.drop_index("ix_portfolio_trades_portfolio_id", table_name="portfolio_trades")
    op.drop_table("portfolio_trades")
    op.drop_column("portfolios", "cash_balance")
