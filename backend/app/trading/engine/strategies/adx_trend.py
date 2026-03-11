"""
ADX Trend Strategy — enter on strong trend confirmation via ADX.

Enter long when ADX crosses above threshold and +DI > -DI (uptrend).
Exit when ADX falls below threshold or -DI crosses above +DI.

Default params: period=14, threshold=25, stop_loss_pct=0.05
"""

from __future__ import annotations

from typing import Any, Dict, List

from .. import Signal
from ...providers import OHLCVBar
from . import register


def _wilder_smooth(values: List[float], period: int) -> List[float]:
    """Wilder's smoothing (used in ADX/DI calculations).

    Args:
        values: Raw series to smooth.
        period: Smoothing period.

    Returns:
        Smoothed series.
    """
    result = [0.0] * len(values)
    if len(values) < period:
        return result
    result[period - 1] = sum(values[:period]) / period
    for i in range(period, len(values)):
        result[i] = (result[i - 1] * (period - 1) + values[i]) / period
    return result


def generate_signals(bars: List[OHLCVBar], params: Dict[str, Any]) -> List[Signal]:
    """Generate entry/exit signals based on ADX trend strength.

    Args:
        bars:   Chronological OHLCV bars.
        params: Strategy parameters.

    Returns:
        List of Signal objects.
    """
    period = params.get("period", 14)
    threshold = params.get("threshold", 25)
    stop_pct = params.get("stop_loss_pct", 0.05)

    if len(bars) < period * 2 + 1:
        return []

    # True Range, +DM, -DM
    tr_list = [0.0] * len(bars)
    plus_dm = [0.0] * len(bars)
    minus_dm = [0.0] * len(bars)

    for i in range(1, len(bars)):
        high_diff = bars[i].high - bars[i - 1].high
        low_diff = bars[i - 1].low - bars[i].low
        tr_list[i] = max(
            bars[i].high - bars[i].low,
            abs(bars[i].high - bars[i - 1].close),
            abs(bars[i].low - bars[i - 1].close),
        )
        plus_dm[i] = high_diff if high_diff > low_diff and high_diff > 0 else 0
        minus_dm[i] = low_diff if low_diff > high_diff and low_diff > 0 else 0

    # Wilder-smooth TR, +DM, -DM
    atr = _wilder_smooth(tr_list, period)
    plus_di_raw = _wilder_smooth(plus_dm, period)
    minus_di_raw = _wilder_smooth(minus_dm, period)

    # +DI and -DI as percentages
    plus_di = [0.0] * len(bars)
    minus_di = [0.0] * len(bars)
    for i in range(len(bars)):
        if atr[i] > 0:
            plus_di[i] = (plus_di_raw[i] / atr[i]) * 100
            minus_di[i] = (minus_di_raw[i] / atr[i]) * 100

    # DX and ADX
    dx = [0.0] * len(bars)
    for i in range(len(bars)):
        di_sum = plus_di[i] + minus_di[i]
        dx[i] = (abs(plus_di[i] - minus_di[i]) / di_sum * 100) if di_sum > 0 else 0

    adx = _wilder_smooth(dx, period)

    signals: List[Signal] = []
    in_position = False
    entry_price = 0.0
    start_idx = period * 2

    for i in range(start_idx, len(bars)):
        if adx[i] == 0:
            continue

        if in_position and bars[i].low <= entry_price * (1 - stop_pct):
            signals.append(Signal(
                timestamp=bars[i].timestamp, signal_type="stop_loss",
                direction="long", price=round(entry_price * (1 - stop_pct), 4),
            ))
            in_position = False

        # ADX above threshold + uptrend (+DI > -DI) → entry
        if (not in_position
                and adx[i] > threshold
                and plus_di[i] > minus_di[i]):
            entry_price = bars[i].close
            signals.append(Signal(
                timestamp=bars[i].timestamp, signal_type="entry",
                direction="long", price=entry_price,
            ))
            in_position = True

        # ADX weakens or trend reverses → exit
        elif (in_position
                and (adx[i] < threshold or minus_di[i] > plus_di[i])):
            signals.append(Signal(
                timestamp=bars[i].timestamp, signal_type="exit",
                direction="long", price=bars[i].close,
            ))
            in_position = False

    return signals


register(
    slug="adx_trend",
    name="ADX Trend",
    description="Trend-following: enter when ADX confirms strong uptrend (+DI > -DI).",
    default_params={"period": 14, "threshold": 25, "stop_loss_pct": 0.05},
    param_schema=[
        {"name": "period", "type": "int", "default": 14, "min": 5, "max": 30, "step": 1, "label": "ADX Period"},
        {"name": "threshold", "type": "int", "default": 25, "min": 15, "max": 40, "step": 1, "label": "ADX Threshold"},
        {"name": "stop_loss_pct", "type": "float", "default": 0.05, "min": 0.005, "max": 0.20, "step": 0.005, "label": "Stop Loss %"},
    ],
    generate_signals=generate_signals,
)
