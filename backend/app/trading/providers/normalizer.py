"""
Normalized Data Service — single entry point for strategy data consumption.

Sits between the ``MarketDataProvider`` adapters and the trading engine.
Strategies and the backtest engine call *only* this service — never a
provider directly.  This guarantees:

  1. All OHLCV data has a consistent shape regardless of the upstream source.
  2. Swapping providers (yfinance → Polygon.io) requires zero strategy changes.
  3. Multi-timeframe alignment reads from the TimescaleDB hypertable for
     intraday intervals (1m, 5m) and falls back to the provider for daily+.

Data flow:
    BacktestEngine → NormalizedDataService.get_bars(...)
                        → provider.get_ohlcv(...)  OR  hypertable read
                        → validated, sorted OHLCVBar list
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from . import MarketDataProvider, OHLCVBar, Quote


# Intraday intervals that live in the TimescaleDB hypertable
_HYPERTABLE_INTERVALS = {"1m", "5m", "15m", "1h"}


class NormalizedDataService:
    """Facade that strategies and the backtest engine use for market data.

    Accepts a concrete ``MarketDataProvider`` at construction time and
    delegates all fetches through it, adding validation and normalisation.
    Optionally accepts an ``AsyncSession`` factory for hypertable reads.

    Args:
        provider:        A concrete ``MarketDataProvider`` instance.
        session_factory: Optional async session factory for DB reads.
    """

    def __init__(
        self,
        provider: MarketDataProvider,
        session_factory=None,
    ) -> None:
        self._provider = provider
        self._session_factory = session_factory

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_bars(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> List[OHLCVBar]:
        """Fetch normalised OHLCV bars for a single symbol and interval.

        For intraday intervals (1m, 5m, 15m, 1h), reads from the
        TimescaleDB hypertable if a session factory is available.
        Falls back to the provider for all other intervals or when
        no DB session is configured.

        Args:
            symbol:   Ticker symbol (will be upper-cased).
            interval: Candle interval string (e.g. ``"1d"``).
            start:    Inclusive start datetime.
            end:      Inclusive end datetime.

        Returns:
            Sorted list of ``OHLCVBar`` with no duplicate timestamps.

        Raises:
            ValueError: If *interval* is unsupported by the provider or
                        *start* >= *end*.
        """
        sym = symbol.upper()
        if start >= end:
            raise ValueError(
                f"start ({start}) must be before end ({end})."
            )

        # Try hypertable for intraday intervals
        if interval in _HYPERTABLE_INTERVALS and self._session_factory:
            bars = await self._read_hypertable(sym, interval, start, end)
            if bars:
                return self._dedupe_and_sort(bars)

        # Clamp lookback to provider maximum for this interval
        max_history = self._provider.get_max_history(interval)
        earliest_allowed = end - max_history
        effective_start = max(start, earliest_allowed)

        bars = await self._provider.get_ohlcv(
            sym, interval, effective_start, end,
        )
        return self._dedupe_and_sort(bars)

    async def get_quote(self, symbol: str) -> Quote:
        """Fetch the latest quote for *symbol*.

        Args:
            symbol: Ticker symbol (will be upper-cased).

        Returns:
            Normalised ``Quote`` snapshot from the provider.
        """
        return await self._provider.get_quote(symbol.upper())

    async def get_multi_timeframe(
        self,
        symbol: str,
        timeframes: List[str],
        start: datetime,
        end: datetime,
    ) -> Dict[str, List[OHLCVBar]]:
        """Fetch aligned OHLCV data at multiple intervals.

        Intraday intervals are read from the TimescaleDB hypertable
        (if available), daily+ intervals use the provider.  Results
        are aligned by trimming all timeframes to the common date range.

        Args:
            symbol:     Ticker symbol (will be upper-cased).
            timeframes: List of interval strings (e.g. ``["1h", "1d"]``).
            start:      Inclusive start datetime.
            end:        Inclusive end datetime.

        Returns:
            Dict mapping each interval to its ``OHLCVBar`` list.
        """
        result: Dict[str, List[OHLCVBar]] = {}
        for tf in timeframes:
            result[tf] = await self.get_bars(symbol, tf, start, end)

        # Align: trim all timeframes so they share the same date extent
        if len(result) > 1:
            common_start = max(
                (bars[0].timestamp for bars in result.values() if bars),
                default=start,
            )
            common_end = min(
                (bars[-1].timestamp for bars in result.values() if bars),
                default=end,
            )
            for tf in result:
                result[tf] = [
                    b for b in result[tf]
                    if common_start <= b.timestamp <= common_end
                ]

        return result

    def get_supported_intervals(self) -> List[str]:
        """Return the provider's supported interval list.

        Returns:
            List of interval strings.
        """
        return self._provider.get_supported_intervals()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _read_hypertable(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> List[OHLCVBar]:
        """Read bars from the intraday_bars TimescaleDB hypertable.

        Args:
            symbol:   Upper-cased ticker symbol.
            interval: Intraday interval string (1m, 5m, 15m, 1h).
            start:    Inclusive start datetime.
            end:      Inclusive end datetime.

        Returns:
            List of ``OHLCVBar`` from the database, or empty list on failure.
        """
        from sqlalchemy import text

        try:
            async with self._session_factory() as session:
                result = await session.execute(
                    text(
                        "SELECT timestamp, open, high, low, close, volume "
                        "FROM intraday_bars "
                        "WHERE symbol = :symbol AND interval = :interval "
                        "  AND timestamp >= :start AND timestamp <= :end "
                        "ORDER BY timestamp"
                    ),
                    {
                        "symbol": symbol,
                        "interval": interval,
                        "start": start,
                        "end": end,
                    },
                )
                rows = result.fetchall()
                if not rows:
                    return []
                return [
                    OHLCVBar(
                        timestamp=row[0],
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=int(row[5]),
                    )
                    for row in rows
                ]
        except Exception:
            return []

    @staticmethod
    def _dedupe_and_sort(bars: List[OHLCVBar]) -> List[OHLCVBar]:
        """Remove duplicate timestamps and sort chronologically.

        Args:
            bars: Raw list of ``OHLCVBar`` from a provider.

        Returns:
            Sorted, deduplicated list.
        """
        seen = set()
        unique: List[OHLCVBar] = []
        for bar in bars:
            if bar.timestamp not in seen:
                seen.add(bar.timestamp)
                unique.append(bar)
        unique.sort(key=lambda b: b.timestamp)
        return unique
