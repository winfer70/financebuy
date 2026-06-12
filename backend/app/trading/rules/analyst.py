"""
analyst.py — Analyst consensus rule checker.

Fires when current price is significantly above the median analyst target,
suggesting limited upside according to consensus estimates.
"""
from __future__ import annotations
from decimal import Decimal
from typing import List, Optional
from .models import RuleContext, RuleAlertData


def check_analyst_consensus(ctx: RuleContext, analyst_target: Optional[float] = None) -> List[RuleAlertData]:
    """Check if price is above analyst consensus target.

    Args:
        ctx:             RuleContext with current_price set.
        analyst_target:  Median analyst price target (fetched separately by arq job).

    Returns:
        List of RuleAlertData (0 or 1 item).
    """
    alerts = []
    if analyst_target is None or analyst_target <= 0:
        return alerts

    config = ctx.config
    flag_pct = config.get("analyst_flag_pct", 0.50)
    current = float(ctx.current_price)
    premium = (current - analyst_target) / analyst_target

    if premium >= flag_pct:
        severity = "critical"
        body = f"{ctx.ticker} at ${current:.2f}, {premium*100:.1f}% above analyst target ${analyst_target:.2f}"
    elif premium >= flag_pct * 0.5:
        severity = "warning"
        body = f"{ctx.ticker} at ${current:.2f}, {premium*100:.1f}% above analyst target ${analyst_target:.2f}"
    else:
        return alerts

    alerts.append(RuleAlertData(
        rule_type="analyst_consensus",
        severity=severity,
        title=f"Analyst Target: {ctx.ticker} +{premium*100:.1f}% above consensus",
        body=body,
        triggered_value=Decimal(str(round(premium, 4))),
    ))
    return alerts
