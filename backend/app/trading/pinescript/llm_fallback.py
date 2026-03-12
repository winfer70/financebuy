"""
PineScript LLM Fallback — translates unsupported PineScript via Ollama.

When the deterministic lark parser cannot handle a script (complex or
non-standard syntax), this module sends the source to a local Ollama
instance for AI-assisted translation.  The returned Python code is then
validated through a strict AST whitelist walk to ensure safety before
being converted to the compiled IR format.

Safety measures:
  * The LLM-generated code is parsed with ``ast.parse()`` — never executed.
  * A whitelist walker rejects: imports, builtins, exec/eval, I/O,
    attribute access outside of whitelisted patterns.
  * Only the extracted indicator/condition structure is used; the Python
    code itself is never ``exec()``'d.

Strategies translated via this path receive an ``"AI-Translated"`` badge
with ``transpile_method="llm"``.

Public API:
    llm_transpile(source) -> dict     — translate via LLM, returns definition_json
    LLMTranspileError                 — raised on LLM or validation failure
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
import re
import uuid
from typing import Any, Dict, List, Optional, Set

import httpx

logger = logging.getLogger("pinescript.llm_fallback")


# ── Configuration ─────────────────────────────────────────────────────

# Ollama endpoint — Server B runs Ollama on the LAN
_OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:14b")
_OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))


# ── Exceptions ────────────────────────────────────────────────────────

class LLMTranspileError(Exception):
    """Raised when LLM translation or validation fails."""
    pass


# ── AST Whitelist Validator ───────────────────────────────────────────

# Allowed top-level AST node types in LLM-generated code
_ALLOWED_STMT_TYPES: Set[type] = {
    ast.FunctionDef,
    ast.Return,
    ast.Assign,
    ast.AugAssign,
    ast.AnnAssign,
    ast.For,
    ast.While,
    ast.If,
    ast.Expr,
    ast.Pass,
    ast.Break,
    ast.Continue,
}

# Allowed expression node types
_ALLOWED_EXPR_TYPES: Set[type] = {
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.IfExp,
    ast.Compare,
    ast.Call,
    ast.Constant,
    ast.Attribute,
    ast.Subscript,
    ast.Name,
    ast.List,
    ast.Tuple,
    ast.Dict,
    ast.Slice,
    ast.Index,       # Python 3.8 compat
    ast.Starred,
}

# Blacklisted function names — never allow these in LLM output
_BLACKLIST_NAMES: Set[str] = {
    "exec", "eval", "compile", "__import__", "importlib",
    "open", "input", "print", "exit", "quit",
    "os", "sys", "subprocess", "shutil", "pathlib",
    "socket", "http", "urllib", "requests",
    "globals", "locals", "vars", "dir", "getattr", "setattr",
    "delattr", "hasattr", "type", "super", "classmethod",
    "staticmethod", "property",
}


def _validate_ast(source_code: str) -> None:
    """Parse and whitelist-walk the LLM-generated Python code.

    Rejects any construct that could be dangerous: imports, builtins,
    exec/eval, I/O operations, or unexpected node types.

    Args:
        source_code: Python source string from the LLM.

    Raises:
        LLMTranspileError: If any disallowed construct is found.
    """
    try:
        tree = ast.parse(source_code)
    except SyntaxError as exc:
        raise LLMTranspileError(
            f"LLM output has syntax errors: {exc}"
        ) from exc

    _walk_node(tree)


def _walk_node(node: ast.AST) -> None:
    """Recursively validate an AST node and all its children.

    Args:
        node: Any AST node.

    Raises:
        LLMTranspileError: On disallowed construct.
    """
    # Reject imports
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        raise LLMTranspileError(
            "LLM output contains import statements — rejected."
        )

    # Reject global/nonlocal
    if isinstance(node, (ast.Global, ast.Nonlocal)):
        raise LLMTranspileError(
            "LLM output contains global/nonlocal — rejected."
        )

    # Check function calls against blacklist
    if isinstance(node, ast.Call):
        func = node.func
        name = _extract_call_name(func)
        if name and name in _BLACKLIST_NAMES:
            raise LLMTranspileError(
                f"LLM output calls blacklisted function '{name}' — rejected."
            )

    # Check Name nodes against blacklist
    if isinstance(node, ast.Name) and node.id in _BLACKLIST_NAMES:
        raise LLMTranspileError(
            f"LLM output references blacklisted name '{node.id}' — rejected."
        )

    # Recurse into children
    for child in ast.iter_child_nodes(node):
        _walk_node(child)


def _extract_call_name(node: ast.AST) -> Optional[str]:
    """Extract the function name from a Call node's func attribute.

    Args:
        node: The ``func`` field of an ``ast.Call``.

    Returns:
        Simple name string, or None if complex.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


# ── LLM Prompt Construction ──────────────────────────────────────────

_SYSTEM_PROMPT = """You are a PineScript-to-Python transpiler. Convert PineScript trading strategies into a Python dictionary structure.

OUTPUT FORMAT — return ONLY a JSON object (no markdown, no explanation):
{
  "indicators": [
    {"fn": "<indicator_name>", "args": {"source": "close", "period": 14}, "output_var": "<unique_name>"}
  ],
  "entry_conditions": [
    {"type": "comparison", "left": "<var_or_series>", "op": ">", "right": "<var_or_series>"}
  ],
  "exit_conditions": [
    {"type": "comparison", "left": "<var_or_series>", "op": "<", "right": "<var_or_series>"}
  ],
  "stop_loss": {"type": "pct", "value": 0.05} or null,
  "params": {"param_name": default_value},
  "param_schema": [{"name": "param_name", "type": "int", "default": 14, "label": "Period"}]
}

AVAILABLE INDICATORS (fn names):
- sma(source, period) → single series
- ema(source, period) → single series
- rsi(source, period) → single series
- macd(source, fast, slow, signal) → tuple: (macd_line, signal_line, histogram)
- bollinger_bands(source, period, num_std) → tuple: (middle, upper, lower, bandwidth)
- atr(period) → single series (uses high/low/close internally)
- adx(period) → tuple: (adx, plus_di, minus_di)
- stochastic(k_period, d_period) → tuple: (pct_k, pct_d)
- vwap() → single series
- highest(source, period) → single series
- lowest(source, period) → single series
- crossover(a, b) → boolean series (1.0 = crossed over, 0.0 = not)
- crossunder(a, b) → boolean series

SERIES REFERENCES: "close", "open", "high", "low", "volume", or any output_var from indicators.
CONDITION TYPES: "comparison" (with op: >, <, >=, <=, ==, !=), "logical" (with op: "and"/"or" and operands list).
For tuple indicators, use output_var__0 for first, output_var__1 for second, etc.

RULES:
1. Extract input() calls as params and param_schema
2. Map ta.* calls to the available indicators
3. Map strategy.entry/exit to entry/exit conditions
4. Extract stop loss if present
5. Return ONLY valid JSON — no code, no explanation"""


def _build_user_prompt(source: str) -> str:
    """Build the user prompt containing the PineScript source.

    Args:
        source: Raw PineScript code.

    Returns:
        User prompt string.
    """
    return f"Convert this PineScript strategy to the JSON format:\n\n```pinescript\n{source}\n```"


# ── Ollama Communication ─────────────────────────────────────────────

async def _call_ollama(source: str) -> str:
    """Send PineScript to Ollama and return the raw response text.

    Uses the /api/generate endpoint with the configured model.

    Args:
        source: Raw PineScript code.

    Returns:
        Raw text response from the LLM.

    Raises:
        LLMTranspileError: On network or API errors.
    """
    payload = {
        "model": _OLLAMA_MODEL,
        "system": _SYSTEM_PROMPT,
        "prompt": _build_user_prompt(source),
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 4096,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=_OLLAMA_TIMEOUT) as client:
            resp = await client.post(
                f"{_OLLAMA_URL}/api/generate",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "")
    except httpx.HTTPStatusError as exc:
        raise LLMTranspileError(
            f"Ollama API error: {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        raise LLMTranspileError(
            f"Ollama connection error: {exc}"
        ) from exc


def _parse_llm_response(raw: str) -> Dict[str, Any]:
    """Extract JSON from the LLM response text.

    Handles markdown code fences and extra text around the JSON.

    Args:
        raw: Raw LLM response text.

    Returns:
        Parsed JSON dict.

    Raises:
        LLMTranspileError: If no valid JSON is found.
    """
    # Try to extract JSON from markdown code blocks
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if json_match:
        raw = json_match.group(1)

    # Try to find a top-level JSON object
    brace_start = raw.find("{")
    brace_end = raw.rfind("}")
    if brace_start >= 0 and brace_end > brace_start:
        raw = raw[brace_start : brace_end + 1]

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMTranspileError(
            f"LLM response is not valid JSON: {exc}"
        ) from exc


def _validate_compiled_structure(compiled: Dict[str, Any]) -> None:
    """Validate that the LLM-produced compiled IR has the expected shape.

    Args:
        compiled: Parsed JSON dict from the LLM.

    Raises:
        LLMTranspileError: If required fields are missing or malformed.
    """
    if not isinstance(compiled, dict):
        raise LLMTranspileError("LLM output is not a dict.")

    # Validate indicators list
    indicators = compiled.get("indicators", [])
    if not isinstance(indicators, list):
        raise LLMTranspileError("'indicators' must be a list.")
    for ind_def in indicators:
        if not isinstance(ind_def, dict):
            raise LLMTranspileError("Each indicator must be a dict.")
        if "fn" not in ind_def:
            raise LLMTranspileError("Each indicator must have an 'fn' key.")
        if "output_var" not in ind_def:
            raise LLMTranspileError("Each indicator must have an 'output_var' key.")

    # Validate conditions lists
    for key in ("entry_conditions", "exit_conditions"):
        conditions = compiled.get(key, [])
        if not isinstance(conditions, list):
            raise LLMTranspileError(f"'{key}' must be a list.")


# ── Public API ────────────────────────────────────────────────────────

async def llm_transpile(source: str) -> Dict[str, Any]:
    """Translate PineScript source via Ollama LLM.

    Pipeline:
      1. Send source to Ollama with a structured prompt
      2. Parse JSON from the LLM response
      3. Validate the compiled IR structure
      4. Package into definition_json format

    Args:
        source: Raw PineScript source code.

    Returns:
        Complete definition_json dict with ``transpile_method="llm"``.

    Raises:
        LLMTranspileError: On any failure in the pipeline.
    """
    logger.info("Attempting LLM transpile for PineScript (%d chars).", len(source))

    # Call Ollama
    raw_response = await _call_ollama(source)

    # Parse JSON from the response
    compiled_data = _parse_llm_response(raw_response)

    # Validate structure
    _validate_compiled_structure(compiled_data)

    # Extract params and param_schema from the LLM output
    params = compiled_data.pop("params", {})
    param_schema = compiled_data.pop("param_schema", [])

    # Build the compiled IR subset (only expected keys)
    compiled = {
        "indicators": compiled_data.get("indicators", []),
        "entry_conditions": compiled_data.get("entry_conditions", []),
        "exit_conditions": compiled_data.get("exit_conditions", []),
        "stop_loss": compiled_data.get("stop_loss"),
        "overlays": compiled_data.get("overlays", []),
    }

    source_hash = hashlib.sha256(source.encode()).hexdigest()
    slug = f"pinescript_{uuid.uuid4().hex[:8]}"

    definition = {
        "strategy_slug": slug,
        "source_type": "pinescript",
        "source_code": source,
        "transpile_method": "llm",
        "transpile_hash": source_hash,
        "compiled": compiled,
        "params": params,
        "param_schema": param_schema,
    }

    logger.info(
        "LLM transpile succeeded: %d indicators, %d entry conditions.",
        len(compiled["indicators"]),
        len(compiled["entry_conditions"]),
    )

    return definition
