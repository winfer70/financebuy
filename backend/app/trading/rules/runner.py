"""
runner.py — Portfolio rules engine orchestrator.

run_all_rules() accepts a RuleContext for a single position and
calls all enabled rule check functions, returning a combined list of alerts.
"""
from __future__ import annotations
from typing import List, Optional
from .models import RuleContext, RuleAlertData
from .house_money import check_house_money
from .stop_proximity import check_stop_proximity
from .semi_cap import check_semi_cap
from .buckets import check_buckets
from .time_stop import check_time_stop
from .analyst import check_analyst_consensus
from .fundamentals import check_fundamentals_health
from .pre_earnings import check_pre_earnings

# All standard rule functions (analyst_consensus handled separately — needs extra arg)
_RULE_FUNCTIONS = {
    "house_money":    check_house_money,
    "stop_proximity": check_stop_proximity,
    "semi_cap":       check_semi_cap,
    "bucket":         check_buckets,
    "time_stop":      check_time_stop,
    "fundamentals":   check_fundamentals_health,
    "pre_earnings":   check_pre_earnings,
}


def run_all_rules(ctx: RuleContext, analyst_target: Optional[float] = None) -> List[RuleAlertData]:
    """Run all enabled rule checks for a single position.

    Calls each rule function in turn, collects their alerts, and returns a
    combined flat list.  Individual rule failures are swallowed so that one
    broken rule cannot abort the entire engine run.

    Args:
        ctx:             RuleContext with all position data populated.
        analyst_target:  Median analyst price target (optional, fetched by caller).

    Returns:
        Combined list of RuleAlertData from all triggered checks.
    """
    enabled = set(
        ctx.config.get(
            "enabled_rules",
            list(_RULE_FUNCTIONS.keys()) + ["analyst_consensus"],
        )
    )
    alerts: List[RuleAlertData] = []

    for rule_name, fn in _RULE_FUNCTIONS.items():
        if rule_name in enabled:
            try:
                alerts.extend(fn(ctx))
            except Exception:
                # Individual rule failure must never crash the engine
                pass

    if "analyst_consensus" in enabled:
        try:
            alerts.extend(check_analyst_consensus(ctx, analyst_target))
        except Exception:
            pass

    return alerts
