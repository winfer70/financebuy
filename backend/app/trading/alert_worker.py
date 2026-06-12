"""
alert_worker.py — arq background worker for evaluating price alerts.

Polls active price alerts, fetches current market prices, and triggers
notifications when alert conditions are met. Self-re-enqueues every
60 seconds during market hours, every 5 minutes outside.

Runs as a standalone arq worker via:
    arq app.trading.alert_worker.WorkerSettings
"""

import asyncio
import os
import uuid
from datetime import datetime
from decimal import Decimal

import structlog
import yfinance as yf
from arq.connections import RedisSettings, create_pool
from arq.cron import cron
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from ..logging_config import configure_structlog
from ..models import Notification, PriceAlert, Portfolio, PortfolioPosition
from .heartbeat import write_worker_heartbeat
from ..services.degiro_sync import sync_degiro_portfolio  # noqa: F401
from .notifications import _send_telegram

# Configure structlog before any logger is obtained — idempotent guard inside
configure_structlog()
logger = structlog.get_logger("alert_worker")

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
        logger.warning("Failed to fetch price for symbol", symbol=symbol, error=str(exc))
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


async def _check_soft_stops(session: AsyncSession) -> None:
    """Check soft_stop_loss on open positions; fire Telegram + in-app notification and clear."""
    result = await session.execute(
        select(PortfolioPosition, Portfolio.user_id)
        .join(Portfolio, PortfolioPosition.portfolio_id == Portfolio.portfolio_id)
        .where(
            PortfolioPosition.soft_stop_loss.isnot(None),
            PortfolioPosition.closed_at.is_(None),
        )
    )
    rows = result.all()
    if not rows:
        return

    by_ticker: dict[str, list] = {}
    for pos, user_id in rows:
        by_ticker.setdefault(pos.ticker, []).append((pos, user_id))

    prices = await asyncio.gather(
        *[asyncio.to_thread(_fetch_price, sym) for sym in by_ticker]
    )
    price_map = dict(zip(by_ticker.keys(), prices))

    triggered = 0
    now = datetime.utcnow()
    for ticker, entries in by_ticker.items():
        current_price = price_map.get(ticker, 0.0)
        if current_price <= 0:
            continue
        for pos, user_id in entries:
            soft_stop = float(pos.soft_stop_loss)
            if current_price <= soft_stop:
                title = f"Soft stop hit: {ticker} at ${current_price:.2f}"
                body = f"{ticker} dropped to ${current_price:.2f} — below your soft stop ${soft_stop:.2f}. Review your position."
                session.add(
                    Notification(
                        notification_id=uuid.uuid4(),
                        user_id=user_id,
                        event_type="soft_stop_loss",
                        title=title,
                        body=body,
                        metadata_json={
                            "ticker": ticker,
                            "soft_stop": soft_stop,
                            "triggered_price": current_price,
                            "position_id": str(pos.position_id),
                        },
                    )
                )
                pos.soft_stop_loss = None
                triggered += 1
                logger.info("Soft stop triggered", ticker=ticker, soft_stop=soft_stop, price=current_price)
                await _send_telegram(title, body)

    if triggered > 0:
        await session.commit()
        logger.info("Soft stops triggered", count=triggered)


async def evaluate_price_alerts(ctx: dict) -> None:
    """Main worker job: check all active alerts against current prices.

    Groups alerts by symbol to minimize API calls, then evaluates each
    alert's condition. Triggered alerts get deactivated and a notification
    is created for the user.

    Args:
        ctx: arq job context dict.
    """
    # Bind per-job context so all log lines carry worker and job_id fields
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        worker="alert-worker", job_id=str(ctx.get("job_id", ""))
    )
    _last_error = ""
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
            "Evaluating alerts",
            alert_count=len(alerts),
            symbol_count=len(by_symbol),
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
                        "Alert triggered",
                        symbol=symbol,
                        condition=alert.condition,
                        target=target,
                        current_price=current_price,
                    )

        if triggered_count > 0:
            await session.commit()
            logger.info("Triggered alerts", count=triggered_count)

        # ── soft stop-loss check ───────────────────────────────────────────
        await _check_soft_stops(session)

    except Exception as exc:
        _last_error = str(exc)[:300]
        logger.exception("Error evaluating price alerts")
        await session.rollback()
    finally:
        await session.close()

        # Re-enqueue: 60s during market hours, 300s outside.
        # MUST be inside finally so early returns / exceptions don't break the chain.
        defer_by = 60 if _is_market_open() else 300
        try:
            pool = await create_pool(RedisSettings.from_dsn(_REDIS_URL))
            await pool.enqueue_job("evaluate_price_alerts", _defer_by=defer_by, _queue_name="arq:alert")
            await pool.close()
        except Exception as exc:
            logger.error("Failed to re-enqueue alert evaluation", error=str(exc))

        # Write heartbeat regardless of success/failure
        await write_worker_heartbeat(
            "alert-worker", _REDIS_URL, jobs_processed_delta=1, last_error=_last_error
        )


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
        await pool.enqueue_job("evaluate_price_alerts", _defer_by=10, _queue_name="arq:alert")
        await pool.close()
    except Exception:
        logger.exception("Failed to seed initial alert evaluation job")


# -- arq worker settings ──────────────────────────────────────────────────


class WorkerSettings:
    """arq worker configuration for the alert evaluation loop.

    Run with: ``arq app.trading.alert_worker.WorkerSettings``
    """

    functions = [evaluate_price_alerts, sync_degiro_portfolio]
    cron_jobs = [cron(sync_degiro_portfolio, hour=2, minute=0)]
    queue_name = "arq:alert"
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(_REDIS_URL)
    max_jobs = 5
    job_timeout = 120
