"""
Strategy Composition Engine — evaluates a graph of indicator nodes and
boolean logic expressions bar-by-bar to produce trading signals.

Allows users to visually compose strategies by connecting built-in
indicator outputs through configurable entry/exit conditions, without
writing any code.

The composition graph is stored as a ``definition_json`` with
``strategy_type="composed"`` and a ``compiled`` dict containing:
  - ``indicators``: list of indicator node definitions
  - ``entry_expr``: boolean expression string referencing indicator vars
  - ``exit_expr``: boolean expression string
  - ``stop_loss``: optional stop loss config

Expression evaluation uses ``ast.parse(expr, mode='eval')`` with a
strict whitelist walk — no function calls, no imports, no attribute
access beyond whitelisted names.

Public API:
    resolve_composed_signals(definition) -> Callable
        Returns a signal-generator function with the standard signature.
"""

from __future__ import annotations

import ast
import logging
import operator
from typing import Any, Callable, Dict, List, Optional, Set

from ..engine import Signal
from ..engine import indicators as ind
from ..providers import OHLCVBar

logger = logging.getLogger("trading.composition")


# ── Safe Expression Evaluator ─────────────────────────────────────────

# Allowed comparison operators in filter expressions
_COMPARE_OPS = {
    ast.Gt: operator.gt,
    ast.Lt: operator.lt,
    ast.GtE: operator.ge,
    ast.LtE: operator.le,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}

# Allowed boolean operators
_BOOL_OPS = {
    ast.And: all,
    ast.Or: any,
}

# Allowed unary operators
_UNARY_OPS = {
    ast.Not: operator.not_,
    ast.USub: operator.neg,
}

# Allowed binary arithmetic operators
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
}


def _validate_expression(expr_str: str) -> ast.Expression:
    """Parse and whitelist-validate an expression string.

    Only allows comparisons, boolean logic, arithmetic, names, and
    numeric/boolean constants. Rejects function calls, attribute
    access, imports, and anything else.

    Args:
        expr_str: Python-like expression string
                  (e.g. ``"fast_sma > slow_sma and rsi < 30"``).

    Returns:
        Parsed ``ast.Expression`` node.

    Raises:
        ValueError: If the expression contains disallowed constructs.
    """
    try:
        tree = ast.parse(expr_str.strip(), mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid expression syntax: {exc}") from exc

    _walk_expr_node(tree.body)
    return tree


# Allowed AST node types inside an expression
_ALLOWED_EXPR_NODES: Set[type] = {
    ast.Expression,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.BinOp,
    ast.UnaryOp,
    ast.Not,
    ast.Compare,
    ast.Name,
    ast.Constant,
    ast.Load,
    # Comparison operators
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    # Arithmetic operators
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
    ast.USub,
}


def _walk_expr_node(node: ast.AST) -> None:
    """Recursively validate every node in the expression AST.

    Args:
        node: Any AST node.

    Raises:
        ValueError: On disallowed node types.
    """
    if type(node) not in _ALLOWED_EXPR_NODES:
        raise ValueError(
            f"Disallowed expression node: {type(node).__name__}. "
            f"Only comparisons, arithmetic, boolean logic, names, "
            f"and constants are allowed."
        )
    for child in ast.iter_child_nodes(node):
        _walk_expr_node(child)


def _eval_expression(
    tree: ast.Expression,
    namespace: Dict[str, float],
) -> bool:
    """Evaluate a pre-validated expression against a variable namespace.

    Args:
        tree:      Pre-validated AST expression.
        namespace: Variable name → float value at the current bar.

    Returns:
        Boolean result of the expression.
    """
    return bool(_eval_node(tree.body, namespace))


def _eval_node(node: ast.AST, ns: Dict[str, float]) -> Any:
    """Recursively evaluate an AST node.

    Args:
        node: AST node.
        ns:   Variable namespace.

    Returns:
        Evaluated value (float or bool).
    """
    if isinstance(node, ast.Constant):
        return node.value

    elif isinstance(node, ast.Name):
        return ns.get(node.id, 0.0)

    elif isinstance(node, ast.BoolOp):
        values = [_eval_node(v, ns) for v in node.values]
        op_fn = _BOOL_OPS.get(type(node.op))
        if op_fn is None:
            return False
        return op_fn(values)

    elif isinstance(node, ast.Compare):
        left = _eval_node(node.left, ns)
        for op, comparator in zip(node.ops, node.comparators):
            right = _eval_node(comparator, ns)
            op_fn = _COMPARE_OPS.get(type(op))
            if op_fn is None:
                return False
            if not op_fn(left, right):
                return False
            left = right
        return True

    elif isinstance(node, ast.BinOp):
        left = _eval_node(node.left, ns)
        right = _eval_node(node.right, ns)
        op_fn = _BIN_OPS.get(type(node.op))
        if op_fn is None:
            return 0.0
        try:
            return op_fn(left, right)
        except ZeroDivisionError:
            return 0.0

    elif isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand, ns)
        op_fn = _UNARY_OPS.get(type(node.op))
        if op_fn is None:
            return operand
        return op_fn(operand)

    return 0.0


# ── Indicator Computation ─────────────────────────────────────────────

def _compute_composed_indicators(
    indicator_defs: List[Dict[str, Any]],
    bars: List[OHLCVBar],
    params: Dict[str, Any],
) -> Dict[str, List[float]]:
    """Compute all indicator series for a composed strategy.

    Each indicator definition specifies:
      - ``slug``: which built-in strategy to source from, OR
      - ``fn``: direct indicator function name from the shared library
      - ``args``: argument dict (with possible param references)
      - ``output_var``: name to store the computed series under

    Args:
        indicator_defs: Indicator node definitions.
        bars:           Chronological OHLCV bars.
        params:         Strategy parameter values.

    Returns:
        Dict of computed indicator series keyed by output variable name.
    """
    # Base price series
    series: Dict[str, List[float]] = {
        "close":  [b.close for b in bars],
        "open":   [b.open for b in bars],
        "high":   [b.high for b in bars],
        "low":    [b.low for b in bars],
        "volume": [b.volume for b in bars],
    }

    for defn in indicator_defs:
        fn_name = defn.get("fn", "")
        args = defn.get("args", {})
        output_var = defn.get("output_var", f"_var_{len(series)}")

        # Resolve param references in args
        resolved_args: Dict[str, Any] = {}
        for k, v in args.items():
            if isinstance(v, str) and v in params:
                resolved_args[k] = params[v]
            else:
                resolved_args[k] = v

        try:
            result = _call_indicator(fn_name, resolved_args, series, params)
        except Exception as exc:
            logger.warning(
                "Composed indicator '%s' (%s) failed: %s",
                output_var, fn_name, exc,
            )
            result = [0.0] * len(bars)

        # Handle tuple results (multi-output indicators)
        if isinstance(result, tuple):
            for idx, sub in enumerate(result):
                if isinstance(sub, list):
                    series[f"{output_var}__{idx}"] = sub
            if result and isinstance(result[0], list):
                series[output_var] = result[0]
        elif isinstance(result, list):
            series[output_var] = result

    return series


def _call_indicator(
    fn_name: str,
    args: Dict[str, Any],
    series: Dict[str, List[float]],
    params: Dict[str, Any],
) -> Any:
    """Dispatch indicator computation to the shared library.

    Args:
        fn_name: Indicator function name.
        args:    Resolved arguments.
        series:  Available named series.
        params:  Strategy parameters.

    Returns:
        Computed series or tuple of series.
    """
    # Resolve source reference
    def resolve(key: str, default: str = "close") -> List[float]:
        ref = args.get(key, default)
        if isinstance(ref, str) and ref in series:
            return series[ref]
        if isinstance(ref, (int, float)):
            return [float(ref)] * len(series.get("close", []))
        return series.get(default, [])

    if fn_name == "sma":
        return ind.sma(resolve("source"), int(args.get("period", 14)))
    elif fn_name == "ema":
        return ind.ema(resolve("source"), int(args.get("period", 14)))
    elif fn_name == "rsi":
        return ind.rsi(resolve("source"), int(args.get("period", 14)))
    elif fn_name == "macd":
        return ind.macd(
            resolve("source"), int(args.get("fast", 12)),
            int(args.get("slow", 26)), int(args.get("signal", 9)),
        )
    elif fn_name == "bollinger_bands":
        return ind.bollinger_bands(
            resolve("source"), int(args.get("period", 20)),
            float(args.get("num_std", 2.0)),
        )
    elif fn_name == "atr":
        return ind.atr(
            series["high"], series["low"], series["close"],
            int(args.get("period", 14)),
        )
    elif fn_name == "adx":
        return ind.adx(
            series["high"], series["low"], series["close"],
            int(args.get("period", 14)),
        )
    elif fn_name == "stochastic":
        return ind.stochastic(
            series["high"], series["low"], series["close"],
            int(args.get("k_period", 14)), int(args.get("d_period", 3)),
        )
    elif fn_name == "vwap":
        return ind.vwap(
            series["high"], series["low"], series["close"],
            series["volume"],
        )
    elif fn_name == "highest":
        return ind.highest(resolve("source", "high"), int(args.get("period", 20)))
    elif fn_name == "lowest":
        return ind.lowest(resolve("source", "low"), int(args.get("period", 20)))
    elif fn_name == "crossover":
        a = resolve("a", "close")
        b = resolve("b", "close")
        bools = ind.crossover(a, b)
        return [1.0 if v else 0.0 for v in bools]
    elif fn_name == "crossunder":
        a = resolve("a", "close")
        b = resolve("b", "close")
        bools = ind.crossunder(a, b)
        return [1.0 if v else 0.0 for v in bools]
    else:
        raise ValueError(f"Unknown indicator: {fn_name}")


# ── Signal Generation ─────────────────────────────────────────────────

def _generate_composed_signals(
    compiled: Dict[str, Any],
    bars: List[OHLCVBar],
    params: Dict[str, Any],
) -> List[Signal]:
    """Evaluate composed strategy bar-by-bar.

    Args:
        compiled: Composed strategy IR with indicators, entry_expr,
                  exit_expr, and optional stop_loss.
        bars:     Chronological OHLCV bars.
        params:   Strategy parameter values.

    Returns:
        List of Signal objects.
    """
    if not bars:
        return []

    indicator_defs = compiled.get("indicators", [])
    entry_expr_str = compiled.get("entry_expr", "")
    exit_expr_str = compiled.get("exit_expr", "")
    stop_loss = compiled.get("stop_loss")

    # Validate expressions
    entry_tree = _validate_expression(entry_expr_str) if entry_expr_str else None
    exit_tree = _validate_expression(exit_expr_str) if exit_expr_str else None

    # Compute all indicator series
    series = _compute_composed_indicators(indicator_defs, bars, params)

    # Determine warmup period from indicator args
    warmup = 0
    for defn in indicator_defs:
        for v in defn.get("args", {}).values():
            if isinstance(v, (int, float)) and v > 0:
                warmup = max(warmup, int(v))
    start_idx = min(warmup * 2, len(bars) - 1)

    signals: List[Signal] = []
    in_position = False
    entry_price = 0.0

    for i in range(start_idx, len(bars)):
        bar = bars[i]

        # Build namespace for expression evaluation at this bar
        ns: Dict[str, float] = {}
        for name, values in series.items():
            ns[name] = values[i] if i < len(values) else 0.0
        # Add param values to namespace
        for k, v in params.items():
            if isinstance(v, (int, float)):
                ns[k] = float(v)

        # Stop loss check
        if in_position and stop_loss:
            stop_val = stop_loss.get("value", 0)
            if isinstance(stop_val, str) and stop_val in params:
                stop_val = float(params[stop_val])
            else:
                stop_val = float(stop_val)
            stop_type = stop_loss.get("type", "pct")
            if stop_type == "pct":
                stop_price = entry_price * (1 - stop_val)
            else:
                stop_price = stop_val
            if bar.low <= stop_price:
                signals.append(Signal(
                    timestamp=bar.timestamp,
                    signal_type="stop_loss",
                    direction="long",
                    price=round(stop_price, 4),
                ))
                in_position = False
                continue

        # Entry check
        if not in_position and entry_tree:
            try:
                if _eval_expression(entry_tree, ns):
                    entry_price = bar.close
                    signals.append(Signal(
                        timestamp=bar.timestamp,
                        signal_type="entry",
                        direction="long",
                        price=entry_price,
                    ))
                    in_position = True
            except Exception as exc:
                logger.debug("Entry expression error at bar %d: %s", i, exc)

        # Exit check
        elif in_position and exit_tree:
            try:
                if _eval_expression(exit_tree, ns):
                    signals.append(Signal(
                        timestamp=bar.timestamp,
                        signal_type="exit",
                        direction="long",
                        price=bar.close,
                    ))
                    in_position = False
            except Exception as exc:
                logger.debug("Exit expression error at bar %d: %s", i, exc)

    return signals


# ── Public API ────────────────────────────────────────────────────────

def resolve_composed_signals(
    definition: Dict[str, Any],
) -> Callable[[List[OHLCVBar], Dict[str, Any]], List[Signal]]:
    """Create a signal-generator function from a composed strategy definition.

    The returned callable has the standard signature expected by
    ``BacktestEngine.run()``::

        signal_fn(bars: List[OHLCVBar], params: Dict) -> List[Signal]

    Args:
        definition: Complete definition_json dict (must contain
                    ``"compiled"`` key with indicators and expressions).

    Returns:
        Signal generator callable.
    """
    compiled = definition.get("compiled", {})
    default_params = definition.get("params", {})

    def signal_fn(
        bars: List[OHLCVBar],
        params: Dict[str, Any],
    ) -> List[Signal]:
        """Generate signals from composed strategy expressions.

        Args:
            bars:   Chronological OHLCV bars.
            params: Strategy parameters (overrides defaults).

        Returns:
            List of Signal objects.
        """
        merged = {**default_params, **params}
        return _generate_composed_signals(compiled, bars, merged)

    return signal_fn
