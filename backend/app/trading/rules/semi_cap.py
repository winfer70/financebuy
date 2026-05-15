"""
semi_cap.py — Rule 12: Semiconductor concentration cap.

Fires when semiconductor positions exceed the configured % of total portfolio.
Portfolio-wide check — should only fire once per portfolio run, not per position.
"""
from __future__ import annotations
from decimal import Decimal
from typing import List
from .models import RuleContext, RuleAlertData


def check_semi_cap(ctx: RuleContext) -> List[RuleAlertData]:
    """Check if semiconductor allocation exceeds cap.

    Only fires if ctx.is_semi is True (checked per position but represents portfolio total).

    Args:
        ctx: RuleContext with semi_total_value and portfolio_total_value set.

    Returns:
        List of RuleAlertData (0 or 1 item).
    """
    alerts = []
    if not ctx.is_semi or ctx.portfolio_total_value <= 0:
        return alerts

    cap = ctx.config.get("semi_cap", 0.35)
    ratio = float(ctx.semi_total_value / ctx.portfolio_total_value)

    if ratio > cap:
        alerts.append(RuleAlertData(
            rule_type="semi_cap",
            severity="warning",
            title=f"Semi Cap: {ratio*100:.1f}% of portfolio",
            body=f"Semiconductor exposure {ratio*100:.1f}% exceeds {cap*100:.0f}% cap",
            triggered_value=Decimal(str(round(ratio, 4))),
        ))
    return alerts
