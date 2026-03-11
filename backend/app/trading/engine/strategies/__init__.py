"""
Strategy Registry — discovery and lookup for built-in strategy modules.

Each strategy module in this package exposes:
    name           — Human-readable strategy name.
    description    — One-line description.
    default_params — Dict of default parameter values.
    param_schema   — List of parameter definitions for the UI.
    generate_signals(bars, params) → List[Signal]

The ``REGISTRY`` dict maps strategy slug → module, populated automatically
at import time.  The ``get_strategy`` helper provides safe lookup.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Any

from .. import Signal
from ...providers import OHLCVBar

# Strategy interface type alias
SignalGenerator = Callable[[List[OHLCVBar], Dict[str, Any]], List[Signal]]


# ---------------------------------------------------------------------------
# Registry — populated by imports below
# ---------------------------------------------------------------------------

REGISTRY: Dict[str, Dict[str, Any]] = {}


def register(
    slug: str,
    name: str,
    description: str,
    default_params: Dict[str, Any],
    param_schema: List[Dict[str, Any]],
    generate_signals: SignalGenerator,
) -> None:
    """Register a strategy module in the global registry.

    Args:
        slug:             Unique identifier (e.g. ``"sma_crossover"``).
        name:             Human-readable name.
        description:      One-line description.
        default_params:   Dict of default parameter values.
        param_schema:     List of param definitions for the frontend.
        generate_signals: Strategy function ``(bars, params) → List[Signal]``.
    """
    REGISTRY[slug] = {
        "name": name,
        "description": description,
        "default_params": default_params,
        "param_schema": param_schema,
        "generate_signals": generate_signals,
    }


def get_strategy(slug: str) -> Dict[str, Any]:
    """Look up a registered strategy by slug.

    Args:
        slug: Strategy identifier.

    Returns:
        Strategy dict with keys: name, description, default_params,
        param_schema, generate_signals.

    Raises:
        KeyError: If *slug* is not registered.
    """
    if slug not in REGISTRY:
        raise KeyError(f"Unknown strategy '{slug}'. Available: {list(REGISTRY.keys())}")
    return REGISTRY[slug]


def list_strategies() -> List[Dict[str, Any]]:
    """Return metadata for all registered strategies (without signal functions).

    Returns:
        List of dicts with keys: slug, name, description, default_params, param_schema.
    """
    return [
        {
            "slug": slug,
            "name": s["name"],
            "description": s["description"],
            "default_params": s["default_params"],
            "param_schema": s["param_schema"],
        }
        for slug, s in REGISTRY.items()
    ]


# ---------------------------------------------------------------------------
# Auto-import all strategy modules to trigger registration
# ---------------------------------------------------------------------------

from . import (  # noqa: E402, F401
    sma_crossover,
    ema_crossover,
    rsi_mean_reversion,
    macd_crossover,
    bollinger_squeeze,
    stochastic,
    adx_trend,
    vwap_bounce,
    breakout,
    ichimoku,
)
