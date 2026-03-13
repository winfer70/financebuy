"""
0019_paper_trading — Paper trading simulation tables.

Creates:
  - paper_trades             — Virtual trading sessions with capital tracking
  - paper_trade_positions    — Individual long/short positions within a paper trade
  - paper_trade_equity_snapshots — Point-in-time equity recordings for equity curves

Revision: 0019
Revises:  0018
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    # -- paper_trades table ----------------------------------------------------
    op.create_table(
        "paper_trades",
        sa.Column("paper_trade_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "strategy_id", UUID(as_uuid=True),
            sa.ForeignKey("strategies.strategy_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("symbol", sa.VARCHAR(20), nullable=False),
        sa.Column("initial_capital", sa.Numeric(18, 2), nullable=False),
        sa.Column("current_equity", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "status", sa.VARCHAR(20),
            server_default="active",
            nullable=False,
        ),
        sa.Column("parameters_json", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index(
        "idx_paper_trades_user_id",
        "paper_trades",
        ["user_id"],
    )

    op.create_index(
        "idx_paper_trades_status",
        "paper_trades",
        ["status"],
    )

    # -- paper_trade_positions table -------------------------------------------
    op.create_table(
        "paper_trade_positions",
        sa.Column("position_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "paper_trade_id", UUID(as_uuid=True),
            sa.ForeignKey("paper_trades.paper_trade_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("side", sa.VARCHAR(10), nullable=False),
        sa.Column("entry_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("entry_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exit_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("exit_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("pnl", sa.Numeric(18, 4), nullable=True),
        sa.Column(
            "status", sa.VARCHAR(20),
            server_default="open",
            nullable=False,
        ),
    )

    op.create_index(
        "idx_paper_positions_trade_id",
        "paper_trade_positions",
        ["paper_trade_id"],
    )

    # -- paper_trade_equity_snapshots table ------------------------------------
    op.create_table(
        "paper_trade_equity_snapshots",
        sa.Column("snapshot_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "paper_trade_id", UUID(as_uuid=True),
            sa.ForeignKey("paper_trades.paper_trade_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("equity", sa.Numeric(18, 4), nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index(
        "idx_paper_equity_trade_id",
        "paper_trade_equity_snapshots",
        ["paper_trade_id"],
    )


def downgrade():
    op.drop_table("paper_trade_equity_snapshots")
    op.drop_table("paper_trade_positions")
    op.drop_table("paper_trades")
