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
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

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
from .notifications import notify_soft_stop

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


def _ny_now() -> datetime:
    return datetime.now(ZoneInfo("America/New_York"))


def _ny_today() -> date:
    return _ny_now().date()


def _is_market_open() -> bool:
    """Check if US market is currently open (NYSE/NASDAQ hours).

    Returns:
        True if current time is within 09:30-16:00 ET on a weekday.
    """
    now = _ny_now()
    if now.weekday() >= 5:
        return False
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now < market_close


def _is_after_rth_close() -> bool:
    """True on a weekday at or after 16:00 America/New_York."""
    now = _ny_now()
    if now.weekday() >= 5:
        return False
    close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return now >= close


def _fetch_daily_close(symbol: str) -> Optional[float]:
    """Regular-hours daily close for *today's* NY session, or None if the bar is not in yet."""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="5d", interval="1d")
        if hist is None or hist.empty:
            return None
        last = hist.iloc[-1]
        ts = hist.index[-1]
        if hasattr(ts, "tz_convert") and getattr(ts, "tz", None) is not None:
            bar_day = ts.tz_convert("America/New_York").date()
        elif getattr(ts, "tzinfo", None) is not None:
            bar_day = ts.astimezone(ZoneInfo("America/New_York")).date()
        elif hasattr(ts, "date"):
            bar_day = ts.date()
        else:
            bar_day = ts
        if bar_day != _ny_today():
            return None
        close = round(_safe_float(last["Close"]), 4)
        return close if close > 0 else None
    except Exception as exc:
        logger.warning("Failed to fetch daily close", symbol=symbol, error=str(exc))
        return None


def _stage_rec(pos: PortfolioPosition, stage: str) -> dict:
    data = pos.soft_stop_delivery_json or {}
    rec = data.get(stage) or {}
    return rec if isinstance(rec, dict) else {}


def _stage_done(pos: PortfolioPosition, stage: str, today: date) -> bool:
    rec = _stage_rec(pos, stage)
    return rec.get("date") == today.isoformat() and bool(rec.get("telegram")) and bool(rec.get("ntfy"))


def _pending_channels(pos: PortfolioPosition, stage: str, today: date) -> tuple[bool, bool, bool]:
    """Return (send_telegram, send_ntfy, send_in_app) for this stage today."""
    rec = _stage_rec(pos, stage)
    first = rec.get("date") != today.isoformat()
    send_tg = first or not bool(rec.get("telegram"))
    send_ntfy = first or not bool(rec.get("ntfy"))
    send_in_app = first or not bool(rec.get("in_app"))
    return send_tg, send_ntfy, send_in_app


def _apply_stage_result(
    pos: PortfolioPosition,
    stage: str,
    today: date,
    result: dict,
    send_telegram: bool,
    send_ntfy: bool,
    send_in_app: bool,
) -> None:
    rec = dict(_stage_rec(pos, stage))
    prev_date = rec.get("date")
    if prev_date != today.isoformat():
        rec = {}
    rec["date"] = today.isoformat()
    if send_telegram:
        rec["telegram"] = bool(result.get("telegram"))
    elif "telegram" not in rec:
        rec["telegram"] = True
    if send_ntfy:
        rec["ntfy"] = bool(result.get("ntfy"))
    elif "ntfy" not in rec:
        rec["ntfy"] = True
    if send_in_app or rec.get("in_app"):
        rec["in_app"] = True

    data = dict(pos.soft_stop_delivery_json or {})
    data[stage] = rec
    pos.soft_stop_delivery_json = data

    delivered = bool(rec.get("telegram")) or bool(rec.get("ntfy"))
    if delivered:
        if stage == "intraday":
            pos.soft_stop_intraday_on = today
        else:
            pos.soft_stop_eod_on = today


def reset_soft_stop_stages(position: PortfolioPosition) -> None:
    """Clear two-stage alert state so a new soft-stop level can fire again."""
    position.reset_soft_stop_stages()


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


async def _fire_soft_stop_stage(
    session: AsyncSession,
    pos: PortfolioPosition,
    user_id,
    stage: str,
    today: date,
    ticker: str,
    soft_stop: float,
    price: float,
) -> bool:
    """Send pending channels for one stage. Returns True if anything was attempted."""
    if _stage_done(pos, stage, today):
        return False

    send_tg, send_ntfy, send_in_app = _pending_channels(pos, stage, today)
    if not (send_tg or send_ntfy or send_in_app):
        return False

    if stage == "intraday":
        title = f"Soft stop hit: {ticker} at ${price:.2f}"
        body = (
            f"{ticker} dropped to ${price:.2f} — below your soft stop "
            f"${soft_stop:.2f}. Review the position (shakeout vs breakdown)."
        )
        event_type = "soft_stop_loss"
        ntfy_priority = 3
    else:
        title = f"CLOSE BELOW SOFT STOP: {ticker} at ${price:.2f}"
        body = (
            f"{ticker} closed at ${price:.2f}, below your soft stop "
            f"${soft_stop:.2f}. Exit at tomorrow's market open."
        )
        event_type = "soft_stop_eod"
        ntfy_priority = 5

    result = await notify_soft_stop(
        db=session,
        user_id=user_id,
        event_type=event_type,
        title=title,
        body=body,
        metadata={
            "ticker": ticker,
            "soft_stop": soft_stop,
            "triggered_price": price,
            "position_id": str(pos.position_id),
            "stage": stage,
        },
        ntfy_priority=ntfy_priority,
        send_in_app=send_in_app,
        send_telegram=send_tg,
        send_ntfy=send_ntfy,
    )
    _apply_stage_result(pos, stage, today, result, send_tg, send_ntfy, send_in_app)
    logger.info(
        "Soft stop stage",
        ticker=ticker,
        stage=stage,
        soft_stop=soft_stop,
        price=price,
        telegram=result.get("telegram"),
        ntfy=result.get("ntfy"),
    )
    return True


async def _check_soft_stops(session: AsyncSession) -> None:
    """Two-stage soft stop: intraday heads-up, then EOD close-below. Never clears the stop."""
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

    today = _ny_today()
    market_open = _is_market_open()
    after_close = _is_after_rth_close()
    if not market_open and not after_close:
        return

    by_ticker: dict[str, list] = {}
    for pos, user_id in rows:
        by_ticker.setdefault(pos.ticker, []).append((pos, user_id))

    price_map: dict[str, float] = {}
    close_map: dict[str, Optional[float]] = {}
    if market_open:
        prices = await asyncio.gather(
            *[asyncio.to_thread(_fetch_price, sym) for sym in by_ticker]
        )
        price_map = dict(zip(by_ticker.keys(), prices))
    if after_close:
        closes = await asyncio.gather(
            *[asyncio.to_thread(_fetch_daily_close, sym) for sym in by_ticker]
        )
        close_map = dict(zip(by_ticker.keys(), closes))

    fired = 0
    for ticker, entries in by_ticker.items():
        for pos, user_id in entries:
            soft_stop = float(pos.soft_stop_loss)
            if market_open:
                current_price = price_map.get(ticker, 0.0)
                if current_price > 0 and current_price <= soft_stop:
                    if await _fire_soft_stop_stage(
                        session, pos, user_id, "intraday", today, ticker, soft_stop, current_price
                    ):
                        fired += 1
            if after_close:
                daily_close = close_map.get(ticker)
                if daily_close is None:
                    continue
                if daily_close <= soft_stop:
                    if await _fire_soft_stop_stage(
                        session, pos, user_id, "eod", today, ticker, soft_stop, daily_close
                    ):
                        fired += 1
                else:
                    logger.info(
                        "Soft stop shakeout",
                        ticker=ticker,
                        close=daily_close,
                        soft_stop=soft_stop,
                    )

    if fired > 0:
        await session.commit()
        logger.info("Soft stop stages processed", count=fired)


async def evaluate_one_soft_stop(ctx: dict, position_id: str) -> None:
    """Immediate check after the user sets a soft stop — ignores the RTH gate.

    Used so a newly entered level that last price is already through still
    notifies (testing, premarket, or a stop set after the breach).
    """
    session: AsyncSession = _SessionLocal()
    try:
        result = await session.execute(
            select(PortfolioPosition, Portfolio.user_id)
            .join(Portfolio, PortfolioPosition.portfolio_id == Portfolio.portfolio_id)
            .where(
                PortfolioPosition.position_id == uuid.UUID(position_id),
                PortfolioPosition.soft_stop_loss.isnot(None),
                PortfolioPosition.closed_at.is_(None),
            )
        )
        row = result.first()
        if not row:
            return
        pos, user_id = row
        current_price = await asyncio.to_thread(_fetch_price, pos.ticker)
        if current_price <= 0:
            logger.warning("Soft stop immediate check: no price", ticker=pos.ticker)
            return
        soft_stop = float(pos.soft_stop_loss)
        if current_price > soft_stop:
            return
        today = _ny_today()
        if await _fire_soft_stop_stage(
            session, pos, user_id, "intraday", today, pos.ticker, soft_stop, current_price
        ):
            await session.commit()
            logger.info(
                "Soft stop immediate notify",
                ticker=pos.ticker,
                soft_stop=soft_stop,
                price=current_price,
            )
    except Exception:
        logger.exception("evaluate_one_soft_stop failed", position_id=position_id)
        await session.rollback()
    finally:
        await session.close()


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

        if alerts:
            # Group alerts by symbol to batch price lookups
            by_symbol: dict = {}
            for alert in alerts:
                by_symbol.setdefault(alert.symbol, []).append(alert)

            logger.info(
                "Evaluating alerts",
                alert_count=len(alerts),
                symbol_count=len(by_symbol),
            )

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
                    continue

                for alert in symbol_alerts:
                    target = float(alert.target_price)
                    if _check_condition(alert.condition, current_price, target):
                        alert.is_active = False
                        alert.triggered_at = now

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
        else:
            logger.debug("No active price alerts to evaluate")

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

    functions = [evaluate_price_alerts, sync_degiro_portfolio, evaluate_one_soft_stop]
    cron_jobs = [cron(sync_degiro_portfolio, hour=2, minute=0)]
    queue_name = "arq:alert"
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(_REDIS_URL)
    max_jobs = 5
    job_timeout = 120
