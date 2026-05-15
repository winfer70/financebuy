"""
models.py — Data classes for the portfolio rules engine.

RuleContext: all data needed to evaluate rules for one position.
RuleAlertData: output of a rule check — maps to a rule_alerts row.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, List
from datetime import date


@dataclass
class RuleContext:
    """All data needed to evaluate all rules for a single portfolio position."""

    # Position identity
    position_id: int           # soft int ref (UUID-based positions store 0)
    portfolio_id: int
    user_id: str               # UUID string
    ticker: str

    # Position data
    quantity: Decimal
    purchase_price: Decimal
    stop_loss: Decimal
    profit_taking: Decimal     # T1
    t2_usd: Optional[Decimal]
    is_semi: bool
    sector: Optional[str]
    bucket: Optional[int]      # 1 | 2 | 3
    date_entered: Optional[date]

    # Live market data
    current_price: Decimal

    # Computed from position + price
    pnl_pct: Decimal           # (current_price - purchase_price) / purchase_price
    cost_basis_total: Decimal  # purchase_price * quantity
    current_value: Decimal     # current_price * quantity

    # SMA50 data for time-stop rule (last 80 daily closes)
    daily_closes: List[Decimal] = field(default_factory=list)
    sessions_below_sma50: int = 0   # pre-computed before calling rules

    # Fundamentals
    debt_to_equity: Optional[float] = None      # percentage (e.g. 150 = 150%)
    gross_margin_recent: Optional[float] = None  # percentage
    gross_margin_yoy_delta: Optional[float] = None  # positive = improved
    insider_net_12m: Optional[float] = None     # net buy/sell as % of float (negative = net selling)

    # Earnings (for pre-earnings alert)
    next_earnings_date: Optional[date] = None

    # Portfolio-wide aggregates (needed for semi_cap and bucket rules)
    portfolio_total_value: Decimal = Decimal("0")
    semi_total_value: Decimal = Decimal("0")
    bucket_values: dict = field(default_factory=dict)  # {1: Decimal, 2: Decimal, 3: Decimal}

    # User-configured thresholds (from preferences.portfolio_rules)
    config: dict = field(default_factory=dict)


@dataclass
class RuleAlertData:
    """Output of a rule check — maps directly to a rule_alerts table row."""

    rule_type: str          # house_money | stop_proximity | semi_cap | bucket | time_stop | analyst_consensus | fundamentals | pre_earnings
    severity: str           # info | warning | critical
    title: str
    body: str
    triggered_value: Optional[Decimal] = None
