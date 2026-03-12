/**
 * PineScriptEditor — textarea-based PineScript code editor with syntax
 * highlighting, line numbers, and validate/transpile buttons.
 *
 * Uses a textarea overlaid with a <pre><code> for regex-based syntax
 * highlighting. No external editor dependencies (Monaco, CodeMirror).
 *
 * Props:
 *   token        — JWT auth token
 *   onTranspiled — (definition, strategyId) callback after successful transpile
 */

import React, { useState, useRef, useCallback } from "react";
import api from "../../api/client";

/* ── PineScript syntax highlighting (regex-based) ─────────────────────── */

const PINE_KEYWORDS = [
  "strategy", "indicator", "if", "else", "for", "while", "var",
  "true", "false", "na", "and", "or", "not", "series", "float",
  "int", "bool", "string", "color", "import", "export",
];

const PINE_BUILTINS = [
  "ta\\.sma", "ta\\.ema", "ta\\.rsi", "ta\\.macd", "ta\\.bb",
  "ta\\.atr", "ta\\.adx", "ta\\.stoch", "ta\\.vwap",
  "ta\\.highest", "ta\\.lowest", "ta\\.crossover", "ta\\.crossunder",
  "math\\.abs", "math\\.max", "math\\.min", "math\\.sqrt", "math\\.log",
  "strategy\\.entry", "strategy\\.exit", "strategy\\.close",
  "strategy\\.close_all",
  "input\\.int", "input\\.float", "input\\.bool", "input\\.string",
  "plot", "hline", "bgcolor", "barcolor",
];

const PINE_SERIES = ["close", "open", "high", "low", "volume", "bar_index"];

/**
 * Apply regex-based syntax highlighting to PineScript source.
 * Returns HTML string with <span> wrappers for each token type.
 *
 * @param {string} code - Raw PineScript source
 * @returns {string} HTML with syntax highlighting spans
 */
function highlight(code) {
  if (!code) return "";
  let html = code
    // Escape HTML entities first
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // Comments (// ...)
  html = html.replace(/(\/\/.*$)/gm, '<span style="color: var(--muted)">$1</span>');

  // Strings
  html = html.replace(/("(?:[^"\\]|\\.)*")/g, '<span style="color: #98c379">$1</span>');
  html = html.replace(/('(?:[^'\\]|\\.)*')/g, '<span style="color: #98c379">$1</span>');

  // Numbers
  html = html.replace(/\b(\d+\.?\d*)\b/g, '<span style="color: #d19a66">$1</span>');

  // Built-in functions (ta.*, strategy.*, input.*, etc.)
  const builtinRe = new RegExp(`\\b(${PINE_BUILTINS.join("|")})\\b`, "g");
  html = html.replace(builtinRe, '<span style="color: #61afef">$1</span>');

  // Series names
  const seriesRe = new RegExp(`\\b(${PINE_SERIES.join("|")})\\b`, "g");
  html = html.replace(seriesRe, '<span style="color: #e5c07b">$1</span>');

  // Keywords
  const kwRe = new RegExp(`\\b(${PINE_KEYWORDS.join("|")})\\b`, "g");
  html = html.replace(kwRe, '<span style="color: #c678dd">$1</span>');

  return html;
}

/* ── Default template ─────────────────────────────────────────────────── */

const DEFAULT_TEMPLATE = `//@version=5
strategy("My Strategy", overlay=true)

// Inputs
fast_period = input.int(10, "Fast Period", minval=2)
slow_period = input.int(50, "Slow Period", minval=5)
stop_loss_pct = input.float(0.05, "Stop Loss %", minval=0.005, step=0.005)

// Indicators
fast_sma = ta.sma(close, fast_period)
slow_sma = ta.sma(close, slow_period)

// Signals
if ta.crossover(fast_sma, slow_sma)
    strategy.entry("Long", strategy.long)
if ta.crossunder(fast_sma, slow_sma)
    strategy.close("Long")

// Plots
plot(fast_sma, color=color.blue, title="Fast SMA")
plot(slow_sma, color=color.red, title="Slow SMA")
`;

/* ── Component ──────────────────────────────────────────────────────── */

export default function PineScriptEditor({ token, onTranspiled }) {
  const [code, setCode] = useState(DEFAULT_TEMPLATE);
  const [name, setName] = useState("");
  const [errors, setErrors] = useState([]);
  const [warnings, setWarnings] = useState([]);
  const [status, setStatus] = useState("");        // "validating" | "transpiling" | ""
  const [useLlm, setUseLlm] = useState(false);
  const textareaRef = useRef(null);
  const preRef = useRef(null);

  // Sync scroll between textarea and highlighted overlay
  const syncScroll = useCallback(() => {
    if (preRef.current && textareaRef.current) {
      preRef.current.scrollTop = textareaRef.current.scrollTop;
      preRef.current.scrollLeft = textareaRef.current.scrollLeft;
    }
  }, []);

  // Line numbers
  const lineCount = (code || "").split("\n").length;
  const lineNums = Array.from({ length: lineCount }, (_, i) => i + 1).join("\n");

  // Validate syntax
  const handleValidate = async () => {
    setStatus("validating");
    setErrors([]);
    setWarnings([]);
    try {
      const result = await api.validatePinescript(code, token);
      if (result.valid) {
        setStatus("");
        setErrors([]);
      } else {
        setErrors(result.errors.map((e) => e.message || JSON.stringify(e)));
        setStatus("");
      }
    } catch (err) {
      setErrors([err.message]);
      setStatus("");
    }
  };

  // Transpile + create strategy
  const handleTranspile = async () => {
    if (!name.trim()) {
      setErrors(["Strategy name is required."]);
      return;
    }
    setStatus("transpiling");
    setErrors([]);
    setWarnings([]);
    try {
      const result = await api.transpilePinescript(
        {
          source_code: code,
          name: name.trim(),
          use_llm_fallback: useLlm,
        },
        token,
      );
      if (result.success) {
        setStatus("");
        setWarnings(result.warnings || []);
        if (onTranspiled) onTranspiled(result.definition_json, result.strategy_id);
      } else {
        setErrors(result.errors || ["Transpilation failed."]);
        setWarnings(result.warnings || []);
        setStatus("");
      }
    } catch (err) {
      setErrors([err.message]);
      setStatus("");
    }
  };

  return (
    <div className="panel" style={{ padding: 12 }}>
      <div className="panel-title" style={{ marginBottom: 8 }}>PINESCRIPT EDITOR</div>

      {/* Strategy name */}
      <div className="form-field" style={{ marginBottom: 8 }}>
        <label className="form-label">STRATEGY NAME</label>
        <input
          className="form-control"
          type="text"
          placeholder="My SMA Strategy"
          value={name}
          onChange={(e) => setName(e.target.value)}
          style={{ fontSize: 11 }}
        />
      </div>

      {/* Editor area: line numbers + textarea + highlight overlay */}
      <div style={{ display: "flex", position: "relative", border: "1px solid var(--border)", borderRadius: 4, overflow: "hidden" }}>
        {/* Line numbers */}
        <pre style={{
          margin: 0, padding: "8px 6px", background: "var(--panel-bg)", color: "var(--muted)",
          fontSize: 11, lineHeight: "16px", fontFamily: "monospace", textAlign: "right",
          userSelect: "none", borderRight: "1px solid var(--border)", minWidth: 30,
          overflow: "hidden",
        }}>
          {lineNums}
        </pre>

        {/* Highlight overlay */}
        <pre
          ref={preRef}
          aria-hidden="true"
          style={{
            position: "absolute", left: 38, top: 0, right: 0, bottom: 0,
            margin: 0, padding: 8, overflow: "hidden", pointerEvents: "none",
            fontSize: 11, lineHeight: "16px", fontFamily: "monospace",
            whiteSpace: "pre-wrap", wordWrap: "break-word",
            color: "var(--text)", background: "transparent",
          }}
          dangerouslySetInnerHTML={{ __html: highlight(code) + "\n" }}
        />

        {/* Textarea (transparent text, visible caret) */}
        <textarea
          ref={textareaRef}
          value={code}
          onChange={(e) => setCode(e.target.value)}
          onScroll={syncScroll}
          spellCheck={false}
          style={{
            flex: 1, margin: 0, padding: 8, border: "none", outline: "none",
            resize: "vertical", minHeight: 280,
            fontSize: 11, lineHeight: "16px", fontFamily: "monospace",
            whiteSpace: "pre-wrap", wordWrap: "break-word",
            color: "transparent", caretColor: "var(--text)",
            background: "var(--panel-bg)",
          }}
        />
      </div>

      {/* Errors */}
      {errors.length > 0 && (
        <div style={{ marginTop: 8, background: "rgba(220,50,50,0.1)", border: "1px solid #d32f2f", borderRadius: 4, padding: "6px 8px" }}>
          {errors.map((e, i) => (
            <div key={i} style={{ color: "#ff6b6b", fontSize: 10, marginBottom: 2 }}>{e}</div>
          ))}
        </div>
      )}

      {/* Warnings */}
      {warnings.length > 0 && (
        <div style={{ marginTop: 4, background: "rgba(255,190,50,0.1)", border: "1px solid var(--amber)", borderRadius: 4, padding: "6px 8px" }}>
          {warnings.map((w, i) => (
            <div key={i} style={{ color: "var(--amber)", fontSize: 10, marginBottom: 2 }}>{w}</div>
          ))}
        </div>
      )}

      {/* Controls */}
      <div style={{ marginTop: 8, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <button
          className="btn-ghost"
          style={{ padding: "4px 10px", fontSize: 9 }}
          onClick={handleValidate}
          disabled={!!status}
        >
          {status === "validating" ? "CHECKING..." : "VALIDATE"}
        </button>
        <button
          className="action-btn"
          style={{ padding: "4px 10px", fontSize: 9 }}
          onClick={handleTranspile}
          disabled={!!status}
        >
          {status === "transpiling" ? "TRANSPILING..." : "TRANSPILE & CREATE"}
        </button>

        {/* LLM fallback toggle */}
        <label style={{ fontSize: 9, display: "flex", alignItems: "center", gap: 4, color: "var(--muted)" }}>
          <input
            type="checkbox"
            checked={useLlm}
            onChange={(e) => setUseLlm(e.target.checked)}
            style={{ accentColor: "var(--amber)" }}
          />
          LLM fallback
        </label>
      </div>
    </div>
  );
}
