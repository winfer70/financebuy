"""
routes/market.py — Market data API endpoints.

Provides real-time and historical market data sourced from yfinance,
including quotes, OHLCV bars, symbol search, SMA, price changes,
exchange rates, and financial events (earnings, dividends, splits).

All endpoints require authentication and use an in-memory cache to
reduce redundant API calls.

Route prefix: /api/v1/market  (registered in main.py)
"""

import asyncio
import json
import math
import time
import urllib.request
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from zoneinfo import ZoneInfo

import yfinance as yf
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..schemas import (
    EventItem,
    EventsResponse,
    FundamentalsResponse,
    SectorItem,
    SectorResponse,
    ScreenerItem,
    ScreenerResponse,
)

# Canonical auth dependency — returns a User ORM object (not a string)
from .auth_routes import get_current_user

router = APIRouter()


class OHLCVBar(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    is_earnings: bool = False


class OHLCVResponse(BaseModel):
    bars: List[OHLCVBar]
    volume_source: Optional[str] = None  # e.g. "GLD" when ETF volume is used
    interval: str = "1d"
    warning: Optional[str] = None


class QuoteOut(BaseModel):
    symbol: str
    name: str
    price: float
    open: float
    high: float
    low: float
    prev_close: float
    volume: int
    change: float
    change_pct: float


class SectorPerformance(BaseModel):
    """Performance data for a single market sector, sourced from its ETF proxy."""
    sector: str
    etf_symbol: str
    price: float
    day_change_pct: float
    week_change_pct: Optional[float]
    month_change_pct: Optional[float]


# ── In-memory cache ──────────────────────────────────────────────────────────
_cache: Dict[str, Tuple[float, object]] = {}

_QUOTE_TTL_OPEN = 3       # seconds — market open
_QUOTE_TTL_CLOSED = 300   # 5 minutes — market closed
_OHLCV_TTL = 300          # 5 minutes
_SYMBOLS_TTL = 3600       # 1 hour
_EVENTS_TTL = 3600        # 1 hour — earnings/dividend dates change infrequently

_NYSE_TZ = ZoneInfo("America/New_York")


def _is_market_open() -> bool:
    """Check if NYSE is currently in regular trading hours (Mon-Fri 9:30-16:00 ET)."""
    now = datetime.now(_NYSE_TZ)
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now < market_close


def _quote_ttl() -> float:
    return _QUOTE_TTL_OPEN if _is_market_open() else _QUOTE_TTL_CLOSED

# Default watchlist symbols shown in /symbols endpoint
_DEFAULT_SYMBOLS = [
    "AAPL", "MSFT", "NVDA", "TSLA", "AMZN",
    "GOOGL", "META", "SPY", "QQQ", "AMD",
]


def _get_cached(key: str, ttl: float) -> Optional[object]:
    entry = _cache.get(key)
    if entry and (time.time() - entry[0]) < ttl:
        return entry[1]
    return None


def _set_cached(key: str, value: object) -> None:
    _cache[key] = (time.time(), value)


# ── Name cache (long-lived — company names rarely change) ────────────────────
_NAME_TTL = 86400  # 24 hours


def _resolve_name(ticker: yf.Ticker, sym: str) -> str:
    """Resolve company name with a long-lived cache to avoid slow ticker.info."""
    cached = _get_cached(f"name:{sym}", _NAME_TTL)
    if cached:
        return cached

    name = sym
    try:
        full_info = ticker.info
        name = full_info.get("longName") or full_info.get("shortName") or sym
    except Exception:
        pass
    _set_cached(f"name:{sym}", name)
    return name


# ── Interval mapping ─────────────────────────────────────────────────────────
# (yf_interval, aggregate_n, max_days)  — None max_days = unlimited
_INTERVAL_MAP: Dict[str, Tuple[str, int, Optional[int]]] = {
    "1m":   ("1m",   1, 7),
    "2m":   ("2m",   1, 60),
    "3m":   ("1m",   3, 7),
    "5m":   ("5m",   1, 60),
    "10m":  ("5m",   2, 60),
    "15m":  ("15m",  1, 60),
    "30m":  ("30m",  1, 60),
    "45m":  ("15m",  3, 60),
    "1h":   ("60m",  1, 730),
    "2h":   ("60m",  2, 730),
    "3h":   ("60m",  3, 730),
    "4h":   ("60m",  4, 730),
    "1d":   ("1d",   1, None),
    "1wk":  ("1wk",  1, None),
    "1mo":  ("1mo",  1, None),
    "3mo":  ("3mo",  1, None),
    "6mo":  ("1mo",  6, None),
    "12mo": ("1mo", 12, None),
}

_INTRADAY_INTERVALS = {"1m", "2m", "3m", "5m", "10m", "15m", "30m", "45m", "1h", "2h", "3h", "4h"}


def _aggregate_bars(bars: List[OHLCVBar], n: int) -> List[OHLCVBar]:
    """Group consecutive bars into candles of size n."""
    result: List[OHLCVBar] = []
    for i in range(0, len(bars), n):
        group = bars[i : i + n]
        if not group:
            break
        result.append(
            OHLCVBar(
                date=group[0].date,
                open=group[0].open,
                high=round(max(b.high for b in group), 2),
                low=round(min(b.low for b in group), 2),
                close=group[-1].close,
                volume=sum(b.volume for b in group),
                is_earnings=any(b.is_earnings for b in group),
            )
        )
    return result


# ── yfinance helpers (synchronous — called via asyncio.to_thread) ────────────

# Futures symbols with unreliable volume → map to ETF for volume data
_FUTURES_TO_ETF = {
    "GC=F": "GLD",   # Gold futures → SPDR Gold Shares
    "SI=F": "SLV",   # Silver futures → iShares Silver Trust
    "PL=F": "PPLT",  # Platinum futures → abrdn Platinum ETF
    "PA=F": "PALL",  # Palladium futures → abrdn Palladium ETF
    "CL=F": "USO",   # Crude oil futures → US Oil Fund
    "NG=F": "UNG",   # Natural gas futures → US Natural Gas Fund
    "HG=F": "CPER",  # Copper futures → US Copper Index Fund
}


def _safe_float(value, default: float = 0.0) -> float:
    """Sanitize a numeric value from yfinance, replacing NaN/Inf with a default.

    Args:
        value: Raw numeric value from yfinance fast_info or history data.
        default: Fallback value when the input is non-finite (NaN, Inf, -Inf).

    Returns:
        A finite float safe for JSON serialization.
    """
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) else default


def _fetch_earnings_dates_set(sym: str) -> Set[str]:
    """Fetch known earnings dates for a symbol as a set of 'YYYY-MM-DD' strings.

    Used by OHLCV fetchers to flag bars that coincide with earnings releases.
    Results are cached for 1 hour under the 'earnings_dates:{sym}' key.

    Args:
        sym: Uppercase ticker symbol.

    Returns:
        A set of date strings in 'YYYY-MM-DD' format.
    """
    cache_key = f"earnings_dates:{sym}"
    cached = _get_cached(cache_key, _EVENTS_TTL)
    if cached is not None:
        return cached

    dates: Set[str] = set()
    try:
        ticker = yf.Ticker(sym)
        earnings_df = ticker.earnings_dates
        if earnings_df is not None and not earnings_df.empty:
            for dt in earnings_df.index:
                dates.add(dt.strftime("%Y-%m-%d"))
    except Exception:
        pass

    _set_cached(cache_key, dates)
    return dates


def _fetch_quote(sym: str) -> QuoteOut:
    ticker = yf.Ticker(sym)
    fi = ticker.fast_info

    # Use fast_info for real-time quote data (faster and more reliable than
    # history() which can intermittently return empty/stale data).
    # _safe_float guards against NaN/Inf values that yfinance can return
    # for futures, crypto, or tickers outside trading hours.
    price = round(_safe_float(fi.last_price), 2)
    prev_close = round(_safe_float(fi.regular_market_previous_close), 2)
    open_price = round(_safe_float(fi.open), 2)
    high = round(_safe_float(fi.day_high), 2)
    low = round(_safe_float(fi.day_low), 2)
    volume = int(_safe_float(fi.last_volume))

    chg = round(price - prev_close, 2)
    chg_pct = round(chg / prev_close * 100, 2) if prev_close else 0.0

    name = _resolve_name(ticker, sym)

    return QuoteOut(
        symbol=sym,
        name=name,
        price=price,
        open=open_price,
        high=high,
        low=low,
        prev_close=prev_close,
        volume=volume,
        change=chg,
        change_pct=chg_pct,
    )


def _fetch_ohlcv(sym: str, years: int) -> OHLCVResponse:
    """Fetch daily OHLCV data for a symbol over the given number of years.

    Flags bars that coincide with earnings release dates. For futures symbols
    with unreliable volume, substitutes ETF volume data.

    Args:
        sym:   Uppercase ticker symbol.
        years: Number of years of history to fetch (1–10).

    Returns:
        OHLCVResponse with bars, optional volume_source, and is_earnings flags.
    """
    ticker = yf.Ticker(sym)
    period = f"{years}y" if years <= 5 else "max"
    hist = ticker.history(period=period, auto_adjust=True)
    if hist.empty:
        raise ValueError(f"No OHLCV data for {sym}")

    # Fetch earnings dates to flag bars that coincide with earnings releases
    earnings_dates = _fetch_earnings_dates_set(sym)

    # If this is a futures symbol with unreliable volume, fetch ETF volume
    etf_sym = _FUTURES_TO_ETF.get(sym)
    etf_vol: Dict[str, int] = {}
    if etf_sym:
        try:
            etf_hist = yf.Ticker(etf_sym).history(period=period, auto_adjust=True)
            for dt, row in etf_hist.iterrows():
                etf_vol[dt.strftime("%Y-%m-%d")] = int(row["Volume"])
        except Exception:
            etf_sym = None  # fall back to original volume

    bars: List[OHLCVBar] = []
    for dt, row in hist.iterrows():
        date_str = dt.strftime("%Y-%m-%d")
        volume = etf_vol.get(date_str, int(row["Volume"])) if etf_vol else int(row["Volume"])
        bars.append(OHLCVBar(
            date=date_str,
            open=round(_safe_float(row["Open"]), 2),
            high=round(_safe_float(row["High"]), 2),
            low=round(_safe_float(row["Low"]), 2),
            close=round(_safe_float(row["Close"]), 2),
            volume=volume,
            is_earnings=date_str in earnings_dates,
        ))
    return OHLCVResponse(
        bars=bars,
        volume_source=etf_sym if etf_vol else None,
    )


def _fetch_ohlcv_interval(sym: str, interval: str, days: int) -> OHLCVResponse:
    """Fetch OHLCV data for a symbol at a specific interval.

    Uses the _INTERVAL_MAP to resolve yfinance base interval and aggregation
    factor.  Clamps `days` to the maximum allowed by yfinance for intraday
    intervals and returns a warning when clamped.  Flags bars that coincide
    with earnings release dates (daily resolution only — intraday bars are
    matched by their date portion).

    Args:
        sym:      Uppercase ticker symbol.
        interval: Requested candle interval (e.g. '1d', '1h', '5m').
        days:     Number of calendar days of history to fetch.

    Returns:
        OHLCVResponse with bars, interval label, optional volume_source,
        is_earnings flags, and optional clamping warning.
    """
    entry = _INTERVAL_MAP.get(interval)
    if entry is None:
        raise ValueError(f"Unsupported interval: {interval}")

    yf_interval, aggregate_n, max_days = entry
    warning = None

    if max_days is not None and days > max_days:
        warning = f"{interval} data limited to {max_days} days of history"
        days = max_days

    is_intraday = interval in _INTRADAY_INTERVALS
    start = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")

    ticker = yf.Ticker(sym)
    hist = ticker.history(start=start, interval=yf_interval, auto_adjust=True)
    if hist.empty:
        raise ValueError(f"No data for {sym} at interval {interval}")

    # Fetch earnings dates to flag bars on earnings days
    earnings_dates = _fetch_earnings_dates_set(sym)

    # Fetch ETF volume for futures symbols
    etf_sym = _FUTURES_TO_ETF.get(sym)
    etf_vol: Dict[str, int] = {}
    if etf_sym and not is_intraday:
        try:
            etf_hist = yf.Ticker(etf_sym).history(
                start=start, interval=yf_interval, auto_adjust=True
            )
            for dt, row in etf_hist.iterrows():
                key = dt.strftime("%Y-%m-%dT%H:%M:%S%z") if is_intraday else dt.strftime("%Y-%m-%d")
                etf_vol[key] = int(row["Volume"])
        except Exception:
            etf_sym = None

    bars: List[OHLCVBar] = []
    for dt, row in hist.iterrows():
        if is_intraday:
            date_str = dt.strftime("%Y-%m-%dT%H:%M:%S%z")
            # For intraday bars, match earnings by the date portion only
            day_str = dt.strftime("%Y-%m-%d")
        else:
            date_str = dt.strftime("%Y-%m-%d")
            day_str = date_str
        volume = etf_vol.get(date_str, int(row["Volume"])) if etf_vol else int(row["Volume"])
        bars.append(
            OHLCVBar(
                date=date_str,
                open=round(_safe_float(row["Open"]), 2),
                high=round(_safe_float(row["High"]), 2),
                low=round(_safe_float(row["Low"]), 2),
                close=round(_safe_float(row["Close"]), 2),
                volume=volume,
                is_earnings=day_str in earnings_dates,
            )
        )

    if aggregate_n > 1:
        bars = _aggregate_bars(bars, aggregate_n)

    return OHLCVResponse(
        bars=bars,
        volume_source=etf_sym if etf_vol else None,
        interval=interval,
        warning=warning,
    )


def _fetch_symbols_info() -> List[dict]:
    results = []
    for sym in _DEFAULT_SYMBOLS:
        try:
            ticker = yf.Ticker(sym)
            fi = ticker.fast_info
            price = round(_safe_float(fi.last_price), 2)
            name = _resolve_name(ticker, sym)
            results.append({"symbol": sym, "name": name, "price": price})
        except Exception:
            continue
    return results


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/quote/{symbol}", response_model=QuoteOut)
async def get_quote(symbol: str, current_user=Depends(get_current_user)):
    sym = symbol.upper()
    cache_key = f"quote:{sym}"
    cached = _get_cached(cache_key, _quote_ttl())
    if cached:
        return cached

    try:
        quote = await asyncio.to_thread(_fetch_quote, sym)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Could not fetch quote for '{sym}': {exc}")

    _set_cached(cache_key, quote)
    return quote


async def get_ohlcv_series(symbol: str, years: int) -> OHLCVResponse:
    """Fetch (or reuse the cached) daily OHLCV history for a symbol.

    Public wrapper around _fetch_ohlcv for callers outside this module (e.g.
    the insider track-record calculation), sharing the same cache as
    GET /market/ohlcv/{symbol}.
    """
    sym = symbol.upper()
    cache_key = f"ohlcv:{sym}:{years}"
    cached = _get_cached(cache_key, _OHLCV_TTL)
    if cached:
        return cached
    result = await asyncio.to_thread(_fetch_ohlcv, sym, years)
    _set_cached(cache_key, result)
    return result


@router.get("/ohlcv/{symbol}", response_model=OHLCVResponse)
async def get_ohlcv(symbol: str, years: int = Query(default=5, ge=1, le=10),
                    current_user=Depends(get_current_user)):
    sym = symbol.upper()
    cache_key = f"ohlcv:{sym}:{years}"
    cached = _get_cached(cache_key, _OHLCV_TTL)
    if cached:
        return cached

    try:
        result = await asyncio.to_thread(_fetch_ohlcv, sym, years)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Could not fetch OHLCV for '{sym}': {exc}")

    _set_cached(cache_key, result)
    return result


@router.get("/ohlcv_interval/{symbol}", response_model=OHLCVResponse)
async def get_ohlcv_interval(
    symbol: str,
    interval: str = Query(
        default="1d",
        description="Candle interval: 1m,2m,3m,5m,10m,15m,30m,45m,1h,2h,3h,4h,1d,1wk,1mo,3mo,6mo,12mo",
    ),
    days: int = Query(default=365, ge=1, le=3650, description="Calendar days of history"),
    current_user=Depends(get_current_user),
):
    """Fetch OHLCV data at any supported interval with automatic aggregation."""
    sym = symbol.upper()

    if interval not in _INTERVAL_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid interval '{interval}'. Valid: {list(_INTERVAL_MAP.keys())}",
        )

    cache_key = f"ohlcv_interval:{sym}:{interval}:{days}"
    cached = _get_cached(cache_key, _OHLCV_TTL)
    if cached:
        return cached

    try:
        result = await asyncio.to_thread(_fetch_ohlcv_interval, sym, interval, days)
    except Exception as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Could not fetch OHLCV for '{sym}' at interval '{interval}': {exc}",
        )

    _set_cached(cache_key, result)
    return result


@router.get("/symbols", response_model=List[dict])
async def list_symbols(current_user=Depends(get_current_user)):
    cache_key = "symbols_list"
    cached = _get_cached(cache_key, _SYMBOLS_TTL)
    if cached:
        return cached

    try:
        symbols = await asyncio.to_thread(_fetch_symbols_info)
    except Exception:
        # Fallback to basic list without prices if Yahoo is unreachable
        symbols = [{"symbol": s, "name": s, "price": 0} for s in _DEFAULT_SYMBOLS]

    _set_cached(cache_key, symbols)
    return symbols


_SEARCH_TTL = 300  # 5 minutes


def _search_symbols(query: str, max_results: int = 8) -> List[dict]:
    """Search Yahoo Finance for symbols matching a query string."""
    url = (
        f"https://query2.finance.yahoo.com/v1/finance/search"
        f"?q={urllib.request.quote(query)}"
        f"&quotesCount={max_results}&newsCount=0&listsCount=0"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())

    results = []
    for q in data.get("quotes", []):
        # Only include equities and ETFs traded on major US exchanges
        if not q.get("isYahooFinance"):
            continue
        results.append({
            "symbol": q.get("symbol", ""),
            "name": q.get("longname") or q.get("shortname") or q.get("symbol", ""),
            "exchange": q.get("exchDisp", ""),
            "type": q.get("typeDisp", ""),
        })
    return results


@router.get("/search", response_model=List[dict])
async def search_symbols(
    q: str = Query(..., min_length=1, description="Search query (ticker or company name)"),
    current_user=Depends(get_current_user),
):
    cache_key = f"search:{q.lower()}"
    cached = _get_cached(cache_key, _SEARCH_TTL)
    if cached:
        return cached

    try:
        results = await asyncio.to_thread(_search_symbols, q)
    except Exception:
        results = []

    _set_cached(cache_key, results)
    return results


# ── Bulk quotes ───────────────────────────────────────────────────────────────

@router.get("/bulk_quotes", response_model=List[QuoteOut])
async def get_bulk_quotes(
    symbols: str = Query(..., description="Comma-separated ticker symbols, e.g. AAPL,MSFT,TSLA"),
    current_user=Depends(get_current_user),
):
    """Fetch quotes for multiple symbols in one request.

    Uses the same per-symbol cache as /quote/{symbol} so repeated calls
    for the same ticker within the TTL are free.  Symbols that fail to
    fetch are silently skipped.
    """
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not sym_list:
        raise HTTPException(status_code=400, detail="No symbols provided.")
    if len(sym_list) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 symbols per request.")

    # Separate cache hits from symbols that need network fetches.
    hit_map: dict = {}
    to_fetch: list = []
    for sym in sym_list:
        cached = _get_cached(f"quote:{sym}", _quote_ttl())
        if cached:
            hit_map[sym] = cached
        else:
            to_fetch.append(sym)

    # Fetch all uncached symbols concurrently to avoid O(n) sequential latency.
    async def _fetch_one(sym: str):
        try:
            q = await asyncio.to_thread(_fetch_quote, sym)
            _set_cached(f"quote:{sym}", q)
            return sym, q
        except Exception:
            return sym, None

    for sym, q in await asyncio.gather(*(_fetch_one(s) for s in to_fetch)):
        if q is not None:
            hit_map[sym] = q

    # Return in original request order, skipping symbols that failed.
    return [hit_map[sym] for sym in sym_list if sym in hit_map]


# ── Price change ──────────────────────────────────────────────────────────────

_PRICE_CHANGE_TTL = 300  # 5 minutes
_SMA_TTL = 300  # 5 minutes

_PERIOD_DAYS_MAP: Dict[str, int] = {
    "1D": 5,    # ~5 calendar days to ensure at least one prior trading day
    "1W": 10,
    "1M": 35,
    "3M": 95,
    "1Y": 370,
}


def _fetch_price_change(sym: str, period: str) -> dict:
    """Compute percentage price change for a symbol over the given period.

    For "1D": compares the last two trading-day closes so the result
    reflects a single-day move (e.g. Friday vs Thursday).

    For longer periods (1W, 1M, 3M, 1Y): compares the most recent close
    to the first close in the window to capture the full-period change.

    Returns 0.0 if insufficient data is available.
    """
    days = _PERIOD_DAYS_MAP[period]
    start = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    hist = yf.Ticker(sym).history(start=start, auto_adjust=True)
    if len(hist) < 2:
        return {"symbol": sym, "period": period, "change_pct": 0.0}
    # For 1D, use the second-to-last bar as the baseline (previous trading day)
    # so the result is a true single-day change, not a multi-day window.
    ref_close = _safe_float(hist.iloc[-2]["Close"]) if period == "1D" else _safe_float(hist.iloc[0]["Close"])
    last_close = _safe_float(hist.iloc[-1]["Close"])
    if ref_close == 0:
        return {"symbol": sym, "period": period, "change_pct": 0.0}
    change_pct = round((last_close - ref_close) / ref_close * 100, 2)
    # Guard the final result in case arithmetic still produced a non-finite value
    return {"symbol": sym, "period": period, "change_pct": _safe_float(change_pct)}


@router.get("/price_change")
async def get_price_change(
    symbol: str = Query(..., description="Ticker symbol"),
    period: str = Query(..., description="Period: 1D, 1W, 1M, 3M, or 1Y"),
    current_user=Depends(get_current_user),
):
    """Return the percentage price change for a symbol over a given period."""
    sym = symbol.upper()
    if period not in _PERIOD_DAYS_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid period '{period}'. Valid values: {list(_PERIOD_DAYS_MAP.keys())}",
        )

    cache_key = f"price_change:{sym}:{period}"
    cached = _get_cached(cache_key, _PRICE_CHANGE_TTL)
    if cached:
        return cached

    try:
        result = await asyncio.to_thread(_fetch_price_change, sym, period)
    except Exception:
        result = {"symbol": sym, "period": period, "change_pct": 0.0}

    _set_cached(cache_key, result)
    return result


# ── SMA (Simple Moving Average) ─────────────────────────────────────────────

def _fetch_sma(sym: str, period: int) -> dict:
    """Compute the Simple Moving Average for a symbol over `period` trading days."""
    # ~1.5 calendar days per trading day + buffer
    cal_days = int(period * 1.5) + 60
    start = (date.today() - timedelta(days=cal_days)).strftime("%Y-%m-%d")
    hist = yf.Ticker(sym).history(start=start, auto_adjust=True)
    if len(hist) < period:
        return {"symbol": sym, "period": period, "sma": None}
    closes = hist["Close"].values[-period:]
    sma_val = _safe_float(sum(closes) / len(closes))
    sma = round(sma_val, 2) if sma_val != 0.0 else None
    return {"symbol": sym, "period": period, "sma": sma}


@router.get("/bulk_sma", response_model=List[dict])
async def get_bulk_sma(
    symbols: str = Query(..., description="Comma-separated ticker symbols"),
    period: int = Query(default=50, ge=5, le=200, description="SMA period in trading days"),
    current_user=Depends(get_current_user),
):
    """Return SMA values for multiple symbols in one request."""
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not sym_list:
        raise HTTPException(status_code=400, detail="No symbols provided.")
    if len(sym_list) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 symbols per request.")

    results: List[dict] = []
    for sym in sym_list:
        cache_key = f"sma:{sym}:{period}"
        cached = _get_cached(cache_key, _SMA_TTL)
        if cached:
            results.append(cached)
            continue
        try:
            sma_result = await asyncio.to_thread(_fetch_sma, sym, period)
            _set_cached(cache_key, sma_result)
            results.append(sma_result)
        except Exception:
            results.append({"symbol": sym, "period": period, "sma": None})
    return results


# ── Exchange rates (ECB via frankfurter.app, 1h cache) ──────────────────────

_EXCHANGE_RATE_TTL = 3600  # 1 hour — ECB updates once per business day

# Supported display currencies (must match schemas.SUPPORTED_CURRENCIES)
_FX_CURRENCIES = ["EUR", "GBP", "PLN", "CHF", "JPY", "CAD", "AUD"]


class ExchangeRateResponse(BaseModel):
    """Exchange rates response — all rates are relative to USD base."""
    base: str = "USD"
    rates: Dict[str, float]
    timestamp: str


def _fetch_exchange_rates() -> dict:
    """Fetch current exchange rates from frankfurter.app (ECB data, free, no API key).

    Requests USD-based rates for all supported display currencies.
    Always includes USD: 1.0 in the result so the frontend can treat
    USD like any other currency without special-casing.

    Returns:
        dict with keys: base, rates, timestamp
    """
    currencies = ",".join(_FX_CURRENCIES)
    url = f"https://api.frankfurter.app/latest?from=USD&to={currencies}"
    req = urllib.request.Request(url, headers={"User-Agent": "TickerTap/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())

    rates = data.get("rates", {})
    # Always include USD → USD at 1.0
    rates["USD"] = 1.0

    return {
        "base": "USD",
        "rates": rates,
        "timestamp": data.get("date", date.today().isoformat()),
    }


@router.get("/exchange-rates", response_model=ExchangeRateResponse)
async def get_exchange_rates(current_user=Depends(get_current_user)):
    """Return current exchange rates (USD base) for all supported currencies.

    Data is sourced from the European Central Bank via frankfurter.app
    and cached for 1 hour.  The ECB publishes rates once per business day
    around 16:00 CET, so more frequent fetching would be wasteful.
    """
    cache_key = "exchange_rates"
    cached = _get_cached(cache_key, _EXCHANGE_RATE_TTL)
    if cached:
        return cached

    try:
        result = await asyncio.to_thread(_fetch_exchange_rates)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not fetch exchange rates: {exc}",
        )

    _set_cached(cache_key, result)
    return result


# ── Fundamentals ──────────────────────────────────────────────────────────

_FUNDAMENTALS_TTL = 3600  # 1 hour — fundamental data changes infrequently


def _fetch_fundamentals(sym: str) -> dict:
    """Fetch fundamental data for a symbol from yfinance Ticker.info.

    Maps the yfinance info dict keys to FundamentalsResponse field names,
    using _safe_float for all numeric values to guard against NaN/Inf.
    String and integer fields are extracted with .get() defaults.

    Args:
        sym: Uppercase ticker symbol.

    Returns:
        A dict matching the FundamentalsResponse schema.
    """
    info = yf.Ticker(sym).info

    # ── Convert exDividendDate from epoch timestamp to ISO date string ──
    ex_div_date = None
    raw_ex_div = info.get("exDividendDate")
    if raw_ex_div is not None:
        try:
            # yfinance returns epoch seconds as int or float
            if isinstance(raw_ex_div, (int, float)):
                ex_div_date = datetime.fromtimestamp(raw_ex_div).date().isoformat()
            else:
                ex_div_date = str(raw_ex_div)
        except (OSError, ValueError, OverflowError):
            pass  # Malformed timestamp — leave as None

    # ── Convert earningsDate from epoch timestamp to ISO date string ────
    earnings_date = None
    raw_earnings = info.get("earningsDate")
    if raw_earnings is not None:
        try:
            if isinstance(raw_earnings, (int, float)):
                earnings_date = datetime.fromtimestamp(raw_earnings).date().isoformat()
            elif isinstance(raw_earnings, list) and raw_earnings:
                # yfinance sometimes returns a list of epoch timestamps
                first = raw_earnings[0]
                if isinstance(first, (int, float)):
                    earnings_date = datetime.fromtimestamp(first).date().isoformat()
                else:
                    earnings_date = str(first)
            else:
                earnings_date = str(raw_earnings)
        except (OSError, ValueError, OverflowError, IndexError):
            pass

    return {
        # Company info
        "symbol": sym,
        "name": info.get("longName") or info.get("shortName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "description": info.get("longBusinessSummary"),
        "website": info.get("website"),
        "country": info.get("country"),
        "employees": info.get("fullTimeEmployees"),
        "exchange": info.get("exchange"),
        "currency": info.get("currency"),

        # Current price (for analyst target range bar)
        "current_price": _safe_float(
            info.get("currentPrice") or info.get("regularMarketPrice"),
            default=None,
        ),

        # Valuation multiples
        "market_cap": _safe_float(info.get("marketCap"), default=None),
        "pe_ratio": _safe_float(info.get("trailingPE"), default=None),
        "forward_pe": _safe_float(info.get("forwardPE"), default=None),
        "peg_ratio": _safe_float(info.get("pegRatio"), default=None),
        "pb_ratio": _safe_float(info.get("priceToBook"), default=None),
        "ps_ratio": _safe_float(info.get("priceToSalesTrailing12Months"), default=None),
        "ev_to_ebitda": _safe_float(info.get("enterpriseToEbitda"), default=None),

        # Financial health
        "revenue": _safe_float(info.get("totalRevenue"), default=None),
        "net_income": _safe_float(info.get("netIncomeToCommon"), default=None),
        "profit_margin": _safe_float(info.get("profitMargins"), default=None),
        "operating_margin": _safe_float(info.get("operatingMargins"), default=None),
        "roe": _safe_float(info.get("returnOnEquity"), default=None),
        "roa": _safe_float(info.get("returnOnAssets"), default=None),
        "debt_to_equity": _safe_float(info.get("debtToEquity"), default=None),
        "current_ratio": _safe_float(info.get("currentRatio"), default=None),
        "free_cash_flow": _safe_float(info.get("freeCashflow"), default=None),

        # Dividends
        "dividend_yield": _safe_float(info.get("dividendYield"), default=None),
        "dividend_rate": _safe_float(info.get("dividendRate"), default=None),
        "payout_ratio": _safe_float(info.get("payoutRatio"), default=None),
        "ex_dividend_date": ex_div_date,

        # Analyst targets
        "target_low": _safe_float(info.get("targetLowPrice"), default=None),
        "target_mean": _safe_float(info.get("targetMeanPrice"), default=None),
        "target_high": _safe_float(info.get("targetHighPrice"), default=None),
        "target_median": _safe_float(info.get("targetMedianPrice"), default=None),
        "recommendation": info.get("recommendationKey"),
        "num_analysts": info.get("numberOfAnalystOpinions"),

        # Earnings
        "eps_trailing": _safe_float(info.get("trailingEps"), default=None),
        "eps_forward": _safe_float(info.get("forwardEps"), default=None),
        "earnings_date": earnings_date,

        # Trading info
        "beta": _safe_float(info.get("beta"), default=None),
        "fifty_two_week_high": _safe_float(info.get("fiftyTwoWeekHigh"), default=None),
        "fifty_two_week_low": _safe_float(info.get("fiftyTwoWeekLow"), default=None),
        "fifty_day_avg": _safe_float(info.get("fiftyDayAverage"), default=None),
        "two_hundred_day_avg": _safe_float(info.get("twoHundredDayAverage"), default=None),
        "avg_volume": _safe_float(info.get("averageVolume"), default=None),
        "shares_outstanding": _safe_float(info.get("sharesOutstanding"), default=None),
        "float_shares": _safe_float(info.get("floatShares"), default=None),
        "short_ratio": _safe_float(info.get("shortRatio"), default=None),
        "short_pct": _safe_float(info.get("shortPercentOfFloat"), default=None),
    }


@router.get("/fundamentals/{symbol}", response_model=FundamentalsResponse)
async def get_fundamentals(
    symbol: str,
    user=Depends(get_current_user),
):
    """Return fundamental data for a single security.

    Fetches company info, valuation multiples, financial health metrics,
    dividend data, analyst targets, earnings, and trading statistics from
    yfinance.  Results are cached for 1 hour.

    Args:
        symbol: Ticker symbol (case-insensitive).
        user:   Authenticated user (injected).

    Returns:
        FundamentalsResponse with all available fundamental fields.
    """
    sym = symbol.upper()
    cache_key = f"fundamentals:{sym}"
    cached = _get_cached(cache_key, _FUNDAMENTALS_TTL)
    if cached:
        return cached

    try:
        result = await asyncio.to_thread(_fetch_fundamentals, sym)
    except Exception as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Could not fetch fundamentals for '{sym}': {exc}",
        )

    _set_cached(cache_key, result)
    return result


# ── Financial events (earnings, dividends, splits, analyst targets) ──────────

def _fetch_events(sym: str) -> dict:
    """Fetch financial events and analyst target prices for a symbol.

    Collects earnings dates, dividend history, stock splits, and analyst
    consensus target prices from yfinance for a single ticker.  Each event
    is normalised into an ``EventItem``-compatible dict.

    Args:
        sym: Uppercase ticker symbol.

    Returns:
        A dict matching the ``EventsResponse`` schema with keys:
        symbol, events, target_mean, target_high, target_low.
    """
    ticker = yf.Ticker(sym)
    events: List[dict] = []

    # ── Earnings dates ─────────────────────────────────────────────────
    try:
        earnings_df = ticker.earnings_dates
        if earnings_df is not None and not earnings_df.empty:
            for dt, row in earnings_df.iterrows():
                date_str = dt.strftime("%Y-%m-%d")
                # EPS estimate may be present in the 'EPS Estimate' column
                eps = None
                if "EPS Estimate" in row.index:
                    raw = row["EPS Estimate"]
                    try:
                        val = float(raw)
                        if math.isfinite(val):
                            eps = val
                    except (TypeError, ValueError):
                        pass
                label = f"Earnings {date_str}"
                if eps is not None:
                    label = f"Earnings (est. ${eps:.2f} EPS)"
                events.append({
                    "date": date_str,
                    "type": "earnings",
                    "value": eps,
                    "label": label,
                })
    except Exception:
        pass

    # ── Dividends ──────────────────────────────────────────────────────
    try:
        divs = ticker.dividends
        if divs is not None and not divs.empty:
            for dt, amount in divs.items():
                date_str = dt.strftime("%Y-%m-%d")
                amt = round(_safe_float(amount), 4)
                events.append({
                    "date": date_str,
                    "type": "dividend",
                    "value": amt,
                    "label": f"${amt:.2f} dividend",
                })
    except Exception:
        pass

    # ── Stock splits ───────────────────────────────────────────────────
    try:
        splits = ticker.splits
        if splits is not None and not splits.empty:
            for dt, ratio in splits.items():
                date_str = dt.strftime("%Y-%m-%d")
                r = _safe_float(ratio)
                events.append({
                    "date": date_str,
                    "type": "split",
                    "value": r,
                    "label": f"{r:.0f}:1 split" if r >= 1 else f"1:{1/r:.0f} reverse split",
                })
    except Exception:
        pass

    # Sort events by date descending (most recent first)
    events.sort(key=lambda e: e["date"], reverse=True)

    # ── Analyst target prices ──────────────────────────────────────────
    target_mean = None
    target_high = None
    target_low = None
    try:
        info = ticker.info
        raw_mean = info.get("targetMeanPrice")
        raw_high = info.get("targetHighPrice")
        raw_low = info.get("targetLowPrice")
        if raw_mean is not None:
            target_mean = round(_safe_float(raw_mean), 2) or None
        if raw_high is not None:
            target_high = round(_safe_float(raw_high), 2) or None
        if raw_low is not None:
            target_low = round(_safe_float(raw_low), 2) or None
    except Exception:
        pass

    return {
        "symbol": sym,
        "events": events,
        "target_mean": target_mean,
        "target_high": target_high,
        "target_low": target_low,
    }


@router.get("/events/{symbol}", response_model=EventsResponse)
async def get_events(
    symbol: str,
    current_user=Depends(get_current_user),
):
    """Return financial events and analyst target prices for a symbol.

    Events include earnings dates (past and upcoming), dividend payments,
    and stock splits.  Analyst consensus target prices (mean, high, low)
    are included when available.  Results are cached for 1 hour.

    Args:
        symbol:       Ticker symbol (case-insensitive).
        current_user: Authenticated user (injected).

    Returns:
        EventsResponse with events list and optional analyst targets.
    """
    sym = symbol.upper()
    cache_key = f"events:{sym}"
    cached = _get_cached(cache_key, _EVENTS_TTL)
    if cached:
        return cached

    try:
        result = await asyncio.to_thread(_fetch_events, sym)
    except Exception as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Could not fetch events for '{sym}': {exc}",
        )

    _set_cached(cache_key, result)
    return result


# ── Sector analysis ──────────────────────────────────────────────────────

# Sector ETF tickers mapped to human-readable sector names.
# Each ETF is a SPDR Select Sector Fund that tracks one GICS sector.
_SECTOR_ETFS = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLV": "Health Care",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLE": "Energy",
    "XLI": "Industrials",
    "XLB": "Materials",
    "XLRE": "Real Estate",
    "XLU": "Utilities",
    "XLC": "Communication",
}

# Mapping from display names (GICS/SPDR) to yfinance sector taxonomy.
# yfinance uses its own naming convention that differs from GICS for 6 sectors.
# Used by the screener to translate the incoming sector filter parameter.
_SECTOR_DISPLAY_TO_YF = {
    "financials":             "financial services",
    "health care":            "healthcare",
    "consumer discretionary": "consumer cyclical",
    "consumer staples":       "consumer defensive",
    "materials":              "basic materials",
    "communication":          "communication services",
}

_SECTOR_TTL = 300  # 5 minutes


def _fetch_sector_etf(sym: str, name: str) -> Optional[dict]:
    """Fetch performance data for a single sector ETF.

    Retrieves the current price, daily change%, YTD return%, and 1-month
    return% by downloading recent history from yfinance.

    Args:
        sym:  ETF ticker symbol (e.g. "XLK").
        name: Human-readable sector name (e.g. "Technology").

    Returns:
        A dict matching the SectorItem schema, or None on failure.
    """
    try:
        ticker = yf.Ticker(sym)
        fi = ticker.fast_info

        price = round(_safe_float(fi.last_price), 2)
        prev_close = _safe_float(fi.regular_market_previous_close)
        change_pct = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0.0

        # YTD performance: compare current price to the first close of the year
        ytd_pct = None
        try:
            year_start = date.today().replace(month=1, day=1).strftime("%Y-%m-%d")
            ytd_hist = ticker.history(start=year_start, auto_adjust=True)
            if len(ytd_hist) >= 2:
                first_close = _safe_float(ytd_hist.iloc[0]["Close"])
                if first_close > 0:
                    ytd_pct = round((price - first_close) / first_close * 100, 2)
        except Exception:
            pass

        # 1-month performance: compare current price to the close ~21 trading days ago
        month_pct = None
        try:
            month_start = (date.today() - timedelta(days=35)).strftime("%Y-%m-%d")
            month_hist = ticker.history(start=month_start, auto_adjust=True)
            if len(month_hist) >= 2:
                first_close = _safe_float(month_hist.iloc[0]["Close"])
                if first_close > 0:
                    month_pct = round((price - first_close) / first_close * 100, 2)
        except Exception:
            pass

        return {
            "symbol": sym,
            "name": name,
            "price": price,
            "change_pct": change_pct,
            "ytd_pct": ytd_pct,
            "month_pct": month_pct,
        }
    except Exception:
        return None


@router.get("/sectors", response_model=SectorResponse)
async def get_sectors(current_user=Depends(get_current_user)):
    """Return sector performance overview using sector ETFs as proxies.

    Fetches current price, daily change%, YTD%, and 1-month% for each
    GICS sector ETF.  All yfinance calls run in parallel via
    asyncio.gather + to_thread.  Results are cached for 5 minutes and
    returned sorted by daily change% (descending).

    Args:
        current_user: Authenticated user (injected by dependency).

    Returns:
        SectorResponse with a list of SectorItem objects.
    """
    cache_key = "sectors_overview"
    cached = _get_cached(cache_key, _SECTOR_TTL)
    if cached:
        return cached

    # Fetch all sector ETFs in parallel — each call runs in a thread
    # to avoid blocking the event loop (yfinance is synchronous).
    tasks = [
        asyncio.to_thread(_fetch_sector_etf, sym, name)
        for sym, name in _SECTOR_ETFS.items()
    ]
    results = await asyncio.gather(*tasks)

    # Filter out failed fetches and sort by daily change% descending
    sectors = [r for r in results if r is not None]
    sectors.sort(key=lambda s: s["change_pct"], reverse=True)

    response = {"sectors": sectors}
    _set_cached(cache_key, response)
    return response


# ── Stock screener ───────────────────────────────────────────────────────

# Universe of ~100 popular tickers (S&P 500 top components + growth/meme
# stocks) used as the screening pool.  yf.download() batch-fetches them
# in a single HTTP call for speed.
_SCREENER_UNIVERSE = [
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "BRK-B",
    "UNH", "JNJ", "JPM", "V", "PG", "XOM", "HD", "MA", "CVX", "MRK",
    "ABBV", "LLY", "PEP", "KO", "COST", "AVGO", "WMT", "MCD", "CSCO",
    "TMO", "ABT", "CRM", "ACN", "DHR", "NKE", "ADBE", "TXN", "NEE",
    "PM", "UNP", "BMY", "RTX", "AMGN", "LOW", "HON", "QCOM", "IBM",
    "SBUX", "CAT", "BA", "GE", "INTC", "AMD", "PYPL", "DIS", "NFLX",
    "GILD", "BLK", "ISRG", "SYK", "MDT", "PLD", "ADP", "VRTX", "REGN",
    "ZTS", "CI", "MMC", "SO", "DUK", "CB", "CL", "CME", "APD", "TGT",
    "FDX", "EMR", "PSA", "NSC", "PNC", "USB", "AIG", "GM", "F",
    "RIVN", "PLTR", "SOFI", "COIN", "MARA", "SQ", "SNAP", "ROKU",
    "DKNG", "ABNB", "UBER", "LYFT", "RBLX", "U", "HOOD", "AFRM",
    "PATH", "NET", "CRWD", "DDOG", "ZS", "SNOW",
]

_SCREENER_TTL = 300  # 5 minutes

# Valid sort fields for the screener endpoint
_SCREENER_SORT_FIELDS = {"change_pct", "volume", "price", "market_cap"}


def _fetch_screener_data() -> List[dict]:
    """Batch-download latest price data for the screener universe.

    Uses yf.download() with group_by='ticker' to fetch 5 days of OHLCV
    data for all tickers in a single request.  Extracts the most recent
    day's data (price, change, volume) and augments each ticker with
    company name, market cap, and sector from yf.Ticker().info (cached
    via _resolve_name and the name cache).

    Returns:
        A list of dicts matching the ScreenerItem schema.
    """
    tickers_str = " ".join(_SCREENER_UNIVERSE)

    # Batch download 3 months of daily data — enough to compute SMA50
    # and daily change even if the most recent day has partial data.
    df = yf.download(tickers_str, period="3mo", group_by="ticker", progress=False)

    items: List[dict] = []
    for sym in _SCREENER_UNIVERSE:
        try:
            # Extract the per-ticker slice from the multi-level DataFrame
            if sym not in df.columns.get_level_values(0):
                continue
            ticker_df = df[sym].dropna(subset=["Close"])
            if len(ticker_df) < 2:
                continue

            # Latest and previous close for daily change calculation
            latest = ticker_df.iloc[-1]
            prev = ticker_df.iloc[-2]

            price = round(_safe_float(latest["Close"]), 2)
            prev_close = _safe_float(prev["Close"])
            change = round(price - prev_close, 2) if prev_close else 0.0
            change_pct = round(change / prev_close * 100, 2) if prev_close else 0.0
            volume = int(_safe_float(latest["Volume"]))

            # Compute 50-day SMA from available close prices
            closes = ticker_df["Close"].values
            sma50 = round(float(closes[-50:].mean()), 2) if len(closes) >= 50 else None

            # Resolve name from the long-lived name cache (avoids slow .info calls
            # on subsequent requests).
            ticker_obj = yf.Ticker(sym)
            name = _resolve_name(ticker_obj, sym)

            # Fetch market cap from fast_info
            market_cap = None
            try:
                fi = ticker_obj.fast_info
                mc = _safe_float(fi.market_cap, default=None)
                if mc and mc > 0:
                    market_cap = mc
            except Exception:
                pass

            # Sector lookup — use a dedicated cache to avoid repeated .info calls
            sector = None
            sector_cache_key = f"sector:{sym}"
            cached_sector = _get_cached(sector_cache_key, _NAME_TTL)
            if cached_sector is not None:
                sector = cached_sector
            else:
                try:
                    info = ticker_obj.info
                    sector = info.get("sector")
                    _set_cached(sector_cache_key, sector)
                except Exception:
                    _set_cached(sector_cache_key, None)

            items.append({
                "symbol": sym,
                "name": name,
                "price": price,
                "change": change,
                "change_pct": change_pct,
                "volume": volume,
                "market_cap": market_cap,
                "sector": sector,
                "sma50": sma50,
            })
        except Exception:
            continue  # Skip tickers that fail to parse

    return items


@router.get("/screener", response_model=ScreenerResponse)
async def run_screener(
    min_price: Optional[float] = Query(None, description="Minimum price filter"),
    max_price: Optional[float] = Query(None, description="Maximum price filter"),
    min_change_pct: Optional[float] = Query(None, description="Minimum daily change %"),
    max_change_pct: Optional[float] = Query(None, description="Maximum daily change %"),
    min_volume: Optional[int] = Query(None, description="Minimum trading volume"),
    sector: Optional[str] = Query(None, description="Filter by sector name"),
    above_sma50: Optional[bool] = Query(None, description="Only show stocks trading above their 50-day SMA"),
    sort_by: str = Query("change_pct", description="Sort field: change_pct, volume, price, market_cap"),
    sort_dir: str = Query("desc", description="Sort direction: asc or desc"),
    limit: int = Query(25, ge=1, le=50, description="Max results to return"),
    current_user=Depends(get_current_user),
):
    """Run a stock screener with optional filters over ~100 popular tickers.

    Applies price, change%, volume, and sector filters to a pre-downloaded
    universe of S&P 500 top components.  Results are sorted by the chosen
    field and truncated to the requested limit.  The full screener data is
    batch-downloaded via yf.download() and cached for 5 minutes.

    Args:
        min_price:      Exclude stocks below this price.
        max_price:      Exclude stocks above this price.
        min_change_pct: Exclude stocks with daily change% below this.
        max_change_pct: Exclude stocks with daily change% above this.
        min_volume:     Exclude stocks with volume below this.
        sector:         Only include stocks in this GICS sector.
        sort_by:        Sort column (change_pct, volume, price, market_cap).
        sort_dir:       Sort direction (asc or desc).
        limit:          Maximum number of results (1-50, default 25).
        current_user:   Authenticated user (injected by dependency).

    Returns:
        ScreenerResponse with filtered/sorted results, total match count,
        and a dict of which filters were applied.
    """
    # Validate sort parameters
    if sort_by not in _SCREENER_SORT_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort_by '{sort_by}'. Valid: {list(_SCREENER_SORT_FIELDS)}",
        )
    if sort_dir not in ("asc", "desc"):
        raise HTTPException(status_code=400, detail="sort_dir must be 'asc' or 'desc'.")

    # Fetch or retrieve cached screener data (the expensive batch download)
    cache_key = "screener_universe"
    items = _get_cached(cache_key, _SCREENER_TTL)
    if items is None:
        try:
            items = await asyncio.to_thread(_fetch_screener_data)
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Screener data fetch failed: {exc}",
            )
        _set_cached(cache_key, items)

    # Build a record of which filters were actually applied (for the response)
    filters_applied: Dict[str, object] = {}

    # Apply filters — each guard only runs if the parameter was provided
    filtered = list(items)

    if min_price is not None:
        filters_applied["min_price"] = min_price
        filtered = [s for s in filtered if s["price"] >= min_price]

    if max_price is not None:
        filters_applied["max_price"] = max_price
        filtered = [s for s in filtered if s["price"] <= max_price]

    if min_change_pct is not None:
        filters_applied["min_change_pct"] = min_change_pct
        filtered = [s for s in filtered if s["change_pct"] >= min_change_pct]

    if max_change_pct is not None:
        filters_applied["max_change_pct"] = max_change_pct
        filtered = [s for s in filtered if s["change_pct"] <= max_change_pct]

    if min_volume is not None:
        filters_applied["min_volume"] = min_volume
        filtered = [s for s in filtered if s["volume"] >= min_volume]

    if sector is not None:
        filters_applied["sector"] = sector
        # Translate GICS/SPDR display name to yfinance taxonomy if needed
        sector_lower = sector.lower()
        yf_sector = _SECTOR_DISPLAY_TO_YF.get(sector_lower, sector_lower)
        filtered = [s for s in filtered if s.get("sector") and s["sector"].lower() == yf_sector]

    if above_sma50 is not None:
        filters_applied["above_sma50"] = above_sma50
        # Keep only stocks whose price is above (or below) their 50-day SMA
        if above_sma50:
            filtered = [s for s in filtered if s.get("sma50") and s["price"] > s["sma50"]]
        else:
            filtered = [s for s in filtered if s.get("sma50") and s["price"] <= s["sma50"]]

    total_matched = len(filtered)

    # Sort — use 0 as default for None values (market_cap can be None)
    reverse = sort_dir == "desc"
    filtered.sort(key=lambda s: s.get(sort_by) or 0, reverse=reverse)

    # Truncate to requested limit
    filtered = filtered[:limit]

    return {
        "results": filtered,
        "total_matched": total_matched,
        "filters_applied": filters_applied,
    }
