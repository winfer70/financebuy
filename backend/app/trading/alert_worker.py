"""
alert_worker.py — arq background worker for evaluating price alerts.

Polls active price alerts, fetches current market prices, and triggers
notifications when alert conditions are met. Self-re-enqueues every
60 seconds during market hours, every 5 minutes outside.

Runs as a standalone arq worker via:
    arq app.trading.alert_worker.WorkerSettings
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime
from decimal import Decimal

import yfinance as yf
from arq.connections import RedisSettings, create_pool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from ..models import Notification, PriceAlert

logger = logging.getLogger("alert_worker")

# -- Database setup (standalone — worker runs outside FastAPI) ─────────────

_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@db:5432/tickerTap",
)
_REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

_engine = create_async_engine(_DATABASE_URL, echo=False, pool_size=5, max_overflow=2, pool_pre_ping=True)
_SessionLocal = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


# -- Utility functions ────────────────────────────────────────────────────


def _safe_float(v) -> float:
    """Safely convert a value to float, returning 0.0 on failure.

    Args:
        v: Any value to convert to float.

    Returns:
        float: The converted value, or 0.0 if conversion fails or NaN.
    """
    try:
        f = float(v)
        if f != f:  # NaN check
            return 0.0
        return f
    except (TypeError, ValueError):
        return 0.0


def _fetch_price(symbol: str) -> float:
    """Fetch the last price for a symbol using yfinance (synchronous).

    Args:
        symbol: Ticker symbol (e.g. "AAPL").

    Returns:
        float: Last price rounded to 4 decimals, or 0.0 on failure.
    """
    try:
        ticker = yf.Ticker(symbol)
        return round(_safe_float(ticker.fast_info.last_price), 4)
    except Exception as exc:
        logger.warning("Failed to fetch price for %s: %s", symbol, exc)
        return 0.0


def _is_market_open() -> bool:
    """Check if US market is currently open (NYSE/NASDAQ hours).

    Returns:
        True if current time is within 09:30-16:00 ET on a weekday.
    """
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("America/New_York"))
    if now.weekday() >= 5:
        return False
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now < market_close


def _check_condition(condition: str, current_price: float, target_price: float) -> bool:
    """Evaluate whether the alert condition is met.

    Args:
        condition: "above", "below", or "crosses".
        current_price: Current market price.
        target_price: User's target price.

    Returns:
        True if the condition is triggered.
    """
    if condition == "above":
        return current_price >= target_price
    elif condition == "below":
        return current_price <= target_price
    elif condition == "crosses":
        # For 'crosses', trigger if price has reached the target from either direction.
        # A future improvement could store last_checked_price on the alert model
        # to detect actual crossover events.
        return current_price >= target_price or current_price <= target_price
    return False


# -- Main periodic job ─────────────────────────────────────────────────────


async def evaluate_price_alerts(ctx: dict) -> None:
    """Main worker job: check all active alerts against current prices.

    Groups alerts by symbol to minimize API calls, then evaluates each
    alert's condition. Triggered alerts get deactivated and a notification
    is created for the user.

    Args:
        ctx: arq job context dict.
    """
    session: AsyncSession = _SessionLocal()
    try:
        # Fetch all active alerts
        result = await session.execute(
            select(PriceAlert).where(PriceAlert.is_active == True)  # noqa: E712
        )
        alerts = result.scalars().all()

        if not alerts:
            logger.debug("No active price alerts to evaluate")
            return

        # Group alerts by symbol to batch price lookups
        by_symbol: dict = {}
        for alert in alerts:
            by_symbol.setdefault(alert.symbol, []).append(alert)

        logger.info(
            "Evaluating %d alerts across %d symbols", len(alerts), len(by_symbol)
        )

        # Fetch prices in parallel (thread pool for sync yfinance calls)
        symbols = list(by_symbol.keys())
        prices = await asyncio.gather(
            *[asyncio.to_thread(_fetch_price, sym) for sym in symbols]
        )
        price_map = dict(zip(symbols, prices))

        triggered_count = 0
        now = datetime.utcnow()

        for symbol, symbol_alerts in by_symbol.items():
            current_price = price_map.get(symbol, 0.0)
            if current_price <= 0:
                continue  # Skip if price fetch failed

            for alert in symbol_alerts:
                target = float(alert.target_price)
                if _check_condition(alert.condition, current_price, target):
                    # Trigger the alert: deactivate and record timestamp
                    alert.is_active = False
                    alert.triggered_at = now

                    # Determine notification text based on condition
                    if alert.condition == "above":
                        direction = "risen above"
                    elif alert.condition == "below":
                        direction = "fallen below"
                    else:
                        direction = "reached"

                    title = f"Price alert: {symbol} has {direction} ${target:.2f}"
                    body = (
                        f"{symbol} is now trading at ${current_price:.2f}, "
                        f"which triggered your {alert.condition} ${target:.2f} alert."
                    )
                    if alert.note:
                        body += f"\nNote: {alert.note}"

                    # Create in-app notification for the user
                    session.add(
                        Notification(
                            notification_id=uuid.uuid4(),
                            user_id=alert.user_id,
                            event_type="price_alert",
                            title=title,
                            body=body,
                            metadata_json={
                                "alert_id": str(alert.alert_id),
                                "symbol": symbol,
                                "condition": alert.condition,
                                "target_price": target,
                                "triggered_price": current_price,
                            },
                        )
                    )
                    triggered_count += 1
                    logger.info(
                        "Alert triggered: %s %s $%.2f (current: $%.2f)",
                        symbol,
                        alert.condition,
                        target,
                        current_price,
                    )

        if triggered_count > 0:
            await session.commit()
            logger.info("Triggered %d alerts", triggered_count)

    except Exception:
        logger.exception("Error evaluating price alerts")
        await session.rollback()
    finally:
        await session.close()

        # Re-enqueue: 60s during market hours, 300s outside.
        # MUST be inside finally so early returns / exceptions don't break the chain.
        defer_by = 60 if _is_market_open() else 300
        try:
            pool = await create_pool(RedisSettings.from_dsn(_REDIS_URL))
            await pool.enqueue_job("evaluate_price_alerts", _defer_by=defer_by)
            await pool.close()
        except Exception as exc:
            logger.error("Failed to re-enqueue alert evaluation: %s", exc)


# -- Startup hook ──────────────────────────────────────────────────────────


async def startup(ctx: dict) -> None:
    """Seed the first evaluation job on worker start.

    Called by arq's on_startup hook. Seeds the self-re-enqueuing
    cycle with a 10-second initial delay.

    Args:
        ctx: arq worker context dict.
    """
    logger.info("Alert worker starting — seeding first evaluation in 10s")
    try:
        pool = await create_pool(RedisSettings.from_dsn(_REDIS_URL))
        await pool.enqueue_job("evaluate_price_alerts", _defer_by=10)
        await pool.close()
    except Exception:
        logger.exception("Failed to seed initial alert evaluation job")


# -- arq worker settings ──────────────────────────────────────────────────


class WorkerSettings:
    """arq worker configuration for the alert evaluation loop.

    Run with: ``arq app.trading.alert_worker.WorkerSettings``
    """

    functions = [evaluate_price_alerts]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(_REDIS_URL)
    max_jobs = 5
    job_timeout = 120
