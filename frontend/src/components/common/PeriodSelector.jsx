/**
 * PeriodSelector — reusable time-period button strip.
 *
 * Renders a row of filter-btn styled buttons for selecting a time period
 * (1W, 1M, 3M, YTD, 1Y, ALL, etc.).  Used by DashboardPage (chart period)
 * and available for any panel that needs a period picker.
 *
 * Props:
 *   periods  — array of period strings, e.g. ["1W", "1M", "3M", "1Y"].
 *   value    — currently selected period string.
 *   onChange — callback receiving the selected period string.
 *   style    — optional override style for each button.
 */

import React from "react";

export default function PeriodSelector({ periods, value, onChange, style }) {
  return (
    <div style={{ display: "flex", gap: 1 }}>
      {periods.map((p) => (
        <button
          key={p}
          className={`filter-btn${p === value ? " active" : ""}`}
          style={{ padding: "4px 10px", fontSize: 9, ...style }}
          onClick={() => onChange(p)}
        >
          {p}
        </button>
      ))}
    </div>
  );
}
