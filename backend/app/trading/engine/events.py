"""
engine/events.py — Event-aware no-trade zones.

Identifies date ranges when trading strategies should pause signals to
avoid entering positions around high-impact events with unpredictable
price gaps.

Sources:
  - Earnings dates (±1 trading day around the report)
  - Ex-dividend dates (day before + day of)
  - FOMC meeting dates (8 per year, hardcoded schedule)
  - Quarterly options expiration (OpEx — third Friday of Mar/Jun/Sep/Dec)
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List

logger = logging.getLogger("trading.events")


@dataclass
class NoTradeZone:
    """A date range during which signals should be suppressed.

    Attributes:
        start:  First date of the no-trade zone (inclusive).
        end:    Last date of the no-trade zone (inclusive).
        reason: Human-readable explanation for the zone.
    """
    start: date
    end: date
    reason: str


# ---------------------------------------------------------------------------
# FOMC meeting dates (2026 schedule — update annually)
# ---------------------------------------------------------------------------

FOMC_2026 = [
    date(2026, 1, 28), date(2026, 1, 29),
    date(2026, 3, 18), date(2026, 3, 19),
    date(2026, 5, 6),  date(2026, 5, 7),
    date(2026, 6, 17), date(2026, 6, 18),
    date(2026, 7, 29), date(2026, 7, 30),
    date(2026, 9, 16), date(2026, 9, 17),
    date(2026, 11, 4), date(2026, 11, 5),
    date(2026, 12, 16), date(2026, 12, 17),
]


def _third_friday(year: int, month: int) -> date:
    """Return the third Friday of a given month.

    Used to determine quarterly options expiration (OpEx) dates.

    Args:
        year:  Calendar year.
        month: Month number (1-12).

    Returns:
        The date of the third Friday.
    """
    # First day of month
    first = date(year, month, 1)
    # Find first Friday: weekday 4 = Friday
    offset = (4 - first.weekday()) % 7
    first_friday = first + timedelta(days=offset)
    # Third Friday = first Friday + 14 days
    return first_friday + timedelta(days=14)


def _get_opex_dates(start_date: date, end_date: date) -> List[date]:
    """Return quarterly OpEx dates within the given range.

    Quarterly options expiration occurs on the third Friday of March,
    June, September, and December.

    Args:
        start_date: Range start (inclusive).
        end_date:   Range end (inclusive).

    Returns:
        List of OpEx dates within the range.
    """
    opex_months = [3, 6, 9, 12]
    dates = []
    year = start_date.year
    while year <= end_date.year:
        for month in opex_months:
            opex = _third_friday(year, month)
            if start_date <= opex <= end_date:
                dates.append(opex)
        year += 1
    return dates


def _get_fomc_zones(start_date: date, end_date: date) -> List[NoTradeZone]:
    """Return FOMC no-trade zones within the date range.

    Creates a ±1 day zone around each FOMC meeting date.

    Args:
        start_date: Range start.
        end_date:   Range end.

    Returns:
        List of NoTradeZone objects for FOMC meetings.
    """
    zones = []
    for fomc_date in FOMC_2026:
        zone_start = fomc_date - timedelta(days=1)
        zone_end = fomc_date + timedelta(days=1)
        if zone_end >= start_date and zone_start <= end_date:
            zones.append(NoTradeZone(
                start=max(zone_start, start_date),
                end=min(zone_end, end_date),
                reason=f"FOMC meeting ({fomc_date.isoformat()})",
            ))
    return zones


def _get_opex_zones(start_date: date, end_date: date) -> List[NoTradeZone]:
    """Return OpEx no-trade zones within the date range.

    Creates a zone on the day before and day of OpEx.

    Args:
        start_date: Range start.
        end_date:   Range end.

    Returns:
        List of NoTradeZone objects for quarterly OpEx.
    """
    zones = []
    for opex_date in _get_opex_dates(start_date, end_date):
        zone_start = opex_date - timedelta(days=1)
        zones.append(NoTradeZone(
            start=max(zone_start, start_date),
            end=min(opex_date, end_date),
            reason=f"Quarterly OpEx ({opex_date.isoformat()})",
        ))
    return zones


async def _get_earnings_zones(
    symbol: str, start_date: date, end_date: date
) -> List[NoTradeZone]:
    """Fetch earnings dates from yfinance and return ±1 day no-trade zones.

    Args:
        symbol:     Ticker symbol.
        start_date: Range start.
        end_date:   Range end.

    Returns:
        List of NoTradeZone objects around earnings dates.
    """
    import asyncio
    import yfinance as yf

    zones = []
    try:
        ticker = yf.Ticker(symbol)
        cal = await asyncio.to_thread(lambda: ticker.calendar)
        if cal is not None and not cal.empty:
            # yfinance calendar returns a DataFrame with dates
            for col in cal.columns:
                try:
                    earnings_date = cal[col].iloc[0]
                    if hasattr(earnings_date, "date"):
                        earnings_date = earnings_date.date()
                    elif isinstance(earnings_date, str):
                        from datetime import datetime as dt
                        earnings_date = dt.strptime(earnings_date, "%Y-%m-%d").date()
                    else:
                        continue

                    zone_start = earnings_date - timedelta(days=1)
                    zone_end = earnings_date + timedelta(days=1)
                    if zone_end >= start_date and zone_start <= end_date:
                        zones.append(NoTradeZone(
                            start=max(zone_start, start_date),
                            end=min(zone_end, end_date),
                            reason=f"Earnings ({earnings_date.isoformat()})",
                        ))
                except Exception:
                    continue
    except Exception as e:
        logger.warning("Failed to fetch earnings for %s: %s", symbol, e)
    return zones


async def _get_dividend_zones(
    symbol: str, start_date: date, end_date: date
) -> List[NoTradeZone]:
    """Fetch ex-dividend dates from yfinance and return no-trade zones.

    Zone covers the day before and day of ex-dividend.

    Args:
        symbol:     Ticker symbol.
        start_date: Range start.
        end_date:   Range end.

    Returns:
        List of NoTradeZone objects around ex-dividend dates.
    """
    import asyncio
    import yfinance as yf

    zones = []
    try:
        ticker = yf.Ticker(symbol)
        dividends = await asyncio.to_thread(lambda: ticker.dividends)
        if dividends is not None and not dividends.empty:
            for ts in dividends.index:
                ex_date = ts.date()
                zone_start = ex_date - timedelta(days=1)
                if zone_start <= end_date and ex_date >= start_date:
                    zones.append(NoTradeZone(
                        start=max(zone_start, start_date),
                        end=min(ex_date, end_date),
                        reason=f"Ex-dividend ({ex_date.isoformat()})",
                    ))
    except Exception as e:
        logger.warning("Failed to fetch dividends for %s: %s", symbol, e)
    return zones


async def get_no_trade_zones(
    symbol: str,
    start_date: date,
    end_date: date,
) -> List[NoTradeZone]:
    """Return all no-trade zones for a symbol within a date range.

    Combines:
      - Earnings dates (±1 day)
      - Ex-dividend dates (day before + day of)
      - FOMC meeting dates (±1 day, hardcoded schedule)
      - Quarterly options expiration (day before + day of)

    Args:
        symbol:     Ticker symbol (e.g. "AAPL").
        start_date: Start of range (inclusive).
        end_date:   End of range (inclusive).

    Returns:
        Sorted list of NoTradeZone objects.
    """
    # Collect all zone sources
    fomc_zones = _get_fomc_zones(start_date, end_date)
    opex_zones = _get_opex_zones(start_date, end_date)
    earnings_zones = await _get_earnings_zones(symbol, start_date, end_date)
    dividend_zones = await _get_dividend_zones(symbol, start_date, end_date)

    all_zones = fomc_zones + opex_zones + earnings_zones + dividend_zones
    all_zones.sort(key=lambda z: z.start)

    logger.info(
        "No-trade zones for %s (%s to %s): %d zones",
        symbol, start_date, end_date, len(all_zones),
    )
    return all_zones


def is_in_no_trade_zone(bar_date: date, zones: List[NoTradeZone]) -> bool:
    """Check if a given date falls within any no-trade zone.

    Strategies call this per-bar to decide whether to suppress signals.

    Args:
        bar_date: The date to check.
        zones:    List of NoTradeZone objects to check against.

    Returns:
        True if the date is within a no-trade zone.
    """
    for zone in zones:
        if zone.start <= bar_date <= zone.end:
            return True
    return False
