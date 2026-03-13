"""
paper_worker.py — Periodic evaluator for active paper trading sessions.

Runs as an arq worker: ``arq app.trading.paper_worker.WorkerSettings``

Uses a self-re-enqueuing pattern to execute every ~60 seconds.  For each
active paper trade the job:

    1. Fetches latest market data (last 100 daily bars via NormalizedDataService).
    2. Evaluates strategy signals against that data.
    3. Opens / closes positions based on the most recent signal.
    4. Checks stop-loss on every open position.
    5. Recalculates current equity (realized + unrealized P&L).
    6. Records an equity snapshot for charting.
    7. Checks the circuit breaker (max drawdown) and stops the trade if tripped.
    8. Creates in-app notifications for new positions, stop-losses, and breaker trips.

Standalone DB engine + sessionmaker — this worker runs outside FastAPI,
so it does NOT import from ``app.db``.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List

from arq.connections import RedisSettings, create_pool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger("paper_worker")

# -- Database setup (standalone — worker runs outside FastAPI) ─────────────

_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@db:5432/tickerTap",
)
_REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

_engine = create_async_engine(_DATABASE_URL, echo=False, pool_size=5)
_SessionLocal = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def _get_session() -> AsyncSession:
    """Create a new async DB session for the worker.

    Returns:
        AsyncSession instance.
    """
    return _SessionLocal()


# -- Main periodic job ─────────────────────────────────────────────────────


async def evaluate_paper_trades(ctx: dict) -> None:
    """Periodic job: evaluate all active paper trades.

    For each active paper trade:
    - Fetch latest market data via NormalizedDataService / YFinanceProvider
    - Load strategy and evaluate signals
    - Open / close positions accordingly
    - Check stop-loss on open positions
    - Update equity snapshot
    - Check circuit breaker

    Args:
        ctx: arq job context dict.
    """
    # Late imports to avoid circular references at module load time
    from ..models import (
        Notification,
        PaperTrade,
        PaperTradeEquitySnapshot,
        PaperTradePosition,
        Strategy,
    )
    from .engine.circuit_breaker import DEFAULT_MAX_DRAWDOWN_PCT, check_drawdown
    from .engine.strategies import get_strategy
    from .providers.normalizer import NormalizedDataService
    from .providers.yfinance_provider import YFinanceProvider

    session = await _get_session()
    try:
        # Load all active paper trades
        result = await session.execute(
            select(PaperTrade).where(PaperTrade.status == "active")
        )
        trades = result.scalars().all()
        if not trades:
            return

        provider = YFinanceProvider()
        norm = NormalizedDataService(provider)

        for trade in trades:
            try:
                await _evaluate_single_trade(
                    session,
                    trade,
                    norm,
                    PaperTrade,
                    PaperTradePosition,
                    PaperTradeEquitySnapshot,
                    Strategy,
                    Notification,
                    get_strategy,
                    check_drawdown,
                    DEFAULT_MAX_DRAWDOWN_PCT,
                )
            except Exception as e:
                logger.error(
                    "Error evaluating paper trade %s: %s",
                    trade.paper_trade_id,
                    e,
                )
                continue

        await session.commit()
    except Exception as e:
        logger.error("Paper trade evaluation failed: %s", e)
        await session.rollback()
    finally:
        await session.close()

        # Re-enqueue for next evaluation cycle (60 seconds).
        # MUST be inside finally so early returns / exceptions don't break the chain.
        try:
            pool = await create_pool(RedisSettings.from_dsn(_REDIS_URL))
            await pool.enqueue_job("evaluate_paper_trades", _defer_by=60)
            await pool.close()
        except Exception as exc:
            logger.error("Failed to re-enqueue paper evaluation: %s", exc)


# -- Single-trade evaluation ───────────────────────────────────────────────


async def _evaluate_single_trade(
    session: AsyncSession,
    trade,
    norm,
    PaperTrade,
    PaperTradePosition,
    PaperTradeEquitySnapshot,
    Strategy,
    Notification,
    get_strategy,
    check_drawdown,
    DEFAULT_MAX_DRAWDOWN_PCT,
) -> None:
    """Evaluate a single paper trade: fetch price, check signals, manage positions.

    Args:
        session:                    Active DB session.
        trade:                      PaperTrade ORM instance (status == "active").
        norm:                       NormalizedDataService for fetching market data.
        PaperTrade:                 PaperTrade model class (late import).
        PaperTradePosition:         PaperTradePosition model class (late import).
        PaperTradeEquitySnapshot:   PaperTradeEquitySnapshot model class (late import).
        Strategy:                   Strategy model class (late import).
        Notification:               Notification model class (late import).
        get_strategy:               Registry lookup function for builtin strategies.
        check_drawdown:             Circuit breaker check function.
        DEFAULT_MAX_DRAWDOWN_PCT:   Default drawdown threshold constant.
    """

    # 1. Load the strategy definition
    strat = (
        await session.execute(
            select(Strategy).where(Strategy.strategy_id == trade.strategy_id)
        )
    ).scalar_one_or_none()
    if not strat:
        logger.warning(
            "Paper trade %s has no valid strategy, stopping.",
            trade.paper_trade_id,
        )
        trade.status = "stopped"
        trade.stopped_at = datetime.utcnow()
        return

    definition = strat.definition_json or {}
    slug = definition.get("strategy_slug", "")
    params = dict(definition.get("params", {}))
    # Apply per-trade parameter overrides
    if trade.parameters_json:
        params.update(trade.parameters_json)

    # 2. Resolve strategy signal generator
    #    All signal generators share the signature:
    #        signal_fn(bars: List[OHLCVBar], params: Dict) -> List[Signal]
    strategy_type = strat.strategy_type or "builtin"
    if strategy_type == "pinescript":
        from .pinescript.executor import resolve_pinescript_signals

        signal_fn = resolve_pinescript_signals(definition)
    elif strategy_type == "composed":
        from .engine.composition import resolve_composed_signals

        signal_fn = resolve_composed_signals(definition)
    else:
        # Built-in / learned / ml — resolve from the registry
        try:
            strat_module = get_strategy(slug)
        except KeyError:
            logger.error(
                "Unknown strategy slug '%s' for paper trade %s",
                slug,
                trade.paper_trade_id,
            )
            return
        signal_fn = strat_module["generate_signals"]

    # 3. Fetch recent OHLCV data (last ~100 daily bars for signal generation)
    now = datetime.utcnow()
    lookback_start = now - timedelta(days=200)  # ~200 calendar days ≈ 100 trading days
    try:
        bars = await norm.get_bars(trade.symbol, "1d", lookback_start, now)
    except Exception as e:
        logger.warning("Failed to fetch data for %s: %s", trade.symbol, e)
        return

    if not bars or len(bars) < 10:
        return

    # 4. Generate signals
    try:
        signals = signal_fn(bars, params)
    except Exception as e:
        logger.warning("Signal generation failed for %s: %s", trade.symbol, e)
        return

    # 5. Determine latest signal direction and current price
    if not signals:
        return

    latest_signal = signals[-1]
    current_price = Decimal(str(bars[-1].close))

    # Map signal_type + direction to a simple buy/sell/hold integer
    # +1 = entry-long (BUY), -1 = exit or entry-short (SELL), 0 = no action
    signal_value = _signal_to_action(latest_signal)

    # 6. Load open positions for this trade
    open_pos_result = await session.execute(
        select(PaperTradePosition).where(
            PaperTradePosition.paper_trade_id == trade.paper_trade_id,
            PaperTradePosition.status == "open",
        )
    )
    open_positions = open_pos_result.scalars().all()

    # 7. Check stop-loss on open positions
    stop_loss_pct = Decimal(str(params.get("stop_loss_pct", 0.05)))
    for pos in open_positions:
        if pos.side == "long":
            loss_pct = (current_price - pos.entry_price) / pos.entry_price
            if loss_pct <= -stop_loss_pct:
                _close_position(pos, current_price)
                session.add(
                    Notification(
                        notification_id=uuid.uuid4(),
                        user_id=trade.user_id,
                        event_type="paper_stop_loss",
                        title=f"Stop-loss hit: {trade.symbol}",
                        body=(
                            f"Paper position closed at {current_price} "
                            f"(loss: {float(loss_pct) * 100:.1f}%)"
                        ),
                        metadata_json={
                            "paper_trade_id": str(trade.paper_trade_id),
                            "price": float(current_price),
                        },
                    )
                )
        elif pos.side == "short":
            loss_pct = (pos.entry_price - current_price) / pos.entry_price
            if loss_pct <= -stop_loss_pct:
                _close_position(pos, current_price)
                session.add(
                    Notification(
                        notification_id=uuid.uuid4(),
                        user_id=trade.user_id,
                        event_type="paper_stop_loss",
                        title=f"Stop-loss hit: {trade.symbol} (short)",
                        body=(
                            f"Short position closed at {current_price} "
                            f"(loss: {float(loss_pct) * 100:.1f}%)"
                        ),
                        metadata_json={
                            "paper_trade_id": str(trade.paper_trade_id),
                            "price": float(current_price),
                        },
                    )
                )

    # 8. Process signals — open / close positions
    #    Reload open positions after stop-loss processing
    open_pos_result = await session.execute(
        select(PaperTradePosition).where(
            PaperTradePosition.paper_trade_id == trade.paper_trade_id,
            PaperTradePosition.status == "open",
        )
    )
    open_positions = open_pos_result.scalars().all()

    if signal_value == 1 and not open_positions:
        # BUY signal with no open position → open long (95% of equity)
        qty = trade.current_equity / current_price * Decimal("0.95")
        session.add(
            PaperTradePosition(
                position_id=uuid.uuid4(),
                paper_trade_id=trade.paper_trade_id,
                side="long",
                entry_price=current_price,
                entry_date=datetime.utcnow(),
                quantity=qty,
                status="open",
            )
        )
        session.add(
            Notification(
                notification_id=uuid.uuid4(),
                user_id=trade.user_id,
                event_type="paper_position_opened",
                title=f"Paper LONG opened: {trade.symbol}",
                body=f"Bought {float(qty):.2f} shares at {current_price}",
                metadata_json={
                    "paper_trade_id": str(trade.paper_trade_id),
                    "side": "long",
                    "price": float(current_price),
                },
            )
        )
    elif signal_value == -1 and open_positions:
        # SELL signal → close all open positions
        for pos in open_positions:
            _close_position(pos, current_price)
        session.add(
            Notification(
                notification_id=uuid.uuid4(),
                user_id=trade.user_id,
                event_type="paper_position_closed",
                title=f"Paper position closed: {trade.symbol}",
                body=f"Closed at {current_price}",
                metadata_json={
                    "paper_trade_id": str(trade.paper_trade_id),
                    "price": float(current_price),
                },
            )
        )

    # 9. Recalculate current equity
    #    Cash = initial_capital + sum of closed position P&Ls
    closed_result = await session.execute(
        select(PaperTradePosition).where(
            PaperTradePosition.paper_trade_id == trade.paper_trade_id,
            PaperTradePosition.status == "closed",
        )
    )
    closed_positions = closed_result.scalars().all()
    realized_pnl = sum(Decimal(str(p.pnl or 0)) for p in closed_positions)

    # Open position unrealized P&L
    open_result = await session.execute(
        select(PaperTradePosition).where(
            PaperTradePosition.paper_trade_id == trade.paper_trade_id,
            PaperTradePosition.status == "open",
        )
    )
    current_open = open_result.scalars().all()
    unrealized_pnl = Decimal("0")
    for pos in current_open:
        if pos.side == "long":
            unrealized_pnl += (current_price - pos.entry_price) * pos.quantity
        else:
            unrealized_pnl += (pos.entry_price - current_price) * pos.quantity

    trade.current_equity = trade.initial_capital + realized_pnl + unrealized_pnl

    # 10. Record equity snapshot
    session.add(
        PaperTradeEquitySnapshot(
            snapshot_id=uuid.uuid4(),
            paper_trade_id=trade.paper_trade_id,
            equity=trade.current_equity,
            timestamp=datetime.utcnow(),
        )
    )

    # 11. Check circuit breaker (max drawdown)
    snap_result = await session.execute(
        select(PaperTradeEquitySnapshot.equity)
        .where(
            PaperTradeEquitySnapshot.paper_trade_id == trade.paper_trade_id
        )
        .order_by(PaperTradeEquitySnapshot.timestamp)
    )
    equity_values = [float(row[0]) for row in snap_result.all()]
    if len(equity_values) >= 2:
        breaker = check_drawdown(equity_values, DEFAULT_MAX_DRAWDOWN_PCT)
        if breaker.tripped:
            trade.status = "stopped"
            trade.stopped_at = datetime.utcnow()
            # Close any remaining open positions before stopping
            for pos in current_open:
                _close_position(pos, current_price)
            session.add(
                Notification(
                    notification_id=uuid.uuid4(),
                    user_id=trade.user_id,
                    event_type="paper_circuit_breaker",
                    title=f"Circuit breaker tripped: {trade.symbol}",
                    body=(
                        f"Paper trade stopped — drawdown of "
                        f"{breaker.current_dd_pct:.1f}% exceeded "
                        f"{breaker.max_allowed_pct:.0f}% limit."
                    ),
                    metadata_json={
                        "paper_trade_id": str(trade.paper_trade_id),
                        "drawdown_pct": breaker.current_dd_pct,
                    },
                )
            )
            logger.info(
                "Circuit breaker tripped for paper trade %s (%.1f%% drawdown)",
                trade.paper_trade_id,
                breaker.current_dd_pct,
            )


# -- Helper functions ──────────────────────────────────────────────────────


def _signal_to_action(signal) -> int:
    """Map a Signal dataclass to a simple action integer.

    Converts the engine's (signal_type, direction) pair into:
        +1  →  open long  (entry + long)
        -1  →  close / open short  (exit, stop_loss, or entry + short)
         0  →  no action

    Args:
        signal: A Signal dataclass instance from the strategy engine.

    Returns:
        Integer action code: +1 (buy), -1 (sell), or 0 (hold).
    """
    if signal.signal_type == "entry" and signal.direction == "long":
        return 1
    if signal.signal_type in ("exit", "stop_loss"):
        return -1
    if signal.signal_type == "entry" and signal.direction == "short":
        return -1
    return 0


def _close_position(pos, current_price: Decimal) -> None:
    """Close a paper trade position and compute realised P&L.

    Mutates the position in place — sets exit_price, exit_date,
    status, and pnl fields.

    Args:
        pos:            PaperTradePosition ORM instance to close.
        current_price:  Market price at which to close the position.
    """
    pos.exit_price = current_price
    pos.exit_date = datetime.utcnow()
    pos.status = "closed"
    if pos.side == "long":
        pos.pnl = (current_price - pos.entry_price) * pos.quantity
    else:
        pos.pnl = (pos.entry_price - current_price) * pos.quantity


# -- Startup hook ──────────────────────────────────────────────────────────


async def startup(ctx: dict) -> None:
    """Enqueue the first paper trade evaluation on worker start.

    Called by arq's on_startup hook.  Seeds the self-re-enqueuing
    cycle with a 10-second initial delay.

    Args:
        ctx: arq worker context dict.
    """
    try:
        pool = await create_pool(RedisSettings.from_dsn(_REDIS_URL))
        await pool.enqueue_job("evaluate_paper_trades", _defer_by=10)
        await pool.close()
    except Exception:
        pass


# -- arq worker settings ──────────────────────────────────────────────────


class WorkerSettings:
    """arq worker configuration for the paper trading evaluator.

    Run with: ``arq app.trading.paper_worker.WorkerSettings``
    """

    functions = [evaluate_paper_trades]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(_REDIS_URL)
    max_jobs = 5
    job_timeout = 120  # 2 minutes max per evaluation cycle
