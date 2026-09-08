"""form144_monitor.py — Poll EDGAR Form 144 notices, resolve ticker, store.

Cron on trading-worker at a slower cadence than Form 4 — a 144 alone
doesn't fire its own Telegram alert (FREE_FILINGS_RESEARCH.md: "surface it,
don't auto-alert on it yet"). insider_monitor.py's sell-gate path calls
get_recent_144_notice() to correlate a Form 4 sell against a matching 144,
turning "insider sold" into "insider sold, and pre-announced it N days
earlier via Form 144" in the advice text.
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

from ..models import Form144Notice
from .cik_ticker_map import resolve_ticker
from .form144_edgar import FORM144_ATOM_URL, parse_form144_xml
from .insider_edgar import EdgarFetcher, parse_atom_accessions, xml_doc_url_from_index_html

logger = structlog.get_logger("form144_monitor")

_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@db:5432/tickerTap",
)
_MAX_NEW_PER_CYCLE = 15
_REQUEST_PAUSE_S = 0.25
# A 144 states an *intended* sale date but the matching Form 4 sometimes
# lands late — widen past that date rather than cutting off exactly on it.
_CORRELATION_WINDOW_DAYS = 90

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
        select(Form144Notice.notice_id).where(Form144Notice.accession == accession).limit(1)
    )
    return res.scalar_one_or_none() is not None


async def get_recent_144_notice(
    session: AsyncSession, owner_cik: str, ticker: str, *, since: Optional[date] = None
) -> Optional[Form144Notice]:
    """Most recent Form 144 notice for this owner+ticker within the
    correlation window — used to enrich a Form 4 sell's advice text.
    None if no notice is on file (most sells have no matching 144, e.g.
    option exercises or sales under a threshold that doesn't require one)."""
    if not owner_cik or not ticker:
        return None
    since = since or (datetime.now(timezone.utc).date() - timedelta(days=_CORRELATION_WINDOW_DAYS))
    res = await session.execute(
        select(Form144Notice)
        .where(
            Form144Notice.owner_cik == owner_cik[:10],
            Form144Notice.ticker == ticker.upper(),
            Form144Notice.notice_date >= since,
        )
        .order_by(desc(Form144Notice.notice_date))
        .limit(1)
    )
    return res.scalar_one_or_none()


async def poll_form144_filings(ctx: dict) -> dict:
    """arq cron entrypoint. No-op without SEC_USER_AGENT."""
    ua = (os.getenv("SEC_USER_AGENT") or "").strip()
    if not ua:
        logger.info("form144_poll_skipped", reason="SEC_USER_AGENT unset")
        return {"skipped": True, "reason": "no_user_agent"}

    fetcher = EdgarFetcher(ua)
    stats = {"fetched": 0, "new": 0, "stored": 0, "errors": 0}
    async with _SessionLocal() as session:
        try:
            atom_xml = await fetcher.get(FORM144_ATOM_URL)
        except Exception:
            logger.exception("form144_atom_fetch_failed")
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
                parsed = parse_form144_xml(xml_text, accession=entry["accession"], filing_url=xml_url)
                if not parsed:
                    continue
                ticker = resolve_ticker(parsed["issuer_cik"])
                session.add(
                    Form144Notice(
                        accession=parsed["accession"],
                        ticker=ticker,
                        issuer_cik=parsed["issuer_cik"][:10] or None,
                        issuer_name=(parsed["issuer_name"] or "")[:256] or None,
                        owner_cik=parsed["owner_cik"][:10] or None,
                        owner_name=(parsed["owner_name"] or "")[:256] or None,
                        relationships=(parsed["relationships"] or "")[:128] or None,
                        broker=(parsed["broker"] or "")[:256] or None,
                        shares=Decimal(str(parsed["shares"])) if parsed["shares"] else None,
                        aggregate_value=(
                            Decimal(str(parsed["aggregate_value"])) if parsed["aggregate_value"] else None
                        ),
                        approx_sale_date=_parse_date(parsed["approx_sale_date"]),
                        notice_date=_parse_date(parsed["notice_date"]),
                        filing_url=xml_url,
                    )
                )
                stats["stored"] += 1
            except Exception:
                stats["errors"] += 1
                logger.exception("form144_entry_failed", accession=entry.get("accession"))

        await session.commit()
    logger.info("form144_poll_done", **stats)
    return stats
