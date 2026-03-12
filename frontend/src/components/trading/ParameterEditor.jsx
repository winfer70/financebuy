/**
 * ParameterEditor — reusable strategy parameter input component.
 *
 * Renders sliders for int/float params, toggles for boolean params,
 * and provides a "Reset to Defaults" button. Extracted from TradingPage
 * for reuse across built-in, PineScript, and composed strategies.
 *
 * Props:
 *   paramSchema  — array of {name, type, default, min, max, step, label}
 *   params       — current param values {name: value}
 *   onChange      — (name, value) callback
 *   onReset      — () callback to reset to defaults
 */

import React from "react";

export default function ParameterEditor({ paramSchema, params, onChange, onReset }) {
  if (!paramSchema || paramSchema.length === 0) {
    return (
      <div style={{ color: "var(--muted)", fontSize: 10, padding: "8px 0" }}>
        No configurable parameters.
      </div>
    );
  }

  return (
    <div>
      {paramSchema.map((p) => {
        const value = params[p.name] ?? p.default;

        // Boolean toggle
        if (p.type === "bool" || p.type === "boolean") {
          return (
            <div key={p.name} style={{ marginTop: 10, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <label className="form-label" style={{ margin: 0 }}>
                {p.label || p.name}
              </label>
              <button
                className={`filter-btn${value ? " active" : ""}`}
                style={{ padding: "2px 10px", fontSize: 9 }}
                onClick={() => onChange(p.name, !value)}
              >
                {value ? "ON" : "OFF"}
              </button>
            </div>
          );
        }

        // Numeric slider (int or float)
        return (
          <div key={p.name} style={{ marginTop: 10 }}>
            <label
              className="form-label"
              style={{ display: "flex", justifyContent: "space-between" }}
            >
              <span>{p.label || p.name}</span>
              <span style={{ color: "var(--amber)" }}>{value}</span>
            </label>
            <input
              type="range"
              min={p.min}
              max={p.max}
              step={p.step}
              value={value}
              onChange={(e) =>
                onChange(
                  p.name,
                  p.type === "float"
                    ? parseFloat(e.target.value)
                    : parseInt(e.target.value, 10),
                )
              }
              style={{ width: "100%", accentColor: "var(--amber)" }}
            />
          </div>
        );
      })}

      {/* Reset button */}
      {onReset && (
        <button
          className="btn-ghost"
          style={{ marginTop: 10, fontSize: 9, padding: "4px 8px", width: "100%" }}
          onClick={onReset}
        >
          RESET TO DEFAULTS
        </button>
      )}
    </div>
  );
}
