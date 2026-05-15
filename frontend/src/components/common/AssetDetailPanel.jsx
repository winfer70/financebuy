/**
 * AssetDetailPanel.jsx
 *
 * Modal component showing comprehensive fundamental data for a symbol.
 * Used from PortfolioManagerPage, WatchlistPage, and ChartsPage.
 * Fetches data from GET /market/fundamentals/{symbol} via api.getFundamentals.
 *
 * Sections rendered:
 *   1. Company Info   2. Valuation   3. Financial Health   4. Dividends
 *   5. Analyst Targets (with visual bar)   6. Earnings   7. Trading Info
 */

import { useState, useEffect } from "react";
import api from "../../api/client";
import { MODAL_BACKDROP as BDK } from "../../styles/shared";

/* ── Formatting helpers ──────────────────────────────────────────────────── */

/**
 * fmtBig — format large numbers with human-readable suffixes.
 * @param {number|null} n - Raw number
 * @returns {string} Formatted string (e.g. "1.23t", "456.78b", "12.34m", "5.67k")
 */
function fmtBig(n) {
  if (n == null || isNaN(n)) return "\u2014";
  const abs = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  if (abs >= 1e12) return sign + (abs / 1e12).toFixed(2) + "t";
  if (abs >= 1e9)  return sign + (abs / 1e9).toFixed(2) + "b";
  if (abs >= 1e6)  return sign + (abs / 1e6).toFixed(2) + "m";
  if (abs >= 1e3)  return sign + (abs / 1e3).toFixed(2) + "k";
  return sign + abs.toFixed(2);
}

/**
 * fmtPctVal — format a value as a percentage.
 * yfinance returns margins as decimals (0.25 = 25%), so multiply by 100 if < 1.
 * @param {number|null} n - Raw value
 * @returns {string} Formatted percentage string
 */
function fmtPctVal(n) {
  if (n == null || isNaN(n)) return "\u2014";
  // Values already > 1 or < -1 are likely already in percent form
  const pct = (Math.abs(n) < 1 && Math.abs(n) > 0) ? n * 100 : n;
  return pct.toFixed(2) + "%";
}

/**
 * fmtNum — format a plain number with 2 decimal places.
 * @param {number|null} n - Raw number
 * @returns {string} Formatted number or em-dash for null/NaN
 */
function fmtNum(n) {
  if (n == null || isNaN(n)) return "\u2014";
  return Number(n).toFixed(2);
}

/**
 * fmtDate — format an ISO date string to a short readable form.
 * @param {string|null} d - ISO date string
 * @returns {string} Formatted date or em-dash
 */
function fmtDateShort(d) {
  if (!d) return "\u2014";
  try {
    return new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  } catch {
    return d;
  }
}

/* ── Style constants ─────────────────────────────────────────────────────── */

/** Modal box — dark surface with subtle border, scrollable body. */
const MODAL_BOX = {
  background: "#1a1a2e",
  border: "1px solid rgba(255,255,255,0.06)",
  borderRadius: 10,
  width: "95vw",
  maxWidth: 700,
  maxHeight: "90vh",
  display: "flex",
  flexDirection: "column",
  overflow: "hidden",
};

/** Sidebar panel — fixed right-edge drawer, full viewport height, scrollable. */
const SIDEBAR_STYLES = {
  position: 'fixed',
  right: 0,
  top: 0,
  width: '380px',
  height: '100vh',
  overflowY: 'auto',
  zIndex: 200,
  background: 'var(--bg-secondary, #1a1a2e)',
  borderLeft: '1px solid var(--border, #333)',
  boxShadow: '-4px 0 20px rgba(0,0,0,0.3)',
  padding: '16px'
};

/** Section card — subtle background block for each data section. */
const SECTION_CARD = {
  background: "rgba(255,255,255,0.03)",
  borderRadius: 6,
  padding: "12px 16px",
  marginBottom: 12,
};

/** Section header text style — amber with uppercase. */
const SECTION_HEADER = {
  fontSize: 12,
  fontWeight: 700,
  color: "#f59e0b",
  letterSpacing: "1.2px",
  textTransform: "uppercase",
  marginBottom: 10,
  fontFamily: "'IBM Plex Mono', monospace",
};

/** Metric label style — muted, uppercase, tiny. */
const LABEL_STYLE = {
  fontSize: 11,
  color: "#6b7280",
  textTransform: "uppercase",
  fontFamily: "'IBM Plex Mono', monospace",
  letterSpacing: "0.5px",
  marginBottom: 2,
};

/** Metric value style — prominent, semibold. */
const VALUE_STYLE = {
  fontSize: 14,
  fontWeight: 600,
  color: "#e2e8f0",
  fontFamily: "'IBM Plex Mono', monospace",
};

/* ── Sub-components ──────────────────────────────────────────────────────── */

/**
 * MetricGrid — renders a 2-column (or 3-column) grid of label/value pairs.
 * @param {Array}  items   - Array of { label, value, color? } objects
 * @param {number} [cols=2] - Number of grid columns
 */
function MetricGrid({ items, cols = 2 }) {
  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: `repeat(${cols}, 1fr)`,
      gap: "10px 20px",
    }}>
      {items.map((item, i) => (
        <div key={i}>
          <div style={LABEL_STYLE}>{item.label}</div>
          <div style={{ ...VALUE_STYLE, color: item.color || VALUE_STYLE.color }}>
            {item.value ?? "\u2014"}
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * colorForValue — return green for positive, red for negative, default otherwise.
 * @param {number|null} n - Numeric value
 * @returns {string|undefined} CSS color string
 */
function colorForValue(n) {
  if (n == null || isNaN(n)) return undefined;
  if (n > 0) return "#00d97e";
  if (n < 0) return "#f04438";
  return undefined;
}

/* ── Main Component ──────────────────────────────────────────────────────── */

/**
 * AssetDetailPanel — modal showing comprehensive fundamental data for a symbol.
 *
 * @param {object}   props
 * @param {string}   props.symbol  - Ticker symbol to display (e.g. "AAPL")
 * @param {string}   props.token   - JWT access token for API calls
 * @param {Function} props.onClose - Callback to close the modal
 */
export default function AssetDetailPanel({ symbol, token, onClose, mode = "modal" }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [descExpanded, setDescExpanded] = useState(false);

  /* Fetch fundamental data on mount and when symbol changes */
  useEffect(() => {
    if (!symbol || !token) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);
    setDescExpanded(false);

    // api.getFundamentals — GET /market/fundamentals/{symbol}, returns fundamental data object
    api.getFundamentals(symbol, token)
      .then(result => { if (!cancelled) setData(result); })
      .catch(err => { if (!cancelled) setError(err.message || "Failed to load fundamentals."); })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [symbol, token]);

  /* Close on Escape key */
  useEffect(() => {
    const handleKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  /* ── Render helpers ──────────────────────────────────────────────────── */

  /** renderCompanyInfo — Section 1: Company name, sector, industry, etc. */
  function renderCompanyInfo() {
    const desc = data.description || "";
    const truncLen = 300;
    const needsTruncate = desc.length > truncLen;
    const displayDesc = descExpanded ? desc : desc.slice(0, truncLen);

    return (
      <div style={SECTION_CARD}>
        <div style={SECTION_HEADER}>COMPANY INFO</div>

        {/* Name + basic fields as a 2-col grid */}
        <MetricGrid items={[
          { label: "Name", value: data.name || symbol },
          { label: "Sector", value: data.sector },
          { label: "Industry", value: data.industry },
          { label: "Country", value: data.country },
          { label: "Employees", value: data.employees != null ? Number(data.employees).toLocaleString() : null },
          { label: "Exchange", value: data.exchange },
        ]} />

        {/* Website link */}
        {data.website && (
          <div style={{ marginTop: 10 }}>
            <div style={LABEL_STYLE}>Website</div>
            <a
              href={data.website}
              target="_blank"
              rel="noopener noreferrer"
              style={{ ...VALUE_STYLE, color: "#3b82f6", textDecoration: "underline", fontSize: 12 }}
            >
              {data.website}
            </a>
          </div>
        )}

        {/* Description — truncated with expand toggle */}
        {desc && (
          <div style={{ marginTop: 10 }}>
            <div style={LABEL_STYLE}>Description</div>
            <div style={{ fontSize: 12, color: "#94a3b8", lineHeight: 1.6, fontFamily: "'IBM Plex Sans', sans-serif" }}>
              {displayDesc}
              {needsTruncate && !descExpanded && "..."}
              {needsTruncate && (
                <button
                  onClick={() => setDescExpanded(!descExpanded)}
                  style={{
                    background: "none", border: "none", color: "#f59e0b",
                    cursor: "pointer", fontSize: 11, fontWeight: 600,
                    marginLeft: 6, padding: 0, fontFamily: "'IBM Plex Mono', monospace",
                  }}
                >
                  {descExpanded ? "SHOW LESS" : "READ MORE"}
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    );
  }

  /** renderValuation — Section 2: Market cap, P/E ratios, PEG, P/B, P/S, EV/EBITDA. */
  function renderValuation() {
    return (
      <div style={SECTION_CARD}>
        <div style={SECTION_HEADER}>VALUATION</div>
        <MetricGrid items={[
          { label: "Market Cap", value: fmtBig(data.market_cap) },
          { label: "P/E (TTM)", value: fmtNum(data.pe_ratio) },
          { label: "Forward P/E", value: fmtNum(data.forward_pe) },
          { label: "PEG Ratio", value: fmtNum(data.peg_ratio) },
          { label: "P/B", value: fmtNum(data.pb_ratio) },
          { label: "P/S", value: fmtNum(data.ps_ratio) },
          { label: "EV/EBITDA", value: fmtNum(data.ev_to_ebitda) },
        ]} />
      </div>
    );
  }

  /** renderFinancialHealth — Section 3: Revenue, income, margins, ROE, ROA, debt ratios. */
  function renderFinancialHealth() {
    return (
      <div style={SECTION_CARD}>
        <div style={SECTION_HEADER}>FINANCIAL HEALTH</div>
        <MetricGrid cols={3} items={[
          { label: "Revenue", value: fmtBig(data.revenue) },
          { label: "Net Income", value: fmtBig(data.net_income), color: colorForValue(data.net_income) },
          { label: "Profit Margin", value: fmtPctVal(data.profit_margin), color: colorForValue(data.profit_margin) },
          { label: "Operating Margin", value: fmtPctVal(data.operating_margin), color: colorForValue(data.operating_margin) },
          { label: "ROE", value: fmtPctVal(data.roe), color: colorForValue(data.roe) },
          { label: "ROA", value: fmtPctVal(data.roa), color: colorForValue(data.roa) },
          { label: "Debt/Equity", value: fmtNum(data.debt_to_equity) },
          { label: "Current Ratio", value: fmtNum(data.current_ratio) },
          { label: "Free Cash Flow", value: fmtBig(data.free_cash_flow), color: colorForValue(data.free_cash_flow) },
        ]} />
      </div>
    );
  }

  /** renderDividends — Section 4: Yield, rate, payout ratio, ex-date. Only shown if dividends exist. */
  function renderDividends() {
    if (!data.dividend_yield) return null;
    return (
      <div style={SECTION_CARD}>
        <div style={SECTION_HEADER}>DIVIDENDS</div>
        <MetricGrid items={[
          { label: "Dividend Yield", value: fmtPctVal(data.dividend_yield) },
          { label: "Dividend Rate", value: data.dividend_rate != null ? "$" + fmtNum(data.dividend_rate) : null },
          { label: "Payout Ratio", value: fmtPctVal(data.payout_ratio) },
          { label: "Ex-Dividend Date", value: fmtDateShort(data.ex_dividend_date) },
        ]} />
      </div>
    );
  }

  /**
   * renderAnalystTargets — Section 5: Low/mean/median/high targets, recommendation badge,
   * number of analysts, and a visual bar showing current price position.
   */
  function renderAnalystTargets() {
    const low = data.target_low;
    const high = data.target_high;
    const mean = data.target_mean;
    const median = data.target_median;
    const price = data.current_price;
    const rec = data.recommendation;
    const numAnalysts = data.num_analysts;

    // Only render if we have at least some analyst data
    if (low == null && high == null && mean == null) return null;

    /* Visual bar: position of current price between analyst low and high targets.
     * Clamped to 0-100% to handle edge cases where price is outside the range. */
    let barPct = null;
    if (low != null && high != null && price != null && high > low) {
      barPct = Math.max(0, Math.min(100, ((price - low) / (high - low)) * 100));
    }

    /* Recommendation badge color mapping */
    const recColors = {
      buy: "#00d97e", strong_buy: "#00d97e", strongbuy: "#00d97e",
      hold: "#f59e0b",
      sell: "#f04438", strong_sell: "#f04438", strongsell: "#f04438",
      underperform: "#f04438", overweight: "#00d97e", underweight: "#f04438",
    };
    const recColor = rec ? (recColors[rec.toLowerCase().replace(/[\s_-]+/g, "")] || "#6b7280") : "#6b7280";

    return (
      <div style={SECTION_CARD}>
        <div style={SECTION_HEADER}>ANALYST TARGETS</div>

        {/* Recommendation badge + analyst count */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
          {rec && (
            <span style={{
              fontSize: 11, fontWeight: 700, fontFamily: "'IBM Plex Mono', monospace",
              color: recColor, background: recColor + "18",
              border: `1px solid ${recColor}40`,
              padding: "3px 10px", borderRadius: 3, textTransform: "uppercase",
              letterSpacing: "0.8px",
            }}>
              {rec}
            </span>
          )}
          {numAnalysts != null && (
            <span style={{ fontSize: 11, color: "#6b7280", fontFamily: "'IBM Plex Mono', monospace" }}>
              {numAnalysts} analyst{numAnalysts !== 1 ? "s" : ""}
            </span>
          )}
        </div>

        <MetricGrid items={[
          { label: "Target Low", value: low != null ? "$" + fmtNum(low) : null },
          { label: "Target Mean", value: mean != null ? "$" + fmtNum(mean) : null },
          { label: "Target Median", value: median != null ? "$" + fmtNum(median) : null },
          { label: "Target High", value: high != null ? "$" + fmtNum(high) : null },
        ]} />

        {/* Visual bar showing current price position between low and high */}
        {barPct != null && (
          <div style={{ marginTop: 14 }}>
            <div style={{ ...LABEL_STYLE, marginBottom: 6 }}>Price vs Target Range</div>
            <div style={{ position: "relative", height: 8, background: "rgba(255,255,255,0.06)", borderRadius: 4, overflow: "hidden" }}>
              {/* Gradient bar from red (low) to green (high) */}
              <div style={{
                position: "absolute", inset: 0,
                background: "linear-gradient(to right, #f04438, #f59e0b, #00d97e)",
                borderRadius: 4, opacity: 0.3,
              }} />
              {/* Current price marker */}
              <div style={{
                position: "absolute", top: -2, width: 4, height: 12,
                background: "#e2e8f0", borderRadius: 2,
                left: `calc(${barPct}% - 2px)`,
                boxShadow: "0 0 6px rgba(226,232,240,0.5)",
              }} />
            </div>
            {/* Low / Price / High labels beneath the bar */}
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
              <span style={{ fontSize: 10, color: "#f04438", fontFamily: "'IBM Plex Mono', monospace" }}>${fmtNum(low)}</span>
              <span style={{ fontSize: 10, color: "#e2e8f0", fontWeight: 600, fontFamily: "'IBM Plex Mono', monospace" }}>
                ${fmtNum(price)} (current)
              </span>
              <span style={{ fontSize: 10, color: "#00d97e", fontFamily: "'IBM Plex Mono', monospace" }}>${fmtNum(high)}</span>
            </div>
          </div>
        )}
      </div>
    );
  }

  /** renderEarnings — Section 6: EPS trailing/forward, next earnings date. */
  function renderEarnings() {
    return (
      <div style={SECTION_CARD}>
        <div style={SECTION_HEADER}>EARNINGS</div>
        <MetricGrid items={[
          { label: "EPS (TTM)", value: data.eps_trailing != null ? "$" + fmtNum(data.eps_trailing) : null, color: colorForValue(data.eps_trailing) },
          { label: "EPS Forward", value: data.eps_forward != null ? "$" + fmtNum(data.eps_forward) : null, color: colorForValue(data.eps_forward) },
          { label: "Next Earnings", value: fmtDateShort(data.earnings_date) },
        ]} />
      </div>
    );
  }

  /** renderTradingInfo — Section 7: Beta, 52wk range, moving averages, volume, short interest. */
  function renderTradingInfo() {
    return (
      <div style={SECTION_CARD}>
        <div style={SECTION_HEADER}>TRADING INFO</div>
        <MetricGrid cols={3} items={[
          { label: "Beta", value: fmtNum(data.beta) },
          { label: "52wk High", value: data.fifty_two_week_high != null ? "$" + fmtNum(data.fifty_two_week_high) : null },
          { label: "52wk Low", value: data.fifty_two_week_low != null ? "$" + fmtNum(data.fifty_two_week_low) : null },
          { label: "50-Day Avg", value: data.fifty_day_avg != null ? "$" + fmtNum(data.fifty_day_avg) : null },
          { label: "200-Day Avg", value: data.two_hundred_day_avg != null ? "$" + fmtNum(data.two_hundred_day_avg) : null },
          { label: "Avg Volume", value: fmtBig(data.avg_volume) },
          { label: "Shares Out", value: fmtBig(data.shares_outstanding) },
          { label: "Float", value: fmtBig(data.float_shares) },
          { label: "Short Ratio", value: fmtNum(data.short_ratio) },
          { label: "Short %", value: fmtPctVal(data.short_pct) },
        ]} />
      </div>
    );
  }

  /* ── Main render ─────────────────────────────────────────────────────── */

  /**
   * content — shared panel content (header + scrollable body) used by both
   * modal and sidebar render paths to avoid duplication.
   */
  const content = (
    <>
      {/* ── Header ── */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "16px 20px", borderBottom: "1px solid rgba(255,255,255,0.06)",
        flexShrink: 0,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{
            fontFamily: "'Bebas Neue', sans-serif", fontSize: 26,
            color: "#0f7d40", letterSpacing: 2, lineHeight: 1,
          }}>
            {symbol}
          </span>
          {data?.name && (
            <span style={{
              fontFamily: "'IBM Plex Mono', monospace", fontSize: 11,
              color: "#6b7280", maxWidth: 260, overflow: "hidden",
              textOverflow: "ellipsis", whiteSpace: "nowrap",
            }}>
              {data.name}
            </span>
          )}
        </div>
        <button
          onClick={onClose}
          style={{
            background: "none", border: "none", color: "#6b7280",
            cursor: "pointer", fontSize: 18, padding: "4px 8px",
            lineHeight: 1,
          }}
          title="Close"
        >
          &times;
        </button>
      </div>

      {/* ── Body (scrollable) ── */}
      <div style={{ flex: 1, overflowY: "auto", padding: "16px 20px" }}>

        {/* Loading state */}
        {loading && (
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "center",
            padding: "60px 0", color: "#6b7280",
            fontFamily: "'IBM Plex Mono', monospace", fontSize: 12,
          }}>
            <span className="loading-pulse">Loading fundamentals for {symbol}...</span>
          </div>
        )}

        {/* Error state */}
        {error && !loading && (
          <div style={{
            padding: "40px 20px", textAlign: "center",
            color: "#f04438", fontFamily: "'IBM Plex Mono', monospace", fontSize: 12,
          }}>
            {error}
          </div>
        )}

        {/* Data sections */}
        {data && !loading && (
          <>
            {renderCompanyInfo()}
            {renderValuation()}
            {renderFinancialHealth()}
            {renderDividends()}
            {renderAnalystTargets()}
            {renderEarnings()}
            {renderTradingInfo()}
          </>
        )}
      </div>
    </>
  );

  /* ── Sidebar render — fixed right-edge drawer, no backdrop overlay ── */
  if (mode === 'sidebar') {
    return (
      <div style={SIDEBAR_STYLES}>
        {/* Close button pinned to top-right corner of the sidebar */}
        <button
          onClick={onClose}
          style={{
            position: 'absolute', top: 12, right: 12,
            background: 'none', border: 'none',
            color: 'var(--text-primary, #fff)',
            fontSize: 20, cursor: 'pointer',
          }}
          title="Close"
        >
          &#x2715;
        </button>
        {content}
      </div>
    );
  }

  /* ── Modal render (default) — backdrop overlay + centered box ── */
  return (
    <div
      style={BDK}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div style={MODAL_BOX}>
        {content}
      </div>
    </div>
  );
}
