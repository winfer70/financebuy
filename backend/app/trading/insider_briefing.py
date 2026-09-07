"""insider_briefing.py — Concern heuristic, owner pattern, redesigned Telegram copy."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class OwnerPattern:
    count: int = 0
    avg_shares: float = 0.0
    avg_interval_days: Optional[float] = None
    looks_scheduled: bool = False

    @property
    def ordinal(self) -> str:
        n = self.count
        if n % 100 in (11, 12, 13):
            suf = "th"
        else:
            suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return f"{n}{suf}"


@dataclass
class PositionBrief:
    quantity: float
    purchase_price: float
    hard_stop: Optional[float] = None
    soft_stop: Optional[float] = None


@dataclass
class ConsensusBrief:
    rating: Optional[str] = None  # e.g. Strong Buy
    n_analysts: Optional[int] = None
    n_buy: Optional[int] = None
    target: Optional[float] = None
    upside_pct: Optional[float] = None


def summarize_owner_history(
    prior_rows: list[dict],
    *,
    current_shares: float = 0.0,
    current_date: Optional[date] = None,
) -> OwnerPattern:
    """Build repeat-seller/buyer pattern from ingested filings (same owner+ticker+code).

    ``prior_rows`` should already be filtered to this owner/ticker/code and include
    the current filing (or we append current_shares/date). Sorted oldest→newest.
    """
    dated = []
    for r in prior_rows:
        d = r.get("transaction_date")
        if isinstance(d, str):
            try:
                d = date.fromisoformat(d[:10])
            except ValueError:
                d = None
        shares = float(r.get("shares") or 0)
        if d is not None:
            dated.append((d, shares))
    if current_date is not None and current_shares:
        if not any(d == current_date for d, _ in dated):
            dated.append((current_date, current_shares))
    dated.sort(key=lambda x: x[0])
    if not dated:
        return OwnerPattern()
    count = len(dated)
    avg_shares = sum(s for _, s in dated) / count
    intervals = []
    for i in range(1, len(dated)):
        intervals.append((dated[i][0] - dated[i - 1][0]).days)
    avg_iv = sum(intervals) / len(intervals) if intervals else None
    looks = False
    if count >= 3 and avg_iv is not None and 20 <= avg_iv <= 100:
        # Similar size each time → scheduled cadence
        if avg_shares > 0:
            spreads = [abs(s - avg_shares) / avg_shares for _, s in dated]
            looks = sum(1 for x in spreads if x <= 0.15) >= max(2, count - 1)
    return OwnerPattern(
        count=count,
        avg_shares=avg_shares,
        avg_interval_days=avg_iv,
        looks_scheduled=looks,
    )


def is_c_suite(filing: dict) -> bool:
    title = (filing.get("officer_title") or "").lower()
    if any(k in title for k in ("ceo", "cfo", "chief executive", "chief financial", "president")):
        return True
    return False


def concern_level(
    filing: dict,
    *,
    cluster_count: int = 1,
    pattern: Optional[OwnerPattern] = None,
) -> str:
    """LOW / MEDIUM / HIGH for the Telegram headline.

    Weights: 10b5-1 (largest), cluster, stake %, C-suite.
    """
    code = (filing.get("transaction_code") or "").upper()
    is_10b5 = filing.get("is_10b5_1") is True
    stake = filing.get("stake_pct")
    csuite = is_c_suite(filing)
    score = 0

    if code == "S":
        if is_10b5:
            score -= 3
        else:
            score += 2
        if stake is not None:
            if stake >= 0.25:
                score += 3
            elif stake >= 0.10:
                score += 2
            elif stake >= 0.05:
                score += 1
            elif stake < 0.02:
                score -= 1
        if csuite and not is_10b5:
            score += 2
        elif csuite:
            score += 1
        if cluster_count >= 3:
            score += 3
        elif cluster_count >= 2:
            score += 1
        if pattern and pattern.looks_scheduled and is_10b5:
            score -= 1
    else:  # buys / other
        if is_10b5:
            score -= 2
        if cluster_count >= 3:
            score += 2
        if csuite:
            score += 1
        if stake is not None and stake >= 0.10:
            score += 1

    if score <= 0:
        return "LOW"
    if score <= 3:
        return "MEDIUM"
    return "HIGH"


def _role_label(filing: dict) -> str:
    if filing.get("officer_title"):
        return filing["officer_title"]
    if filing.get("is_director"):
        return "director"
    if filing.get("is_officer"):
        return "officer"
    if filing.get("is_ten_percent"):
        return "10% owner"
    return "insider"


def _plan_line(is_10b5) -> str:
    if is_10b5 is True:
        return "10b5-1 plan: YES ✓"
    if is_10b5 is False:
        return "10b5-1 plan: NO — discretionary"
    return "10b5-1 plan: unknown"


def format_volume_compact(snap: dict) -> str:
    parts = []
    ratio = snap.get("vol_ratio")
    if ratio is None:
        parts.append("Volume n/a")
    else:
        day = "up" if snap.get("price_up") else "down"
        tag = " LEAVING" if snap.get("leaving") else ""
        parts.append(f"Volume{tag} {ratio:.1f}× 50d avg, {day} day")
    etf = snap.get("sector_etf")
    sratio = snap.get("sector_vol_ratio")
    if etf and sratio is not None:
        sday = "up" if snap.get("sector_price_up") else "down"
        sector = snap.get("sector") or "sector"
        parts.append(f"Sector ({etf}/{sector}) {sratio:.1f}× 50d, {sday} day")
    return " | ".join(parts)


def format_news_digest(items: list[dict], *, status: str = "ok") -> list[str]:
    """status: ok | empty | error. Distinguishes checked-empty from check-failed."""
    if status == "error":
        return ["News (48h): could not query DB — do not treat as 'no news'"]
    if not items:
        return ["News (48h): 0 articles scored for this ticker (worker checked)"]
    scores = [int(i.get("score") or 0) for i in items]
    avg = sum(scores) / len(scores)
    if avg >= 2:
        bias = "BULL"
    elif avg <= -2:
        bias = "BEAR"
    else:
        bias = "MIXED"
    titles = [((i.get("title") or "").strip()) for i in items[:4] if (i.get("title") or "").strip()]
    head = f"News (48h): {len(items)} articles — avg {avg:+.1f} {bias}"
    if not titles:
        return [head]
    # One compact line of titles when short enough
    joined = ", ".join(t[:60] for t in titles)
    if len(joined) <= 180:
        return [head, f"  {joined}"]
    lines = [head]
    for t in titles:
        lines.append(f"  • {t[:90]}")
    return lines


def format_insider_telegram(
    filing: dict,
    *,
    snap: dict,
    news: list[dict],
    news_status: str = "ok",
    cluster_count: int = 1,
    cluster_kind: str = "buyers",  # buyers | sellers
    pattern: Optional[OwnerPattern] = None,
    position: Optional[PositionBrief] = None,
    consensus: Optional[ConsensusBrief] = None,
    advice: str = "",
    sector_pct: Optional[float] = None,
    sector_cap: Optional[float] = None,
    ticker_sector: Optional[str] = None,
    notional: Optional[float] = None,
    reasons: Optional[list] = None,
) -> tuple[str, str]:
    """Return (title, body) for Telegram/ntfy. Body capped at 3500 chars."""
    ticker = (filing.get("ticker") or "").upper()
    code = (filing.get("transaction_code") or "").upper()
    action = "BUY" if code == "P" else "SELL" if code == "S" else code or "TXN"
    usd = float(notional) if notional is not None else float(filing.get("shares") or 0) * float(
        filing.get("price") or 0
    )
    concern = concern_level(filing, cluster_count=cluster_count, pattern=pattern)
    emoji = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴"}.get(concern, "⚪")
    title = f"{emoji} {ticker} insider {action} — ${usd:,.0f} ({concern} concern)"

    owner = filing.get("owner_name") or "unknown"
    role = _role_label(filing)
    shares = float(filing.get("shares") or 0)
    price = float(filing.get("price") or 0)
    parts: list[str] = []
    parts.append(f"{owner}, {role}")
    txn_date = filing.get("transaction_date")
    if txn_date is not None:
        if hasattr(txn_date, "isoformat"):
            txn_s = txn_date.isoformat()[:10]
        else:
            txn_s = str(txn_date)[:10]
        if txn_s:
            parts.append(f"Trade date: {txn_s}")
    parts.append(f"{shares:g} sh @ ${price:,.2f} | {_plan_line(filing.get('is_10b5_1'))}")

    stake = filing.get("stake_pct")
    if stake is not None and code == "S":
        parts.append(f"Stake sold: {stake:.1%} of holdings")
    elif filing.get("shares_after") is not None:
        parts.append(f"Shares after: {float(filing['shares_after']):g}")

    if pattern and pattern.count >= 2:
        iv = (
            f", ~{pattern.avg_interval_days:.0f}-day intervals"
            if pattern.avg_interval_days is not None
            else ""
        )
        note = " — looks scheduled, not opportunistic" if pattern.looks_scheduled else ""
        parts.append("")
        parts.append(
            f"Pattern: {pattern.ordinal} {action.lower()} by this insider in 12mo"
        )
        parts.append(f"  avg {pattern.avg_shares:,.0f} sh{iv}{note}")
    elif pattern and pattern.count == 1:
        parts.append("")
        parts.append("Pattern: first filing by this insider we have in 12mo")

    parts.append("")
    verb = "sold" if code == "S" else "bought"
    other = max(cluster_count - 1, 0)
    if cluster_count <= 1:
        parts.append(f"Cluster: 1/1 insiders {verb} in trailing 30d (no other officers)")
    else:
        parts.append(
            f"Cluster: {cluster_count} unique {cluster_kind} / 30d "
            f"({other} other insider(s) also {verb})"
        )

    if position is not None:
        stop = position.soft_stop if position.soft_stop is not None else position.hard_stop
        stop_s = f", stop ${stop:,.2f}" if stop is not None else ""
        parts.append(
            f"Your position: {position.quantity:g} sh, BEP ${position.purchase_price:,.2f}{stop_s}"
        )
    else:
        parts.append("Your position: none open")

    if consensus and (consensus.target or consensus.rating):
        bits = []
        if consensus.rating:
            if consensus.n_buy and consensus.n_analysts:
                bits.append(f"{consensus.rating} ({consensus.n_buy}/{consensus.n_analysts})")
            else:
                bits.append(consensus.rating)
        if consensus.target is not None:
            up = f" ({consensus.upside_pct:+.0f}%)" if consensus.upside_pct is not None else ""
            bits.append(f"target ${consensus.target:,.2f}{up}")
        parts.append("Consensus: " + ", ".join(bits))

    if sector_pct is not None:
        cap_s = f" vs {sector_cap:.0%} cap" if sector_cap is not None else ""
        sector = ticker_sector or snap.get("sector") or "sector"
        parts.append(f"Sector book: {sector} {sector_pct:.0%}{cap_s}")

    parts.append("")
    parts.append(format_volume_compact(snap))
    parts.extend(format_news_digest(news, status=news_status))

    url = filing.get("filing_url") or ""
    if url:
        parts.append("")
        parts.append(f"Filing: {url}")

    if reasons:
        parts.append("")
        parts.append("Gate: " + "; ".join(reasons))

    if advice:
        parts.append("")
        parts.append(advice)

    body = "\n".join(parts)[:3500]
    return title, body
