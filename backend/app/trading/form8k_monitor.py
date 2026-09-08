"""form8k_monitor.py — Poll EDGAR 8-K atom feed, keep only tracked tickers.

8-K volume is dozens per 5-minute tick across every US issuer — this reuses
finra_short_interest.py's tracked-ticker query (open positions + anything
with an insider filing on record) to discard everything else *before*
storing anything, so this never becomes a market-wide firehose. No
per-filing document fetch is needed at all: item codes come straight from
the atom feed (see form8k_edgar.py).
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from ..models import EightKFiling
from .cik_ticker_map import resolve_ticker
from .finra_short_interest import _wanted_tickers
from .form8k_edgar import FORM8K_ATOM_URL, parse_8k_atom_feed
from .insider_edgar import EdgarFetcher

logger = structlog.get_logger("form8k_monitor")

_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@db:5432/tickerTap",
)
_RECENT_WINDOW_DAYS = 14

_engine = create_async_engine(_DATABASE_URL, echo=False, pool_size=2, max_overflow=1, pool_pre_ping=True)
_SessionLocal = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


def _parse_updated(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


async def _already_stored(session: AsyncSession, accession: str) -> bool:
    res = await session.execute(
        select(EightKFiling.filing_id).where(EightKFiling.accession == accession).limit(1)
    )
    return res.scalar_one_or_none() is not None


async def get_recent_8k_filings(
    session: AsyncSession, ticker: str, *, since: Optional[date] = None, limit: int = 5
) -> list[EightKFiling]:
    """Recent tracked 8-Ks for a ticker — market color for insider alerts
    ("why might this stock actually be moving")."""
    if not ticker:
        return []
    since = since or (datetime.now(timezone.utc).date() - timedelta(days=_RECENT_WINDOW_DAYS))
    res = await session.execute(
        select(EightKFiling)
        .where(
            EightKFiling.ticker == ticker.upper(),
            EightKFiling.filed_at >= datetime.combine(since, datetime.min.time(), tzinfo=timezone.utc),
        )
        .order_by(desc(EightKFiling.filed_at))
        .limit(limit)
    )
    return list(res.scalars().all())


async def poll_8k_filings(ctx: dict) -> dict:
    """arq cron entrypoint. No-op without SEC_USER_AGENT."""
    ua = (os.getenv("SEC_USER_AGENT") or "").strip()
    if not ua:
        logger.info("form8k_poll_skipped", reason="SEC_USER_AGENT unset")
        return {"skipped": True, "reason": "no_user_agent"}

    fetcher = EdgarFetcher(ua)
    stats = {"fetched": 0, "matched": 0, "stored": 0, "errors": 0}
    try:
        atom_xml = await fetcher.get(FORM8K_ATOM_URL)
    except Exception:
        logger.exception("form8k_atom_fetch_failed")
        return stats

    entries = parse_8k_atom_feed(atom_xml)
    stats["fetched"] = len(entries)
    if not entries:
        return stats

    async with _SessionLocal() as session:
        wanted = await _wanted_tickers(session)
        if not wanted:
            logger.info("form8k_no_tracked_tickers")
            return stats

        for entry in entries:
            try:
                if await _already_stored(session, entry["accession"]):
                    continue
                ticker = resolve_ticker(entry["issuer_cik"])
                if not ticker or ticker not in wanted:
                    continue
                stats["matched"] += 1
                session.add(
                    EightKFiling(
                        accession=entry["accession"],
                        ticker=ticker,
                        issuer_cik=entry["issuer_cik"][:10] or None,
                        issuer_name=(entry["issuer_name"] or "")[:256] or None,
                        is_amendment=bool(entry["is_amendment"]),
                        items=entry["items"] or None,
                        filed_at=_parse_updated(entry.get("updated")),
                        filing_url=entry.get("index_url") or None,
                    )
                )
                stats["stored"] += 1
            except Exception:
                stats["errors"] += 1
                logger.exception("form8k_entry_failed", accession=entry.get("accession"))

        await session.commit()
    logger.info("form8k_poll_done", **stats)
    return stats
