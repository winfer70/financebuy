"""
buckets.py — Rule 13: Bucket allocation checker.

Fires when any bucket deviates from its target allocation by more than the threshold.
"""
from __future__ import annotations
from decimal import Decimal
from typing import List
from .models import RuleContext, RuleAlertData


def check_buckets(ctx: RuleContext) -> List[RuleAlertData]:
    """Check bucket allocation vs targets.

    Args:
        ctx: RuleContext with bucket_values and portfolio_total_value set.

    Returns:
        List of RuleAlertData (one per out-of-bounds bucket).
    """
    alerts = []
    if ctx.portfolio_total_value <= 0 or not ctx.bucket_values:
        return alerts

    config = ctx.config
    targets = {
        1: config.get("bucket_1_target", 0.35),
        2: config.get("bucket_2_target", 0.35),
        3: config.get("bucket_3_target", 0.30),
    }
    tolerance = 0.05  # ±5% deviation triggers warning

    for bucket_num, target in targets.items():
        bucket_val = ctx.bucket_values.get(bucket_num, Decimal("0"))
        actual = float(bucket_val / ctx.portfolio_total_value)
        deviation = abs(actual - target)
        if deviation > tolerance:
            direction = "overweight" if actual > target else "underweight"
            alerts.append(RuleAlertData(
                rule_type="bucket",
                severity="warning",
                title=f"Bucket {bucket_num} {direction}: {actual*100:.1f}%",
                body=f"Bucket {bucket_num} at {actual*100:.1f}%, target {target*100:.0f}% (±{tolerance*100:.0f}%)",
                triggered_value=Decimal(str(round(actual, 4))),
            ))
    return alerts
