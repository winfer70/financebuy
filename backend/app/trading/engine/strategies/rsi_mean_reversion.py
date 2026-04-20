"""
RSI Mean Reversion Strategy — fade overbought/oversold RSI readings.

Enter long when RSI dips below oversold level, exit when it rises above
overbought level.  Stop loss on percentage drop from entry.

Default params: period=14, oversold=30, overbought=70, stop_loss_pct=0.05
"""

from __future__ import annotations

from typing import Any, Dict, List

from .. import Signal
from ...providers import OHLCVBar
from . import register


def _rsi(closes: List[float], period: int) -> List[float]:
    """Compute RSI series using Wilder's smoothing.

    Args:
        closes: List of close prices.
        period: RSI lookback period.

    Returns:
        RSI series (0.0 for insufficient lookback).
    """
    result = [0.0] * len(closes)
    if len(closes) < period + 1:
        return result

    gains = []
    losses = []
    for i in range(1, period + 1):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100 - (100 / (1 + rs))

    for i in range(period + 1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gain = max(delta, 0)
        loss = max(-delta, 0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        if avg_loss == 0:
            result[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i] = 100 - (100 / (1 + rs))

    return result


def generate_signals(bars: List[OHLCVBar], params: Dict[str, Any]) -> List[Signal]:
    """Generate entry/exit signals based on RSI mean reversion.

    Args:
        bars:   Chronological OHLCV bars.
        params: Strategy parameters.

    Returns:
        List of Signal objects.
    """
    period = params.get("period", 14)
    oversold = params.get("oversold", 30)
    overbought = params.get("overbought", 70)
    stop_pct = params.get("stop_loss_pct", 0.05)

    if len(bars) < period + 2:
        return []

    closes = [b.close for b in bars]
    rsi = _rsi(closes, period)

    signals: List[Signal] = []
    in_position = False
    entry_price = 0.0

    for i in range(period + 1, len(bars)):
        if rsi[i] == 0:
            continue

        if in_position and bars[i].low <= entry_price * (1 - stop_pct):
            signals.append(Signal(
                timestamp=bars[i].timestamp, signal_type="stop_loss",
                direction="long", price=round(entry_price * (1 - stop_pct), 4),
            ))
            in_position = False

        if not in_position and rsi[i - 1] >= oversold and rsi[i] < oversold:
            entry_price = bars[i].close
            signals.append(Signal(
                timestamp=bars[i].timestamp, signal_type="entry",
                direction="long", price=entry_price,
            ))
            in_position = True
        elif in_position and rsi[i] > overbought:
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
    period = params.get("period", 14)
    return {
        "rsi": _rsi(closes, period),
    }


register(
    slug="rsi_mean_reversion",
    name="RSI Mean Reversion",
    description="Mean reversion: enter on RSI oversold, exit on RSI overbought.",
    default_params={"period": 14, "oversold": 30, "overbought": 70, "stop_loss_pct": 0.05},
    param_schema=[
        {"name": "period", "type": "int", "default": 14, "min": 2, "max": 50, "step": 1, "label": "RSI Period"},
        {"name": "oversold", "type": "int", "default": 30, "min": 10, "max": 45, "step": 1, "label": "Oversold Level"},
        {"name": "overbought", "type": "int", "default": 70, "min": 55, "max": 90, "step": 1, "label": "Overbought Level"},
        {"name": "stop_loss_pct", "type": "float", "default": 0.05, "min": 0.005, "max": 0.20, "step": 0.005, "label": "Stop Loss %"},
    ],
    generate_signals=generate_signals,
)
