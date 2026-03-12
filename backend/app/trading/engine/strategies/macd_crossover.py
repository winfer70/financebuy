"""
MACD Crossover Strategy — trend-following using MACD line/signal crossovers.

Enter long when MACD line crosses above signal line, exit on crossunder.

Default params: fast=12, slow=26, signal=9, stop_loss_pct=0.05
"""

from __future__ import annotations

from typing import Any, Dict, List

from .. import Signal
from ...providers import OHLCVBar
from . import register


def _ema(closes: List[float], period: int) -> List[float]:
    """Compute EMA series (SMA-seeded)."""
    result = [0.0] * len(closes)
    if len(closes) < period:
        return result
    result[period - 1] = sum(closes[:period]) / period
    k = 2 / (period + 1)
    for i in range(period, len(closes)):
        result[i] = closes[i] * k + result[i - 1] * (1 - k)
    return result


def generate_signals(bars: List[OHLCVBar], params: Dict[str, Any]) -> List[Signal]:
    """Generate entry/exit signals based on MACD crossover.

    Args:
        bars:   Chronological OHLCV bars.
        params: Strategy parameters (fast, slow, signal, stop_loss_pct).

    Returns:
        List of Signal objects.
    """
    fast_p = params.get("fast", 12)
    slow_p = params.get("slow", 26)
    sig_p = params.get("signal", 9)
    stop_pct = params.get("stop_loss_pct", 0.05)
    min_bars = slow_p + sig_p + 1

    if len(bars) < min_bars:
        return []

    closes = [b.close for b in bars]
    fast_ema = _ema(closes, fast_p)
    slow_ema = _ema(closes, slow_p)

    # MACD line = fast EMA - slow EMA
    macd_line = [0.0] * len(closes)
    for i in range(slow_p - 1, len(closes)):
        if fast_ema[i] and slow_ema[i]:
            macd_line[i] = fast_ema[i] - slow_ema[i]

    # Signal line = EMA of MACD line
    macd_values = macd_line[slow_p - 1:]
    sig_ema = _ema(macd_values, sig_p)
    signal_line = [0.0] * len(closes)
    offset = slow_p - 1
    for i in range(len(sig_ema)):
        signal_line[offset + i] = sig_ema[i]

    signals: List[Signal] = []
    in_position = False
    entry_price = 0.0
    start_idx = slow_p + sig_p - 1

    for i in range(start_idx, len(bars)):
        if signal_line[i] == 0 or signal_line[i - 1] == 0:
            continue

        if in_position and bars[i].low <= entry_price * (1 - stop_pct):
            signals.append(Signal(
                timestamp=bars[i].timestamp, signal_type="stop_loss",
                direction="long", price=round(entry_price * (1 - stop_pct), 4),
            ))
            in_position = False

        prev_diff = macd_line[i - 1] - signal_line[i - 1]
        curr_diff = macd_line[i] - signal_line[i]

        if not in_position and prev_diff <= 0 and curr_diff > 0:
            entry_price = bars[i].close
            signals.append(Signal(
                timestamp=bars[i].timestamp, signal_type="entry",
                direction="long", price=entry_price,
            ))
            in_position = True
        elif in_position and prev_diff >= 0 and curr_diff < 0:
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
    fast_p = params.get("fast", 12)
    slow_p = params.get("slow", 26)
    sig_p = params.get("signal", 9)
    fast_ema = _ema(closes, fast_p)
    slow_ema = _ema(closes, slow_p)
    macd_line = [0.0] * len(closes)
    for i in range(slow_p - 1, len(closes)):
        if fast_ema[i] and slow_ema[i]:
            macd_line[i] = fast_ema[i] - slow_ema[i]
    macd_values = macd_line[slow_p - 1:]
    sig_ema = _ema(macd_values, sig_p)
    signal_line = [0.0] * len(closes)
    offset = slow_p - 1
    for i in range(len(sig_ema)):
        signal_line[offset + i] = sig_ema[i]
    histogram = [macd_line[i] - signal_line[i] for i in range(len(closes))]
    return {
        "macd_line": macd_line,
        "signal_line": signal_line,
        "histogram": histogram,
    }


register(
    slug="macd_crossover",
    name="MACD Crossover",
    description="Trend-following: enter on MACD/signal crossover, exit on crossunder.",
    default_params={"fast": 12, "slow": 26, "signal": 9, "stop_loss_pct": 0.05},
    param_schema=[
        {"name": "fast", "type": "int", "default": 12, "min": 2, "max": 50, "step": 1, "label": "Fast EMA"},
        {"name": "slow", "type": "int", "default": 26, "min": 10, "max": 100, "step": 1, "label": "Slow EMA"},
        {"name": "signal", "type": "int", "default": 9, "min": 2, "max": 30, "step": 1, "label": "Signal EMA"},
        {"name": "stop_loss_pct", "type": "float", "default": 0.05, "min": 0.005, "max": 0.20, "step": 0.005, "label": "Stop Loss %"},
    ],
    generate_signals=generate_signals,
)
