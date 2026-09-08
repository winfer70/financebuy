"""market_context.py — Volume + scored-news snapshot for alert copy.

Reuses the scanner's 50-day volume-ratio definition (current bar vs prior 50)
and the same GICS→sector-ETF map. Does not import scanner_worker (that module
creates a DB engine on import).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import yfinance as yf
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import NewsArticle, NewsArticleTicker

from .briefing_advice import (
    EVENT_INSIDER_BUY,
    EVENT_INSIDER_SELL,
    EVENT_SOFT_STOP,
    format_advice_block,
)
SECTOR_ETFS = {
    "Technology": "XLK",
    "Communication Services": "XLC",
    "Consumer Discretionary": "XLY",
    "Financials": "XLF",
    "Healthcare": "XLV",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
    "Consumer Staples": "XLP",
}

VOLUME_SURGE = 2.0
LIGHT_VOLUME = 0.6


def _volume_ratio(df: pd.DataFrame) -> tuple[float, bool]:
    """Current volume vs mean of previous up-to-50 bars; True if last close > prior close."""
    if df is None or len(df) < 3 or "Volume" not in df.columns:
        return 0.0, False
    avg_vol = df["Volume"].iloc[:-1].tail(50).mean()
    if avg_vol == 0 or pd.isna(avg_vol):
        return 0.0, False
    ratio = float(df["Volume"].iloc[-1] / avg_vol)
    price_up = float(df["Close"].iloc[-1]) > float(df["Close"].iloc[-2])
    return ratio, price_up


def _ohlcv(symbol: str, period: str = "3mo") -> Optional[pd.DataFrame]:
    t = yf.Ticker(symbol)
    df = t.history(period=period, auto_adjust=True)
    if df is None or df.empty:
        return None
    return df


def fetch_price_history_bars(symbol: str, period: str = "2y") -> list[tuple[str, float]]:
    """(date_iso, close) pairs for a symbol — sync/yfinance, same as the
    other helpers here. Used for the insider track-record calculation
    (insider_track_record.py), which needs enough history to cover
    whatever window the caller's filings span.
    """
    df = _ohlcv(symbol, period=period)
    if df is None:
        return []
    return [(idx.strftime("%Y-%m-%d"), float(row["Close"])) for idx, row in df.iterrows()]


def fetch_volume_snapshot(ticker: str, sector: Optional[str] = None) -> dict:
    """Sync yfinance snapshot: name volume vs 50d avg, and sector ETF if known."""
    out = {
        "ticker": ticker.upper(),
        "vol_ratio": None,
        "price_up": None,
        "leaving": False,
        "sector": sector,
        "sector_etf": None,
        "sector_vol_ratio": None,
        "sector_price_up": None,
    }
    df = _ohlcv(ticker)
    if df is not None:
        ratio, up = _volume_ratio(df)
        out["vol_ratio"] = round(ratio, 2)
        out["price_up"] = up
        out["leaving"] = bool(ratio >= VOLUME_SURGE and not up)

    sector_name = sector
    if not sector_name:
        try:
            info = yf.Ticker(ticker).info or {}
            sector_name = info.get("sector")
            out["sector"] = sector_name
        except Exception:
            sector_name = None

    etf = SECTOR_ETFS.get(sector_name or "")
    if etf:
        out["sector_etf"] = etf
        sdf = _ohlcv(etf)
        if sdf is not None:
            sratio, sup = _volume_ratio(sdf)
            out["sector_vol_ratio"] = round(sratio, 2)
            out["sector_price_up"] = sup
    return out


def _score_label(score: int) -> str:
    if score >= 2:
        return "BULL"
    if score <= -2:
        return "BEAR"
    return "MIXED"


def _severity(score: int) -> str:
    mag = abs(int(score))
    if mag >= 4:
        return "high"
    if mag >= 2:
        return "med"
    return "low"


async def fetch_ticker_news(session: AsyncSession, ticker: str, hours: int = 48, limit: int = 5) -> list[dict]:
    """Recent LLM-scored articles for a ticker (news_article_tickers)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = (
        select(NewsArticleTicker, NewsArticle)
        .join(NewsArticle, NewsArticle.article_id == NewsArticleTicker.article_id)
        .where(
            NewsArticleTicker.ticker == ticker.upper(),
            NewsArticle.scored_at >= cutoff,
        )
        .order_by(desc(NewsArticle.scored_at))
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    items = []
    for nt, art in rows:
        score = int(nt.score if nt.score is not None else 0)
        items.append(
            {
                "title": (art.title or "")[:120],
                "score": score,
                "label": _score_label(score),
                "severity": _severity(score),
                "source": art.source,
                "reasoning": (nt.reasoning or art.general_reasoning or "")[:180],
            }
        )
    return items


def format_volume_lines(snap: dict) -> list[str]:
    lines = []
    ratio = snap.get("vol_ratio")
    up = snap.get("price_up")
    if ratio is None:
        lines.append("Volume: n/a")
    else:
        day = "up day" if up else "down day"
        if snap.get("leaving"):
            lines.append(f"Volume LEAVING: {ratio:.1f}× 50d avg on a {day} (scanner 2× dump rule)")
        elif ratio >= VOLUME_SURGE and up:
            lines.append(f"Volume surge {ratio:.1f}× 50d avg on an {day} — not distribution")
        elif ratio < LIGHT_VOLUME and not up:
            lines.append(f"Light volume ({ratio:.1f}× 50d avg) on the drop — no dump confirmation")
        else:
            lines.append(f"Volume {ratio:.1f}× 50d avg, {day}")

    etf = snap.get("sector_etf")
    sratio = snap.get("sector_vol_ratio")
    if etf and sratio is not None:
        sday = "up" if snap.get("sector_price_up") else "down"
        sector = snap.get("sector") or "sector"
        lines.append(f"Sector {sector} ({etf}): {sratio:.1f}× 50d avg, {sday} day")
    return lines


def format_news_lines(items: list[dict], *, status: str = "ok") -> list[str]:
    """status ok|empty|error. Prefer titles; keep scores for soft-stop detail."""
    from .insider_briefing import format_news_digest

    # Soft-stop still wants score lines when present; digests handle empty/error.
    if status != "ok" or not items:
        return format_news_digest(items or [], status=status if status != "ok" else "empty")
    scores = [i["score"] for i in items]
    avg = sum(scores) / len(scores)
    lines = [f"News (48h): {len(items)} articles — avg {avg:+.1f} {_score_label(round(avg))}"]
    titles = [(i.get("title") or "").strip() for i in items[:4] if (i.get("title") or "").strip()]
    if titles:
        joined = ", ".join(t[:60] for t in titles)
        if len(joined) <= 180:
            lines.append(f"  {joined}")
        else:
            for t in titles:
                lines.append(f"  • {t[:90]}")
    for i in items[:3]:
        if i.get("reasoning"):
            lines.append(f"  {i['score']:+d} {i['label']}: {i['reasoning'][:120]}")
    return lines


def format_soft_stop_report(
    ticker: str,
    price: float,
    soft_stop: float,
    stage: str,
    snap: dict,
    news: list[dict],
    *,
    held: bool = True,
    ticker_sector: Optional[str] = None,
    rules: Optional[dict] = None,
    news_status: str = "ok",
    position=None,
) -> str:
    """Telegram/ntfy body. Keep under Telegram's 4096-char limit."""
    pct = ((price - soft_stop) / soft_stop * 100) if soft_stop else 0.0
    if stage == "eod":
        head = (
            f"{ticker} CLOSED at ${price:.2f} vs soft stop ${soft_stop:.2f} ({pct:+.1f}%). "
            "Exit at tomorrow's open unless this is a gap you accept."
        )
    else:
        head = (
            f"{ticker} last ${price:.2f} vs soft stop ${soft_stop:.2f} ({pct:+.1f}%). "
            "Shakeout vs breakdown — check volume and news before acting."
        )
    parts = [head, ""]
    parts.extend(format_volume_lines(snap))
    parts.append("")
    parts.extend(format_news_lines(news, status=news_status))
    advice = format_advice_block(
        ticker=ticker,
        event=EVENT_SOFT_STOP,
        held=held,
        ticker_sector=ticker_sector or snap.get("sector"),
        snap=snap,
        news=news,
        rules=rules,
        stage=stage,
        position=position,
    )
    if advice:
        parts.append("")
        parts.append(advice)
    text = "\n".join(parts)
    return text[:3500]


def format_insider_report(
    filing: dict,
    reasons: list,
    snap: dict,
    news: list[dict],
    *,
    cluster_count: int = 1,
    sector_pct: Optional[float] = None,
    sector_cap: Optional[float] = None,
    ticker_sector: Optional[str] = None,
    notional: Optional[float] = None,
    held: bool = False,
    rules: Optional[dict] = None,
    pattern=None,
    position=None,
    consensus=None,
    short_interest=None,
    news_status: str = "ok",
) -> str:
    """Telegram/ntfy body for a gated Form 4 (redesigned template)."""
    from .insider_briefing import format_insider_telegram

    code = (filing.get("transaction_code") or "").upper()
    event = EVENT_INSIDER_SELL if code == "S" else EVENT_INSIDER_BUY
    advice = format_advice_block(
        ticker=(filing.get("ticker") or ""),
        event=event,
        held=held,
        sector_pct=sector_pct,
        sector_cap=sector_cap,
        ticker_sector=ticker_sector or snap.get("sector"),
        snap=snap,
        news=news,
        rules=rules,
        cluster_count=cluster_count,
        position=position,
        consensus=consensus,
        short_interest=short_interest,
    )
    _title, body = format_insider_telegram(
        filing,
        snap=snap,
        news=news,
        news_status=news_status,
        cluster_count=cluster_count,
        cluster_kind="sellers" if code == "S" else "buyers",
        pattern=pattern,
        position=position,
        consensus=consensus,
        advice=advice,
        sector_pct=sector_pct,
        sector_cap=sector_cap,
        ticker_sector=ticker_sector,
        notional=notional,
        reasons=reasons,
    )
    return body


def format_insider_title(
    filing: dict,
    *,
    notional: Optional[float] = None,
    cluster_count: int = 1,
    pattern=None,
) -> str:
    from .insider_briefing import concern_level

    ticker = (filing.get("ticker") or "").upper()
    code = (filing.get("transaction_code") or "").upper()
    action = "BUY" if code == "P" else "SELL" if code == "S" else code or "TXN"
    usd = float(notional) if notional is not None else float(filing.get("shares") or 0) * float(
        filing.get("price") or 0
    )
    concern = concern_level(filing, cluster_count=cluster_count, pattern=pattern)
    emoji = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴"}.get(concern, "⚪")
    return f"{emoji} {ticker} insider {action} — ${usd:,.0f} ({concern} concern)"
