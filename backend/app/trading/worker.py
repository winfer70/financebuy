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

import os
import uuid as _uuid_mod
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

import structlog
from arq import create_pool
from arq.connections import RedisSettings
from arq.cron import cron
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import UUID

from ..logging_config import configure_structlog
from .heartbeat import write_worker_heartbeat
from .scanner_worker import run_scanner  # noqa: F401 — registered in WorkerSettings
from ..services.degiro_sync import sync_degiro_portfolio  # noqa: F401 — registered in WorkerSettings

# Configure structlog before any logger is obtained — idempotent guard inside
configure_structlog()
logger = structlog.get_logger("trading.worker")

# -- Database setup (standalone — worker runs outside FastAPI) ─────────────

_DATABASE_URL = os.environ["DATABASE_URL"]
_REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

_engine = create_async_engine(_DATABASE_URL, echo=False, pool_size=5, max_overflow=2, pool_pre_ping=True)
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


def _is_market_open() -> bool:
    """Return True when the US equity market is currently open (ET 9:30–16:00, Mon–Fri).

    Uses a UTC-5 approximation (EST).  Assumes DST does not change results by
    more than 1 hour, which is acceptable for re-queue timing decisions.

    Returns:
        bool: True if market hours are active.
    """
    import pytz
    now_et = datetime.now(pytz.timezone("America/New_York"))
    if now_et.weekday() >= 5:  # Saturday or Sunday
        return False
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now_et <= market_close


async def enqueue_backtest(backtest_id: str) -> None:
    """Enqueue a backtest job to the arq worker.

    Called from the API route after creating a BacktestResult row.

    Args:
        backtest_id: UUID string of the BacktestResult to process.
    """
    redis = await _get_redis()
    await redis.enqueue_job("run_backtest", backtest_id, _queue_name="arq:trading")


async def enqueue_portfolio_rules(portfolio_id: str, user_id: str, schedule: str = "on_demand") -> str:
    """Enqueue a portfolio rules engine job to the arq trading worker.

    Called from the API route after verifying portfolio ownership.

    Args:
        portfolio_id: UUID string of the portfolio to evaluate.
        user_id:      UUID string of the portfolio owner.
        schedule:     Execution context hint: on_demand | market_hours | end_of_day.

    Returns:
        arq job_id string, or empty string on failure.
    """
    try:
        redis = await _get_redis()
        job = await redis.enqueue_job(
            "run_portfolio_rules", portfolio_id, user_id, schedule,
            _queue_name="arq:trading",
        )
        return job.job_id if job else ""
    except Exception as exc:
        logger.error("enqueue_portfolio_rules failed", portfolio_id=portfolio_id, error=str(exc))
        return ""


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
    # Bind per-job context so all log lines carry worker name and backtest_id
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        worker="trading-worker", backtest_id=backtest_id
    )
    _last_error = ""

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
            logger.warning("Backtest not found or not pending", backtest_id=backtest_id)
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

        # Resolve signal generator based on strategy type
        definition = strategy.definition_json or {}
        slug = definition.get("strategy_slug", "")
        params = definition.get("params", {})

        # Apply any parameter overrides from the backtest request
        if bt.parameters_json:
            params.update(bt.parameters_json)

        strategy_type = strategy.strategy_type or "builtin"

        if strategy_type == "pinescript":
            # PineScript strategy — use the PineScript executor
            from .pinescript.executor import resolve_pinescript_signals
            signal_fn = resolve_pinescript_signals(definition)
        elif strategy_type == "composed":
            # Composed strategy — use the composition engine
            from .engine.composition import resolve_composed_signals
            signal_fn = resolve_composed_signals(definition)
        else:
            # Built-in / learned / ml — resolve from the registry
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
            "Backtest completed",
            backtest_id=backtest_id,
            total_trades=all_metrics["total_trades"],
            total_return=all_metrics["total_return"],
            sharpe_ratio=all_metrics["sharpe_ratio"],
        )

    except Exception as exc:
        _last_error = str(exc)[:300]
        logger.exception("Backtest failed", backtest_id=backtest_id, error=str(exc))
        try:
            bt.status = "failed"
            bt.error_message = str(exc)[:500]
            bt.completed_at = datetime.utcnow()
            await session.commit()
        except Exception:
            pass
    finally:
        await session.close()
        # Write heartbeat after every job execution, successful or failed
        await write_worker_heartbeat(
            "trading-worker", _REDIS_URL, jobs_processed_delta=1, last_error=_last_error
        )


# -- Portfolio rules job ───────────────────────────────────────────────────────

async def run_portfolio_rules(ctx: dict, portfolio_id: str, user_id: str, schedule: str = "on_demand") -> None:
    """Execute the portfolio rules engine for all open positions in a portfolio.

    Job lifecycle:
        1. Load all non-closed positions for the portfolio.
        2. Load user rule config from users.preferences["portfolio_rules"].
        3. Fetch live prices via yfinance for all position tickers.
        4. Fetch 80-day daily closes for time_stop rule; compute SMA50 sessions.
        5. Compute portfolio-wide aggregates (total, semi, bucket values).
        6. For each position, build RuleContext and call run_all_rules().
        7. Upsert rule_alerts rows (dedup by user_id + rule_type + title).
        8. Expire active alerts whose ticker is no longer an open position.
        9. Create Notification rows for warning and critical alerts.
       10. Re-enqueue self in 60 s when schedule="market_hours" and market open.
       11. Write worker heartbeat.

    Args:
        ctx:          arq job context dict.
        portfolio_id: UUID string of the portfolio to evaluate.
        user_id:      UUID string of the portfolio owner.
        schedule:     Execution hint: on_demand | market_hours | end_of_day.
    """
    # Late imports to avoid circular references and to keep module load fast
    import asyncio
    import pandas as pd
    import yfinance as yf

    from ..models import Portfolio, PortfolioPosition, User, RuleAlert, Notification
    from ..schemas import PortfolioRulesConfig
    from .rules import run_all_rules, RuleContext

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        worker="trading-worker",
        portfolio_id=portfolio_id,
        user_id=user_id,
    )

    _last_error = ""
    session = _SessionLocal()

    try:
        loop = asyncio.get_event_loop()
        portfolio_uuid = _uuid_mod.UUID(portfolio_id)
        user_uuid = _uuid_mod.UUID(user_id)

        # ── 1. Verify portfolio ownership and load open positions ─────────────
        port_res = await session.execute(
            select(Portfolio).where(
                Portfolio.portfolio_id == portfolio_uuid,
                Portfolio.user_id == user_uuid,
            )
        )
        portfolio = port_res.scalar_one_or_none()
        if not portfolio:
            logger.warning("Portfolio not found or wrong owner", portfolio_id=portfolio_id)
            return

        pos_res = await session.execute(
            select(PortfolioPosition).where(
                PortfolioPosition.portfolio_id == portfolio_uuid,
                PortfolioPosition.closed_at.is_(None),
                PortfolioPosition.is_excluded.is_(False),
            )
        )
        positions = pos_res.scalars().all()

        if not positions:
            logger.info("No open positions to evaluate", portfolio_id=portfolio_id)
            return

        # ── 2. Load user rule config ───────────────────────────────────────────
        user_res = await session.execute(
            select(User).where(User.user_id == user_uuid)
        )
        user_obj = user_res.scalar_one_or_none()
        prefs = (user_obj.preferences or {}) if user_obj else {}
        rules_config_raw = prefs.get("portfolio_rules", {})
        try:
            rules_config_obj = PortfolioRulesConfig(**rules_config_raw)
        except Exception:
            rules_config_obj = PortfolioRulesConfig()
        config = rules_config_obj.dict()
        enabled_rules = set(config.get("enabled_rules", []))

        unique_tickers = list({pos.ticker for pos in positions})

        # ── 3. Fetch live prices ──────────────────────────────────────────────
        def _fetch_prices(symbols):
            """Fetch latest close price for each symbol via yfinance.

            Args:
                symbols: List of ticker strings.

            Returns:
                Dict mapping ticker → float price.
            """
            prices = {}
            for sym in symbols:
                try:
                    hist = yf.Ticker(sym).history(period="2d", interval="1d")
                    if not hist.empty:
                        prices[sym] = float(hist["Close"].iloc[-1])
                except Exception:
                    pass
            return prices

        price_map: dict = await loop.run_in_executor(None, lambda: _fetch_prices(unique_tickers))

        # ── 4. Fetch 80-day OHLCV and compute SMA50 sessions for time_stop ────
        ohlcv_map: dict = {}  # ticker -> list[float] oldest-to-newest closes

        if "time_stop" in enabled_rules:
            def _fetch_ohlcv(symbols):
                """Fetch last 80 daily closes for each symbol.

                Args:
                    symbols: List of ticker strings.

                Returns:
                    Dict mapping ticker → list of float closes.
                """
                result = {}
                for sym in symbols:
                    try:
                        hist = yf.Ticker(sym).history(period="100d", interval="1d")
                        if not hist.empty:
                            result[sym] = [float(c) for c in hist["Close"].values[-80:]]
                        else:
                            result[sym] = []
                    except Exception:
                        result[sym] = []
                return result

            ohlcv_map = await loop.run_in_executor(None, lambda: _fetch_ohlcv(unique_tickers))

        def _sessions_below_sma50(closes_list: list) -> int:
            """Count consecutive most-recent sessions a ticker traded below its SMA50.

            Args:
                closes_list: Daily close prices oldest-to-newest (need >= 51 values).

            Returns:
                Integer count of consecutive sessions below rolling SMA50.
            """
            if len(closes_list) < 51:
                return 0
            closes = pd.Series(closes_list, dtype=float)
            sma50 = closes.rolling(50).mean()
            count = 0
            for i in range(len(closes) - 1, 48, -1):
                if pd.isna(sma50.iloc[i]):
                    break
                if closes.iloc[i] < sma50.iloc[i]:
                    count += 1
                else:
                    break
            return count

        # ── 5. Fetch fundamentals / analyst targets per ticker ────────────────
        fundamentals_map: dict = {}
        need_fundamentals = bool(
            enabled_rules & {"fundamentals", "analyst_consensus", "pre_earnings"}
        )

        if need_fundamentals:
            def _fetch_fundamentals(symbols):
                """Fetch analyst target, D/E, margins, insider data, and earnings dates.

                Args:
                    symbols: Unique ticker list.

                Returns:
                    Dict mapping ticker → dict of fundamental values.
                """
                result = {}
                for sym in symbols:
                    entry: dict = {}
                    try:
                        t = yf.Ticker(sym)
                        info = t.info

                        # Analyst median price target
                        entry["analyst_target"] = (
                            info.get("targetMedianPrice") or info.get("targetMeanPrice")
                        )

                        # Debt-to-equity (yfinance returns percent already, e.g. 150.0)
                        entry["debt_to_equity"] = info.get("debtToEquity")

                        # Gross margin as percentage (yfinance gives decimal 0–1)
                        gm = info.get("grossMargins")
                        entry["gross_margin_recent"] = float(gm) * 100 if gm is not None else None

                        # Gross margin YoY delta from quarterly financials
                        gm_delta = None
                        try:
                            qf = t.quarterly_financials
                            if qf is not None and not qf.empty:
                                if "Gross Profit" in qf.index and "Total Revenue" in qf.index:
                                    gp = qf.loc["Gross Profit"].values
                                    tr = qf.loc["Total Revenue"].values
                                    if (
                                        len(gp) >= 5
                                        and tr[0] not in (0, None)
                                        and tr[4] not in (0, None)
                                    ):
                                        gm_now = float(gp[0]) / float(tr[0]) * 100
                                        gm_then = float(gp[4]) / float(tr[4]) * 100
                                        gm_delta = gm_now - gm_then
                        except Exception:
                            pass
                        entry["gross_margin_yoy_delta"] = gm_delta

                        # Insider net buying/selling as fraction of shares outstanding
                        insider_net = None
                        try:
                            txns = t.insider_transactions
                            shares_out = info.get("sharesOutstanding")
                            if (
                                txns is not None
                                and not txns.empty
                                and shares_out
                                and shares_out > 0
                                and "Shares" in txns.columns
                            ):
                                net_shares = txns["Shares"].sum()
                                insider_net = float(net_shares) / float(shares_out)
                        except Exception:
                            pass
                        entry["insider_net_12m"] = insider_net

                        # Next earnings date
                        earnings_date = None
                        try:
                            cal = t.calendar
                            if cal is not None and not cal.empty and "Earnings Date" in cal.index:
                                ed = cal.loc["Earnings Date"].iloc[0]
                                ts = pd.Timestamp(ed)
                                earnings_date = ts.date()
                        except Exception:
                            pass
                        entry["next_earnings_date"] = earnings_date

                    except Exception:
                        pass
                    result[sym] = entry
                return result

            fundamentals_map = await loop.run_in_executor(
                None, lambda: _fetch_fundamentals(unique_tickers)
            )

        # ── 6. Compute portfolio-wide aggregates ───────────────────────────────
        total_value = Decimal("0")
        semi_total = Decimal("0")
        bucket_vals: dict = {1: Decimal("0"), 2: Decimal("0"), 3: Decimal("0")}

        for pos in positions:
            price = Decimal(str(price_map.get(pos.ticker, float(pos.purchase_price))))
            pos_value = price * Decimal(str(pos.quantity))
            total_value += pos_value
            if pos.is_semi:
                semi_total += pos_value
            if pos.bucket in (1, 2, 3):
                bucket_vals[pos.bucket] += pos_value

        # ── 7. Build RuleContext and run rules for each position ───────────────
        all_new_alerts = []

        for pos in positions:
            ticker = pos.ticker
            price = Decimal(str(price_map.get(ticker, float(pos.purchase_price))))
            purchase_price = Decimal(str(pos.purchase_price))
            stop_loss = Decimal(str(pos.stop_loss or 0))
            profit_taking = Decimal(str(pos.profit_taking or 0))
            t2_usd = Decimal(str(pos.t2_usd)) if pos.t2_usd is not None else None
            quantity = Decimal(str(pos.quantity))

            cost_basis_total = purchase_price * quantity
            current_value = price * quantity
            pnl_pct = (
                (price - purchase_price) / purchase_price
                if purchase_price > 0
                else Decimal("0")
            )

            closes = ohlcv_map.get(ticker, [])
            sessions_below = _sessions_below_sma50(closes)

            fund = fundamentals_map.get(ticker, {})

            ctx_obj = RuleContext(
                position_id=0,     # Soft ref — UUID PK cannot fit in BigInteger
                portfolio_id=0,    # Soft ref — UUID PK cannot fit in BigInteger
                user_id=user_id,
                ticker=ticker,
                quantity=quantity,
                purchase_price=purchase_price,
                stop_loss=stop_loss,
                profit_taking=profit_taking,
                t2_usd=t2_usd,
                is_semi=bool(pos.is_semi),
                sector=pos.sector,
                date_entered=pos.date_entered,
                bucket=pos.bucket,
                current_price=price,
                pnl_pct=pnl_pct,
                cost_basis_total=cost_basis_total,
                current_value=current_value,
                daily_closes=[Decimal(str(c)) for c in closes],
                sessions_below_sma50=sessions_below,
                debt_to_equity=fund.get("debt_to_equity"),
                gross_margin_recent=fund.get("gross_margin_recent"),
                gross_margin_yoy_delta=fund.get("gross_margin_yoy_delta"),
                insider_net_12m=fund.get("insider_net_12m"),
                next_earnings_date=fund.get("next_earnings_date"),
                portfolio_total_value=total_value,
                semi_total_value=semi_total,
                bucket_values=bucket_vals,
                config=config,
            )

            analyst_target = fund.get("analyst_target")
            alerts = run_all_rules(ctx_obj, analyst_target=analyst_target)
            all_new_alerts.extend(alerts)

        # ── 8. Upsert rule_alerts (dedup by user_id + rule_type + title) ──────
        for alert_data in all_new_alerts:
            existing_stmt = select(RuleAlert).where(
                RuleAlert.user_id == user_uuid,
                RuleAlert.state == "active",
                RuleAlert.rule_type == alert_data.rule_type,
                RuleAlert.title == alert_data.title,
            )
            existing = (await session.execute(existing_stmt)).scalar_one_or_none()

            if existing:
                # Update body, triggered_value, and severity if alert still active
                existing.body = alert_data.body
                existing.triggered_value = alert_data.triggered_value
                existing.severity = alert_data.severity
            else:
                new_alert = RuleAlert(
                    user_id=user_uuid,
                    rule_type=alert_data.rule_type,
                    severity=alert_data.severity,
                    title=alert_data.title,
                    body=alert_data.body,
                    triggered_value=alert_data.triggered_value,
                    state="active",
                )
                session.add(new_alert)

        # ── 9. Expire active alerts for tickers no longer open ────────────────
        open_tickers = {pos.ticker for pos in positions}
        active_alerts_stmt = select(RuleAlert).where(
            RuleAlert.user_id == user_uuid,
            RuleAlert.state == "active",
        )
        active_alerts = (await session.execute(active_alerts_stmt)).scalars().all()

        for alert in active_alerts:
            # Extract ticker from title format "RuleDesc: TICKER ..."
            if not alert.title:
                continue
            parts = alert.title.split(":")
            if len(parts) < 2:
                continue
            first_word = parts[1].strip().split(" ")[0]
            # Ticker heuristic: uppercase, 1–10 chars
            if first_word and first_word.isupper() and 1 <= len(first_word) <= 10:
                if first_word not in open_tickers:
                    alert.state = "expired"

        # ── 10. Create Notification rows for warning / critical alerts ─────────
        for alert_data in all_new_alerts:
            if alert_data.severity in ("warning", "critical"):
                notif = Notification(
                    user_id=user_uuid,
                    event_type=f"rule_alert_{alert_data.rule_type}",
                    title=alert_data.title or "",
                    body=alert_data.body,
                    metadata_json={
                        "rule_type": alert_data.rule_type,
                        "severity": alert_data.severity,
                        "portfolio_id": portfolio_id,
                    },
                )
                session.add(notif)

        await session.commit()

        logger.info(
            "Portfolio rules run complete",
            portfolio_id=portfolio_id,
            positions_evaluated=len(positions),
            alerts_generated=len(all_new_alerts),
        )

    except Exception as exc:
        _last_error = str(exc)[:300]
        logger.exception("Portfolio rules job failed", portfolio_id=portfolio_id, error=str(exc))
        try:
            await session.rollback()
        except Exception:
            pass
    finally:
        await session.close()

    # ── 11. Re-enqueue if market_hours and market is still open ───────────────
    if schedule == "market_hours" and _is_market_open():
        try:
            redis = await _get_redis()
            await redis.enqueue_job(
                "run_portfolio_rules",
                portfolio_id,
                user_id,
                schedule,
                _defer_by=60,
                _queue_name="arq:trading",
            )
        except Exception as requeue_exc:
            logger.warning("run_portfolio_rules re-enqueue failed", error=str(requeue_exc))

    # Always write heartbeat regardless of success/failure
    await write_worker_heartbeat(
        "trading-worker", _REDIS_URL, jobs_processed_delta=1, last_error=_last_error
    )


# -- arq worker settings ───────────────────────────────────────────────────

async def _periodic_heartbeat(ctx: dict) -> None:
    """Keep the health-check key alive between jobs.

    Runs every 5 minutes via arq cron so the worker shows healthy
    even when no backtest or scanner jobs are queued.
    """
    await write_worker_heartbeat(
        "trading-worker", _REDIS_URL, jobs_processed_delta=0, last_error=""
    )


async def _worker_startup(ctx: dict) -> None:
    """Write an initial heartbeat when the trading worker process starts.

    Called by arq's on_startup hook. Signals to /metrics that the worker
    is alive before any backtest jobs have been processed.

    Args:
        ctx: arq worker context dict.
    """
    await write_worker_heartbeat(
        "trading-worker", _REDIS_URL, jobs_processed_delta=0, last_error=""
    )


class WorkerSettings:
    """arq worker configuration.

    Run with: ``arq app.trading.worker.WorkerSettings``
    """
    functions = [run_backtest, run_scanner, run_portfolio_rules, sync_degiro_portfolio]
    queue_name = "arq:trading"
    cron_jobs = [
        cron(_periodic_heartbeat, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
        cron(sync_degiro_portfolio, hour=2, minute=0),
    ]
    on_startup = _worker_startup
    redis_settings = RedisSettings.from_dsn(_REDIS_URL)
    max_jobs = 10
    job_timeout = 300  # 5 minutes max per backtest
