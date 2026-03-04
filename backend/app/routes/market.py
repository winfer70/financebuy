import asyncio
import json
import math
import time
import urllib.request
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import yfinance as yf
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

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


# ── In-memory cache ──────────────────────────────────────────────────────────
_cache: Dict[str, Tuple[float, object]] = {}

_QUOTE_TTL_OPEN = 3       # seconds — market open
_QUOTE_TTL_CLOSED = 300   # 5 minutes — market closed
_OHLCV_TTL = 300          # 5 minutes
_SYMBOLS_TTL = 3600       # 1 hour

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
    ticker = yf.Ticker(sym)
    period = f"{years}y" if years <= 5 else "max"
    hist = ticker.history(period=period, auto_adjust=True)
    if hist.empty:
        raise ValueError(f"No OHLCV data for {sym}")

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
            is_earnings=False,
        ))
    return OHLCVResponse(
        bars=bars,
        volume_source=etf_sym if etf_vol else None,
    )


def _fetch_ohlcv_interval(sym: str, interval: str, days: int) -> OHLCVResponse:
    """Fetch OHLCV data for a symbol at a specific interval.

    Uses the _INTERVAL_MAP to resolve yfinance base interval and aggregation
    factor.  Clamps `days` to the maximum allowed by yfinance for intraday
    intervals and returns a warning when clamped.
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
        else:
            date_str = dt.strftime("%Y-%m-%d")
        volume = etf_vol.get(date_str, int(row["Volume"])) if etf_vol else int(row["Volume"])
        bars.append(
            OHLCVBar(
                date=date_str,
                open=round(_safe_float(row["Open"]), 2),
                high=round(_safe_float(row["High"]), 2),
                low=round(_safe_float(row["Low"]), 2),
                close=round(_safe_float(row["Close"]), 2),
                volume=volume,
                is_earnings=False,
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

    results: List[QuoteOut] = []
    for sym in sym_list:
        cache_key = f"quote:{sym}"
        cached = _get_cached(cache_key, _quote_ttl())
        if cached:
            results.append(cached)
            continue
        try:
            quote = await asyncio.to_thread(_fetch_quote, sym)
            _set_cached(cache_key, quote)
            results.append(quote)
        except Exception:
            pass  # Skip symbols that can't be fetched
    return results


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

    Fetches history from (today - period_days) to today and computes:
        change_pct = (last_close - first_close) / first_close * 100

    Returns 0.0 if insufficient data is available.
    """
    days = _PERIOD_DAYS_MAP[period]
    start = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    hist = yf.Ticker(sym).history(start=start, auto_adjust=True)
    if len(hist) < 2:
        return {"symbol": sym, "period": period, "change_pct": 0.0}
    first_close = _safe_float(hist.iloc[0]["Close"])
    last_close = _safe_float(hist.iloc[-1]["Close"])
    if first_close == 0:
        return {"symbol": sym, "period": period, "change_pct": 0.0}
    change_pct = round((last_close - first_close) / first_close * 100, 2)
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
