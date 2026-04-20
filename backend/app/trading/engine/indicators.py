"""
Shared Indicator Library — reusable technical indicator computations.

Provides pure-function implementations of common indicators used by both
the built-in strategy modules and the PineScript transpiler/executor.
All functions accept plain lists and return plain lists — no ORM or
framework dependencies.

Functions:
    sma, ema, rsi, macd, bollinger_bands, atr, adx, stochastic,
    vwap, highest, lowest, crossover, crossunder, wilder_smooth,
    true_range
"""

from __future__ import annotations

import math
from typing import List, Tuple


# ── Simple Moving Average ────────────────────────────────────────────────

def sma(values: List[float], period: int) -> List[float]:
    """Compute simple moving average series.

    Args:
        values: Input series (e.g. close prices).
        period: Lookback window size.

    Returns:
        List of same length; first (period-1) entries are 0.0.
    """
    n = len(values)
    result = [0.0] * n
    for i in range(period - 1, n):
        result[i] = sum(values[i - period + 1 : i + 1]) / period
    return result


# ── Exponential Moving Average ───────────────────────────────────────────

def ema(values: List[float], period: int) -> List[float]:
    """Compute exponential moving average series (SMA-seeded).

    Args:
        values: Input series.
        period: EMA lookback period.

    Returns:
        EMA series; first (period-1) entries are 0.0.
    """
    n = len(values)
    result = [0.0] * n
    if n < period:
        return result
    # Seed the first EMA value with SMA
    result[period - 1] = sum(values[:period]) / period
    k = 2 / (period + 1)
    for i in range(period, n):
        result[i] = values[i] * k + result[i - 1] * (1 - k)
    return result


# ── Wilder's Smoothing ──────────────────────────────────────────────────

def wilder_smooth(values: List[float], period: int) -> List[float]:
    """Wilder's smoothing method (used in ADX, ATR calculations).

    Args:
        values: Raw series to smooth.
        period: Smoothing period.

    Returns:
        Smoothed series.
    """
    n = len(values)
    result = [0.0] * n
    if n < period:
        return result
    result[period - 1] = sum(values[:period]) / period
    for i in range(period, n):
        result[i] = (result[i - 1] * (period - 1) + values[i]) / period
    return result


# ── Relative Strength Index ─────────────────────────────────────────────

def rsi(closes: List[float], period: int) -> List[float]:
    """Compute RSI series using Wilder's smoothing.

    Args:
        closes: Close prices.
        period: RSI lookback period.

    Returns:
        RSI values 0-100; first entries are 0.0 for insufficient data.
    """
    n = len(closes)
    result = [0.0] * n
    if n < period + 1:
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

    for i in range(period + 1, n):
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


# ── MACD ─────────────────────────────────────────────────────────────────

def macd(
    closes: List[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Tuple[List[float], List[float], List[float]]:
    """Compute MACD line, signal line, and histogram.

    Args:
        closes: Close prices.
        fast:   Fast EMA period.
        slow:   Slow EMA period.
        signal: Signal line EMA period.

    Returns:
        Tuple of (macd_line, signal_line, histogram), each same length
        as closes.
    """
    n = len(closes)
    fast_ema = ema(closes, fast)
    slow_ema = ema(closes, slow)

    macd_line = [0.0] * n
    for i in range(n):
        if fast_ema[i] != 0 and slow_ema[i] != 0:
            macd_line[i] = fast_ema[i] - slow_ema[i]

    signal_line = ema(macd_line, signal)

    histogram = [0.0] * n
    for i in range(n):
        histogram[i] = macd_line[i] - signal_line[i]

    return macd_line, signal_line, histogram


# ── Bollinger Bands ──────────────────────────────────────────────────────

def bollinger_bands(
    closes: List[float],
    period: int = 20,
    num_std: float = 2.0,
) -> Tuple[List[float], List[float], List[float], List[float]]:
    """Compute Bollinger Bands (middle, upper, lower, bandwidth).

    Args:
        closes: Close prices.
        period: SMA period for the middle band.
        num_std: Number of standard deviations for the bands.

    Returns:
        Tuple of (middle, upper, lower, bandwidth).
    """
    n = len(closes)
    middle = [0.0] * n
    upper = [0.0] * n
    lower = [0.0] * n
    bandwidth = [0.0] * n

    for i in range(period - 1, n):
        window = closes[i - period + 1 : i + 1]
        mean = sum(window) / period
        std = math.sqrt(sum((x - mean) ** 2 for x in window) / period)
        middle[i] = mean
        upper[i] = mean + num_std * std
        lower[i] = mean - num_std * std
        bandwidth[i] = (upper[i] - lower[i]) / mean if mean > 0 else 0

    return middle, upper, lower, bandwidth


# ── True Range / ATR ────────────────────────────────────────────────────

def true_range(
    highs: List[float],
    lows: List[float],
    closes: List[float],
) -> List[float]:
    """Compute true range series.

    Args:
        highs:  High prices.
        lows:   Low prices.
        closes: Close prices.

    Returns:
        True range series; first entry is 0.0.
    """
    n = len(highs)
    tr = [0.0] * n
    for i in range(1, n):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
    return tr


def atr(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 14,
) -> List[float]:
    """Compute Average True Range using Wilder's smoothing.

    Args:
        highs, lows, closes: Price series.
        period: ATR lookback period.

    Returns:
        ATR series.
    """
    tr = true_range(highs, lows, closes)
    return wilder_smooth(tr, period)


# ── ADX (Average Directional Index) ─────────────────────────────────────

def adx(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 14,
) -> Tuple[List[float], List[float], List[float]]:
    """Compute ADX, +DI, and -DI series.

    Args:
        highs, lows, closes: Price series.
        period: ADX lookback period.

    Returns:
        Tuple of (adx_series, plus_di, minus_di).
    """
    n = len(highs)

    # True Range, +DM, -DM
    tr_list = [0.0] * n
    plus_dm = [0.0] * n
    minus_dm = [0.0] * n

    for i in range(1, n):
        high_diff = highs[i] - highs[i - 1]
        low_diff = lows[i - 1] - lows[i]
        tr_list[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        plus_dm[i] = high_diff if high_diff > low_diff and high_diff > 0 else 0
        minus_dm[i] = low_diff if low_diff > high_diff and low_diff > 0 else 0

    # Wilder-smooth TR, +DM, -DM
    atr_vals = wilder_smooth(tr_list, period)
    plus_di_raw = wilder_smooth(plus_dm, period)
    minus_di_raw = wilder_smooth(minus_dm, period)

    # +DI and -DI as percentages
    plus_di = [0.0] * n
    minus_di = [0.0] * n
    for i in range(n):
        if atr_vals[i] > 0:
            plus_di[i] = (plus_di_raw[i] / atr_vals[i]) * 100
            minus_di[i] = (minus_di_raw[i] / atr_vals[i]) * 100

    # DX
    dx = [0.0] * n
    for i in range(n):
        di_sum = plus_di[i] + minus_di[i]
        dx[i] = (abs(plus_di[i] - minus_di[i]) / di_sum * 100) if di_sum > 0 else 0

    # ADX = Wilder-smooth of DX
    adx_series = wilder_smooth(dx, period)

    return adx_series, plus_di, minus_di


# ── Stochastic Oscillator ───────────────────────────────────────────────

def stochastic(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    k_period: int = 14,
    d_period: int = 3,
) -> Tuple[List[float], List[float]]:
    """Compute Stochastic Oscillator %K and %D.

    Args:
        highs, lows, closes: Price series.
        k_period: %K lookback period.
        d_period: %D smoothing period (SMA of %K).

    Returns:
        Tuple of (pct_k, pct_d).
    """
    n = len(closes)
    pct_k = [0.0] * n
    pct_d = [0.0] * n

    # %K
    for i in range(k_period - 1, n):
        h_window = highs[i - k_period + 1 : i + 1]
        l_window = lows[i - k_period + 1 : i + 1]
        high_val = max(h_window)
        low_val = min(l_window)
        rng = high_val - low_val
        pct_k[i] = ((closes[i] - low_val) / rng * 100) if rng > 0 else 50.0

    # %D = SMA of %K
    for i in range(k_period + d_period - 2, n):
        pct_d[i] = sum(pct_k[i - d_period + 1 : i + 1]) / d_period

    return pct_k, pct_d


# ── VWAP ────────────────────────────────────────────────────────────────

def vwap(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    volumes: List[float],
) -> List[float]:
    """Compute cumulative Volume Weighted Average Price.

    Args:
        highs, lows, closes, volumes: Price and volume series.

    Returns:
        VWAP series.
    """
    n = len(closes)
    result = [0.0] * n
    cum_vol = 0.0
    cum_tp_vol = 0.0
    for i in range(n):
        tp = (highs[i] + lows[i] + closes[i]) / 3
        cum_vol += volumes[i]
        cum_tp_vol += tp * volumes[i]
        result[i] = cum_tp_vol / cum_vol if cum_vol > 0 else 0.0
    return result


# ── Highest / Lowest ────────────────────────────────────────────────────

def highest(values: List[float], period: int) -> List[float]:
    """Compute rolling highest value over a lookback window.

    Args:
        values: Input series.
        period: Lookback window.

    Returns:
        Rolling high series; first (period-1) entries are 0.0.
    """
    n = len(values)
    result = [0.0] * n
    for i in range(period - 1, n):
        result[i] = max(values[i - period + 1 : i + 1])
    return result


def lowest(values: List[float], period: int) -> List[float]:
    """Compute rolling lowest value over a lookback window.

    Args:
        values: Input series.
        period: Lookback window.

    Returns:
        Rolling low series; first (period-1) entries are 0.0.
    """
    n = len(values)
    result = [0.0] * n
    for i in range(period - 1, n):
        result[i] = min(values[i - period + 1 : i + 1])
    return result


# ── Crossover / Crossunder ──────────────────────────────────────────────

def crossover(a: List[float], b: List[float]) -> List[bool]:
    """Detect where series *a* crosses above series *b*.

    Args:
        a: First series.
        b: Second series.

    Returns:
        Boolean list; True at each bar where a crosses above b.
    """
    n = min(len(a), len(b))
    result = [False] * n
    for i in range(1, n):
        if a[i - 1] <= b[i - 1] and a[i] > b[i]:
            result[i] = True
    return result


def crossunder(a: List[float], b: List[float]) -> List[bool]:
    """Detect where series *a* crosses below series *b*.

    Args:
        a: First series.
        b: Second series.

    Returns:
        Boolean list; True at each bar where a crosses below b.
    """
    n = min(len(a), len(b))
    result = [False] * n
    for i in range(1, n):
        if a[i - 1] >= b[i - 1] and a[i] < b[i]:
            result[i] = True
    return result
