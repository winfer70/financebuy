/**
 * FilterBar — reusable category / status filter button strip.
 *
 * Wraps the `.filter-bar` + `.filter-btn` CSS pattern used across
 * DashboardPage, NewsPage, TransactionsPage, and OrdersPage.
 *
 * Props:
 *   items    — array of { id, label } filter options.
 *   value    — currently active filter id.
 *   onChange — callback receiving the selected filter id.
 *   style    — optional override style for each button.
 */

import React from "react";

export default function FilterBar({ items, value, onChange, style }) {
  return (
    <div className="filter-bar">
      {items.map((f) => (
        <button
          key={f.id}
          className={`filter-btn${f.id === value ? " active" : ""}`}
          style={style}
          onClick={() => onChange(f.id)}
        >
          {f.label}
        </button>
      ))}
    </div>
  );
}
