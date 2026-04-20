"""
Breakout Strategy — enter on price breaking above N-bar high with volume confirmation.

Enter long when price closes above the highest high of the lookback window
and volume exceeds the average volume by a configurable factor.  Exit when
price falls below the lookback low.

Default params: lookback=20, volume_factor=1.5, stop_loss_pct=0.05
"""

from __future__ import annotations

from typing import Any, Dict, List

from .. import Signal
from ...providers import OHLCVBar
from . import register


def generate_signals(bars: List[OHLCVBar], params: Dict[str, Any]) -> List[Signal]:
    """Generate entry/exit signals based on price breakout with volume.

    Args:
        bars:   Chronological OHLCV bars.
        params: Strategy parameters.

    Returns:
        List of Signal objects.
    """
    lookback = params.get("lookback", 20)
    vol_factor = params.get("volume_factor", 1.5)
    stop_pct = params.get("stop_loss_pct", 0.05)

    if len(bars) < lookback + 1:
        return []

    signals: List[Signal] = []
    in_position = False
    entry_price = 0.0

    for i in range(lookback, len(bars)):
        window = bars[i - lookback : i]
        highest_high = max(b.high for b in window)
        lowest_low = min(b.low for b in window)
        avg_volume = sum(b.volume for b in window) / lookback

        if in_position and bars[i].low <= entry_price * (1 - stop_pct):
            signals.append(Signal(
                timestamp=bars[i].timestamp, signal_type="stop_loss",
                direction="long", price=round(entry_price * (1 - stop_pct), 4),
            ))
            in_position = False

        # Breakout: close above highest high + volume confirmation
        if (not in_position
                and bars[i].close > highest_high
                and bars[i].volume > avg_volume * vol_factor):
            entry_price = bars[i].close
            signals.append(Signal(
                timestamp=bars[i].timestamp, signal_type="entry",
                direction="long", price=entry_price,
            ))
            in_position = True

        # Exit: price falls below lookback low
        elif in_position and bars[i].close < lowest_low:
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
    lookback = params.get("lookback", 20)
    n = len(bars)
    highest_high = [0.0] * n
    lowest_low = [0.0] * n
    avg_volume = [0.0] * n
    for i in range(lookback, n):
        window = bars[i - lookback : i]
        highest_high[i] = max(b.high for b in window)
        lowest_low[i] = min(b.low for b in window)
        avg_volume[i] = sum(b.volume for b in window) / lookback
    return {
        "highest_high": highest_high,
        "lowest_low": lowest_low,
        "avg_volume": avg_volume,
    }


register(
    slug="breakout",
    name="Breakout",
    description="Momentum breakout: enter on N-bar high breakout with volume confirmation.",
    default_params={"lookback": 20, "volume_factor": 1.5, "stop_loss_pct": 0.05},
    param_schema=[
        {"name": "lookback", "type": "int", "default": 20, "min": 5, "max": 60, "step": 1, "label": "Lookback Period"},
        {"name": "volume_factor", "type": "float", "default": 1.5, "min": 1.0, "max": 3.0, "step": 0.1, "label": "Volume Factor"},
        {"name": "stop_loss_pct", "type": "float", "default": 0.05, "min": 0.005, "max": 0.20, "step": 0.005, "label": "Stop Loss %"},
    ],
    generate_signals=generate_signals,
)
