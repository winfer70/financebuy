"""
PineScript Executor — interprets compiled IR against OHLCV bars to
produce trading signals.

Takes the ``compiled`` dict produced by the transpiler and evaluates
each indicator, entry/exit condition, and stop-loss rule bar-by-bar,
producing a ``List[Signal]`` compatible with the BacktestEngine.

The executor is the bridge between user-authored PineScript code and
the backtest engine: it reads the compiled intermediate representation,
computes all indicator time-series using the shared indicators module,
and then walks bar-by-bar to fire entry/exit signals when conditions
are satisfied.

Public API:
    resolve_pinescript_signals(definition) -> Callable
        Returns a signal-generator function with the standard signature
        ``(bars: List[OHLCVBar], params: Dict) -> List[Signal]``.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from ..engine import Signal
from ..engine import indicators as ind
from ..providers import OHLCVBar

logger = logging.getLogger("pinescript.executor")


# ── Series resolution ────────────────────────────────────────────────

def _extract_price_series(
    bars: List[OHLCVBar],
) -> Dict[str, List[float]]:
    """Extract base price/volume series from OHLCV bars.

    Args:
        bars: Chronological OHLCV bars.

    Returns:
        Dict mapping series names ("close", "open", "high", "low",
        "volume") to float lists.
    """
    return {
        "close":  [b.close for b in bars],
        "open":   [b.open for b in bars],
        "high":   [b.high for b in bars],
        "low":    [b.low for b in bars],
        "volume": [b.volume for b in bars],
    }


def _resolve_source(
    source: Any,
    series: Dict[str, List[float]],
    params: Dict[str, Any],
) -> List[float]:
    """Resolve a source reference to a concrete float series.

    The *source* can be:
      - A built-in name (``"close"``, ``"high"``, etc.)
      - A computed indicator variable name (``"_ind_sma_1"``)
      - A param reference (string that matches a key in *params*),
        in which case a constant series is returned.
      - A numeric literal (int / float), returned as a constant series.

    Args:
        source:  Source reference from the compiled IR.
        series:  Pre-computed named series (price data + indicators).
        params:  Strategy parameter values.

    Returns:
        Float list of the same length as the price series.
    """
    if isinstance(source, str):
        # Direct series lookup
        if source in series:
            return series[source]
        # Param reference → constant series
        if source in params:
            val = float(params[source])
            n = max(len(v) for v in series.values()) if series else 0
            return [val] * n
    # Numeric literal → constant series
    if isinstance(source, (int, float)):
        n = max(len(v) for v in series.values()) if series else 0
        return [float(source)] * n
    # Fallback — return close
    logger.warning("Could not resolve source '%s'; defaulting to close.", source)
    return series.get("close", [])


# ── Indicator computation ─────────────────────────────────────────────

def _compute_indicators(
    indicator_defs: List[Dict[str, Any]],
    series: Dict[str, List[float]],
    params: Dict[str, Any],
) -> Dict[str, List[float]]:
    """Compute all indicators defined in the compiled IR.

    Each indicator definition has the form:
        {"fn": "sma", "args": {"source": "close", "period": 14},
         "output_var": "_ind_sma_1"}

    Computed series are added to *series* (mutated in place) and also
    returned.

    Args:
        indicator_defs: List of indicator definitions from compiled IR.
        series:         Mutable dict of named series (price data +
                        previously computed indicators).
        params:         Strategy parameter values (for param refs in args).

    Returns:
        Dict of newly computed indicator series keyed by output_var.
    """
    new_series: Dict[str, List[float]] = {}

    for defn in indicator_defs:
        fn_name = defn["fn"]
        args = defn.get("args", {})
        output_var = defn["output_var"]

        # Resolve argument values — if an arg value is a string matching
        # a param name, substitute the param value
        resolved: Dict[str, Any] = {}
        for k, v in args.items():
            if isinstance(v, str) and v in params:
                resolved[k] = params[v]
            else:
                resolved[k] = v

        try:
            result = _call_indicator(fn_name, resolved, series, params)
        except Exception as exc:
            logger.warning(
                "Indicator '%s' (%s) failed: %s — filling with zeros.",
                output_var, fn_name, exc,
            )
            n = max(len(v) for v in series.values()) if series else 0
            result = [0.0] * n

        # Indicators may return tuples (e.g. MACD, BB, ADX, Stochastic).
        # Store the primary output under output_var, and sub-outputs
        # under output_var__0, output_var__1, etc.
        if isinstance(result, tuple):
            for idx, sub in enumerate(result):
                sub_key = f"{output_var}__{idx}"
                if isinstance(sub, list):
                    series[sub_key] = sub
                    new_series[sub_key] = sub
            # Primary output is first element
            if result and isinstance(result[0], list):
                series[output_var] = result[0]
                new_series[output_var] = result[0]
        elif isinstance(result, list):
            series[output_var] = result
            new_series[output_var] = result

    return new_series


def _call_indicator(
    fn_name: str,
    args: Dict[str, Any],
    series: Dict[str, List[float]],
    params: Dict[str, Any],
) -> Any:
    """Dispatch a single indicator computation to the shared library.

    Args:
        fn_name: Indicator function name (e.g. "sma", "macd").
        args:    Resolved arguments from the compiled IR.
        series:  Available named series.
        params:  Strategy parameter values.

    Returns:
        Computed series (List[float]) or tuple of series.
    """
    if fn_name == "sma":
        source = _resolve_source(args.get("source", "close"), series, params)
        period = int(args.get("period", 14))
        return ind.sma(source, period)

    elif fn_name == "ema":
        source = _resolve_source(args.get("source", "close"), series, params)
        period = int(args.get("period", 14))
        return ind.ema(source, period)

    elif fn_name == "rsi":
        source = _resolve_source(args.get("source", "close"), series, params)
        period = int(args.get("period", 14))
        return ind.rsi(source, period)

    elif fn_name == "macd":
        source = _resolve_source(args.get("source", "close"), series, params)
        fast = int(args.get("fast", 12))
        slow = int(args.get("slow", 26))
        signal = int(args.get("signal", 9))
        return ind.macd(source, fast, slow, signal)

    elif fn_name == "bollinger_bands":
        source = _resolve_source(args.get("source", "close"), series, params)
        period = int(args.get("period", 20))
        num_std = float(args.get("num_std", 2.0))
        return ind.bollinger_bands(source, period, num_std)

    elif fn_name == "atr":
        return ind.atr(
            series["high"], series["low"], series["close"],
            period=int(args.get("period", 14)),
        )

    elif fn_name == "adx":
        return ind.adx(
            series["high"], series["low"], series["close"],
            period=int(args.get("period", 14)),
        )

    elif fn_name == "stochastic":
        return ind.stochastic(
            series["high"], series["low"], series["close"],
            k_period=int(args.get("k_period", 14)),
            d_period=int(args.get("d_period", 3)),
        )

    elif fn_name == "vwap":
        return ind.vwap(
            series["high"], series["low"], series["close"],
            series["volume"],
        )

    elif fn_name == "highest":
        source = _resolve_source(args.get("source", "high"), series, params)
        period = int(args.get("period", 20))
        return ind.highest(source, period)

    elif fn_name == "lowest":
        source = _resolve_source(args.get("source", "low"), series, params)
        period = int(args.get("period", 20))
        return ind.lowest(source, period)

    elif fn_name == "crossover":
        a = _resolve_source(args.get("a", ""), series, params)
        b = _resolve_source(args.get("b", ""), series, params)
        # crossover returns List[bool]; convert to List[float] for uniform handling
        bools = ind.crossover(a, b)
        return [1.0 if v else 0.0 for v in bools]

    elif fn_name == "crossunder":
        a = _resolve_source(args.get("a", ""), series, params)
        b = _resolve_source(args.get("b", ""), series, params)
        bools = ind.crossunder(a, b)
        return [1.0 if v else 0.0 for v in bools]

    else:
        raise ValueError(f"Unknown indicator function: {fn_name}")


# ── Condition evaluation ──────────────────────────────────────────────

def _eval_condition(
    condition: Any,
    series: Dict[str, List[float]],
    params: Dict[str, Any],
    bar_idx: int,
) -> bool:
    """Evaluate a single condition at a specific bar index.

    Conditions come from the compiled IR and can be:
      - A comparison dict: {"type": "comparison", "left": ..., "op": ..., "right": ...}
      - A logical dict: {"type": "logical", "op": "and"|"or", "operands": [...]}
      - A crossover/crossunder indicator reference (value > 0.5 means fired)
      - A strategy_entry/strategy_exit dict (always True — triggers on context)
      - A boolean literal

    Args:
        condition: Condition from compiled IR.
        series:    Named series (price + indicators).
        params:    Strategy parameter values.
        bar_idx:   Current bar index.

    Returns:
        True if the condition is satisfied at this bar.
    """
    if condition is None:
        return False
    if isinstance(condition, bool):
        return condition

    if isinstance(condition, dict):
        cond_type = condition.get("type", "")

        if cond_type == "comparison":
            return _eval_comparison(condition, series, params, bar_idx)
        elif cond_type == "logical":
            return _eval_logical(condition, series, params, bar_idx)
        elif cond_type in ("strategy_entry", "strategy_exit", "strategy_close_all"):
            # Evaluate the embedded condition from the if-block
            inner = condition.get("condition")
            if inner is None:
                return True
            return _eval_condition(inner, series, params, bar_idx)

    # String reference to an indicator that acts as a boolean signal
    # (e.g. crossover output > 0.5 means signal fired)
    if isinstance(condition, str) and condition in series:
        val = series[condition][bar_idx] if bar_idx < len(series[condition]) else 0.0
        return val > 0.5

    return False


def _get_value_at(
    ref: Any,
    series: Dict[str, List[float]],
    params: Dict[str, Any],
    bar_idx: int,
) -> float:
    """Resolve a value reference to a float at a given bar index.

    Handles series references, param references, numeric literals,
    and series-with-offset (e.g. ``"close[1]"``).

    Args:
        ref:     Value reference from the compiled IR.
        series:  Named series.
        params:  Strategy parameter values.
        bar_idx: Current bar index.

    Returns:
        Float value at the given bar.
    """
    if isinstance(ref, (int, float)):
        return float(ref)

    if isinstance(ref, str):
        # Handle series offset syntax: "name[offset]"
        if "[" in ref and ref.endswith("]"):
            name, offset_str = ref.split("[", 1)
            offset = int(offset_str.rstrip("]"))
            actual_idx = bar_idx - offset
            if name in series and 0 <= actual_idx < len(series[name]):
                return series[name][actual_idx]
            return 0.0

        # Direct series lookup
        if ref in series and bar_idx < len(series[ref]):
            return series[ref][bar_idx]
        # Param lookup
        if ref in params:
            return float(params[ref])

    # String arithmetic expression — not supported at runtime, return 0
    return 0.0


def _eval_comparison(
    cond: Dict[str, Any],
    series: Dict[str, List[float]],
    params: Dict[str, Any],
    bar_idx: int,
) -> bool:
    """Evaluate a comparison condition at bar_idx.

    Args:
        cond:    Comparison dict with "left", "op", "right".
        series:  Named series.
        params:  Strategy parameter values.
        bar_idx: Current bar index.

    Returns:
        Boolean result of the comparison.
    """
    left = _get_value_at(cond["left"], series, params, bar_idx)
    right = _get_value_at(cond["right"], series, params, bar_idx)
    op = cond["op"]

    if op == ">":
        return left > right
    elif op == "<":
        return left < right
    elif op == ">=":
        return left >= right
    elif op == "<=":
        return left <= right
    elif op == "==":
        return abs(left - right) < 1e-10
    elif op == "!=":
        return abs(left - right) >= 1e-10
    return False


def _eval_logical(
    cond: Dict[str, Any],
    series: Dict[str, List[float]],
    params: Dict[str, Any],
    bar_idx: int,
) -> bool:
    """Evaluate a logical (and/or) condition at bar_idx.

    Args:
        cond:    Logical dict with "op" and "operands".
        series:  Named series.
        params:  Strategy parameter values.
        bar_idx: Current bar index.

    Returns:
        Boolean result.
    """
    op = cond["op"]
    operands = cond.get("operands", [])

    if op == "and":
        return all(_eval_condition(o, series, params, bar_idx) for o in operands)
    elif op == "or":
        return any(_eval_condition(o, series, params, bar_idx) for o in operands)
    return False


# ── Signal generation ─────────────────────────────────────────────────

def _generate_signals(
    compiled: Dict[str, Any],
    bars: List[OHLCVBar],
    params: Dict[str, Any],
) -> List[Signal]:
    """Core signal generation loop.

    Computes all indicators, then walks bar-by-bar evaluating entry
    and exit conditions to produce Signal objects.

    Args:
        compiled: Compiled IR dict from the transpiler.
        bars:     Chronological OHLCV bars.
        params:   Strategy parameter values.

    Returns:
        List of Signal objects.
    """
    if not bars:
        return []

    # Extract base price series from bars
    series = _extract_price_series(bars)

    # Compute all indicators
    indicator_defs = compiled.get("indicators", [])
    _compute_indicators(indicator_defs, series, params)

    entry_conditions = compiled.get("entry_conditions", [])
    exit_conditions = compiled.get("exit_conditions", [])
    stop_loss = compiled.get("stop_loss")

    signals: List[Signal] = []
    in_position = False
    entry_price = 0.0

    # Determine warm-up period — skip bars until all indicators are valid.
    # Find the maximum period across all indicator args.
    warmup = 0
    for defn in indicator_defs:
        for v in defn.get("args", {}).values():
            if isinstance(v, (int, float)) and v > 0:
                warmup = max(warmup, int(v))
    # Double the warmup for indicators that chain (like ADX which uses
    # Wilder smoothing twice)
    start_idx = min(warmup * 2, len(bars) - 1)

    for i in range(start_idx, len(bars)):
        bar = bars[i]

        # Check stop loss first (if in position)
        if in_position and stop_loss:
            triggered = _check_stop_loss(
                stop_loss, bar, entry_price, params,
            )
            if triggered:
                stop_price = _get_stop_price(
                    stop_loss, entry_price, params,
                )
                signals.append(Signal(
                    timestamp=bar.timestamp,
                    signal_type="stop_loss",
                    direction="long",
                    price=stop_price,
                ))
                in_position = False
                continue

        # Check entry conditions (only if not already in position)
        if not in_position and entry_conditions:
            entry_fired = any(
                _eval_condition(c, series, params, i)
                for c in entry_conditions
            )
            if entry_fired:
                direction = _get_direction(entry_conditions)
                entry_price = bar.close
                signals.append(Signal(
                    timestamp=bar.timestamp,
                    signal_type="entry",
                    direction=direction,
                    price=entry_price,
                ))
                in_position = True

        # Check exit conditions (only if in position)
        elif in_position and exit_conditions:
            exit_fired = any(
                _eval_condition(c, series, params, i)
                for c in exit_conditions
            )
            if exit_fired:
                signals.append(Signal(
                    timestamp=bar.timestamp,
                    signal_type="exit",
                    direction="long",
                    price=bar.close,
                ))
                in_position = False

    return signals


def _get_direction(conditions: List[Dict[str, Any]]) -> str:
    """Extract trade direction from entry conditions.

    Args:
        conditions: Entry condition dicts.

    Returns:
        ``"long"`` or ``"short"``.
    """
    for c in conditions:
        if isinstance(c, dict) and "direction" in c:
            return c["direction"]
    return "long"


def _check_stop_loss(
    stop_cfg: Dict[str, Any],
    bar: OHLCVBar,
    entry_price: float,
    params: Dict[str, Any],
) -> bool:
    """Check if stop loss was triggered at this bar.

    Args:
        stop_cfg:    Stop loss config from compiled IR.
        bar:         Current OHLCV bar.
        entry_price: Position entry price.
        params:      Strategy parameter values.

    Returns:
        True if stop loss triggered.
    """
    stop_price = _get_stop_price(stop_cfg, entry_price, params)
    return bar.low <= stop_price


def _get_stop_price(
    stop_cfg: Dict[str, Any],
    entry_price: float,
    params: Dict[str, Any],
) -> float:
    """Calculate the stop-loss price level.

    Args:
        stop_cfg:    Stop loss config {"type": "pct"|"price", "value": ...}.
        entry_price: Position entry price.
        params:      Strategy parameter values.

    Returns:
        Absolute stop price.
    """
    value = stop_cfg.get("value", 0)
    # Resolve param references
    if isinstance(value, str) and value in params:
        value = float(params[value])
    else:
        value = float(value)

    stop_type = stop_cfg.get("type", "pct")
    if stop_type == "pct":
        return round(entry_price * (1 - value), 4)
    elif stop_type == "price":
        return round(value, 4)
    return round(entry_price * 0.95, 4)  # fallback: 5% stop


# ── Public API ────────────────────────────────────────────────────────

def resolve_pinescript_signals(
    definition: Dict[str, Any],
) -> Callable[[List[OHLCVBar], Dict[str, Any]], List[Signal]]:
    """Create a signal-generator function from a PineScript definition.

    The returned callable has the standard signature expected by
    ``BacktestEngine.run()``::

        signal_fn(bars: List[OHLCVBar], params: Dict) -> List[Signal]

    The compiled IR is captured in the closure so the function can be
    called multiple times with different bars/params.

    Args:
        definition: Complete definition_json dict (must contain
                    ``"compiled"`` key with the IR).

    Returns:
        Signal generator callable.
    """
    compiled = definition.get("compiled", {})
    default_params = definition.get("params", {})

    def signal_fn(
        bars: List[OHLCVBar],
        params: Dict[str, Any],
    ) -> List[Signal]:
        """Generate signals from PineScript compiled IR.

        Args:
            bars:   Chronological OHLCV bars.
            params: Strategy parameters (overrides defaults).

        Returns:
            List of Signal objects.
        """
        # Merge default params with runtime overrides
        merged = {**default_params, **params}
        return _generate_signals(compiled, bars, merged)

    return signal_fn
