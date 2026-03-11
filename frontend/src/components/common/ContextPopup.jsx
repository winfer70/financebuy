/**
 * ContextPopup — reusable positioned context-menu dropdown.
 *
 * Renders a fixed-position popup at (x, y) with a title header and a list
 * of action items.  Replaces the duplicated heatmapPopup (DashboardPage)
 * and tickerPopup (NewsPage) markup.
 *
 * Props:
 *   x, y       — screen coordinates (from useContextPopup).
 *   title      — header text (e.g. ticker symbol).
 *   actions    — array of { label, onClick } items to render as buttons.
 */

import React from "react";

/* -- Inline styles (Bloomberg terminal aesthetic) ------------------------- */

const WRAP = {
  position: "fixed",
  zIndex: 1000,
  background: "var(--bg2)",
  border: "1px solid var(--border)",
  borderRadius: 3,
  padding: "6px 0",
  boxShadow: "0 4px 16px rgba(0,0,0,0.5)",
  fontFamily: "var(--font-mono)",
  fontSize: 10,
  minWidth: 140,
};

const HEADER = {
  padding: "4px 12px",
  color: "var(--amber)",
  fontWeight: 600,
  letterSpacing: "0.5px",
  borderBottom: "1px solid var(--border)",
  marginBottom: 2,
};

const BTN = {
  display: "block",
  width: "100%",
  textAlign: "left",
  background: "none",
  border: "none",
  cursor: "pointer",
  color: "var(--bright)",
  padding: "5px 12px",
  fontFamily: "var(--font-mono)",
  fontSize: 10,
  letterSpacing: "0.3px",
};

export default function ContextPopup({ x, y, title, actions }) {
  if (!actions || actions.length === 0) return null;
  return (
    <div
      onClick={(e) => e.stopPropagation()}
      style={{ ...WRAP, left: x, top: y }}
    >
      {title && <div style={HEADER}>{title}</div>}
      {actions.map((a, i) => (
        <button
          key={i}
          onClick={a.onClick}
          style={BTN}
          onMouseOver={(e) => (e.currentTarget.style.background = "var(--bg3)")}
          onMouseOut={(e) => (e.currentTarget.style.background = "none")}
        >
          {a.label}
        </button>
      ))}
    </div>
  );
}
