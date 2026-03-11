/**
 * EmptyState — reusable "nothing here yet" placeholder.
 *
 * Two variants:
 *   1. Block — centred text in a padded div (for panel/page-level empties).
 *   2. Table row — full-width colSpan cell (for empty table bodies).
 *
 * Props:
 *   message  — the text to display.
 *   asRow    — if true, renders as a <tr><td> for table context.
 *   colSpan  — column span when asRow is true (default 99).
 *   style    — optional additional inline styles.
 */

import React from "react";

const BASE = {
  textAlign: "center",
  color: "var(--muted)",
  fontFamily: "var(--font-mono)",
  fontSize: 12,
};

export default function EmptyState({
  message,
  asRow = false,
  colSpan = 99,
  style,
}) {
  if (asRow) {
    return (
      <tr>
        <td
          colSpan={colSpan}
          style={{ ...BASE, padding: "32px 0", ...style }}
        >
          {message}
        </td>
      </tr>
    );
  }

  return (
    <div style={{ ...BASE, padding: "48px 20px", ...style }}>
      {message}
    </div>
  );
}
