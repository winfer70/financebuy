"""
fundamentals.py — Fundamental health rule checker.

Checks debt-to-equity stress, gross margin compression, and insider selling.
All fundamental data is fetched by the arq job before calling this function.
"""
from __future__ import annotations
from decimal import Decimal
from typing import List
from .models import RuleContext, RuleAlertData


def check_fundamentals_health(ctx: RuleContext) -> List[RuleAlertData]:
    """Check fundamental health indicators for a position.

    Args:
        ctx: RuleContext with debt_to_equity, gross_margin_recent,
             gross_margin_yoy_delta, insider_net_12m populated.

    Returns:
        List of RuleAlertData (0 to 3 items, one per triggered indicator).
    """
    alerts = []
    config = ctx.config

    # D/E ratio check
    if ctx.debt_to_equity is not None:
        de = ctx.debt_to_equity
        de_critical = config.get("de_ratio_critical", 500.0)
        de_warn = config.get("de_ratio_warn", 200.0)
        if de >= de_critical:
            alerts.append(RuleAlertData(
                rule_type="fundamentals",
                severity="critical",
                title=f"D/E Stress: {ctx.ticker} {de:.0f}%",
                body=f"{ctx.ticker} debt-to-equity {de:.0f}% — critical threshold {de_critical:.0f}%",
                triggered_value=Decimal(str(round(de, 2))),
            ))
        elif de >= de_warn:
            alerts.append(RuleAlertData(
                rule_type="fundamentals",
                severity="warning",
                title=f"D/E Elevated: {ctx.ticker} {de:.0f}%",
                body=f"{ctx.ticker} debt-to-equity {de:.0f}% — warning threshold {de_warn:.0f}%",
                triggered_value=Decimal(str(round(de, 2))),
            ))

    # Gross margin compression check
    if ctx.gross_margin_yoy_delta is not None:
        compression_warn = -abs(config.get("margin_compression_warn_pct", 30.0))
        delta = ctx.gross_margin_yoy_delta
        if delta <= compression_warn:
            alerts.append(RuleAlertData(
                rule_type="fundamentals",
                severity="warning",
                title=f"Margin Compression: {ctx.ticker} {delta:+.1f}% YoY",
                body=f"{ctx.ticker} gross margin compressed {delta:.1f}% year-over-year",
                triggered_value=Decimal(str(round(delta, 2))),
            ))

    # Insider net selling check (negative = net selling)
    if ctx.insider_net_12m is not None and ctx.insider_net_12m < -0.02:
        pct = ctx.insider_net_12m * 100
        alerts.append(RuleAlertData(
            rule_type="fundamentals",
            severity="warning",
            title=f"Insider Selling: {ctx.ticker} {pct:.1f}% net",
            body=f"{ctx.ticker} insiders net sold {abs(pct):.1f}% of float in last 12 months",
            triggered_value=Decimal(str(round(ctx.insider_net_12m, 4))),
        ))

    return alerts
