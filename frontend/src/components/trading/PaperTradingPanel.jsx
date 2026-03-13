/**
 * PaperTradingPanel.jsx — Paper trading session manager.
 *
 * Embedded as a tab within TradingPage. Lets the user start, monitor,
 * pause/resume, and stop paper (simulated) trading sessions. Displays
 * an active-trades list, a "start new trade" form, and a detail view
 * with equity chart and position history for the selected session.
 *
 * Auto-refreshes active trades every 30 seconds via polling.
 *
 * Props:
 *   @param {string}              token      — JWT access token
 *   @param {Array<{slug,name}>}  strategies — Strategy registry entries
 */

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { apiFetch } from "../../api/client";
import { fmtUSD, fmtPct, fmtDate } from "../../utils/formatters";

/* ── Constants ─────────────────────────────────────────────────────────────── */

/** Polling interval for active-trade refresh (ms). */
const POLL_MS = 30_000;

/** Colour tokens for P&L colouring. */
const GREEN = "#00d97e";
const RED = "#f04438";

/* ── Status Badge ──────────────────────────────────────────────────────────── */

/**
 * StatusBadge — Renders a coloured chip for a paper-trade status.
 *
 * @param {string} status — One of "active", "paused", "stopped", "error".
 * @returns {JSX.Element}
 */
function StatusBadge({ status }) {
  const palette = {
    active:  { bg: "rgba(0,217,126,0.15)", fg: GREEN },
    paused:  { bg: "rgba(255,171,0,0.15)",  fg: "var(--amber)" },
    stopped: { bg: "rgba(255,255,255,0.06)", fg: "var(--muted)" },
    error:   { bg: "rgba(240,68,56,0.15)",   fg: RED },
  };
  const p = palette[status] || palette.stopped;
  return (
    <span
      className="type-chip"
      style={{
        background: p.bg,
        color: p.fg,
        fontSize: 9,
        fontWeight: 700,
        letterSpacing: "0.06em",
        padding: "2px 7px",
        borderRadius: 3,
        textTransform: "uppercase",
      }}
    >
      {status}
    </span>
  );
}

/* ── P&L helpers ───────────────────────────────────────────────────────────── */

/**
 * pnlColor — Return green for positive, red for negative, muted for zero.
 *
 * @param {number} val — Numeric value.
 * @returns {string} CSS colour string.
 */
function pnlColor(val) {
  if (val > 0) return GREEN;
  if (val < 0) return RED;
  return "var(--muted)";
}

/* ── Mini SVG Equity Chart ─────────────────────────────────────────────────── */

/**
 * EquityChart — Simple SVG line chart for equity snapshots.
 *
 * @param {Array<{timestamp: string, equity: number}>} data   — Time series points.
 * @param {number}                                     height — Chart height in px.
 * @returns {JSX.Element}
 */
function EquityChart({ data, height = 180 }) {
  const containerRef = useRef(null);
  const [width, setWidth] = useState(500);

  /* Track container width via ResizeObserver for responsive SVG. */
  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  /* Compute Y-axis bounds from equity values. */
  const { minVal, maxVal, values } = useMemo(() => {
    const vals = data.map((d) => d.equity);
    let min = Infinity;
    let max = -Infinity;
    vals.forEach((v) => {
      if (v < min) min = v;
      if (v > max) max = v;
    });
    return { minVal: min, maxVal: max, values: vals };
  }, [data]);

  const range = maxVal - minVal || 1;
  const pad = 6;

  /* Determine line colour: green if equity grew, red if declined. */
  const lineColor =
    values.length >= 2 && values[values.length - 1] >= values[0] ? GREEN : RED;

  /* Build SVG polyline points string. */
  const points = useMemo(() => {
    if (!values.length) return "";
    const step = (width - pad * 2) / Math.max(values.length - 1, 1);
    return values
      .map((v, i) => {
        const x = pad + i * step;
        const y = height - pad - ((v - minVal) / range) * (height - pad * 2);
        return `${x},${y}`;
      })
      .join(" ");
  }, [values, width, height, minVal, range]);

  if (!data.length) {
    return (
      <div style={{ color: "var(--muted)", fontSize: 11, padding: "20px 0", textAlign: "center" }}>
        No equity data yet.
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      style={{
        width: "100%",
        background: "var(--bg1)",
        borderRadius: 4,
        border: "1px solid var(--border)",
      }}
    >
      <svg width={width} height={height}>
        <polyline
          points={points}
          fill="none"
          stroke={lineColor}
          strokeWidth={1.5}
          opacity={0.9}
        />
      </svg>
    </div>
  );
}

/* ── New Paper Trade Form ──────────────────────────────────────────────────── */

/**
 * NewTradeForm — Form for starting a new paper trading session.
 *
 * @param {Array<{slug,name}>} strategies — Available strategy options.
 * @param {Function}           onSubmit   — Callback(body) to start the trade.
 * @param {boolean}            loading    — Whether submission is in progress.
 * @returns {JSX.Element}
 */
function NewTradeForm({ strategies, onSubmit, loading }) {
  const [slug, setSlug] = useState("");
  const [symbol, setSymbol] = useState("");
  const [capital, setCapital] = useState("10000");

  /**
   * handleSubmit — Validate inputs and invoke parent callback.
   * @param {Event} e — Form submit event.
   */
  const handleSubmit = (e) => {
    e.preventDefault();
    if (!slug || !symbol.trim() || !capital) return;
    onSubmit({
      strategy_slug: slug,
      symbol: symbol.trim().toUpperCase(),
      initial_capital: parseFloat(capital),
    });
  };

  return (
    <form onSubmit={handleSubmit} style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap", marginBottom: 14 }}>
      {/* Strategy selector */}
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <label style={labelStyle}>STRATEGY</label>
        <select
          className="form-control"
          style={{ fontSize: 10, minWidth: 160 }}
          value={slug}
          onChange={(e) => setSlug(e.target.value)}
        >
          <option value="">Select strategy...</option>
          {strategies.map((s) => (
            <option key={s.slug} value={s.slug}>{s.name}</option>
          ))}
        </select>
      </div>

      {/* Symbol input */}
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <label style={labelStyle}>SYMBOL</label>
        <input
          className="form-control"
          style={{ fontSize: 10, width: 90, textTransform: "uppercase" }}
          placeholder="AAPL"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
        />
      </div>

      {/* Initial capital input */}
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <label style={labelStyle}>CAPITAL ($)</label>
        <input
          className="form-control"
          type="number"
          min="100"
          step="100"
          style={{ fontSize: 10, width: 100 }}
          value={capital}
          onChange={(e) => setCapital(e.target.value)}
        />
      </div>

      {/* Submit button */}
      <button
        className="btn"
        type="submit"
        disabled={loading || !slug || !symbol.trim()}
        style={{ fontSize: 10, padding: "5px 14px", background: "var(--amber)", color: "#000", fontWeight: 700 }}
      >
        {loading ? "STARTING..." : "START"}
      </button>
    </form>
  );
}

/* ── Trade Detail View ─────────────────────────────────────────────────────── */

/**
 * TradeDetail — Expanded detail view for a selected paper trade.
 *
 * Shows header info, equity statistics, an equity chart, position history
 * table, and action buttons (PAUSE/RESUME, STOP).
 *
 * @param {object}   trade       — Full paper trade object from API.
 * @param {Array}    equity      — Equity snapshot time series.
 * @param {Array}    positions   — Position history records.
 * @param {Function} onPause     — Callback to pause the trade.
 * @param {Function} onResume    — Callback to resume the trade.
 * @param {Function} onStop      — Callback to stop the trade.
 * @param {Function} onBack      — Callback to deselect (return to list).
 * @param {boolean}  actionLoading — Whether an action request is in flight.
 * @returns {JSX.Element}
 */
function TradeDetail({ trade, equity, positions, onPause, onResume, onStop, onBack, actionLoading }) {
  /* Derive P&L values from trade object. */
  const pnlDollar = (trade.current_equity ?? trade.initial_capital) - trade.initial_capital;
  const pnlPct = trade.initial_capital ? (pnlDollar / trade.initial_capital) * 100 : 0;

  return (
    <div>
      {/* Back link */}
      <button
        className="btn btn-outline"
        style={{ fontSize: 9, padding: "3px 8px", marginBottom: 10 }}
        onClick={onBack}
      >
        &larr; BACK TO LIST
      </button>

      {/* ── Header ───────────────────────────────────────────────────────── */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12, flexWrap: "wrap" }}>
        <span style={{ fontFamily: "var(--font-disp)", fontSize: 15, fontWeight: 700, color: "var(--fg)" }}>
          {trade.strategy_name || trade.strategy_slug}
        </span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 13, color: "var(--amber)", fontWeight: 600 }}>
          {trade.symbol}
        </span>
        <StatusBadge status={trade.status} />
        <span style={{ fontSize: 10, color: "var(--muted)" }}>
          Started {fmtDate(trade.started_at || trade.created_at)}
        </span>
      </div>

      {/* ── Equity Stats Grid ────────────────────────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 8, marginBottom: 14 }}>
        <StatCard label="INITIAL CAPITAL" value={fmtUSD(trade.initial_capital)} />
        <StatCard label="CURRENT EQUITY" value={fmtUSD(trade.current_equity ?? trade.initial_capital)} />
        <StatCard label="P&L %" value={fmtPct(pnlPct)} color={pnlColor(pnlDollar)} />
        <StatCard label="P&L $" value={fmtUSD(Math.abs(pnlDollar))} prefix={pnlDollar >= 0 ? "+" : "-"} color={pnlColor(pnlDollar)} />
      </div>

      {/* ── Equity Chart ─────────────────────────────────────────────────── */}
      <div style={{ marginBottom: 14 }}>
        <div style={sectionHeading}>EQUITY CURVE</div>
        <EquityChart data={equity} height={180} />
      </div>

      {/* ── Position History Table ────────────────────────────────────────── */}
      <div style={{ marginBottom: 14 }}>
        <div style={sectionHeading}>POSITION HISTORY</div>
        {positions.length === 0 ? (
          <div style={{ color: "var(--muted)", fontSize: 11, padding: "8px 0" }}>
            No positions recorded yet.
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="data-table" style={{ width: "100%", fontSize: 10 }}>
              <thead>
                <tr>
                  <th style={thStyle}>SIDE</th>
                  <th style={thStyle}>ENTRY</th>
                  <th style={thStyle}>EXIT</th>
                  <th style={thStyle}>P&L</th>
                  <th style={thStyle}>STATUS</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos, i) => {
                  const posColor = pnlColor(pos.pnl ?? 0);
                  return (
                    <tr key={pos.id || i}>
                      <td style={tdStyle}>
                        <span
                          className="type-chip"
                          style={{
                            fontSize: 8,
                            fontWeight: 700,
                            padding: "1px 5px",
                            background: pos.side === "long" ? "rgba(0,217,126,0.12)" : "rgba(240,68,56,0.12)",
                            color: pos.side === "long" ? GREEN : RED,
                            borderRadius: 2,
                            textTransform: "uppercase",
                          }}
                        >
                          {pos.side}
                        </span>
                      </td>
                      <td style={tdStyle}>{fmtUSD(pos.entry_price)}</td>
                      <td style={tdStyle}>{pos.exit_price != null ? fmtUSD(pos.exit_price) : "\u2014"}</td>
                      <td style={{ ...tdStyle, color: posColor, fontWeight: 600 }}>
                        {pos.pnl != null ? fmtUSD(pos.pnl) : "\u2014"}
                      </td>
                      <td style={tdStyle}>
                        <StatusBadge status={pos.status || (pos.exit_price != null ? "closed" : "open")} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Action Buttons ───────────────────────────────────────────────── */}
      {(trade.status === "active" || trade.status === "paused") && (
        <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
          {trade.status === "active" ? (
            <button
              className="btn btn-outline"
              style={{ fontSize: 10, padding: "4px 12px" }}
              disabled={actionLoading}
              onClick={onPause}
            >
              {actionLoading ? "..." : "PAUSE"}
            </button>
          ) : (
            <button
              className="btn btn-outline"
              style={{ fontSize: 10, padding: "4px 12px" }}
              disabled={actionLoading}
              onClick={onResume}
            >
              {actionLoading ? "..." : "RESUME"}
            </button>
          )}
          <button
            className="btn"
            style={{ fontSize: 10, padding: "4px 12px", background: RED, color: "#fff", fontWeight: 700 }}
            disabled={actionLoading}
            onClick={onStop}
          >
            {actionLoading ? "..." : "STOP"}
          </button>
        </div>
      )}
    </div>
  );
}

/* ── Stat Card (small metric tile) ─────────────────────────────────────────── */

/**
 * StatCard — Small labelled metric tile used in the detail header.
 *
 * @param {string} label  — Metric label (e.g. "INITIAL CAPITAL").
 * @param {string} value  — Formatted display value.
 * @param {string} [color]  — Override text colour for the value.
 * @param {string} [prefix] — Optional prefix (e.g. "+" or "-").
 * @returns {JSX.Element}
 */
function StatCard({ label, value, color, prefix }) {
  return (
    <div className="panel" style={{ padding: "8px 10px", background: "var(--bg1)", border: "1px solid var(--border)", borderRadius: 4 }}>
      <div style={{ fontSize: 8, fontWeight: 700, color: "var(--muted)", letterSpacing: "0.06em", marginBottom: 3 }}>
        {label}
      </div>
      <div style={{ fontSize: 14, fontWeight: 700, fontFamily: "var(--font-mono)", color: color || "var(--fg)" }}>
        {prefix && <span>{prefix}</span>}{value}
      </div>
    </div>
  );
}

/* ── Main Component ────────────────────────────────────────────────────────── */

/**
 * PaperTradingPanel — Top-level paper trading manager.
 *
 * Renders an active-trades list, a form to start new trades, and an
 * expandable detail view for any selected trade. Polls the backend
 * every 30 seconds to refresh active trade data.
 *
 * @param {string}              token      — JWT access token.
 * @param {Array<{slug,name}>}  strategies — Available strategies from registry.
 * @returns {JSX.Element}
 */
export function PaperTradingPanel({ token, strategies }) {
  /* ── List state ─────────────────────────────────────────────────────── */
  const [trades, setTrades] = useState([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState(null);

  /* ── New-trade form state ───────────────────────────────────────────── */
  const [startLoading, setStartLoading] = useState(false);
  const [startError, setStartError] = useState(null);

  /* ── Selected trade detail state ────────────────────────────────────── */
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [equity, setEquity] = useState([]);
  const [positions, setPositions] = useState([]);
  const [detailLoading, setDetailLoading] = useState(false);

  /* ── Action state (pause / resume / stop) ───────────────────────────── */
  const [actionLoading, setActionLoading] = useState(false);

  /* ── Fetch all paper trades ─────────────────────────────────────────── */

  /**
   * fetchTrades — Retrieve all paper trades from the backend and update
   * list state. Called on mount and every POLL_MS for active refresh.
   */
  const fetchTrades = useCallback(async () => {
    try {
      const data = await apiFetch("/trading/paper", { token });
      setTrades(data || []);
      setListError(null);
    } catch (err) {
      setListError(err.message);
    } finally {
      setListLoading(false);
    }
  }, [token]);

  /* Initial fetch on mount. */
  useEffect(() => {
    fetchTrades();
  }, [fetchTrades]);

  /* Poll every 30 seconds for active-trade updates. */
  useEffect(() => {
    const id = setInterval(fetchTrades, POLL_MS);
    return () => clearInterval(id);
  }, [fetchTrades]);

  /* ── Fetch detail for selected trade ────────────────────────────────── */

  /**
   * fetchDetail — Load trade detail, equity curve, and position history
   * for the currently selected paper trade ID.
   *
   * @param {string} id — Paper trade ID to load.
   */
  const fetchDetail = useCallback(
    async (id) => {
      setDetailLoading(true);
      try {
        /* Fetch trade detail, equity, and positions in parallel. */
        const [tradeData, equityData, posData] = await Promise.all([
          apiFetch(`/trading/paper/${id}`, { token }),
          apiFetch(`/trading/paper/${id}/equity`, { token }),
          apiFetch(`/trading/paper/${id}/positions`, { token }),
        ]);
        setDetail(tradeData);
        setEquity(equityData || []);
        setPositions(posData || []);
      } catch {
        /* On error, reset detail to null so UI shows list fallback. */
        setDetail(null);
        setEquity([]);
        setPositions([]);
      } finally {
        setDetailLoading(false);
      }
    },
    [token],
  );

  /* Reload detail whenever selectedId changes. */
  useEffect(() => {
    if (selectedId) fetchDetail(selectedId);
  }, [selectedId, fetchDetail]);

  /* ── Auto-refresh detail for active/paused trades ───────────────────── */
  useEffect(() => {
    if (!selectedId || !detail) return;
    if (detail.status !== "active" && detail.status !== "paused") return;
    const id = setInterval(() => fetchDetail(selectedId), POLL_MS);
    return () => clearInterval(id);
  }, [selectedId, detail, fetchDetail]);

  /* ── Start a new paper trade ────────────────────────────────────────── */

  /**
   * handleStart — Submit a new paper trade to the backend.
   *
   * @param {object} body — { strategy_slug, symbol, initial_capital }.
   */
  const handleStart = useCallback(
    async (body) => {
      setStartLoading(true);
      setStartError(null);
      try {
        await apiFetch("/trading/paper", { method: "POST", body, token });
        /* Refresh list to include the newly created trade. */
        await fetchTrades();
      } catch (err) {
        setStartError(err.message);
      } finally {
        setStartLoading(false);
      }
    },
    [token, fetchTrades],
  );

  /* ── Action handlers (pause, resume, stop) ──────────────────────────── */

  /**
   * handleAction — Execute a state-transition action on the selected trade.
   *
   * @param {"pause"|"resume"|"stop"} action — Action to execute.
   */
  const handleAction = useCallback(
    async (action) => {
      if (!selectedId) return;
      setActionLoading(true);
      try {
        await apiFetch(`/trading/paper/${selectedId}/${action}`, { method: "POST", token });
        /* Refresh both the detail view and the trades list. */
        await Promise.all([fetchDetail(selectedId), fetchTrades()]);
      } catch {
        /* Silently ignore — the UI state will not change, signalling failure. */
      } finally {
        setActionLoading(false);
      }
    },
    [selectedId, token, fetchDetail, fetchTrades],
  );

  const onPause  = useCallback(() => handleAction("pause"),  [handleAction]);
  const onResume = useCallback(() => handleAction("resume"), [handleAction]);
  const onStop   = useCallback(() => handleAction("stop"),   [handleAction]);

  /* ── Derived: sort trades — active first, then paused, then stopped ─── */
  const sortedTrades = useMemo(() => {
    const order = { active: 0, paused: 1, stopped: 2, error: 3 };
    return [...trades].sort((a, b) => (order[a.status] ?? 9) - (order[b.status] ?? 9));
  }, [trades]);

  /* ── Render ─────────────────────────────────────────────────────────── */
  return (
    <div style={{ padding: 12 }}>
      {/* ── New Trade Form ──────────────────────────────────────────────── */}
      <div style={sectionHeading}>NEW PAPER TRADE</div>
      <NewTradeForm strategies={strategies} onSubmit={handleStart} loading={startLoading} />
      {startError && (
        <div style={{ color: RED, fontSize: 11, marginBottom: 8 }}>Error: {startError}</div>
      )}

      {/* ── Detail View (selected trade) ────────────────────────────────── */}
      {selectedId && detail && !detailLoading ? (
        <TradeDetail
          trade={detail}
          equity={equity}
          positions={positions}
          onPause={onPause}
          onResume={onResume}
          onStop={onStop}
          onBack={() => { setSelectedId(null); setDetail(null); }}
          actionLoading={actionLoading}
        />
      ) : selectedId && detailLoading ? (
        <div style={{ color: "var(--muted)", fontSize: 11, padding: "12px 0" }}>
          Loading trade details...
        </div>
      ) : (
        /* ── Active Trades List ──────────────────────────────────────────── */
        <>
          <div style={sectionHeading}>YOUR PAPER TRADES</div>

          {listLoading && (
            <div style={{ color: "var(--muted)", fontSize: 11, padding: "12px 0" }}>
              Loading trades...
            </div>
          )}

          {listError && (
            <div style={{ color: RED, fontSize: 11, marginBottom: 8 }}>Error: {listError}</div>
          )}

          {!listLoading && !listError && sortedTrades.length === 0 && (
            <div style={{ color: "var(--muted)", fontSize: 11, padding: "12px 0" }}>
              No paper trades yet. Start one above.
            </div>
          )}

          {sortedTrades.length > 0 && (
            <div style={{ overflowX: "auto" }}>
              <table className="data-table" style={{ width: "100%", fontSize: 10 }}>
                <thead>
                  <tr>
                    <th style={thStyle}>STATUS</th>
                    <th style={thStyle}>SYMBOL</th>
                    <th style={thStyle}>STRATEGY</th>
                    <th style={{ ...thStyle, textAlign: "right" }}>P&L %</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedTrades.map((t) => {
                    const pnl = t.initial_capital
                      ? (((t.current_equity ?? t.initial_capital) - t.initial_capital) / t.initial_capital) * 100
                      : 0;
                    return (
                      <tr
                        key={t.id}
                        style={{ cursor: "pointer" }}
                        onClick={() => setSelectedId(t.id)}
                      >
                        <td style={tdStyle}><StatusBadge status={t.status} /></td>
                        <td style={{ ...tdStyle, fontFamily: "var(--font-mono)", color: "var(--amber)", fontWeight: 600 }}>
                          {t.symbol}
                        </td>
                        <td style={tdStyle}>{t.strategy_name || t.strategy_slug}</td>
                        <td style={{ ...tdStyle, textAlign: "right", fontFamily: "var(--font-mono)", fontWeight: 600, color: pnlColor(pnl) }}>
                          {fmtPct(pnl)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ── Inline Styles ─────────────────────────────────────────────────────────── */

const labelStyle = {
  fontSize: 8,
  fontWeight: 700,
  color: "var(--muted)",
  letterSpacing: "0.06em",
  textTransform: "uppercase",
};

const sectionHeading = {
  fontSize: 11,
  fontWeight: 700,
  color: "var(--fg)",
  letterSpacing: "0.05em",
  marginBottom: 8,
};

const thStyle = {
  textAlign: "left",
  padding: "8px 10px",
  fontSize: 9,
  fontWeight: 700,
  color: "var(--muted)",
  letterSpacing: "0.05em",
};

const tdStyle = {
  padding: "6px 10px",
  borderTop: "1px solid var(--border)",
};
