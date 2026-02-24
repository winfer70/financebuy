import asyncio
import json
import time
import urllib.request
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import yfinance as yf
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..dependencies import get_current_user

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

def _fetch_quote(sym: str) -> QuoteOut:
    ticker = yf.Ticker(sym)
    fi = ticker.fast_info

    # Use fast_info for real-time quote data (faster and more reliable than
    # history() which can intermittently return empty/stale data).
    price = round(float(fi.last_price), 2)
    prev_close = round(float(fi.regular_market_previous_close), 2)
    open_price = round(float(fi.open), 2)
    high = round(float(fi.day_high), 2)
    low = round(float(fi.day_low), 2)
    volume = int(fi.last_volume)

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
            open=round(float(row["Open"]), 2),
            high=round(float(row["High"]), 2),
            low=round(float(row["Low"]), 2),
            close=round(float(row["Close"]), 2),
            volume=volume,
            is_earnings=False,
        ))
    return OHLCVResponse(
        bars=bars,
        volume_source=etf_sym if etf_vol else None,
    )


def _fetch_symbols_info() -> List[dict]:
    results = []
    for sym in _DEFAULT_SYMBOLS:
        try:
            ticker = yf.Ticker(sym)
            fi = ticker.fast_info
            price = round(float(fi.last_price), 2)
            name = _resolve_name(ticker, sym)
            results.append({"symbol": sym, "name": name, "price": price})
        except Exception:
            continue
    return results


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/quote/{symbol}", response_model=QuoteOut)
async def get_quote(symbol: str, current_user: str = Depends(get_current_user)):
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
                    current_user: str = Depends(get_current_user)):
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


@router.get("/symbols", response_model=List[dict])
async def list_symbols(current_user: str = Depends(get_current_user)):
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
    current_user: str = Depends(get_current_user),
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
