"""briefing_advice.py — Template advice from investment_rules.json + book.

No LLM. Telegram copy must stay deterministic and cite the live rules file.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

_RULES_PATH = Path(__file__).resolve().parent.parent / "config" / "investment_rules.json"

EVENT_INSIDER_BUY = "insider_buy"
EVENT_INSIDER_SELL = "insider_sell"
EVENT_SOFT_STOP = "soft_stop"


def load_investment_rules() -> dict:
    try:
        return json.loads(_RULES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _upper_set(rules: dict, key: str) -> set[str]:
    return {str(t).upper() for t in rules.get(key, [])}


def watchlist_tier(ticker: str, rules: dict) -> Optional[str]:
    t = ticker.upper()
    if t in _upper_set(rules, "watchlist_tier_s"):
        return "S"
    if t in _upper_set(rules, "watchlist_tier_a"):
        return "A"
    if t in _upper_set(rules, "watchlist_tier_b"):
        return "B"
    return None


def vol_class(ticker: str, rules: dict) -> str:
    t = ticker.upper()
    if t in _upper_set(rules, "volatile_tickers"):
        return "volatile"
    if t in _upper_set(rules, "stable_tickers"):
        return "stable"
    return "unclassified"


def _news_bias(news: list) -> str:
    if not news:
        return "NONE"
    scores = [int(i.get("score") or 0) for i in news]
    avg = sum(scores) / len(scores)
    if avg >= 1.5:
        return "BULL"
    if avg <= -1.5:
        return "BEAR"
    return "MIXED"


def advice_lines(
    ticker: str,
    event: str,
    *,
    held: bool = False,
    sector_pct: Optional[float] = None,
    sector_cap: Optional[float] = None,
    ticker_sector: Optional[str] = None,
    snap: Optional[dict] = None,
    news: Optional[list] = None,
    rules: Optional[dict] = None,
    cluster_count: int = 1,
    stage: Optional[str] = None,
) -> list[str]:
    """Action lines for Telegram. Empty if rules file is missing."""
    rules = rules if rules is not None else load_investment_rules()
    if not rules:
        return []
    ticker = (ticker or "").upper()
    snap = snap or {}
    news = news or []
    bias = _news_bias(news)
    klass = vol_class(ticker, rules)
    tier = watchlist_tier(ticker, rules)
    t1 = rules.get("swing_target1_pct", 7.0)
    t2 = rules.get("swing_target2_pct", 12.0)
    swing_sl = rules.get("swing_stop_loss_pct", 5.0)
    max_swing = rules.get("swing_max_concurrent_trades", 2)
    risk_pct = rules.get("swing_risk_per_trade_pct", 1.0)
    vol_cool = rules.get("reentry_cooloff_volatile_days", 2)
    leaving = bool(snap.get("leaving"))
    light = snap.get("vol_ratio") is not None and snap["vol_ratio"] < 0.6 and snap.get("price_up") is False
    sector = ticker_sector or snap.get("sector") or "sector"
    lines: list[str] = []

    if ticker in _upper_set(rules, "avoid_tickers"):
        lines.append(f"{ticker} is on avoid_tickers — do not open (or re-open) a position.")

    if event == EVENT_INSIDER_BUY:
        lines.append("Do not chase this Form 4 — wait for YOUR entry, not the print.")
        if held:
            lines.append("Already in the book. No averaging down if red; add only if this was a planned scale-in.")
        elif tier:
            lines.append(
                f"Watchlist tier {tier} — in-universe. Still need a planned setup, defined exit, and size."
            )
        else:
            lines.append("Not on S/A/B watchlist — research only. Do not FOMO a new name off one filing.")
        if klass == "volatile":
            lines.append(
                f"VOLATILE: {vol_cool}-day cooloff, swing stop {swing_sl:g}%, "
                f"max {max_swing} concurrent swings, risk {risk_pct:g}% of book."
            )
        elif klass == "stable":
            bep = rules.get("stable_bep_trigger_pct", 2.0)
            lines.append(f"STABLE: BEP trigger {bep:g}%. Hard stop at entry, never moved against.")
        if ticker == "SNDK":
            ban = rules.get("sndk_strike3_ban_days", 5)
            lines.append(f"SNDK: 3-strike = {ban}-day ban, two-bucket system only.")
        if sector_pct is not None and sector_cap is not None:
            room = sector_cap - sector_pct
            if room <= 0:
                lines.append(
                    f"Sector {sector} {sector_pct:.0%} already at/over {sector_cap:.0%} cap — no add."
                )
            else:
                lines.append(
                    f"Sector {sector} {sector_pct:.0%} vs {sector_cap:.0%} cap "
                    f"({room:.0%} room). A full-size add must stay under the cap."
                )
        if cluster_count >= 3:
            lines.append(
                f"Cluster {cluster_count} unique buyers/30d is stronger — still not a market order. "
                f"T1 +{t1:g}% / T2 +{t2:g}%."
            )
        elif not held:
            lines.append(f"If this becomes a swing: T1 +{t1:g}%, T2 +{t2:g}%, hard stop at entry.")
        if leaving and not held:
            lines.append("Volume LEAVING on a down day — do not buy into distribution.")
        if bias == "BEAR":
            lines.append("Scored news is BEAR — the Form 4 does not override a broken tape.")
        lines.append("FOMO check: planned setup? exit defined? sized? If not — tomorrow, not now.")

    elif event == EVENT_INSIDER_SELL:
        if held:
            lines.append("Insider sell on a name we hold — default is respect it. Do not average down.")
        else:
            lines.append("Insider sell on an unheld name — log only unless you were about to buy.")
        if leaving:
            lines.append("Volume LEAVING confirms distribution — honor stops; no heroic hold.")
        elif light:
            lines.append("Light volume on the drop — shakeout possible, but do not add into an insider sale.")
        if klass == "volatile":
            lines.append(f"VOLATILE: if you exit, {vol_cool}-day cooloff, no same-day re-entry.")
        lines.append("Hard stop stays where it was set at entry — never moved against the position.")
        if bias == "BULL":
            lines.append("Bull headlines do not cancel an officer/director sale.")

    elif event == EVENT_SOFT_STOP:
        if stage == "eod":
            lines.append("EOD through the soft stop — exit at tomorrow's open unless you accept the gap.")
        elif leaving:
            lines.append("Soft stop + volume LEAVING (2× dump rule) — breakdown. Do not average down.")
        elif light:
            lines.append("Soft stop on light volume — shakeout possible. Still no averaging down; decide at the close.")
        else:
            lines.append("Soft stop hit — honor it or accept the gap. No adding.")
        if klass == "volatile":
            lines.append(f"VOLATILE: no same-day re-entry; {vol_cool}-day cooloff after a stop.")
        else:
            lines.append("Hard stop is the floor and is never moved against the position.")
        if bias == "BULL":
            lines.append("Bull news does not authorize averaging down through a stop.")
        lines.append("If you scratch: wait for a new planned entry, not the bounce.")

    # Cap so Telegram stays readable under the 3500-char body budget.
    return lines[:8]


def format_advice_block(**kwargs) -> str:
    lines = advice_lines(**kwargs)
    if not lines:
        return ""
    return "Advice\n" + "\n".join(f"- {line}" for line in lines)
