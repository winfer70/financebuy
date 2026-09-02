"""Add trade_analyses table."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trade_analyses",
        sa.Column(
            "analysis_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "position_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("portfolio_positions.position_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "portfolio_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("portfolios.portfolio_id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("rules_snapshot", postgresql.JSONB, nullable=True),
        sa.Column("market_data_snapshot", postgresql.JSONB, nullable=True),
        sa.Column("analysis_json", postgresql.JSONB, nullable=True),
        sa.Column("recommendation", sa.String(16), nullable=True),
        sa.Column("suggested_entry", sa.Numeric(18, 4), nullable=True),
        sa.Column("suggested_stop", sa.Numeric(18, 4), nullable=True),
        sa.Column("suggested_target", sa.Numeric(18, 4), nullable=True),
        sa.Column("risk_reward_ratio", sa.Numeric(8, 2), nullable=True),
        sa.Column("actual_entry", sa.Numeric(18, 4), nullable=True),
        sa.Column("actual_exit", sa.Numeric(18, 4), nullable=True),
        sa.Column("actual_pnl_pct", sa.Numeric(8, 4), nullable=True),
        sa.Column("outcome", sa.String(16), nullable=True),
        sa.Column("evaluation_json", postgresql.JSONB, nullable=True),
        sa.Column("chromadb_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_trade_analyses_ticker", "trade_analyses", ["ticker"])
    op.create_index(
        "ix_trade_analyses_portfolio_id", "trade_analyses", ["portfolio_id"]
    )
    op.create_index(
        "ix_trade_analyses_requested_at", "trade_analyses", ["requested_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_trade_analyses_requested_at", table_name="trade_analyses")
    op.drop_index("ix_trade_analyses_portfolio_id", table_name="trade_analyses")
    op.drop_index("ix_trade_analyses_ticker", table_name="trade_analyses")
    op.drop_table("trade_analyses")
