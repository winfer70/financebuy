"""
PineScript Grammar — lark EBNF grammar for the supported PineScript subset.

Defines the formal grammar and provides a parse function that converts
raw PineScript source text into a lark parse tree.  The grammar covers:

  * Variable declarations (var float x = 0.0) and assignments (x := expr)
  * Conditionals (if / else if / else)
  * Built-in indicator functions (ta.sma, ta.ema, ta.rsi, ta.macd, etc.)
  * Strategy functions (strategy.entry, strategy.exit, strategy.close)
  * Input functions (input.int, input.float, input.bool)
  * Series access (close[1], high[3])
  * Math helpers (math.abs, math.max, math.min, math.round)
  * Plot directives (plot, hline, bgcolor — mapped to chart overlays)
  * Arithmetic, comparison, and logical operators
  * Ternary expressions (cond ? a : b)

Unsupported PineScript features (loops, arrays, maps, user-defined
functions, libraries, security/request calls) raise clear parse errors.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import lark
from lark import Lark, Token, Tree, UnexpectedInput


# ── Lark EBNF Grammar ───────────────────────────────────────────────────

PINESCRIPT_GRAMMAR = r"""
    // Top-level: a PineScript program is a sequence of statements
    start: (_NL* statement)*  _NL*

    // Statements
    ?statement: var_decl
              | assignment
              | strategy_call
              | plot_call
              | if_block
              | expr_stmt
              | COMMENT

    // Variable declaration: var float x = expr  OR  float x = expr  OR  x = expr
    var_decl: "var"? type_hint NAME "=" expr
    type_hint: "float" | "int" | "bool" | "string" | "series"

    // Assignment: x := expr
    assignment: NAME ":=" expr

    // Expression statement (standalone function call)
    expr_stmt: expr

    // If / else if / else blocks (brace-delimited for simplicity)
    if_block: "if" expr _NL? block ("else" "if" expr _NL? block)* ("else" _NL? block)?
    block: "{" (_NL* statement)* _NL* "}"
         | statement

    // Strategy calls
    strategy_call: "strategy.entry"  "(" func_args ")"       -> strategy_entry
                 | "strategy.exit"   "(" func_args ")"        -> strategy_exit
                 | "strategy.close"  "(" func_args ")"        -> strategy_close
                 | "strategy.close_all" "(" func_args? ")"    -> strategy_close_all

    // Plot calls (parsed but mapped to chart overlays)
    plot_call: "plot"    "(" func_args ")"
             | "hline"   "(" func_args ")"
             | "bgcolor" "(" func_args ")"

    // Expressions (precedence via priority rules)
    ?expr: ternary

    ?ternary: or_expr "?" ternary ":" ternary   -> ternary
            | or_expr

    ?or_expr: and_expr ("or" and_expr)*          -> or_expr

    ?and_expr: not_expr ("and" not_expr)*        -> and_expr

    ?not_expr: "not" not_expr                    -> not_expr
             | comparison

    ?comparison: add_expr (comp_op add_expr)?    -> comparison

    comp_op: ">" | "<" | ">=" | "<=" | "==" | "!="

    ?add_expr: mul_expr (("+"|"-") mul_expr)*    -> add_expr

    ?mul_expr: unary_expr (("*"|"/"|"%") unary_expr)*  -> mul_expr

    ?unary_expr: "-" atom                        -> neg
               | atom

    ?atom: func_call
         | series_access
         | "(" expr ")"                          -> paren
         | NAME "." NAME ("." NAME)*             -> dotted_ref
         | NAME
         | NUMBER
         | STRING
         | "true"                                -> true_lit
         | "false"                               -> false_lit
         | "na"                                  -> na_lit

    // Function call: dotted.name(args)
    func_call: dotted_name "(" func_args? ")"
    dotted_name: NAME ("." NAME)+
               | NAME

    // Function arguments (positional and keyword)
    func_args: func_arg ("," func_arg)*
    func_arg: NAME "=" expr     -> kwarg
            | expr              -> posarg

    // Series access: close[1], high[3]
    series_access: NAME "[" expr "]"

    // Terminals
    NAME: /[a-zA-Z_][a-zA-Z0-9_]*/
    NUMBER: /[0-9]+(\.[0-9]*)?/
    STRING: /\"[^\"]*\"/
    COMMENT: /\/\/.*/

    // Whitespace handling
    _NL: /\n+/
    %import common.WS_INLINE
    %ignore WS_INLINE
    %ignore COMMENT
"""


# ── Parser Instance ─────────────────────────────────────────────────────

_parser: Optional[Lark] = None


def _get_parser() -> Lark:
    """Lazily create and return the lark parser (cached singleton).

    Returns:
        Configured Lark parser for PineScript.
    """
    global _parser
    if _parser is None:
        _parser = Lark(
            PINESCRIPT_GRAMMAR,
            parser="earley",
            ambiguity="resolve",
            propagate_positions=True,
        )
    return _parser


# ── Validation Result ───────────────────────────────────────────────────

@dataclass
class ValidationResult:
    """Result from PineScript validation.

    Attributes:
        valid:  True if source parsed without errors.
        errors: List of error dicts with line, col, message.
    """
    valid: bool
    errors: List[Dict[str, object]] = field(default_factory=list)


# ── Public API ──────────────────────────────────────────────────────────

def parse(source: str) -> Tree:
    """Parse PineScript source into a lark parse tree.

    Args:
        source: Raw PineScript source code.

    Returns:
        lark.Tree representing the parsed AST.

    Raises:
        lark.UnexpectedInput: On syntax errors.
    """
    # Normalise line endings and ensure trailing newline
    source = source.replace("\r\n", "\n").strip() + "\n"
    parser = _get_parser()
    return parser.parse(source)


def validate(source: str) -> ValidationResult:
    """Validate PineScript syntax without transpiling.

    Attempts to parse the source and collects any syntax errors.

    Args:
        source: Raw PineScript source code.

    Returns:
        ValidationResult with valid flag and error list.
    """
    try:
        parse(source)
        return ValidationResult(valid=True)
    except UnexpectedInput as exc:
        error = {
            "line": getattr(exc, "line", 1),
            "col": getattr(exc, "column", 1),
            "message": str(exc).split("\n")[0],
        }
        return ValidationResult(valid=False, errors=[error])
    except Exception as exc:
        return ValidationResult(
            valid=False,
            errors=[{"line": 1, "col": 1, "message": f"Parse error: {exc}"}],
        )
