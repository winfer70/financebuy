"""
scanner_session.py — Market session detection and volume projection for the scanner.

Determines the current NYSE/NASDAQ session state and computes an elapsed-weight
factor used to project intraday volumes onto a full-day basis.
"""
from __future__ import annotations

import os
from datetime import datetime, time
from typing import Tuple

import pytz

_ET = pytz.timezone("America/New_York")

# NYSE/NASDAQ session boundaries (all times Eastern)
_PRE_OPEN    = time(4, 0)
_OPEN        = time(9, 30)
_MID_START   = time(11, 0)    # mid-session starts after opening volatility
_POWER_START = time(14, 30)   # power hour region
_CLOSE       = time(16, 0)
_AFTER_CLOSE = time(20, 0)


def get_market_session(dt_et: datetime) -> str:
    """Return the current market session label for a given Eastern-time datetime.

    Args:
        dt_et: datetime in US/Eastern timezone.

    Returns:
        One of: "pre" | "open" | "mid" | "power" | "close" | "after" | "closed"
    """
    t = dt_et.time()
    # Weekend check
    if dt_et.weekday() >= 5:
        return "closed"
    if t < _PRE_OPEN:
        return "closed"
    if t < _OPEN:
        return "pre"
    if t < _MID_START:
        return "open"
    if t < _POWER_START:
        return "mid"
    if t < _CLOSE:
        return "power"
    if t < _AFTER_CLOSE:
        return "after"
    return "closed"


def get_elapsed_weight(dt_et: datetime) -> float:
    """Return the fraction of the regular NYSE session elapsed at the given time.

    Regular session: 9:30 AM - 4:00 PM ET = 390 minutes.

    Args:
        dt_et: datetime in US/Eastern timezone.

    Returns:
        Float in [0.0, 1.0]. 0.0 before open or outside hours, 1.0 at/after close.
    """
    if dt_et.weekday() >= 5:
        return 0.0
    t = dt_et.time()
    open_t  = _OPEN
    close_t = _CLOSE
    if t < open_t:
        return 0.0
    if t >= close_t:
        return 1.0
    open_minutes    = open_t.hour * 60 + open_t.minute
    close_minutes   = close_t.hour * 60 + close_t.minute
    current_minutes = t.hour * 60 + t.minute + t.second / 60
    elapsed = (current_minutes - open_minutes) / (close_minutes - open_minutes)
    return round(min(max(elapsed, 0.0), 1.0), 4)


def project_daily_volume(intraday_vol: float, elapsed_weight: float) -> float:
    """Project a full-day volume estimate from intraday volume and elapsed weight.

    Args:
        intraday_vol:   Volume accumulated so far in the session.
        elapsed_weight: Fraction of session elapsed (from get_elapsed_weight).

    Returns:
        Projected full-day volume. Returns intraday_vol unchanged if elapsed_weight == 0.
    """
    if elapsed_weight <= 0:
        return intraday_vol
    return intraday_vol / elapsed_weight


def get_session_context() -> dict:
    """Return a full session context dict for the current moment.

    Returns:
        dict with keys: session_state (str), elapsed_weight (float), mode (str).
        mode is always "auto" — the caller can override it.
    """
    now_et = datetime.now(_ET)
    return {
        "session_state": get_market_session(now_et),
        "elapsed_weight": get_elapsed_weight(now_et),
        "mode": "auto",
    }
