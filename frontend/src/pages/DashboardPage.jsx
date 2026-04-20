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
import { SkeletonRow, useMarketStatus } from "../components/common";
import { PortfolioChart, AllocationDonut, Heatmap } from "../components/charts";
import { useCurrency } from "../context/CurrencyContext";
import { useI18n } from "../context/I18nContext";
import { useQuotes } from "../context/QuotesContext";
import PeriodSelector from "../components/common/PeriodSelector";
import FilterBar from "../components/common/FilterBar";
import useContextPopup from "../hooks/useContextPopup";
import ContextPopup from "../components/common/ContextPopup";

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
  }, [token]);

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
  }, [token, activePortfolioId]);

  /* -- Register held symbols with shared QuotesContext -------------------- */
  useEffect(() => {
    const symbols = [...new Set(positions.map(p => p.ticker))];
    if (symbols.length > 0) registerSymbols("dashboard", symbols);
    return () => unregisterSymbols("dashboard");
  }, [positions, registerSymbols, unregisterSymbols]);

  /* ── Compute portfolio performance time-series via backend endpoint ──── */
  const [perfData, setPerfData] = useState([]);
  const [perfLoading, setPerfLoading] = useState(false);

  /* ── Error state for failed data fetches ───────────────────────────────── */
  const [fetchError, setFetchError] = useState(null);

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
      return {
        id: g.symbol,
        symbol: g.symbol,
        name: q?.name || g.name || g.symbol,
        quantity: g.totalQty,
        average_cost: avg,
        current_price: price,
        market_value: g.totalQty * price,
        chg: q ? parseFloat(q.change) || 0 : 0,
        chgPct: q ? parseFloat(q.change_pct) || 0 : 0,
        volume: q ? parseFloat(q.volume) || 0 : 0,
        asset_type: g.asset_type,
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

  /* ── Render ─────────────────────────────────────────────────────────────── */
  return (
    <div className="page-scroll">
      {fetchError && (
        <div style={{ padding:"8px 16px", background:"#7f1d1d", color:"#fca5a5", borderRadius:6, marginBottom:12, fontSize:12 }}>
          {fetchError}
        </div>
      )}

      {/* Page header */}
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "flex-end", gap: 16 }}>
          <div>
            <div className="page-title">{t("nav.dashboard")}</div>
            <div className="page-sub">
              {mktStatus.dateStr} · {mktStatus.isOpen ? t("dashboard.marketOpen") : t("dashboard.marketClosed")} · NYSE · NASDAQ
            </div>
          </div>

          {/* Portfolio selector dropdown */}
          {hasPortfolios && (
            <select
              value={activePortfolioId || ""}
              onChange={e => setActivePortfolioId(e.target.value)}
              className="form-control"
              style={{
                width: "auto", minWidth: 180, padding: "5px 28px 5px 10px",
                fontSize: 11, fontWeight: 600, letterSpacing: "0.04em",
                marginBottom: 2,
              }}
            >
              {portfolios.map(p => (
                <option key={p.portfolio_id} value={p.portfolio_id}>{p.name}</option>
              ))}
            </select>
          )}
        </div>

        <div className="page-actions">
          <button className="btn btn-amber" onClick={onNewTx}><Ic.plus /> {t("dashboard.newTransaction")}</button>
        </div>
      </div>

      {/* ── No-portfolio empty state ──────────────────────────────────────── */}
      {!loadingPortfolios && !hasPortfolios && (
        <>
          {/* Heatmap — always visible */}
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

            {/* Create portfolio prompt */}
            <div style={{
              textAlign: "center", padding: "48px 24px",
              background: "var(--panel)", border: "1px solid var(--border)",
            }}>
              <div style={{
                fontFamily: "var(--font-disp)", fontSize: 24, color: "var(--bright)",
                letterSpacing: "1px", marginBottom: 8,
              }}>
                {t("dashboard.noPortfolios")}
              </div>
              <div style={{
                fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--muted)",
                marginBottom: 20, maxWidth: 420, margin: "0 auto 20px",
              }}>
                {t("dashboard.createFirst")}
              </div>
              <button
                className="btn btn-amber"
                onClick={() => setPage("portfolio-manager")}
              >
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
          {/* Stats row */}
          <div className="grid-stats stagger">
            {[
              { lbl: t("dashboard.portfolioValue"), val: formatValue(total, { compact: true }), cls: "amber" },
              { lbl: t("dashboard.unrealizedPnl"),  val: formatValue(pnl, { compact: true, showSign: true }), cls: pnl >= 0 ? "green" : "red" },
              { lbl: t("dashboard.dayChange"),      val: formatValue(dayChg, { showSign: true }), cls: dayChg >= 0 ? "green" : "red" },
              { lbl: t("dashboard.positions"),       val: String(holdings.length), cls: "" },
              { lbl: t("dashboard.portfolio"),       val: activePortfolioName || "—", cls: "amber" },
            ].map((s, i) => (
              <div key={i} className="stat-block">
                <div className="stat-lbl">{s.lbl}</div>
                <div className={`stat-val${s.cls ? " " + s.cls : ""}`}>{s.val}</div>
                {i === 1 && (
                  <div className={`stat-badge ${pnl >= 0 ? "badge-green" : "badge-red"}`}>
                    {pnl >= 0 ? <Ic.up /> : <Ic.down />} {Math.abs(pnlPct).toFixed(2)}% {t("dashboard.allTime")}
                  </div>
                )}
                {i === 2 && (
                  <div className={`stat-badge ${dayChg >= 0 ? "badge-green" : "badge-red"}`}>
                    {dayChg >= 0 ? <Ic.up /> : <Ic.down />} {total > 0 ? Math.abs((dayChg / total) * 100).toFixed(2) : "0.00"}% {t("dashboard.today")}
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="page-inner stagger">
            {/* Heatmap */}
            <div className="panel">
              <div className="panel-header">
                <span className="panel-title">{t("dashboard.heatmap")}</span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>{t("dashboard.byVolume")}</span>
              </div>
              <div className="panel-body" style={{ padding: 0 }}>
                <Heatmap holdings={holdings} onTileAction={handleHeatmapClick} />
              </div>
            </div>

            {/* Portfolio Performance — full-width panel above grid */}
            <div className="panel">
              <div className="panel-header">
                <span className="panel-title">{t("dashboard.perfChart")} · {chartPeriod}</span>
                <PeriodSelector
                  periods={["1W", "1M", "3M", "YTD", "1Y", "ALL"]}
                  value={chartPeriod}
                  onChange={setChartPeriod}
                />
              </div>
              <div className="panel-body" style={{ paddingBottom: 8 }}>
                {perfLoading ? (
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 200, color: "var(--c-muted)", fontSize: 12 }}>
                    Loading chart...
                  </div>
                ) : (
                  <PortfolioChart key={activePortfolioId + chartPeriod} height={160} data={perfData} period={chartPeriod} currencySymbol={currencySymbol} />
                )}
              </div>
            </div>

            {/* Main grid: Gainers/Losers + Allocation sidebar */}
            <div className="grid-main">
              {/* Left column: Top Positions stacked */}
              <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                {/* Top gainers — most profitable positions */}
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
                            <td colSpan={5} style={{
                              textAlign: "center", padding: "24px 0",
                              fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--muted)",
                            }}>
                              {t("dashboard.noGainers")}
                            </td>
                          </tr>
                        ) : topGainers.map(h => {
                          const chgColor = (h.chgPct || 0) >= 0 ? "var(--green)" : "var(--red)";
                          const gainPct = h.average_cost > 0 ? ((h.current_price - h.average_cost) / h.average_cost * 100).toFixed(2) : "0.00";
                          return (
                            <tr key={h.id}>
                              <td>
                                <span style={{
                                  fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 600,
                                  color: "var(--green)", letterSpacing: "0.5px",
                                }}>{h.symbol}</span>
                              </td>
                              <td className="right" style={{ fontSize: 11, color: "var(--muted)" }}>{formatValue(h.average_cost)}</td>
                              <td className="right" style={{ fontSize: 11, color: "var(--green)" }}>{formatValue(h.current_price)}</td>
                              <td className="right" style={{ fontSize: 11, color: chgColor }}>
                                {formatValue(h.chg, { showSign: true })} ({(h.chgPct || 0).toFixed(2)}%)
                              </td>
                              <td className="right" style={{ fontSize: 11, color: "var(--green)" }}>
                                {formatValue(h.pl, { showSign: true })} ({gainPct}%)
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Biggest losers — worst performing positions */}
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
                            <td colSpan={5} style={{
                              textAlign: "center", padding: "24px 0",
                              fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--muted)",
                            }}>
                              {t("dashboard.noLosers")}
                            </td>
                          </tr>
                        ) : topLosers.map(h => {
                          const chgColor = (h.chgPct || 0) >= 0 ? "var(--green)" : "var(--red)";
                          const lossPct = h.average_cost > 0 ? ((h.current_price - h.average_cost) / h.average_cost * 100).toFixed(2) : "0.00";
                          return (
                            <tr key={h.id}>
                              <td>
                                <span style={{
                                  fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 600,
                                  color: "var(--red)", letterSpacing: "0.5px",
                                }}>{h.symbol}</span>
                              </td>
                              <td className="right" style={{ fontSize: 11, color: "var(--muted)" }}>{formatValue(h.average_cost)}</td>
                              <td className="right" style={{ fontSize: 11, color: "var(--red)" }}>{formatValue(h.current_price)}</td>
                              <td className="right" style={{ fontSize: 11, color: chgColor }}>
                                {formatValue(h.chg, { showSign: true })} ({(h.chgPct || 0).toFixed(2)}%)
                              </td>
                              <td className="right" style={{ fontSize: 11, color: "var(--red)" }}>
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
              {/* Right sidebar: Allocation */}
              <div className="panel">
                <div className="panel-header">
                  <span className="panel-title">{t("dashboard.allocation")}</span>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>{holdings.length} {t("dashboard.positions")}</span>
                </div>
                <div className="panel-body">
                  <AllocationDonut holdings={holdings} currencySymbol={currencySymbol} />
                </div>
              </div>
            </div>
          </div>
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
