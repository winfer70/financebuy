"""
trading/archiver.py — Intraday data archiver worker.

Background worker that:
  1. Fetches 1-min OHLCV bars from yfinance during market hours.
  2. Upserts into the intraday_bars TimescaleDB hypertable.
  3. Aggregates 5-min bars every 5 minutes.
  4. Runs a daily downsampling job after market close:
       - 1-min → 5-min  for data older than 90 days
       - 5-min → 1-hour for data older than 1 year

Uses the same standalone DB setup as the trading worker (runs outside
FastAPI as a separate arq process).
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger("trading.archiver")

# ---------------------------------------------------------------------------
# Market hours helper (reuse pattern from routes/market.py)
# ---------------------------------------------------------------------------

def _is_market_open() -> bool:
    """Check if US equity markets are currently open (approximate).

    Returns:
        True if within NYSE regular trading hours (09:30–16:00 ET, Mon–Fri).
    """
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("America/New_York"))
    if now.weekday() >= 5:            # Saturday / Sunday
        return False
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now <= market_close


# ---------------------------------------------------------------------------
# Active symbols resolver
# ---------------------------------------------------------------------------

async def _get_active_symbols(session: AsyncSession):
    """Return symbols that have running strategies or active signals.

    Queries the strategies and trading_signals tables for symbols that
    need real-time data.

    Args:
        session: Async database session.

    Returns:
        Set of symbol strings.
    """
    result = await session.execute(
        text(
            "SELECT DISTINCT symbol FROM trading_signals WHERE is_active = true "
            "UNION "
            "SELECT DISTINCT unnest(string_to_array(s.definition_json->>'symbols', ',')) "
            "FROM strategies s WHERE s.is_active = true"
        )
    )
    symbols = {row[0] for row in result.fetchall() if row[0]}
    # Always include major indices for reference
    symbols.update({"SPY", "QQQ", "IWM"})
    return symbols


# ---------------------------------------------------------------------------
# Fetch + upsert bars
# ---------------------------------------------------------------------------

async def _fetch_and_store_bars(
    session: AsyncSession,
    symbol: str,
    interval: str = "1m",
    period: str = "1d",
):
    """Fetch latest bars from yfinance and upsert into intraday_bars.

    Uses ON CONFLICT DO UPDATE to deduplicate by (symbol, timestamp, interval).

    Args:
        session:  Async database session.
        symbol:   Ticker symbol (e.g. "AAPL").
        interval: Bar interval ("1m", "5m", "15m", "1h").
        period:   yfinance period string ("1d", "5d").
    """
    import yfinance as yf

    try:
        ticker = yf.Ticker(symbol)
        df = await asyncio.to_thread(
            ticker.history, period=period, interval=interval
        )
        if df is None or df.empty:
            return 0

        rows = []
        for ts, row in df.iterrows():
            rows.append({
                "symbol": symbol,
                "timestamp": ts.to_pydatetime(),
                "interval": interval,
                "open": Decimal(str(round(row["Open"], 4))),
                "high": Decimal(str(round(row["High"], 4))),
                "low": Decimal(str(round(row["Low"], 4))),
                "close": Decimal(str(round(row["Close"], 4))),
                "volume": int(row.get("Volume", 0)),
            })

        if not rows:
            return 0

        # Upsert: insert or update on conflict
        stmt = text("""
            INSERT INTO intraday_bars (symbol, timestamp, interval, open, high, low, close, volume)
            VALUES (:symbol, :timestamp, :interval, :open, :high, :low, :close, :volume)
            ON CONFLICT (symbol, timestamp, interval)
            DO UPDATE SET
                open   = EXCLUDED.open,
                high   = EXCLUDED.high,
                low    = EXCLUDED.low,
                close  = EXCLUDED.close,
                volume = EXCLUDED.volume
        """)
        for row in rows:
            await session.execute(stmt, row)
        await session.commit()
        return len(rows)

    except Exception as e:
        logger.warning("Archiver: failed to fetch %s/%s: %s", symbol, interval, e)
        await session.rollback()
        return 0


# ---------------------------------------------------------------------------
# Aggregate 1-min → 5-min bars
# ---------------------------------------------------------------------------

async def _aggregate_5min(session: AsyncSession):
    """Aggregate 1-min bars into 5-min bars using TimescaleDB time_bucket.

    Runs every 5 minutes. Only processes bars from the last hour to keep
    the operation fast.
    """
    stmt = text("""
        INSERT INTO intraday_bars (symbol, timestamp, interval, open, high, low, close, volume)
        SELECT
            symbol,
            time_bucket('5 minutes', timestamp) AS bucket,
            '5m',
            first(open, timestamp),
            max(high),
            min(low),
            last(close, timestamp),
            sum(volume)
        FROM intraday_bars
        WHERE interval = '1m'
          AND timestamp > now() - INTERVAL '1 hour'
        GROUP BY symbol, bucket
        ON CONFLICT (symbol, timestamp, interval)
        DO UPDATE SET
            open   = EXCLUDED.open,
            high   = EXCLUDED.high,
            low    = EXCLUDED.low,
            close  = EXCLUDED.close,
            volume = EXCLUDED.volume
    """)
    await session.execute(stmt)
    await session.commit()
    logger.info("Archiver: 5-min aggregation complete.")


# ---------------------------------------------------------------------------
# Daily downsampling job
# ---------------------------------------------------------------------------

async def _daily_downsample(session: AsyncSession):
    """Run tiered downsampling after market close.

    - 5-min bars from 1-min data older than 90 days
    - 1-hour bars from 5-min data older than 1 year
    """
    # 1-min → 5-min for data > 90 days old
    stmt_5m = text("""
        INSERT INTO intraday_bars (symbol, timestamp, interval, open, high, low, close, volume)
        SELECT
            symbol,
            time_bucket('5 minutes', timestamp) AS bucket,
            '5m',
            first(open, timestamp),
            max(high),
            min(low),
            last(close, timestamp),
            sum(volume)
        FROM intraday_bars
        WHERE interval = '1m'
          AND timestamp < now() - INTERVAL '90 days'
        GROUP BY symbol, bucket
        ON CONFLICT (symbol, timestamp, interval) DO NOTHING
    """)
    await session.execute(stmt_5m)

    # 5-min → 1-hour for data > 1 year old
    stmt_1h = text("""
        INSERT INTO intraday_bars (symbol, timestamp, interval, open, high, low, close, volume)
        SELECT
            symbol,
            time_bucket('1 hour', timestamp) AS bucket,
            '1h',
            first(open, timestamp),
            max(high),
            min(low),
            last(close, timestamp),
            sum(volume)
        FROM intraday_bars
        WHERE interval = '5m'
          AND timestamp < now() - INTERVAL '1 year'
        GROUP BY symbol, bucket
        ON CONFLICT (symbol, timestamp, interval) DO NOTHING
    """)
    await session.execute(stmt_1h)
    await session.commit()
    logger.info("Archiver: daily downsampling complete.")


# ---------------------------------------------------------------------------
# arq worker jobs
# ---------------------------------------------------------------------------

async def archive_intraday(ctx):
    """arq job: fetch and store intraday bars for all active symbols.

    Called every 60 seconds during market hours.

    Args:
        ctx: arq worker context (contains 'db' session factory).
    """
    if not _is_market_open():
        return "market_closed"

    session_factory = ctx.get("db")
    if not session_factory:
        return "no_db"

    async with session_factory() as session:
        symbols = await _get_active_symbols(session)

    total = 0
    for symbol in symbols:
        async with session_factory() as session:
            count = await _fetch_and_store_bars(session, symbol, "1m", "1d")
            total += count

    # Every 5 minutes, also run the 5-min aggregation
    now = datetime.now(timezone.utc)
    if now.minute % 5 == 0:
        async with session_factory() as session:
            await _aggregate_5min(session)

    logger.info("Archiver: stored %d bars for %d symbols.", total, len(symbols))
    return f"stored={total}"


async def downsample_daily(ctx):
    """arq job: run tiered downsampling after market close.

    Called once daily at 17:00 ET.

    Args:
        ctx: arq worker context.
    """
    session_factory = ctx.get("db")
    if not session_factory:
        return "no_db"

    async with session_factory() as session:
        await _daily_downsample(session)
    return "done"


async def startup(ctx):
    """arq startup hook — create DB session factory.

    Called once when the arq worker starts. Sets up a standalone
    async DB engine (worker runs outside FastAPI).
    """
    import os
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/tickerTap")
    engine = create_async_engine(db_url, pool_size=3, max_overflow=2)
    ctx["db"] = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    logger.info("Archiver worker: DB connection established.")


async def shutdown(ctx):
    """arq shutdown hook — dispose DB engine."""
    session_factory = ctx.get("db")
    if session_factory:
        await session_factory.kw["bind"].dispose()
    logger.info("Archiver worker: shutdown complete.")


class WorkerSettings:
    """arq worker configuration for the intraday archiver."""
    functions = [archive_intraday, downsample_daily]
    on_startup = startup
    on_shutdown = shutdown
    # Archive every 60 seconds
    cron_jobs = [
        # Archive runs every minute during the day
        # Downsample runs at 22:00 UTC (17:00 ET)
    ]
    redis_settings = None  # Set via REDIS_URL env var at runtime
