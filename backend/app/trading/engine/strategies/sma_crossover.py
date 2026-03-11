"""
SMA Crossover Strategy — trend-following using simple moving average crossovers.

Generates a long entry when the fast SMA crosses above the slow SMA, and
an exit when it crosses below.  Includes a percentage-based stop loss.

Default params: fast_period=10, slow_period=50, stop_loss_pct=0.05
"""

from __future__ import annotations

from typing import Any, Dict, List

from .. import Signal
from ...providers import OHLCVBar
from . import register


def _sma(closes: List[float], period: int) -> List[float]:
    """Compute simple moving average series.

    Args:
        closes: List of close prices.
        period: SMA lookback period.

    Returns:
        List of same length as closes; first (period-1) values are 0.0.
    """
    result = [0.0] * len(closes)
    for i in range(period - 1, len(closes)):
        result[i] = sum(closes[i - period + 1 : i + 1]) / period
    return result


def generate_signals(bars: List[OHLCVBar], params: Dict[str, Any]) -> List[Signal]:
    """Generate entry/exit signals based on SMA crossover.

    Args:
        bars:   Chronological OHLCV bars.
        params: Strategy parameters (fast_period, slow_period, stop_loss_pct).

    Returns:
        List of Signal objects.
    """
    fast_p = params.get("fast_period", 10)
    slow_p = params.get("slow_period", 50)
    stop_pct = params.get("stop_loss_pct", 0.05)

    if len(bars) < slow_p + 1:
        return []

    closes = [b.close for b in bars]
    fast = _sma(closes, fast_p)
    slow = _sma(closes, slow_p)

    signals: List[Signal] = []
    in_position = False
    entry_price = 0.0

    for i in range(slow_p, len(bars)):
        if fast[i] == 0 or slow[i] == 0 or fast[i - 1] == 0 or slow[i - 1] == 0:
            continue

        # Stop-loss check
        if in_position and bars[i].low <= entry_price * (1 - stop_pct):
            signals.append(Signal(
                timestamp=bars[i].timestamp,
                signal_type="stop_loss",
                direction="long",
                price=round(entry_price * (1 - stop_pct), 4),
            ))
            in_position = False

        # Crossover: fast crosses above slow → entry
        if not in_position and fast[i - 1] <= slow[i - 1] and fast[i] > slow[i]:
            entry_price = bars[i].close
            signals.append(Signal(
                timestamp=bars[i].timestamp,
                signal_type="entry",
                direction="long",
                price=entry_price,
            ))
            in_position = True

        # Crossunder: fast crosses below slow → exit
        elif in_position and fast[i - 1] >= slow[i - 1] and fast[i] < slow[i]:
            signals.append(Signal(
                timestamp=bars[i].timestamp,
                signal_type="exit",
                direction="long",
                price=bars[i].close,
            ))
            in_position = False

    return signals


register(
    slug="sma_crossover",
    name="SMA Crossover",
    description="Trend-following: enter on fast/slow SMA crossover, exit on crossunder.",
    default_params={"fast_period": 10, "slow_period": 50, "stop_loss_pct": 0.05},
    param_schema=[
        {"name": "fast_period", "type": "int", "default": 10, "min": 2, "max": 200, "step": 1, "label": "Fast SMA Period"},
        {"name": "slow_period", "type": "int", "default": 50, "min": 5, "max": 500, "step": 1, "label": "Slow SMA Period"},
        {"name": "stop_loss_pct", "type": "float", "default": 0.05, "min": 0.005, "max": 0.20, "step": 0.005, "label": "Stop Loss %"},
    ],
    generate_signals=generate_signals,
)
