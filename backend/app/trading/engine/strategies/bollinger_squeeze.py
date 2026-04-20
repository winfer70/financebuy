"""
Bollinger Band Squeeze Strategy — volatility breakout from Bollinger Band contraction.

Enter long when price breaks above the upper band after a squeeze
(band width below average), exit when price falls below the middle band.

Default params: period=20, std_dev=2.0, stop_loss_pct=0.05
"""

from __future__ import annotations

import math
from typing import Any, Dict, List

from .. import Signal
from ...providers import OHLCVBar
from . import register


def generate_signals(bars: List[OHLCVBar], params: Dict[str, Any]) -> List[Signal]:
    """Generate entry/exit signals based on Bollinger Band squeeze breakout.

    Args:
        bars:   Chronological OHLCV bars.
        params: Strategy parameters.

    Returns:
        List of Signal objects.
    """
    period = params.get("period", 20)
    num_std = params.get("std_dev", 2.0)
    stop_pct = params.get("stop_loss_pct", 0.05)

    if len(bars) < period + 1:
        return []

    closes = [b.close for b in bars]

    # Compute Bollinger Bands
    sma = [0.0] * len(closes)
    upper = [0.0] * len(closes)
    lower = [0.0] * len(closes)
    bandwidth = [0.0] * len(closes)

    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1 : i + 1]
        mean = sum(window) / period
        std = math.sqrt(sum((x - mean) ** 2 for x in window) / period)
        sma[i] = mean
        upper[i] = mean + num_std * std
        lower[i] = mean - num_std * std
        bandwidth[i] = (upper[i] - lower[i]) / mean if mean > 0 else 0

    # Average bandwidth for squeeze detection
    bw_values = [bw for bw in bandwidth[period - 1:] if bw > 0]
    avg_bw = sum(bw_values) / len(bw_values) if bw_values else 0

    signals: List[Signal] = []
    in_position = False
    entry_price = 0.0

    for i in range(period, len(bars)):
        if sma[i] == 0:
            continue

        if in_position and bars[i].low <= entry_price * (1 - stop_pct):
            signals.append(Signal(
                timestamp=bars[i].timestamp, signal_type="stop_loss",
                direction="long", price=round(entry_price * (1 - stop_pct), 4),
            ))
            in_position = False

        # Squeeze: bandwidth below average, then price breaks above upper band
        is_squeeze = bandwidth[i - 1] < avg_bw
        if not in_position and is_squeeze and closes[i] > upper[i]:
            entry_price = bars[i].close
            signals.append(Signal(
                timestamp=bars[i].timestamp, signal_type="entry",
                direction="long", price=entry_price,
            ))
            in_position = True
        elif in_position and closes[i] < sma[i]:
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
    period = params.get("period", 20)
    num_std = params.get("std_dev", 2.0)
    n = len(closes)
    bb_sma = [0.0] * n
    bb_upper = [0.0] * n
    bb_lower = [0.0] * n
    bb_bandwidth = [0.0] * n
    for i in range(period - 1, n):
        window = closes[i - period + 1 : i + 1]
        mean = sum(window) / period
        std = math.sqrt(sum((x - mean) ** 2 for x in window) / period)
        bb_sma[i] = mean
        bb_upper[i] = mean + num_std * std
        bb_lower[i] = mean - num_std * std
        bb_bandwidth[i] = (bb_upper[i] - bb_lower[i]) / mean if mean > 0 else 0
    return {
        "bb_sma": bb_sma,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "bb_bandwidth": bb_bandwidth,
    }


register(
    slug="bollinger_squeeze",
    name="Bollinger Band Squeeze",
    description="Volatility breakout: enter on squeeze breakout above upper band.",
    default_params={"period": 20, "std_dev": 2.0, "stop_loss_pct": 0.05},
    param_schema=[
        {"name": "period", "type": "int", "default": 20, "min": 5, "max": 50, "step": 1, "label": "BB Period"},
        {"name": "std_dev", "type": "float", "default": 2.0, "min": 1.0, "max": 3.0, "step": 0.1, "label": "Std Dev Multiplier"},
        {"name": "stop_loss_pct", "type": "float", "default": 0.05, "min": 0.005, "max": 0.20, "step": 0.005, "label": "Stop Loss %"},
    ],
    generate_signals=generate_signals,
)
