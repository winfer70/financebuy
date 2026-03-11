/**
 * TradingPage.jsx — Trading AI page for TickerTap.
 *
 * Bloomberg terminal–style layout with:
 *   - Left panel: symbol search, strategy picker, parameter sliders,
 *     date range, commission/slippage, backtest controls.
 *   - Right top: OHLCVChart with signal overlays (entry/exit/stop-loss).
 *   - Right bottom: tabbed area — Metrics, Equity Curve, Trade Log, Replay.
 *
 * Data flow:
 *   1. User selects symbol + strategy → adjusts params
 *   2. "RUN BACKTEST" queues an arq job via POST /trading/backtest
 *   3. Polls GET /trading/backtest/{id} until status = completed
 *   4. Displays metrics, equity curve, signals on chart, trade log
 *
 * Props:
 *   @param {string}   token       — JWT access token
 *   @param {Function} onViewChart — Navigate to advanced chart page for a symbol
 */

import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import api, { apiFetch } from "../api/client";
import { Ic } from "../components/common/Icons";
import { OHLCVChart } from "../components/charts";
import { fmtUSD, fmtPct, fmtDate } from "../utils/formatters";
import PeriodSelector from "../components/common/PeriodSelector";
import StatBlock from "../components/common/StatBlock";
import EmptyState from "../components/common/EmptyState";

/* -- Constants ------------------------------------------------------------ */

const INTERVALS = [
  { id: "1d", label: "1D" },
  { id: "1h", label: "1H" },
  { id: "15m", label: "15M" },
  { id: "5m", label: "5M" },
];

const PERIODS = ["1M", "3M", "6M", "1Y", "2Y", "5Y", "ALL"];

const PERIOD_DAYS = {
  "1M": 30, "3M": 90, "6M": 180, "1Y": 365,
  "2Y": 730, "5Y": 1825, "ALL": 3650,
};

const BOTTOM_TABS = [
  { id: "metrics", label: "METRICS" },
  { id: "equity", label: "EQUITY CURVE" },
  { id: "trades", label: "TRADE LOG" },
  { id: "replay", label: "REPLAY" },
];

/** Disclaimer text displayed at the top of the page. */
const DISCLAIMER =
  "\u26a0 DISCLAIMER: Trading AI signals are for educational purposes only " +
  "and do not constitute financial advice. Past performance does not " +
  "guarantee future results.";

/* ========================================================================== */

export function TradingPage({ token, onViewChart }) {
  /* -- State: controls ---------------------------------------------------- */
  const [symbol, setSymbol] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [showSearch, setShowSearch] = useState(false);
  const [strategies, setStrategies] = useState([]);
  const [selectedStrategy, setSelectedStrategy] = useState(null);
  const [params, setParams] = useState({});
  const [interval, setInterval] = useState("1d");
  const [period, setPeriod] = useState("1Y");
  const [commission, setCommission] = useState(0.001);
  const [slippage, setSlippage] = useState(0.0005);

  /* -- State: position sizing --------------------------------------------- */
  const [initialCapital, setInitialCapital] = useState(10000);
  const [riskModel, setRiskModel] = useState("all_in"); // all_in | fixed_pct | atr_based
  const [riskPct, setRiskPct] = useState(2.0);

  /* -- State: backtest ---------------------------------------------------- */
  const [backtestId, setBacktestId] = useState(null);
  const [backtestStatus, setBacktestStatus] = useState("idle"); // idle | queued | running | completed | failed
  const [backtestResult, setBacktestResult] = useState(null);
  const [ohlcvData, setOhlcvData] = useState([]);

  /* -- State: market regime ----------------------------------------------- */
  const [regime, setRegime] = useState(null); // { regime, confidence, volatility_percentile, trend_strength }

  /* -- State: UI ---------------------------------------------------------- */
  const [bottomTab, setBottomTab] = useState("metrics");
  const [replayIdx, setReplayIdx] = useState(-1);
  const [replayPlaying, setReplayPlaying] = useState(false);
  const [replaySpeed, setReplaySpeed] = useState(1);
  const replayTimer = useRef(null);
  const searchTimeoutRef = useRef(null);

  /* -- Load strategies on mount ------------------------------------------- */
  useEffect(() => {
    (async () => {
      try {
        const res = await apiFetch("/trading/strategies/registry");
        setStrategies(res || []);
      } catch { /* swallow — strategies list will be empty */ }
    })();
  }, []);

  /* -- Symbol search (debounced) ------------------------------------------ */
  useEffect(() => {
    if (!searchQuery || searchQuery.length < 1) {
      setSearchResults([]);
      return;
    }
    clearTimeout(searchTimeoutRef.current);
    searchTimeoutRef.current = setTimeout(async () => {
      try {
        const res = await api.searchSymbols(searchQuery, token);
        setSearchResults(res || []);
        setShowSearch(true);
      } catch { setSearchResults([]); }
    }, 300);
    return () => clearTimeout(searchTimeoutRef.current);
  }, [searchQuery, token]);

  /** Select symbol from search dropdown. */
  const pickSymbol = useCallback((sym) => {
    setSymbol(sym);
    setSearchQuery(sym);
    setShowSearch(false);
    setSearchResults([]);
  }, []);

  /* -- Regime detection (fires when symbol or period changes) ------------- */
  useEffect(() => {
    if (!symbol || !token) { setRegime(null); return; }
    let alive = true;
    (async () => {
      try {
        const res = await api.detectRegime(
          { symbol, interval, period_days: PERIOD_DAYS[period] || 365 },
          token,
        );
        if (alive) setRegime(res);
      } catch { if (alive) setRegime(null); }
    })();
    return () => { alive = false; };
  }, [symbol, interval, period, token]);

  /* -- Strategy selection ------------------------------------------------- */
  const handleStrategyChange = useCallback((e) => {
    const slug = e.target.value;
    const strat = strategies.find((s) => s.slug === slug);
    setSelectedStrategy(strat || null);
    if (strat?.default_params) setParams({ ...strat.default_params });
  }, [strategies]);

  /** Update a single parameter. */
  const updateParam = useCallback((name, value) => {
    setParams((prev) => ({ ...prev, [name]: value }));
  }, []);

  /* -- Run Backtest ------------------------------------------------------- */
  const runBacktest = useCallback(async () => {
    if (!symbol || !selectedStrategy) return;
    setBacktestStatus("queued");
    setBacktestResult(null);
    try {
      const end = new Date();
      const start = new Date();
      start.setDate(start.getDate() - (PERIOD_DAYS[period] || 365));

      const body = {
        strategy_slug: selectedStrategy.slug,
        symbol,
        interval,
        start_date: start.toISOString().slice(0, 10),
        end_date: end.toISOString().slice(0, 10),
        params,
        initial_capital: initialCapital,
        commission_pct: commission,
        slippage_pct: slippage,
        risk_model: riskModel,
        risk_pct: riskPct / 100,
      };

      const res = await apiFetch("/trading/backtest", {
        method: "POST",
        body,
        token,
      });
      setBacktestId(res.result_id);
    } catch (err) {
      setBacktestStatus("failed");
    }
  }, [symbol, selectedStrategy, interval, period, params, commission, slippage, token, initialCapital, riskModel, riskPct]);

  /* -- Poll backtest status ----------------------------------------------- */
  useEffect(() => {
    if (!backtestId || backtestStatus === "completed" || backtestStatus === "failed") return;
    let alive = true;
    const poll = async () => {
      while (alive) {
        try {
          const res = await apiFetch(`/trading/backtest/${backtestId}`, { token });
          if (!alive) break;
          if (res.status === "completed") {
            setBacktestResult(res);
            setBacktestStatus("completed");
            // Load OHLCV data for the chart
            try {
              const bars = await api.getOhlcv(symbol, token, 2);
              setOhlcvData(
                (bars || []).map((b) => ({
                  date: b.date || b.timestamp,
                  open: b.open,
                  high: b.high,
                  low: b.low,
                  close: b.close,
                  volume: b.volume,
                })),
              );
            } catch { /* chart data optional */ }
            break;
          }
          if (res.status === "failed") {
            setBacktestStatus("failed");
            break;
          }
          setBacktestStatus(res.status || "running");
        } catch { /* retry */ }
        await new Promise((r) => setTimeout(r, 2000));
      }
    };
    poll();
    return () => { alive = false; };
  }, [backtestId, token, symbol]);

  /* -- Signal markers for the chart --------------------------------------- */
  const signalMarkers = useMemo(() => {
    if (!backtestResult?.trades || ohlcvData.length === 0) return [];
    const markers = [];
    const dateMap = {};
    ohlcvData.forEach((bar, idx) => {
      const key = typeof bar.date === "string" ? bar.date.slice(0, 10) : bar.date;
      dateMap[key] = idx;
    });

    for (const trade of backtestResult.trades) {
      const entryDate = (trade.entry_time || "").slice(0, 10);
      const exitDate = (trade.exit_time || "").slice(0, 10);
      if (dateMap[entryDate] !== undefined) {
        markers.push({
          index: dateMap[entryDate],
          type: "entry",
          label: "BUY",
          color: "#00d97e",
        });
      }
      if (dateMap[exitDate] !== undefined) {
        markers.push({
          index: dateMap[exitDate],
          type: "exit",
          label: trade.exit_reason === "stop_loss" ? "STOP" : "SELL",
          color: trade.exit_reason === "stop_loss" ? "#fbbf24" : "#f04438",
        });
      }
    }
    return markers;
  }, [backtestResult, ohlcvData]);

  /* -- Metrics helper ----------------------------------------------------- */
  const metrics = backtestResult?.metrics || {};

  /* -- Equity curve data -------------------------------------------------- */
  const equityCurve = useMemo(() => {
    if (!backtestResult?.equity_curve) return [];
    return backtestResult.equity_curve;
  }, [backtestResult]);

  /* -- Replay logic ------------------------------------------------------- */
  useEffect(() => {
    if (!replayPlaying || ohlcvData.length === 0) {
      clearInterval(replayTimer.current);
      return;
    }
    const delay = Math.max(20, 200 / replaySpeed);
    replayTimer.current = setInterval(() => {
      setReplayIdx((prev) => {
        const next = prev + 1;
        if (next >= ohlcvData.length) {
          setReplayPlaying(false);
          return prev;
        }
        return next;
      });
    }, delay);
    return () => clearInterval(replayTimer.current);
  }, [replayPlaying, replaySpeed, ohlcvData.length]);

  const replayData = useMemo(() => {
    if (replayIdx < 0 || bottomTab !== "replay") return ohlcvData;
    return ohlcvData.slice(0, replayIdx + 1);
  }, [replayIdx, bottomTab, ohlcvData]);

  const replaySignals = useMemo(() => {
    if (replayIdx < 0 || bottomTab !== "replay") return signalMarkers;
    return signalMarkers.filter((s) => s.index <= replayIdx);
  }, [replayIdx, bottomTab, signalMarkers]);

  /* ====================================================================== */
  /* -- Render ------------------------------------------------------------- */
  /* ====================================================================== */
  return (
    <div className="page-scroll">
      {/* Disclaimer banner */}
      <div
        style={{
          background: "rgba(251,191,36,0.08)",
          border: "1px solid rgba(251,191,36,0.2)",
          padding: "8px 24px",
          fontFamily: "var(--font-mono)",
          fontSize: 10,
          color: "#fbbf24",
          letterSpacing: "0.3px",
        }}
      >
        {DISCLAIMER}
      </div>

      {/* Page header */}
      <div className="page-header">
        <div>
          <div className="page-title">TRADING AI</div>
          <div className="page-sub">
            ALGORITHMIC BACKTESTING & SIGNAL GENERATION
            {symbol && ` · ${symbol}`}
            {selectedStrategy && ` · ${selectedStrategy.name}`}
          </div>
        </div>
      </div>

      <div className="page-inner">
        {/* Main layout: controls left, chart + tabs right */}
        <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>

          {/* ── Left Panel: Controls ──────────────────────────────────────── */}
          <div
            style={{
              width: 260,
              flexShrink: 0,
              display: "flex",
              flexDirection: "column",
              gap: 12,
            }}
          >
            {/* Symbol search */}
            <div className="panel" style={{ padding: 12 }}>
              <div className="panel-title" style={{ marginBottom: 8 }}>SYMBOL</div>
              <div style={{ position: "relative" }}>
                <input
                  className="form-control"
                  placeholder="Search ticker..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value.toUpperCase())}
                  onFocus={() => searchResults.length > 0 && setShowSearch(true)}
                />
                {showSearch && searchResults.length > 0 && (
                  <div
                    style={{
                      position: "absolute",
                      top: "100%",
                      left: 0,
                      right: 0,
                      zIndex: 100,
                      background: "var(--bg2)",
                      border: "1px solid var(--border)",
                      maxHeight: 200,
                      overflowY: "auto",
                    }}
                  >
                    {searchResults.slice(0, 8).map((r) => (
                      <div
                        key={r.symbol}
                        onClick={() => pickSymbol(r.symbol)}
                        style={{
                          padding: "6px 10px",
                          cursor: "pointer",
                          fontFamily: "var(--font-mono)",
                          fontSize: 11,
                          color: "var(--text)",
                          display: "flex",
                          justifyContent: "space-between",
                        }}
                        onMouseOver={(e) =>
                          (e.currentTarget.style.background = "var(--bg3)")
                        }
                        onMouseOut={(e) =>
                          (e.currentTarget.style.background = "none")
                        }
                      >
                        <span style={{ color: "var(--amber)", fontWeight: 600 }}>
                          {r.symbol}
                        </span>
                        <span style={{ color: "var(--muted)", fontSize: 9, maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis" }}>
                          {r.shortname || r.name || ""}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Strategy selector */}
            <div className="panel" style={{ padding: 12 }}>
              <div className="panel-title" style={{ marginBottom: 8 }}>STRATEGY</div>
              <select
                className="form-control"
                value={selectedStrategy?.slug || ""}
                onChange={handleStrategyChange}
              >
                <option value="">-- Select --</option>
                {strategies.map((s) => (
                  <option key={s.slug || s.strategy_id} value={s.slug}>
                    {s.name}
                  </option>
                ))}
              </select>

              {/* Dynamic parameter sliders */}
              {selectedStrategy?.param_schema &&
                selectedStrategy.param_schema.map((p) => (
                  <div key={p.name} style={{ marginTop: 10 }}>
                    <label
                      className="form-label"
                      style={{ display: "flex", justifyContent: "space-between" }}
                    >
                      <span>{p.label || p.name}</span>
                      <span style={{ color: "var(--amber)" }}>
                        {params[p.name] ?? p.default}
                      </span>
                    </label>
                    <input
                      type="range"
                      min={p.min}
                      max={p.max}
                      step={p.step}
                      value={params[p.name] ?? p.default}
                      onChange={(e) =>
                        updateParam(
                          p.name,
                          p.type === "float"
                            ? parseFloat(e.target.value)
                            : parseInt(e.target.value, 10),
                        )
                      }
                      style={{ width: "100%", accentColor: "var(--amber)" }}
                    />
                  </div>
                ))}
            </div>

            {/* Interval + Period */}
            <div className="panel" style={{ padding: 12 }}>
              <div className="panel-title" style={{ marginBottom: 8 }}>TIMEFRAME</div>
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 8 }}>
                {INTERVALS.map((iv) => (
                  <button
                    key={iv.id}
                    className={`filter-btn${iv.id === interval ? " active" : ""}`}
                    style={{ padding: "4px 10px", fontSize: 9 }}
                    onClick={() => setInterval(iv.id)}
                  >
                    {iv.label}
                  </button>
                ))}
              </div>
              <PeriodSelector
                periods={PERIODS}
                value={period}
                onChange={setPeriod}
              />
            </div>

            {/* Commission + Slippage */}
            <div className="panel" style={{ padding: 12 }}>
              <div className="panel-title" style={{ marginBottom: 8 }}>EXECUTION</div>
              <div className="form-field" style={{ marginBottom: 8 }}>
                <label className="form-label">COMMISSION %</label>
                <input
                  className="form-control"
                  type="number"
                  step="0.001"
                  value={commission}
                  onChange={(e) => setCommission(parseFloat(e.target.value) || 0)}
                />
              </div>
              <div className="form-field">
                <label className="form-label">SLIPPAGE %</label>
                <input
                  className="form-control"
                  type="number"
                  step="0.0001"
                  value={slippage}
                  onChange={(e) => setSlippage(parseFloat(e.target.value) || 0)}
                />
              </div>
            </div>

            {/* Position Sizing */}
            <div className="panel" style={{ padding: 12 }}>
              <div className="panel-title" style={{ marginBottom: 8 }}>POSITION SIZING</div>
              <div className="form-field" style={{ marginBottom: 8 }}>
                <label className="form-label">INITIAL CAPITAL</label>
                <input
                  className="form-control"
                  type="number"
                  step="1000"
                  min="1000"
                  value={initialCapital}
                  onChange={(e) => setInitialCapital(parseInt(e.target.value, 10) || 10000)}
                />
              </div>
              <div className="form-field" style={{ marginBottom: 8 }}>
                <label className="form-label">RISK MODEL</label>
                <select
                  className="form-control"
                  value={riskModel}
                  onChange={(e) => setRiskModel(e.target.value)}
                >
                  <option value="all_in">All-In (Single Position)</option>
                  <option value="fixed_pct">Fixed % Risk</option>
                  <option value="atr_based">ATR-Based</option>
                </select>
              </div>
              {riskModel !== "all_in" && (
                <div className="form-field">
                  <label className="form-label" style={{ display: "flex", justifyContent: "space-between" }}>
                    <span>RISK PER TRADE</span>
                    <span style={{ color: "var(--amber)" }}>{riskPct}%</span>
                  </label>
                  <input
                    type="range"
                    min={0.5}
                    max={10}
                    step={0.5}
                    value={riskPct}
                    onChange={(e) => setRiskPct(parseFloat(e.target.value))}
                    style={{ width: "100%", accentColor: "var(--amber)" }}
                  />
                </div>
              )}
            </div>

            {/* Run Backtest button */}
            <button
              className="btn btn-amber"
              style={{ width: "100%", justifyContent: "center", padding: "12px 0", fontSize: 12, letterSpacing: "1.5px" }}
              onClick={runBacktest}
              disabled={!symbol || !selectedStrategy || backtestStatus === "queued" || backtestStatus === "running"}
            >
              {backtestStatus === "queued" || backtestStatus === "running" ? (
                <span className="loading-pulse">RUNNING...</span>
              ) : (
                <>
                  <Ic.charts /> RUN BACKTEST
                </>
              )}
            </button>

            {/* Metrics summary (when results available) */}
            {backtestResult && (
              <div className="panel" style={{ padding: 12 }}>
                <div className="panel-title" style={{ marginBottom: 8 }}>PERFORMANCE</div>
                {[
                  { lbl: "TOTAL RETURN", val: fmtPct(metrics.total_return_pct), cls: (metrics.total_return_pct || 0) >= 0 ? "green" : "red" },
                  { lbl: "SHARPE RATIO", val: (metrics.sharpe_ratio || 0).toFixed(2), cls: "" },
                  { lbl: "MAX DRAWDOWN", val: fmtPct(-(metrics.max_drawdown_pct || 0)), cls: "red" },
                  { lbl: "WIN RATE", val: fmtPct(metrics.win_rate), cls: "" },
                  { lbl: "PROFIT FACTOR", val: (metrics.profit_factor || 0).toFixed(2), cls: "" },
                  { lbl: "TOTAL TRADES", val: metrics.total_trades || 0, cls: "" },
                  { lbl: "CALMAR RATIO", val: (metrics.calmar_ratio || 0).toFixed(2), cls: "" },
                ].map((m, i) => (
                  <div
                    key={i}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      padding: "4px 0",
                      borderBottom: "1px solid var(--border)",
                      fontFamily: "var(--font-mono)",
                      fontSize: 10,
                    }}
                  >
                    <span style={{ color: "var(--muted)", letterSpacing: "0.5px" }}>{m.lbl}</span>
                    <span className={m.cls} style={{ fontWeight: 600 }}>{m.val}</span>
                  </div>
                ))}
                {/* Overfit warning */}
                {metrics.overfit_score > 0.5 && (
                  <div
                    style={{
                      marginTop: 8,
                      padding: "4px 8px",
                      background: "rgba(251,191,36,0.08)",
                      border: "1px solid rgba(251,191,36,0.2)",
                      fontFamily: "var(--font-mono)",
                      fontSize: 9,
                      color: "#fbbf24",
                      letterSpacing: "0.3px",
                    }}
                  >
                    OVERFIT RISK: {(metrics.overfit_score * 100).toFixed(0)}%
                  </div>
                )}
              </div>
            )}
          </div>

          {/* ── Right Panel: Chart + Tabs ─────────────────────────────────── */}
          <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 1 }}>
            {/* Regime indicator strip */}
            {regime && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  padding: "6px 14px",
                  background: "var(--bg2)",
                  borderBottom: "1px solid var(--border)",
                  fontFamily: "var(--font-mono)",
                  fontSize: 10,
                }}
              >
                <span style={{ color: "var(--muted)", letterSpacing: "0.5px" }}>REGIME</span>
                <span
                  style={{
                    padding: "2px 8px",
                    borderRadius: 2,
                    fontWeight: 600,
                    letterSpacing: "0.5px",
                    fontSize: 9,
                    background:
                      regime.regime === "trending_up" ? "rgba(0,217,126,0.12)" :
                      regime.regime === "trending_down" ? "rgba(240,68,56,0.12)" :
                      regime.regime === "high_volatility" ? "rgba(251,191,36,0.12)" :
                      "rgba(100,116,139,0.12)",
                    color:
                      regime.regime === "trending_up" ? "#00d97e" :
                      regime.regime === "trending_down" ? "#f04438" :
                      regime.regime === "high_volatility" ? "#fbbf24" :
                      "#94a3b8",
                  }}
                >
                  {regime.regime.replace(/_/g, " ").toUpperCase()}
                </span>
                <span style={{ color: "var(--muted)" }}>
                  CONF {(regime.confidence * 100).toFixed(0)}%
                </span>
                <span style={{ color: "var(--muted)" }}>
                  VOL {regime.volatility_percentile.toFixed(0)}th
                </span>
                <span style={{ color: "var(--muted)" }}>
                  TREND {regime.trend_strength.toFixed(1)}
                </span>
              </div>
            )}

            {/* Chart area */}
            <div className="panel" style={{ height: 420, overflow: "hidden" }}>
              {ohlcvData.length > 0 ? (
                <OHLCVChart
                  data={bottomTab === "replay" ? replayData : ohlcvData}
                  chartType="candle"
                  showVolume
                  showCrosshair
                  signals={bottomTab === "replay" ? replaySignals : signalMarkers}
                  smaOverlays={[
                    { period: 50, color: "#3d7ef5" },
                    { period: 200, color: "#f59e0b", dashed: true },
                  ]}
                />
              ) : (
                <div
                  style={{
                    height: "100%",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexDirection: "column",
                    gap: 8,
                  }}
                >
                  <div
                    style={{
                      fontFamily: "var(--font-disp)",
                      fontSize: 24,
                      color: "var(--muted)",
                      letterSpacing: "1px",
                    }}
                  >
                    SELECT A SYMBOL & RUN BACKTEST
                  </div>
                  <div
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: 11,
                      color: "var(--muted)",
                    }}
                  >
                    Results will appear here with signal overlays
                  </div>
                </div>
              )}
            </div>

            {/* Bottom tabs */}
            <div style={{ background: "var(--bg2)", display: "flex", gap: 0, borderBottom: "1px solid var(--border)" }}>
              {BOTTOM_TABS.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setBottomTab(tab.id)}
                  style={{
                    padding: "10px 18px",
                    fontFamily: "var(--font-mono)",
                    fontSize: 10,
                    fontWeight: 500,
                    color: bottomTab === tab.id ? "var(--amber)" : "var(--muted)",
                    cursor: "pointer",
                    border: "none",
                    background: "none",
                    letterSpacing: "0.8px",
                    borderBottom: `2px solid ${bottomTab === tab.id ? "var(--amber)" : "transparent"}`,
                    marginBottom: -1,
                  }}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Tab content */}
            <div className="panel" style={{ minHeight: 220, padding: 16 }}>
              {/* METRICS tab */}
              {bottomTab === "metrics" && (
                backtestResult ? (
                  <div>
                    <div className="grid-stats stagger" style={{ marginBottom: 16 }}>
                      {[
                        { label: "TOTAL RETURN", value: fmtPct(metrics.total_return_pct), cls: (metrics.total_return_pct || 0) >= 0 ? "green" : "red" },
                        { label: "ANNUALIZED", value: fmtPct(metrics.annualized_return_pct), cls: (metrics.annualized_return_pct || 0) >= 0 ? "green" : "red" },
                        { label: "SHARPE", value: (metrics.sharpe_ratio || 0).toFixed(2), cls: "" },
                        { label: "SORTINO", value: (metrics.sortino_ratio || 0).toFixed(2), cls: "" },
                        { label: "WIN RATE", value: fmtPct(metrics.win_rate), cls: "" },
                      ].map((s, i) => (
                        <StatBlock key={i} label={s.label} value={s.value} cls={s.cls} />
                      ))}
                    </div>
                    {/* Benchmark comparison */}
                    {metrics.benchmark_return_pct != null && (
                      <div
                        style={{
                          display: "flex",
                          gap: 24,
                          fontFamily: "var(--font-mono)",
                          fontSize: 11,
                          padding: "8px 0",
                          borderTop: "1px solid var(--border)",
                        }}
                      >
                        <span>
                          <span style={{ color: "var(--muted)" }}>BUY & HOLD: </span>
                          <span className={metrics.benchmark_return_pct >= 0 ? "green" : "red"}>
                            {fmtPct(metrics.benchmark_return_pct)}
                          </span>
                        </span>
                        <span>
                          <span style={{ color: "var(--muted)" }}>STRATEGY: </span>
                          <span className={(metrics.total_return_pct || 0) >= 0 ? "green" : "red"}>
                            {fmtPct(metrics.total_return_pct)}
                          </span>
                        </span>
                        <span>
                          <span style={{ color: "var(--muted)" }}>ALPHA: </span>
                          <span className={(metrics.total_return_pct - metrics.benchmark_return_pct) >= 0 ? "green" : "red"}>
                            {fmtPct((metrics.total_return_pct || 0) - (metrics.benchmark_return_pct || 0))}
                          </span>
                        </span>
                      </div>
                    )}
                  </div>
                ) : (
                  <EmptyState message="Run a backtest to view performance metrics." />
                )
              )}

              {/* EQUITY CURVE tab */}
              {bottomTab === "equity" && (
                backtestResult?.equity_curve?.length > 0 ? (
                  <OHLCVChart
                    data={equityCurve.map((pt) => ({
                      date: pt.date || pt.timestamp,
                      open: pt.value,
                      high: pt.value,
                      low: pt.value,
                      close: pt.value,
                      volume: 0,
                    }))}
                    chartType="line"
                    showVolume={false}
                    showCrosshair
                    height={180}
                    currencySymbol="$"
                  />
                ) : (
                  <EmptyState message="Run a backtest to view the equity curve." />
                )
              )}

              {/* TRADE LOG tab */}
              {bottomTab === "trades" && (
                backtestResult?.trades?.length > 0 ? (
                  <div style={{ maxHeight: 200, overflowY: "auto" }}>
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>ENTRY</th>
                          <th>EXIT</th>
                          <th>DIR</th>
                          <th className="right">ENTRY $</th>
                          <th className="right">EXIT $</th>
                          <th className="right">P&L</th>
                          <th className="right">P&L %</th>
                          <th>REASON</th>
                        </tr>
                      </thead>
                      <tbody>
                        {backtestResult.trades.map((t, i) => {
                          const pnl = (t.exit_price - t.entry_price) * (t.direction === "long" ? 1 : -1);
                          const pnlPct = t.entry_price ? (pnl / t.entry_price) * 100 : 0;
                          return (
                            <tr key={i}>
                              <td>{fmtDate(t.entry_time)}</td>
                              <td>{fmtDate(t.exit_time)}</td>
                              <td>
                                <span className={`type-chip ${t.direction === "long" ? "tc-buy" : "tc-sell"}`}>
                                  {t.direction?.toUpperCase()}
                                </span>
                              </td>
                              <td className="right">{fmtUSD(t.entry_price)}</td>
                              <td className="right">{fmtUSD(t.exit_price)}</td>
                              <td className={`right ${pnl >= 0 ? "pnl-pos" : "pnl-neg"}`}>
                                {fmtUSD(pnl)}
                              </td>
                              <td className={`right ${pnl >= 0 ? "pnl-pos" : "pnl-neg"}`}>
                                {fmtPct(pnlPct)}
                              </td>
                              <td>
                                <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--muted)", letterSpacing: "0.3px" }}>
                                  {(t.exit_reason || "signal").toUpperCase()}
                                </span>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <EmptyState message="Run a backtest to view the trade log." />
                )
              )}

              {/* REPLAY tab */}
              {bottomTab === "replay" && (
                ohlcvData.length > 0 ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <button
                      className="btn btn-ghost"
                      onClick={() => {
                        if (replayPlaying) {
                          setReplayPlaying(false);
                        } else {
                          if (replayIdx < 0 || replayIdx >= ohlcvData.length - 1) {
                            setReplayIdx(0);
                          }
                          setReplayPlaying(true);
                        }
                      }}
                    >
                      {replayPlaying ? "PAUSE" : "PLAY"}
                    </button>
                    <button
                      className="btn btn-ghost"
                      onClick={() => { setReplayIdx(0); setReplayPlaying(false); }}
                    >
                      RESET
                    </button>
                    <div style={{ display: "flex", gap: 4 }}>
                      {[1, 2, 5, 10].map((s) => (
                        <button
                          key={s}
                          className={`filter-btn${replaySpeed === s ? " active" : ""}`}
                          style={{ padding: "3px 8px", fontSize: 9 }}
                          onClick={() => setReplaySpeed(s)}
                        >
                          {s}x
                        </button>
                      ))}
                    </div>
                    <input
                      type="range"
                      min={0}
                      max={ohlcvData.length - 1}
                      value={Math.max(0, replayIdx)}
                      onChange={(e) => setReplayIdx(parseInt(e.target.value, 10))}
                      style={{ flex: 1, accentColor: "var(--amber)" }}
                    />
                    <span
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: 10,
                        color: "var(--muted)",
                        minWidth: 80,
                        textAlign: "right",
                      }}
                    >
                      BAR {Math.max(0, replayIdx + 1)} / {ohlcvData.length}
                    </span>
                  </div>
                ) : (
                  <EmptyState message="Run a backtest first to enable replay." />
                )
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
