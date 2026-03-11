"""
Performance Metrics Calculator — computes risk/return statistics for backtests.

All functions accept either a list of ``TradeRecord`` objects or an equity
curve and return scalar metrics.  The ``compute_all`` function bundles
everything into a single dict matching the ``MetricsOut`` schema.

Metrics computed:
    total_return, annualized_return (CAGR), sharpe_ratio, sortino_ratio,
    calmar_ratio, max_drawdown, max_drawdown_duration, win_rate,
    profit_factor, expectancy, total_trades, avg_win, avg_loss,
    benchmark_comparison, overfit_score.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from . import TradeRecord


# ---------------------------------------------------------------------------
# Individual metric functions
# ---------------------------------------------------------------------------

def total_return(initial_equity: float, final_equity: float) -> float:
    """Total return as a percentage.

    Args:
        initial_equity: Starting portfolio value.
        final_equity:   Ending portfolio value.

    Returns:
        Percentage return (e.g. 25.0 for +25%).
    """
    if initial_equity <= 0:
        return 0.0
    return round(((final_equity - initial_equity) / initial_equity) * 100, 4)


def annualized_return(
    initial_equity: float,
    final_equity: float,
    num_bars: int,
    bars_per_year: float = 252,
) -> float:
    """Compound Annual Growth Rate (CAGR).

    Args:
        initial_equity: Starting value.
        final_equity:   Ending value.
        num_bars:       Total bars in the backtest.
        bars_per_year:  Bars in one year (252 for daily, ~1512 for 1h, etc.).

    Returns:
        Annualized return percentage.
    """
    if initial_equity <= 0 or final_equity <= 0 or num_bars <= 0:
        return 0.0
    years = num_bars / bars_per_year
    if years <= 0:
        return 0.0
    cagr = (final_equity / initial_equity) ** (1 / years) - 1
    return round(cagr * 100, 4)


def sharpe_ratio(
    equity_curve: List[float],
    risk_free_rate: float = 0.0,
    bars_per_year: float = 252,
) -> float:
    """Annualised Sharpe ratio from an equity curve.

    Args:
        equity_curve:    List of equity values (one per bar).
        risk_free_rate:  Annual risk-free rate (default 0).
        bars_per_year:   Bars per year for annualisation.

    Returns:
        Sharpe ratio (0.0 if insufficient data or zero std dev).
    """
    returns = _pct_returns(equity_curve)
    if len(returns) < 2:
        return 0.0
    avg = sum(returns) / len(returns)
    std = _std(returns)
    if std == 0:
        return 0.0
    daily_rf = risk_free_rate / bars_per_year
    return round(((avg - daily_rf) / std) * math.sqrt(bars_per_year), 4)


def sortino_ratio(
    equity_curve: List[float],
    risk_free_rate: float = 0.0,
    bars_per_year: float = 252,
) -> float:
    """Annualised Sortino ratio (downside deviation only).

    Args:
        equity_curve:    List of equity values.
        risk_free_rate:  Annual risk-free rate.
        bars_per_year:   Bars per year.

    Returns:
        Sortino ratio.
    """
    returns = _pct_returns(equity_curve)
    if len(returns) < 2:
        return 0.0
    avg = sum(returns) / len(returns)
    downside = [r for r in returns if r < 0]
    if not downside:
        return 0.0 if avg <= 0 else 99.99
    down_std = _std(downside)
    if down_std == 0:
        return 0.0
    daily_rf = risk_free_rate / bars_per_year
    return round(((avg - daily_rf) / down_std) * math.sqrt(bars_per_year), 4)


def max_drawdown(equity_curve: List[float]) -> float:
    """Maximum drawdown as a negative percentage.

    Args:
        equity_curve: List of equity values.

    Returns:
        Max drawdown (e.g. -15.5 for a 15.5% peak-to-trough drop).
    """
    if len(equity_curve) < 2:
        return 0.0
    peak = equity_curve[0]
    worst = 0.0
    for val in equity_curve:
        if val > peak:
            peak = val
        dd = ((val - peak) / peak) * 100 if peak > 0 else 0.0
        if dd < worst:
            worst = dd
    return round(worst, 4)


def max_drawdown_duration(equity_curve: List[float]) -> int:
    """Longest drawdown duration in bars (peak-to-new-peak).

    Args:
        equity_curve: List of equity values.

    Returns:
        Number of bars in the longest drawdown period.
    """
    if len(equity_curve) < 2:
        return 0
    peak = equity_curve[0]
    dd_start = 0
    longest = 0
    for i, val in enumerate(equity_curve):
        if val >= peak:
            peak = val
            duration = i - dd_start
            if duration > longest:
                longest = duration
            dd_start = i
    # Check if still in drawdown at end
    final_duration = len(equity_curve) - 1 - dd_start
    if final_duration > longest:
        longest = final_duration
    return longest


def win_rate(trades: List[TradeRecord]) -> float:
    """Percentage of profitable trades.

    Args:
        trades: List of completed trades.

    Returns:
        Win rate as a percentage (e.g. 62.5).
    """
    if not trades:
        return 0.0
    wins = sum(1 for t in trades if t.pnl > 0)
    return round((wins / len(trades)) * 100, 2)


def profit_factor(trades: List[TradeRecord]) -> float:
    """Gross profit divided by gross loss.

    Args:
        trades: List of completed trades.

    Returns:
        Profit factor (> 1.0 is profitable). 0.0 if no losses.
    """
    gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
    gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))
    if gross_loss == 0:
        return 99.99 if gross_profit > 0 else 0.0
    return round(gross_profit / gross_loss, 4)


def expectancy(trades: List[TradeRecord]) -> float:
    """Expected return per trade.

    Args:
        trades: List of completed trades.

    Returns:
        Average P&L per trade.
    """
    if not trades:
        return 0.0
    return round(sum(t.pnl for t in trades) / len(trades), 4)


def avg_win(trades: List[TradeRecord]) -> float:
    """Average return of winning trades (percentage).

    Args:
        trades: List of completed trades.

    Returns:
        Average win P&L percentage.
    """
    wins = [t.pnl_pct for t in trades if t.pnl > 0]
    return round(sum(wins) / len(wins), 4) if wins else 0.0


def avg_loss(trades: List[TradeRecord]) -> float:
    """Average return of losing trades (percentage, negative).

    Args:
        trades: List of completed trades.

    Returns:
        Average loss P&L percentage.
    """
    losses = [t.pnl_pct for t in trades if t.pnl < 0]
    return round(sum(losses) / len(losses), 4) if losses else 0.0


def calmar_ratio(
    initial_equity: float,
    final_equity: float,
    equity_curve: List[float],
    num_bars: int,
    bars_per_year: float = 252,
) -> float:
    """Calmar ratio = annualized return / |max drawdown|.

    Args:
        initial_equity: Starting value.
        final_equity:   Ending value.
        equity_curve:   Equity values per bar.
        num_bars:       Total bars.
        bars_per_year:  Bars per year.

    Returns:
        Calmar ratio.
    """
    ann = annualized_return(initial_equity, final_equity, num_bars, bars_per_year)
    mdd = abs(max_drawdown(equity_curve))
    if mdd == 0:
        return 0.0
    return round(ann / mdd, 4)


def benchmark_comparison(
    strategy_equity: List[float],
    buy_hold_equity: List[float],
    spy_equity: Optional[List[float]] = None,
) -> Dict[str, float]:
    """Compare strategy equity curve against benchmarks.

    Args:
        strategy_equity:  Strategy equity values per bar.
        buy_hold_equity:  Buy-and-hold equity values per bar.
        spy_equity:       Optional SPY buy-and-hold equity per bar.

    Returns:
        Dict with return percentages for each series.
    """
    def _return(curve: List[float]) -> float:
        if len(curve) < 2 or curve[0] <= 0:
            return 0.0
        return round(((curve[-1] - curve[0]) / curve[0]) * 100, 2)

    result = {
        "strategy_return": _return(strategy_equity),
        "buy_hold_return": _return(buy_hold_equity),
    }
    if spy_equity:
        result["spy_return"] = _return(spy_equity)
    return result


def overfit_score(num_params: int, num_trades: int) -> bool:
    """Heuristic overfit warning based on parameter count vs trade count.

    Rule of thumb: if trades-per-parameter < 15, flag as potentially overfit.

    Args:
        num_params:  Number of tunable strategy parameters.
        num_trades:  Number of trades in the backtest.

    Returns:
        ``True`` if overfitting is likely.
    """
    if num_params <= 0:
        return False
    trades_per_param = num_trades / num_params
    return trades_per_param < 15


# ---------------------------------------------------------------------------
# Aggregate function
# ---------------------------------------------------------------------------

def compute_all(
    trades: List[TradeRecord],
    equity_curve: List[float],
    initial_equity: float,
    final_equity: float,
    num_bars: int,
    bars_per_year: float = 252,
    num_params: int = 0,
) -> Dict[str, Any]:
    """Compute all performance metrics in a single call.

    Args:
        trades:          List of completed trades.
        equity_curve:    Equity values per bar.
        initial_equity:  Starting value.
        final_equity:    Ending value.
        num_bars:        Total bars in the backtest.
        bars_per_year:   Bars per year.
        num_params:      Number of tunable strategy parameters.

    Returns:
        Dict matching the ``MetricsOut`` schema fields.
    """
    return {
        "total_return": total_return(initial_equity, final_equity),
        "annualized_return": annualized_return(
            initial_equity, final_equity, num_bars, bars_per_year,
        ),
        "sharpe_ratio": sharpe_ratio(equity_curve, bars_per_year=bars_per_year),
        "sortino_ratio": sortino_ratio(equity_curve, bars_per_year=bars_per_year),
        "max_drawdown": max_drawdown(equity_curve),
        "max_drawdown_duration": max_drawdown_duration(equity_curve),
        "win_rate": win_rate(trades),
        "profit_factor": profit_factor(trades),
        "total_trades": len(trades),
        "avg_win": avg_win(trades),
        "avg_loss": avg_loss(trades),
        "expectancy": expectancy(trades),
        "calmar_ratio": calmar_ratio(
            initial_equity, final_equity, equity_curve, num_bars, bars_per_year,
        ),
        "overfit_warning": overfit_score(num_params, len(trades)),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _pct_returns(equity_curve: List[float]) -> List[float]:
    """Convert an equity curve to bar-over-bar percentage returns.

    Args:
        equity_curve: List of equity values.

    Returns:
        List of percentage returns (length = len(equity_curve) - 1).
    """
    returns = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1]
        if prev != 0:
            returns.append((equity_curve[i] - prev) / prev)
        else:
            returns.append(0.0)
    return returns


def _std(values: List[float]) -> float:
    """Sample standard deviation.

    Args:
        values: List of numeric values.

    Returns:
        Standard deviation (0.0 if fewer than 2 values).
    """
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    return math.sqrt(variance)
