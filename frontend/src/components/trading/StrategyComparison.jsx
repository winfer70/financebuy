/**
 * StrategyComparison.jsx — Side-by-side strategy backtest comparison.
 *
 * Allows users to select 2–3 strategies and run backtests on the same
 * symbol/period, then displays metrics side-by-side with overlaid
 * equity curves on a single chart.
 *
 * Props:
 *   @param {string} token    — JWT access token
 *   @param {string} symbol   — Currently selected symbol (e.g. "AAPL")
 *   @param {string} interval — Current interval (e.g. "1d")
 *   @param {string} period   — Current period (e.g. "1Y")
 */

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { apiFetch } from "../../api/client";
import api from "../../api/client";

/* ── Constants ─────────────────────────────────────────────────────────────── */

const COLORS = ["var(--amber)", "var(--cyan)", "var(--green)"];
const MAX_SLOTS = 3;

const PERIOD_DAYS = {
  "1M": 30, "3M": 90, "6M": 180, "1Y": 365,
  "2Y": 730, "5Y": 1825, "ALL": 3650,
};

/**
 * CompareMetric — Single metric row in the comparison table.
 *
 * @param {string}   label  — Metric label (e.g. "Total Return")
 * @param {string[]} values — One value per strategy slot
 * @param {string[]} colors — Colour per slot
 */
function CompareMetric({ label, values, colors }) {
  return (
    <tr>
      <td style={metricLabel}>{label}</td>
      {values.map((v, i) => (
        <td key={i} style={{ ...metricValue, color: colors[i] || "var(--text)" }}>
          {v ?? "—"}
        </td>
      ))}
    </tr>
  );
}

/* ── Mini Equity Chart (SVG overlay) ───────────────────────────────────────── */

/**
 * EquityOverlayChart — Overlaid equity curves for up to 3 strategies.
 *
 * @param {Array}  curves — Array of { color, equity: number[] }
 * @param {number} height — Chart height in px
 */
function EquityOverlayChart({ curves, height = 200 }) {
  const containerRef = useRef(null);
  const [width, setWidth] = useState(600);

  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width));
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  // Compute global min/max across all curves for shared Y axis
  const { minVal, maxVal } = useMemo(() => {
    let min = Infinity, max = -Infinity;
    curves.forEach(({ equity }) => {
      equity.forEach((v) => {
        if (v < min) min = v;
        if (v > max) max = v;
      });
    });
    return { minVal: min, maxVal: max };
  }, [curves]);

  const range = maxVal - minVal || 1;
  const pad = 4;

  return (
    <div ref={containerRef} style={{ width: "100%", background: "var(--bg-panel, #1a1a2e)", borderRadius: 4, border: "1px solid var(--border)" }}>
      <svg width={width} height={height}>
        {curves.map(({ color, equity }, ci) => {
          if (!equity.length) return null;
          const step = (width - pad * 2) / Math.max(equity.length - 1, 1);
          const pts = equity.map((v, i) => {
            const x = pad + i * step;
            const y = height - pad - ((v - minVal) / range) * (height - pad * 2);
            return `${x},${y}`;
          }).join(" ");
          return <polyline key={ci} points={pts} fill="none" stroke={color} strokeWidth={1.5} opacity={0.85} />;
        })}
      </svg>
    </div>
  );
}

/* ── Main Component ────────────────────────────────────────────────────────── */

export default function StrategyComparison({ token, symbol, interval, period }) {
  /* -- State: strategy selection ----------------------------------------- */
  const [allStrategies, setAllStrategies] = useState([]);
  const [slots, setSlots] = useState(["", ""]); // strategy_id or slug strings
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);

  /* -- State: comparison results ----------------------------------------- */
  const [results, setResults] = useState([]); // { strategy, metrics, equity }

  /* -- Fetch user's strategies on mount ---------------------------------- */
  useEffect(() => {
    (async () => {
      try {
        const strats = await api.listStrategies(token);
        setAllStrategies(strats || []);
      } catch { /* ignore */ }
    })();
  }, [token]);

  /* -- Update slot value ------------------------------------------------- */
  const setSlot = (index, value) => {
    const next = [...slots];
    next[index] = value;
    setSlots(next);
  };

  /* -- Add/remove slot --------------------------------------------------- */
  const addSlot = () => {
    if (slots.length < MAX_SLOTS) setSlots([...slots, ""]);
  };
  const removeSlot = (index) => {
    if (slots.length <= 2) return;
    setSlots(slots.filter((_, i) => i !== index));
  };

  /* -- Run comparison backtests ------------------------------------------ */
  const runComparison = useCallback(async () => {
    const activeSlots = slots.filter(Boolean);
    if (activeSlots.length < 2 || !symbol) return;

    setRunning(true);
    setError(null);
    setResults([]);

    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - (PERIOD_DAYS[period] || 365));

    try {
      // Queue all backtests in parallel
      const backtestPromises = activeSlots.map(async (slug) => {
        const strat = allStrategies.find((s) => s.slug === slug);
        const body = {
          strategy_slug: slug,
          symbol,
          interval,
          start_date: start.toISOString().slice(0, 10),
          end_date: end.toISOString().slice(0, 10),
          params: strat?.default_params || {},
          initial_capital: 10000,
          commission_pct: 0.001,
          slippage_pct: 0.0005,
        };

        // Queue backtest
        const res = await apiFetch("/trading/backtest", { method: "POST", body, token });
        const resultId = res.result_id;

        // Poll until completed
        let result = null;
        for (let i = 0; i < 120; i++) {
          await new Promise((r) => setTimeout(r, 2000));
          const poll = await apiFetch(`/trading/backtest/${resultId}`, { token });
          if (poll.status === "completed") { result = poll; break; }
          if (poll.status === "failed") throw new Error(`Backtest failed for ${slug}`);
        }
        if (!result) throw new Error(`Backtest timeout for ${slug}`);

        return {
          strategy: strat || { name: slug, slug },
          metrics: result.metrics_json || {},
          equity: (result.results_json?.equity_curve || []).map((e) => e.value || e),
        };
      });

      const compareResults = await Promise.all(backtestPromises);
      setResults(compareResults);
    } catch (err) {
      setError(err.message);
    } finally {
      setRunning(false);
    }
  }, [slots, symbol, interval, period, allStrategies, token]);

  /* -- Metric extraction helper ------------------------------------------ */
  const fmt = (v, suffix = "") => v != null ? `${Number(v).toFixed(2)}${suffix}` : "—";

  /* ── Render ─────────────────────────────────────────────────────────────── */
  return (
    <div style={{ padding: 12 }}>
      {/* Strategy Selection */}
      <div style={{ display: "flex", gap: 8, alignItems: "flex-end", marginBottom: 12, flexWrap: "wrap" }}>
        {slots.map((slug, i) => (
          <div key={i} style={{ display: "flex", gap: 4, alignItems: "center" }}>
            <div style={{ width: 8, height: 8, borderRadius: "50%", background: COLORS[i], flexShrink: 0 }} />
            <select
              className="form-control"
              style={{ fontSize: 10, minWidth: 150 }}
              value={slug}
              onChange={(e) => setSlot(i, e.target.value)}
            >
              <option value="">Select strategy...</option>
              {allStrategies.map((s) => (
                <option key={s.slug} value={s.slug}>{s.name}</option>
              ))}
            </select>
            {slots.length > 2 && (
              <button
                className="btn btn-outline"
                style={{ padding: "2px 6px", fontSize: 9 }}
                onClick={() => removeSlot(i)}
              >
                &times;
              </button>
            )}
          </div>
        ))}
        {slots.length < MAX_SLOTS && (
          <button
            className="btn btn-outline"
            style={{ padding: "2px 8px", fontSize: 9 }}
            onClick={addSlot}
          >
            + ADD
          </button>
        )}
        <button
          className="btn btn-primary"
          style={{ fontSize: 10, padding: "4px 12px" }}
          disabled={running || slots.filter(Boolean).length < 2 || !symbol}
          onClick={runComparison}
        >
          {running ? "COMPARING..." : "COMPARE"}
        </button>
      </div>

      {!symbol && (
        <div style={{ color: "var(--muted)", fontSize: 11, marginBottom: 8 }}>
          Select a symbol above to compare strategies.
        </div>
      )}

      {error && (
        <div style={{ color: "var(--red)", fontSize: 11, marginBottom: 8 }}>
          Error: {error}
        </div>
      )}

      {/* Results */}
      {results.length > 0 && (
        <>
          {/* Equity Overlay Chart */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text)", marginBottom: 6, letterSpacing: "0.05em" }}>
              EQUITY CURVES
            </div>
            <EquityOverlayChart
              curves={results.map((r, i) => ({
                color: COLORS[i],
                equity: r.equity,
              }))}
              height={200}
            />
            {/* Legend */}
            <div style={{ display: "flex", gap: 16, marginTop: 6 }}>
              {results.map((r, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 9 }}>
                  <div style={{ width: 10, height: 3, background: COLORS[i], borderRadius: 1 }} />
                  <span style={{ color: "var(--muted)" }}>{r.strategy.name}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Metrics Comparison Table */}
          <table className="data-table" style={{ width: "100%", fontSize: 11 }}>
            <thead>
              <tr>
                <th style={thStyle}>METRIC</th>
                {results.map((r, i) => (
                  <th key={i} style={{ ...thStyle, color: COLORS[i] }}>{r.strategy.name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              <CompareMetric
                label="TOTAL RETURN"
                values={results.map((r) => fmt(r.metrics.total_return_pct, "%"))}
                colors={COLORS}
              />
              <CompareMetric
                label="SHARPE RATIO"
                values={results.map((r) => fmt(r.metrics.sharpe_ratio))}
                colors={COLORS}
              />
              <CompareMetric
                label="MAX DRAWDOWN"
                values={results.map((r) => fmt(r.metrics.max_drawdown_pct, "%"))}
                colors={COLORS}
              />
              <CompareMetric
                label="WIN RATE"
                values={results.map((r) => fmt(r.metrics.win_rate_pct, "%"))}
                colors={COLORS}
              />
              <CompareMetric
                label="TOTAL TRADES"
                values={results.map((r) => r.metrics.total_trades ?? "—")}
                colors={COLORS}
              />
              <CompareMetric
                label="AVG TRADE"
                values={results.map((r) => fmt(r.metrics.avg_trade_pct, "%"))}
                colors={COLORS}
              />
              <CompareMetric
                label="PROFIT FACTOR"
                values={results.map((r) => fmt(r.metrics.profit_factor))}
                colors={COLORS}
              />
              <CompareMetric
                label="SORTINO RATIO"
                values={results.map((r) => fmt(r.metrics.sortino_ratio))}
                colors={COLORS}
              />
              <CompareMetric
                label="CALMAR RATIO"
                values={results.map((r) => fmt(r.metrics.calmar_ratio))}
                colors={COLORS}
              />
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

/* ── Inline Styles ─────────────────────────────────────────────────────────── */

const metricLabel = {
  padding: "6px 10px",
  fontSize: 9,
  fontWeight: 700,
  color: "var(--muted)",
  letterSpacing: "0.05em",
  borderTop: "1px solid var(--border)",
};

const metricValue = {
  padding: "6px 10px",
  fontSize: 11,
  fontWeight: 600,
  borderTop: "1px solid var(--border)",
  textAlign: "right",
};

const thStyle = {
  textAlign: "right",
  padding: "8px 10px",
  fontSize: 9,
  fontWeight: 700,
  color: "var(--muted)",
  letterSpacing: "0.05em",
};
