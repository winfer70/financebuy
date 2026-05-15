"""
stop_proximity.py — Stop proximity rule checker.

Fires when current price is within the configured buffer of the stop-loss,
or when the stop has already been breached.
"""
from __future__ import annotations
from decimal import Decimal
from typing import List
from .models import RuleContext, RuleAlertData


def check_stop_proximity(ctx: RuleContext) -> List[RuleAlertData]:
    """Check if current price is dangerously close to or below stop-loss.

    Args:
        ctx: RuleContext with current_price and stop_loss set.

    Returns:
        List of RuleAlertData (0 or 1 item).
    """
    alerts = []
    if ctx.stop_loss <= 0:
        return alerts

    buffer_pct = ctx.config.get("stop_proximity_pct", 0.07)
    if ctx.current_price <= ctx.stop_loss:
        severity = "critical"
        body = f"{ctx.ticker} at ${ctx.current_price:.2f} — stop-loss ${ctx.stop_loss:.2f} breached"
        triggered = ctx.current_price - ctx.stop_loss
    else:
        buffer = float((ctx.current_price - ctx.stop_loss) / ctx.current_price)
        if buffer <= buffer_pct:
            severity = "warning"
            body = f"{ctx.ticker} within {buffer*100:.1f}% of stop-loss ${ctx.stop_loss:.2f}"
            triggered = Decimal(str(round(buffer, 4)))
        else:
            return alerts

    alerts.append(RuleAlertData(
        rule_type="stop_proximity",
        severity=severity,
        title=f"Stop Proximity: {ctx.ticker}",
        body=body,
        triggered_value=triggered,
    ))
    return alerts
