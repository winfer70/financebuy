"""
time_stop.py — Rule 16: Time-Stop (SMA50 sessions below check).

Fires when a position has traded below its 50-day SMA for too many consecutive sessions.
"""
from __future__ import annotations
from decimal import Decimal
from typing import List
from .models import RuleContext, RuleAlertData


def check_time_stop(ctx: RuleContext) -> List[RuleAlertData]:
    """Check if position has been below 50-day SMA for too long.

    Uses ctx.sessions_below_sma50 which is pre-computed by the arq job
    to avoid recalculating SMA inside the rule function.

    Args:
        ctx: RuleContext with sessions_below_sma50 set.

    Returns:
        List of RuleAlertData (0 or 1 item).
    """
    alerts = []
    sessions = ctx.sessions_below_sma50
    config = ctx.config
    critical_sessions = config.get("time_stop_critical_sessions", 21)
    warn_sessions = config.get("time_stop_warn_sessions", 10)

    if sessions >= critical_sessions:
        severity = "critical"
        body = f"{ctx.ticker} below 50-day SMA for {sessions} sessions — time-stop triggered"
    elif sessions >= warn_sessions:
        severity = "warning"
        body = f"{ctx.ticker} below 50-day SMA for {sessions} sessions"
    else:
        return alerts

    alerts.append(RuleAlertData(
        rule_type="time_stop",
        severity=severity,
        title=f"Time-Stop: {ctx.ticker} {sessions} sessions below SMA50",
        body=body,
        triggered_value=Decimal(str(sessions)),
    ))
    return alerts
