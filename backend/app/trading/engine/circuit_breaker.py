"""
engine/circuit_breaker.py — Drawdown circuit breaker for strategy risk control.

Monitors a strategy's equity curve (from backtests or simulated P&L) and
automatically pauses the strategy when the drawdown from the peak exceeds
a configurable threshold.

When the circuit breaker triggers:
    1. All active signals for the strategy are deactivated.
    2. A notification is dispatched to the user.
    3. An audit log entry is recorded.

The breaker is checked after each backtest completes and (in Phase 6) on
every new paper-trading tick.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger("trading.circuit_breaker")


# Default maximum drawdown before pausing a strategy (15%)
DEFAULT_MAX_DRAWDOWN_PCT = 15.0


@dataclass
class BreakerStatus:
    """Result of a circuit breaker check.

    Attributes:
        tripped:        True if drawdown exceeds the threshold.
        current_dd_pct: Current drawdown from peak as a positive percentage.
        max_allowed_pct: The configured maximum drawdown threshold.
        peak_equity:    Highest equity value recorded.
        current_equity: Most recent equity value.
    """
    tripped: bool
    current_dd_pct: float
    max_allowed_pct: float
    peak_equity: float
    current_equity: float


def check_drawdown(
    equity_values: List[float],
    max_drawdown_pct: float = DEFAULT_MAX_DRAWDOWN_PCT,
) -> BreakerStatus:
    """Check if the equity curve's drawdown exceeds the threshold.

    Computes the current drawdown from the peak equity value and
    returns a ``BreakerStatus`` indicating whether the circuit
    breaker should trip.

    Args:
        equity_values:   List of equity values (one per bar / tick).
        max_drawdown_pct: Maximum allowed drawdown as a positive
                          percentage (e.g. 15.0 for 15%).

    Returns:
        ``BreakerStatus`` with trip status and diagnostic values.
    """
    if not equity_values:
        return BreakerStatus(
            tripped=False,
            current_dd_pct=0.0,
            max_allowed_pct=max_drawdown_pct,
            peak_equity=0.0,
            current_equity=0.0,
        )

    peak = equity_values[0]
    for val in equity_values:
        if val > peak:
            peak = val

    current = equity_values[-1]

    if peak <= 0:
        return BreakerStatus(
            tripped=False,
            current_dd_pct=0.0,
            max_allowed_pct=max_drawdown_pct,
            peak_equity=peak,
            current_equity=current,
        )

    dd_pct = round(((peak - current) / peak) * 100, 4)
    tripped = dd_pct >= max_drawdown_pct

    if tripped:
        logger.warning(
            "Circuit breaker TRIPPED: drawdown %.2f%% >= threshold %.1f%%",
            dd_pct, max_drawdown_pct,
        )

    return BreakerStatus(
        tripped=tripped,
        current_dd_pct=dd_pct,
        max_allowed_pct=max_drawdown_pct,
        peak_equity=round(peak, 2),
        current_equity=round(current, 2),
    )


async def check_circuit_breaker(
    strategy_id: str,
    user_id: str,
    session,
    max_drawdown_pct: Optional[float] = None,
) -> BreakerStatus:
    """Check and enforce the circuit breaker for a strategy.

    Loads recent backtest equity curves from the DB, computes current
    drawdown, and if the breaker trips:
      1. Deactivates all active signals for the strategy.
      2. Creates a notification for the user.
      3. Logs the event to the audit trail.

    Args:
        strategy_id:     UUID string of the strategy.
        user_id:         UUID string of the owning user.
        session:         Async SQLAlchemy session.
        max_drawdown_pct: Threshold override (default 15%).

    Returns:
        ``BreakerStatus`` indicating current state.
    """
    from sqlalchemy import text

    if max_drawdown_pct is None:
        max_drawdown_pct = DEFAULT_MAX_DRAWDOWN_PCT

    # Load the most recent completed backtest's equity curve
    result = await session.execute(
        text(
            "SELECT results_json "
            "FROM backtest_results "
            "WHERE strategy_id = :sid AND user_id = :uid "
            "  AND status = 'completed' "
            "ORDER BY created_at DESC "
            "LIMIT 1"
        ),
        {"sid": strategy_id, "uid": user_id},
    )
    row = result.fetchone()
    if not row or not row[0]:
        return BreakerStatus(
            tripped=False,
            current_dd_pct=0.0,
            max_allowed_pct=max_drawdown_pct,
            peak_equity=0.0,
            current_equity=0.0,
        )

    rj = row[0]
    curve = rj.get("equity_curve", [])
    equity_values = []
    for pt in curve:
        val = pt.get("equity") or pt.get("value")
        if val is not None:
            equity_values.append(float(val))

    status = check_drawdown(equity_values, max_drawdown_pct)

    if status.tripped:
        await _trip_breaker(strategy_id, user_id, session, status)

    return status


async def _trip_breaker(
    strategy_id: str,
    user_id: str,
    session,
    status: BreakerStatus,
) -> None:
    """Execute circuit breaker trip: deactivate signals, notify, and log.

    Args:
        strategy_id: UUID string of the strategy.
        user_id:     UUID string of the user.
        session:     Async SQLAlchemy session.
        status:      The BreakerStatus that triggered the trip.
    """
    from sqlalchemy import text
    import uuid

    # 1. Deactivate all active signals for this strategy
    await session.execute(
        text(
            "UPDATE trading_signals "
            "SET is_active = FALSE "
            "WHERE strategy_id = :sid AND user_id = :uid AND is_active = TRUE"
        ),
        {"sid": strategy_id, "uid": user_id},
    )

    # 2. Create notification
    await session.execute(
        text(
            "INSERT INTO notifications "
            "(notification_id, user_id, event_type, title, body, metadata_json) "
            "VALUES (:nid, :uid, :etype, :title, :body, :meta)"
        ),
        {
            "nid": str(uuid.uuid4()),
            "uid": user_id,
            "etype": "circuit_breaker_tripped",
            "title": "Circuit Breaker Tripped",
            "body": (
                f"Strategy paused — drawdown of {status.current_dd_pct:.1f}% "
                f"exceeded {status.max_allowed_pct:.0f}% threshold."
            ),
            "meta": "{}",
        },
    )

    # 3. Audit log
    await session.execute(
        text(
            "INSERT INTO audit_log "
            "(user_id, action, table_name, record_id, new_values) "
            "VALUES (:uid, :action, :tbl, :rid, :vals::jsonb)"
        ),
        {
            "uid": user_id,
            "action": "circuit_breaker_tripped",
            "tbl": "trading_signals",
            "rid": strategy_id,
            "vals": f'{{"drawdown_pct": {status.current_dd_pct}, "threshold": {status.max_allowed_pct}}}',
        },
    )

    await session.commit()

    logger.info(
        "Circuit breaker tripped for strategy %s (user %s): "
        "deactivated signals, notified user.",
        strategy_id, user_id,
    )
