/**
 * Shared Formatters — centralised number, currency, percentage, date, and
 * volume formatting used across all TickerTap pages.
 *
 * Every page-level formatter that was previously duplicated inline (fmtUSD,
 * fmtPct, fmtQty, fmtDate, fmtVol, timeAgo) is defined here once and
 * exported for consistent usage.
 */

/* -- Currency & numbers --------------------------------------------------- */

/**
 * Format a number as USD currency string.
 * @param {number|null} n — value to format.
 * @returns {string} e.g. "$1,234.56" or em-dash for null.
 */
export const fmtUSD = (n) =>
  n == null
    ? "\u2014"
    : `$${parseFloat(n).toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })}`;

/**
 * Format a quantity with up to 6 decimal places.
 * @param {number|null} n — value to format.
 * @returns {string} e.g. "12.5" or em-dash for null.
 */
export const fmtQty = (n) =>
  n == null
    ? "\u2014"
    : parseFloat(n).toLocaleString("en-US", { maximumFractionDigits: 6 });

/**
 * Format a number as a signed percentage string.
 * @param {number|null} n — value to format.
 * @returns {string} e.g. "+1.25%" or em-dash for null.
 */
export const fmtPct = (n) =>
  n == null
    ? "\u2014"
    : `${parseFloat(n) >= 0 ? "+" : ""}${parseFloat(n).toFixed(2)}%`;

/* -- Dates ---------------------------------------------------------------- */

/**
 * Format a date string as "MMM D, YYYY".
 * @param {string|null} s — ISO date string.
 * @returns {string} e.g. "Feb 23, 2026" or em-dash for invalid/null.
 */
export const fmtDate = (s) => {
  if (!s) return "\u2014";
  try {
    return new Date(s).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return "\u2014";
  }
};

/**
 * Relative timestamp — "just now", "5m ago", "3h ago", or "MMM D".
 * @param {string|null} dt — ISO datetime string.
 * @returns {string} human-readable relative time.
 */
export function timeAgo(dt) {
  if (!dt) return "";
  try {
    const diff = (Date.now() - new Date(dt).getTime()) / 1000;
    if (diff < 60) return "just now";
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return new Date(dt).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    });
  } catch {
    return "";
  }
}

/* -- Volume / compact numbers --------------------------------------------- */

/**
 * Format a volume number into a compact string (e.g. "1.23B", "456M", "12K").
 * @param {number} v — volume value.
 * @returns {string} compact representation.
 */
export const fmtVol = (v) =>
  v >= 1e9
    ? (v / 1e9).toFixed(2) + "B"
    : v >= 1e6
      ? (v / 1e6).toFixed(2) + "M"
      : v >= 1e3
        ? (v / 1e3).toFixed(0) + "K"
        : String(v);
