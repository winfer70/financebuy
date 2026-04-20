/**
 * ExitPointsPage.jsx — Exit Points Analysis page for TickerTap.
 *
 * Provides an interactive exit-point analysis tool that calculates and
 * visualises key price levels (ATR stops, Bollinger bands, moving-average
 * support/resistance, Fibonacci retracements, 52-week extremes) for any
 * given ticker symbol.
 *
 * Layout:
 *   1. Input bar — symbol text input, period dropdown, ANALYZE button
 *   2. Overview panel — current price, trend, RSI, ATR, support/resistance zones
 *   3. Price ladder — vertical div-based visualisation of all levels
 *   4. Levels table — sortable, colour-coded table of every computed level
 *
 * Data flow:
 *   - User enters symbol + period and clicks ANALYZE
 *   - POST /trading/exit-analysis is called via api.analyzeExitPoints()
 *   - Response populates all four sections
 */

import { useState, useCallback, useMemo } from "react";
import api from "../api/client";

/* ── Period dropdown options ──────────────────────────────────────────────── */
const PERIOD_OPTIONS = [
  { label: "6M", value: 180 },
  { label: "1Y", value: 365 },
  { label: "2Y", value: 730 },
];

/* ── Level type colour map — used for badges and ladder lines ────────────── */
const TYPE_COLORS = {
  stop_loss:   { bg: "rgba(239,68,68,0.15)",  text: "#ef4444", border: "#ef4444" },
  take_profit: { bg: "rgba(34,197,94,0.15)",   text: "#22c55e", border: "#22c55e" },
  support:     { bg: "rgba(59,130,246,0.15)",  text: "#3b82f6", border: "#3b82f6" },
  resistance:  { bg: "rgba(249,115,22,0.15)",  text: "#f97316", border: "#f97316" },
  fibonacci:   { bg: "rgba(168,85,247,0.15)",  text: "#a855f7", border: "#a855f7" },
};

/* ── Trend badge colour ──────────────────────────────────────────────────── */
const TREND_COLORS = {
  bullish: "#22c55e",
  bearish: "#ef4444",
  neutral: "#6b7280",
};

/* ── Sort keys for the table ─────────────────────────────────────────────── */
const SORT_KEYS = [
  { key: "level_type", label: "TYPE" },
  { key: "price",      label: "PRICE" },
  { key: "distance",   label: "DISTANCE" },
  { key: "label",      label: "LABEL" },
];

/* ── Utility: format a number as USD ─────────────────────────────────────── */
/**
 * fmtUsd — format a numeric price to USD string.
 * @param {number} n - Price value
 * @returns {string} Formatted string e.g. "$175.50"
 */
function fmtUsd(n) {
  if (n == null) return "--";
  return "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/**
 * fmtPct — format a number as a signed percentage string.
 * @param {number} n - Percentage value
 * @returns {string} Formatted string e.g. "+3.7%" or "-4.0%"
 */
function fmtPct(n) {
  const sign = n >= 0 ? "+" : "";
  return sign + n.toFixed(2) + "%";
}

/* ── Reusable style constants ────────────────────────────────────────────── */
const CARD_STYLE = {
  background: "rgba(255,255,255,0.03)",
  borderRadius: 8,
  padding: "16px 20px",
  border: "1px solid rgba(255,255,255,0.06)",
};

const SECTION_HEADER = {
  fontFamily: "var(--font-mono)",
  fontSize: 11,
  letterSpacing: "1px",
  color: "var(--muted)",
  marginBottom: 12,
  textTransform: "uppercase",
};

/* ═══════════════════════════════════════════════════════════════════════════
   PRICE LADDER — Vertical div-based visualisation of all levels
═══════════════════════════════════════════════════════════════════════════ */

/**
 * PriceLadder — renders a vertical bar with horizontal lines for each level
 * and the current price, scaled proportionally within a fixed container height.
 *
 * @param {object}   props
 * @param {number}   props.currentPrice - Current price of the symbol
 * @param {Array}    props.levels       - Array of ExitLevel objects
 */
function PriceLadder({ currentPrice, levels }) {
  const CONTAINER_HEIGHT = 420; // px
  const PADDING = 24;           // top/bottom padding in px

  // Collect all prices (levels + current) to determine the range
  const allPrices = useMemo(() => {
    const prices = levels.map((l) => l.price);
    prices.push(currentPrice);
    return prices;
  }, [levels, currentPrice]);

  const minPrice = Math.min(...allPrices);
  const maxPrice = Math.max(...allPrices);
  const range = maxPrice - minPrice || 1; // avoid division by zero

  /**
   * priceToY — map a price to a vertical pixel offset inside the container.
   * Higher prices are closer to the top (lower y value).
   *
   * @param {number} price
   * @returns {number} Pixel offset from top of the container
   */
  const priceToY = (price) => {
    const pct = (price - minPrice) / range;
    // Invert so high prices = top
    return PADDING + (1 - pct) * (CONTAINER_HEIGHT - 2 * PADDING);
  };

  // Deduplicate overlapping levels — group by rounded y-position
  const sortedLevels = useMemo(() => {
    return [...levels].sort((a, b) => b.price - a.price);
  }, [levels]);

  return (
    <div style={{ ...CARD_STYLE, position: "relative", height: CONTAINER_HEIGHT, overflow: "hidden" }}>
      <div style={SECTION_HEADER}>PRICE LEVELS CHART</div>

      {/* Vertical centre line */}
      <div
        style={{
          position: "absolute",
          left: "40%",
          top: PADDING,
          bottom: PADDING,
          width: 1,
          background: "rgba(255,255,255,0.08)",
        }}
      />

      {/* Level lines */}
      {sortedLevels.map((level, i) => {
        const y = priceToY(level.price);
        const color = TYPE_COLORS[level.level_type]?.border || "#6b7280";
        return (
          <div
            key={`${level.label}-${i}`}
            style={{
              position: "absolute",
              left: "15%",
              right: 12,
              top: y,
              height: 0,
              borderTop: `1px dashed ${color}`,
              display: "flex",
              alignItems: "center",
            }}
          >
            {/* Price label on the left */}
            <span
              style={{
                position: "absolute",
                left: -2,
                top: -16,
                fontFamily: "var(--font-mono)",
                fontSize: 10,
                color,
                whiteSpace: "nowrap",
              }}
            >
              {fmtUsd(level.price)}
            </span>
            {/* Level name on the right */}
            <span
              style={{
                position: "absolute",
                right: 0,
                top: -16,
                fontFamily: "var(--font-mono)",
                fontSize: 10,
                color,
                whiteSpace: "nowrap",
              }}
            >
              {level.label}
            </span>
          </div>
        );
      })}

      {/* Current price — thick amber line */}
      <div
        style={{
          position: "absolute",
          left: "10%",
          right: 8,
          top: priceToY(currentPrice),
          height: 0,
          borderTop: "2px solid var(--amber)",
          zIndex: 2,
        }}
      >
        <span
          style={{
            position: "absolute",
            left: -2,
            top: -18,
            fontFamily: "var(--font-mono)",
            fontSize: 11,
            fontWeight: 700,
            color: "var(--amber)",
            whiteSpace: "nowrap",
          }}
        >
          {fmtUsd(currentPrice)}  CURRENT
        </span>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   TYPE BADGE — coloured pill for level type
═══════════════════════════════════════════════════════════════════════════ */

/**
 * TypeBadge — small pill-shaped badge with a type-specific colour.
 *
 * @param {object} props
 * @param {string} props.type - One of "stop_loss", "take_profit", "support", "resistance", "fibonacci"
 */
function TypeBadge({ type }) {
  const style = TYPE_COLORS[type] || { bg: "rgba(255,255,255,0.1)", text: "#aaa" };
  const labels = {
    stop_loss:   "STOP LOSS",
    take_profit: "TAKE PROFIT",
    support:     "SUPPORT",
    resistance:  "RESISTANCE",
    fibonacci:   "FIBONACCI",
  };
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: 4,
        fontSize: 10,
        fontFamily: "var(--font-mono)",
        fontWeight: 600,
        letterSpacing: "0.5px",
        background: style.bg,
        color: style.text,
        whiteSpace: "nowrap",
      }}
    >
      {labels[type] || type.toUpperCase()}
    </span>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   EXIT POINTS PAGE — main component
═══════════════════════════════════════════════════════════════════════════ */

/**
 * ExitPointsPage — renders the full exit analysis page.
 *
 * @param {object} props
 * @param {string} props.token - JWT access token
 */
export default function ExitPointsPage({ token }) {
  /* ── Local state ─────────────────────────────────────────────────────── */
  const [symbol,    setSymbol]    = useState("");
  const [period,    setPeriod]    = useState(365);
  const [loading,   setLoading]   = useState(false);
  const [error,     setError]     = useState("");
  const [data,      setData]      = useState(null);
  const [sortKey,   setSortKey]   = useState("price");
  const [sortAsc,   setSortAsc]   = useState(true);

  /* ── Analyze handler ─────────────────────────────────────────────────── */
  /**
   * handleAnalyze — call the backend exit-analysis endpoint.
   * Validates input, shows loading state, and stores the response.
   */
  const handleAnalyze = useCallback(async () => {
    const sym = symbol.trim().toUpperCase();
    if (!sym) { setError("Please enter a symbol."); return; }
    setError("");
    setLoading(true);
    setData(null);
    try {
      const result = await api.analyzeExitPoints(
        { symbol: sym, period_days: period },
        token,
      );
      setData(result);
    } catch (e) {
      setError(e.message || "Analysis failed.");
    } finally {
      setLoading(false);
    }
  }, [symbol, period, token]);

  /* ── Sort handler for the levels table ───────────────────────────────── */
  /**
   * handleSort — toggle sort direction when clicking same column,
   *              or switch sort key when clicking a different column.
   * @param {string} key - Column key to sort by
   */
  const handleSort = (key) => {
    if (key === sortKey) {
      setSortAsc((prev) => !prev);
    } else {
      setSortKey(key);
      setSortAsc(true);
    }
  };

  /* ── Compute sorted levels with distance % ──────────────────────────── */
  const sortedLevels = useMemo(() => {
    if (!data) return [];
    const enriched = data.levels.map((l) => ({
      ...l,
      distance: data.current_price
        ? ((l.price - data.current_price) / data.current_price) * 100
        : 0,
    }));

    enriched.sort((a, b) => {
      let av = a[sortKey], bv = b[sortKey];
      if (typeof av === "string") av = av.toLowerCase();
      if (typeof bv === "string") bv = bv.toLowerCase();
      if (av < bv) return sortAsc ? -1 : 1;
      if (av > bv) return sortAsc ? 1 : -1;
      return 0;
    });
    return enriched;
  }, [data, sortKey, sortAsc]);

  /* ── RSI colour helper ──────────────────────────────────────────────── */
  /**
   * rsiColor — return a CSS colour string based on RSI value.
   * @param {number} val - RSI reading (0-100)
   * @returns {string} CSS colour
   */
  const rsiColor = (val) => {
    if (val >= 70) return "#ef4444";
    if (val <= 30) return "#22c55e";
    return "#f59e0b";
  };

  /* ── Handle Enter key in symbol input ───────────────────────────────── */
  const handleKeyDown = (e) => {
    if (e.key === "Enter") handleAnalyze();
  };

  /* ══════════════════════════════════════════════════════════════════════
     RENDER
  ══════════════════════════════════════════════════════════════════════ */
  return (
    <div className="page-scroll">
    <div className="page-content" style={{ padding: "24px 32px", maxWidth: 1100 }}>
      {/* Page title */}
      <h2
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: 16,
          letterSpacing: "1.5px",
          color: "var(--amber)",
          marginBottom: 20,
          fontWeight: 600,
        }}
      >
        EXIT POINTS ANALYSIS
      </h2>

      {/* ── Input bar ──────────────────────────────────────────────────── */}
      <div
        style={{
          ...CARD_STYLE,
          display: "flex",
          alignItems: "center",
          gap: 12,
          marginBottom: 20,
          flexWrap: "wrap",
        }}
      >
        {/* Symbol input */}
        <label
          style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--muted)", letterSpacing: "0.5px" }}
        >
          SYMBOL
        </label>
        <input
          type="text"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          onKeyDown={handleKeyDown}
          placeholder="AAPL"
          maxLength={20}
          style={{
            background: "rgba(255,255,255,0.05)",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: 4,
            padding: "6px 10px",
            fontFamily: "var(--font-mono)",
            fontSize: 13,
            color: "#fff",
            width: 110,
            outline: "none",
          }}
        />

        {/* Period dropdown */}
        <label
          style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--muted)", letterSpacing: "0.5px" }}
        >
          PERIOD
        </label>
        <select
          value={period}
          onChange={(e) => setPeriod(Number(e.target.value))}
          style={{
            background: "rgba(255,255,255,0.05)",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: 4,
            padding: "6px 10px",
            fontFamily: "var(--font-mono)",
            fontSize: 13,
            color: "#fff",
            cursor: "pointer",
            outline: "none",
          }}
        >
          {PERIOD_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value} style={{ background: "#1a1a2e" }}>
              {opt.label}
            </option>
          ))}
        </select>

        {/* Analyze button */}
        <button
          onClick={handleAnalyze}
          disabled={loading || !symbol.trim()}
          style={{
            background: "var(--amber)",
            color: "#000",
            border: "none",
            borderRadius: 4,
            padding: "7px 20px",
            fontFamily: "var(--font-mono)",
            fontSize: 12,
            fontWeight: 700,
            letterSpacing: "1px",
            cursor: loading ? "wait" : "pointer",
            opacity: loading || !symbol.trim() ? 0.5 : 1,
            transition: "opacity 0.15s",
          }}
        >
          {loading ? "ANALYZING..." : "ANALYZE"}
        </button>
      </div>

      {/* ── Error display ──────────────────────────────────────────────── */}
      {error && (
        <div
          style={{
            background: "rgba(239,68,68,0.1)",
            border: "1px solid rgba(239,68,68,0.3)",
            borderRadius: 6,
            padding: "10px 16px",
            marginBottom: 20,
            fontFamily: "var(--font-mono)",
            fontSize: 12,
            color: "#ef4444",
          }}
        >
          {error}
        </div>
      )}

      {/* ── Loading spinner ────────────────────────────────────────────── */}
      {loading && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: 32,
            justifyContent: "center",
          }}
        >
          <div
            style={{
              width: 18,
              height: 18,
              border: "2px solid rgba(245,158,11,0.3)",
              borderTop: "2px solid var(--amber)",
              borderRadius: "50%",
              animation: "spin 0.8s linear infinite",
            }}
          />
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 12,
              color: "var(--amber)",
              letterSpacing: "0.5px",
            }}
          >
            Analyzing exit points...
          </span>
          {/* Inline keyframe for the spinner */}
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      )}

      {/* ── Results ────────────────────────────────────────────────────── */}
      {data && !loading && (
        <>
          {/* ── Overview panel ──────────────────────────────────────────── */}
          <div style={{ ...CARD_STYLE, marginBottom: 20 }}>
            <div style={SECTION_HEADER}>OVERVIEW</div>
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: "16px 32px",
                alignItems: "baseline",
              }}
            >
              {/* Symbol + price */}
              <div>
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: 18,
                    fontWeight: 700,
                    color: "#fff",
                    letterSpacing: "1px",
                  }}
                >
                  {data.symbol}
                </span>
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: 18,
                    fontWeight: 600,
                    color: "var(--amber)",
                    marginLeft: 12,
                  }}
                >
                  {fmtUsd(data.current_price)}
                </span>
              </div>

              {/* Trend badge */}
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: 11,
                    color: "var(--muted)",
                  }}
                >
                  Trend:
                </span>
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: 12,
                    fontWeight: 700,
                    color: TREND_COLORS[data.trend] || "#6b7280",
                    textTransform: "uppercase",
                    letterSpacing: "0.5px",
                  }}
                >
                  {data.trend}
                </span>
              </div>

              {/* RSI */}
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: 11,
                    color: "var(--muted)",
                  }}
                >
                  RSI:
                </span>
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: 13,
                    fontWeight: 600,
                    color: rsiColor(data.rsi),
                  }}
                >
                  {data.rsi.toFixed(1)}
                </span>
              </div>

              {/* ATR */}
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: 11,
                    color: "var(--muted)",
                  }}
                >
                  ATR(14):
                </span>
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: 13,
                    fontWeight: 600,
                    color: "#fff",
                  }}
                >
                  {fmtUsd(data.atr_value)} ({data.atr_pct.toFixed(2)}%)
                </span>
              </div>

              {/* Support zone */}
              {data.support_zone != null && (
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: 11,
                      color: "var(--muted)",
                    }}
                  >
                    Support Zone:
                  </span>
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: 13,
                      fontWeight: 600,
                      color: "#3b82f6",
                    }}
                  >
                    {fmtUsd(data.support_zone)}
                  </span>
                </div>
              )}

              {/* Resistance zone */}
              {data.resistance_zone != null && (
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: 11,
                      color: "var(--muted)",
                    }}
                  >
                    Resistance Zone:
                  </span>
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: 13,
                      fontWeight: 600,
                      color: "#f97316",
                    }}
                  >
                    {fmtUsd(data.resistance_zone)}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* ── Price ladder visualisation ──────────────────────────────── */}
          <div style={{ marginBottom: 20 }}>
            <PriceLadder
              currentPrice={data.current_price}
              levels={data.levels}
            />
          </div>

          {/* ── Levels table ───────────────────────────────────────────── */}
          <div style={{ ...CARD_STYLE, padding: 0, overflow: "hidden" }}>
            <div style={{ ...SECTION_HEADER, padding: "16px 20px 0 20px" }}>
              LEVELS TABLE
            </div>
            <div style={{ overflowX: "auto" }}>
              <table className="data-table" style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    {SORT_KEYS.map((col) => (
                      <th
                        key={col.key}
                        onClick={() => handleSort(col.key)}
                        style={{
                          cursor: "pointer",
                          textAlign: "left",
                          padding: "10px 16px",
                          fontFamily: "var(--font-mono)",
                          fontSize: 10,
                          letterSpacing: "1px",
                          color: sortKey === col.key ? "var(--amber)" : "var(--muted)",
                          borderBottom: "1px solid rgba(255,255,255,0.06)",
                          userSelect: "none",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {col.label}
                        {sortKey === col.key && (
                          <span style={{ marginLeft: 4 }}>{sortAsc ? "\u25B2" : "\u25BC"}</span>
                        )}
                      </th>
                    ))}
                    <th
                      style={{
                        textAlign: "left",
                        padding: "10px 16px",
                        fontFamily: "var(--font-mono)",
                        fontSize: 10,
                        letterSpacing: "1px",
                        color: "var(--muted)",
                        borderBottom: "1px solid rgba(255,255,255,0.06)",
                      }}
                    >
                      RATIONALE
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sortedLevels.map((level, idx) => (
                    <tr
                      key={`${level.label}-${idx}`}
                      style={{
                        borderBottom: "1px solid rgba(255,255,255,0.04)",
                        transition: "background 0.1s",
                      }}
                      onMouseOver={(e) => (e.currentTarget.style.background = "rgba(255,255,255,0.03)")}
                      onMouseOut={(e) => (e.currentTarget.style.background = "transparent")}
                    >
                      {/* Type badge */}
                      <td style={{ padding: "8px 16px" }}>
                        <TypeBadge type={level.level_type} />
                      </td>

                      {/* Price */}
                      <td
                        style={{
                          padding: "8px 16px",
                          fontFamily: "var(--font-mono)",
                          fontSize: 12,
                          color: "#fff",
                          fontWeight: 600,
                        }}
                      >
                        {fmtUsd(level.price)}
                      </td>

                      {/* Distance from current price */}
                      <td
                        style={{
                          padding: "8px 16px",
                          fontFamily: "var(--font-mono)",
                          fontSize: 12,
                          fontWeight: 600,
                          color: level.distance >= 0 ? "#22c55e" : "#ef4444",
                        }}
                      >
                        {fmtPct(level.distance)}
                      </td>

                      {/* Label */}
                      <td
                        style={{
                          padding: "8px 16px",
                          fontFamily: "var(--font-mono)",
                          fontSize: 11,
                          color: "rgba(255,255,255,0.7)",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {level.label}
                      </td>

                      {/* Rationale */}
                      <td
                        style={{
                          padding: "8px 16px",
                          fontFamily: "var(--font-mono)",
                          fontSize: 11,
                          color: "var(--muted)",
                          maxWidth: 320,
                        }}
                      >
                        {level.rationale}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* Empty state — shown before any analysis is run */}
      {!data && !loading && !error && (
        <div
          style={{
            textAlign: "center",
            padding: "60px 20px",
            color: "var(--muted)",
            fontFamily: "var(--font-mono)",
            fontSize: 12,
            letterSpacing: "0.5px",
          }}
        >
          Enter a symbol and click ANALYZE to compute exit points.
        </div>
      )}
    </div>
    </div>
  );
}
