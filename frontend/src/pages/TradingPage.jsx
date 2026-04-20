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
 *   @param {string}   token          — JWT access token
 *   @param {Function} onViewChart    — Navigate to advanced chart page for a symbol
 *   @param {string}   [initialSymbol] — Pre-fill the symbol input (e.g. from Portfolio/Watchlist quick-launch)
 */

import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import api, { apiFetch } from "../api/client";
import { Ic } from "../components/common/Icons";
import { OHLCVChart } from "../components/charts";
import { fmtUSD, fmtPct, fmtDate } from "../utils/formatters";
import PeriodSelector from "../components/common/PeriodSelector";
import StatBlock from "../components/common/StatBlock";
import EmptyState from "../components/common/EmptyState";
import ParameterEditor from "../components/trading/ParameterEditor";
import PineScriptEditor from "../components/trading/PineScriptEditor";
import CompositionEditor from "../components/trading/CompositionEditor";
import StrategyComparison from "../components/trading/StrategyComparison";
import { PaperTradingPanel } from "../components/trading/PaperTradingPanel";

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
  { id: "compare", label: "COMPARE" },
  { id: "batch", label: "BATCH" },
  { id: "score", label: "SCORE" },
  { id: "paper", label: "PAPER" },
];

/** Disclaimer text displayed at the top of the page. */
const DISCLAIMER =
  "\u26a0 DISCLAIMER: Trading AI signals are for educational purposes only " +
  "and do not constitute financial advice. Past performance does not " +
  "guarantee future results.";

/* ========================================================================== */

export function TradingPage({ token, onViewChart, initialSymbol }) {
  /* -- Responsive: detect mobile viewport for layout changes -------------- */
  const [isMobile, setIsMobile] = useState(() => window.innerWidth <= 768);
  useEffect(() => {
    const handler = () => setIsMobile(window.innerWidth <= 768);
    window.addEventListener("resize", handler);
    return () => window.removeEventListener("resize", handler);
  }, []);

  /* -- State: controls ---------------------------------------------------- */
  const [strategyMode, setStrategyMode] = useState("builtin"); // builtin | pinescript | compose
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
  const [backtestStartTime, setBacktestStartTime] = useState(null); // epoch ms when backtest was queued
  const [elapsedSec, setElapsedSec] = useState(0); // seconds since backtest started

  /* -- State: market regime ----------------------------------------------- */
  const [regime, setRegime] = useState(null); // { regime, confidence, volatility_percentile, trend_strength }

  /* -- State: UI ---------------------------------------------------------- */
  const [bottomTab, setBottomTab] = useState("metrics");
  const [replayIdx, setReplayIdx] = useState(-1);
  const [replayPlaying, setReplayPlaying] = useState(false);
  const [replaySpeed, setReplaySpeed] = useState(1);
  const [showTooltip, setShowTooltip] = useState(false);           // strategy info tooltip on hover
  const [showStrategyDetail, setShowStrategyDetail] = useState(false); // strategy detail modal on click
  const replayTimer = useRef(null);
  const searchTimeoutRef = useRef(null);

  /* -- State: batch backtest ---------------------------------------------- */
  const [batchRunning, setBatchRunning] = useState(false);
  const [batchResults, setBatchResults] = useState([]); // { symbol, status, result_id, metrics }
  const [batchIds, setBatchIds] = useState([]);

  /* -- State: order creation ---------------------------------------------- */
  const [orderCreating, setOrderCreating] = useState(null); // index of trade being submitted

  /* -- State: portfolio score --------------------------------------------- */
  const [scoreResults, setScoreResults] = useState(null);   // portfolio score API response
  const [scoreLoading, setScoreLoading] = useState(false);  // loading indicator for score

  /* -- Pre-fill symbol from initialSymbol prop (quick-launch) ------------- */
  useEffect(() => {
    if (initialSymbol) {
      setSymbol(initialSymbol.toUpperCase());
      setSearchQuery(initialSymbol.toUpperCase());
    }
  }, [initialSymbol]);

  /* -- Load strategies (built-in + user-created, refreshable) ------------- */
  const loadStrategies = useCallback(
    /**
     * Fetches the full strategy list (built-in + user-created) and updates
     * state. Returns the resolved array so callers can chain with .then().
     * @returns {Promise<Array>} The refreshed strategy list.
     */
    () =>
      api.listStrategies(token)
        .then((res) => {
          const list = res || [];
          setStrategies(list);
          return list;
        })
        .catch(() => []),
    [token],
  );

  useEffect(() => {
    loadStrategies();
  }, [loadStrategies]);

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
    setBacktestStartTime(Date.now());
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
      setBacktestStartTime(null);
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
            setBacktestStartTime(null);
            // Load OHLCV data for the chart
            try {
              const resp = await api.getOhlcv(symbol, token, 2);
              const bars = resp.bars || resp;
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
            } catch (err) { console.error("OHLCV fetch failed:", err); }
            break;
          }
          if (res.status === "failed") {
            setBacktestStatus("failed");
            setBacktestStartTime(null);
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

  /* -- Elapsed time tracker for running backtest -------------------------- */
  useEffect(() => {
    if (!backtestStartTime) { setElapsedSec(0); return; }
    const iv = setInterval(
      () => setElapsedSec(Math.floor((Date.now() - backtestStartTime) / 1000)),
      1000,
    );
    return () => clearInterval(iv);
  }, [backtestStartTime]);

  /* -- Signal markers for the chart --------------------------------------- */
  const signalMarkers = useMemo(() => {
    if (!backtestResult?.results_json?.trades || ohlcvData.length === 0) return [];
    const markers = [];
    const dateMap = {};
    ohlcvData.forEach((bar, idx) => {
      const key = typeof bar.date === "string" ? bar.date.slice(0, 10) : bar.date;
      dateMap[key] = idx;
    });

    for (const trade of backtestResult.results_json.trades) {
      const entryDate = (trade.entry_date || "").slice(0, 10);
      const exitDate = (trade.exit_date || "").slice(0, 10);
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
  const metrics = backtestResult?.metrics_json || {};
  const benchmarkData = backtestResult?.benchmark_json || {};

  /* -- Equity curve data -------------------------------------------------- */
  const equityCurve = useMemo(() => {
    if (!backtestResult?.results_json?.equity_curve) return [];
    return backtestResult.results_json.equity_curve;
  }, [backtestResult]);

  /* -- Replay logic ------------------------------------------------------- */
  useEffect(() => {
    if (!replayPlaying || ohlcvData.length === 0) return;
    let raf;
    let last = performance.now();
    const delay = Math.max(16, 200 / replaySpeed);
    const step = (now) => {
      if (now - last >= delay) {
        last = now;
        setReplayIdx((prev) => {
          const next = prev + 1;
          if (next >= ohlcvData.length) {
            setReplayPlaying(false);
            return prev;
          }
          return next;
        });
      }
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [replayPlaying, replaySpeed, ohlcvData.length]);

  const replayData = useMemo(() => {
    if (replayIdx < 0 || bottomTab !== "replay") return ohlcvData;
    return ohlcvData.slice(0, replayIdx + 1);
  }, [replayIdx, bottomTab, ohlcvData]);

  const replaySignals = useMemo(() => {
    if (replayIdx < 0 || bottomTab !== "replay") return signalMarkers;
    return signalMarkers.filter((s) => s.index <= replayIdx);
  }, [replayIdx, bottomTab, signalMarkers]);

  /* -- Batch backtest: run strategy across a set of symbols --------------- */
  const _runBatch = useCallback(async (fetchSymbols, emptyMsg) => {
    if (!selectedStrategy || batchRunning) return;
    setBatchRunning(true);
    setBatchResults([]);
    setBatchIds([]);
    setBottomTab("batch");
    try {
      const symbols = await fetchSymbols();
      if (!symbols.length) {
        setBatchResults([{ symbol: "—", status: emptyMsg, metrics: {} }]);
        setBatchRunning(false);
        return;
      }

      const end = new Date();
      const start = new Date();
      start.setDate(start.getDate() - (PERIOD_DAYS[period] || 365));

      const body = {
        strategy_slug: selectedStrategy.slug,
        symbols: symbols.slice(0, 20),
        interval,
        start_date: start.toISOString().slice(0, 10),
        end_date: end.toISOString().slice(0, 10),
        parameters: params,
        initial_capital: initialCapital,
        commission,
        slippage,
      };

      const res = await api.queueBatchBacktest(body, token);
      const ids = res.backtest_ids || [];
      setBatchIds(ids);

      // Initialize results with queued status
      const usedSymbols = body.symbols;
      setBatchResults(usedSymbols.map((s, i) => ({
        symbol: s,
        status: "queued",
        result_id: ids[i],
        metrics: {},
      })));

      // Poll each backtest result
      const settled = new Set();
      for (let attempt = 0; attempt < 120 && settled.size < ids.length; attempt++) {
        await new Promise((r) => setTimeout(r, 2000));
        for (let i = 0; i < ids.length; i++) {
          if (settled.has(i)) continue;
          try {
            const poll = await apiFetch(`/trading/backtest/${ids[i]}`, { token });
            if (poll.status === "completed" || poll.status === "failed") {
              settled.add(i);
              setBatchResults((prev) => {
                const next = [...prev];
                next[i] = {
                  ...next[i],
                  status: poll.status,
                  metrics: poll.metrics_json || {},
                  results: poll.results_json || {},
                };
                return next;
              });
            }
          } catch { /* retry next loop */ }
        }
      }
    } catch (err) {
      setBatchResults([{ symbol: "—", status: `Error: ${err.message}`, metrics: {} }]);
    } finally {
      setBatchRunning(false);
    }
  }, [selectedStrategy, batchRunning, token, period, interval, params, initialCapital, commission, slippage]);

  /* -- Fetch watchlist symbols and run batch ------------------------------- */
  const runBatchWatchlist = useCallback(() => _runBatch(async () => {
    const lists = await api.getWatchlists(token);
    if (!lists?.length) return [];
    // Fetch items from ALL watchlists and collect symbols into a deduplicated Set
    const allSymbols = new Set();
    for (const wl of lists) {
      const detail = await api.getWatchlist(wl.watchlist_id, token);
      (detail?.items || []).forEach((it) => { if (it.symbol) allSymbols.add(it.symbol); });
    }
    return [...allSymbols];
  }, "No watchlist items found"), [_runBatch, token]);

  /* -- Fetch portfolio positions and run batch ----------------------------- */
  const runBatchPortfolio = useCallback(() => _runBatch(async () => {
    const portfolios = await api.listPortfolios(token);
    if (!portfolios?.length) return [];
    // Collect tickers from all portfolios, deduplicate
    const allTickers = new Set();
    for (const p of portfolios) {
      const positions = await api.listPositions(p.portfolio_id, token);
      (positions || []).forEach((pos) => { if (pos.ticker) allTickers.add(pos.ticker); });
    }
    return [...allTickers];
  }, "No portfolio positions found"), [_runBatch, token]);

  /* -- Portfolio scoring: fetch all symbols and score ---------------------- */
  const _runScore = useCallback(async () => {
    if (scoreLoading) return;
    setScoreLoading(true);
    setScoreResults(null);
    setBottomTab("score");
    try {
      // Combine portfolio tickers + watchlist symbols into one deduplicated list
      const allSymbols = new Set();

      // Fetch portfolio positions (same logic as runBatchPortfolio)
      try {
        const portfolios = await api.listPortfolios(token);
        if (portfolios?.length) {
          for (const p of portfolios) {
            const positions = await api.listPositions(p.portfolio_id, token);
            (positions || []).forEach((pos) => {
              if (pos.ticker) allSymbols.add(pos.ticker);
            });
          }
        }
      } catch { /* portfolio fetch failed — continue with watchlist */ }

      // Fetch watchlist symbols from ALL watchlists
      try {
        const lists = await api.getWatchlists(token);
        if (lists?.length) {
          for (const wl of lists) {
            const detail = await api.getWatchlist(wl.watchlist_id, token);
            (detail?.items || []).forEach((it) => {
              if (it.symbol) allSymbols.add(it.symbol);
            });
          }
        }
      } catch { /* watchlist fetch failed — continue with what we have */ }

      if (allSymbols.size === 0) {
        setScoreResults({ error: "No symbols found in portfolio or watchlist." });
        return;
      }

      const res = await api.scorePortfolio({ symbols: [...allSymbols] }, token);
      setScoreResults(res);
    } catch (err) {
      console.error("Score failed:", err);
      setScoreResults({ error: err.message || "Portfolio scoring failed." });
    } finally {
      setScoreLoading(false);
    }
  }, [token, scoreLoading]);

  /* -- Export backtest result as CSV --------------------------------------- */
  const handleExport = useCallback(async (format = "csv") => {
    if (!backtestResult?.result_id) return;
    try {
      const blob = await api.exportBacktest(backtestResult.result_id, format, token);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `backtest_${backtestResult.result_id.slice(0, 8)}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Export failed:", err);
    }
  }, [backtestResult, token]);

  /* -- Create order from trade log entry ---------------------------------- */
  const handleCreateOrder = useCallback(async (trade, index) => {
    setOrderCreating(index);
    try {
      await api.createOrder({
        symbol,
        side: trade.direction === "long" ? "buy" : "sell",
        order_type: "limit",
        quantity: trade.quantity || 1,
        limit_price: trade.entry_price,
      }, token);
    } catch (err) {
      console.error("Order creation failed:", err);
    } finally {
      setOrderCreating(null);
    }
  }, [symbol, token]);

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
        {/* Main layout: controls left, chart + tabs right (stacked on mobile) */}
        <div style={{ display: "flex", gap: 16, alignItems: "flex-start", flexDirection: isMobile ? "column" : "row" }}>

          {/* ── Left Panel: Controls ──────────────────────────────────────── */}
          <div
            style={{
              width: isMobile ? "100%" : 260,
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

            {/* Strategy mode selector + content */}
            <div className="panel" style={{ padding: 12 }}>
              <div className="panel-title" style={{ marginBottom: 8 }}>STRATEGY</div>

              {/* Mode selector tabs */}
              <div style={{ display: "flex", gap: 4, marginBottom: 8 }}>
                {[
                  { id: "builtin", label: "BUILT-IN" },
                  { id: "pinescript", label: "PINESCRIPT" },
                  { id: "compose", label: "COMPOSE" },
                ].map((m) => (
                  <button
                    key={m.id}
                    className={`filter-btn${strategyMode === m.id ? " active" : ""}`}
                    style={{ padding: "4px 10px", fontSize: 9 }}
                    onClick={() => setStrategyMode(m.id)}
                  >
                    {m.label}
                  </button>
                ))}
              </div>

              {/* BUILT-IN mode: strategy dropdown + ParameterEditor */}
              {strategyMode === "builtin" && (
                <>
                  {/* Strategy dropdown + info icon */}
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <select
                      className="form-control"
                      style={{ flex: 1 }}
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

                    {/* Info icon — hover for tooltip, click for detail modal */}
                    {selectedStrategy && (
                      <span
                        style={{
                          position: "relative",
                          fontSize: 14,
                          color: "var(--muted)",
                          cursor: "pointer",
                          userSelect: "none",
                          lineHeight: 1,
                          transition: "color 0.15s",
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.color = "var(--amber)";
                          setShowTooltip(true);
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.color = "var(--muted)";
                          setShowTooltip(false);
                        }}
                        onClick={() => setShowStrategyDetail(true)}
                        title="" /* suppress native tooltip */
                      >
                        &#9432; {/* ⓘ info circle */}

                        {/* Hover tooltip — strategy description */}
                        {showTooltip && selectedStrategy.description && (
                          <span style={{
                            position: "absolute",
                            top: "calc(100% + 6px)",
                            left: "50%",
                            transform: "translateX(-50%)",
                            background: "rgba(0,0,0,0.95)",
                            border: "1px solid var(--border)",
                            borderRadius: 4,
                            padding: 8,
                            maxWidth: 300,
                            minWidth: 180,
                            fontSize: 11,
                            color: "var(--fg)",
                            zIndex: 100,
                            whiteSpace: "normal",
                            lineHeight: 1.4,
                            pointerEvents: "none",
                            boxShadow: "0 4px 12px rgba(0,0,0,0.5)",
                          }}>
                            {selectedStrategy.description}
                          </span>
                        )}
                      </span>
                    )}
                  </div>

                  {/* Strategy badge */}
                  {selectedStrategy && (
                    <div style={{ marginTop: 6, display: "flex", gap: 4 }}>
                      <span style={{
                        fontSize: 8, padding: "2px 6px", borderRadius: 3,
                        background: "rgba(0,200,100,0.15)", color: "#00c864", border: "1px solid rgba(0,200,100,0.3)",
                      }}>
                        VERIFIED
                      </span>
                    </div>
                  )}

                  {/* Strategy detail modal — name, description, default params table */}
                  {showStrategyDetail && selectedStrategy && (
                    <div
                      style={{
                        position: "fixed",
                        top: 0, left: 0, right: 0, bottom: 0,
                        background: "rgba(0,0,0,0.7)",
                        zIndex: 9999,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                      }}
                      onClick={() => setShowStrategyDetail(false)} /* close on backdrop click */
                    >
                      <div
                        style={{
                          background: "var(--bg1)",
                          border: "1px solid var(--amber)",
                          borderRadius: 6,
                          maxWidth: 500,
                          width: "90%",
                          maxHeight: "80vh",
                          overflowY: "auto",
                          padding: 20,
                          position: "relative",
                        }}
                        onClick={(e) => e.stopPropagation()} /* prevent close when clicking panel */
                      >
                        {/* Close button */}
                        <button
                          onClick={() => setShowStrategyDetail(false)}
                          style={{
                            position: "absolute",
                            top: 10, right: 12,
                            background: "none",
                            border: "none",
                            color: "var(--muted)",
                            fontSize: 18,
                            cursor: "pointer",
                            lineHeight: 1,
                            padding: 0,
                          }}
                          onMouseEnter={(e) => { e.currentTarget.style.color = "var(--amber)"; }}
                          onMouseLeave={(e) => { e.currentTarget.style.color = "var(--muted)"; }}
                        >
                          &#10005; {/* X close */}
                        </button>

                        {/* Strategy name */}
                        <div style={{
                          fontSize: 14,
                          fontWeight: 700,
                          color: "var(--amber)",
                          marginBottom: 12,
                          paddingRight: 24,
                        }}>
                          {selectedStrategy.name}
                        </div>

                        {/* Full description */}
                        {selectedStrategy.description && (
                          <div style={{
                            fontSize: 12,
                            color: "var(--fg)",
                            lineHeight: 1.5,
                            marginBottom: 16,
                          }}>
                            {selectedStrategy.description}
                          </div>
                        )}

                        {/* Default parameters table */}
                        {selectedStrategy.param_schema && selectedStrategy.param_schema.length > 0 && (
                          <div>
                            <div style={{
                              fontSize: 10,
                              color: "var(--muted)",
                              textTransform: "uppercase",
                              letterSpacing: 1,
                              marginBottom: 8,
                            }}>
                              Default Parameters
                            </div>
                            <table style={{
                              width: "100%",
                              borderCollapse: "collapse",
                              fontSize: 11,
                            }}>
                              <thead>
                                <tr style={{ borderBottom: "1px solid var(--border)" }}>
                                  {["Name", "Type", "Default", "Min", "Max"].map((h) => (
                                    <th key={h} style={{
                                      textAlign: "left",
                                      padding: "6px 8px",
                                      color: "var(--muted)",
                                      fontWeight: 600,
                                      fontSize: 10,
                                    }}>
                                      {h}
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {selectedStrategy.param_schema.map((p) => (
                                  <tr key={p.name} style={{ borderBottom: "1px solid var(--border)" }}>
                                    <td style={{ padding: "5px 8px", color: "var(--fg)" }}>
                                      {p.label || p.name}
                                    </td>
                                    <td style={{ padding: "5px 8px", color: "var(--muted)" }}>
                                      {p.type}
                                    </td>
                                    <td style={{ padding: "5px 8px", color: "var(--amber)" }}>
                                      {p.default != null ? String(p.default) : "\u2014"}
                                    </td>
                                    <td style={{ padding: "5px 8px", color: "var(--muted)" }}>
                                      {p.min != null ? String(p.min) : "\u2014"}
                                    </td>
                                    <td style={{ padding: "5px 8px", color: "var(--muted)" }}>
                                      {p.max != null ? String(p.max) : "\u2014"}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Parameter sliders */}
                  {selectedStrategy?.param_schema && (
                    <ParameterEditor
                      paramSchema={selectedStrategy.param_schema}
                      params={params}
                      onChange={updateParam}
                      onReset={() => {
                        if (selectedStrategy?.default_params) setParams({ ...selectedStrategy.default_params });
                      }}
                    />
                  )}
                </>
              )}
            </div>

            {/* PINESCRIPT mode: PineScriptEditor below strategy panel */}
            {strategyMode === "pinescript" && (
              <PineScriptEditor
                token={token}
                onTranspiled={(def, sid) => {
                  // Refresh strategy list, then auto-select the transpiled strategy
                  // and return to the standard selector view.
                  loadStrategies().then((list) => {
                    const strat = (list || []).find((s) => s.strategy_id === sid);
                    if (strat) setSelectedStrategy(strat);
                    setStrategyMode("standard");
                  });
                }}
              />
            )}

            {/* COMPOSE mode: CompositionEditor */}
            {strategyMode === "compose" && (
              <CompositionEditor
                token={token}
                onCreated={(sid) => {
                  // Refresh strategy list, then auto-select the composed strategy
                  // and return to the standard selector view.
                  loadStrategies().then((list) => {
                    const strat = (list || []).find((s) => s.strategy_id === sid);
                    if (strat) setSelectedStrategy(strat);
                    setStrategyMode("standard");
                  });
                }}
              />
            )}

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
            <div style={{ position: "relative" }}>
              {/* Inline keyframes for spinner + progress bar animations */}
              <style>{`
                @keyframes tt-spin { to { transform: rotate(360deg); } }
                @keyframes tt-indeterminate {
                  0%   { left: -40%; width: 40%; }
                  50%  { left: 30%;  width: 50%; }
                  100% { left: 100%; width: 40%; }
                }
              `}</style>
              <button
                className="btn btn-amber"
                style={{
                  width: "100%",
                  justifyContent: "center",
                  padding: "12px 0",
                  fontSize: 12,
                  letterSpacing: "1.5px",
                  position: "relative",
                  overflow: "hidden",
                }}
                onClick={runBacktest}
                disabled={!symbol || !selectedStrategy || backtestStatus === "queued" || backtestStatus === "running"}
              >
                {backtestStatus === "queued" ? (
                  /* Queuing state: spinner + QUEUING label */
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                    <svg width="14" height="14" viewBox="0 0 14 14" style={{ animation: "tt-spin 0.8s linear infinite" }}>
                      <circle cx="7" cy="7" r="5.5" fill="none" stroke="var(--amber)" strokeWidth="2"
                        strokeDasharray="20 14" strokeLinecap="round" />
                    </svg>
                    QUEUING...
                  </span>
                ) : backtestStatus === "running" ? (
                  /* Running state: spinner + RUNNING + elapsed seconds */
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                    <svg width="14" height="14" viewBox="0 0 14 14" style={{ animation: "tt-spin 0.8s linear infinite" }}>
                      <circle cx="7" cy="7" r="5.5" fill="none" stroke="var(--amber)" strokeWidth="2"
                        strokeDasharray="20 14" strokeLinecap="round" />
                    </svg>
                    RUNNING
                    <span style={{
                      fontFamily: "'IBM Plex Mono', monospace",
                      fontSize: 10,
                      color: "var(--amber)",
                      minWidth: 28,
                      textAlign: "right",
                    }}>
                      {elapsedSec}s
                    </span>
                  </span>
                ) : (
                  <>
                    <Ic.charts /> RUN BACKTEST
                  </>
                )}

                {/* Indeterminate progress bar — visible only while queued/running */}
                {(backtestStatus === "queued" || backtestStatus === "running") && (
                  <span style={{
                    position: "absolute",
                    bottom: 0,
                    left: 0,
                    width: "100%",
                    height: 2,
                    overflow: "hidden",
                    pointerEvents: "none",
                  }}>
                    <span style={{
                      position: "absolute",
                      height: "100%",
                      background: "var(--amber)",
                      borderRadius: 1,
                      animation: "tt-indeterminate 1.4s ease-in-out infinite",
                    }} />
                  </span>
                )}
              </button>
            </div>

            {/* Batch + Export row */}
            <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
              <button
                className="btn btn-outline"
                style={{ flex: 1, justifyContent: "center", fontSize: 9, padding: "6px 0", letterSpacing: "0.8px" }}
                disabled={!selectedStrategy || batchRunning}
                onClick={runBatchWatchlist}
              >
                {batchRunning ? "RUNNING..." : "WATCHLIST"}
              </button>
              <button
                className="btn btn-outline"
                style={{ flex: 1, justifyContent: "center", fontSize: 9, padding: "6px 0", letterSpacing: "0.8px" }}
                disabled={!selectedStrategy || batchRunning}
                onClick={runBatchPortfolio}
              >
                {batchRunning ? "RUNNING..." : "PORTFOLIO"}
              </button>
              {backtestResult && (
                <button
                  className="btn btn-outline"
                  style={{ fontSize: 9, padding: "6px 10px", letterSpacing: "0.8px" }}
                  onClick={() => handleExport("csv")}
                >
                  EXPORT CSV
                </button>
              )}
            </div>

            {/* Score portfolio row */}
            <div style={{ marginTop: 6 }}>
              <button
                className="btn btn-outline"
                style={{
                  width: "100%",
                  justifyContent: "center",
                  fontSize: 9,
                  padding: "6px 0",
                  letterSpacing: "0.8px",
                  color: scoreLoading ? "var(--amber)" : undefined,
                }}
                disabled={scoreLoading}
                onClick={_runScore}
              >
                {scoreLoading ? "SCORING..." : "SCORE PORTFOLIO"}
              </button>
            </div>

            {/* Metrics summary (when results available) */}
            {backtestResult && (
              <div className="panel" style={{ padding: 12 }}>
                <div className="panel-title" style={{ marginBottom: 8 }}>PERFORMANCE</div>
                {[
                  { lbl: "TOTAL RETURN", val: fmtPct(metrics.total_return), cls: (metrics.total_return || 0) >= 0 ? "green" : "red" },
                  { lbl: "SHARPE RATIO", val: (metrics.sharpe_ratio || 0).toFixed(2), cls: "" },
                  { lbl: "MAX DRAWDOWN", val: fmtPct(-(metrics.max_drawdown || 0)), cls: "red" },
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
                {metrics.overfit_warning && (
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
                    OVERFIT RISK DETECTED
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
            <div className="panel" style={{ height: isMobile ? 300 : 520, overflow: "hidden" }}>
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
                  enableZoom
                  enableDrawingTools
                  enableControls
                  showStatsBar
                  symbol={symbol}
                  chartId="tradingMain"
                />
              ) : batchResults.some((r) => r.status === "completed" && r.metrics.total_return != null) ? (
                /* Batch returns bar chart — fills the main chart area */
                (() => {
                  const completed = batchResults
                    .filter((r) => r.status === "completed" && r.metrics.total_return != null)
                    .sort((a, b) => b.metrics.total_return - a.metrics.total_return);
                  const maxAbs = Math.max(...completed.map((r) => Math.abs(r.metrics.total_return)), 1);
                  const barH = Math.max(16, Math.min(32, Math.floor(460 / completed.length) - 6));
                  const chartH = completed.length * (barH + 6) + 40;
                  const labelW = 70;
                  const valueW = 80;
                  const barArea = 500;
                  const svgW = labelW + barArea + valueW + 10;
                  return (
                    <div style={{ height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", overflowY: "auto" }}>
                      <div style={{ fontFamily: "var(--font-disp)", fontSize: 14, color: "var(--muted)", letterSpacing: "1px", marginBottom: 12 }}>
                        BATCH RETURNS — {selectedStrategy?.name || "Strategy"} · {completed.length} SYMBOLS
                      </div>
                      <svg width={svgW} height={chartH} style={{ display: "block" }}>
                        {/* Zero line */}
                        <line x1={labelW + barArea / 2} y1={10} x2={labelW + barArea / 2} y2={chartH - 10} stroke="var(--border)" strokeWidth={1} />
                        <text x={labelW + barArea / 2} y={chartH - 1} textAnchor="middle" fill="var(--muted)" fontSize={9} fontFamily="monospace">0%</text>
                        {completed.map((r, i) => {
                          const val = r.metrics.total_return;
                          const pct = val / maxAbs;
                          const w = Math.abs(pct) * (barArea / 2 - 8);
                          const y = i * (barH + 6) + 14;
                          const x = val >= 0 ? labelW + barArea / 2 : labelW + barArea / 2 - w;
                          const fill = val >= 0 ? "#00d97e" : "#f04438";
                          return (
                            <g key={i}>
                              <text x={labelW - 6} y={y + barH / 2 + 4} textAnchor="end" fill="var(--amber)" fontSize={10} fontWeight="600" fontFamily="monospace">{r.symbol}</text>
                              <rect x={x} y={y} width={Math.max(w, 2)} height={barH} rx={3} fill={fill} opacity={0.8} />
                              <text x={labelW + barArea + 6} y={y + barH / 2 + 4} fill={fill} fontSize={10} fontWeight="600" fontFamily="monospace">{val >= 0 ? "+" : ""}{val.toFixed(1)}%</text>
                            </g>
                          );
                        })}
                      </svg>
                    </div>
                  );
                })()
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
                    {batchRunning ? "RUNNING BATCH BACKTEST..." : "SELECT A SYMBOL & RUN BACKTEST"}
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
                        { label: "TOTAL RETURN", value: fmtPct(metrics.total_return), cls: (metrics.total_return || 0) >= 0 ? "green" : "red" },
                        { label: "ANNUALIZED", value: fmtPct(metrics.annualized_return), cls: (metrics.annualized_return || 0) >= 0 ? "green" : "red" },
                        { label: "SHARPE", value: (metrics.sharpe_ratio || 0).toFixed(2), cls: "" },
                        { label: "SORTINO", value: (metrics.sortino_ratio || 0).toFixed(2), cls: "" },
                        { label: "WIN RATE", value: fmtPct(metrics.win_rate), cls: "" },
                      ].map((s, i) => (
                        <StatBlock key={i} label={s.label} value={s.value} cls={s.cls} />
                      ))}
                    </div>
                    {/* Benchmark comparison */}
                    {benchmarkData.buy_hold_return != null && (
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
                          <span className={benchmarkData.buy_hold_return >= 0 ? "green" : "red"}>
                            {fmtPct(benchmarkData.buy_hold_return)}
                          </span>
                        </span>
                        <span>
                          <span style={{ color: "var(--muted)" }}>STRATEGY: </span>
                          <span className={(metrics.total_return || 0) >= 0 ? "green" : "red"}>
                            {fmtPct(metrics.total_return)}
                          </span>
                        </span>
                        <span>
                          <span style={{ color: "var(--muted)" }}>ALPHA: </span>
                          <span className={((metrics.total_return || 0) - benchmarkData.buy_hold_return) >= 0 ? "green" : "red"}>
                            {fmtPct((metrics.total_return || 0) - (benchmarkData.buy_hold_return || 0))}
                          </span>
                        </span>
                      </div>
                    )}
                  </div>
                ) : batchResults.some((r) => r.status === "completed") ? (
                  /* Batch aggregate metrics */
                  (() => {
                    const done = batchResults.filter((r) => r.status === "completed" && r.metrics.total_return != null);
                    const avg = (key) => done.reduce((s, r) => s + (r.metrics[key] || 0), 0) / (done.length || 1);
                    const best = done.reduce((b, r) => (r.metrics.total_return || 0) > (b.metrics.total_return || 0) ? r : b, done[0]);
                    const worst = done.reduce((w, r) => (r.metrics.total_return || 0) < (w.metrics.total_return || 0) ? r : w, done[0]);
                    return (
                      <div>
                        <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)", marginBottom: 12, letterSpacing: "0.8px" }}>
                          BATCH SUMMARY — {done.length} SYMBOLS
                        </div>
                        <div className="grid-stats stagger" style={{ marginBottom: 16 }}>
                          {[
                            { label: "AVG RETURN", value: fmtPct(avg("total_return")), cls: avg("total_return") >= 0 ? "green" : "red" },
                            { label: "AVG SHARPE", value: avg("sharpe_ratio").toFixed(2), cls: "" },
                            { label: "AVG WIN RATE", value: fmtPct(avg("win_rate")), cls: "" },
                            { label: "BEST", value: `${best?.symbol} ${fmtPct(best?.metrics.total_return)}`, cls: "green" },
                            { label: "WORST", value: `${worst?.symbol} ${fmtPct(worst?.metrics.total_return)}`, cls: "red" },
                          ].map((s, i) => (
                            <StatBlock key={i} label={s.label} value={s.value} cls={s.cls} />
                          ))}
                        </div>
                      </div>
                    );
                  })()
                ) : (
                  <EmptyState message="Run a backtest to view performance metrics." />
                )
              )}

              {/* EQUITY CURVE tab */}
              {bottomTab === "equity" && (
                backtestResult?.results_json?.equity_curve?.length > 0 ? (
                  <OHLCVChart
                    data={equityCurve.map((pt) => ({
                      date: pt.date || pt.timestamp,
                      open: pt.equity,
                      high: pt.equity,
                      low: pt.equity,
                      close: pt.equity,
                      volume: 0,
                    }))}
                    chartType="line"
                    showVolume={false}
                    showCrosshair
                    height={180}
                    currencySymbol="$"
                    chartId="tradingEquity"
                  />
                ) : batchResults.some((r) => r.status === "completed" && r.results?.equity_curve?.length > 0) ? (
                  /* Overlaid batch equity curves as normalized % returns */
                  (() => {
                    const COLORS = ["#00d97e", "#3d7ef5", "#f59e0b", "#f04438", "#a855f7", "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#6366f1",
                      "#14b8a6", "#e879f9", "#facc15", "#22d3ee", "#fb923c", "#818cf8", "#4ade80", "#f472b6", "#38bdf8", "#a3e635"];
                    const series = batchResults
                      .filter((r) => r.status === "completed" && r.results?.equity_curve?.length > 1)
                      .map((r, i) => {
                        const curve = r.results.equity_curve;
                        const base = curve[0]?.equity || 1;
                        return { symbol: r.symbol, color: COLORS[i % COLORS.length], points: curve.map((pt) => ((pt.equity / base) - 1) * 100) };
                      });
                    if (!series.length) return <EmptyState message="No equity data available." />;
                    const allPts = series.flatMap((s) => s.points);
                    const minY = Math.min(...allPts, 0);
                    const maxY = Math.max(...allPts, 0);
                    const rangeY = maxY - minY || 1;
                    const W = 700, H = 170, PAD = { t: 10, b: 22, l: 50, r: 10 };
                    const plotW = W - PAD.l - PAD.r, plotH = H - PAD.t - PAD.b;
                    const toX = (i, len) => PAD.l + (i / (len - 1)) * plotW;
                    const toY = (v) => PAD.t + plotH - ((v - minY) / rangeY) * plotH;
                    return (
                      <div style={{ overflowX: "auto" }}>
                        <svg width={W} height={H} style={{ display: "block" }}>
                          {/* Zero line */}
                          <line x1={PAD.l} y1={toY(0)} x2={W - PAD.r} y2={toY(0)} stroke="var(--border)" strokeWidth={1} strokeDasharray="4,3" />
                          <text x={PAD.l - 4} y={toY(0) + 3} textAnchor="end" fill="var(--muted)" fontSize={8} fontFamily="monospace">0%</text>
                          <text x={PAD.l - 4} y={toY(maxY) + 3} textAnchor="end" fill="var(--muted)" fontSize={8} fontFamily="monospace">{maxY.toFixed(0)}%</text>
                          <text x={PAD.l - 4} y={toY(minY) + 3} textAnchor="end" fill="var(--muted)" fontSize={8} fontFamily="monospace">{minY.toFixed(0)}%</text>
                          {/* Equity lines */}
                          {series.map((s) => (
                            <polyline
                              key={s.symbol}
                              fill="none"
                              stroke={s.color}
                              strokeWidth={1.5}
                              opacity={0.85}
                              points={s.points.map((v, i) => `${toX(i, s.points.length)},${toY(v)}`).join(" ")}
                            />
                          ))}
                        </svg>
                        {/* Legend */}
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 12px", padding: "4px 0 0 50px" }}>
                          {series.map((s) => (
                            <span key={s.symbol} style={{ fontSize: 9, fontFamily: "var(--font-mono)", display: "flex", alignItems: "center", gap: 4 }}>
                              <span style={{ width: 10, height: 3, background: s.color, borderRadius: 1, display: "inline-block" }} />
                              {s.symbol}
                            </span>
                          ))}
                        </div>
                      </div>
                    );
                  })()
                ) : (
                  <EmptyState message="Run a backtest to view the equity curve." />
                )
              )}

              {/* TRADE LOG tab */}
              {bottomTab === "trades" && (
                backtestResult?.results_json?.trades?.length > 0 ? (
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
                          <th className="right">BARS</th>
                          <th className="right">ORDER</th>
                        </tr>
                      </thead>
                      <tbody>
                        {backtestResult.results_json.trades.map((t, i) => {
                          const pnl = (t.exit_price - t.entry_price) * (t.direction === "long" ? 1 : -1);
                          const pnlPct = t.entry_price ? (pnl / t.entry_price) * 100 : 0;
                          return (
                            <tr key={i}>
                              <td>{fmtDate(t.entry_date)}</td>
                              <td>{fmtDate(t.exit_date)}</td>
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
                              <td className="right">
                                <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--muted)", letterSpacing: "0.3px" }}>
                                  {t.bars_held || "—"}
                                </span>
                              </td>
                              <td className="right">
                                <button
                                  className="btn btn-outline"
                                  style={{ padding: "2px 6px", fontSize: 8, letterSpacing: "0.3px" }}
                                  disabled={orderCreating === i}
                                  onClick={(e) => { e.stopPropagation(); handleCreateOrder(t, i); }}
                                >
                                  {orderCreating === i ? "..." : "ORDER"}
                                </button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : batchResults.some((r) => r.status === "completed" && r.results?.trades?.length > 0) ? (
                  /* Combined batch trade log */
                  <div style={{ maxHeight: 200, overflowY: "auto" }}>
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>SYMBOL</th>
                          <th>ENTRY</th>
                          <th>EXIT</th>
                          <th>DIR</th>
                          <th className="right">ENTRY $</th>
                          <th className="right">EXIT $</th>
                          <th className="right">P&L %</th>
                          <th className="right">BARS</th>
                        </tr>
                      </thead>
                      <tbody>
                        {batchResults
                          .filter((r) => r.status === "completed" && r.results?.trades?.length > 0)
                          .flatMap((r) => r.results.trades.map((t) => ({ ...t, _symbol: r.symbol })))
                          .map((t, i) => {
                            const pnl = (t.exit_price - t.entry_price) * (t.direction === "long" ? 1 : -1);
                            const pnlPct = t.entry_price ? (pnl / t.entry_price) * 100 : 0;
                            return (
                              <tr key={i}>
                                <td style={{ color: "var(--amber)", fontWeight: 600 }}>{t._symbol}</td>
                                <td>{fmtDate(t.entry_date)}</td>
                                <td>{fmtDate(t.exit_date)}</td>
                                <td>
                                  <span className={`type-chip ${t.direction === "long" ? "tc-buy" : "tc-sell"}`}>
                                    {t.direction?.toUpperCase()}
                                  </span>
                                </td>
                                <td className="right">{fmtUSD(t.entry_price)}</td>
                                <td className="right">{fmtUSD(t.exit_price)}</td>
                                <td className={`right ${pnl >= 0 ? "pnl-pos" : "pnl-neg"}`}>{fmtPct(pnlPct)}</td>
                                <td className="right" style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--muted)" }}>{t.bars_held || "—"}</td>
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
                  <EmptyState message={batchResults.length > 0 ? "Replay requires a single-symbol backtest. Select a symbol above and run a backtest." : "Run a backtest first to enable replay."} />
                )
              )}

              {/* COMPARE tab */}
              {bottomTab === "compare" && (
                <StrategyComparison
                  token={token}
                  symbol={symbol}
                  interval={interval}
                  period={period}
                />
              )}

              {/* BATCH tab */}
              {bottomTab === "batch" && (
                batchResults.length > 0 ? (
                  <div style={{ display: "flex", gap: 12, maxHeight: 250, overflow: "hidden" }}>
                    {/* Returns bar chart */}
                    {(() => {
                      const completed = batchResults.filter((r) => r.status === "completed" && r.metrics.total_return != null);
                      if (!completed.length) return null;
                      const maxAbs = Math.max(...completed.map((r) => Math.abs(r.metrics.total_return)), 1);
                      const barH = Math.max(12, Math.min(20, Math.floor(220 / completed.length) - 4));
                      const chartH = completed.length * (barH + 4) + 20;
                      const labelW = 52;
                      const valueW = 60;
                      const barArea = 200;
                      const svgW = labelW + barArea + valueW + 10;
                      return (
                        <div style={{ minWidth: svgW, overflowY: "auto", flexShrink: 0 }}>
                          <svg width={svgW} height={chartH} style={{ display: "block" }}>
                            {/* Zero line */}
                            <line x1={labelW + barArea / 2} y1={0} x2={labelW + barArea / 2} y2={chartH} stroke="var(--border)" strokeWidth={1} strokeDasharray="3,3" />
                            {completed.map((r, i) => {
                              const val = r.metrics.total_return;
                              const pct = val / maxAbs;
                              const w = Math.abs(pct) * (barArea / 2 - 4);
                              const y = i * (barH + 4) + 2;
                              const x = val >= 0 ? labelW + barArea / 2 : labelW + barArea / 2 - w;
                              const fill = val >= 0 ? "#00d97e" : "#f04438";
                              return (
                                <g key={i}>
                                  <text x={labelW - 4} y={y + barH / 2 + 4} textAnchor="end" fill="var(--amber)" fontSize={9} fontFamily="monospace">{r.symbol}</text>
                                  <rect x={x} y={y} width={Math.max(w, 1)} height={barH} rx={2} fill={fill} opacity={0.75} />
                                  <text x={labelW + barArea + 4} y={y + barH / 2 + 4} fill={fill} fontSize={9} fontFamily="monospace">{val >= 0 ? "+" : ""}{val.toFixed(1)}%</text>
                                </g>
                              );
                            })}
                          </svg>
                        </div>
                      );
                    })()}
                    {/* Results table */}
                    <div style={{ flex: 1, overflowY: "auto" }}>
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>SYMBOL</th>
                            <th>STATUS</th>
                            <th className="right">RETURN</th>
                            <th className="right">SHARPE</th>
                            <th className="right">WIN RATE</th>
                            <th className="right">DRAWDOWN</th>
                            <th className="right">TRADES</th>
                          </tr>
                        </thead>
                        <tbody>
                          {batchResults.map((r, i) => (
                            <tr key={i}>
                              <td style={{ color: "var(--amber)", fontWeight: 600 }}>{r.symbol}</td>
                              <td>
                                <span style={{
                                  fontSize: 9,
                                  padding: "2px 6px",
                                  borderRadius: 2,
                                  background: r.status === "completed" ? "rgba(0,217,126,0.1)" : r.status === "failed" ? "rgba(240,68,56,0.1)" : "rgba(251,191,36,0.1)",
                                  color: r.status === "completed" ? "#00d97e" : r.status === "failed" ? "#f04438" : "#fbbf24",
                                }}>
                                  {r.status.toUpperCase()}
                                </span>
                              </td>
                              <td className={`right ${(r.metrics.total_return || 0) >= 0 ? "pnl-pos" : "pnl-neg"}`}>
                                {r.metrics.total_return != null ? fmtPct(r.metrics.total_return) : "—"}
                              </td>
                              <td className="right">{r.metrics.sharpe_ratio != null ? r.metrics.sharpe_ratio.toFixed(2) : "—"}</td>
                              <td className="right">{r.metrics.win_rate != null ? fmtPct(r.metrics.win_rate) : "—"}</td>
                              <td className="right pnl-neg">{r.metrics.max_drawdown != null ? fmtPct(-r.metrics.max_drawdown) : "—"}</td>
                              <td className="right">{r.metrics.total_trades ?? "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : (
                  <EmptyState message="Click WATCHLIST or PORTFOLIO to batch-backtest across multiple symbols." />
                )
              )}

              {/* SCORE tab */}
              {bottomTab === "score" && (
                scoreLoading ? (
                  <div style={{ padding: 24, textAlign: "center" }}>
                    <div style={{
                      color: "var(--amber)",
                      fontSize: 13,
                      letterSpacing: "0.5px",
                      marginBottom: 8,
                    }}>
                      SCORING PORTFOLIO...
                    </div>
                    <div style={{
                      width: 120,
                      height: 2,
                      margin: "0 auto",
                      background: "var(--border)",
                      borderRadius: 1,
                      overflow: "hidden",
                    }}>
                      <div style={{
                        width: "40%",
                        height: "100%",
                        background: "var(--amber)",
                        borderRadius: 1,
                        animation: "tt-indeterminate 1.4s ease-in-out infinite",
                      }} />
                    </div>
                  </div>
                ) : scoreResults && !scoreResults.error ? (
                  <div style={{ padding: 12, overflow: "auto", maxHeight: 420 }}>
                    {/* Overall score header */}
                    <div style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "10px 14px",
                      marginBottom: 12,
                      background: "var(--bg)",
                      border: "1px solid var(--border)",
                      borderRadius: 4,
                    }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                        <span style={{
                          fontSize: 11,
                          color: "var(--muted)",
                          textTransform: "uppercase",
                          letterSpacing: "0.8px",
                        }}>
                          Portfolio Score
                        </span>
                        <span style={{
                          fontSize: 28,
                          fontWeight: 700,
                          color: (scoreResults.overall_score ?? 0) >= 70
                            ? "var(--green)"
                            : (scoreResults.overall_score ?? 0) >= 40
                              ? "var(--amber)"
                              : "var(--red)",
                        }}>
                          {scoreResults.overall_score ?? "—"}
                          <span style={{ fontSize: 14, color: "var(--muted)", fontWeight: 400 }}>/100</span>
                        </span>
                      </div>
                      {(scoreResults.top_suggestion || scoreResults.suggestion) && (
                        <div style={{
                          fontSize: 11,
                          color: "var(--muted)",
                          maxWidth: 320,
                          textAlign: "right",
                          lineHeight: 1.4,
                        }}>
                          {scoreResults.top_suggestion || scoreResults.suggestion}
                        </div>
                      )}
                    </div>

                    {/* Per-symbol table */}
                    {(scoreResults.positions || scoreResults.symbols)?.length > 0 && (
                      <div style={{ overflowX: "auto" }}>
                        <table className="data-table" style={{
                          width: "100%",
                          borderCollapse: "collapse",
                          fontSize: 11,
                        }}>
                          <thead>
                            <tr style={{ borderBottom: "1px solid var(--border)" }}>
                              {["SYMBOL", "PRICE", "TREND", "RSI", "VOL", "SIGNAL", "SCORE"].map((h) => (
                                <th key={h} style={{
                                  textAlign: h === "SYMBOL" ? "left" : "right",
                                  padding: "8px 10px",
                                  color: "var(--muted)",
                                  fontWeight: 600,
                                  fontSize: 10,
                                  letterSpacing: "0.5px",
                                  whiteSpace: "nowrap",
                                }}>
                                  {h}
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {(scoreResults.positions || scoreResults.symbols).map((s, idx) => {
                              /* Trend badge color */
                              const trendColor = (s.trend || "").toLowerCase().includes("bull")
                                ? "var(--green)"
                                : (s.trend || "").toLowerCase().includes("bear")
                                  ? "var(--red)"
                                  : "var(--amber)";
                              const trendIcon = (s.trend || "").toLowerCase().includes("bull")
                                ? "\ud83d\udfe2"
                                : (s.trend || "").toLowerCase().includes("bear")
                                  ? "\ud83d\udd34"
                                  : "\ud83d\udfe1";

                              /* Signal badge color */
                              const signalUpper = (s.signal || "").toUpperCase();
                              const signalColor = signalUpper === "BUY"
                                ? "var(--green)"
                                : signalUpper === "SELL"
                                  ? "var(--red)"
                                  : "var(--amber)";

                              /* Score bar color */
                              const scoreVal = s.score ?? 0;
                              const scoreColor = scoreVal >= 70
                                ? "var(--green)"
                                : scoreVal >= 40
                                  ? "var(--amber)"
                                  : "var(--red)";

                              return (
                                <tr key={s.symbol || idx} style={{
                                  borderBottom: "1px solid var(--border)",
                                }}>
                                  {/* Symbol */}
                                  <td style={{
                                    padding: "7px 10px",
                                    fontWeight: 600,
                                    color: "var(--fg)",
                                    textAlign: "left",
                                  }}>
                                    {s.symbol}
                                  </td>

                                  {/* Price */}
                                  <td style={{
                                    padding: "7px 10px",
                                    textAlign: "right",
                                    color: "var(--fg)",
                                    fontVariantNumeric: "tabular-nums",
                                  }}>
                                    {s.price != null ? fmtUSD(s.price) : "—"}
                                  </td>

                                  {/* Trend */}
                                  <td style={{
                                    padding: "7px 10px",
                                    textAlign: "right",
                                  }}>
                                    <span style={{
                                      display: "inline-block",
                                      padding: "2px 8px",
                                      borderRadius: 3,
                                      fontSize: 10,
                                      fontWeight: 600,
                                      color: trendColor,
                                      background: `color-mix(in srgb, ${trendColor} 12%, transparent)`,
                                      letterSpacing: "0.3px",
                                    }}>
                                      {trendIcon} {(s.trend || "N/A").toUpperCase()}
                                    </span>
                                  </td>

                                  {/* RSI */}
                                  <td style={{
                                    padding: "7px 10px",
                                    textAlign: "right",
                                    color: "var(--fg)",
                                    fontVariantNumeric: "tabular-nums",
                                  }}>
                                    {s.rsi != null ? Math.round(s.rsi) : "—"}
                                  </td>

                                  {/* Volatility */}
                                  <td style={{
                                    padding: "7px 10px",
                                    textAlign: "right",
                                    color: "var(--fg)",
                                    fontVariantNumeric: "tabular-nums",
                                  }}>
                                    {s.volatility != null ? `${(s.volatility * 100).toFixed(1)}%` : "—"}
                                  </td>

                                  {/* Signal */}
                                  <td style={{
                                    padding: "7px 10px",
                                    textAlign: "right",
                                  }}>
                                    <span style={{
                                      display: "inline-block",
                                      padding: "2px 8px",
                                      borderRadius: 3,
                                      fontSize: 10,
                                      fontWeight: 600,
                                      color: signalColor,
                                      background: `color-mix(in srgb, ${signalColor} 12%, transparent)`,
                                      letterSpacing: "0.3px",
                                    }}>
                                      {signalUpper || "—"}
                                    </span>
                                  </td>

                                  {/* Score with colored bar */}
                                  <td style={{
                                    padding: "7px 10px",
                                    textAlign: "right",
                                  }}>
                                    <div style={{
                                      display: "flex",
                                      alignItems: "center",
                                      justifyContent: "flex-end",
                                      gap: 6,
                                    }}>
                                      <div style={{
                                        width: 48,
                                        height: 4,
                                        background: "var(--border)",
                                        borderRadius: 2,
                                        overflow: "hidden",
                                      }}>
                                        <div style={{
                                          width: `${Math.min(scoreVal, 100)}%`,
                                          height: "100%",
                                          background: scoreColor,
                                          borderRadius: 2,
                                        }} />
                                      </div>
                                      <span style={{
                                        fontWeight: 600,
                                        color: scoreColor,
                                        fontVariantNumeric: "tabular-nums",
                                        minWidth: 20,
                                      }}>
                                        {scoreVal}
                                      </span>
                                    </div>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                ) : scoreResults?.error ? (
                  <EmptyState message={scoreResults.error} />
                ) : (
                  <EmptyState message="Click SCORE PORTFOLIO to analyze your holdings and watchlist." />
                )
              )}

              {/* PAPER tab */}
              {bottomTab === "paper" && (
                <PaperTradingPanel
                  token={token}
                  strategies={strategies.map((s) => ({ slug: s.slug, name: s.name }))}
                />
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
