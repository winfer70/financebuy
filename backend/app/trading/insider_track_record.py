"""insider_track_record.py — Forward-return track record for a Form 4 filer.

Pure computation, decoupled from how price bars get fetched: routes/insider.py
(web API — async, cached yfinance via market.get_ohlcv_series) and
insider_monitor.py (Telegram — sync yfinance via a worker thread, matching
this module's other market_context.py helpers) each fetch bars their own way
and pass them in here, so the actual win-rate math lives in exactly one place
and both surfaces report the same thing for the same filing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional, Sequence, Tuple

from .insider_briefing import summarize_owner_history

HORIZON_DAYS = 30


@dataclass
class TrackRecord:
    """A historical pattern, not a forecast — see `label` for the caveat
    baked into the text itself."""

    sample_size: int
    evaluated: int
    win_rate: Optional[float] = None
    avg_aligned_return_pct: Optional[float] = None
    horizon_days: int = HORIZON_DAYS
    label: str = ""
    basis: str = ""


def _as_date(value) -> Optional[date]:
    if isinstance(value, date):
        return value
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def compute_track_record(
    rows: Sequence[dict],
    bars: Sequence[Tuple[str, float]],
    *,
    today: Optional[date] = None,
) -> Optional[TrackRecord]:
    """For each past open-market P/S trade in `rows`, check where the price
    (from `bars`) was ~30 days later. A "hit" is a buy followed by a gain,
    or a sell followed by a decline — the direction the trade implied.

    Args:
        rows: dicts with transaction_code / transaction_date / shares, for
            one owner+ticker (any mix of P/S — non-P/S rows are ignored).
        bars: (date_iso, close) pairs for that ticker, any order/dedup state.
        today: override "now" for deterministic tests.

    Returns:
        None if there's no meaningful basis (fewer than 2 open-market trades,
        or no price data at all). Otherwise a TrackRecord — `evaluated` may
        still be 0 if every trade is too recent to have 30-day forward data,
        in which case `label` explains that rather than showing a win rate.
    """
    ps_rows = [
        r for r in rows
        if (r.get("transaction_code") or "").upper() in ("P", "S") and r.get("transaction_date")
    ]
    sample_size = len(ps_rows)
    if sample_size < 2 or not bars:
        return None

    today = today or date.today()
    by_date = {d: c for d, c in bars}
    sorted_dates = sorted(by_date)

    def _close_on_or_after(target: date) -> Optional[float]:
        target_s = target.isoformat()
        for ds in sorted_dates:
            if ds >= target_s:
                return by_date[ds]
        return None

    aligned_returns: list[float] = []
    hits = 0
    horizon = timedelta(days=HORIZON_DAYS)
    for r in ps_rows:
        txn_date = _as_date(r.get("transaction_date"))
        if txn_date is None:
            continue
        future_date = txn_date + horizon
        if future_date > today:
            continue  # not enough time has passed yet to score this one
        txn_close = _close_on_or_after(txn_date)
        future_close = _close_on_or_after(future_date)
        if not txn_close or not future_close:
            continue
        fwd_return = (future_close - txn_close) / txn_close
        code = (r.get("transaction_code") or "").upper()
        aligned = fwd_return if code == "P" else -fwd_return
        aligned_returns.append(aligned)
        if aligned > 0:
            hits += 1

    evaluated = len(aligned_returns)
    if evaluated < 2:
        return TrackRecord(
            sample_size=sample_size,
            evaluated=0,
            label="Not enough time has passed since this owner's trades to score a track record yet.",
            basis=f"{sample_size} open-market trade(s) on file, none {HORIZON_DAYS}+ days old with price data.",
        )

    win_rate = hits / evaluated
    avg_aligned = sum(aligned_returns) / evaluated

    last_code = (ps_rows[-1].get("transaction_code") or "").upper()
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
            {"transaction_date": _as_date(r.get("transaction_date")), "shares": float(r.get("shares") or 0)}
            for r in ps_rows if (r.get("transaction_code") or "").upper() == "S"
        ])
        if sell_pattern.looks_scheduled:
            scheduled_note = (
                " Note: this owner's sells look scheduled (10b5-1-style), which weakens "
                "how predictive any single filing is."
            )

    label = (
        f"{'Favorable' if win_rate >= 0.65 else 'Unfavorable' if win_rate <= 0.35 else 'Mixed'} "
        f"track record: {hits}/{evaluated} trades ({win_rate:.0%}) preceded a move in the "
        f"implied direction, avg {avg_aligned:+.1%} over {HORIZON_DAYS}d — {outlook}.{scheduled_note}"
    )

    return TrackRecord(
        sample_size=sample_size,
        evaluated=evaluated,
        win_rate=win_rate,
        avg_aligned_return_pct=avg_aligned * 100,
        horizon_days=HORIZON_DAYS,
        label=label,
        basis=f"{evaluated} of {sample_size} open-market P/S trades had {HORIZON_DAYS}-day forward price data.",
    )
