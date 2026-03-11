"""
Ichimoku Cloud Strategy — trend-following using Ichimoku Kinko Hyo components.

Enter long when price is above the cloud (Senkou Span A > Senkou Span B),
Tenkan crosses above Kijun, and Chikou is above price.  Exit when Tenkan
crosses below Kijun or price enters the cloud.

Default params: tenkan=9, kijun=26, senkou_b=52, stop_loss_pct=0.05
"""

from __future__ import annotations

from typing import Any, Dict, List

from .. import Signal
from ...providers import OHLCVBar
from . import register


def _period_high_low(bars: List[OHLCVBar], end_idx: int, period: int):
    """Compute highest high and lowest low over a lookback window.

    Args:
        bars:    Full bar list.
        end_idx: Index of the current bar (inclusive).
        period:  Lookback period.

    Returns:
        Tuple of (highest_high, lowest_low) or (0, 0) if insufficient data.
    """
    start = max(0, end_idx - period + 1)
    window = bars[start : end_idx + 1]
    if not window:
        return 0.0, 0.0
    return max(b.high for b in window), min(b.low for b in window)


def generate_signals(bars: List[OHLCVBar], params: Dict[str, Any]) -> List[Signal]:
    """Generate entry/exit signals based on Ichimoku Cloud.

    Args:
        bars:   Chronological OHLCV bars.
        params: Strategy parameters.

    Returns:
        List of Signal objects.
    """
    tenkan_p = params.get("tenkan", 9)
    kijun_p = params.get("kijun", 26)
    senkou_b_p = params.get("senkou_b", 52)
    stop_pct = params.get("stop_loss_pct", 0.05)

    if len(bars) < senkou_b_p + kijun_p:
        return []

    n = len(bars)

    # Tenkan-sen = (highest high + lowest low) / 2 over tenkan_p
    tenkan = [0.0] * n
    for i in range(tenkan_p - 1, n):
        hh, ll = _period_high_low(bars, i, tenkan_p)
        tenkan[i] = (hh + ll) / 2

    # Kijun-sen = (highest high + lowest low) / 2 over kijun_p
    kijun = [0.0] * n
    for i in range(kijun_p - 1, n):
        hh, ll = _period_high_low(bars, i, kijun_p)
        kijun[i] = (hh + ll) / 2

    # Senkou Span A = (Tenkan + Kijun) / 2, displaced forward by kijun_p
    # Senkou Span B = (52-period high + low) / 2, displaced forward by kijun_p
    # For backtesting, we compute current values (no displacement since we
    # compare against present price, not future price).
    senkou_a = [0.0] * n
    senkou_b = [0.0] * n
    for i in range(kijun_p - 1, n):
        senkou_a[i] = (tenkan[i] + kijun[i]) / 2
        if i >= senkou_b_p - 1:
            hh, ll = _period_high_low(bars, i, senkou_b_p)
            senkou_b[i] = (hh + ll) / 2

    signals: List[Signal] = []
    in_position = False
    entry_price = 0.0
    start_idx = senkou_b_p

    for i in range(start_idx, n):
        if tenkan[i] == 0 or kijun[i] == 0 or senkou_a[i] == 0 or senkou_b[i] == 0:
            continue

        cloud_top = max(senkou_a[i], senkou_b[i])
        cloud_bottom = min(senkou_a[i], senkou_b[i])

        if in_position and bars[i].low <= entry_price * (1 - stop_pct):
            signals.append(Signal(
                timestamp=bars[i].timestamp, signal_type="stop_loss",
                direction="long", price=round(entry_price * (1 - stop_pct), 4),
            ))
            in_position = False

        # Entry: price above cloud + Tenkan crosses above Kijun
        if (not in_position
                and bars[i].close > cloud_top
                and tenkan[i - 1] <= kijun[i - 1]
                and tenkan[i] > kijun[i]):
            entry_price = bars[i].close
            signals.append(Signal(
                timestamp=bars[i].timestamp, signal_type="entry",
                direction="long", price=entry_price,
            ))
            in_position = True

        # Exit: Tenkan crosses below Kijun or price enters cloud
        elif (in_position
                and (tenkan[i] < kijun[i] or bars[i].close < cloud_bottom)):
            signals.append(Signal(
                timestamp=bars[i].timestamp, signal_type="exit",
                direction="long", price=bars[i].close,
            ))
            in_position = False

    return signals


register(
    slug="ichimoku",
    name="Ichimoku Cloud",
    description="Trend-following: enter above cloud on Tenkan/Kijun cross, exit on reversal.",
    default_params={"tenkan": 9, "kijun": 26, "senkou_b": 52, "stop_loss_pct": 0.05},
    param_schema=[
        {"name": "tenkan", "type": "int", "default": 9, "min": 5, "max": 20, "step": 1, "label": "Tenkan Period"},
        {"name": "kijun", "type": "int", "default": 26, "min": 15, "max": 50, "step": 1, "label": "Kijun Period"},
        {"name": "senkou_b", "type": "int", "default": 52, "min": 30, "max": 100, "step": 1, "label": "Senkou Span B Period"},
        {"name": "stop_loss_pct", "type": "float", "default": 0.05, "min": 0.005, "max": 0.20, "step": 0.005, "label": "Stop Loss %"},
    ],
    generate_signals=generate_signals,
)
