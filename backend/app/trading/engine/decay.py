"""
engine/decay.py — Strategy performance decay detection.

Monitors rolling strategy performance against historical averages to
detect when a strategy is losing its edge.  Used by the daily learner
job (Phase 3.4) and can be called on-demand from the backtest results
screen.

Algorithm:
    1. Compute a rolling 30-day Sharpe ratio over the *lookback_days* window.
    2. Compare each rolling window's Sharpe against the all-time average.
    3. If the most recent rolling Sharpe < 50% of the average for 2+
       consecutive periods → flag as decaying.

When decay is detected the notification service is invoked to alert
the user.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger("trading.decay")


@dataclass
class DecayResult:
    """Result of a strategy decay check.

    Attributes:
        is_decaying:    True if the strategy shows sustained underperformance.
        current_sharpe: Most recent rolling Sharpe ratio.
        avg_sharpe:     All-time average Sharpe ratio.
        decay_pct:      How far current Sharpe has fallen from the average (%).
        consecutive:    Number of consecutive periods below threshold.
    """
    is_decaying: bool
    current_sharpe: float
    avg_sharpe: float
    decay_pct: float
    consecutive: int


def detect_decay(
    equity_values: List[float],
    window_size: int = 30,
    threshold_pct: float = 0.50,
    min_consecutive: int = 2,
    bars_per_year: float = 252,
) -> DecayResult:
    """Detect performance decay from an equity curve.

    Computes rolling Sharpe ratios over *window_size*-bar windows across
    the equity curve.  Compares the most recent windows against the
    all-time average Sharpe to identify sustained underperformance.

    Args:
        equity_values:   List of portfolio equity values (one per bar).
        window_size:     Rolling window size in bars (default 30).
        threshold_pct:   Fraction of avg Sharpe below which decay is
                         flagged (default 0.50 = 50%).
        min_consecutive: Minimum consecutive periods below threshold
                         before flagging decay (default 2).
        bars_per_year:   Bars per year for Sharpe annualisation.

    Returns:
        ``DecayResult`` with decay status and diagnostic values.
    """
    if len(equity_values) < window_size + 1:
        return DecayResult(
            is_decaying=False,
            current_sharpe=0.0,
            avg_sharpe=0.0,
            decay_pct=0.0,
            consecutive=0,
        )

    # Compute bar-over-bar returns
    returns = []
    for i in range(1, len(equity_values)):
        prev = equity_values[i - 1]
        if prev != 0:
            returns.append((equity_values[i] - prev) / prev)
        else:
            returns.append(0.0)

    # Compute rolling Sharpe for each window
    rolling_sharpes = _rolling_sharpe(returns, window_size, bars_per_year)

    if not rolling_sharpes:
        return DecayResult(
            is_decaying=False,
            current_sharpe=0.0,
            avg_sharpe=0.0,
            decay_pct=0.0,
            consecutive=0,
        )

    avg_sharpe = sum(rolling_sharpes) / len(rolling_sharpes)
    current_sharpe = rolling_sharpes[-1]

    # Count consecutive recent periods below threshold
    cutoff = avg_sharpe * threshold_pct
    consecutive = 0
    for s in reversed(rolling_sharpes):
        if s < cutoff:
            consecutive += 1
        else:
            break

    # Decay percentage: how far current is below average
    if avg_sharpe != 0:
        decay_pct = round(((avg_sharpe - current_sharpe) / abs(avg_sharpe)) * 100, 2)
    else:
        decay_pct = 0.0

    is_decaying = consecutive >= min_consecutive

    if is_decaying:
        logger.info(
            "Decay detected: current Sharpe=%.2f, avg=%.2f, "
            "%d consecutive periods below %.0f%% threshold",
            current_sharpe, avg_sharpe, consecutive, threshold_pct * 100,
        )

    return DecayResult(
        is_decaying=is_decaying,
        current_sharpe=round(current_sharpe, 4),
        avg_sharpe=round(avg_sharpe, 4),
        decay_pct=decay_pct,
        consecutive=consecutive,
    )


async def detect_decay_for_strategy(
    strategy_id: str,
    symbol: str,
    session,
    lookback_days: int = 90,
) -> Optional[DecayResult]:
    """Load recent backtest results for a strategy and check for decay.

    Queries the ``backtest_results`` table for completed backtests of
    the given strategy + symbol, extracts equity curves, and runs
    ``detect_decay``.

    Args:
        strategy_id:  UUID string of the strategy.
        symbol:       Ticker symbol.
        session:      Async SQLAlchemy session.
        lookback_days: How far back to look for backtest results.

    Returns:
        ``DecayResult`` if sufficient data exists, else ``None``.
    """
    from sqlalchemy import text
    from datetime import datetime, timedelta

    cutoff = datetime.utcnow() - timedelta(days=lookback_days)

    result = await session.execute(
        text(
            "SELECT results_json "
            "FROM backtest_results "
            "WHERE strategy_id = :sid AND symbol = :symbol "
            "  AND status = 'completed' AND created_at >= :cutoff "
            "ORDER BY created_at DESC "
            "LIMIT 5"
        ),
        {"sid": strategy_id, "symbol": symbol, "cutoff": cutoff},
    )
    rows = result.fetchall()
    if not rows:
        return None

    # Merge equity curves from recent backtests
    all_equity: List[float] = []
    for row in reversed(rows):
        rj = row[0] if row[0] else {}
        curve = rj.get("equity_curve", [])
        for pt in curve:
            val = pt.get("equity") or pt.get("value")
            if val is not None:
                all_equity.append(float(val))

    if len(all_equity) < 31:
        return None

    return detect_decay(all_equity)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _rolling_sharpe(
    returns: List[float],
    window: int,
    bars_per_year: float,
) -> List[float]:
    """Compute rolling annualised Sharpe ratios.

    Args:
        returns:       Bar-over-bar returns.
        window:        Rolling window size.
        bars_per_year: For annualisation.

    Returns:
        List of Sharpe ratios, one per complete window.
    """
    sharpes: List[float] = []
    for i in range(window, len(returns) + 1):
        chunk = returns[i - window : i]
        avg = sum(chunk) / len(chunk)
        variance = sum((r - avg) ** 2 for r in chunk) / (len(chunk) - 1) if len(chunk) > 1 else 0
        std = math.sqrt(variance) if variance > 0 else 0
        if std == 0:
            sharpes.append(0.0)
        else:
            sharpes.append((avg / std) * math.sqrt(bars_per_year))
    return sharpes
