"""
engine/walk_forward.py — Rolling walk-forward validation.

Provides honest out-of-sample evaluation of trading strategies by:
  1. Splitting data into overlapping train/test windows.
  2. For each window: run backtest on train set, evaluate on test set.
  3. Aggregating out-of-sample results for unbiased performance metrics.

This guards against overfitting — a strategy that only works on the
training data will show poor walk-forward results.

Defaults: train_window=252 bars (1 year), test_window=63 bars (3 months),
step=63 bars.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable

from . import BacktestEngine, BacktestOutput, Signal
from .metrics import compute_all

logger = logging.getLogger("trading.walk_forward")


@dataclass
class WalkForwardWindow:
    """A single train/test window result.

    Attributes:
        window_index:   Sequential index of this window.
        train_start:    Index of first bar in the training set.
        train_end:      Index of last bar in the training set.
        test_start:     Index of first bar in the test set.
        test_end:       Index of last bar in the test set.
        train_metrics:  Performance metrics from training (in-sample).
        test_metrics:   Performance metrics from testing (out-of-sample).
        test_output:    Full backtest output from the test set.
    """
    window_index: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    train_metrics: Dict = field(default_factory=dict)
    test_metrics: Dict = field(default_factory=dict)
    test_output: Optional[BacktestOutput] = None


@dataclass
class WalkForwardResult:
    """Aggregated walk-forward validation results.

    Attributes:
        windows:                List of individual window results.
        aggregate_metrics:      Averaged out-of-sample metrics across all windows.
        naive_backtest_metrics: Metrics from a single full-period backtest (for comparison).
        degradation_pct:        Percentage drop from naive to walk-forward (overfitting indicator).
        is_robust:              True if walk-forward return > 50% of naive return.
    """
    windows: List[WalkForwardWindow] = field(default_factory=list)
    aggregate_metrics: Dict = field(default_factory=dict)
    naive_backtest_metrics: Dict = field(default_factory=dict)
    degradation_pct: float = 0.0
    is_robust: bool = False


def walk_forward_validate(
    strategy_fn: Callable,
    bars: list,
    params: dict,
    train_window: int = 252,
    test_window: int = 63,
    step: int = 63,
    initial_capital: float = 10000.0,
    commission_pct: float = 0.001,
    slippage_pct: float = 0.0005,
) -> WalkForwardResult:
    """Run rolling walk-forward analysis on a strategy.

    Splits the data into overlapping train/test windows, backtests each,
    and aggregates out-of-sample performance.

    Args:
        strategy_fn:     Callable that takes (bars, params) and returns List[Signal].
        bars:            Full list of OHLCVBar-like objects (must have open/high/low/close/volume).
        params:          Strategy parameters dict.
        train_window:    Number of bars in the training set (default: 252 = ~1 year daily).
        test_window:     Number of bars in the test set (default: 63 = ~3 months daily).
        step:            Number of bars to advance per window (default: 63).
        initial_capital: Starting capital for each window's backtest.
        commission_pct:  Commission percentage per trade.
        slippage_pct:    Slippage percentage per trade.

    Returns:
        WalkForwardResult with per-window and aggregate metrics.
    """
    n = len(bars)
    min_required = train_window + test_window
    if n < min_required:
        logger.warning(
            "Not enough data for walk-forward: %d bars, need %d", n, min_required
        )
        return WalkForwardResult()

    windows = []
    all_test_trades = []
    all_test_returns = []

    # Slide the train/test window across the data
    window_idx = 0
    start = 0
    while start + min_required <= n:
        train_start = start
        train_end = start + train_window
        test_start = train_end
        test_end = min(test_start + test_window, n)

        train_bars = bars[train_start:train_end]
        test_bars = bars[test_start:test_end]

        # Generate signals on training data (in-sample)
        try:
            train_signals = strategy_fn(train_bars, params)
        except Exception as e:
            logger.warning("Walk-forward: strategy failed on train window %d: %s", window_idx, e)
            start += step
            continue

        # Run backtest on training set
        engine = BacktestEngine(
            initial_capital=initial_capital,
            commission_pct=commission_pct,
            slippage_pct=slippage_pct,
        )
        train_output = engine.run(train_bars, train_signals)
        train_metrics = compute_all(train_output.trades, initial_capital)

        # Generate signals on test data (out-of-sample)
        try:
            test_signals = strategy_fn(test_bars, params)
        except Exception as e:
            logger.warning("Walk-forward: strategy failed on test window %d: %s", window_idx, e)
            start += step
            continue

        # Run backtest on test set
        engine = BacktestEngine(
            initial_capital=initial_capital,
            commission_pct=commission_pct,
            slippage_pct=slippage_pct,
        )
        test_output = engine.run(test_bars, test_signals)
        test_metrics = compute_all(test_output.trades, initial_capital)

        wf_window = WalkForwardWindow(
            window_index=window_idx,
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
            train_metrics=train_metrics,
            test_metrics=test_metrics,
            test_output=test_output,
        )
        windows.append(wf_window)
        all_test_trades.extend(test_output.trades)

        if test_metrics.get("total_return_pct") is not None:
            all_test_returns.append(test_metrics["total_return_pct"])

        window_idx += 1
        start += step

    if not windows:
        return WalkForwardResult()

    # Aggregate out-of-sample metrics
    aggregate = compute_all(all_test_trades, initial_capital)

    # Naive full-period backtest for comparison
    try:
        naive_signals = strategy_fn(bars, params)
        engine = BacktestEngine(
            initial_capital=initial_capital,
            commission_pct=commission_pct,
            slippage_pct=slippage_pct,
        )
        naive_output = engine.run(bars, naive_signals)
        naive_metrics = compute_all(naive_output.trades, initial_capital)
    except Exception:
        naive_metrics = {}

    # Calculate degradation (how much worse is walk-forward vs naive)
    naive_return = naive_metrics.get("total_return_pct", 0) or 0
    wf_return = aggregate.get("total_return_pct", 0) or 0
    degradation = 0.0
    if naive_return != 0:
        degradation = ((naive_return - wf_return) / abs(naive_return)) * 100

    is_robust = wf_return > (naive_return * 0.5) if naive_return > 0 else wf_return > 0

    return WalkForwardResult(
        windows=windows,
        aggregate_metrics=aggregate,
        naive_backtest_metrics=naive_metrics,
        degradation_pct=round(degradation, 2),
        is_robust=is_robust,
    )
