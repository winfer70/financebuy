"""
VWAP Bounce Strategy — intraday mean reversion around VWAP.

Enter long when price drops below VWAP by a configurable deviation and
bounces back.  Exit when price reaches VWAP or rises above by deviation.

Default params: deviation=0.02, stop_loss_pct=0.03
"""

from __future__ import annotations

from typing import Any, Dict, List

from .. import Signal
from ...providers import OHLCVBar
from . import register


def _compute_vwap(bars: List[OHLCVBar]) -> List[float]:
    """Compute cumulative VWAP series.

    Args:
        bars: Chronological OHLCV bars.

    Returns:
        VWAP values per bar (0.0 where volume is insufficient).
    """
    vwap = [0.0] * len(bars)
    cum_vol = 0.0
    cum_tp_vol = 0.0
    for i, b in enumerate(bars):
        tp = (b.high + b.low + b.close) / 3
        cum_vol += b.volume
        cum_tp_vol += tp * b.volume
        vwap[i] = cum_tp_vol / cum_vol if cum_vol > 0 else 0.0
    return vwap


def generate_signals(bars: List[OHLCVBar], params: Dict[str, Any]) -> List[Signal]:
    """Generate entry/exit signals based on VWAP bounce.

    Args:
        bars:   Chronological OHLCV bars.
        params: Strategy parameters.

    Returns:
        List of Signal objects.
    """
    deviation = params.get("deviation", 0.02)
    stop_pct = params.get("stop_loss_pct", 0.03)

    if len(bars) < 10:
        return []

    vwap = _compute_vwap(bars)

    signals: List[Signal] = []
    in_position = False
    entry_price = 0.0

    for i in range(1, len(bars)):
        if vwap[i] == 0:
            continue

        lower_band = vwap[i] * (1 - deviation)
        upper_band = vwap[i] * (1 + deviation)

        if in_position and bars[i].low <= entry_price * (1 - stop_pct):
            signals.append(Signal(
                timestamp=bars[i].timestamp, signal_type="stop_loss",
                direction="long", price=round(entry_price * (1 - stop_pct), 4),
            ))
            in_position = False

        # Price dipped below lower band and now bouncing back above it
        if (not in_position
                and bars[i - 1].close < lower_band
                and bars[i].close >= lower_band):
            entry_price = bars[i].close
            signals.append(Signal(
                timestamp=bars[i].timestamp, signal_type="entry",
                direction="long", price=entry_price,
            ))
            in_position = True

        # Price reaches upper band or VWAP → take profit
        elif in_position and bars[i].close >= upper_band:
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
    deviation = params.get("deviation", 0.02)
    vwap_vals = _compute_vwap(bars)
    lower_band = [v * (1 - deviation) if v > 0 else 0.0 for v in vwap_vals]
    upper_band = [v * (1 + deviation) if v > 0 else 0.0 for v in vwap_vals]
    return {
        "vwap": vwap_vals,
        "vwap_lower": lower_band,
        "vwap_upper": upper_band,
    }


register(
    slug="vwap_bounce",
    name="VWAP Bounce",
    description="Mean reversion: enter on bounce below VWAP, exit at VWAP + deviation.",
    default_params={"deviation": 0.02, "stop_loss_pct": 0.03},
    param_schema=[
        {"name": "deviation", "type": "float", "default": 0.02, "min": 0.005, "max": 0.05, "step": 0.005, "label": "VWAP Deviation"},
        {"name": "stop_loss_pct", "type": "float", "default": 0.03, "min": 0.005, "max": 0.10, "step": 0.005, "label": "Stop Loss %"},
    ],
    generate_signals=generate_signals,
)
