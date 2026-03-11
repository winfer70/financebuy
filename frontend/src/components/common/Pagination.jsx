/**
 * Pagination — reusable page navigation + per-page selector.
 *
 * Extracted from NewsPage.  Renders PREV / NEXT buttons, a page counter,
 * and an optional per-page size picker.
 *
 * Props:
 *   currentPage     — 1-based current page number.
 *   totalPages      — total number of pages.
 *   onPrev          — callback for previous page.
 *   onNext          — callback for next page.
 *   perPage         — current items-per-page value  (optional, enables size selector).
 *   perPageOptions  — array of size options, e.g. [25, 50, 75, 100].
 *   onPerPageChange — callback receiving new per-page value.
 */

import React from "react";

/* Nav button style — disabled variant dims and removes cursor. */
const btnStyle = (disabled) => ({
  fontFamily: "var(--font-mono)",
  fontSize: 10,
  fontWeight: 600,
  letterSpacing: "0.5px",
  padding: "4px 12px",
  background: disabled ? "transparent" : "var(--bg3)",
  border: `1px solid ${disabled ? "var(--bg3)" : "var(--border)"}`,
  color: disabled ? "var(--bg3)" : "var(--muted)",
  cursor: disabled ? "default" : "pointer",
  borderRadius: 2,
});

export default function Pagination({
  currentPage,
  totalPages,
  onPrev,
  onNext,
  perPage,
  perPageOptions,
  onPerPageChange,
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 16,
        padding: "16px 0 8px",
        flexWrap: "wrap",
      }}
    >
      {/* Prev / page counter / Next */}
      <button
        onClick={onPrev}
        disabled={currentPage <= 1}
        style={btnStyle(currentPage <= 1)}
      >
        &lt; PREV
      </button>

      <span
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: 11,
          fontWeight: 600,
          color: "var(--bright)",
          letterSpacing: "0.5px",
        }}
      >
        PAGE {currentPage} OF {totalPages}
      </span>

      <button
        onClick={onNext}
        disabled={currentPage >= totalPages}
        style={btnStyle(currentPage >= totalPages)}
      >
        NEXT &gt;
      </button>

      {/* Per-page size selector (optional) */}
      {perPageOptions && onPerPageChange && (
        <div
          style={{
            display: "flex",
            gap: 4,
            alignItems: "center",
            marginLeft: "auto",
          }}
        >
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 9,
              color: "var(--muted)",
              letterSpacing: "0.5px",
            }}
          >
            PER PAGE
          </span>
          {perPageOptions.map((size) => (
            <button
              key={size}
              onClick={() => onPerPageChange(size)}
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 10,
                fontWeight: 600,
                padding: "3px 8px",
                cursor: "pointer",
                borderRadius: 2,
                letterSpacing: "0.3px",
                background:
                  perPage === size ? "var(--amber)" : "transparent",
                color:
                  perPage === size ? "var(--bg1)" : "var(--muted)",
                border:
                  perPage === size
                    ? "1px solid var(--amber)"
                    : "1px solid var(--border)",
              }}
            >
              {size}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
