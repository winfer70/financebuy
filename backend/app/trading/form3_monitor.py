"""form3_monitor.py — Poll EDGAR Form 3 initial ownership statements, store.

Cron on trading-worker at the same slower cadence as Form 144 — a Form 3
alone doesn't fire its own Telegram alert, it just needs to be on file
before a first Form 4 sale from that owner shows up so insider_monitor.py
can contextualize it ("sold 10% of initial grant" vs "sold 80%").
"""
from __future__ import annotations

import asyncio
import os
from datetime import date
from decimal import Decimal
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from ..models import Form3Statement
from .insider_edgar import EdgarFetcher, parse_atom_accessions, parse_form3_xml, xml_doc_url_from_index_html

logger = structlog.get_logger("form3_monitor")

FORM3_ATOM_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcurrent&type=3&owner=include&count=40&output=atom"
)

_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@db:5432/tickerTap",
)
_MAX_NEW_PER_CYCLE = 15
_REQUEST_PAUSE_S = 0.25

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
        select(Form3Statement.statement_id).where(Form3Statement.accession == accession).limit(1)
    )
    return res.scalar_one_or_none() is not None


async def get_form3_baseline(session: AsyncSession, owner_cik: str, ticker: str) -> Optional[Form3Statement]:
    """The owner's starting position for this ticker, if one was ever
    filed. Used to contextualize a Form 4 sale as a fraction of their
    initial stake ("sold 10% of initial grant" vs "sold 80%")."""
    if not owner_cik or not ticker:
        return None
    res = await session.execute(
        select(Form3Statement).where(
            Form3Statement.owner_cik == owner_cik[:10],
            Form3Statement.ticker == ticker.upper(),
        )
        .limit(1)
    )
    return res.scalar_one_or_none()


async def poll_form3_filings(ctx: dict) -> dict:
    """arq cron entrypoint. No-op without SEC_USER_AGENT."""
    ua = (os.getenv("SEC_USER_AGENT") or "").strip()
    if not ua:
        logger.info("form3_poll_skipped", reason="SEC_USER_AGENT unset")
        return {"skipped": True, "reason": "no_user_agent"}

    fetcher = EdgarFetcher(ua)
    stats = {"fetched": 0, "new": 0, "stored": 0, "errors": 0}
    async with _SessionLocal() as session:
        try:
            atom_xml = await fetcher.get(FORM3_ATOM_URL)
        except Exception:
            logger.exception("form3_atom_fetch_failed")
            return stats
        entries = parse_atom_accessions(atom_xml)
        stats["fetched"] = len(entries)

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
        stats["new"] = len(fresh)

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
                parsed = parse_form3_xml(xml_text, accession=entry["accession"], filing_url=xml_url)
                if not parsed:
                    continue
                session.add(
                    Form3Statement(
                        accession=parsed["accession"],
                        ticker=parsed["ticker"],
                        issuer_cik=(parsed["issuer_cik"] or "")[:10] or None,
                        owner_name=(parsed["owner_name"] or "")[:256] or None,
                        owner_cik=(parsed["owner_cik"] or "")[:10] or None,
                        is_director=bool(parsed["is_director"]),
                        is_officer=bool(parsed["is_officer"]),
                        is_ten_percent=bool(parsed["is_ten_percent"]),
                        officer_title=(parsed["officer_title"] or "")[:128] or None,
                        shares_owned=Decimal(str(parsed["shares_owned"])) if parsed["shares_owned"] else None,
                        period_of_report=_parse_date(parsed["period_of_report"]),
                        filing_url=xml_url,
                    )
                )
                stats["stored"] += 1
            except Exception:
                stats["errors"] += 1
                logger.exception("form3_entry_failed", accession=entry.get("accession"))

        await session.commit()
    logger.info("form3_poll_done", **stats)
    return stats
