"""
house_money.py — Rule 11: House Money rule checker.

Fires when a position's current value is a multiple of its cost basis,
suggesting the user could reduce risk by taking some profit off the table.
"""
from __future__ import annotations
from decimal import Decimal
from typing import List
from .models import RuleContext, RuleAlertData


def check_house_money(ctx: RuleContext) -> List[RuleAlertData]:
    """Check if position has achieved house-money multiple.

    Args:
        ctx: RuleContext with current_value and cost_basis_total set.

    Returns:
        List of RuleAlertData (0 or 1 item).
    """
    alerts = []
    if ctx.cost_basis_total <= 0:
        return alerts

    config = ctx.config
    multiple = float(ctx.current_value / ctx.cost_basis_total)
    critical = config.get("house_money_multiple", 2.0)
    warn = config.get("house_money_warn_at", 1.75)
    info = config.get("house_money_info_at", 1.50)

    if multiple >= critical:
        severity = "critical"
        msg = f"{ctx.ticker} is at {multiple:.2f}× cost basis — house money threshold reached"
    elif multiple >= warn:
        severity = "warning"
        msg = f"{ctx.ticker} is at {multiple:.2f}× cost basis — approaching house money"
    elif multiple >= info:
        severity = "info"
        msg = f"{ctx.ticker} is at {multiple:.2f}× cost basis — monitor for house money"
    else:
        return alerts

    alerts.append(RuleAlertData(
        rule_type="house_money",
        severity=severity,
        title=f"House Money: {ctx.ticker} {multiple:.2f}×",
        body=msg,
        triggered_value=Decimal(str(round(multiple, 4))),
    ))
    return alerts
