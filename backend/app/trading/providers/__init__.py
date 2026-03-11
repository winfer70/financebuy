"""
Market Data Provider — Abstract interface and data types.

Defines the ``MarketDataProvider`` ABC that every data source adapter must
implement, plus the normalised ``OHLCVBar`` / ``Quote`` / ``SymbolInfo``
dataclasses that the rest of the trading engine consumes.

Role in the project:
  routes/market.py  →  raw yfinance calls  (user-facing quotes / charts)
  trading/providers  →  normalised pipeline  (strategy engine consumption)
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Normalised data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OHLCVBar:
    """Single OHLCV candle in normalised form.

    Fields:
        timestamp: Bar open time (UTC-aware).
        open:      Opening price.
        high:      Highest price during the bar.
        low:       Lowest price during the bar.
        close:     Closing price.
        volume:    Volume traded during the bar.
    """
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Quote:
    """Real-time (or last-available) quote snapshot.

    Fields:
        symbol:     Ticker symbol (upper-case).
        price:      Latest trade price.
        change:     Absolute price change from previous close.
        change_pct: Percentage change from previous close.
        volume:     Cumulative session volume.
        timestamp:  Time of the snapshot.
    """
    symbol: str
    price: float
    change: float
    change_pct: float
    volume: float
    timestamp: datetime


@dataclass(frozen=True)
class SymbolInfo:
    """Minimal symbol metadata returned by search.

    Fields:
        symbol:    Ticker symbol (upper-case).
        name:      Human-readable company / asset name.
        exchange:  Exchange identifier (e.g. "NMS", "NYQ").
        asset_type: Category string (e.g. "EQUITY", "ETF", "CRYPTO").
    """
    symbol: str
    name: str
    exchange: str = ""
    asset_type: str = ""


# ---------------------------------------------------------------------------
# Abstract provider
# ---------------------------------------------------------------------------

class MarketDataProvider(abc.ABC):
    """Abstract interface that every market-data adapter must implement.

    Concrete subclasses (e.g. ``YFinanceProvider``) translate vendor-specific
    responses into the normalised types above so that the strategy engine and
    normalizer never depend on a particular vendor SDK.
    """

    @abc.abstractmethod
    async def get_ohlcv(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> List[OHLCVBar]:
        """Fetch OHLCV bars for *symbol* at the given *interval*.

        Args:
            symbol:   Ticker symbol (upper-case).
            interval: Bar interval string (e.g. ``"1d"``, ``"1h"``).
            start:    Inclusive start datetime (UTC).
            end:      Inclusive end datetime (UTC).

        Returns:
            Chronologically ordered list of ``OHLCVBar``.
        """
        ...

    @abc.abstractmethod
    async def get_quote(self, symbol: str) -> Quote:
        """Fetch the latest quote for *symbol*.

        Args:
            symbol: Ticker symbol (upper-case).

        Returns:
            ``Quote`` snapshot.
        """
        ...

    @abc.abstractmethod
    async def search(self, query: str) -> List[SymbolInfo]:
        """Search for symbols matching *query*.

        Args:
            query: Free-text search string.

        Returns:
            List of matching ``SymbolInfo`` results.
        """
        ...

    @abc.abstractmethod
    def get_supported_intervals(self) -> List[str]:
        """Return the list of bar intervals this provider supports.

        Returns:
            e.g. ``["1m", "5m", "15m", "1h", "1d", "1wk", "1mo"]``
        """
        ...

    @abc.abstractmethod
    def get_max_history(self, interval: str) -> timedelta:
        """Return the maximum historical lookback for *interval*.

        Args:
            interval: Bar interval string.

        Returns:
            ``timedelta`` representing how far back data is available.
        """
        ...
