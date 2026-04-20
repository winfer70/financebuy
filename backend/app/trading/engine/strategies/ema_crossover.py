"""
EMA Crossover Strategy — trend-following using exponential moving averages.

Faster response than SMA crossover due to EMA weighting recent prices.
Long entry on fast EMA crossing above slow EMA, exit on crossunder.

Default params: fast_period=9, slow_period=21, stop_loss_pct=0.05
"""

from __future__ import annotations

from typing import Any, Dict, List

from .. import Signal
from ...providers import OHLCVBar
from . import register


def _ema(closes: List[float], period: int) -> List[float]:
    """Compute exponential moving average series.

    Args:
        closes: List of close prices.
        period: EMA lookback period.

    Returns:
        EMA series (first value = SMA seed, then EMA thereafter).
    """
    result = [0.0] * len(closes)
    if len(closes) < period:
        return result
    # Seed with SMA
    result[period - 1] = sum(closes[:period]) / period
    k = 2 / (period + 1)
    for i in range(period, len(closes)):
        result[i] = closes[i] * k + result[i - 1] * (1 - k)
    return result


def generate_signals(bars: List[OHLCVBar], params: Dict[str, Any]) -> List[Signal]:
    """Generate entry/exit signals based on EMA crossover.

    Args:
        bars:   Chronological OHLCV bars.
        params: Strategy parameters.

    Returns:
        List of Signal objects.
    """
    fast_p = params.get("fast_period", 9)
    slow_p = params.get("slow_period", 21)
    stop_pct = params.get("stop_loss_pct", 0.05)

    if len(bars) < slow_p + 1:
        return []

    closes = [b.close for b in bars]
    fast = _ema(closes, fast_p)
    slow = _ema(closes, slow_p)

    signals: List[Signal] = []
    in_position = False
    entry_price = 0.0

    for i in range(slow_p, len(bars)):
        if fast[i] == 0 or slow[i] == 0 or fast[i - 1] == 0 or slow[i - 1] == 0:
            continue

        if in_position and bars[i].low <= entry_price * (1 - stop_pct):
            signals.append(Signal(
                timestamp=bars[i].timestamp, signal_type="stop_loss",
                direction="long", price=round(entry_price * (1 - stop_pct), 4),
            ))
            in_position = False

        if not in_position and fast[i - 1] <= slow[i - 1] and fast[i] > slow[i]:
            entry_price = bars[i].close
            signals.append(Signal(
                timestamp=bars[i].timestamp, signal_type="entry",
                direction="long", price=entry_price,
            ))
            in_position = True
        elif in_position and fast[i - 1] >= slow[i - 1] and fast[i] < slow[i]:
            signals.append(Signal(
                timestamp=bars[i].timestamp, signal_type="exit",
                direction="long", price=bars[i].close,
            ))
            in_position = False

    return signals


def indicator_outputs(bars: List[OHLCVBar], params: Dict[str, Any]) -> Dict[str, List[float]]:
    """Expose indicator series for the composition engine.

    Args:
        bars:   Chronological OHLCV bars.
        params: Strategy parameters.

    Returns:
        Dict mapping indicator names to float series.
    """
    closes = [b.close for b in bars]
    fast_p = params.get("fast_period", 9)
    slow_p = params.get("slow_period", 21)
    return {
        "fast_ema": _ema(closes, fast_p),
        "slow_ema": _ema(closes, slow_p),
    }


register(
    slug="ema_crossover",
    name="EMA Crossover",
    description="Trend-following: enter on fast/slow EMA crossover, exit on crossunder.",
    default_params={"fast_period": 9, "slow_period": 21, "stop_loss_pct": 0.05},
    param_schema=[
        {"name": "fast_period", "type": "int", "default": 9, "min": 2, "max": 100, "step": 1, "label": "Fast EMA Period"},
        {"name": "slow_period", "type": "int", "default": 21, "min": 5, "max": 200, "step": 1, "label": "Slow EMA Period"},
        {"name": "stop_loss_pct", "type": "float", "default": 0.05, "min": 0.005, "max": 0.20, "step": 0.005, "label": "Stop Loss %"},
    ],
    generate_signals=generate_signals,
)
