"""finra_short_interest.py — Poll FINRA's free biweekly short-interest flat
file, filter to tickers we actually track, store.

FINRA settles short interest twice a month (Rule 4560) but publishes the
flat file with a ~2-3 week lag and doesn't expose a predictable "latest"
URL — cdn.finra.org/equity/otcmarket/biweekly/shrt{YYYYMMDD}.csv 404s
(actually 403s, CDN-style) for any date that isn't an exact settlement
date. So this scans backward from today with cheap HEAD requests until it
finds one that exists, caching the resolved date so a normal cycle (no new
settlement published since last check) costs one HEAD, not forty.

Despite the "otcmarket" path segment this covers NYSE/Nasdaq-listed names
too (verified against live data during development) — it's FINRA's
internal grouping term for broker-dealer-reported positions, not a literal
OTC-only filter. The file itself is market-wide (thousands of tickers,
~2MB) so only rows matching our own watch set are kept, mirroring the same
"open positions + insider filers" set feedback.py's watch-tickers endpoint
uses for the news worker — computed directly here via DB query since this
poller already runs inside trading-worker with a live session, no HTTP
round-trip needed.
"""
from __future__ import annotations

import asyncio
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

import requests
import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from ..models import InsiderFiling, PortfolioPosition, ShortInterestSnapshot

logger = structlog.get_logger("finra_short_interest")

_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@db:5432/tickerTap",
)
_engine = create_async_engine(_DATABASE_URL, echo=False, pool_size=2, max_overflow=1, pool_pre_ping=True)
_SessionLocal = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

_CDN_URL_TEMPLATE = "https://cdn.finra.org/equity/otcmarket/biweekly/shrt{date}.csv"
_MAX_LOOKBACK_DAYS = 45
_FETCH_TIMEOUT = 30

# Cache of the last resolved settlement date — avoids re-scanning on every
# cycle. Cleared (implicitly outdated) once a poll finds nothing newer for
# a while; the scan is cheap (HEAD requests) so there's no harm re-running
# it, this just skips it when we already know today's answer.
_cached_settlement_date_str: Optional[str] = None
_cache_checked_on: Optional[date] = None


def _find_latest_settlement_date() -> Optional[str]:
    """Sync — HEAD-scan backward for the most recent published file.
    Returns YYYYMMDD string, or None if nothing found in the lookback
    window (never raises; a down CDN just means an empty cycle)."""
    global _cached_settlement_date_str, _cache_checked_on
    today = date.today()
    if _cached_settlement_date_str and _cache_checked_on == today:
        return _cached_settlement_date_str

    for offset in range(_MAX_LOOKBACK_DAYS):
        d = today - timedelta(days=offset)
        date_str = d.strftime("%Y%m%d")
        url = _CDN_URL_TEMPLATE.format(date=date_str)
        try:
            resp = requests.head(url, timeout=_FETCH_TIMEOUT)
        except requests.RequestException:
            continue
        if resp.status_code == 200:
            _cached_settlement_date_str = date_str
            _cache_checked_on = today
            return date_str
    return None


def _fetch_csv(date_str: str) -> Optional[str]:
    url = _CDN_URL_TEMPLATE.format(date=date_str)
    try:
        resp = requests.get(url, timeout=_FETCH_TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException:
        return None


def _parse_and_filter(csv_text: str, wanted_tickers: set[str]) -> list[dict]:
    """Pipe-delimited (despite the .csv extension), header row first. Only
    rows matching wanted_tickers are kept — the file is market-wide."""
    lines = csv_text.splitlines()
    if not lines:
        return []
    header = [h.strip() for h in lines[0].split("|")]
    idx = {name: i for i, name in enumerate(header)}
    if "symbolCode" not in idx or "settlementDate" not in idx:
        return []

    def _cell(parts: list[str], name: str) -> str:
        i = idx.get(name)
        if i is None or i >= len(parts):
            return ""
        return parts[i].strip()

    out = []
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split("|")
        symbol = _cell(parts, "symbolCode").upper()
        if not symbol or symbol not in wanted_tickers:
            continue
        out.append(
            {
                "ticker": symbol,
                "settlement_date": _cell(parts, "settlementDate"),
                "current_short_position": _cell(parts, "currentShortPositionQuantity"),
                "previous_short_position": _cell(parts, "previousShortPositionQuantity"),
                "average_daily_volume": _cell(parts, "averageDailyVolumeQuantity"),
                "days_to_cover": _cell(parts, "daysToCoverQuantity"),
                "change_percent": _cell(parts, "changePercent"),
            }
        )
    return out


def _to_decimal(value: str) -> Optional[Decimal]:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _parse_iso_date(value: str) -> Optional[date]:
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError:
        return None


async def _wanted_tickers(session: AsyncSession) -> set[str]:
    """Everything worth storing short interest for: open positions across
    all users, plus every ticker with an insider filing ever ingested (no
    time window — a name's history stays relevant even after the filing
    ages out of the 21-day watch-tickers window news uses)."""
    held = await session.execute(
        select(PortfolioPosition.ticker).where(PortfolioPosition.closed_at.is_(None)).distinct()
    )
    filed = await session.execute(select(InsiderFiling.ticker).distinct())
    out: set[str] = set()
    for row in (*held.all(), *filed.all()):
        t = (row[0] or "").strip().upper()
        if t:
            out.add(t)
    return out


async def _already_stored(session: AsyncSession, ticker: str, settlement_date: date) -> bool:
    res = await session.execute(
        select(ShortInterestSnapshot.snapshot_id).where(
            ShortInterestSnapshot.ticker == ticker,
            ShortInterestSnapshot.settlement_date == settlement_date,
        ).limit(1)
    )
    return res.scalar_one_or_none() is not None


async def get_latest_short_interest(session: AsyncSession, ticker: str) -> Optional[ShortInterestSnapshot]:
    """Most recent snapshot for a ticker, or None if never stored (e.g. the
    ticker wasn't tracked yet as of the last settlement date, or it's an
    OTC/foreign name FINRA's file doesn't cover). Used by insider_monitor.py
    to add squeeze/crowding context to alert advice."""
    if not ticker:
        return None
    res = await session.execute(
        select(ShortInterestSnapshot)
        .where(ShortInterestSnapshot.ticker == ticker.upper())
        .order_by(desc(ShortInterestSnapshot.settlement_date))
        .limit(1)
    )
    return res.scalar_one_or_none()


async def poll_short_interest(ctx: dict) -> dict:
    """arq cron entrypoint. Daily is plenty — FINRA only republishes every
    two weeks, and the settlement-date scan is cached per-day regardless."""
    loop = asyncio.get_running_loop()
    date_str = await loop.run_in_executor(None, _find_latest_settlement_date)
    if date_str is None:
        logger.warning("finra_short_interest_no_file_found")
        return {"found": False}

    settlement_date = _parse_iso_date(f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}")
    stats = {"settlement_date": date_str, "matched": 0, "stored": 0, "errors": 0}

    async with _SessionLocal() as session:
        wanted = await _wanted_tickers(session)
        if not wanted:
            logger.info("finra_short_interest_no_tracked_tickers")
            return stats

        csv_text = await loop.run_in_executor(None, _fetch_csv, date_str)
        if csv_text is None:
            logger.warning("finra_short_interest_fetch_failed", settlement_date=date_str)
            return stats

        rows = _parse_and_filter(csv_text, wanted)
        stats["matched"] = len(rows)

        for row in rows:
            row_settlement = _parse_iso_date(row["settlement_date"]) or settlement_date
            try:
                if await _already_stored(session, row["ticker"], row_settlement):
                    continue
                session.add(
                    ShortInterestSnapshot(
                        ticker=row["ticker"],
                        settlement_date=row_settlement,
                        current_short_position=_to_decimal(row["current_short_position"]),
                        previous_short_position=_to_decimal(row["previous_short_position"]),
                        average_daily_volume=_to_decimal(row["average_daily_volume"]),
                        days_to_cover=_to_decimal(row["days_to_cover"]),
                        change_percent=_to_decimal(row["change_percent"]),
                    )
                )
                stats["stored"] += 1
            except Exception:
                stats["errors"] += 1
                logger.exception("finra_short_interest_row_failed", ticker=row.get("ticker"))

        await session.commit()

    logger.info("finra_short_interest_poll_done", **stats)
    return stats
