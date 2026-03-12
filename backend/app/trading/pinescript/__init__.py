"""
PineScript Parser & Transpiler — converts PineScript source to executable
strategy definitions.

This package implements a subset of TradingView's PineScript language,
parsing user-authored scripts into an intermediate representation (IR)
that the BacktestEngine can execute.  Two translation paths exist:

  * **Deterministic (lark)** — parses a supported grammar subset with
    guaranteed safety.  Strategies get a "Verified" badge.
  * **LLM fallback** — sends unsupported scripts to Ollama for
    translation, then validates the result via AST whitelist.
    Strategies get an "AI-Translated" badge.

Public API:
    validate(source)   — syntax check only, returns errors list
    transpile(source)  — full parse → compile → definition dict
    resolve_pinescript_signals(definition) → signal generator callable
    llm_transpile(source) — LLM fallback translation (async)
    PineScriptError / PineScriptSyntaxError / PineScriptUnsupportedError
    LLMTranspileError
"""

from __future__ import annotations

from .grammar import validate
from .transpiler import transpile
from .transpiler import PineScriptError, PineScriptSyntaxError, PineScriptUnsupportedError
from .executor import resolve_pinescript_signals
from .llm_fallback import llm_transpile, LLMTranspileError

__all__ = [
    "validate",
    "transpile",
    "resolve_pinescript_signals",
    "llm_transpile",
    "PineScriptError",
    "PineScriptSyntaxError",
    "PineScriptUnsupportedError",
    "LLMTranspileError",
]
