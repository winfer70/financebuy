"""
0016_intraday_bars — TimescaleDB hypertable for intraday OHLCV data.

Creates the intraday_bars table as a TimescaleDB hypertable with:
  - Automatic partitioning by timestamp
  - Compression policy for chunks older than 7 days
  - Retention policy to drop 1-min data older than 90 days

Requires the timescale/timescaledb Docker image.

Revision: 0016
Revises:  0015
"""

from alembic import op
import sqlalchemy as sa


revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    # Enable TimescaleDB extension
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")

    # Create the intraday_bars table
    op.create_table(
        "intraday_bars",
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval", sa.String(5), nullable=False),
        sa.Column("open", sa.Numeric(18, 4), nullable=False),
        sa.Column("high", sa.Numeric(18, 4), nullable=False),
        sa.Column("low", sa.Numeric(18, 4), nullable=False),
        sa.Column("close", sa.Numeric(18, 4), nullable=False),
        sa.Column("volume", sa.BigInteger, nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("symbol", "timestamp", "interval"),
    )

    # Convert to a TimescaleDB hypertable partitioned by timestamp
    op.execute(
        "SELECT create_hypertable('intraday_bars', 'timestamp', "
        "migrate_data => true, if_not_exists => true);"
    )

    # Compression policy: compress chunks older than 7 days
    op.execute(
        "ALTER TABLE intraday_bars SET ("
        "  timescaledb.compress,"
        "  timescaledb.compress_segmentby = 'symbol,interval'"
        ");"
    )
    op.execute(
        "SELECT add_compression_policy('intraday_bars', INTERVAL '7 days', "
        "if_not_exists => true);"
    )

    # Retention: drop data older than 90 days (1-min bars)
    op.execute(
        "SELECT add_retention_policy('intraday_bars', INTERVAL '90 days', "
        "if_not_exists => true);"
    )

    # Index for common query pattern: symbol + interval + time range
    op.create_index(
        "idx_intraday_bars_symbol_interval",
        "intraday_bars",
        ["symbol", "interval", "timestamp"],
    )


def downgrade():
    op.drop_table("intraday_bars")
    op.execute("DROP EXTENSION IF EXISTS timescaledb CASCADE;")
