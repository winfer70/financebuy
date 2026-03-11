"""
Stochastic Oscillator Strategy — mean reversion using %K/%D crossovers.

Enter long when %K crosses above %D in the oversold zone, exit when
%K crosses below %D in the overbought zone.

Default params: k_period=14, d_period=3, oversold=20, overbought=80
"""

from __future__ import annotations

from typing import Any, Dict, List

from .. import Signal
from ...providers import OHLCVBar
from . import register


def generate_signals(bars: List[OHLCVBar], params: Dict[str, Any]) -> List[Signal]:
    """Generate entry/exit signals based on Stochastic Oscillator.

    Args:
        bars:   Chronological OHLCV bars.
        params: Strategy parameters.

    Returns:
        List of Signal objects.
    """
    k_period = params.get("k_period", 14)
    d_period = params.get("d_period", 3)
    oversold = params.get("oversold", 20)
    overbought = params.get("overbought", 80)
    stop_pct = params.get("stop_loss_pct", 0.05)
    min_bars = k_period + d_period

    if len(bars) < min_bars + 1:
        return []

    # Compute %K
    pct_k = [0.0] * len(bars)
    for i in range(k_period - 1, len(bars)):
        window = bars[i - k_period + 1 : i + 1]
        highest = max(b.high for b in window)
        lowest = min(b.low for b in window)
        rng = highest - lowest
        pct_k[i] = ((bars[i].close - lowest) / rng * 100) if rng > 0 else 50.0

    # Compute %D = SMA of %K
    pct_d = [0.0] * len(bars)
    for i in range(k_period + d_period - 2, len(bars)):
        pct_d[i] = sum(pct_k[i - d_period + 1 : i + 1]) / d_period

    signals: List[Signal] = []
    in_position = False
    entry_price = 0.0
    start_idx = k_period + d_period - 1

    for i in range(start_idx, len(bars)):
        if pct_d[i] == 0 or pct_d[i - 1] == 0:
            continue

        if in_position and bars[i].low <= entry_price * (1 - stop_pct):
            signals.append(Signal(
                timestamp=bars[i].timestamp, signal_type="stop_loss",
                direction="long", price=round(entry_price * (1 - stop_pct), 4),
            ))
            in_position = False

        # %K crosses above %D in oversold zone → long entry
        if (not in_position
                and pct_k[i - 1] <= pct_d[i - 1]
                and pct_k[i] > pct_d[i]
                and pct_k[i] < oversold):
            entry_price = bars[i].close
            signals.append(Signal(
                timestamp=bars[i].timestamp, signal_type="entry",
                direction="long", price=entry_price,
            ))
            in_position = True

        # %K crosses below %D in overbought zone → exit
        elif (in_position
                and pct_k[i - 1] >= pct_d[i - 1]
                and pct_k[i] < pct_d[i]
                and pct_k[i] > overbought):
            signals.append(Signal(
                timestamp=bars[i].timestamp, signal_type="exit",
                direction="long", price=bars[i].close,
            ))
            in_position = False

    return signals


register(
    slug="stochastic",
    name="Stochastic Oscillator",
    description="Mean reversion: enter on oversold %K/%D crossover, exit on overbought.",
    default_params={"k_period": 14, "d_period": 3, "oversold": 20, "overbought": 80, "stop_loss_pct": 0.05},
    param_schema=[
        {"name": "k_period", "type": "int", "default": 14, "min": 5, "max": 30, "step": 1, "label": "%K Period"},
        {"name": "d_period", "type": "int", "default": 3, "min": 2, "max": 10, "step": 1, "label": "%D Period"},
        {"name": "oversold", "type": "int", "default": 20, "min": 5, "max": 40, "step": 1, "label": "Oversold"},
        {"name": "overbought", "type": "int", "default": 80, "min": 60, "max": 95, "step": 1, "label": "Overbought"},
        {"name": "stop_loss_pct", "type": "float", "default": 0.05, "min": 0.005, "max": 0.20, "step": 0.005, "label": "Stop Loss %"},
    ],
    generate_signals=generate_signals,
)
