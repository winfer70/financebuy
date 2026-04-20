/**
 * CompositionEditor — visual strategy composer using indicator nodes
 * and boolean logic expressions.
 *
 * Users drag indicator "nodes" from a palette, configure each node's
 * parameters, then write entry/exit expression strings referencing the
 * indicator output variables. The editor produces a composition_json
 * object that the backend /compose endpoint accepts.
 *
 * Zero external dependencies — uses div positioning for nodes and
 * inline SVG for connection lines.
 *
 * Props:
 *   token        — JWT auth token
 *   onCreated    — (strategyId) callback after successful creation
 */

import React, { useState, useCallback } from "react";
import api from "../../api/client";

/* ── Available indicator palette ──────────────────────────────────────── */

const INDICATOR_PALETTE = [
  { fn: "sma", label: "SMA", args: { source: "close", period: 14 }, outputs: ["sma"] },
  { fn: "ema", label: "EMA", args: { source: "close", period: 14 }, outputs: ["ema"] },
  { fn: "rsi", label: "RSI", args: { source: "close", period: 14 }, outputs: ["rsi"] },
  { fn: "macd", label: "MACD", args: { source: "close", fast: 12, slow: 26, signal: 9 }, outputs: ["macd_line", "signal_line", "histogram"] },
  { fn: "bollinger_bands", label: "BB", args: { source: "close", period: 20, num_std: 2.0 }, outputs: ["middle", "upper", "lower", "bandwidth"] },
  { fn: "atr", label: "ATR", args: { period: 14 }, outputs: ["atr"] },
  { fn: "adx", label: "ADX", args: { period: 14 }, outputs: ["adx", "plus_di", "minus_di"] },
  { fn: "stochastic", label: "Stoch", args: { k_period: 14, d_period: 3 }, outputs: ["pct_k", "pct_d"] },
  { fn: "vwap", label: "VWAP", args: {}, outputs: ["vwap"] },
  { fn: "highest", label: "Highest", args: { source: "high", period: 20 }, outputs: ["highest"] },
  { fn: "lowest", label: "Lowest", args: { source: "low", period: 20 }, outputs: ["lowest"] },
];

/* ── Component ──────────────────────────────────────────────────────── */

export default function CompositionEditor({ token, onCreated }) {
  // Strategy metadata
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  // Indicator nodes added by the user
  const [nodes, setNodes] = useState([]);

  // Expression strings
  const [entryExpr, setEntryExpr] = useState("");
  const [exitExpr, setExitExpr] = useState("");

  // Stop loss
  const [stopLossEnabled, setStopLossEnabled] = useState(false);
  const [stopLossPct, setStopLossPct] = useState(0.05);

  // UI state
  const [errors, setErrors] = useState([]);
  const [creating, setCreating] = useState(false);
  const [nodeCounter, setNodeCounter] = useState(0);

  /** Add an indicator node from the palette. */
  const addNode = useCallback((template) => {
    const id = nodeCounter;
    setNodeCounter((c) => c + 1);
    const outputVar = `${template.fn}_${id}`;
    setNodes((prev) => [
      ...prev,
      {
        id,
        fn: template.fn,
        label: template.label,
        args: { ...template.args },
        output_var: outputVar,
        outputs: template.outputs.map((o, i) =>
          i === 0 ? outputVar : `${outputVar}__${i}`
        ),
      },
    ]);
  }, [nodeCounter]);

  /** Remove a node. */
  const removeNode = useCallback((nodeId) => {
    setNodes((prev) => prev.filter((n) => n.id !== nodeId));
  }, []);

  /** Update a node arg value. */
  const updateNodeArg = useCallback((nodeId, argName, value) => {
    setNodes((prev) =>
      prev.map((n) =>
        n.id === nodeId
          ? { ...n, args: { ...n.args, [argName]: value } }
          : n
      )
    );
  }, []);

  /** Build composition JSON and create strategy. */
  const handleCreate = async () => {
    if (!name.trim()) {
      setErrors(["Strategy name is required."]);
      return;
    }
    if (!entryExpr.trim()) {
      setErrors(["Entry expression is required."]);
      return;
    }
    if (nodes.length === 0) {
      setErrors(["Add at least one indicator."]);
      return;
    }

    setCreating(true);
    setErrors([]);

    const compositionJson = {
      indicators: nodes.map((n) => ({
        fn: n.fn,
        args: n.args,
        output_var: n.output_var,
      })),
      entry_expr: entryExpr.trim(),
      exit_expr: exitExpr.trim(),
      stop_loss: stopLossEnabled ? { type: "pct", value: stopLossPct } : null,
      params: {},
      param_schema: [],
    };

    try {
      const result = await api.createComposedStrategy(
        { name: name.trim(), description: description.trim() || null, composition_json: compositionJson },
        token,
      );
      if (onCreated) onCreated(result.strategy_id);
    } catch (err) {
      setErrors([err.message]);
    } finally {
      setCreating(false);
    }
  };

  // All available output variable names for reference
  const allOutputs = nodes.flatMap((n) => n.outputs);

  return (
    <div className="panel" style={{ padding: 12 }}>
      <div className="panel-title" style={{ marginBottom: 8 }}>STRATEGY COMPOSER</div>

      {/* Name + Description */}
      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <div className="form-field" style={{ flex: 1 }}>
          <label className="form-label">NAME</label>
          <input className="form-control" type="text" value={name} onChange={(e) => setName(e.target.value)} style={{ fontSize: 11 }} placeholder="My Composed Strategy" />
        </div>
        <div className="form-field" style={{ flex: 1 }}>
          <label className="form-label">DESCRIPTION</label>
          <input className="form-control" type="text" value={description} onChange={(e) => setDescription(e.target.value)} style={{ fontSize: 11 }} placeholder="Optional..." />
        </div>
      </div>

      {/* Indicator Palette */}
      <div style={{ marginBottom: 8 }}>
        <div style={{ fontSize: 9, color: "var(--muted)", marginBottom: 4 }}>ADD INDICATOR</div>
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
          {INDICATOR_PALETTE.map((tmpl) => (
            <button
              key={tmpl.fn}
              className="filter-btn"
              style={{ padding: "3px 8px", fontSize: 9 }}
              onClick={() => addNode(tmpl)}
            >
              + {tmpl.label}
            </button>
          ))}
        </div>
      </div>

      {/* Active Nodes */}
      {nodes.length > 0 && (
        <div style={{ marginBottom: 8, display: "flex", flexDirection: "column", gap: 6 }}>
          <div style={{ fontSize: 9, color: "var(--muted)" }}>INDICATORS ({nodes.length})</div>
          {nodes.map((node) => (
            <div
              key={node.id}
              style={{
                background: "var(--panel-bg)", border: "1px solid var(--border)",
                borderRadius: 4, padding: "6px 8px",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                <span style={{ fontSize: 10, fontWeight: 600, color: "var(--amber)" }}>
                  {node.label} — <code style={{ fontSize: 9, color: "var(--text)" }}>{node.output_var}</code>
                </span>
                <button
                  style={{ background: "none", border: "none", color: "#ff6b6b", cursor: "pointer", fontSize: 10, padding: "0 2px" }}
                  onClick={() => removeNode(node.id)}
                >
                  X
                </button>
              </div>
              {/* Node args */}
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {Object.entries(node.args).map(([argName, argVal]) => (
                  <div key={argName} style={{ fontSize: 9 }}>
                    <label style={{ color: "var(--muted)", marginRight: 3 }}>{argName}:</label>
                    <input
                      className="form-control"
                      type={typeof argVal === "number" ? "number" : "text"}
                      value={argVal}
                      onChange={(e) => {
                        const v = typeof argVal === "number"
                          ? (String(argVal).includes(".") ? parseFloat(e.target.value) : parseInt(e.target.value, 10))
                          : e.target.value;
                        updateNodeArg(node.id, argName, v || 0);
                      }}
                      style={{ width: 60, fontSize: 9, padding: "2px 4px", display: "inline" }}
                    />
                  </div>
                ))}
              </div>
              {/* Output variable names */}
              <div style={{ fontSize: 8, color: "var(--muted)", marginTop: 2 }}>
                Outputs: {node.outputs.join(", ")}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Available variables reference */}
      {allOutputs.length > 0 && (
        <div style={{ fontSize: 9, color: "var(--muted)", marginBottom: 6, padding: "4px 8px", background: "var(--panel-bg)", borderRadius: 4, border: "1px solid var(--border)" }}>
          Available: <code style={{ color: "var(--amber)" }}>{allOutputs.join(", ")}</code>
          {" "}+ <code style={{ color: "var(--amber)" }}>close, open, high, low, volume</code>
        </div>
      )}

      {/* Entry Expression */}
      <div className="form-field" style={{ marginBottom: 8 }}>
        <label className="form-label">ENTRY CONDITION (Python expression)</label>
        <input
          className="form-control"
          type="text"
          value={entryExpr}
          onChange={(e) => setEntryExpr(e.target.value)}
          placeholder='e.g. sma_0 > sma_1 and rsi_2 < 30'
          style={{ fontSize: 11, fontFamily: "monospace" }}
        />
      </div>

      {/* Exit Expression */}
      <div className="form-field" style={{ marginBottom: 8 }}>
        <label className="form-label">EXIT CONDITION (Python expression)</label>
        <input
          className="form-control"
          type="text"
          value={exitExpr}
          onChange={(e) => setExitExpr(e.target.value)}
          placeholder='e.g. sma_0 < sma_1 or rsi_2 > 70'
          style={{ fontSize: 11, fontFamily: "monospace" }}
        />
      </div>

      {/* Stop Loss */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <label style={{ fontSize: 9, display: "flex", alignItems: "center", gap: 4, color: "var(--muted)" }}>
          <input
            type="checkbox"
            checked={stopLossEnabled}
            onChange={(e) => setStopLossEnabled(e.target.checked)}
            style={{ accentColor: "var(--amber)" }}
          />
          Stop Loss
        </label>
        {stopLossEnabled && (
          <input
            className="form-control"
            type="number"
            step="0.005"
            min="0.005"
            max="0.5"
            value={stopLossPct}
            onChange={(e) => setStopLossPct(parseFloat(e.target.value) || 0.05)}
            style={{ width: 70, fontSize: 10 }}
          />
        )}
        {stopLossEnabled && (
          <span style={{ fontSize: 9, color: "var(--muted)" }}>({(stopLossPct * 100).toFixed(1)}%)</span>
        )}
      </div>

      {/* Errors */}
      {errors.length > 0 && (
        <div style={{ marginBottom: 8, background: "rgba(220,50,50,0.1)", border: "1px solid #d32f2f", borderRadius: 4, padding: "6px 8px" }}>
          {errors.map((e, i) => (
            <div key={i} style={{ color: "#ff6b6b", fontSize: 10 }}>{e}</div>
          ))}
        </div>
      )}

      {/* Create button */}
      <button
        className="action-btn"
        style={{ padding: "6px 14px", fontSize: 10, width: "100%" }}
        onClick={handleCreate}
        disabled={creating}
      >
        {creating ? "CREATING..." : "CREATE COMPOSED STRATEGY"}
      </button>
    </div>
  );
}
