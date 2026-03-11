"""
0015_trading_strategies — Trading AI core tables.

Creates four tables required by the algorithmic trading engine:

  - strategies           — User and system strategy definitions
  - strategy_versions    — Immutable snapshots of strategy definitions
  - backtest_results     — Queued / completed backtest jobs
  - trading_signals      — Forward-looking entry/exit/stop-loss signals

Revision: 0015
Revises:  0014
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# Revision identifiers
revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create trading AI core tables."""

    # ── strategies ────────────────────────────────────────────────────────
    op.create_table(
        "strategies",
        sa.Column("strategy_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=True,
            comment="NULL for system strategies.",
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "strategy_type",
            sa.String(30),
            nullable=False,
            comment="builtin | learned | pinescript | ml",
        ),
        sa.Column(
            "category",
            sa.String(30),
            nullable=True,
            comment="trend_following | mean_reversion | momentum | breakout | volatility | ml_based | hybrid",
        ),
        sa.Column(
            "timeframe",
            sa.String(20),
            nullable=True,
            comment="scalping | day_trading | swing | position",
        ),
        sa.Column(
            "asset_class",
            sa.String(20),
            nullable=True,
            comment="stocks | etfs | futures | crypto",
        ),
        sa.Column("definition_json", JSONB, nullable=False),
        sa.Column("is_public", sa.Boolean, server_default="FALSE", nullable=False),
        sa.Column("is_system", sa.Boolean, server_default="FALSE", nullable=False),
        sa.Column("version", sa.Integer, server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("idx_strategies_user_id", "strategies", ["user_id"])
    op.create_index("idx_strategies_type", "strategies", ["strategy_type"])
    op.create_index(
        "idx_strategies_public",
        "strategies",
        ["is_public"],
        postgresql_where="is_public = TRUE",
    )

    # ── strategy_versions ─────────────────────────────────────────────────
    op.create_table(
        "strategy_versions",
        sa.Column("version_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "strategy_id",
            UUID(as_uuid=True),
            sa.ForeignKey("strategies.strategy_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("definition_json", JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "strategy_id", "version_number",
            name="uq_strategy_versions_strategy_version",
        ),
    )

    # ── backtest_results ──────────────────────────────────────────────────
    op.create_table(
        "backtest_results",
        sa.Column("result_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "strategy_id",
            UUID(as_uuid=True),
            sa.ForeignKey("strategies.strategy_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column(
            "interval",
            sa.String(10),
            nullable=False,
            comment="e.g. 1d, 1h",
        ),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("parameters_json", JSONB, nullable=True),
        sa.Column(
            "commission_per_trade",
            sa.Numeric(10, 4),
            server_default="1.00",
            nullable=False,
        ),
        sa.Column(
            "slippage_pct",
            sa.Numeric(6, 4),
            server_default="0.0005",
            nullable=False,
            comment="Default 0.05%",
        ),
        sa.Column("results_json", JSONB, nullable=True, comment="Trades, equity curve, signals"),
        sa.Column("metrics_json", JSONB, nullable=True, comment="Sharpe, drawdown, win rate, etc."),
        sa.Column("benchmark_json", JSONB, nullable=True, comment="Buy-and-hold + SPY comparison"),
        sa.Column("overfit_warning", sa.Boolean, server_default="FALSE", nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            server_default="pending",
            nullable=False,
            comment="pending | running | completed | failed",
        ),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_backtest_results_user_id", "backtest_results", ["user_id"])
    op.create_index("idx_backtest_results_strategy_id", "backtest_results", ["strategy_id"])
    op.create_index("idx_backtest_results_status", "backtest_results", ["status"])

    # ── trading_signals ───────────────────────────────────────────────────
    op.create_table(
        "trading_signals",
        sa.Column("signal_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "strategy_id",
            UUID(as_uuid=True),
            sa.ForeignKey("strategies.strategy_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column(
            "signal_type",
            sa.String(10),
            nullable=False,
            comment="entry | exit | stop_loss",
        ),
        sa.Column(
            "direction",
            sa.String(10),
            nullable=False,
            comment="long | short",
        ),
        sa.Column("price", sa.Numeric(18, 4), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=True, comment="0.00–1.00"),
        sa.Column("reasoning", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="TRUE", nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_trading_signals_user_strategy",
        "trading_signals",
        ["user_id", "strategy_id"],
    )
    op.create_index("idx_trading_signals_symbol", "trading_signals", ["symbol"])
    op.create_index(
        "idx_trading_signals_active",
        "trading_signals",
        ["is_active"],
        postgresql_where="is_active = TRUE",
    )


def downgrade() -> None:
    """Drop trading AI core tables in reverse dependency order."""

    op.drop_table("trading_signals")
    op.drop_table("backtest_results")
    op.drop_table("strategy_versions")
    op.drop_table("strategies")
