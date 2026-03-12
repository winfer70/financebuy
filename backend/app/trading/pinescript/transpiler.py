"""
PineScript Transpiler — converts a lark parse tree into the compiled
intermediate representation (IR) that the executor can run.

The transpiler walks the AST produced by ``grammar.parse()`` and maps
each supported node to a safe, whitelisted operation.  The output is a
``definition_json`` dict suitable for storage in the Strategy model's
JSONB column.

Key responsibilities:
  * Extract ``param_schema`` from ``input.*()`` calls.
  * Map ``ta.*`` calls to indicator definitions in the compiled IR.
  * Map ``strategy.entry/exit/close`` to signal definitions.
  * Map ``plot/hline`` to chart overlay definitions.
  * Reject any construct not in the whitelist.

Public API:
    transpile(source) -> dict   — parse + compile, returns definition_json
    PineScriptError             — base exception
    PineScriptSyntaxError       — parse failure
    PineScriptUnsupportedError  — unsupported construct
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any, Dict, List, Optional, Tuple

from lark import Token, Tree, Transformer, v_args

from .grammar import parse


# ── Exceptions ──────────────────────────────────────────────────────────

class PineScriptError(Exception):
    """Base exception for PineScript processing errors."""
    pass


class PineScriptSyntaxError(PineScriptError):
    """Raised when the PineScript source has syntax errors."""
    pass


class PineScriptUnsupportedError(PineScriptError):
    """Raised when a PineScript construct is not supported."""
    pass


# ── Whitelisted indicator functions ─────────────────────────────────────

#: Set of dotted function names that map to indicator computations.
INDICATOR_WHITELIST = {
    "ta.sma", "ta.ema", "ta.rsi", "ta.macd", "ta.bb", "ta.atr",
    "ta.adx", "ta.stoch", "ta.vwap", "ta.highest", "ta.lowest",
    "ta.crossover", "ta.crossunder",
}

MATH_WHITELIST = {
    "math.abs", "math.max", "math.min", "math.round",
}

STRATEGY_CALLS = {
    "strategy.entry", "strategy.exit", "strategy.close",
    "strategy.close_all",
}

INPUT_CALLS = {
    "input.int", "input.float", "input.bool", "input.string",
}

#: Maps ta.* function names to the shared indicator module function name.
TA_TO_INDICATOR = {
    "ta.sma": "sma",
    "ta.ema": "ema",
    "ta.rsi": "rsi",
    "ta.macd": "macd",
    "ta.bb": "bollinger_bands",
    "ta.atr": "atr",
    "ta.adx": "adx",
    "ta.stoch": "stochastic",
    "ta.vwap": "vwap",
    "ta.highest": "highest",
    "ta.lowest": "lowest",
    "ta.crossover": "crossover",
    "ta.crossunder": "crossunder",
}


# ── Compiled IR Structure ───────────────────────────────────────────────

def _empty_compiled() -> Dict[str, Any]:
    """Return an empty compiled IR skeleton.

    Returns:
        Dict with indicators, entry_conditions, exit_conditions,
        stop_loss, and overlays.
    """
    return {
        "indicators": [],
        "entry_conditions": [],
        "exit_conditions": [],
        "stop_loss": None,
        "overlays": [],
    }


# ── AST Visitor ─────────────────────────────────────────────────────────

class _PineScriptVisitor:
    """Walk a lark parse tree and build the compiled IR.

    Attributes:
        compiled:     The intermediate representation being built.
        params:       Default parameter values extracted from input.*() calls.
        param_schema: Schema items extracted from input.*() calls.
        variables:    Map of variable names to their resolved values/refs.
        warnings:     Non-fatal messages collected during transpilation.
    """

    def __init__(self) -> None:
        self.compiled: Dict[str, Any] = _empty_compiled()
        self.params: Dict[str, Any] = {}
        self.param_schema: List[Dict[str, Any]] = []
        self.variables: Dict[str, Any] = {}
        self.warnings: List[str] = []
        self._indicator_counter = 0
        self._condition_stack: List[Any] = []

    # -- Tree walking entry point --

    def visit(self, tree: Tree) -> None:
        """Recursively walk the parse tree and populate the compiled IR.

        Args:
            tree: lark.Tree root node.
        """
        if isinstance(tree, Tree):
            method = f"_visit_{tree.data}"
            if hasattr(self, method):
                getattr(self, method)(tree)
            else:
                # Recurse into children
                for child in tree.children:
                    if isinstance(child, Tree):
                        self.visit(child)

    # -- Statement handlers --

    def _visit_var_decl(self, node: Tree) -> None:
        """Process a variable declaration (var float x = expr)."""
        children = [c for c in node.children if not isinstance(c, Tree) or c.data != "type_hint"]
        name_tok = None
        expr_node = None
        for c in node.children:
            if isinstance(c, Token) and c.type == "NAME":
                name_tok = c
            elif isinstance(c, Tree) and c.data != "type_hint":
                expr_node = c
        if name_tok is None:
            return
        value = self._eval_expr(expr_node) if expr_node else None
        self.variables[str(name_tok)] = value

    def _visit_assignment(self, node: Tree) -> None:
        """Process an assignment (x := expr)."""
        name_tok = node.children[0]
        expr_node = node.children[1]
        self.variables[str(name_tok)] = self._eval_expr(expr_node)

    def _visit_expr_stmt(self, node: Tree) -> None:
        """Process a standalone expression (usually a function call)."""
        if node.children:
            self._eval_expr(node.children[0])

    def _process_strategy_call(self, node: Tree, call_type: str) -> None:
        """Process a strategy.entry/exit/close call and register the condition.

        Args:
            node:      The strategy call tree node (children are func_args).
            call_type: One of 'entry', 'exit', 'close', 'close_all'.
        """
        args_node = None
        for c in node.children:
            if isinstance(c, Tree) and str(c.data) == "func_args":
                args_node = c

        # Parse args
        args = self._parse_func_args(args_node) if args_node else ([], {})
        pos_args, kw_args = args

        # Determine direction from the first positional arg (trade id)
        trade_id = str(pos_args[0]).strip('"') if pos_args else "long"
        direction = "long" if "long" in trade_id.lower() else "short"

        # Detect stop loss from named args
        if kw_args.get("stop") or kw_args.get("loss"):
            stop_val = kw_args.get("stop") or kw_args.get("loss")
            self.compiled["stop_loss"] = {"type": "price", "value": stop_val}

        # Attach the current if-condition from the stack
        active_cond = self._condition_stack[-1] if self._condition_stack else None

        if call_type == "entry":
            self.compiled["entry_conditions"].append({
                "type": "strategy_entry",
                "direction": direction,
                "trade_id": trade_id,
                "condition": active_cond,
            })
        elif call_type == "close_all":
            self.compiled["exit_conditions"].append({
                "type": "strategy_close_all",
                "condition": active_cond,
            })
        else:
            # exit or close
            self.compiled["exit_conditions"].append({
                "type": "strategy_exit",
                "direction": direction,
                "trade_id": trade_id,
                "condition": active_cond,
            })

    def _visit_strategy_entry(self, node: Tree) -> None:
        """Handle strategy.entry() calls."""
        self._process_strategy_call(node, "entry")

    def _visit_strategy_exit(self, node: Tree) -> None:
        """Handle strategy.exit() calls."""
        self._process_strategy_call(node, "exit")

    def _visit_strategy_close(self, node: Tree) -> None:
        """Handle strategy.close() calls."""
        self._process_strategy_call(node, "close")

    def _visit_strategy_close_all(self, node: Tree) -> None:
        """Handle strategy.close_all() calls."""
        self._process_strategy_call(node, "close_all")

    def _visit_plot_call(self, node: Tree) -> None:
        """Process plot/hline/bgcolor calls → chart overlays."""
        args_node = None
        for c in node.children:
            if isinstance(c, Tree) and c.data == "func_args":
                args_node = c

        pos_args, kw_args = self._parse_func_args(args_node) if args_node else ([], {})
        source = str(pos_args[0]) if pos_args else "close"
        color = kw_args.get("color", "#3d7ef5")
        title = kw_args.get("title", source)

        self.compiled["overlays"].append({
            "type": "line",
            "source": source,
            "color": str(color).strip('"'),
            "title": str(title).strip('"'),
        })

    def _visit_if_block(self, node: Tree) -> None:
        """Process if/else blocks — extract conditions for entry/exit.

        Evaluates the if-condition expression and pushes it onto a stack
        so that strategy.entry/exit calls inside the block inherit
        the condition.
        """
        children = list(node.children)
        i = 0
        while i < len(children):
            child = children[i]
            if isinstance(child, Tree) and str(child.data) == "block":
                # This block belongs to the condition pushed before it
                self.visit(child)
                if self._condition_stack:
                    self._condition_stack.pop()
            elif isinstance(child, Tree) and str(child.data) != "block":
                # This is a condition expression for an if / else if
                cond = self._build_condition(child)
                self._condition_stack.append(cond)
            i += 1
        # Clean up any remaining conditions on the stack
        self._condition_stack.clear()

    def _build_condition(self, node: Any) -> Any:
        """Build a condition dict from an expression node.

        Converts comparisons, crossovers, and logical expressions
        into the structured condition format the executor expects.
        """
        if isinstance(node, Token):
            name = str(node)
            if name in self.variables:
                return self.variables[name]
            return name

        if not isinstance(node, Tree):
            return node

        rule = node.data

        if rule == "comparison":
            if len(node.children) >= 3:
                left = self._build_condition(node.children[0])
                op_node = node.children[1]
                op = str(op_node.children[0]) if isinstance(op_node, Tree) else str(op_node)
                right = self._build_condition(node.children[2])
                return {"type": "comparison", "left": left, "op": op, "right": right}
            # Single child (no operator) — pass through
            return self._build_condition(node.children[0])

        if rule in ("and_expr",):
            operands = [self._build_condition(c) for c in node.children
                        if isinstance(c, Tree) or (isinstance(c, Token) and c.type != "RULE")]
            if len(operands) == 1:
                return operands[0]
            return {"type": "logical", "op": "and", "operands": operands}

        if rule in ("or_expr",):
            operands = [self._build_condition(c) for c in node.children
                        if isinstance(c, Tree) or (isinstance(c, Token) and c.type != "RULE")]
            if len(operands) == 1:
                return operands[0]
            return {"type": "logical", "op": "or", "operands": operands}

        if rule == "not_expr":
            inner = self._build_condition(node.children[0])
            return {"type": "logical", "op": "not", "operands": [inner]}

        if rule == "func_call":
            # Crossover/crossunder become indicator references
            ref = self._eval_func_call(node)
            return ref

        # Recurse into wrapper rules
        for child in node.children:
            result = self._build_condition(child)
            if result is not None:
                return result
        return None

    def _visit_block(self, node: Tree) -> None:
        """Visit block contents."""
        for child in node.children:
            if isinstance(child, Tree):
                self.visit(child)

    # -- Expression evaluation --

    def _eval_expr(self, node: Any) -> Any:
        """Evaluate an expression node and return its value or reference.

        For most expressions this returns a string reference (variable
        name) or a literal value.  Function calls may produce side
        effects (registering indicators or input params).

        Args:
            node: lark Tree node or Token.

        Returns:
            Evaluated value (str reference, number, or dict).
        """
        if node is None:
            return None

        if isinstance(node, Token):
            if node.type == "NAME":
                name = str(node)
                # Built-in series references
                if name in ("close", "open", "high", "low", "volume"):
                    return name
                return self.variables.get(name, name)
            elif node.type == "NUMBER":
                val = str(node)
                return int(val) if "." not in val else float(val)
            elif node.type == "STRING":
                return str(node).strip('"')
            return str(node)

        if not isinstance(node, Tree):
            return node

        rule = node.data

        if rule == "func_call":
            return self._eval_func_call(node)
        elif rule == "series_access":
            name = str(node.children[0])
            offset = self._eval_expr(node.children[1])
            return f"{name}[{offset}]"
        elif rule in ("true_lit",):
            return True
        elif rule in ("false_lit",):
            return False
        elif rule in ("na_lit",):
            return None
        elif rule == "paren":
            return self._eval_expr(node.children[0])
        elif rule == "dotted_ref":
            # Resolve PineScript dotted constants (strategy.long, etc.)
            parts = [str(c) for c in node.children]
            full = ".".join(parts)
            _DOTTED_CONSTANTS = {
                "strategy.long": "long",
                "strategy.short": "short",
                "strategy.direction.long": "long",
                "strategy.direction.short": "short",
                "strategy.direction.all": "all",
            }
            return _DOTTED_CONSTANTS.get(full, full)
        elif rule == "neg":
            val = self._eval_expr(node.children[0])
            if isinstance(val, (int, float)):
                return -val
            return f"-{val}"
        elif rule == "comparison":
            return self._eval_comparison(node)
        elif rule in ("add_expr", "mul_expr"):
            return self._eval_binary(node)
        elif rule in ("or_expr", "and_expr"):
            return self._eval_logical(node)
        elif rule == "not_expr":
            return self._eval_expr(node.children[0])
        elif rule == "ternary":
            return self._eval_expr(node.children[1])
        elif rule in ("posarg", "kwarg"):
            # Unwrap argument wrappers
            return self._eval_expr(node.children[-1])

        # Fall through: recurse and return last child's value
        result = None
        for child in node.children:
            result = self._eval_expr(child)
        return result

    def _eval_func_call(self, node: Tree) -> Any:
        """Evaluate a function call node.

        Handles ta.*, input.*, math.*, and strategy.* calls.

        Args:
            node: func_call Tree node.

        Returns:
            Output variable reference for indicators, or param default
            for input calls.
        """
        # Reconstruct dotted name
        dotted = node.children[0]
        parts = [str(t) for t in dotted.children if isinstance(t, Token)]
        func_name = ".".join(parts)

        # Parse arguments
        args_node = node.children[1] if len(node.children) > 1 else None
        pos_args, kw_args = self._parse_func_args(args_node) if args_node else ([], {})

        # -- input.* calls → extract param_schema --
        if func_name in INPUT_CALLS:
            return self._handle_input_call(func_name, pos_args, kw_args)

        # -- ta.* calls → register indicator --
        if func_name in INDICATOR_WHITELIST:
            return self._handle_indicator_call(func_name, pos_args, kw_args)

        # -- math.* calls → pass through --
        if func_name in MATH_WHITELIST:
            return self._handle_math_call(func_name, pos_args)

        # -- strategy.* calls (handled at statement level) --
        if func_name in STRATEGY_CALLS:
            return None

        # Unknown function — warn but don't fail
        self.warnings.append(
            f"Unknown function '{func_name}' — ignored."
        )
        return None

    def _handle_input_call(
        self,
        func_name: str,
        pos_args: List[Any],
        kw_args: Dict[str, Any],
    ) -> Any:
        """Process an input.int/float/bool call.

        Extracts parameter name, default, min, max, step, and label
        into the param_schema.

        Args:
            func_name: Dotted function name (e.g. "input.int").
            pos_args:  Positional arguments.
            kw_args:   Keyword arguments.

        Returns:
            Default value for the parameter.
        """
        type_map = {
            "input.int": "int",
            "input.float": "float",
            "input.bool": "bool",
            "input.string": "string",
        }
        param_type = type_map.get(func_name, "float")
        defval = kw_args.get("defval", pos_args[0] if pos_args else 0)
        title = str(kw_args.get("title", f"param_{len(self.param_schema)}")).strip('"')
        # Sanitise param name: lowercase, replace spaces with underscores
        param_name = title.lower().replace(" ", "_").replace("%", "pct")

        schema_entry: Dict[str, Any] = {
            "name": param_name,
            "type": param_type,
            "default": defval,
            "label": title,
        }
        # Optional bounds
        if "minval" in kw_args:
            schema_entry["min"] = kw_args["minval"]
        if "maxval" in kw_args:
            schema_entry["max"] = kw_args["maxval"]
        if "step" in kw_args:
            schema_entry["step"] = kw_args["step"]

        self.param_schema.append(schema_entry)
        self.params[param_name] = defval
        # Store variable mapping so later refs resolve to the param name
        return param_name

    def _handle_indicator_call(
        self,
        func_name: str,
        pos_args: List[Any],
        kw_args: Dict[str, Any],
    ) -> str:
        """Process a ta.* indicator call.

        Registers the indicator in the compiled IR and returns an
        output variable name that other expressions can reference.

        Args:
            func_name: Dotted ta function name (e.g. "ta.sma").
            pos_args:  Positional arguments.
            kw_args:   Keyword arguments.

        Returns:
            String name of the output variable.
        """
        self._indicator_counter += 1
        indicator_fn = TA_TO_INDICATOR[func_name]
        output_var = f"_ind_{indicator_fn}_{self._indicator_counter}"

        # Build args dict from positional and keyword arguments
        args: Dict[str, Any] = {}

        # Map common positional argument patterns
        if func_name in ("ta.sma", "ta.ema"):
            args["source"] = str(pos_args[0]) if pos_args else "close"
            args["period"] = pos_args[1] if len(pos_args) > 1 else kw_args.get("length", 14)
        elif func_name == "ta.rsi":
            args["source"] = str(pos_args[0]) if pos_args else "close"
            args["period"] = pos_args[1] if len(pos_args) > 1 else kw_args.get("length", 14)
        elif func_name == "ta.macd":
            args["source"] = str(pos_args[0]) if pos_args else "close"
            args["fast"] = pos_args[1] if len(pos_args) > 1 else kw_args.get("fastlen", 12)
            args["slow"] = pos_args[2] if len(pos_args) > 2 else kw_args.get("slowlen", 26)
            args["signal"] = pos_args[3] if len(pos_args) > 3 else kw_args.get("siglen", 9)
        elif func_name == "ta.bb":
            args["source"] = str(pos_args[0]) if pos_args else "close"
            args["period"] = pos_args[1] if len(pos_args) > 1 else kw_args.get("length", 20)
            args["num_std"] = pos_args[2] if len(pos_args) > 2 else kw_args.get("mult", 2.0)
        elif func_name == "ta.atr":
            args["period"] = pos_args[0] if pos_args else kw_args.get("length", 14)
        elif func_name == "ta.adx":
            args["period"] = pos_args[0] if pos_args else kw_args.get("length", 14)
        elif func_name == "ta.stoch":
            args["k_period"] = pos_args[0] if pos_args else kw_args.get("k", 14)
            args["d_period"] = pos_args[1] if len(pos_args) > 1 else kw_args.get("d", 3)
        elif func_name == "ta.vwap":
            pass  # No args needed — computed from HLCV
        elif func_name in ("ta.highest", "ta.lowest"):
            args["source"] = str(pos_args[0]) if pos_args else "high" if "highest" in func_name else "low"
            args["period"] = pos_args[1] if len(pos_args) > 1 else kw_args.get("length", 20)
        elif func_name in ("ta.crossover", "ta.crossunder"):
            args["a"] = str(pos_args[0]) if pos_args else ""
            args["b"] = str(pos_args[1]) if len(pos_args) > 1 else ""

        self.compiled["indicators"].append({
            "fn": indicator_fn,
            "args": args,
            "output_var": output_var,
        })

        return output_var

    def _handle_math_call(self, func_name: str, pos_args: List[Any]) -> Any:
        """Process a math.* call with literal evaluation where possible.

        Args:
            func_name: Dotted math function name.
            pos_args:  Positional arguments.

        Returns:
            Literal result or string reference.
        """
        # Try to evaluate with literal values
        nums = [a for a in pos_args if isinstance(a, (int, float))]
        if func_name == "math.abs" and len(nums) == 1:
            return abs(nums[0])
        elif func_name == "math.max" and len(nums) >= 2:
            return max(nums)
        elif func_name == "math.min" and len(nums) >= 2:
            return min(nums)
        elif func_name == "math.round" and len(nums) >= 1:
            return round(nums[0])
        return f"{func_name}({', '.join(str(a) for a in pos_args)})"

    def _eval_comparison(self, node: Tree) -> Dict[str, Any]:
        """Evaluate a comparison expression into a condition dict.

        Args:
            node: comparison Tree node.

        Returns:
            Dict describing the comparison condition.
        """
        children = node.children
        if len(children) < 3:
            return self._eval_expr(children[0]) if children else None

        left = self._eval_expr(children[0])
        op_node = children[1]
        right = self._eval_expr(children[2])

        # Extract operator text
        op = str(op_node.children[0]) if isinstance(op_node, Tree) else str(op_node)

        return {"type": "comparison", "left": left, "op": op, "right": right}

    def _eval_binary(self, node: Tree) -> Any:
        """Evaluate arithmetic binary expression.

        Args:
            node: add_expr or mul_expr Tree node.

        Returns:
            Result of the arithmetic, or a string expression.
        """
        result = self._eval_expr(node.children[0])
        i = 1
        while i < len(node.children):
            op = str(node.children[i])
            right = self._eval_expr(node.children[i + 1])
            # If both are numeric literals, compute
            if isinstance(result, (int, float)) and isinstance(right, (int, float)):
                if op == "+":
                    result = result + right
                elif op == "-":
                    result = result - right
                elif op == "*":
                    result = result * right
                elif op == "/" and right != 0:
                    result = result / right
                elif op == "%":
                    result = result % right
            else:
                result = f"({result} {op} {right})"
            i += 2
        return result

    def _eval_logical(self, node: Tree) -> Dict[str, Any]:
        """Evaluate logical and/or expression.

        Args:
            node: or_expr or and_expr Tree node.

        Returns:
            Dict describing the logical operation.
        """
        op = "and" if node.data == "and_expr" else "or"
        operands = [self._eval_expr(c) for c in node.children if isinstance(c, Tree)]
        if len(operands) == 1:
            return operands[0]
        return {"type": "logical", "op": op, "operands": operands}

    # -- Argument parsing helpers --

    def _parse_func_args(
        self, node: Optional[Tree]
    ) -> Tuple[List[Any], Dict[str, Any]]:
        """Parse function arguments from a func_args node.

        Args:
            node: func_args Tree node, or None.

        Returns:
            Tuple of (positional_args, keyword_args).
        """
        if node is None:
            return [], {}
        pos: List[Any] = []
        kw: Dict[str, Any] = {}
        for child in node.children:
            if isinstance(child, Tree):
                if child.data == "kwarg":
                    key = str(child.children[0])
                    val = self._eval_expr(child.children[1])
                    kw[key] = val
                elif child.data == "posarg":
                    pos.append(self._eval_expr(child.children[0]))
                else:
                    pos.append(self._eval_expr(child))
            else:
                pos.append(self._eval_expr(child))
        return pos, kw


# ── Public API ──────────────────────────────────────────────────────────

def transpile(source: str) -> Dict[str, Any]:
    """Parse PineScript source and compile to executable IR.

    Full pipeline: source → parse tree → compiled IR → definition_json.

    Args:
        source: Raw PineScript source code.

    Returns:
        Complete definition_json dict ready for storage in
        Strategy.definition_json.

    Raises:
        PineScriptSyntaxError:      On parse failure.
        PineScriptUnsupportedError: On unsupported constructs.
    """
    try:
        tree = parse(source)
    except Exception as exc:
        raise PineScriptSyntaxError(f"PineScript parse error: {exc}") from exc

    visitor = _PineScriptVisitor()
    visitor.visit(tree)

    # Compute a hash of the source for caching
    source_hash = hashlib.sha256(source.encode()).hexdigest()

    # Generate a unique slug
    slug = f"pinescript_{uuid.uuid4().hex[:8]}"

    return {
        "strategy_slug": slug,
        "source_type": "pinescript",
        "source_code": source,
        "transpile_method": "lark",
        "transpile_hash": source_hash,
        "compiled": visitor.compiled,
        "params": visitor.params,
        "param_schema": visitor.param_schema,
    }
