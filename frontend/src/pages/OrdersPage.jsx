/**
 * Orders Page
 * 
 * Displays open and filled orders with ability to cancel pending orders.
 */

import { useState, useMemo, useEffect, useCallback, useRef } from "react";
import api, { useApi } from "../api/client";
import { Ic } from "../components/common/Icons";
import { SkeletonRow, ApiError } from "../components/common";
import { ORDERS } from "../styles/globals";

export function OrdersPage({ onNewTx, token, accountId, goBack }) {
  const [statusFilter, setStatusFilter] = useState("all");
  const { data: apiOrders, loading, error, refetch } =
    useApi(() => (token && accountId) ? api.listOrders(accountId, token) : Promise.resolve(null), [token, accountId]);

  const allOrders = (apiOrders || []).map(o => ({
    id: o.order_id || o.id,
    symbol: o.symbol || "—",
    side: o.side,
    type: o.order_type || o.type,
    qty: +(o.quantity || o.qty || 0),
    price: o.price != null ? +o.price : null,
    filled: +(o.filled_quantity || o.filled || 0),
    status: o.status,
    placed: o.placed_at || o.placed || "",
  }));
  const filtered    = statusFilter==="all" ? allOrders : allOrders.filter(o=>o.status===statusFilter);
  const openCount   = allOrders.filter(o=>o.status==="open"||o.status==="pending").length;
  const filledCount = allOrders.filter(o=>o.status==="filled").length;

  const handleCancel = async (orderId) => {
    if (!token) return;
    try { await api.cancelOrder(orderId, token); refetch(); }
    catch (e) { console.error("Cancel failed:", e.message); }
  };

  return (
    <div className="page-scroll">
      <div className="page-header">
        <div>
          <div className="page-title"><button className="btn btn-ghost" onClick={goBack} style={{padding:"4px 6px",marginRight:8,verticalAlign:"middle"}}><Ic.back/></button>ORDERS</div>
          <div className="page-sub">{allOrders.length} ORDERS · {openCount} OPEN · {filledCount} FILLED</div>
        </div>
        <div className="page-actions">
          {openCount > 0 && <button className="btn btn-danger">CANCEL ALL OPEN</button>}
          <button className="btn btn-amber" onClick={onNewTx}><Ic.plus/> PLACE ORDER</button>
        </div>
      </div>

      <div className="grid-stats stagger">
        {[
          {lbl:"Total Orders",     val:allOrders.length,  cls:""},
          {lbl:"Open Orders",      val:openCount,          cls:"cyan"},
          {lbl:"Filled Orders",    val:filledCount,        cls:"green"},
          {lbl:"Cancelled",        val:allOrders.filter(o=>o.status==="cancelled").length, cls:""},
          {lbl:"Open Notional",    val:`$${allOrders.filter(o=>o.status==="open"||o.status==="pending").reduce((s,o)=>s+(o.qty||0)*(o.price||0),0).toLocaleString("en-US",{minimumFractionDigits:2})}`,     cls:"amber"},
        ].map((s,i)=>(
          <div key={i} className="stat-block">
            <div className="stat-lbl">{s.lbl}</div>
            <div className={`stat-val${s.cls?" "+s.cls:""}`}>{s.val}</div>
          </div>
        ))}
      </div>

      <div className="page-inner stagger">
        {/* Filter */}
        <div style={{display:"flex",gap:12,alignItems:"center"}}>
          <div className="filter-bar">
            {["all","pending","filled","cancelled"].map(f=>(
              <button key={f} className={`filter-btn${statusFilter===f?" active":""}`} onClick={()=>setStatusFilter(f)}>
                {f === "pending" ? "OPEN" : f.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        {/* Orders table */}
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">ORDER BLOTTER</span>
            <span style={{fontFamily:"var(--font-mono)",fontSize:10,color:"var(--muted)"}}>
              {accountId ? `ACCOUNT ${String(accountId).slice(0,8).toUpperCase()}` : "DEMO"}
            </span>
          </div>
          <div style={{overflowX:"auto"}}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>ORDER ID</th>
                  <th>SYMBOL</th>
                  <th>SIDE</th>
                  <th>TYPE</th>
                  <th className="right">QTY</th>
                  <th className="right">LIMIT PRICE</th>
                  <th className="right">FILLED</th>
                  <th>STATUS</th>
                  <th>PLACED AT</th>
                </tr>
              </thead>
              <tbody>
                {filtered.length===0 ? (
                  <tr><td colSpan={9} style={{textAlign:"center",color:"var(--muted)",padding:"32px"}}>
                    NO ORDERS FOUND
                  </td></tr>
                ) : filtered.map(o=>(
                  <tr key={o.id}>
                    <td style={{fontWeight:500,color:"var(--amber)",fontSize:11}}>{o.id}</td>
                    <td>
                      <div className="cell-symbol">
                        <div className="sym-badge">{o.symbol.slice(0,3)}</div>
                        <span className="cell-main">{o.symbol}</span>
                      </div>
                    </td>
                    <td><span className={`type-chip tc-${o.side}`}>{o.side}</span></td>
                    <td><span className={`type-chip tc-${o.type}`}>{o.type}</span></td>
                    <td className="right">{o.qty}</td>
                    <td className="right">{o.price ? `$${o.price.toFixed(2)}` : <span style={{color:"var(--muted)"}}>MKT</span>}</td>
                    <td className="right">
                      <span style={{color:o.filled===o.qty?"var(--green)":o.filled>0?"var(--amber)":"var(--muted)"}}>
                        {o.filled} / {o.qty}
                      </span>
                    </td>
                    <td>
                      <span className={`status-pill ${
                        o.status==="open"||o.status==="pending"?"sp-open":
                        o.status==="filled"?"sp-filled":
                        "sp-cancelled"
                      }`}>{o.status==="pending"?"open":o.status}</span>
                    </td>
                    <td style={{color:"var(--muted)",fontSize:11}}>{o.placed}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Open orders detail cards */}
        {statusFilter==="all"||statusFilter==="pending" ? (
          <div>
            <div style={{fontFamily:"var(--font-mono)",fontSize:10,color:"var(--muted)",letterSpacing:"1px",marginBottom:10}}>
              OPEN ORDER DETAIL
            </div>
            <div style={{display:"flex",flexDirection:"column",gap:1}}>
              {allOrders.filter(o=>o.status==="open"||o.status==="pending").map(o=>(
                <div key={o.id} style={{
                  background:"var(--panel)", border:"1px solid var(--border)",
                  borderLeft:`2px solid ${o.side==="buy"?"var(--green)":"var(--red)"}`,
                  padding:"12px 16px",
                  display:"flex",alignItems:"center",gap:24,
                }}>
                  <div style={{display:"flex",flexDirection:"column",gap:3,minWidth:100}}>
                    <div style={{fontFamily:"var(--font-mono)",fontSize:11,color:"var(--muted)"}}>{o.id}</div>
                    <div style={{display:"flex",alignItems:"center",gap:8}}>
                      <div className="sym-badge">{o.symbol.slice(0,3)}</div>
                      <span style={{fontFamily:"var(--font-mono)",fontSize:14,fontWeight:600,color:"var(--bright)"}}>{o.symbol}</span>
                    </div>
                  </div>
                  <div>
                    <div style={{fontFamily:"var(--font-mono)",fontSize:10,color:"var(--muted)"}}>SIDE</div>
                    <span className={`type-chip tc-${o.side}`}>{o.side}</span>
                  </div>
                  <div>
                    <div style={{fontFamily:"var(--font-mono)",fontSize:10,color:"var(--muted)"}}>TYPE</div>
                    <span className={`type-chip tc-${o.type}`}>{o.type}</span>
                  </div>
                  <div>
                    <div style={{fontFamily:"var(--font-mono)",fontSize:10,color:"var(--muted)"}}>QTY</div>
                    <div style={{fontFamily:"var(--font-mono)",fontSize:13,fontWeight:500,color:"var(--bright)"}}>{o.qty}</div>
                  </div>
                  <div>
                    <div style={{fontFamily:"var(--font-mono)",fontSize:10,color:"var(--muted)"}}>LIMIT</div>
                    <div style={{fontFamily:"var(--font-mono)",fontSize:13,fontWeight:500,color:"var(--cyan)"}}>
                      {o.price ? `$${o.price.toFixed(2)}` : "MARKET"}
                    </div>
                  </div>
                  <div>
                    <div style={{fontFamily:"var(--font-mono)",fontSize:10,color:"var(--muted)"}}>NOTIONAL</div>
                    <div style={{fontFamily:"var(--font-mono)",fontSize:13,fontWeight:500,color:"var(--amber)"}}>
                      ${o.price ? (o.qty*o.price).toFixed(2) : "—"}
                    </div>
                  </div>
                  <div style={{marginLeft:"auto",display:"flex",gap:8}}>
                    <button className="btn btn-ghost" style={{fontSize:9,padding:"4px 10px"}}>MODIFY</button>
                    <button className="btn btn-danger" style={{fontSize:9,padding:"4px 10px"}}>CANCEL</button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   ROOT APP
───────────────────────────────────────────────────────────────────────────── */

/* ═══════════════════════════════════════════════════════════════════════════
   CHARTS PAGE
═══════════════════════════════════════════════════════════════════════════ */

/* ─────────────────────────────────────────────────────────────────────────────
   CHARTS PAGE — Bloomberg-style interactive stock analysis
   Candlestick chart · Volume bars · SMA overlays · Breakout detection
   Crosshair · Tooltip · Zoom/pan · Custom SMA period
───────────────────────────────────────────────────────────────────────────── */

const CHART_CSS = `
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=IBM+Plex+Mono:wght@300;400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');

.charts-page { display: flex; flex-direction: column; flex: 1; min-height: 0; overflow: hidden; background: #090b0f; }

/* ── Search bar ── */
.chart-search-bar {
  background: #0e1117;
  border-bottom: 1px solid #1e2535;
  padding: 14px 24px;
  display: flex; align-items: center; gap: 16px;
  flex-wrap: wrap;
  flex-shrink: 0;
}
.chart-search-wrap {
  position: relative; display: flex; align-items: center;
}
.chart-search-icon {
  position: absolute; left: 10px; color: #4a5568; pointer-events: none;
}
.chart-search-input {
  background: #141820; border: 1px solid #1e2535;
  padding: 8px 12px 8px 32px;
  font-family: 'IBM Plex Mono', monospace; font-size: 13px;
  color: #e8f0fa; outline: none; width: 220px; border-radius: 2px;
  text-transform: uppercase; letter-spacing: 1px;
  transition: border-color 0.1s;
}
.chart-search-input:focus { border-color: #0f7d40; }
.chart-search-input::placeholder { color: #4a5568; text-transform: none; letter-spacing: 0; }
.search-suggestions {
  position: absolute; top: calc(100% + 4px); left: 0; right: 0;
  background: #141820; border: 1px solid #1e2535;
  z-index: 50; max-height: 200px; overflow-y: auto;
}
.suggestion-item {
  padding: 8px 12px; cursor: pointer;
  font-family: 'IBM Plex Mono', monospace; font-size: 12px;
  display: flex; gap: 12px; align-items: center;
  border-bottom: 1px solid #1e2535; transition: background 0.08s;
}
.suggestion-item:last-child { border-bottom: none; }
.suggestion-item:hover { background: #1a1d2e; }
.sug-sym { color: #0f7d40; font-weight: 600; min-width: 56px; }
.sug-name { color: #718096; font-size: 11px; }

/* ── Watchlist chips ── */
.watchlist { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
.watch-chip {
  padding: 5px 12px; background: #141820; border: 1px solid #1e2535;
  font-family: 'IBM Plex Mono', monospace; font-size: 11px; font-weight: 600;
  color: #718096; cursor: pointer; border-radius: 2px;
  transition: all 0.1s; letter-spacing: 0.5px;
  display: flex; align-items: center; gap: 6px;
}
.watch-chip:hover { border-color: #263045; color: #c8d3e0; }
.watch-chip.active { color: #0f7d40; border-color: #0f7d40; background: rgba(15,125,64,0.06); }
.watch-chip .chip-chg { font-size: 10px; }
.watch-chip .chip-chg.pos { color: #00d97e; }
.watch-chip .chip-chg.neg { color: #f04438; }
.watch-chip-close {
  color: #4a5568; background: none; border: none; cursor: pointer;
  padding: 0; display: flex; align-items: center; font-size: 11px;
  transition: color 0.1s; line-height: 1;
}
.watch-chip-close:hover { color: #f04438; }

/* ── Controls row ── */
.chart-controls {
  background: #0e1117; border-bottom: 1px solid #1e2535;
  padding: 8px 24px; display: flex; align-items: center; gap: 16px;
  flex-shrink: 0;
  flex-wrap: wrap;
}
.ctrl-group { display: flex; gap: 1px; background: #1e2535; }
.ctrl-btn {
  padding: 5px 12px; background: #0e1117; border: none; cursor: pointer;
  font-family: 'IBM Plex Mono', monospace; font-size: 10px; font-weight: 500;
  color: #4a5568; letter-spacing: 0.8px; text-transform: uppercase;
  transition: all 0.1s;
}
.ctrl-btn:hover { background: #141820; color: #c8d3e0; }
.ctrl-btn.active { background: #141820; color: #0f7d40; }

.overlay-toggles { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.overlay-toggle {
  display: flex; align-items: center; gap: 5px; cursor: pointer;
  font-family: 'IBM Plex Mono', monospace; font-size: 10px;
  padding: 4px 10px; border: 1px solid #1e2535; background: #0e1117;
  border-radius: 2px; transition: all 0.1s; user-select: none;
  color: #4a5568;
}
.overlay-toggle:hover { border-color: #263045; color: #718096; }
.overlay-toggle.on { border-color: transparent; }
.overlay-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }

.sma-custom-wrap { display: flex; align-items: center; gap: 6px; }
.sma-custom-input {
  width: 52px; background: #141820; border: 1px solid #1e2535;
  padding: 4px 7px; font-family: 'IBM Plex Mono', monospace; font-size: 11px;
  color: #e8f0fa; outline: none; border-radius: 2px; text-align: center;
  transition: border-color 0.1s;
}
.sma-custom-input:focus { border-color: #a78bfa; }

.ctrl-sep { width: 1px; height: 20px; background: #1e2535; }
.ctrl-label { font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: #4a5568; letter-spacing: 0.5px; }

/* ── Stats bar ── */
.stock-stats-bar {
  background: #0e1117; border-bottom: 1px solid #1e2535;
  padding: 12px 24px; display: flex; gap: 0; align-items: stretch;
  flex-shrink: 0; overflow-x: auto;
}
.stat-sep { width: 1px; background: #1e2535; margin: 0 20px; flex-shrink: 0; }
.stock-stat { display: flex; flex-direction: column; gap: 3px; min-width: 100px; }
.ss-label { font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: #4a5568; letter-spacing: 1px; text-transform: uppercase; }
.ss-value { font-family: 'IBM Plex Mono', monospace; font-size: 18px; font-weight: 600; color: #e8f0fa; line-height: 1; letter-spacing: -0.5px; }
.ss-value.pos { color: #00d97e; }
.ss-value.neg { color: #f04438; }
.ss-value.amber { color: #0f7d40; }
.ss-sub { font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: #4a5568; }
.ss-badge {
  display: inline-flex; align-items: center; gap: 3px;
  font-family: 'IBM Plex Mono', monospace; font-size: 10px; font-weight: 500;
  padding: 2px 7px; border-radius: 1px; align-self: flex-start; margin-top: 2px;
}
.ss-badge.pos { color: #00d97e; background: rgba(0,217,126,0.08); border: 1px solid rgba(0,217,126,0.15); }
.ss-badge.neg { color: #f04438; background: rgba(240,68,56,0.08); border: 1px solid rgba(240,68,56,0.15); }

/* ── Chart area ── */
.chart-main { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-height: 0; }
.chart-canvas-wrap {
  flex: 1; position: relative; cursor: crosshair; overflow: hidden; min-height: 0;
  background: #090b0f; display: flex; flex-direction: column;
}
.chart-canvas-wrap:active { cursor: grabbing; }
.chart-svg { display: block; width: 100%; height: 100%; }

/* ── Tooltip / crosshair ── */
.crosshair-tooltip {
  position: absolute; pointer-events: none;
  background: #141820; border: 1px solid #263045;
  padding: 10px 12px; min-width: 180px;
  font-family: 'IBM Plex Mono', monospace;
  z-index: 30;
  box-shadow: 0 8px 32px rgba(0,0,0,0.7);
}
.tt-date { font-size: 10px; color: #4a5568; letter-spacing: 0.5px; margin-bottom: 7px; border-bottom: 1px solid #1e2535; padding-bottom: 6px; }
.tt-row { display: flex; justify-content: space-between; gap: 16px; font-size: 11px; margin-bottom: 3px; }
.tt-key { color: #4a5568; }
.tt-val { color: #e8f0fa; font-weight: 500; }
.tt-val.pos { color: #00d97e; }
.tt-val.neg { color: #f04438; }
.tt-divider { height: 1px; background: #1e2535; margin: 5px 0; }
.tt-sma { display: flex; align-items: center; gap: 6px; font-size: 11px; margin-bottom: 3px; }
.tt-sma-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.tt-sma-key { color: #4a5568; }
.tt-sma-val { color: #e8f0fa; margin-left: auto; }

/* ── Breakout badge ── */
.breakout-badge {
  position: absolute; pointer-events: none;
  font-family: 'IBM Plex Mono', monospace; font-size: 9px; font-weight: 700;
  padding: 2px 6px; border-radius: 1px; letter-spacing: 0.8px;
  white-space: nowrap; z-index: 10;
}
.bo-bull { background: rgba(0,217,126,0.9); color: #060f08; }
.bo-bear { background: rgba(240,68,56,0.9); color: #fff; }

/* ── Price axis ── */
.price-axis-label {
  font-family: 'IBM Plex Mono', monospace; font-size: 10px; fill: #4a5568;
}
.current-price-line text {
  font-family: 'IBM Plex Mono', monospace; font-size: 10px;
}

/* ── Empty state ── */
.chart-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  height: 100%; gap: 12px;
  font-family: 'IBM Plex Mono', monospace; color: #4a5568;
}
.chart-empty-title { font-family: 'Bebas Neue', sans-serif; font-size: 32px; color: var(--border2); letter-spacing: 2px; }
.chart-empty-sub { font-size: 11px; letter-spacing: 1px; text-transform: uppercase; }

/* ── Legend ── */
.chart-legend {
  position: absolute; top: 12px; left: 16px;
  display: flex; gap: 12px; align-items: center; pointer-events: none; z-index: 5;
  flex-wrap: wrap;
}
.legend-item {
  display: flex; align-items: center; gap: 5px;
  font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: #4a5568;
  background: rgba(9,11,15,0.8); padding: 2px 6px;
}
.legend-line { width: 16px; height: 2px; border-radius: 1px; flex-shrink: 0; }

/* ── Y-axis price tag ── */
.price-tag {
  position: absolute; right: 0;
  font-family: 'IBM Plex Mono', monospace; font-size: 10px; font-weight: 600;
  padding: 2px 6px; pointer-events: none;
}

/* ── Scanline ── */
.charts-page::before {
  content: '';
  position: fixed; inset: 0; z-index: 9999; pointer-events: none;
  background: repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.03) 2px, rgba(0,0,0,0.03) 4px);
}
`;

/* ─── GENERATE REALISTIC OHLCV DATA (5 years = ~1260 trading days) ──────────── */
