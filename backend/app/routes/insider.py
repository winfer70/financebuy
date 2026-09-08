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
from ..trading.insider_briefing import summarize_owner_history
from .auth_routes import get_current_user
from .market import get_ohlcv_series

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


class TrackRecordOut(BaseModel):
    """Forward-return track record over this owner's past open-market P/S
    trades — a historical pattern, not a guarantee of future performance."""

    sample_size: int
    evaluated: int
    win_rate: Optional[float] = None
    avg_aligned_return_pct: Optional[float] = None
    horizon_days: int
    label: str
    basis: str


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
    track_record: Optional[TrackRecordOut] = None


def _f(v) -> Optional[float]:
    if v is None:
        return None
    return float(v)


_TRACK_RECORD_HORIZON_DAYS = 30


async def _compute_track_record(
    rows: list[InsiderFiling],
    ticker: Optional[str],
) -> Optional[TrackRecordOut]:
    """For each past open-market P/S trade by this owner, check where the
    stock's price was ~30 days later. A "win" is a buy followed by a gain,
    or a sell followed by a decline — the direction the trade implied. This
    describes a historical pattern only; it is not a forecast.

    Only meaningful scoped to a single ticker (the UI always passes one when
    opening this panel from a filing row) — returns None otherwise, or when
    there isn't enough history to say anything.
    """
    if not ticker:
        return None
    ps_rows = [
        r for r in rows
        if (r.transaction_code or "").upper() in ("P", "S") and r.transaction_date
    ]
    sample_size = len(ps_rows)
    if sample_size < 2:
        return None

    today = date.today()
    earliest = min(r.transaction_date for r in ps_rows)
    years_needed = max(1, min(6, (today - earliest).days // 365 + 2))
    try:
        series = await get_ohlcv_series(ticker, years_needed)
    except Exception:
        return None
    bars = series.bars
    if not bars:
        return None

    by_date = {b.date: b.close for b in bars}
    sorted_dates = sorted(by_date)

    def _close_on_or_after(target: date) -> Optional[float]:
        target_s = target.isoformat()
        for ds in sorted_dates:
            if ds >= target_s:
                return by_date[ds]
        return None

    aligned_returns: list[float] = []
    hits = 0
    horizon = timedelta(days=_TRACK_RECORD_HORIZON_DAYS)
    for r in ps_rows:
        future_date = r.transaction_date + horizon
        if future_date > today:
            continue  # not enough time has passed yet to score this one
        txn_close = _close_on_or_after(r.transaction_date)
        future_close = _close_on_or_after(future_date)
        if not txn_close or not future_close:
            continue
        fwd_return = (future_close - txn_close) / txn_close
        code = (r.transaction_code or "").upper()
        aligned = fwd_return if code == "P" else -fwd_return
        aligned_returns.append(aligned)
        if aligned > 0:
            hits += 1

    evaluated = len(aligned_returns)
    if evaluated < 2:
        return TrackRecordOut(
            sample_size=sample_size,
            evaluated=0,
            horizon_days=_TRACK_RECORD_HORIZON_DAYS,
            label="Not enough time has passed since this owner's trades to score a track record yet.",
            basis=f"{sample_size} open-market trade(s) on file, none {_TRACK_RECORD_HORIZON_DAYS}+ days old with price data.",
        )

    win_rate = hits / evaluated
    avg_aligned = sum(aligned_returns) / evaluated

    last_code = (ps_rows[-1].transaction_code or "").upper()
    last_action = "buying" if last_code == "P" else "selling"

    if win_rate >= 0.65:
        outlook = (
            f"their {last_action} has historically preceded a favorable move — "
            "the current filing may follow the same pattern, though past results don't guarantee it"
        )
    elif win_rate <= 0.35:
        outlook = (
            f"their {last_action} has not reliably preceded a favorable move — "
            "treat this filing as a weak signal on its own"
        )
    else:
        outlook = "no strong directional signal from this owner's past trades alone"

    scheduled_note = ""
    if last_code == "S":
        sell_pattern = summarize_owner_history([
            {"transaction_date": r.transaction_date, "shares": float(r.shares or 0)}
            for r in ps_rows if (r.transaction_code or "").upper() == "S"
        ])
        if sell_pattern.looks_scheduled:
            scheduled_note = (
                " Note: this owner's sells look scheduled (10b5-1-style), which weakens "
                "how predictive any single filing is."
            )

    label = (
        f"{'Favorable' if win_rate >= 0.65 else 'Unfavorable' if win_rate <= 0.35 else 'Mixed'} "
        f"track record: {hits}/{evaluated} trades ({win_rate:.0%}) preceded a move in the "
        f"implied direction, avg {avg_aligned:+.1%} over {_TRACK_RECORD_HORIZON_DAYS}d — "
        f"{outlook}.{scheduled_note}"
    )

    return TrackRecordOut(
        sample_size=sample_size,
        evaluated=evaluated,
        win_rate=win_rate,
        avg_aligned_return_pct=avg_aligned * 100,
        horizon_days=_TRACK_RECORD_HORIZON_DAYS,
        label=label,
        basis=f"{evaluated} of {sample_size} open-market P/S trades had {_TRACK_RECORD_HORIZON_DAYS}-day forward price data.",
    )


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
        # Most Form 4 activity for a typical executive is grants (A), tax
        # withholding on vests (F), and option exercises (M) rather than
        # open-market P/S trades — counting only "P"/"S" left this panel
        # showing all-zero figures for owners with real filings but no
        # open-market trades in the window. acquired_disposed is the SEC
        # form's own A/D flag and covers every transaction type, so it
        # reflects the owner's real net share change; transaction_code is
        # kept as a fallback for any older/malformed row missing it.
        ad = (r.acquired_disposed or "").upper()
        if not ad:
            ad = "A" if code == "P" else "D" if code == "S" else ""
        sh = float(r.shares or 0)
        nt = float(r.notional or 0)
        if ad == "A":
            buy_count += 1
            buy_shares += sh
            buy_notional += nt
        elif ad == "D":
            sell_count += 1
            sell_shares += sh
            sell_notional += nt
        # Sell cadence is specifically about open-market selling intent
        # (e.g. a 10b5-1 plan's fixed schedule) — tax-withholding disposals
        # on every vest would swamp this with noise unrelated to trading.
        if code == "S" and r.transaction_date:
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

    track_record = await _compute_track_record(rows, ticker)

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
        track_record=track_record,
    )
