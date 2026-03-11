"""
Strategy Templates — pre-built system strategies seeded into the database.

These templates are inserted as ``is_system=True`` strategies during the
first application startup (or via a management command).  Users can clone
them to create personalised variants.

Each template references a built-in strategy slug and provides tuned
parameter overrides targeting a specific trading style.
"""

from __future__ import annotations

from typing import Any, Dict, List

# Template definitions — each becomes a row in the strategies table
TEMPLATES: List[Dict[str, Any]] = [
    {
        "name": "Conservative SMA (Golden Cross)",
        "description": "Position trading: 50/200 SMA golden cross. Low frequency, high conviction. Best for stocks with clear long-term trends.",
        "strategy_type": "builtin",
        "category": "trend_following",
        "timeframe": "position",
        "asset_class": "stocks",
        "definition_json": {
            "strategy_slug": "sma_crossover",
            "params": {"fast_period": 50, "slow_period": 200, "stop_loss_pct": 0.08},
        },
    },
    {
        "name": "Aggressive RSI Scalper",
        "description": "Swing trading: tight RSI bands (25/75) on 14-period RSI. Frequent trades on mean-reversion moves.",
        "strategy_type": "builtin",
        "category": "mean_reversion",
        "timeframe": "swing",
        "asset_class": "stocks",
        "definition_json": {
            "strategy_slug": "rsi_mean_reversion",
            "params": {"period": 14, "oversold": 25, "overbought": 75, "stop_loss_pct": 0.03},
        },
    },
    {
        "name": "Momentum Breakout",
        "description": "Breakout trading: enter on 20-bar high breakout with 1.5x volume confirmation. Captures momentum surges.",
        "strategy_type": "builtin",
        "category": "breakout",
        "timeframe": "swing",
        "asset_class": "stocks",
        "definition_json": {
            "strategy_slug": "breakout",
            "params": {"lookback": 20, "volume_factor": 1.5, "stop_loss_pct": 0.05},
        },
    },
    {
        "name": "Trend Rider (ADX + EMA)",
        "description": "Trend confirmation: ADX > 25 confirms strong trend, EMA 9/21 crossover for timing. Combines strength and direction.",
        "strategy_type": "builtin",
        "category": "trend_following",
        "timeframe": "swing",
        "asset_class": "stocks",
        "definition_json": {
            "strategy_slug": "adx_trend",
            "params": {"period": 14, "threshold": 25, "stop_loss_pct": 0.05},
        },
    },
    {
        "name": "Bollinger Mean Reversion",
        "description": "Fade moves to outer Bollinger Bands. Enter when price pierces lower band during a squeeze, exit at middle band.",
        "strategy_type": "builtin",
        "category": "mean_reversion",
        "timeframe": "swing",
        "asset_class": "stocks",
        "definition_json": {
            "strategy_slug": "bollinger_squeeze",
            "params": {"period": 20, "std_dev": 2.0, "stop_loss_pct": 0.04},
        },
    },
]
