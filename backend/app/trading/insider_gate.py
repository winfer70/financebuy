"""insider_gate.py — Decide whether an insider filing is worth a Telegram briefing.

Uses GICS sector weights (portfolio_positions.sector), NOT is_semi.
Integrity flags come from the same thresholds as fundamentals.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, Optional


DEFAULT_SECTOR_CAP = Decimal("0.30")
DEFAULT_MIN_BUY_USD = Decimal("25000")
DE_RATIO_CRITICAL = 500.0
DE_RATIO_WARN = 200.0


@dataclass
class BookSnapshot:
    total_value: Decimal
    sector_values: dict  # str -> Decimal
    held_tickers: set
    avoid_tickers: set
    sector_cap: Decimal = DEFAULT_SECTOR_CAP
    min_buy_usd: Decimal = DEFAULT_MIN_BUY_USD
    # ticker -> {quantity, purchase_price, hard_stop, soft_stop}
    positions: dict = field(default_factory=dict)


@dataclass
class Integrity:
    debt_to_equity: Optional[float] = None
    insider_net_12m: Optional[float] = None


@dataclass
class GateResult:
    worth_telegram: bool
    in_app: bool
    severity: str
    event_type: str
    reasons: list = field(default_factory=list)
    cluster_count: int = 0
    sector_pct: Optional[float] = None
    notional: Decimal = Decimal("0")


def _notional(filing: dict) -> Decimal:
    shares = Decimal(str(filing.get("shares") or 0))
    price = Decimal(str(filing.get("price") or 0))
    return shares * price


def evaluate_filing(
    filing: dict,
    book: BookSnapshot,
    *,
    ticker_sector: Optional[str] = None,
    cluster_count: int = 1,
    integrity: Optional[Integrity] = None,
) -> GateResult:
    """Pure gate. No I/O.

    Telegram only for:
      - Open-market SELL (S) on a ticker we hold
      - Open-market BUY (P) by officer/director (or cluster >= 3), not 10b5-1,
        not avoid-list, sector under cap, notional >= min, no critical D/E
    """
    integrity = integrity or Integrity()
    code = (filing.get("transaction_code") or "").upper()
    ticker = (filing.get("ticker") or "").upper()
    notional = _notional(filing)
    reasons: list[str] = []
    held = ticker in book.held_tickers

    sector_pct = None
    if ticker_sector and book.total_value > 0:
        sec_val = book.sector_values.get(ticker_sector, Decimal("0"))
        sector_pct = float(sec_val / book.total_value)

    if code == "S":
        if held:
            reasons.append("insider sell on a name we hold")
            # Still Telegram — concern_level in the body distinguishes 10b5-1 routine vs dump.
            sev = "warning" if filing.get("is_10b5_1") is True else "critical"
            stake = filing.get("stake_pct")
            if filing.get("is_10b5_1") is True and stake is not None and float(stake) < 0.05:
                sev = "info"
            return GateResult(
                True, True, sev, "insider_sell", reasons, cluster_count, sector_pct, notional
            )
        return GateResult(False, False, "info", "insider_sell", ["sell on unheld name — log only"], cluster_count, sector_pct, notional)

    if code != "P":
        return GateResult(False, False, "info", "insider_other", [f"code {code} not P/S"], cluster_count, sector_pct, notional)

    # Buys
    in_app = True
    event = "insider_buy"
    if ticker in book.avoid_tickers:
        reasons.append("avoid_tickers")
        return GateResult(False, True, "info", event, reasons, cluster_count, sector_pct, notional)
    if filing.get("is_10b5_1") is True:
        reasons.append("10b5-1 plan — scheduled, not discretionary")
        return GateResult(False, True, "info", event, reasons, cluster_count, sector_pct, notional)
    if notional < book.min_buy_usd:
        reasons.append(f"notional ${notional:.0f} below ${book.min_buy_usd:.0f}")
        return GateResult(False, True, "info", event, reasons, cluster_count, sector_pct, notional)
    if sector_pct is not None and Decimal(str(sector_pct)) >= book.sector_cap:
        reasons.append(f"sector {ticker_sector} already {sector_pct:.0%} >= cap {float(book.sector_cap):.0%}")
        return GateResult(False, True, "warning", event, reasons, cluster_count, sector_pct, notional)
    if integrity.debt_to_equity is not None and integrity.debt_to_equity >= DE_RATIO_CRITICAL:
        reasons.append(f"D/E {integrity.debt_to_equity:.0f}% critical")
        return GateResult(False, True, "warning", event, reasons, cluster_count, sector_pct, notional)

    role_ok = bool(filing.get("is_officer") or filing.get("is_director"))
    cluster_ok = cluster_count >= 3
    if not role_ok and not cluster_ok:
        reasons.append("not officer/director and cluster < 3")
        return GateResult(False, True, "info", event, reasons, cluster_count, sector_pct, notional)

    if cluster_ok:
        event = "insider_cluster"
        reasons.append(f"cluster {cluster_count} unique buyers / 30d")
    if role_ok:
        title = filing.get("officer_title") or ("director" if filing.get("is_director") else "officer")
        reasons.append(f"open-market buy by {title}")
    if integrity.insider_net_12m is not None and integrity.insider_net_12m < -0.02:
        reasons.append(f"yfinance 12m insider net still selling ({integrity.insider_net_12m:.1%})")

    severity = "warning" if cluster_ok or role_ok else "info"
    return GateResult(True, in_app, severity, event, reasons, cluster_count, sector_pct, notional)


def sector_exposure(positions: Iterable[dict], total_value: Decimal) -> dict:
    """positions: {sector, market_value}."""
    out: dict = {}
    for p in positions:
        sec = p.get("sector") or "Unknown"
        out[sec] = out.get(sec, Decimal("0")) + Decimal(str(p.get("market_value") or 0))
    return out
