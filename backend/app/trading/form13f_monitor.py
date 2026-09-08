"""form13f_monitor.py — Poll EDGAR 13F-HR filings, resolve CUSIPs, keep only
tracked-ticker holdings.

Daily cadence (same as finra_short_interest.py) — 13F is quarterly
positioning data, not a trading signal, so there's no benefit to polling
more often than that. A single filer can list hundreds of holdings, so
this reuses finra_short_interest.py's tracked-ticker query and resolves
CUSIPs via the free OpenFIGI API (cusip_ticker_map.py) only for filings
that are actually new, discarding anything that doesn't match a tracked
ticker before storing.
"""
from __future__ import annotations

import asyncio
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from ..models import Form13FHolding
from .cusip_ticker_map import resolve_cusips
from .finra_short_interest import _wanted_tickers
from .form13f_edgar import (
    FORM13F_ATOM_URL,
    infotable_xml_url_from_index_html,
    parse_13f_atom_feed,
    parse_13f_infotable_xml,
)
from .insider_edgar import EdgarFetcher

logger = structlog.get_logger("form13f_monitor")

_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@db:5432/tickerTap",
)
_MAX_NEW_FILINGS_PER_CYCLE = 5
_REQUEST_PAUSE_S = 0.25
_RECENT_WINDOW_DAYS = 100  # 13F is quarterly — a wider lookback than the other filing types

_engine = create_async_engine(_DATABASE_URL, echo=False, pool_size=2, max_overflow=1, pool_pre_ping=True)
_SessionLocal = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def _already_stored(session: AsyncSession, accession: str) -> bool:
    res = await session.execute(
        select(Form13FHolding.holding_id).where(Form13FHolding.accession == accession).limit(1)
    )
    return res.scalar_one_or_none() is not None


async def get_recent_13f_holders(
    session: AsyncSession, ticker: str, *, since: Optional[date] = None, limit: int = 5
) -> list[Form13FHolding]:
    """Recent tracked-ticker 13F holdings — "which funds hold this name"
    market color for insider alerts."""
    if not ticker:
        return []
    since = since or (datetime.now(timezone.utc).date() - timedelta(days=_RECENT_WINDOW_DAYS))
    res = await session.execute(
        select(Form13FHolding)
        .where(
            Form13FHolding.ticker == ticker.upper(),
            Form13FHolding.filed_at >= datetime.combine(since, datetime.min.time(), tzinfo=timezone.utc),
        )
        .order_by(desc(Form13FHolding.filed_at))
        .limit(limit)
    )
    return list(res.scalars().all())


async def poll_13f_filings(ctx: dict) -> dict:
    """arq cron entrypoint. No-op without SEC_USER_AGENT."""
    ua = (os.getenv("SEC_USER_AGENT") or "").strip()
    if not ua:
        logger.info("form13f_poll_skipped", reason="SEC_USER_AGENT unset")
        return {"skipped": True, "reason": "no_user_agent"}

    fetcher = EdgarFetcher(ua)
    stats = {"fetched": 0, "new": 0, "holdings_seen": 0, "matched": 0, "stored": 0, "errors": 0}
    try:
        atom_xml = await fetcher.get(FORM13F_ATOM_URL)
    except Exception:
        logger.exception("form13f_atom_fetch_failed")
        return stats

    entries_meta = parse_13f_atom_feed(atom_xml)
    stats["fetched"] = len(entries_meta)

    async with _SessionLocal() as session:
        wanted = await _wanted_tickers(session)
        if not wanted:
            logger.info("form13f_no_tracked_tickers")
            return stats

        seen_this_cycle: set[str] = set()
        fresh = []
        for e in entries_meta:
            acc = e["accession"]
            if acc in seen_this_cycle:
                continue
            if await _already_stored(session, acc):
                seen_this_cycle.add(acc)
                continue
            seen_this_cycle.add(acc)
            fresh.append(e)
            if len(fresh) >= _MAX_NEW_FILINGS_PER_CYCLE:
                break
        stats["new"] = len(fresh)

        for entry in fresh:
            if _REQUEST_PAUSE_S:
                await asyncio.sleep(_REQUEST_PAUSE_S)
            try:
                index_html = await fetcher.get(entry["index_url"])
                infotable_url = infotable_xml_url_from_index_html(index_html, entry["index_url"])
                if not infotable_url:
                    continue
                if _REQUEST_PAUSE_S:
                    await asyncio.sleep(_REQUEST_PAUSE_S)
                infotable_xml = await fetcher.get(infotable_url)
                holdings = parse_13f_infotable_xml(infotable_xml)
                stats["holdings_seen"] += len(holdings)
                if not holdings:
                    continue

                cusip_map = resolve_cusips([h["cusip"] for h in holdings])
                filed_at = datetime.now(timezone.utc)

                for h in holdings:
                    ticker = cusip_map.get(h["cusip"])
                    if not ticker or ticker not in wanted:
                        continue
                    stats["matched"] += 1
                    session.add(
                        Form13FHolding(
                            accession=entry["accession"],
                            filer_cik=entry["filer_cik"][:10] or None,
                            filer_name=(entry["filer_name"] or "")[:256] or None,
                            ticker=ticker,
                            cusip=h["cusip"][:9],
                            issuer_name=(h["issuer_name"] or "")[:256] or None,
                            shares=Decimal(str(h["shares"])) if h["shares"] else None,
                            value_usd=Decimal(str(h["value"])) if h["value"] else None,
                            is_amendment=bool(entry["is_amendment"]),
                            filed_at=filed_at,
                            filing_url=infotable_url,
                        )
                    )
                    stats["stored"] += 1
            except Exception:
                stats["errors"] += 1
                logger.exception("form13f_entry_failed", accession=entry.get("accession"))

        await session.commit()
    logger.info("form13f_poll_done", **stats)
    return stats
