"""
Trading Worker — arq background worker for async backtest execution.

Runs as a separate process: ``arq app.trading.worker.WorkerSettings``

Job lifecycle:
    1. Load BacktestResult from DB (status=pending)
    2. Set status=running
    3. Resolve strategy → load signal generator from registry
    4. Fetch OHLCV data via NormalizedDataService
    5. Run BacktestEngine
    6. Compute metrics + benchmark comparison
    7. Check overfit score
    8. Store results_json, metrics_json, benchmark_json
    9. Set status=completed (or failed with error_message)
   10. Write audit log entry
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import UUID

logger = logging.getLogger("trading.worker")

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


# -- Redis pool for enqueuing from the API ─────────────────────────────────

_redis_pool = None


async def _get_redis():
    """Lazily create and return the arq Redis pool.

    Returns:
        arq Redis connection pool.
    """
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = await create_pool(RedisSettings.from_dsn(_REDIS_URL))
    return _redis_pool


async def enqueue_backtest(backtest_id: str) -> None:
    """Enqueue a backtest job to the arq worker.

    Called from the API route after creating a BacktestResult row.

    Args:
        backtest_id: UUID string of the BacktestResult to process.
    """
    redis = await _get_redis()
    await redis.enqueue_job("run_backtest", backtest_id)


# -- Backtest job ──────────────────────────────────────────────────────────

async def run_backtest(ctx: dict, backtest_id: str) -> None:
    """Execute a backtest job.

    Loaded by arq as a background task. Fetches the pending BacktestResult,
    runs the strategy against historical data, computes metrics, and stores
    results.

    Args:
        ctx:          arq job context.
        backtest_id:  UUID string of the BacktestResult to process.
    """
    # Late imports to avoid circular references at module load time
    from ..models import BacktestResult, Strategy, AuditLog
    from .engine import BacktestEngine
    from .engine.strategies import get_strategy
    from .engine import metrics
    from .providers.yfinance_provider import YFinanceProvider
    from .providers.normalizer import NormalizedDataService

    session = await _get_session()
    try:
        # 1. Load the backtest row
        stmt = select(BacktestResult).where(
            BacktestResult.result_id == backtest_id
        )
        result = await session.execute(stmt)
        bt = result.scalar_one_or_none()
        if not bt or bt.status != "pending":
            logger.warning("Backtest %s not found or not pending.", backtest_id)
            return

        # 2. Mark as running
        bt.status = "running"
        await session.commit()

        # 3. Load the strategy definition
        strat_stmt = select(Strategy).where(
            Strategy.strategy_id == bt.strategy_id
        )
        strat_result = await session.execute(strat_stmt)
        strategy = strat_result.scalar_one_or_none()
        if not strategy:
            bt.status = "failed"
            bt.error_message = "Strategy not found."
            bt.completed_at = datetime.utcnow()
            await session.commit()
            return

        # Resolve signal generator from the built-in registry
        definition = strategy.definition_json or {}
        slug = definition.get("strategy_slug", "")
        params = definition.get("params", {})

        # Apply any parameter overrides from the backtest request
        if bt.parameters_json:
            params.update(bt.parameters_json)

        try:
            strat_module = get_strategy(slug)
        except KeyError:
            bt.status = "failed"
            bt.error_message = f"Unknown strategy slug: {slug}"
            bt.completed_at = datetime.utcnow()
            await session.commit()
            return

        signal_fn = strat_module["generate_signals"]

        # 4. Fetch OHLCV data
        provider = YFinanceProvider()
        data_service = NormalizedDataService(provider)
        bars = await data_service.get_bars(
            bt.symbol, bt.interval, bt.start_date, bt.end_date,
        )

        if not bars:
            bt.status = "failed"
            bt.error_message = f"No market data for {bt.symbol} ({bt.interval})."
            bt.completed_at = datetime.utcnow()
            await session.commit()
            return

        # 5. Run backtest
        engine = BacktestEngine()
        initial_capital = 10_000.0
        output = engine.run(
            signal_fn=signal_fn,
            bars=bars,
            params=params,
            initial_capital=initial_capital,
            commission=float(bt.commission_per_trade),
            slippage_pct=float(bt.slippage_pct),
        )

        # 6. Compute metrics
        equity_values = [pt["equity"] for pt in output.equity_curve]
        num_params = len(params)

        # Determine bars-per-year based on interval
        bpy_map = {"1m": 252 * 390, "5m": 252 * 78, "15m": 252 * 26,
                    "1h": 252 * 6.5, "1d": 252, "1wk": 52, "1mo": 12}
        bars_per_year = bpy_map.get(bt.interval, 252)

        all_metrics = metrics.compute_all(
            trades=output.trades,
            equity_curve=equity_values,
            initial_equity=initial_capital,
            final_equity=output.final_equity,
            num_bars=len(bars),
            bars_per_year=bars_per_year,
            num_params=num_params,
        )

        # 7. Build buy-and-hold benchmark
        buy_hold = [initial_capital * (b.close / bars[0].close) for b in bars]
        benchmark = metrics.benchmark_comparison(equity_values, buy_hold)

        # 8. Serialize results
        trades_json = [
            {
                "entry_date": t.entry_date.isoformat(),
                "exit_date": t.exit_date.isoformat(),
                "direction": t.direction,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "quantity": round(t.quantity, 6),
                "commission": t.commission,
                "pnl": t.pnl,
                "pnl_pct": t.pnl_pct,
                "bars_held": t.bars_held,
            }
            for t in output.trades
        ]

        signals_json = [
            {
                "timestamp": s.timestamp.isoformat(),
                "signal_type": s.signal_type,
                "direction": s.direction,
                "price": s.price,
            }
            for s in output.signals
        ]

        bt.results_json = {
            "trades": trades_json,
            "signals": signals_json,
            "equity_curve": output.equity_curve,
            "final_equity": output.final_equity,
        }
        bt.metrics_json = all_metrics
        bt.benchmark_json = benchmark
        bt.overfit_warning = all_metrics.get("overfit_warning", False)
        bt.status = "completed"
        bt.completed_at = datetime.utcnow()

        # 9. Audit log
        audit = AuditLog(
            user_id=bt.user_id,
            action="backtest_completed",
            table_name="backtest_results",
            record_id=bt.result_id,
            new_values={
                "symbol": bt.symbol,
                "total_trades": all_metrics["total_trades"],
                "total_return": all_metrics["total_return"],
                "sharpe_ratio": all_metrics["sharpe_ratio"],
            },
        )
        session.add(audit)
        await session.commit()

        logger.info(
            "Backtest %s completed: %d trades, %.1f%% return, Sharpe %.2f",
            backtest_id,
            all_metrics["total_trades"],
            all_metrics["total_return"],
            all_metrics["sharpe_ratio"],
        )

    except Exception as exc:
        logger.exception("Backtest %s failed: %s", backtest_id, exc)
        try:
            bt.status = "failed"
            bt.error_message = str(exc)[:500]
            bt.completed_at = datetime.utcnow()
            await session.commit()
        except Exception:
            pass
    finally:
        await session.close()


# -- arq worker settings ───────────────────────────────────────────────────

class WorkerSettings:
    """arq worker configuration.

    Run with: ``arq app.trading.worker.WorkerSettings``
    """
    functions = [run_backtest]
    redis_settings = RedisSettings.from_dsn(_REDIS_URL)
    max_jobs = 10
    job_timeout = 300  # 5 minutes max per backtest
