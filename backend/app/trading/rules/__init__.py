"""
rules/__init__.py — Portfolio rules engine for TickerTap.

Exports the rule runner and individual check functions.
Each rule function is pure: takes a RuleContext, returns list of RuleAlertData.
No DB or network calls inside rule functions — data is fetched before calling rules.
"""
from .runner import run_all_rules
from .models import RuleContext, RuleAlertData

__all__ = ["run_all_rules", "RuleContext", "RuleAlertData"]
