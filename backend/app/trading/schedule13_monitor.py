"""schedule13_monitor.py — Poll EDGAR Schedule 13D/13G, resolve ticker, store.

Cron on trading-worker at the same slower cadence as Form 144/3 — no direct
alert (see FREE_FILINGS_RESEARCH.md's "surface it, don't auto-alert"
guidance); insider_monitor.py surfaces recent hits as ticker-wide market
color on insider BUY/SELL alerts rather than owner-correlated context
(13D/13G filers are typically institutions/activists, not the same
individuals filing Form 4s).
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

from ..models import BeneficialOwnership
from .cik_ticker_map import resolve_ticker
from .insider_edgar import EdgarFetcher, parse_atom_accessions, xml_doc_url_from_index_html
from .schedule13_edgar import (
    FORM_13D_ATOM_URL,
    FORM_13G_ATOM_URL,
    parse_schedule13d_xml,
    parse_schedule13g_xml,
)

logger = structlog.get_logger("schedule13_monitor")

_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@db:5432/tickerTap",
)
_MAX_NEW_PER_CYCLE = 10  # per form type
_REQUEST_PAUSE_S = 0.25
_RECENT_WINDOW_DAYS = 14

_engine = create_async_engine(_DATABASE_URL, echo=False, pool_size=2, max_overflow=1, pool_pre_ping=True)
_SessionLocal = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


async def _already_stored(session: AsyncSession, accession: str) -> bool:
    res = await session.execute(
        select(BeneficialOwnership.ownership_id).where(BeneficialOwnership.accession == accession).limit(1)
    )
    return res.scalar_one_or_none() is not None


async def get_recent_beneficial_ownership(
    session: AsyncSession, ticker: str, *, since: Optional[date] = None, limit: int = 5
) -> list[BeneficialOwnership]:
    """Recent >5% ownership disclosures for a ticker — used to add market
    color to insider alerts. Not owner-correlated (unlike Form 144/3):
    13D/13G filers are typically institutions/activists, not the same
    people filing Form 4s, so this is ticker-wide, any filer."""
    if not ticker:
        return []
    since = since or (datetime.now(timezone.utc).date() - timedelta(days=_RECENT_WINDOW_DAYS))
    res = await session.execute(
        select(BeneficialOwnership)
        .where(
            BeneficialOwnership.ticker == ticker.upper(),
            BeneficialOwnership.event_date >= since,
        )
        .order_by(desc(BeneficialOwnership.event_date))
        .limit(limit)
    )
    return list(res.scalars().all())


async def _poll_one_form_type(
    session: AsyncSession,
    fetcher: EdgarFetcher,
    atom_url: str,
    parse_fn,
    stats: dict,
) -> None:
    try:
        atom_xml = await fetcher.get(atom_url)
    except Exception:
        logger.exception("schedule13_atom_fetch_failed", url=atom_url)
        return
    entries = parse_atom_accessions(atom_xml)
    stats["fetched"] += len(entries)

    seen_this_cycle: set[str] = set()
    fresh = []
    for e in entries:
        acc = e.get("accession") or ""
        if not acc or acc in seen_this_cycle:
            continue
        if await _already_stored(session, acc):
            seen_this_cycle.add(acc)
            continue
        seen_this_cycle.add(acc)
        fresh.append(e)
        if len(fresh) >= _MAX_NEW_PER_CYCLE:
            break
    stats["new"] += len(fresh)

    for entry in fresh:
        if _REQUEST_PAUSE_S:
            await asyncio.sleep(_REQUEST_PAUSE_S)
        try:
            index_html = await fetcher.get(entry["index_url"])
            xml_url = xml_doc_url_from_index_html(
                index_html, entry["accession"], entry.get("index_url") or ""
            )
            if not xml_url:
                continue
            if _REQUEST_PAUSE_S:
                await asyncio.sleep(_REQUEST_PAUSE_S)
            xml_text = await fetcher.get(xml_url)
            rows = parse_fn(xml_text, accession=entry["accession"], filing_url=xml_url)
            if not rows:
                continue
            ticker = resolve_ticker(rows[0]["issuer_cik"])
            for row in rows:
                session.add(
                    BeneficialOwnership(
                        accession=row["accession"],
                        person_index=row["person_index"],
                        is_13d=row["is_13d"],
                        is_amendment=row["is_amendment"],
                        ticker=ticker,
                        issuer_cik=(row["issuer_cik"] or "")[:10] or None,
                        issuer_name=(row["issuer_name"] or "")[:256] or None,
                        filer_cik=(row["filer_cik"] or "")[:10] or None,
                        filer_name=(row["filer_name"] or "")[:256] or None,
                        shares_owned=Decimal(str(row["shares_owned"])) if row["shares_owned"] else None,
                        pct_owned=Decimal(str(row["pct_owned"])) if row["pct_owned"] else None,
                        event_date=_parse_date(row["event_date"]),
                        purpose_text=row["purpose_text"] or None,
                        filing_url=xml_url,
                    )
                )
            stats["stored"] += len(rows)
        except Exception:
            stats["errors"] += 1
            logger.exception("schedule13_entry_failed", accession=entry.get("accession"))


async def poll_schedule13_filings(ctx: dict) -> dict:
    """arq cron entrypoint. No-op without SEC_USER_AGENT."""
    ua = (os.getenv("SEC_USER_AGENT") or "").strip()
    if not ua:
        logger.info("schedule13_poll_skipped", reason="SEC_USER_AGENT unset")
        return {"skipped": True, "reason": "no_user_agent"}

    fetcher = EdgarFetcher(ua)
    stats = {"fetched": 0, "new": 0, "stored": 0, "errors": 0}
    async with _SessionLocal() as session:
        await _poll_one_form_type(session, fetcher, FORM_13D_ATOM_URL, parse_schedule13d_xml, stats)
        await _poll_one_form_type(session, fetcher, FORM_13G_ATOM_URL, parse_schedule13g_xml, stats)
        await session.commit()
    logger.info("schedule13_poll_done", **stats)
    return stats
