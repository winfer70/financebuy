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
 *  3.  Fetch live quotes via bulkQuotes after positions load
 *  4.  Poll quotes on a market-aware interval (3s open / 300s closed)
 *
 * Props:
 *  @param {Function} onNewTx    - Open transaction modal
 *  @param {string}   token      - JWT access token
 *  @param {string}   accountId  - Account UUID (for transaction listing)
 *  @param {Function} setPage    - Navigate to another page
 */

import { useState, useEffect, useMemo } from "react";
import api from "../api/client";
import { Ic } from "../components/common/Icons";
import { SkeletonRow, useMarketStatus } from "../components/common";
import { Sparkline, PortfolioChart, AllocationDonut, Heatmap } from "../components/charts";

export function DashboardPage({ onNewTx, token, setPage }) {
  const mktStatus = useMarketStatus();
  const [chartPeriod, setChartPeriod] = useState("3M");

  /* ── Portfolio data source ──────────────────────────────────────────────── */
  const [portfolios,        setPortfolios]        = useState([]);
  const [activePortfolioId, setActivePortfolioId] = useState(null);
  const [positions,         setPositions]         = useState([]);
  const [quotesMap,         setQuotesMap]         = useState({});
  const [loadingPortfolios, setLoadingPortfolios] = useState(true);
  const [loadingPositions,  setLoadingPositions]  = useState(false);

  /* -- Load portfolios ---------------------------------------------------- */
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      setLoadingPortfolios(true);
      try {
        const list = await api.listPortfolios(token);
        if (cancelled) return;
        setPortfolios(list || []);
        if (list && list.length) setActivePortfolioId(list[0].portfolio_id);
      } catch { /* non-fatal */ }
      finally { if (!cancelled) setLoadingPortfolios(false); }
    })();
    return () => { cancelled = true; };
  }, [token]);

  /* -- Load positions when active portfolio changes ----------------------- */
  useEffect(() => {
    if (!token || !activePortfolioId) { setPositions([]); setQuotesMap({}); return; }
    let cancelled = false;
    (async () => {
      setLoadingPositions(true);
      try {
        const list = await api.listPositions(activePortfolioId, token);
        if (cancelled) return;
        setPositions(list || []);
      } catch { /* non-fatal */ }
      finally { if (!cancelled) setLoadingPositions(false); }
    })();
    return () => { cancelled = true; };
  }, [token, activePortfolioId]);

  /* -- Poll live quotes for held symbols ---------------------------------- */
  const dashPollMs = mktStatus.isOpen ? 3000 : 300000;
  useEffect(() => {
    if (!token || positions.length === 0) return;
    let cancelled = false;
    const symbols = [...new Set(positions.map(p => p.ticker))];
    const fetchQuotes = async () => {
      try {
        const quoteList = await api.bulkQuotes(symbols, token);
        if (cancelled) return;
        const map = {};
        quoteList.forEach(q => { map[q.symbol] = q; });
        setQuotesMap(map);
      } catch { /* non-fatal */ }
    };
    fetchQuotes();
    const id = setInterval(fetchQuotes, dashPollMs);
    return () => { cancelled = true; clearInterval(id); };
  }, [token, positions, dashPollMs]);

  /* ── Derived holdings from positions + quotes ───────────────────────────── */
  const holdings = useMemo(() =>
    positions.filter(p => !p.is_excluded).map(p => {
      const q = quotesMap[p.ticker];
      const qty = parseFloat(p.quantity) || 0;
      const avg = parseFloat(p.purchase_price) || 0;
      const price = q ? parseFloat(q.price) || 0 : 0;
      return {
        symbol: p.ticker,
        name: q?.name || p.name || p.ticker,
        quantity: qty,
        average_cost: avg,
        current_price: price,
        market_value: qty * price,
        chg: q ? parseFloat(q.change) || 0 : 0,
        chgPct: q ? parseFloat(q.change_pct) || 0 : 0,
        volume: q ? parseFloat(q.volume) || 0 : 0,
      };
    }),
  [positions, quotesMap]);

  /* ── Summary stats ──────────────────────────────────────────────────────── */
  const total  = holdings.reduce((s, h) => s + h.quantity * h.current_price, 0);
  const cost   = holdings.reduce((s, h) => s + h.quantity * h.average_cost, 0);
  const pnl    = total - cost;
  const pnlPct = cost > 0 ? (pnl / cost) * 100 : 0;
  const dayChg = holdings.reduce((s, h) => s + h.chg * h.quantity, 0);

  const hasPortfolios = portfolios.length > 0;
  const activePortfolioName = portfolios.find(p => p.portfolio_id === activePortfolioId)?.name || "";

  /* ── Render ─────────────────────────────────────────────────────────────── */
  return (
    <div className="page-scroll">
      {/* Page header */}
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "flex-end", gap: 16 }}>
          <div>
            <div className="page-title">DASHBOARD</div>
            <div className="page-sub">
              {mktStatus.dateStr} · {mktStatus.isOpen ? "MARKET OPEN" : "MARKET CLOSED"} · NYSE · NASDAQ
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
          <button className="btn btn-amber" onClick={onNewTx}><Ic.plus /> NEW TRANSACTION</button>
        </div>
      </div>

      {/* ── No-portfolio empty state ──────────────────────────────────────── */}
      {!loadingPortfolios && !hasPortfolios && (
        <>
          {/* Heatmap — always visible */}
          <div className="page-inner">
            <div className="panel">
              <div className="panel-header">
                <span className="panel-title">MARKET HEATMAP</span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>BY VOLUME</span>
              </div>
              <div className="panel-body" style={{ padding: 0 }}>
                <Heatmap holdings={[]} />
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
                NO PORTFOLIOS YET
              </div>
              <div style={{
                fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--muted)",
                marginBottom: 20, maxWidth: 420, margin: "0 auto 20px",
              }}>
                Create your first portfolio to see performance stats, allocation charts,
                and top positions right here on the dashboard.
              </div>
              <button
                className="btn btn-amber"
                onClick={() => setPage("portfolio-manager")}
              >
                <Ic.plus /> CREATE PORTFOLIO
              </button>
            </div>
          </div>
        </>
      )}

      {/* ── Loading state ─────────────────────────────────────────────────── */}
      {loadingPortfolios && (
        <div style={{ textAlign: "center", padding: "48px 0" }}>
          <span className="loading-pulse" style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--muted)" }}>
            LOADING PORTFOLIO DATA...
          </span>
        </div>
      )}

      {/* ── Full dashboard (portfolio selected) ───────────────────────────── */}
      {hasPortfolios && !loadingPortfolios && (
        <>
          {/* Stats row */}
          <div className="grid-stats stagger">
            {[
              { lbl: "Portfolio Value", val: `$${(total / 1000).toFixed(2)}K`, cls: "amber" },
              { lbl: "Unrealized P&L",  val: `${pnl >= 0 ? "+" : ""}$${(Math.abs(pnl) / 1000).toFixed(2)}K`, cls: pnl >= 0 ? "green" : "red" },
              { lbl: "Day Change",      val: `${dayChg >= 0 ? "+" : ""}$${Math.abs(dayChg).toFixed(2)}`, cls: dayChg >= 0 ? "green" : "red" },
              { lbl: "Positions",       val: String(holdings.length), cls: "" },
              { lbl: "Portfolio",       val: activePortfolioName || "—", cls: "amber" },
            ].map((s, i) => (
              <div key={i} className="stat-block">
                <div className="stat-lbl">{s.lbl}</div>
                <div className={`stat-val${s.cls ? " " + s.cls : ""}`}>{s.val}</div>
                {i === 1 && (
                  <div className={`stat-badge ${pnl >= 0 ? "badge-green" : "badge-red"}`}>
                    {pnl >= 0 ? <Ic.up /> : <Ic.down />} {Math.abs(pnlPct).toFixed(2)}% ALL TIME
                  </div>
                )}
                {i === 2 && (
                  <div className={`stat-badge ${dayChg >= 0 ? "badge-green" : "badge-red"}`}>
                    {dayChg >= 0 ? <Ic.up /> : <Ic.down />} {total > 0 ? Math.abs((dayChg / total) * 100).toFixed(2) : "0.00"}% TODAY
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="page-inner stagger">
            {/* Heatmap */}
            <div className="panel">
              <div className="panel-header">
                <span className="panel-title">MARKET HEATMAP</span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>BY VOLUME</span>
              </div>
              <div className="panel-body" style={{ padding: 0 }}>
                <Heatmap holdings={holdings} />
              </div>
            </div>

            {/* Main chart + allocation */}
            <div className="grid-main">
              <div className="panel">
                <div className="panel-header">
                  <span className="panel-title">PORTFOLIO PERFORMANCE · {chartPeriod}</span>
                  <div style={{ display: "flex", gap: 1 }}>
                    {["1W", "1M", "3M", "YTD", "1Y", "ALL"].map(p => (
                      <button
                        key={p}
                        className={`filter-btn${p === chartPeriod ? " active" : ""}`}
                        style={{ padding: "4px 10px", fontSize: 9 }}
                        onClick={() => setChartPeriod(p)}
                      >{p}</button>
                    ))}
                  </div>
                </div>
                <div className="panel-body" style={{ paddingBottom: 8 }}>
                  <PortfolioChart height={160} period={chartPeriod} />
                </div>
              </div>
              <div className="panel">
                <div className="panel-header">
                  <span className="panel-title">ALLOCATION</span>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>{holdings.length} POSITIONS</span>
                </div>
                <div className="panel-body">
                  <AllocationDonut holdings={holdings} />
                </div>
              </div>
            </div>

            {/* Top positions */}
            <div className="panel">
              <div className="panel-header">
                <span className="panel-title">TOP POSITIONS</span>
                <button
                  className="btn btn-ghost"
                  style={{ fontSize: 9, padding: "3px 10px" }}
                  onClick={() => setPage("portfolio-manager")}
                >VIEW ALL →</button>
              </div>
              <div style={{ overflowX: "auto" }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>SYMBOL</th>
                      <th className="right">LAST</th>
                      <th className="right">CHG</th>
                      <th className="right">QTY</th>
                      <th className="right">MKT VALUE</th>
                      <th className="right">P&L</th>
                      <th className="right">RETURN</th>
                      <th>TREND</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loadingPositions ? (
                      Array.from({ length: 3 }).map((_, i) => <SkeletonRow key={i} cols={8} />)
                    ) : holdings.length === 0 ? (
                      <tr>
                        <td colSpan={8} style={{
                          textAlign: "center", padding: "32px 0",
                          fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--muted)",
                        }}>
                          No positions in this portfolio
                        </td>
                      </tr>
                    ) : holdings.slice(0, 5).map(h => {
                      const qty = h.quantity || 0;
                      const price = h.current_price || 0;
                      const avg = h.average_cost || 0;
                      const val = qty * price;
                      const pl = (price - avg) * qty;
                      const ret = avg > 0 ? ((price - avg) / avg) * 100 : 0;
                      return (
                        <tr key={h.symbol}>
                          <td>
                            <div className="cell-symbol">
                              <div className="sym-badge">{(h.symbol || "?").slice(0, 3)}</div>
                              <div>
                                <div className="cell-main">{h.symbol}</div>
                                <div className="sym-name">{h.name}</div>
                              </div>
                            </div>
                          </td>
                          <td className="right">${price.toFixed(2)}</td>
                          <td className={`right ${(h.chgPct || 0) >= 0 ? "pnl-pos" : "pnl-neg"}`}>
                            {(h.chgPct || 0) >= 0 ? "+" : ""}{(h.chgPct || 0).toFixed(2)}%
                          </td>
                          <td className="right">{qty}</td>
                          <td className="right cell-main">${val.toFixed(2)}</td>
                          <td className={`right ${pl >= 0 ? "pnl-pos" : "pnl-neg"}`}>
                            {pl >= 0 ? "+" : ""}${pl.toFixed(2)}
                          </td>
                          <td className={`right ${ret >= 0 ? "pnl-pos" : "pnl-neg"}`}>
                            {ret >= 0 ? "+" : ""}{ret.toFixed(2)}%
                          </td>
                          <td><Sparkline positive={(h.chgPct || 0) >= 0} w={72} h={22} /></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
