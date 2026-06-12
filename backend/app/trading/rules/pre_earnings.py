"""
pre_earnings.py — Pre-earnings alert.

Fires INFO alert when a position has an earnings event within 2 business days.
"""
from __future__ import annotations
from decimal import Decimal
from typing import List
from datetime import date, timedelta
from .models import RuleContext, RuleAlertData


def _business_days_until(target: date, today: date) -> int:
    """Count business days between today and target date (exclusive of today).

    Args:
        target: The future date to count towards.
        today:  The starting date (exclusive).

    Returns:
        Number of Mon-Fri days between today and target.
    """
    days = 0
    current = today
    while current < target:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Mon-Fri
            days += 1
    return days


def check_pre_earnings(ctx: RuleContext) -> List[RuleAlertData]:
    """Check if earnings date is within 2 business days.

    Args:
        ctx: RuleContext with next_earnings_date populated.

    Returns:
        List of RuleAlertData (0 or 1 item).
    """
    alerts = []
    if ctx.next_earnings_date is None:
        return alerts

    today = date.today()
    if ctx.next_earnings_date < today:
        return alerts

    bdays = _business_days_until(ctx.next_earnings_date, today)
    if bdays <= 2:
        alerts.append(RuleAlertData(
            rule_type="pre_earnings",
            severity="info",
            title=f"Earnings: {ctx.ticker} in {bdays} business day{'s' if bdays != 1 else ''}",
            body=f"{ctx.ticker} reports earnings on {ctx.next_earnings_date} ({bdays} business day{'s' if bdays != 1 else ''} away)",
            triggered_value=Decimal(str(bdays)),
        ))
    return alerts
