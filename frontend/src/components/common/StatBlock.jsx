/**
 * StatBlock — single stat card for the grid-stats row.
 *
 * Replaces the duplicated { lbl, val, cls } → stat-block pattern found in
 * DashboardPage, PortfolioManagerPage, WatchlistPage, TransactionsPage,
 * and OrdersPage.
 *
 * Props:
 *   label    — upper-case label text (e.g. "TOTAL VALUE").
 *   value    — displayed value (string or JSX).
 *   cls      — optional colour class: "amber", "green", "red", "cyan".
 *   badge    — optional badge JSX (e.g. "▲ 1.25% ALL TIME").
 */

import React from "react";

export default function StatBlock({ label, value, cls, badge }) {
  return (
    <div className="stat-block">
      <div className="stat-lbl">{label}</div>
      <div className={`stat-val${cls ? " " + cls : ""}`}>{value}</div>
      {badge && badge}
    </div>
  );
}
