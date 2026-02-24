import asyncio
import json
import time
import urllib.request
from typing import Dict, List, Optional, Tuple

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

_QUOTE_TTL = 60        # seconds
_OHLCV_TTL = 300       # 5 minutes
_SYMBOLS_TTL = 3600    # 1 hour

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


# ── yfinance helpers (synchronous — called via asyncio.to_thread) ────────────

def _fetch_quote(sym: str) -> QuoteOut:
    ticker = yf.Ticker(sym)
    info = ticker.fast_info
    hist = ticker.history(period="2d")
    if hist.empty or len(hist) < 1:
        raise ValueError(f"No data for {sym}")

    last_row = hist.iloc[-1]
    prev_close = hist.iloc[-2]["Close"] if len(hist) >= 2 else last_row["Close"]
    price = float(last_row["Close"])
    chg = round(price - float(prev_close), 2)
    chg_pct = round(chg / float(prev_close) * 100, 2) if prev_close else 0.0

    name = getattr(info, "long_name", None) or sym
    # fast_info may not have long_name; fall back to the ticker info dict
    if name == sym:
        try:
            full_info = ticker.info
            name = full_info.get("longName") or full_info.get("shortName") or sym
        except Exception:
            pass

    return QuoteOut(
        symbol=sym,
        name=name,
        price=price,
        open=float(last_row["Open"]),
        high=float(last_row["High"]),
        low=float(last_row["Low"]),
        prev_close=round(float(prev_close), 2),
        volume=int(last_row["Volume"]),
        change=chg,
        change_pct=chg_pct,
    )


def _fetch_ohlcv(sym: str, years: int) -> List[OHLCVBar]:
    ticker = yf.Ticker(sym)
    period = f"{years}y" if years <= 5 else "max"
    hist = ticker.history(period=period, auto_adjust=True)
    if hist.empty:
        raise ValueError(f"No OHLCV data for {sym}")

    bars: List[OHLCVBar] = []
    for dt, row in hist.iterrows():
        bars.append(OHLCVBar(
            date=dt.strftime("%Y-%m-%d"),
            open=round(float(row["Open"]), 2),
            high=round(float(row["High"]), 2),
            low=round(float(row["Low"]), 2),
            close=round(float(row["Close"]), 2),
            volume=int(row["Volume"]),
            is_earnings=False,
        ))
    return bars


def _fetch_symbols_info() -> List[dict]:
    results = []
    for sym in _DEFAULT_SYMBOLS:
        try:
            ticker = yf.Ticker(sym)
            hist = ticker.history(period="1d")
            if hist.empty:
                continue
            price = float(hist.iloc[-1]["Close"])
            name = sym
            try:
                fi = ticker.fast_info
                name = getattr(fi, "long_name", None) or sym
                if name == sym:
                    full_info = ticker.info
                    name = full_info.get("longName") or full_info.get("shortName") or sym
            except Exception:
                pass
            results.append({"symbol": sym, "name": name, "price": round(price, 2)})
        except Exception:
            continue
    return results


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/quote/{symbol}", response_model=QuoteOut)
async def get_quote(symbol: str, current_user: str = Depends(get_current_user)):
    sym = symbol.upper()
    cache_key = f"quote:{sym}"
    cached = _get_cached(cache_key, _QUOTE_TTL)
    if cached:
        return cached

    try:
        quote = await asyncio.to_thread(_fetch_quote, sym)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Could not fetch quote for '{sym}': {exc}")

    _set_cached(cache_key, quote)
    return quote


@router.get("/ohlcv/{symbol}", response_model=List[OHLCVBar])
async def get_ohlcv(symbol: str, years: int = Query(default=5, ge=1, le=10),
                    current_user: str = Depends(get_current_user)):
    sym = symbol.upper()
    cache_key = f"ohlcv:{sym}:{years}"
    cached = _get_cached(cache_key, _OHLCV_TTL)
    if cached:
        return cached

    try:
        bars = await asyncio.to_thread(_fetch_ohlcv, sym, years)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Could not fetch OHLCV for '{sym}': {exc}")

    _set_cached(cache_key, bars)
    return bars


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
