"""
YFinance Provider — MarketDataProvider implementation backed by yfinance.

Wraps the yfinance SDK behind the ``MarketDataProvider`` interface so the
trading engine consumes normalised ``OHLCVBar`` / ``Quote`` objects and
never imports yfinance directly.

Reuses the in-memory cache TTL strategy and ``_safe_float`` sanitiser
pattern established in ``routes/market.py``.

Data flow:
    BacktestEngine / NormalizedDataService
        → YFinanceProvider.get_ohlcv(...)
            → yf.Ticker(...).history(...)   (sync, via asyncio.to_thread)
            → Normalised OHLCVBar list
"""

from __future__ import annotations

import asyncio
import math
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import yfinance as yf

from . import MarketDataProvider, OHLCVBar, Quote, SymbolInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(value, default: float = 0.0) -> float:
    """Sanitize a numeric value from yfinance (NaN / Inf → default).

    Args:
        value:   Raw numeric from yfinance fast_info or history DataFrame.
        default: Fallback value for non-finite inputs.

    Returns:
        Finite float safe for JSON serialisation and arithmetic.
    """
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) else default


# -- In-memory cache (same pattern as routes/market.py) --------------------

_cache: Dict[str, Tuple[float, object]] = {}
_OHLCV_TTL = 300        # 5 minutes
_QUOTE_TTL_OPEN = 3     # seconds — market open
_QUOTE_TTL_CLOSED = 300  # seconds — market closed
_SEARCH_TTL = 300        # 5 minutes

def _get_cached(key: str, ttl: float) -> Optional[object]:
    """Return cached value if still fresh, else ``None``."""
    entry = _cache.get(key)
    if entry and (time.time() - entry[0]) < ttl:
        return entry[1]
    return None

def _set_cached(key: str, value: object) -> None:
    """Store *value* in the in-memory cache with a fresh timestamp."""
    _cache[key] = (time.time(), value)


# -- Interval mapping (yfinance native interval, max lookback days) --------

_INTERVAL_SUPPORT: Dict[str, Tuple[str, Optional[int]]] = {
    "1m":  ("1m",  7),
    "2m":  ("2m",  60),
    "5m":  ("5m",  60),
    "15m": ("15m", 60),
    "30m": ("30m", 60),
    "1h":  ("60m", 730),
    "1d":  ("1d",  None),
    "1wk": ("1wk", None),
    "1mo": ("1mo", None),
}


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class YFinanceProvider(MarketDataProvider):
    """Market data adapter backed by the **yfinance** library.

    All synchronous yfinance calls are executed via ``asyncio.to_thread``
    so they do not block the async event loop.
    """

    # -- MarketDataProvider interface ----------------------------------------

    async def get_ohlcv(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> List[OHLCVBar]:
        """Fetch OHLCV bars from yfinance and return normalised OHLCVBars.

        Args:
            symbol:   Ticker symbol (upper-case).
            interval: Candle interval (e.g. ``"1d"``, ``"1h"``).
            start:    Inclusive start datetime.
            end:      Inclusive end datetime.

        Returns:
            Chronologically ordered list of ``OHLCVBar``.

        Raises:
            ValueError: If *interval* is not supported.
        """
        sym = symbol.upper()
        if interval not in _INTERVAL_SUPPORT:
            raise ValueError(
                f"Unsupported interval '{interval}'. "
                f"Valid: {list(_INTERVAL_SUPPORT.keys())}"
            )

        cache_key = f"provider:ohlcv:{sym}:{interval}:{start.date()}:{end.date()}"
        cached = _get_cached(cache_key, _OHLCV_TTL)
        if cached is not None:
            return cached

        yf_interval = _INTERVAL_SUPPORT[interval][0]
        bars = await asyncio.to_thread(
            self._fetch_ohlcv_sync, sym, yf_interval, start, end,
        )
        _set_cached(cache_key, bars)
        return bars

    async def get_quote(self, symbol: str) -> Quote:
        """Fetch the latest quote for *symbol* from yfinance.

        Args:
            symbol: Ticker symbol (upper-case).

        Returns:
            Normalised ``Quote`` snapshot.
        """
        sym = symbol.upper()
        ttl = _QUOTE_TTL_OPEN if self._is_market_open() else _QUOTE_TTL_CLOSED
        cache_key = f"provider:quote:{sym}"
        cached = _get_cached(cache_key, ttl)
        if cached is not None:
            return cached

        quote = await asyncio.to_thread(self._fetch_quote_sync, sym)
        _set_cached(cache_key, quote)
        return quote

    async def search(self, query: str) -> List[SymbolInfo]:
        """Search for symbols matching *query* via yfinance.

        Args:
            query: Free-text search string.

        Returns:
            List of ``SymbolInfo`` results.
        """
        cache_key = f"provider:search:{query}"
        cached = _get_cached(cache_key, _SEARCH_TTL)
        if cached is not None:
            return cached

        results = await asyncio.to_thread(self._search_sync, query)
        _set_cached(cache_key, results)
        return results

    def get_supported_intervals(self) -> List[str]:
        """Return the list of candle intervals this provider supports.

        Returns:
            Sorted list of interval strings.
        """
        return sorted(_INTERVAL_SUPPORT.keys(), key=self._interval_sort_key)

    def get_max_history(self, interval: str) -> timedelta:
        """Return maximum lookback for *interval*.

        Args:
            interval: Candle interval string.

        Returns:
            ``timedelta`` of maximum lookback, or 10 years for unlimited.

        Raises:
            ValueError: If *interval* is not supported.
        """
        if interval not in _INTERVAL_SUPPORT:
            raise ValueError(f"Unsupported interval '{interval}'.")
        max_days = _INTERVAL_SUPPORT[interval][1]
        return timedelta(days=max_days) if max_days else timedelta(days=3650)

    # -- Synchronous yfinance calls (run via asyncio.to_thread) -------------

    def _fetch_ohlcv_sync(
        self,
        sym: str,
        yf_interval: str,
        start: datetime,
        end: datetime,
    ) -> List[OHLCVBar]:
        """Synchronous OHLCV fetch from yfinance.

        Args:
            sym:         Upper-case ticker symbol.
            yf_interval: Native yfinance interval string (e.g. ``"1d"``).
            start:       Inclusive start datetime.
            end:         Inclusive end datetime.

        Returns:
            List of ``OHLCVBar`` in chronological order.
        """
        ticker = yf.Ticker(sym)
        df = ticker.history(
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval=yf_interval,
            auto_adjust=True,
        )
        if df is None or df.empty:
            return []

        bars: List[OHLCVBar] = []
        for idx, row in df.iterrows():
            ts = idx.to_pydatetime()
            bars.append(OHLCVBar(
                timestamp=ts,
                open=round(_safe_float(row["Open"]), 4),
                high=round(_safe_float(row["High"]), 4),
                low=round(_safe_float(row["Low"]), 4),
                close=round(_safe_float(row["Close"]), 4),
                volume=round(_safe_float(row.get("Volume", 0))),
            ))
        return bars

    def _fetch_quote_sync(self, sym: str) -> Quote:
        """Synchronous quote fetch from yfinance.

        Args:
            sym: Upper-case ticker symbol.

        Returns:
            Normalised ``Quote`` object.
        """
        ticker = yf.Ticker(sym)
        fi = ticker.fast_info
        price = round(_safe_float(fi.last_price), 4)
        prev = round(_safe_float(fi.regular_market_previous_close), 4)
        chg = round(price - prev, 4)
        chg_pct = round(chg / prev * 100, 2) if prev else 0.0
        vol = round(_safe_float(fi.last_volume))

        return Quote(
            symbol=sym,
            price=price,
            change=chg,
            change_pct=chg_pct,
            volume=vol,
            timestamp=datetime.utcnow(),
        )

    def _search_sync(self, query: str) -> List[SymbolInfo]:
        """Synchronous symbol search via yfinance.

        Args:
            query: Free-text search string.

        Returns:
            List of ``SymbolInfo`` results.
        """
        try:
            results = yf.Tickers(query)
            # yfinance search returns a dict of Ticker objects
            # Use the Yahoo Finance search endpoint instead
            import json
            import urllib.request
            url = (
                "https://query2.finance.yahoo.com/v1/finance/search"
                f"?q={query}&quotesCount=10&newsCount=0"
            )
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
            return [
                SymbolInfo(
                    symbol=q.get("symbol", ""),
                    name=q.get("shortname", q.get("longname", "")),
                    exchange=q.get("exchange", ""),
                    asset_type=q.get("quoteType", ""),
                )
                for q in data.get("quotes", [])
            ]
        except Exception:
            return []

    # -- Internal helpers ---------------------------------------------------

    @staticmethod
    def _is_market_open() -> bool:
        """Check if NYSE is in regular trading hours."""
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("America/New_York"))
        if now.weekday() >= 5:
            return False
        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
        return market_open <= now < market_close

    @staticmethod
    def _interval_sort_key(interval: str) -> int:
        """Return a numeric sort key so intervals order from shortest to longest."""
        order = {
            "1m": 1, "2m": 2, "5m": 3, "15m": 4, "30m": 5,
            "1h": 6, "1d": 7, "1wk": 8, "1mo": 9,
        }
        return order.get(interval, 99)
