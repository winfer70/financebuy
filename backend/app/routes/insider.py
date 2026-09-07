"""insider.py — Browse ingested Form 4 filings and per-person breakdowns.

Read-only API over insider_filings (populated by trading-worker poller).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import InsiderFiling
from .auth_routes import get_current_user

router = APIRouter(prefix="/insider", tags=["insider"])

_SORTABLE = {
    "transaction_date": InsiderFiling.transaction_date,
    "ticker": InsiderFiling.ticker,
    "owner_name": InsiderFiling.owner_name,
    "transaction_code": InsiderFiling.transaction_code,
    "shares": InsiderFiling.shares,
    "price": InsiderFiling.price,
    "notional": InsiderFiling.notional,
    "stake_pct": InsiderFiling.stake_pct,
    "created_at": InsiderFiling.created_at,
}


class FilingOut(BaseModel):
    filing_id: UUID
    accession: str
    ticker: str
    owner_name: Optional[str] = None
    owner_cik: Optional[str] = None
    officer_title: Optional[str] = None
    is_director: bool = False
    is_officer: bool = False
    transaction_code: str
    shares: Optional[float] = None
    price: Optional[float] = None
    notional: Optional[float] = None
    shares_after: Optional[float] = None
    stake_pct: Optional[float] = None
    transaction_date: Optional[date] = None
    is_10b5_1: Optional[bool] = None
    filing_url: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class FilingListOut(BaseModel):
    total: int
    items: list[FilingOut]


class OwnerTxnOut(BaseModel):
    accession: str
    ticker: str
    transaction_code: str
    shares: Optional[float] = None
    price: Optional[float] = None
    notional: Optional[float] = None
    stake_pct: Optional[float] = None
    transaction_date: Optional[date] = None
    is_10b5_1: Optional[bool] = None
    filing_url: Optional[str] = None


class OwnerBreakdownOut(BaseModel):
    owner_cik: str
    owner_name: Optional[str] = None
    officer_title: Optional[str] = None
    ticker: Optional[str] = None
    window_days: int
    buy_count: int
    sell_count: int
    buy_shares: float
    sell_shares: float
    buy_notional: float
    sell_notional: float
    net_shares: float
    avg_sell_interval_days: Optional[float] = None
    pct_10b5_1: Optional[float] = None
    transactions: list[OwnerTxnOut] = Field(default_factory=list)


def _f(v) -> Optional[float]:
    if v is None:
        return None
    return float(v)


@router.get("/filings", response_model=FilingListOut)
async def list_filings(
    ticker: Optional[str] = Query(None),
    owner_cik: Optional[str] = Query(None),
    code: Optional[str] = Query(None, description="P or S"),
    days: int = Query(90, ge=1, le=730),
    sort: str = Query("transaction_date"),
    order: str = Query("desc"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Paginated Form 4 rows with sortable columns."""
    col = _SORTABLE.get(sort, InsiderFiling.transaction_date)
    direction = desc if order.lower() != "asc" else asc
    since = datetime.now(timezone.utc).date() - timedelta(days=days)

    filters = [InsiderFiling.transaction_date >= since]
    if ticker:
        filters.append(InsiderFiling.ticker == ticker.upper())
    if owner_cik:
        filters.append(InsiderFiling.owner_cik == owner_cik[:10])
    if code:
        filters.append(InsiderFiling.transaction_code == code.upper()[:4])

    total = (
        await db.execute(select(func.count()).select_from(InsiderFiling).where(*filters))
    ).scalar() or 0

    res = await db.execute(
        select(InsiderFiling)
        .where(*filters)
        .order_by(direction(col).nullslast(), desc(InsiderFiling.created_at))
        .offset(offset)
        .limit(limit)
    )
    rows = res.scalars().all()
    items = []
    for r in rows:
        items.append(
            FilingOut(
                filing_id=r.filing_id,
                accession=r.accession,
                ticker=r.ticker,
                owner_name=r.owner_name,
                owner_cik=r.owner_cik,
                officer_title=r.officer_title,
                is_director=bool(r.is_director),
                is_officer=bool(r.is_officer),
                transaction_code=r.transaction_code,
                shares=_f(r.shares),
                price=_f(r.price),
                notional=_f(r.notional),
                shares_after=_f(r.shares_after),
                stake_pct=_f(r.stake_pct),
                transaction_date=r.transaction_date,
                is_10b5_1=r.is_10b5_1,
                filing_url=r.filing_url,
                created_at=r.created_at,
            )
        )
    return FilingListOut(total=int(total), items=items)


@router.get("/owners/{owner_cik}", response_model=OwnerBreakdownOut)
async def owner_breakdown(
    owner_cik: str,
    ticker: Optional[str] = Query(None),
    days: int = Query(365, ge=30, le=730),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Per-person Form 4 breakdown (buys vs sells, cadence, 10b5-1 share)."""
    cik = owner_cik.strip()[:10]
    if not cik:
        raise HTTPException(status_code=400, detail="owner_cik required")
    since = datetime.now(timezone.utc).date() - timedelta(days=days)
    filters = [
        InsiderFiling.owner_cik == cik,
        InsiderFiling.transaction_date >= since,
    ]
    if ticker:
        filters.append(InsiderFiling.ticker == ticker.upper())

    res = await db.execute(
        select(InsiderFiling)
        .where(*filters)
        .order_by(asc(InsiderFiling.transaction_date), asc(InsiderFiling.created_at))
    )
    rows = list(res.scalars().all())
    if not rows:
        raise HTTPException(status_code=404, detail="No filings for this owner in window")

    buy_count = sell_count = 0
    buy_shares = sell_shares = buy_notional = sell_notional = 0.0
    ten_b5 = 0
    sell_dates = []
    txns = []
    for r in rows:
        code = (r.transaction_code or "").upper()
        sh = float(r.shares or 0)
        nt = float(r.notional or 0)
        if code == "P":
            buy_count += 1
            buy_shares += sh
            buy_notional += nt
        elif code == "S":
            sell_count += 1
            sell_shares += sh
            sell_notional += nt
            if r.transaction_date:
                sell_dates.append(r.transaction_date)
        if r.is_10b5_1 is True:
            ten_b5 += 1
        txns.append(
            OwnerTxnOut(
                accession=r.accession,
                ticker=r.ticker,
                transaction_code=r.transaction_code,
                shares=_f(r.shares),
                price=_f(r.price),
                notional=_f(r.notional),
                stake_pct=_f(r.stake_pct),
                transaction_date=r.transaction_date,
                is_10b5_1=r.is_10b5_1,
                filing_url=r.filing_url,
            )
        )

    avg_iv = None
    if len(sell_dates) >= 2:
        sell_dates = sorted(set(sell_dates))
        gaps = [(sell_dates[i] - sell_dates[i - 1]).days for i in range(1, len(sell_dates))]
        if gaps:
            avg_iv = sum(gaps) / len(gaps)

    first = rows[0]
    return OwnerBreakdownOut(
        owner_cik=cik,
        owner_name=first.owner_name,
        officer_title=first.officer_title,
        ticker=ticker.upper() if ticker else None,
        window_days=days,
        buy_count=buy_count,
        sell_count=sell_count,
        buy_shares=buy_shares,
        sell_shares=sell_shares,
        buy_notional=buy_notional,
        sell_notional=sell_notional,
        net_shares=buy_shares - sell_shares,
        avg_sell_interval_days=avg_iv,
        pct_10b5_1=(ten_b5 / len(rows)) if rows else None,
        transactions=txns,
    )
