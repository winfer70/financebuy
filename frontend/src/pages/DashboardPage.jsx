/**
 * DashboardPage.jsx — Main dashboard for TickerTap.
 *
 * Displays portfolio overview sourced from the custom Portfolio Manager system.
 * A dropdown lets the user select which portfolio drives the stats, performance
 * chart, allocation donut, and top-positions table.
 *
 * When no custom portfolios exist the page shows only the market heatmap and
 * a prominent call-to-action to create the first portfolio.
 *
 * Data flow:
 *  1.  Load portfolios on mount → auto-select first
 *  2.  Load positions when active portfolio changes
 *  3.  Register held symbols with shared QuotesContext
 *  4.  QuotesContext polls bulkQuotes on a market-aware interval (3s open / 300s closed)
 *
 * Props:
 *  @param {Function} onNewTx    - Open transaction modal
 *  @param {string}   token      - JWT access token
 *  @param {string}   accountId  - Account UUID (for transaction listing)
 *  @param {Function} setPage    - Navigate to another page
 */

import { useState, useEffect, useMemo, useCallback } from "react";
import api from "../api/client";
import { Ic } from "../components/common/Icons";
import { SkeletonRow, SkeletonChartArea, SkeletonCard, ApiError, useMarketStatus } from "../components/common";
import { PortfolioChart, AllocationDonut, Heatmap } from "../components/charts";
import { useCurrency } from "../context/CurrencyContext";
import { useI18n } from "../context/I18nContext";
import { useQuotes } from "../context/QuotesContext";
import PeriodSelector from "../components/common/PeriodSelector";
import FilterBar from "../components/common/FilterBar";
import useContextPopup from "../hooks/useContextPopup";
import ContextPopup from "../components/common/ContextPopup";
import QuickSellDrawer from "../components/common/QuickSellDrawer";
import { fmtUSD, fmtPct } from "../utils/formatters";

/* ── Vanguard terminal sub-components ──────────────────────────────────────── */

/**
 * KpiCard — Single metric tile with label, value, and optional sub-text.
 *
 * @param {string}  lbl   - Uppercase label text
 * @param {string}  val   - Primary value to display
 * @param {string}  [sub] - Optional secondary text beneath value
 * @param {string}  [tone="amber"] - Color tone: "amber"|"green"|"red"|"blue"
 * @param {boolean} [big=false]    - Use larger font sizing
 */
function KpiCard({ lbl, val, sub, tone = "amber", big = false }) {
  return (
    <div style={{
      background: "var(--panel)", borderLeft: `2px solid var(--${tone})`,
      padding: big ? "14px 16px" : "10px 14px", flex: 1, minWidth: 0,
    }}>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--muted)", letterSpacing: 1.2, textTransform: "uppercase" }}>{lbl}</div>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: big ? 26 : 18, fontWeight: 600, color: `var(--${tone === "green" ? "green" : tone === "red" ? "red" : tone === "blue" ? "blue" : "bright"})`, marginTop: 4, letterSpacing: -0.4, lineHeight: 1 }}>{val}</div>
      {sub && <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--mid)", marginTop: 5 }}>{sub}</div>}
    </div>
  );
}

/**
 * AssetRibbon — Proportional bar showing allocation by asset type.
 * Width = market value weight; color intensity = day P&L magnitude.
 *
 * @param {Array} holdings - Enriched holdings array with mv, chgPct, asset_type
 */
function AssetRibbon({ holdings }) {
  const byType = {};
  holdings.forEach(h => {
    const t = (h.asset_type || "OTHER").toUpperCase();
    if (!byType[t]) byType[t] = { type: t, mv: 0, dayPL: 0 };
    byType[t].mv += h.mv;
    byType[t].dayPL += (h.price * ((h.chgPct || 0) / 100)) * h.qty;
  });
  const rows = Object.values(byType).sort((a, b) => b.mv - a.mv);
  const totalMV = rows.reduce((s, r) => s + r.mv, 0) || 1;
  if (!rows.length) return null;
  return (
    <div style={{ display: "flex", width: "100%", background: "var(--bg2)", border: "1px solid var(--border)", height: 44 }}>
      {rows.map((r, i) => {
        const w = (r.mv / totalMV) * 100;
        const chgPct = r.mv > 0 ? (r.dayPL / r.mv) * 100 : 0;
        const bg = chgPct >= 0
          ? `rgba(0,217,126,${Math.min(0.05 + Math.abs(chgPct) * 0.04, 0.35)})`
          : `rgba(240,68,56,${Math.min(0.05 + Math.abs(chgPct) * 0.04, 0.35)})`;
        return (
          <div key={r.type} style={{
            width: `${w}%`, display: "flex", flexDirection: "column", justifyContent: "center",
            padding: "0 10px", borderRight: i < rows.length - 1 ? "1px solid var(--border)" : "none",
            background: bg, overflow: "hidden", minWidth: 0,
          }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--bright)", fontWeight: 500, letterSpacing: 0.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.type}</div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: chgPct >= 0 ? "var(--green)" : "var(--red)" }}>
              {fmtPct(chgPct)} · {w.toFixed(0)}%
            </div>
          </div>
        );
      })}
    </div>
  );
}

/**
 * ConcentrationChips — Four risk/concentration metric tiles.
 *
 * @param {Array}  holdings     - Enriched holdings with mv, asset_type, symbol
 * @param {number} cashBalance  - Portfolio cash balance
 * @param {number} total        - Total portfolio market value
 */
function ConcentrationChips({ holdings, cashBalance, total }) {
  const totalMV = total || 1;
  const top3 = [...holdings].sort((a, b) => b.mv - a.mv).slice(0, 3);
  const top3Pct = (top3.reduce((s, h) => s + h.mv, 0) / totalMV) * 100;
  const cryptoPct = (holdings.filter(h => (h.asset_type || "").toUpperCase() === "CRYPTO").reduce((s, h) => s + h.mv, 0) / totalMV) * 100;
  const cashPct = totalMV > 0 ? ((cashBalance || 0) / (totalMV + (cashBalance || 0))) * 100 : 0;
  const chips = [
    { lbl: "TOP 3 WEIGHT", val: top3Pct.toFixed(1) + "%", tone: top3Pct > 50 ? "red" : "amber", hint: top3.map(h => h.symbol).join(" · ") || "—" },
    { lbl: "POSITIONS", val: String(holdings.length), tone: "amber", hint: "ACTIVE" },
    { lbl: "CRYPTO", val: cryptoPct.toFixed(1) + "%", tone: "mid", hint: holdings.filter(h => (h.asset_type || "").toUpperCase() === "CRYPTO").map(h => h.symbol).slice(0, 3).join(" · ") || "NONE" },
    { lbl: "CASH WEIGHT", val: cashPct.toFixed(1) + "%", tone: cashPct < 5 ? "red" : "green", hint: fmtUSD(cashBalance || 0) },
  ];
  return (
    <div style={{ display: "flex", gap: 1, background: "var(--border)" }}>
      {chips.map((c, i) => (
        <div key={i} style={{ flex: 1, background: "var(--panel)", padding: "10px 14px", minWidth: 0 }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--muted)", letterSpacing: 1, textTransform: "uppercase" }}>{c.lbl}</div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 18, fontWeight: 600, color: `var(--${c.tone === "red" ? "red" : c.tone === "green" ? "green" : c.tone === "amber" ? "bright" : "mid"})`, marginTop: 3, letterSpacing: -0.3 }}>{c.val}</div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--muted)", marginTop: 3, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{c.hint}</div>
        </div>
      ))}
    </div>
  );
}

/**
 * MiniSparkline — Inline SVG sparkline with gradient fill. No external deps.
 *
 * @param {boolean} positive  - Trending up (green) or down (red)
 * @param {number}  [w=56]    - SVG width in px
 * @param {number}  [h=16]    - SVG height in px
 * @param {number}  [seed=1]  - Deterministic seed for shape variation
 */
function MiniSparkline({ positive, w = 56, h = 16, seed = 1 }) {
  const pts = [];
  let v = 0;
  /* Deterministic pseudo-random using sin — avoids React hydration mismatch */
  const rnd = i => (Math.sin(seed * 9.1 + i * 1.7) + 1) / 2;
  for (let i = 0; i < 18; i++) {
    v += (positive ? 1.1 : -0.7) + (rnd(i) - 0.5) * 3.6;
    pts.push(v);
  }
  const mn = Math.min(...pts), mx = Math.max(...pts), rng = mx - mn || 1;
  const norm = pts.map((val, i) => ({ x: (i / (pts.length - 1)) * w, y: h - ((val - mn) / rng) * (h - 3) - 1.5 }));
  const line = norm.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const fill = line + ` L${w},${h} L0,${h} Z`;
  const c = positive ? "#00d97e" : "#f04438";
  const gid = `spk${seed}${positive ? 1 : 0}`;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ display: "block", flexShrink: 0 }}>
      <defs>
        <linearGradient id={gid} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={c} stopOpacity="0.2"/>
          <stop offset="100%" stopColor={c} stopOpacity="0"/>
        </linearGradient>
      </defs>
      <path d={fill} fill={`url(#${gid})`}/>
      <path d={line} fill="none" stroke={c} strokeWidth="1" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

/**
 * PositionMatrix — Responsive card grid for all holdings.
 * Each card shows symbol, asset type, price, day change, qty, MV, and P&L.
 * Left border color indicates today's direction; sparkline is decorative.
 *
 * @param {Array}    holdings      - Enriched holdings with price, qty, mv, pl, plPct, chgPct
 * @param {Function} [onViewChart] - Called with symbol string on card click
 */
function PositionMatrix({ holdings, onViewChart }) {
  const [quickSellPos, setQuickSellPos] = useState(null);
  return (
    <>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 1, background: "var(--border)" }}>
        {holdings.map((h) => {
          const pos = (h.chgPct || 0) >= 0;
          const pnlPos = (h.pl || 0) >= 0;
          return (
            <div
              key={h.symbol}
              style={{
                background: "var(--panel)", padding: "10px 12px",
                borderLeft: `2px solid ${pos ? "var(--green)" : "var(--red)"}`,
                display: "flex", flexDirection: "column", gap: 4, cursor: "pointer",
                transition: "background 0.12s",
              }}
              onClick={() => onViewChart?.(h.symbol)}
              onMouseEnter={e => e.currentTarget.style.background = "var(--bg3)"}
              onMouseLeave={e => e.currentTarget.style.background = "var(--panel)"}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 13, color: "var(--bright)", fontWeight: 600, letterSpacing: 0.4 }}>{h.symbol}</span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--muted)", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{(h.asset_type || "").toUpperCase()}</span>
                <MiniSparkline positive={pos} w={52} h={14} seed={h.symbol.charCodeAt(0)} />
              </div>
              <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 15, color: "var(--bright)", fontWeight: 500 }}>
                  {fmtUSD(h.price || 0)}
                </span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: pos ? "var(--green)" : "var(--red)" }}>
                  {pos ? "+" : ""}{(h.chgPct || 0).toFixed(2)}%
                </span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--muted)" }}>
                <span>QTY {h.qty}</span>
                <span>MV ${(h.mv / 1000).toFixed(1)}K</span>
                <span style={{ color: pnlPos ? "var(--green)" : "var(--red)" }}>
                  {pnlPos ? "+" : ""}{(h.plPct || 0).toFixed(1)}%
                </span>
              </div>
              {/* Quick sell button — stopPropagation prevents triggering chart nav */}
              <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 2 }}>
                <button
                  className="btn-ghost table-action-btn"
                  style={{ fontSize: "10px", padding: "2px 6px" }}
                  onClick={(e) => { e.stopPropagation(); setQuickSellPos(h); }}
                >SELL</button>
              </div>
            </div>
          );
        })}
      </div>
      {/* Quick sell drawer — opens when a SELL button is clicked on a card */}
      <QuickSellDrawer
        position={quickSellPos}
        isOpen={!!quickSellPos}
        onClose={() => setQuickSellPos(null)}
      />
    </>
  );
}

/* -- Category filter IDs for Top Positions panel (labels resolved via t()) -- */

export function DashboardPage({ onNewTx, token, setPage, onViewChart }) {
  const mktStatus = useMarketStatus();
  const { formatValue, currencySymbol } = useCurrency();
  const { t } = useI18n();
  /* ── Category filter config for Top Positions panel (i18n-aware) ──────── */
  const POSITION_CATEGORIES = useMemo(() => [
    { id: "all",      label: t("watchlist.all") },
    { id: "stock",    label: t("watchlist.stocks") },
    { id: "crypto",   label: t("watchlist.crypto") },
    { id: "etf",      label: t("watchlist.etfs") },
    { id: "physical", label: t("watchlist.physical") },
  ], [t]);
  const { quotesMap: sharedQuotesMap, registerSymbols, unregisterSymbols } = useQuotes();
  const [chartPeriod, setChartPeriod] = useState("3M");
  const [positionCategory, setPositionCategory] = useState("all");
  const [loserCategory, setLoserCategory] = useState("all");

  /* ── Portfolio data source ──────────────────────────────────────────────── */
  const [portfolios,        setPortfolios]        = useState(() => {
    try { return JSON.parse(sessionStorage.getItem("tickertap_portfolios") || "null") || []; }
    catch { return []; }
  });
  const [activePortfolioId, setActivePortfolioId] = useState(() => {
    try {
      const cached = JSON.parse(sessionStorage.getItem("tickertap_portfolios") || "null");
      return cached && cached.length ? cached[0].portfolio_id : null;
    } catch { return null; }
  });
  const [positions,         setPositions]         = useState(() => {
    try { return JSON.parse(sessionStorage.getItem("tickertap_positions") || "null") || []; }
    catch { return []; }
  });
  /* quotesMap is now derived from the shared QuotesContext */
  const quotesMap = sharedQuotesMap;
  /* Skip loading state if cache is available — dashboard renders instantly */
  const hasCachedPortfolios = portfolios.length > 0;
  const [loadingPortfolios, setLoadingPortfolios] = useState(!hasCachedPortfolios);
  const [loadingPositions,  setLoadingPositions]  = useState(false);

  /* ── Error + retry state — declared before effects that reference them ─── */
  const [perfData,    setPerfData]    = useState([]);
  const [perfLoading, setPerfLoading] = useState(false);
  const [fetchError,  setFetchError]  = useState(null);
  const [retryKey,    setRetryKey]    = useState(0);
  const handleRetry = () => { setFetchError(null); setRetryKey(k => k + 1); };

  /* -- Load portfolios (stale-while-revalidate: cache renders instantly,
        fresh fetch updates in background) --------------------------------- */
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      if (!hasCachedPortfolios) setLoadingPortfolios(true);
      try {
        const list = await api.listPortfolios(token);
        if (cancelled) return;
        setPortfolios(list || []);
        sessionStorage.setItem("tickertap_portfolios", JSON.stringify(list || []));
        if (list && list.length) {
          setActivePortfolioId(prev => prev || list[0].portfolio_id);
        }
      } catch (e) { setFetchError(e?.message || "Failed to load data"); }
      finally { if (!cancelled) setLoadingPortfolios(false); }
    })();
    return () => { cancelled = true; };
  }, [token, retryKey]);

  /* -- Load positions when active portfolio changes (caches to sessionStorage) */
  useEffect(() => {
    if (!token || !activePortfolioId) { setPositions([]); return; }
    let cancelled = false;
    (async () => {
      setLoadingPositions(true);
      try {
        const list = await api.listPositions(activePortfolioId, token);
        if (cancelled) return;
        setPositions(list || []);
        sessionStorage.setItem("tickertap_positions", JSON.stringify(list || []));
      } catch (e) { setFetchError(e?.message || "Failed to load data"); }
      finally { if (!cancelled) setLoadingPositions(false); }
    })();
    return () => { cancelled = true; };
  }, [token, activePortfolioId, retryKey]);

  /* -- Register held symbols with shared QuotesContext -------------------- */
  useEffect(() => {
    const symbols = [...new Set(positions.map(p => p.ticker))];
    if (symbols.length > 0) registerSymbols("dashboard", symbols);
    return () => unregisterSymbols("dashboard");
  }, [positions, registerSymbols, unregisterSymbols]);


  useEffect(() => {
    if (!token || positions.length === 0 || !activePortfolioId) { setPerfData([]); return; }
    let cancelled = false;

    (async () => {
      setPerfLoading(true);
      try {
        /* The backend handles OHLCV fetching, forward-fill, and dynamic
           ALL range computation — no local PERIOD_DAYS map needed. */
        const series = await api.getPortfolioPerformance(activePortfolioId, chartPeriod, token);
        if (!cancelled) setPerfData(series);
      } catch (e) { setFetchError(e?.message || "Failed to load data"); }
      finally { if (!cancelled) setPerfLoading(false); }
    })();
    return () => { cancelled = true; };
  }, [token, activePortfolioId, positions, chartPeriod]);

  /* ── Derived holdings from positions + quotes (consolidated by symbol) ─── */
  const holdings = useMemo(() => {
    /* Group positions by symbol, then consolidate qty + cost */
    const grouped = {};
    positions.filter(p => !p.is_excluded).forEach(p => {
      const key = p.ticker;
      if (!grouped[key]) {
        grouped[key] = { symbol: key, name: p.name, totalQty: 0, totalCost: 0, asset_type: p.asset_type || "stock" };
      }
      const qty = parseFloat(p.quantity) || 0;
      const avg = parseFloat(p.purchase_price) || 0;
      grouped[key].totalQty += qty;
      grouped[key].totalCost += qty * avg;
    });

    return Object.values(grouped).map(g => {
      const q = quotesMap[g.symbol];
      const price = q ? parseFloat(q.price) || 0 : 0;
      const avg = g.totalQty > 0 ? g.totalCost / g.totalQty : 0;
      const mv = g.totalQty * price;
      const plAbs = (price - avg) * g.totalQty;
      const plPct = avg > 0 ? ((price - avg) / avg) * 100 : 0;
      return {
        id:            g.symbol,
        symbol:        g.symbol,
        name:          q?.name || g.name || g.symbol,
        /* canonical field names */
        quantity:      g.totalQty,
        average_cost:  avg,
        current_price: price,
        market_value:  mv,
        /* aliases expected by Vanguard components */
        price,
        qty:           g.totalQty,
        mv,
        pl:            plAbs,
        plPct,
        /* quote fields */
        chg:           q ? parseFloat(q.change)     || 0 : 0,
        chgPct:        q ? parseFloat(q.change_pct) || 0 : 0,
        volume:        q ? parseFloat(q.volume)      || 0 : 0,
        asset_type:    g.asset_type,
      };
    });
  }, [positions, quotesMap]);

  /* ── Category-filtered holdings for Top Positions panel ───────────────── */
  const filteredHoldings = useMemo(() =>
    positionCategory === "all"
      ? holdings
      : holdings.filter(h => h.asset_type === positionCategory),
  [holdings, positionCategory]);

  /* ── Category-filtered holdings for Biggest Losers panel ─────────────── */
  const filteredLosersHoldings = useMemo(() =>
    loserCategory === "all"
      ? holdings
      : holdings.filter(h => h.asset_type === loserCategory),
  [holdings, loserCategory]);

  /* ── Top gainers: sorted by P&L descending, top 5 with positive gain ─── */
  const topGainers = useMemo(() => {
    return [...filteredHoldings]
      .map(h => ({ ...h, pl: (h.current_price - h.average_cost) * h.quantity }))
      .filter(h => h.pl > 0)
      .sort((a, b) => b.pl - a.pl)
      .slice(0, 5);
  }, [filteredHoldings]);

  /* ── Biggest losers: sorted by P&L ascending, top 5 with negative P&L ── */
  const topLosers = useMemo(() => {
    return [...filteredLosersHoldings]
      .map(h => ({ ...h, pl: (h.current_price - h.average_cost) * h.quantity }))
      .filter(h => h.pl < 0)
      .sort((a, b) => a.pl - b.pl)
      .slice(0, 5);
  }, [filteredLosersHoldings]);

  /* ── Summary stats ──────────────────────────────────────────────────────── */
  const total  = holdings.reduce((s, h) => s + h.quantity * h.current_price, 0);
  const cost   = holdings.reduce((s, h) => s + h.quantity * h.average_cost, 0);
  const pnl    = total - cost;
  const pnlPct = cost > 0 ? (pnl / cost) * 100 : 0;
  const dayChg = holdings.reduce((s, h) => s + h.chg * h.quantity, 0);

  /* ── Heatmap click popup state ───────────────────────────────────────── */
  const heatmapCtx = useContextPopup();

  /**
   * handleHeatmapClick — opens a context popup on a heatmap tile click.
   * Captures symbol + mouse coords for absolute positioning.
   *
   * @param {string} symbol - ticker symbol from the clicked tile
   * @param {MouseEvent} e  - click event for positioning
   */
  const handleHeatmapClick = useCallback((symbol, e) => {
    heatmapCtx.open({ symbol }, e);
  }, [heatmapCtx]);

  const hasPortfolios = portfolios.length > 0;
  const activePortfolioName = portfolios.find(p => p.portfolio_id === activePortfolioId)?.name || "";
  const activePortfolio = portfolios.find(p => p.portfolio_id === activePortfolioId);

  /* ── Render — Vanguard terminal layout ─────────────────────────────────── */
  return (
    <div className="page-scroll">
      {fetchError && (
        <ApiError message={fetchError} onRetry={handleRetry} />
      )}

      {/* ── SLIM HEADER — portfolio value + P&L + controls ─────────────── */}
      <div style={{
        background: "var(--bg2)", borderBottom: "1px solid var(--border)",
        padding: "14px 24px", display: "flex", alignItems: "center", gap: 20, flexWrap: "wrap",
      }}>
        {/* Big value block */}
        <div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--muted)", letterSpacing: 1.5, textTransform: "uppercase" }}>
            {activePortfolioName || t("dashboard.portfolio")} · {mktStatus.isOpen ? "OPEN" : "CLOSED"}
          </div>
          <div style={{ fontFamily: "var(--font-disp)", fontSize: 36, color: "var(--bright)", letterSpacing: 2, lineHeight: 1, marginTop: 3 }}>
            {formatValue(total, { compact: true })}
          </div>
        </div>

        {/* P&L lines */}
        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: pnl >= 0 ? "var(--green)" : "var(--red)", fontWeight: 500 }}>
            {pnl >= 0 ? "▲" : "▼"} {formatValue(Math.abs(pnl), { showSign: false })}{" "}
            <span style={{ color: "var(--muted)" }}>ALL-TIME · {pnlPct.toFixed(2)}%</span>
          </span>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: dayChg >= 0 ? "var(--green)" : "var(--red)" }}>
            {dayChg >= 0 ? "▲" : "▼"} {formatValue(Math.abs(dayChg), { showSign: false })}{" "}
            <span style={{ color: "var(--muted)" }}>
              TODAY · {total > 0 ? ((Math.abs(dayChg) / total) * 100).toFixed(2) : "0.00"}%
            </span>
          </span>
        </div>

        {/* Spacer */}
        <div style={{ flex: 1 }} />

        {/* Portfolio selector */}
        {hasPortfolios && (
          <select
            value={activePortfolioId || ""}
            onChange={e => setActivePortfolioId(e.target.value)}
            className="form-control"
            style={{
              width: "auto", minWidth: 180, padding: "5px 28px 5px 10px",
              fontSize: 11, fontWeight: 600, letterSpacing: "0.04em",
            }}
          >
            {portfolios.map(p => (
              <option key={p.portfolio_id} value={p.portfolio_id}>{p.name}</option>
            ))}
          </select>
        )}

        {/* New Transaction button */}
        <button className="btn btn-amber" onClick={onNewTx}>
          <Ic.plus /> {t("dashboard.newTransaction")}
        </button>
      </div>

      {/* ── No-portfolio empty state ──────────────────────────────────────── */}
      {!loadingPortfolios && !hasPortfolios && (
        <>
          <div className="page-inner">
            <div className="panel">
              <div className="panel-header">
                <span className="panel-title">{t("dashboard.heatmap")}</span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>{t("dashboard.byVolume")}</span>
              </div>
              <div className="panel-body" style={{ padding: 0 }}>
                <Heatmap holdings={[]} onTileAction={handleHeatmapClick} />
              </div>
            </div>
            <div style={{
              textAlign: "center", padding: "48px 24px",
              background: "var(--panel)", border: "1px solid var(--border)",
            }}>
              <div style={{ fontFamily: "var(--font-disp)", fontSize: 24, color: "var(--bright)", letterSpacing: "1px", marginBottom: 8 }}>
                {t("dashboard.noPortfolios")}
              </div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--muted)", marginBottom: 20, maxWidth: 420, margin: "0 auto 20px" }}>
                {t("dashboard.createFirst")}
              </div>
              <button className="btn btn-amber" onClick={() => setPage("portfolio-manager")}>
                <Ic.plus /> {t("dashboard.createPortfolio")}
              </button>
            </div>
          </div>
        </>
      )}

      {/* ── Loading state ─────────────────────────────────────────────────── */}
      {loadingPortfolios && (
        <div style={{ textAlign: "center", padding: "48px 0" }}>
          <span className="loading-pulse" style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--muted)" }}>
            {t("dashboard.loadingPortfolio")}
          </span>
        </div>
      )}

      {/* ── Full dashboard (portfolio selected) ───────────────────────────── */}
      {hasPortfolios && !loadingPortfolios && (
        <>
          {/* ASSET TYPE RIBBON */}
          {holdings.length > 0 && (
            <div style={{ padding: "12px 24px 0" }}>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--muted)", letterSpacing: 1.5, marginBottom: 6, textTransform: "uppercase" }}>
                Asset Allocation · Width=Weight · Color=Today
              </div>
              <AssetRibbon holdings={holdings} />
            </div>
          )}

          {/* CONCENTRATION CHIPS */}
          {holdings.length > 0 && (
            <div style={{ padding: "12px 24px 0" }}>
              <ConcentrationChips
                holdings={holdings}
                cashBalance={parseFloat(activePortfolio?.cash_balance || 0)}
                total={total}
              />
            </div>
          )}

          {/* MAIN GRID: equity curve + heatmap */}
          {holdings.length > 0 && (
            <div style={{ padding: "16px 24px 0", display: "grid", gridTemplateColumns: "1fr 1.4fr", gap: 16 }}>
              {/* Left: Equity Curve */}
              <div className="panel">
                <div className="panel-header">
                  <span className="panel-title">EQUITY CURVE</span>
                  <div style={{ display: "flex", gap: 4 }}>
                    {["1W", "1M", "3M", "YTD", "1Y", "ALL"].map(p => (
                      <button
                        key={p}
                        onClick={() => setChartPeriod(p)}
                        style={{
                          fontFamily: "var(--font-mono)", fontSize: 9, padding: "2px 6px",
                          background: chartPeriod === p ? "var(--amber)" : "transparent",
                          color: chartPeriod === p ? "#fff" : "var(--muted)",
                          border: "1px solid var(--border)", cursor: "pointer", letterSpacing: 0.5,
                        }}
                      >{p}</button>
                    ))}
                  </div>
                </div>
                <div className="panel-body" style={{ paddingBottom: 8 }}>
                  {perfLoading ? (
                    <SkeletonChartArea />
                  ) : (
                    <PortfolioChart key={activePortfolioId + chartPeriod} height={160} data={perfData} period={chartPeriod} currencySymbol={currencySymbol} />
                  )}
                </div>
              </div>

              {/* Right: Heatmap */}
              <div className="panel">
                <div className="panel-header">
                  <span className="panel-title">HEATMAP · VOLUME × CHG</span>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>{t("dashboard.byVolume")}</span>
                </div>
                <div style={{ padding: 1 }}>
                  <Heatmap holdings={holdings} onTileAction={handleHeatmapClick} />
                </div>
              </div>
            </div>
          )}

          {/* POSITION MATRIX */}
          {(holdings.length > 0 || loadingPositions) && (
            <div style={{ padding: "16px 24px 0" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--amber)", letterSpacing: 1.5 }}>
                  POSITIONS · {holdings.length}
                </div>
                {/* Use POSITION_CATEGORIES for correct asset_type IDs */}
                <div style={{ display: "flex", gap: 4 }}>
                  {POSITION_CATEGORIES.map(cat => (
                    <button
                      key={cat.id}
                      onClick={() => setPositionCategory(cat.id)}
                      style={{
                        fontFamily: "var(--font-mono)", fontSize: 9, padding: "2px 8px",
                        background: positionCategory === cat.id ? "var(--amber)" : "transparent",
                        color: positionCategory === cat.id ? "#fff" : "var(--muted)",
                        border: "1px solid var(--border)", cursor: "pointer", letterSpacing: 0.5,
                        textTransform: "uppercase",
                      }}
                    >{cat.label}</button>
                  ))}
                </div>
              </div>
              {loadingPositions ? (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "8px" }}>
                  {Array.from({ length: 6 }).map((_, i) => <SkeletonCard key={i} />)}
                </div>
              ) : (
                <PositionMatrix holdings={filteredHoldings} onViewChart={onViewChart} />
              )}
            </div>
          )}

          {/* TOP GAINERS + LOSERS */}
          {holdings.length > 0 && (
            <div style={{ padding: "16px 24px 24px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              {/* Top gainers */}
              <div className="panel">
                <div className="panel-header">
                  <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                    <span className="panel-title" style={{ color: "var(--green)" }}>{t("dashboard.topGainers")}</span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>
                      {filteredHoldings.length} {t("dashboard.held")}
                    </span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <FilterBar
                      items={POSITION_CATEGORIES}
                      value={positionCategory}
                      onChange={setPositionCategory}
                      style={{ padding: "4px 10px", fontSize: 9 }}
                    />
                    <button
                      className="btn btn-ghost"
                      style={{ fontSize: 9, padding: "3px 10px" }}
                      onClick={() => setPage("portfolio-manager", { sortCol: "gainloss", sortDir: "desc" })}
                    >{t("dashboard.viewAll")} →</button>
                  </div>
                </div>
                <div style={{ overflowX: "auto" }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>{t("dashboard.symbol")}</th>
                        <th className="right">{t("portfolioManager.breakeven")}</th>
                        <th className="right">{t("portfolioManager.price")}</th>
                        <th className="right">{t("dashboard.chg")}</th>
                        <th className="right">{t("portfolioManager.gainLoss")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {loadingPositions ? (
                        Array.from({ length: 3 }).map((_, i) => <SkeletonRow key={i} cols={5} />)
                      ) : topGainers.length === 0 ? (
                        <tr>
                          <td colSpan={5} style={{ textAlign: "center", padding: "24px 0", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--muted)" }}>
                            {t("dashboard.noGainers")}
                          </td>
                        </tr>
                      ) : topGainers.map(h => {
                        const chgColor = (h.chgPct || 0) >= 0 ? "var(--green)" : "var(--red)";
                        const gainPct = h.average_cost > 0 ? ((h.current_price - h.average_cost) / h.average_cost * 100).toFixed(2) : "0.00";
                        return (
                          <tr key={h.id}>
                            <td data-label="TICKER">
                              <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 600, color: "var(--green)", letterSpacing: "0.5px" }}>
                                {h.symbol}
                              </span>
                            </td>
                            <td data-label="BEP" className="right" style={{ fontSize: 11, color: "var(--muted)" }}>{formatValue(h.average_cost)}</td>
                            <td data-label="PRICE" className="right" style={{ fontSize: 11, color: "var(--green)" }}>{formatValue(h.current_price)}</td>
                            <td data-label="CHG" className="right" style={{ fontSize: 11, color: chgColor }}>
                              {formatValue(h.chg, { showSign: true })} ({(h.chgPct || 0).toFixed(2)}%)
                            </td>
                            <td data-label="GAIN/LOSS" className="right" style={{ fontSize: 11, color: "var(--green)" }}>
                              {formatValue(h.pl, { showSign: true })} ({gainPct}%)
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Biggest losers */}
              <div className="panel">
                <div className="panel-header">
                  <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                    <span className="panel-title" style={{ color: "var(--red)" }}>{t("dashboard.biggestLosers")}</span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>
                      {filteredLosersHoldings.length} {t("dashboard.held")}
                    </span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <FilterBar
                      items={POSITION_CATEGORIES}
                      value={loserCategory}
                      onChange={setLoserCategory}
                      style={{ padding: "4px 10px", fontSize: 9 }}
                    />
                    <button
                      className="btn btn-ghost"
                      style={{ fontSize: 9, padding: "3px 10px" }}
                      onClick={() => setPage("portfolio-manager", { sortCol: "gainloss", sortDir: "asc" })}
                    >{t("dashboard.viewAll")} →</button>
                  </div>
                </div>
                <div style={{ overflowX: "auto" }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>{t("dashboard.symbol")}</th>
                        <th className="right">{t("portfolioManager.breakeven")}</th>
                        <th className="right">{t("portfolioManager.price")}</th>
                        <th className="right">{t("dashboard.chg")}</th>
                        <th className="right">{t("portfolioManager.gainLoss")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {loadingPositions ? (
                        Array.from({ length: 3 }).map((_, i) => <SkeletonRow key={i} cols={5} />)
                      ) : topLosers.length === 0 ? (
                        <tr>
                          <td colSpan={5} style={{ textAlign: "center", padding: "24px 0", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--muted)" }}>
                            {t("dashboard.noLosers")}
                          </td>
                        </tr>
                      ) : topLosers.map(h => {
                        const chgColor = (h.chgPct || 0) >= 0 ? "var(--green)" : "var(--red)";
                        const lossPct = h.average_cost > 0 ? ((h.current_price - h.average_cost) / h.average_cost * 100).toFixed(2) : "0.00";
                        return (
                          <tr key={h.id}>
                            <td data-label="TICKER">
                              <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 600, color: "var(--red)", letterSpacing: "0.5px" }}>
                                {h.symbol}
                              </span>
                            </td>
                            <td data-label="BEP" className="right" style={{ fontSize: 11, color: "var(--muted)" }}>{formatValue(h.average_cost)}</td>
                            <td data-label="PRICE" className="right" style={{ fontSize: 11, color: "var(--red)" }}>{formatValue(h.current_price)}</td>
                            <td data-label="CHG" className="right" style={{ fontSize: 11, color: chgColor }}>
                              {formatValue(h.chg, { showSign: true })} ({(h.chgPct || 0).toFixed(2)}%)
                            </td>
                            <td data-label="GAIN/LOSS" className="right" style={{ fontSize: 11, color: "var(--red)" }}>
                              {formatValue(h.pl, { showSign: true })} ({lossPct}%)
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {/* ── Heatmap click popup ────────────────────────────────────────── */}
      {heatmapCtx.popup && (
        <ContextPopup
          x={heatmapCtx.popup.x}
          y={heatmapCtx.popup.y}
          title={heatmapCtx.popup.symbol}
          actions={[
            {
              label: `${t("dashboard.viewChart")} →`,
              onClick: () => { onViewChart && onViewChart(heatmapCtx.popup.symbol); heatmapCtx.close(); },
            },
          ]}
        />
      )}
    </div>
  );
}
