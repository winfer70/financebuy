import { useState, useRef, useEffect, useMemo, useCallback } from "react";

/* ═══════════════════════════════════════════════════════════════════════════
   API CLIENT — centralised fetch wrapper with JWT injection + error handling
═══════════════════════════════════════════════════════════════════════════ */
const API_BASE = import.meta.env.VITE_API_URL || "https://ticker-tap.com";

async function apiFetch(path, { method="GET", body, token } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401 && token) {
    // Token expired — dispatch event so App component triggers logout via React state
    window.dispatchEvent(new Event("session-expired"));
    throw new Error("Session expired");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

/* ── Typed API calls ── */
const api = {
  // Auth
  login:            (email, password)    => apiFetch("/auth/login",    { method:"POST", body:{ email, password } }),
  register:         (payload)            => apiFetch("/auth/register",  { method:"POST", body: payload }),

  // Accounts
  listAccounts:     (userId, token)      => apiFetch(`/accounts/?user_id=${userId}`, { token }),

  // Transactions
  listTransactions: (accountId, token)   => apiFetch(`/transactions/?account_id=${accountId}`, { token }),
  createTransaction:(payload, token)     => apiFetch("/transactions/create", { method:"POST", body: payload, token }),

  // Holdings
  listHoldings:     (accountId, token)   => apiFetch(`/holdings/?account_id=${accountId}`, { token }),

  // Orders
  listOrders:       (accountId, token)   => apiFetch(`/orders/?account_id=${accountId}`, { token }),
  cancelOrder:      (orderId, token)     => apiFetch(`/orders/${orderId}/cancel`, { method:"POST", token }),

  // Health check
  health:           ()                   => apiFetch("/health"),

  // Password recovery
  forgotPassword:   (email)              => apiFetch("/auth/forgot-password", { method:"POST", body:{ email } }),
  resetPassword:    (token, new_password)=> apiFetch("/auth/reset-password",  { method:"POST", body:{ token, new_password } }),

  // Market data
  getQuote:         (symbol, token)      => apiFetch(`/market/quote/${symbol}`, { token }),
  getSymbols:       (token)              => apiFetch("/market/symbols", { token }),
  getOhlcv:         (symbol, token, years=5) => apiFetch(`/market/ohlcv/${symbol}?years=${years}`, { token }),
  searchSymbols:    (query, token)       => apiFetch(`/market/search?q=${encodeURIComponent(query)}`, { token }),

  // Portfolio
  getPositions:     (token)              => apiFetch("/portfolio/positions", { token }),
  getPortfolioSummary: (token)           => apiFetch("/portfolio/summary", { token }),
};

/* ── useApi hook: fetch with loading/error/data states ── */
function useApi(fetcher, deps = []) {
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);

  const refetch = useCallback(async () => {
    setLoading(true); setError(null);
    try { setData(await fetcher()); }
    catch(e) { setError(e.message); }
    finally { setLoading(false); }
  }, deps);

  useEffect(() => { refetch(); }, [refetch]);
  return { data, loading, error, refetch };
}

/* ── Skeleton loader ── */
function SkeletonRow({ cols = 6 }) {
  return (
    <tr>
      {Array.from({length: cols}).map((_, i) => (
        <td key={i}>
          <div style={{
            height: 12, borderRadius: 2, background: "var(--border)",
            animation: "lpulse 1.2s ease-in-out infinite",
            animationDelay: `${i * 80}ms`,
            width: `${50 + Math.random() * 40}%`,
          }}/>
        </td>
      ))}
    </tr>
  );
}

function ApiError({ message, onRetry }) {
  return (
    <div style={{
      padding: "20px 24px", display: "flex", alignItems: "center", gap: 16,
      fontFamily: "var(--font-mono)", fontSize: 11,
      background: "rgba(240,68,56,0.06)", border: "1px solid rgba(240,68,56,0.2)",
      borderLeft: "3px solid var(--red)", margin: "0 0 12px",
    }}>
      <span style={{color: "var(--red)", fontWeight: 600}}>API ERROR</span>
      <span style={{color: "var(--mid)", flex: 1}}>{message}</span>
      {onRetry && (
        <button onClick={onRetry} style={{
          background: "none", border: "1px solid var(--border)", cursor: "pointer",
          color: "var(--amber)", fontFamily: "var(--font-mono)", fontSize: 10,
          padding: "3px 10px", letterSpacing: "0.5px",
        }}>RETRY</button>
      )}
    </div>
  );
}


/* ─────────────────────────────────────────────────────────────────────────────
   DESIGN SYSTEM
   Bloomberg-inspired: near-black bg, amber/orange accent like terminal text,
   IBM Plex Mono for data, Bebas Neue for headers, dense information layout,
   subtle scan-line texture, crisp borders, no rounded-corner softness.
───────────────────────────────────────────────────────────────────────────── */

const GLOBAL_CSS = `
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=IBM+Plex+Mono:wght@300;400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg:        #090b0f;
  --bg2:       #0e1117;
  --bg3:       #141820;
  --panel:     #111520;
  --border:    #1e2535;
  --border2:   #263045;
  --amber:     #0f7d40;
  --amber-dim: #094d27;
  --green:     #00d97e;
  --red:       #f04438;
  --blue:      #3d7ef5;
  --cyan:      #0fc0d0;
  --muted:     #4a5568;
  --mid:       #718096;
  --text:      #c8d3e0;
  --bright:    #e8f0fa;
  --font-mono: 'IBM Plex Mono', monospace;
  --font-sans: 'IBM Plex Sans', sans-serif;
  --font-disp: 'Bebas Neue', sans-serif;
}

html { height: 100%; overflow: hidden; }
body { height: 100%; background: var(--bg); color: var(--text); font-family: var(--font-sans); margin: 0; overflow: hidden; max-width: 100vw; }
#root { height: 100%; overflow: hidden; }

::-webkit-scrollbar { width: 3px; height: 3px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--border2); }

/* Scanline overlay */
body::before {
  content: '';
  position: fixed; inset: 0; z-index: 9999; pointer-events: none;
  background: repeating-linear-gradient(
    0deg,
    transparent,
    transparent 2px,
    rgba(0,0,0,0.04) 2px,
    rgba(0,0,0,0.04) 4px
  );
}

/* ── Layout ── */
.app-shell { display: flex; height: 100vh; max-height: 100vh; overflow: hidden; max-width: 100vw; }

/* ── Sidebar ── */
.sidebar {
  width: 180px;
  background: var(--bg2);
  border-right: 1px solid var(--border);
  display: flex; flex-direction: column; align-items: stretch;
  padding: 0;
  flex-shrink: 0;
  z-index: 50;
}
.sidebar-logo {
  width: 100%; height: 48px;
  display: flex; align-items: center; gap: 10px; padding: 0 16px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
}
.logo-glyph {
  font-family: var(--font-disp);
  font-size: 22px;
  color: var(--amber);
  letter-spacing: 0;
  line-height: 1;
}
.logo-name {
  font-family: var(--font-disp);
  font-size: 16px;
  color: var(--bright);
  letter-spacing: 1px;
  line-height: 1;
}
.sidebar-nav { display: flex; flex-direction: column; gap: 2px; padding: 10px 8px; flex: 1; }
.nav-btn {
  width: 100%; height: 36px;
  background: none; border: none; cursor: pointer;
  display: flex; align-items: center; gap: 10px; padding: 0 10px;
  color: var(--muted); border-radius: 4px;
  font-family: var(--font-mono); font-size: 11px; letter-spacing: 0.5px;
  transition: all 0.12s; position: relative; text-align: left;
}
.nav-btn:hover { color: var(--text); background: var(--bg3); }
.nav-btn.active { color: var(--amber); background: rgba(15,125,64,0.08); }
.nav-btn.active::before {
  content: '';
  position: absolute; left: 0; top: 50%; transform: translateY(-50%);
  width: 2px; height: 20px;
  background: var(--amber);
  border-radius: 0 1px 1px 0;
}
.nav-label { flex: 1; }
.nav-tooltip { display: none; }
.sidebar-bottom { padding: 8px 8px 12px; display: flex; flex-direction: column; gap: 2px; }
.avatar-btn {
  width: 32px; height: 32px; border-radius: 2px;
  background: linear-gradient(135deg, var(--amber-dim), #052b16);
  border: 1px solid var(--amber-dim);
  display: flex; align-items: center; justify-content: center;
  font-family: var(--font-mono); font-size: 11px; font-weight: 600;
  color: var(--amber); cursor: pointer;
}

/* ── Main area ── */
.main-area { flex: 1; min-width: 0; display: flex; flex-direction: column; overflow: hidden; }

/* ── Top bar ── */
.topbar {
  height: 48px; flex-shrink: 0;
  background: var(--bg2); border-bottom: 1px solid var(--border);
  display: flex; align-items: center; padding: 0 20px;
  gap: 0;
}
.topbar-breadcrumb {
  display: flex; align-items: center; gap: 6px;
  font-family: var(--font-mono); font-size: 11px; color: var(--muted);
}
.topbar-breadcrumb .current {
  color: var(--amber); font-weight: 500;
}
.topbar-sep { color: var(--border2); margin: 0 4px; }
.ticker-strip {
  flex: 1;
  overflow: hidden; position: relative; margin: 0 24px;
  mask-image: linear-gradient(90deg, transparent, black 60px, black calc(100% - 60px), transparent);
}
.ticker-inner {
  display: flex; gap: 32px; white-space: nowrap;
  animation: tickerScroll 30s linear infinite;
  font-family: var(--font-mono); font-size: 11px;
}
.ticker-item { display: flex; gap: 6px; align-items: center; }
.ticker-sym { color: var(--bright); font-weight: 500; }
.ticker-price { color: var(--text); }
.ticker-chg-pos { color: var(--green); }
.ticker-chg-neg { color: var(--red); }
@keyframes tickerScroll { from { transform: translateX(0) } to { transform: translateX(-50%) } }

.topbar-right {
  display: flex; align-items: center; gap: 12px; flex-shrink: 0;
}
.clock {
  font-family: var(--font-mono); font-size: 12px; color: var(--mid);
}
.market-status {
  display: flex; align-items: center; gap: 5px;
  font-family: var(--font-mono); font-size: 10px;
  color: var(--green); letter-spacing: 0.5px;
}
.market-dot {
  width: 6px; height: 6px; border-radius: 50%; background: var(--green);
  animation: blink 2s ease-in-out infinite;
}
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.3} }

/* ── Page scroll area ── */
.page-scroll { flex: 1; overflow-y: auto; overflow-x: hidden; }

/* ── Page header band ── */
.page-header {
  background: var(--bg2);
  border-bottom: 1px solid var(--border);
  padding: 14px 24px;
  display: flex; align-items: flex-end; justify-content: space-between;
}
.page-title { font-family: var(--font-disp); font-size: 28px; color: var(--bright); letter-spacing: 1px; line-height: 1; }
.page-sub { font-family: var(--font-mono); font-size: 11px; color: var(--muted); margin-top: 4px; }
.page-actions { display: flex; gap: 8px; align-items: center; }

/* ── Buttons ── */
.btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 7px 14px; border: none; cursor: pointer;
  font-family: var(--font-mono); font-size: 11px; font-weight: 500;
  letter-spacing: 0.5px; text-transform: uppercase;
  transition: all 0.1s; border-radius: 2px;
}
.btn-amber { background: var(--amber); color: #e8f0fa; }
.btn-amber:hover { background: #12a050; box-shadow: 0 0 16px rgba(15,125,64,0.4); }
.btn-outline { background: transparent; color: var(--text); border: 1px solid var(--border2); }
.btn-outline:hover { border-color: var(--mid); color: var(--bright); }
.btn-ghost { background: var(--bg3); color: var(--mid); border: 1px solid var(--border); }
.btn-ghost:hover { color: var(--text); border-color: var(--border2); }
.btn-danger { background: transparent; color: var(--red); border: 1px solid rgba(240,68,56,0.3); }
.btn-danger:hover { background: rgba(240,68,56,0.08); }

/* ── Grid layouts ── */
.grid-stats { display: grid; grid-template-columns: repeat(5, 1fr); gap: 1px; background: var(--border); margin-bottom: 1px; }
.grid-2col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.grid-3col { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }
.grid-main { display: grid; grid-template-columns: 1fr 320px; gap: 16px; }

/* ── Stat block ── */
.stat-block {
  background: var(--panel);
  padding: 14px 18px 12px;
}
.stat-lbl {
  font-family: var(--font-mono); font-size: 10px;
  color: var(--muted); letter-spacing: 1px; text-transform: uppercase;
  margin-bottom: 6px;
}
.stat-val {
  font-family: var(--font-mono); font-size: 22px; font-weight: 600;
  color: var(--bright); line-height: 1; letter-spacing: -0.5px;
}
.stat-val.amber { color: var(--amber); }
.stat-val.green { color: var(--green); }
.stat-val.red { color: var(--red); }
.stat-badge {
  display: inline-flex; align-items: center; gap: 3px;
  font-family: var(--font-mono); font-size: 10px; font-weight: 500;
  padding: 2px 6px; margin-top: 5px;
  border-radius: 1px;
}
.badge-green { color: var(--green); background: rgba(0,217,126,0.08); border: 1px solid rgba(0,217,126,0.15); }
.badge-red   { color: var(--red);   background: rgba(240,68,56,0.08);  border: 1px solid rgba(240,68,56,0.15); }
.badge-amber { color: var(--amber); background: rgba(15,125,64,0.08); border: 1px solid rgba(15,125,64,0.15); }
.badge-mid   { color: var(--mid);   background: var(--bg3);            border: 1px solid var(--border); }

/* ── Panel / card ── */
.panel {
  background: var(--panel);
  border: 1px solid var(--border);
}
.panel-header {
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center; justify-content: space-between;
}
.panel-title {
  font-family: var(--font-mono); font-size: 10px; font-weight: 500;
  color: var(--amber); letter-spacing: 1.5px; text-transform: uppercase;
}
.panel-body { padding: 16px; }

/* ── Data table ── */
.data-table { width: 100%; border-collapse: collapse; }
.data-table th {
  text-align: left; padding: 8px 12px;
  font-family: var(--font-mono); font-size: 10px; font-weight: 500;
  color: var(--muted); letter-spacing: 1px; text-transform: uppercase;
  border-bottom: 1px solid var(--border);
  background: var(--bg2); white-space: nowrap;
}
.data-table th.right, .data-table td.right { text-align: right; }
.data-table td {
  padding: 9px 12px;
  font-family: var(--font-mono); font-size: 12px; color: var(--text);
  border-bottom: 1px solid var(--border); white-space: nowrap;
}
.data-table tr:last-child td { border-bottom: none; }
.data-table tbody tr { transition: background 0.08s; cursor: default; }
.data-table tbody tr:hover td { background: rgba(255,255,255,0.02); }

.cell-symbol {
  display: flex; align-items: center; gap: 10px;
}
.sym-badge {
  width: 34px; height: 24px;
  background: var(--bg3); border: 1px solid var(--border2);
  display: flex; align-items: center; justify-content: center;
  font-family: var(--font-mono); font-size: 9px; font-weight: 600;
  color: var(--amber); letter-spacing: 0.5px;
  flex-shrink: 0;
}
.sym-name { font-size: 10px; color: var(--muted); margin-top: 1px; }
.cell-main { font-weight: 500; color: var(--bright); }

.pnl-pos { color: var(--green); }
.pnl-neg { color: var(--red); }

/* ── Inline sparkline ── */
.spark-cell { display: flex; align-items: center; }

/* ── Status pill ── */
.status-pill {
  display: inline-flex; align-items: center; gap: 4px;
  font-family: var(--font-mono); font-size: 10px; font-weight: 500;
  padding: 2px 7px; letter-spacing: 0.5px; text-transform: uppercase;
  border-radius: 1px;
}
.sp-completed { color: var(--green); background: rgba(0,217,126,0.07); border: 1px solid rgba(0,217,126,0.18); }
.sp-pending   { color: var(--amber); background: rgba(15,125,64,0.07); border: 1px solid rgba(15,125,64,0.18); }
.sp-cancelled { color: var(--muted); background: var(--bg3);            border: 1px solid var(--border); }
.sp-filled    { color: var(--blue);  background: rgba(61,126,245,0.07); border: 1px solid rgba(61,126,245,0.18); }
.sp-open      { color: var(--cyan);  background: rgba(15,192,208,0.07); border: 1px solid rgba(15,192,208,0.18); }

/* ── Type chip ── */
.type-chip {
  display: inline-block;
  font-family: var(--font-mono); font-size: 10px; font-weight: 600;
  padding: 2px 7px; letter-spacing: 0.8px; text-transform: uppercase;
  border-radius: 1px;
}
.tc-buy        { color: var(--green); border: 1px solid rgba(0,217,126,0.25); background: rgba(0,217,126,0.06); }
.tc-sell       { color: var(--red);   border: 1px solid rgba(240,68,56,0.25); background: rgba(240,68,56,0.06); }
.tc-deposit    { color: var(--blue);  border: 1px solid rgba(61,126,245,0.25); background: rgba(61,126,245,0.06); }
.tc-withdrawal { color: var(--amber); border: 1px solid rgba(15,125,64,0.25); background: rgba(15,125,64,0.06); }
.tc-market     { color: var(--mid);   border: 1px solid var(--border2); background: var(--bg3); }
.tc-limit      { color: var(--cyan);  border: 1px solid rgba(15,192,208,0.25); background: rgba(15,192,208,0.06); }
.tc-stop       { color: var(--amber); border: 1px solid rgba(15,125,64,0.25); background: rgba(15,125,64,0.06); }

/* ── Page padding ── */
.page-inner { padding: 16px 24px; display: flex; flex-direction: column; gap: 16px; }

/* ── Chart area ── */
.chart-area { position: relative; overflow: hidden; }
.chart-yaxis {
  position: absolute; left: 0; top: 0; bottom: 20px;
  width: 56px; display: flex; flex-direction: column; justify-content: space-between;
  padding: 8px 0;
}
.chart-yval {
  font-family: var(--font-mono); font-size: 10px; color: var(--muted);
  text-align: right; padding-right: 8px;
}
.chart-svg-wrap { margin-left: 56px; }
.chart-gridline { stroke: var(--border); stroke-width: 1; stroke-dasharray: 2,4; }
.chart-line { fill: none; stroke: var(--amber); stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round; }
.chart-fill { stroke: none; }
.chart-xaxis {
  display: flex; justify-content: space-between;
  margin-left: 56px; margin-top: 4px;
}
.chart-xlabel { font-family: var(--font-mono); font-size: 10px; color: var(--muted); }

/* ── Donut ── */
.donut-wrap { display: flex; flex-direction: column; align-items: center; gap: 12px; }
.donut-legend { width: 100%; display: flex; flex-direction: column; gap: 5px; }
.donut-row {
  display: flex; align-items: center; gap: 8px;
  font-family: var(--font-mono); font-size: 11px;
}
.donut-swatch { width: 8px; height: 2px; flex-shrink: 0; }
.donut-sym { color: var(--bright); font-weight: 500; min-width: 40px; }
.donut-pct { color: var(--muted); margin-left: auto; }
.donut-val { color: var(--amber); min-width: 70px; text-align: right; }

/* ── Order book mini ── */
.ob-row {
  display: flex; align-items: center; gap: 8px;
  font-family: var(--font-mono); font-size: 11px;
  padding: 4px 0; border-bottom: 1px solid var(--border);
  position: relative;
}
.ob-row:last-child { border-bottom: none; }
.ob-bar {
  position: absolute; top: 0; bottom: 0; opacity: 0.08;
  border-radius: 1px;
}
.ob-ask-bar { background: var(--red); right: 0; }
.ob-bid-bar { background: var(--green); left: 0; }
.ob-price { min-width: 70px; font-weight: 500; }
.ob-size  { min-width: 60px; color: var(--mid); }
.ob-total { margin-left: auto; color: var(--muted); font-size: 10px; }

/* ── Divider ── */
.hdivider { height: 1px; background: var(--border); }
.vdivider { width: 1px; background: var(--border); }

/* ── Filter bar ── */
.filter-bar {
  display: flex; gap: 1px; background: var(--border);
  border: 1px solid var(--border);
}
.filter-btn {
  padding: 6px 14px; background: var(--bg2);
  border: none; cursor: pointer;
  font-family: var(--font-mono); font-size: 10px; font-weight: 500;
  color: var(--muted); letter-spacing: 0.8px; text-transform: uppercase;
  transition: all 0.1s;
}
.filter-btn:hover { background: var(--bg3); color: var(--text); }
.filter-btn.active { background: var(--panel); color: var(--amber); }

/* ── Search input ── */
.search-input {
  background: var(--bg3); border: 1px solid var(--border);
  padding: 6px 10px; font-family: var(--font-mono); font-size: 11px;
  color: var(--text); outline: none; width: 200px;
  border-radius: 2px;
}
.search-input:focus { border-color: var(--amber); }
.search-input::placeholder { color: var(--muted); }

/* ── Form ── */
.form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.form-field { display: flex; flex-direction: column; gap: 5px; }
.form-label {
  font-family: var(--font-mono); font-size: 10px; font-weight: 500;
  color: var(--muted); letter-spacing: 0.8px; text-transform: uppercase;
}
.form-control {
  background: var(--bg3); border: 1px solid var(--border);
  padding: 9px 11px; font-family: var(--font-mono); font-size: 12px;
  color: var(--bright); outline: none; width: 100%; border-radius: 2px;
  transition: border-color 0.1s;
}
.form-control:focus { border-color: var(--amber); }
.form-control::placeholder { color: var(--muted); }
select.form-control {
  appearance: none; cursor: pointer;
  background-image: url("data:image/svg+xml,%3Csvg width='10' height='6' viewBox='0 0 10 6' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%234a5568' strokeWidth='1.2'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: right 10px center;
  padding-right: 28px;
}
select.form-control option { background: var(--bg3); }
.form-hint { font-family: var(--font-mono); font-size: 10px; color: var(--muted); }

/* ── Modal ── */
.modal-overlay {
  position: fixed; inset: 0; z-index: 200;
  background: rgba(0,0,0,0.75);
  display: flex; align-items: center; justify-content: center;
  animation: fadeIn 0.15s;
}
.modal-box {
  background: var(--panel); border: 1px solid var(--border2);
  width: 460px; max-width: 95vw;
  box-shadow: 0 24px 80px rgba(0,0,0,0.7), 0 0 0 1px rgba(15,125,64,0.06);
  animation: slideUp 0.18s;
}
.modal-top {
  background: var(--bg2); border-bottom: 1px solid var(--border);
  padding: 14px 18px;
  display: flex; align-items: center; justify-content: space-between;
}
.modal-title {
  font-family: var(--font-disp); font-size: 20px; color: var(--bright); letter-spacing: 1px;
}
.modal-close {
  background: none; border: none; cursor: pointer;
  color: var(--muted); transition: color 0.1s;
  width: 28px; height: 28px; display: flex; align-items: center; justify-content: center;
}
.modal-close:hover { color: var(--red); }
.modal-body { padding: 20px 18px; display: flex; flex-direction: column; gap: 14px; }
.modal-footer { padding: 14px 18px; border-top: 1px solid var(--border); display: flex; gap: 8px; justify-content: flex-end; }

/* ── Toast ── */
.toast-stack { position: fixed; bottom: 20px; right: 20px; z-index: 300; display: flex; flex-direction: column; gap: 8px; }
.toast {
  background: var(--panel); border: 1px solid var(--border2);
  border-left: 2px solid var(--green);
  padding: 12px 16px; min-width: 260px;
  font-family: var(--font-mono); font-size: 11px; color: var(--text);
  display: flex; align-items: center; gap: 10px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.5);
  animation: slideInRight 0.2s, fadeOut 0.3s 2.7s forwards;
}
.toast.toast-err { border-left-color: var(--red); }
.toast-icon { flex-shrink: 0; }

/* ─── LOGIN PAGE ─── */
.login-wrap {
  height: 100vh; max-height: 100vh; background: var(--bg);
  display: flex; align-items: stretch;
  position: relative; overflow: hidden;
}
.login-left {
  flex: 1; min-width: 0; display: flex; flex-direction: column;
  justify-content: center; padding: 60px;
  border-right: 1px solid var(--border);
  position: relative; z-index: 1;
  overflow-y: auto;
}
.login-right {
  width: 440px; flex-shrink: 0;
  display: flex; flex-direction: column; justify-content: center;
  padding: 60px 48px;
  background: var(--bg2);
  position: relative; z-index: 1;
  overflow-y: auto;
}
.login-grid-bg {
  position: absolute; inset: 0;
  background-image:
    linear-gradient(var(--border) 1px, transparent 1px),
    linear-gradient(90deg, var(--border) 1px, transparent 1px);
  background-size: 40px 40px;
  opacity: 0.5;
}
.login-glow {
  position: absolute;
  width: 600px; height: 600px; border-radius: 50%;
  background: radial-gradient(circle, rgba(15,125,64,0.05) 0%, transparent 70%);
  top: 50%; left: 40%; transform: translate(-50%, -50%);
  pointer-events: none;
}
.login-brand { margin-bottom: 48px; }
.login-brand-mark {
  font-family: var(--font-disp); font-size: 56px; color: var(--amber);
  letter-spacing: 2px; line-height: 1;
}
.login-brand-sub {
  font-family: var(--font-mono); font-size: 11px; color: var(--muted);
  letter-spacing: 3px; text-transform: uppercase; margin-top: 6px;
}
.login-stats { display: flex; flex-direction: column; gap: 24px; }
.login-stat-row { display: flex; gap: 40px; }
.login-stat-val {
  font-family: var(--font-mono); font-size: 28px; font-weight: 300; color: var(--bright);
  letter-spacing: -1px;
}
.login-stat-lbl { font-family: var(--font-mono); font-size: 10px; color: var(--muted); letter-spacing: 1px; text-transform: uppercase; margin-top: 2px; }
.login-divider { height: 1px; background: linear-gradient(90deg, var(--amber) 0%, transparent 60%); margin: 40px 0 0; }

.login-head {
  font-family: var(--font-disp); font-size: 32px; color: var(--bright);
  letter-spacing: 1px; margin-bottom: 4px;
}
.login-subhead { font-family: var(--font-mono); font-size: 11px; color: var(--muted); margin-bottom: 32px; }
.login-form { display: flex; flex-direction: column; gap: 16px; }
.pw-wrap { position: relative; }
.pw-eye {
  position: absolute; right: 10px; top: 50%; transform: translateY(-50%);
  background: none; border: none; cursor: pointer; color: var(--muted);
  display: flex; align-items: center; transition: color 0.1s;
}
.pw-eye:hover { color: var(--amber); }
.login-btn-full { width: 100%; justify-content: center; padding: 11px; font-size: 12px; letter-spacing: 2px; margin-top: 4px; }
.login-footer-links { display: flex; justify-content: space-between; margin-top: 20px; }
.login-link { font-family: var(--font-mono); font-size: 10px; color: var(--muted); cursor: pointer; letter-spacing: 0.5px; transition: color 0.1s; }
.login-link:hover { color: var(--amber); }
.login-security {
  margin-top: 40px; padding-top: 20px; border-top: 1px solid var(--border);
  font-family: var(--font-mono); font-size: 10px; color: var(--muted);
  display: flex; gap: 16px;
}
.security-item { display: flex; align-items: center; gap: 4px; }

/* ── Animations ── */
@keyframes fadeIn { from{opacity:0} to{opacity:1} }
@keyframes slideUp { from{transform:translateY(12px);opacity:0} to{transform:translateY(0);opacity:1} }
@keyframes slideInRight { from{transform:translateX(20px);opacity:0} to{transform:translateX(0);opacity:1} }
@keyframes fadeOut { from{opacity:1} to{opacity:0;transform:translateY(6px)} }
@keyframes stagger0 { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:translateY(0)} }

.stagger > * { animation: stagger0 0.25s both; }
.stagger > *:nth-child(1){animation-delay:0ms}
.stagger > *:nth-child(2){animation-delay:50ms}
.stagger > *:nth-child(3){animation-delay:100ms}
.stagger > *:nth-child(4){animation-delay:150ms}
.stagger > *:nth-child(5){animation-delay:200ms}
.stagger > *:nth-child(6){animation-delay:250ms}
.stagger > *:nth-child(7){animation-delay:300ms}
.stagger > *:nth-child(8){animation-delay:350ms}

.loading-pulse {
  animation: lpulse 0.8s ease-in-out infinite;
}
@keyframes lpulse { 0%,100%{opacity:1} 50%{opacity:0.4} }

/* ── Footer ── */
.app-footer {
  background: var(--bg2); border-top: 1px solid var(--border);
  padding: 8px 24px; display: flex; align-items: center; justify-content: space-between;
  font-family: var(--font-mono); font-size: 10px; color: var(--muted);
  letter-spacing: 0.4px; flex-shrink: 0; gap: 16px;
}
.app-footer a { color: var(--amber); text-decoration: none; }
.app-footer a:hover { text-decoration: underline; }
`;

/* ─── MOCK DATA ─────────────────────────────────────────────────────────────── */
const HOLDINGS = [
  { symbol:"AAPL", name:"Apple Inc.",         qty:12.5, avg:142.30, price:189.45, chg:+2.34, chgPct:+1.25 },
  { symbol:"MSFT", name:"Microsoft Corp.",    qty:8,    avg:310.00, price:378.90, chg:+4.22, chgPct:+1.12 },
  { symbol:"NVDA", name:"NVIDIA Corp.",       qty:5,    avg:480.00, price:721.28, chg:+34.6, chgPct:+4.87 },
  { symbol:"TSLA", name:"Tesla Inc.",         qty:15,   avg:251.40, price:213.65, chg:-4.12, chgPct:-1.90 },
  { symbol:"AMZN", name:"Amazon.com Inc.",    qty:6,    avg:180.00, price:196.40, chg:+1.43, chgPct:+0.73 },
  { symbol:"GOOGL", name:"Alphabet Inc.",     qty:4,    avg:155.00, price:172.30, chg:+0.87, chgPct:+0.51 },
  { symbol:"META", name:"Meta Platforms",     qty:10,   avg:320.00, price:492.80, chg:+8.32, chgPct:+1.72 },
];

const TRANSACTIONS = [
  { id:"TXN-0012", type:"buy",        symbol:"NVDA",  amount:2401.40, status:"completed", date:"2026-02-23", currency:"USD", acct:"ACC-4821" },
  { id:"TXN-0011", type:"deposit",    symbol:null,    amount:10000.0, status:"completed", date:"2026-02-20", currency:"USD", acct:"ACC-4821" },
  { id:"TXN-0010", type:"sell",       symbol:"TSLA",  amount:1282.50, status:"completed", date:"2026-02-18", currency:"USD", acct:"ACC-4821" },
  { id:"TXN-0009", type:"buy",        symbol:"AAPL",  amount:1893.75, status:"pending",   date:"2026-02-23", currency:"USD", acct:"ACC-4821" },
  { id:"TXN-0008", type:"withdrawal", symbol:null,    amount:2500.00, status:"completed", date:"2026-02-15", currency:"USD", acct:"ACC-4821" },
  { id:"TXN-0007", type:"buy",        symbol:"MSFT",  amount:3031.20, status:"completed", date:"2026-02-12", currency:"USD", acct:"ACC-4821" },
  { id:"TXN-0006", type:"sell",       symbol:"GOOGL", amount:688.00,  status:"completed", date:"2026-02-10", currency:"USD", acct:"ACC-4821" },
  { id:"TXN-0005", type:"buy",        symbol:"META",  amount:4928.00, status:"completed", date:"2026-02-06", currency:"USD", acct:"ACC-4821" },
];

const ORDERS = [
  { id:"ORD-1024", symbol:"GOOGL", side:"buy",  type:"limit",  qty:3,  price:165.00, status:"open",      filled:0,   placed:"2026-02-23 09:31" },
  { id:"ORD-1023", symbol:"META",  side:"buy",  type:"market", qty:5,  price:null,   status:"filled",    filled:5,   placed:"2026-02-22 14:05" },
  { id:"ORD-1022", symbol:"TSLA",  side:"sell", type:"stop",   qty:8,  price:200.00, status:"open",      filled:0,   placed:"2026-02-21 11:22" },
  { id:"ORD-1021", symbol:"AAPL",  side:"buy",  type:"limit",  qty:10, price:185.00, status:"cancelled", filled:0,   placed:"2026-02-19 09:45" },
  { id:"ORD-1020", symbol:"NVDA",  side:"buy",  type:"limit",  qty:2,  price:700.00, status:"open",      filled:0,   placed:"2026-02-18 10:00" },
  { id:"ORD-1019", symbol:"MSFT",  side:"sell", type:"limit",  qty:3,  price:395.00, status:"filled",    filled:3,   placed:"2026-02-17 15:50" },
];

const TICKER_DATA = [
  { sym:"AAPL",  price:"189.45", chg:"+1.25%", pos:true  },
  { sym:"MSFT",  price:"378.90", chg:"+1.12%", pos:true  },
  { sym:"NVDA",  price:"721.28", chg:"+4.87%", pos:true  },
  { sym:"TSLA",  price:"213.65", chg:"-1.90%", pos:false },
  { sym:"AMZN",  price:"196.40", chg:"+0.73%", pos:true  },
  { sym:"GOOGL", price:"172.30", chg:"+0.51%", pos:true  },
  { sym:"META",  price:"492.80", chg:"+1.72%", pos:true  },
  { sym:"SPX",   price:"5831.2", chg:"+0.84%", pos:true  },
  { sym:"NDX",   price:"20542",  chg:"+1.03%", pos:true  },
  { sym:"DJI",   price:"43287",  chg:"+0.42%", pos:true  },
  { sym:"BTC",   price:"94,210", chg:"-0.38%", pos:false },
  { sym:"GOLD",  price:"2,943",  chg:"+0.91%", pos:true  },
];

/* ─── ICONS (minimal SVG) ──────────────────────────────────────────────────── */
const Ic = {
  dashboard:    ()=><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/></svg>,
  transactions: ()=><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M7 16V4m0 0L3 8m4-4l4 4M17 8v12m0 0l4-4m-4 4l-4-4"/></svg>,
  holdings:     ()=><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M3 3v18h18"/><path d="M7 16l4-4 4 4 4-6"/></svg>,
  orders:       ()=><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/><path d="M9 12h6M9 16h4"/></svg>,
  plus:         ()=><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14"/></svg>,
  close:        ()=><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>,
  up:           ()=><svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M12 4l9 16H3z"/></svg>,
  down:         ()=><svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M12 20l9-16H3z"/></svg>,
  eye:          ()=><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>,
  eyeOff:       ()=><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19M1 1l22 22"/></svg>,
  logout:       ()=><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9"/></svg>,
  lock:         ()=><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>,
  shield:       ()=><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>,
  search:       ()=><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>,
  filter:       ()=><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M22 3H2l8 9.46V19l4 2v-8.54z"/></svg>,
  check:        ()=><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M20 6L9 17l-5-5"/></svg>,
  charts:       ()=><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="2" y="2" width="20" height="20" rx="1"/><path d="M8 16V10M12 16V7M16 16v-4"/></svg>,
  import:       ()=><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>,
  upload:       ()=><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12"/></svg>,
  file:         ()=><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/></svg>,
  trash:        ()=><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/></svg>,
  externalLink: ()=><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3"/></svg>,
  back:         ()=><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>,
};

/* ─── MINI SPARKLINE SVG ────────────────────────────────────────────────────── */
function Sparkline({ positive, w=80, h=24 }) {
  const pts = useRef(Array.from({length:18},(_,i)=>{
    const t = positive ? i*1.3 : -i*0.8;
    return t + (Math.random()-0.45)*5;
  })).current;
  const mn = Math.min(...pts), mx = Math.max(...pts), rng = mx-mn||1;
  const norm = pts.map((v,i)=>({ x:(i/(pts.length-1))*w, y:h-((v-mn)/rng)*(h-4)-2 }));
  const line = norm.map((p,i)=>`${i===0?"M":"L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const fill = line+` L${w},${h} L0,${h} Z`;
  const c = positive ? "#00d97e" : "#f04438";
  const id = `sg${positive?1:0}${w}`;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{display:"block"}}>
      <defs>
        <linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={c} stopOpacity="0.25"/>
          <stop offset="100%" stopColor={c} stopOpacity="0"/>
        </linearGradient>
      </defs>
      <path d={fill} fill={`url(#${id})`}/>
      <path d={line} fill="none" stroke={c} strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

/* ─── AREA CHART (portfolio) ─────────────────────────────────────────────────── */
function PortfolioChart({ height=160, data=null, period="3M" }) {
  const raw = useMemo(() => {
    if (data && data.length > 0) return data.map(d => typeof d === "number" ? d : d.close || d);
    return Array.from({length:60},(_,i)=>
      42000 + i*380 + (Math.sin(i*0.4)*800) + ((Math.sin(i*1.7+3)*0.5+0.15))*1200
    );
  }, [data]);
  const [hover, setHover] = useState(null);
  const svgRef = useRef(null);
  const W=600, H=height;
  const mn=Math.min(...raw), mx=Math.max(...raw), rng=mx-mn||1;
  const pts = raw.map((v,i)=>({
    x:(i/(raw.length-1))*W,
    y:H-((v-mn)/rng)*(H-16)-8
  }));
  const line = pts.map((p,i)=>`${i===0?"M":"L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const fill = line+` L${W},${H} L0,${H} Z`;
  const yVals = [mx, (mx+mn)/2, mn].map(v=>"$"+(v/1000).toFixed(1)+"K");
  const xLabels = ["DEC '25","JAN '26","FEB '26"];

  const handleMouseMove = useCallback((e) => {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const relX = (e.clientX - rect.left) / rect.width * W;
    const idx = Math.min(Math.max(Math.round((relX / W) * (raw.length - 1)), 0), raw.length - 1);
    setHover({ idx, x: pts[idx].x, y: pts[idx].y, value: raw[idx] });
  }, [raw, pts]);

  return (
    <div className="chart-area" style={{position:"relative"}}>
      <div className="chart-yaxis">
        {yVals.map((v,i)=><div key={i} className="chart-yval">{v}</div>)}
      </div>
      <div className="chart-svg-wrap">
        <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} width="100%" height={H} preserveAspectRatio="none"
             onMouseMove={handleMouseMove} onMouseLeave={()=>setHover(null)} style={{cursor:"crosshair"}}>
          <defs>
            <linearGradient id="ag" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="#0f7d40" stopOpacity="0.18"/>
              <stop offset="100%" stopColor="#0f7d40" stopOpacity="0"/>
            </linearGradient>
          </defs>
          {[H*0.1,H*0.5,H*0.9].map((y,i)=>(
            <line key={i} x1="0" y1={y} x2={W} y2={y} className="chart-gridline"/>
          ))}
          <path d={fill} fill="url(#ag)" className="chart-fill"/>
          <path d={line} className="chart-line"/>
          {hover && (
            <>
              <line x1={hover.x} y1={0} x2={hover.x} y2={H} stroke="var(--muted)" strokeWidth="0.5" strokeDasharray="2,2"/>
              <circle cx={hover.x} cy={hover.y} r="4" fill="#0f7d40" stroke="var(--panel)" strokeWidth="2"/>
            </>
          )}
          {!hover && (
            <>
              <circle cx={pts[pts.length-1].x} cy={pts[pts.length-1].y} r="3" fill="#0f7d40"/>
              <circle cx={pts[pts.length-1].x} cy={pts[pts.length-1].y} r="6" fill="#0f7d40" opacity="0.2"/>
            </>
          )}
        </svg>
        {hover && (
          <div style={{
            position:"absolute", left:`${(hover.x/W)*100}%`, top:hover.y-36,
            transform:"translateX(-50%)", background:"var(--bg2)", border:"1px solid var(--border)",
            padding:"4px 8px", borderRadius:2, pointerEvents:"none",
            fontFamily:"var(--font-mono)", fontSize:10, color:"var(--amber)",
            whiteSpace:"nowrap", zIndex:5,
          }}>
            ${(hover.value/1000).toFixed(2)}K
          </div>
        )}
      </div>
      <div className="chart-xaxis">
        {xLabels.map((l,i)=><div key={i} className="chart-xlabel">{l}</div>)}
      </div>
    </div>
  );
}

/* ─── DONUT CHART ──────────────────────────────────────────────────────────── */
const PALETTE = ["#0f7d40","#3d7ef5","#00d97e","#f04438","#0fc0d0","#a78bfa","#fb923c"];

function AllocationDonut({ holdings: holdingsProp = null }) {
  const [hoverIdx, setHoverIdx] = useState(null);
  const data = holdingsProp || [];
  const total = data.reduce((s,h)=>s+(h.quantity||h.qty||0)*(h.current_price||h.price||0),0);
  if (total === 0) return (
    <div style={{fontFamily:"var(--font-mono)",fontSize:11,color:"var(--muted)",padding:"24px 0",textAlign:"center"}}>
      NO ALLOCATION DATA
    </div>
  );
  const slices = data.map((h,i)=>({
    symbol: h.symbol,
    name: h.name || h.symbol,
    qty: h.quantity||h.qty||0,
    val: (h.quantity||h.qty||0)*(h.current_price||h.price||0),
    pct: ((h.quantity||h.qty||0)*(h.current_price||h.price||0)/total)*100,
    color: PALETTE[i % PALETTE.length],
  }));
  const R=52, cx=60, cy=60, gap=0.03;
  let angle = -Math.PI/2;
  const paths = slices.map(s=>{
    const sweep = (s.pct/100)*(2*Math.PI) - gap;
    const x1=cx+R*Math.cos(angle), y1=cy+R*Math.sin(angle);
    const x2=cx+R*Math.cos(angle+sweep), y2=cy+R*Math.sin(angle+sweep);
    const large = sweep > Math.PI ? 1 : 0;
    const d = `M${cx},${cy} L${x1.toFixed(2)},${y1.toFixed(2)} A${R},${R} 0 ${large},1 ${x2.toFixed(2)},${y2.toFixed(2)} Z`;
    angle += sweep + gap;
    return { d, color: s.color, symbol: s.symbol, pct: s.pct, val: s.val };
  });
  return (
    <div style={{display:"flex",gap:16,alignItems:"flex-start"}}>
      <svg viewBox="0 0 120 120" width={110} height={110} style={{flexShrink:0}}>
        {paths.map((p,i)=>(
          <path key={i} d={p.d} fill={p.color}
            opacity={hoverIdx === null ? 0.88 : hoverIdx === i ? 1 : 0.4}
            stroke="var(--panel)" strokeWidth="1"
            style={{cursor:"pointer",transition:"opacity 0.15s"}}
            onMouseEnter={()=>setHoverIdx(i)} onMouseLeave={()=>setHoverIdx(null)}
          />
        ))}
        <circle cx={cx} cy={cy} r={32} fill="var(--panel)"/>
        {hoverIdx !== null ? (
          <>
            <text x={cx} y={cy-10} textAnchor="middle" fill={slices[hoverIdx].color} fontSize="8" fontFamily="IBM Plex Mono" fontWeight="600">
              {slices[hoverIdx].symbol}
            </text>
            <text x={cx} y={cy+2} textAnchor="middle" fill="var(--text)" fontSize="9" fontFamily="IBM Plex Mono">
              {slices[hoverIdx].pct.toFixed(1)}%
            </text>
            <text x={cx} y={cy+14} textAnchor="middle" fill="var(--amber)" fontSize="9" fontFamily="IBM Plex Mono">
              ${(slices[hoverIdx].val/1000).toFixed(2)}K
            </text>
          </>
        ) : (
          <>
            <text x={cx} y={cy-5} textAnchor="middle" fill="var(--muted)" fontSize="8" fontFamily="IBM Plex Mono" letterSpacing="1">TOTAL</text>
            <text x={cx} y={cy+10} textAnchor="middle" fill="var(--amber)" fontSize="11" fontFamily="IBM Plex Mono" fontWeight="600">
              ${(total/1000).toFixed(1)}K
            </text>
          </>
        )}
      </svg>
      <div className="donut-legend">
        {slices.map((s,i)=>(
          <div key={i} className="donut-row"
            style={{opacity: hoverIdx === null ? 1 : hoverIdx === i ? 1 : 0.4, transition:"opacity 0.15s", cursor:"pointer"}}
            onMouseEnter={()=>setHoverIdx(i)} onMouseLeave={()=>setHoverIdx(null)}
          >
            <div className="donut-swatch" style={{background:s.color}}/>
            <span className="donut-sym">{s.symbol}</span>
            <span style={{color:"var(--mid)",fontSize:10,fontFamily:"var(--font-mono)"}}>
              {s.pct.toFixed(1)}%
            </span>
            <span className="donut-val">${(s.val/1000).toFixed(2)}K</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ─── CLOCK ────────────────────────────────────────────────────────────────── */
function Clock() {
  const [time, setTime] = useState(() => new Date());
  useEffect(()=>{ const id = setInterval(()=>setTime(new Date()),1000); return ()=>clearInterval(id); },[]);
  const fmt = t => t.toLocaleTimeString("en-US",{hour:"2-digit",minute:"2-digit",second:"2-digit",hour12:false});
  const tzAbbr = time.toLocaleTimeString("en-US", { timeZoneName: "short" }).split(" ").pop();
  return <span className="clock">{fmt(time)} {tzAbbr}</span>;
}

/* ─── NYSE MARKET STATUS ──────────────────────────────────────────────────── */
function useMarketStatus() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30000);
    return () => clearInterval(id);
  }, []);

  const etStr = now.toLocaleString("en-US", { timeZone: "America/New_York" });
  const et = new Date(etStr);
  const day = et.getDay();
  const totalMin = et.getHours() * 60 + et.getMinutes();

  const openMin = 9 * 60 + 30;   // 9:30 AM ET
  const closeMin = 16 * 60;      // 4:00 PM ET
  const isWeekday = day >= 1 && day <= 5;
  const isOpen = isWeekday && totalMin >= openMin && totalMin < closeMin;

  let countdown = "";
  if (!isOpen) {
    const nextOpen = new Date(et);
    if (isWeekday && totalMin < openMin) {
      nextOpen.setHours(9, 30, 0, 0);
    } else {
      nextOpen.setDate(nextOpen.getDate() + 1);
      while (nextOpen.getDay() === 0 || nextOpen.getDay() === 6) {
        nextOpen.setDate(nextOpen.getDate() + 1);
      }
      nextOpen.setHours(9, 30, 0, 0);
    }
    const diffMs = nextOpen - et;
    const diffH = Math.floor(diffMs / 3600000);
    const diffM = Math.floor((diffMs % 3600000) / 60000);
    countdown = `${diffH}H ${diffM}M`;
  }

  const dateStr = now.toLocaleDateString("en-US", {
    weekday: "short", day: "2-digit", month: "short", year: "numeric",
  }).toUpperCase();
  const timeStr = now.toLocaleTimeString("en-US", {
    hour: "2-digit", minute: "2-digit", hour12: false, timeZoneName: "short",
  });

  return { isOpen, countdown, dateStr, timeStr };
}

/* ─── FOOTER ───────────────────────────────────────────────────────────────── */
function Footer() {
  const year = new Date().getFullYear();
  return (
    <footer className="app-footer">
      <span>&copy; {year} Ticker-Tap. All rights reserved.</span>
      <span>Market data provided by Yahoo Finance. Not financial advice.</span>
    </footer>
  );
}

/* ─── TICKER STRIP ─────────────────────────────────────────────────────────── */
function TickerStrip({ token }) {
  const SYMBOLS = ["AAPL","MSFT","NVDA","TSLA","AMZN","GOOGL","META","SPY","QQQ","AMD"];
  const [quotes, setQuotes] = useState(TICKER_DATA);
  const mktStatus = useMarketStatus();
  const pollMs = mktStatus.isOpen ? 3000 : 300000;

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    const fetchQuotes = () => {
      Promise.allSettled(SYMBOLS.map(s => api.getQuote(s, token)))
        .then(results => {
          if (cancelled) return;
          const live = results
            .filter(r => r.status === "fulfilled")
            .map(r => ({
              sym: r.value.symbol,
              price: Number(r.value.price).toFixed(2),
              chg: `${r.value.change_pct >= 0 ? "+" : ""}${Number(r.value.change_pct).toFixed(2)}%`,
              pos: r.value.change_pct >= 0,
            }));
          if (live.length > 0) setQuotes(live);
        });
    };
    fetchQuotes();
    const id = setInterval(fetchQuotes, pollMs);
    return () => { cancelled = true; clearInterval(id); };
  }, [token, pollMs]);

  const doubled = [...quotes,...quotes];
  return (
    <div className="ticker-strip">
      <div className="ticker-inner">
        {doubled.map((t,i)=>(
          <div key={i} className="ticker-item">
            <span className="ticker-sym">{t.sym}</span>
            <span className="ticker-price">{t.price}</span>
            <span className={t.pos ? "ticker-chg-pos":"ticker-chg-neg"}>{t.chg}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ─── TOAST SYSTEM ─────────────────────────────────────────────────────────── */
function ToastContainer({ toasts }) {
  return (
    <div className="toast-stack">
      {toasts.map(t=>(
        <div key={t.id} className={`toast${t.err?" toast-err":""}`}>
          <span className="toast-icon" style={{color:t.err?"var(--red)":"var(--green)"}}>
            {t.err ? <Ic.close/> : <Ic.check/>}
          </span>
          {t.msg}
        </div>
      ))}
    </div>
  );
}

/* ─── NEW TRANSACTION MODAL ─────────────────────────────────────────────────── */
function TxModal({ onClose, onSubmit }) {
  const [form, setForm] = useState({
    account_id: "ACC-4821",
    transaction_type: "deposit",
    amount: "",
    currency: "USD",
    symbol: "",
  });
  const [loading, setLoading] = useState(false);
  const [err, setErr]         = useState("");
  const needsSymbol = ["buy","sell"].includes(form.transaction_type);

  const handle = async () => {
    if (!form.amount || isNaN(+form.amount) || +form.amount <= 0) return;
    setLoading(true);
    try {
      await onSubmit(form);
      onClose();
    } catch(e) {
      setErr(e.message || "Transaction failed");
    } finally {
      setLoading(false);
    }
  };

  const set = (k,v) => setForm(f=>({...f,[k]:v}));

  return (
    <div className="modal-overlay" onClick={e=>e.target===e.currentTarget&&onClose()}>
      <div className="modal-box">
        <div className="modal-top">
          <div className="modal-title">NEW TRANSACTION</div>
          <button className="modal-close" onClick={onClose}><Ic.close/></button>
        </div>
        <div className="modal-body">
          <div className="form-field">
            <label className="form-label">Account ID</label>
            <input className="form-control" value={form.account_id} onChange={e=>set("account_id",e.target.value)}/>
          </div>
          <div className="form-row">
            <div className="form-field">
              <label className="form-label">Transaction Type</label>
              <select className="form-control" value={form.transaction_type} onChange={e=>set("transaction_type",e.target.value)}>
                <option value="deposit">DEPOSIT</option>
                <option value="withdrawal">WITHDRAWAL</option>
                <option value="buy">BUY</option>
                <option value="sell">SELL</option>
              </select>
            </div>
            <div className="form-field">
              <label className="form-label">Currency</label>
              <select className="form-control" value={form.currency} onChange={e=>set("currency",e.target.value)}>
                <option>USD</option><option>EUR</option><option>GBP</option>
              </select>
            </div>
          </div>
          {needsSymbol && (
            <div className="form-field">
              <label className="form-label">Symbol</label>
              <input className="form-control" placeholder="e.g. AAPL" value={form.symbol} onChange={e=>set("symbol",e.target.value.toUpperCase())}/>
            </div>
          )}
          <div className="form-field">
            <label className="form-label">Amount (USD)</label>
            <input className="form-control" type="number" min="0.01" step="0.01" placeholder="0.00"
              value={form.amount} onChange={e=>set("amount",e.target.value)}/>
            <span className="form-hint">Positive values only. Server validates on /transactions/create</span>
          </div>
        </div>
        {err && (
          <div style={{padding:"8px 20px",fontFamily:"var(--font-mono)",fontSize:11,color:"var(--red)",background:"rgba(240,68,56,0.06)",borderTop:"1px solid rgba(240,68,56,0.2)"}}>
            ⚠ {err}
          </div>
        )}
        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose}>CANCEL</button>
          <button className="btn btn-amber" onClick={handle} disabled={loading}>
            {loading ? <span className="loading-pulse">SUBMITTING...</span> : "SUBMIT ORDER"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   PAGE: FORGOT PASSWORD
───────────────────────────────────────────────────────────────────────────── */
function ForgotPasswordPage({ onBack, backendOk }) {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [err, setErr] = useState("");

  const handleSubmit = async () => {
    if (!email) { setErr("EMAIL REQUIRED"); return; }
    setErr(""); setLoading(true);
    try {
      await api.forgotPassword(email);
      setSent(true);
    } catch(e) {
      setErr(e.message || "REQUEST FAILED");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-wrap">
      <div className="login-grid-bg"/>
      <div className="login-glow"/>
      <div className="login-left">
        <div className="login-brand">
          <div className="login-brand-mark">TICKER-TAP</div>
          <div className="login-brand-sub">Professional Investment Terminal · v4.2</div>
        </div>
        <div className="login-stats stagger">
          <div className="login-stat-row">
            {[{val:"$2.4B",lbl:"Assets Under Management"},{val:"147K",lbl:"Active Accounts"}].map((s,i)=>(
              <div key={i}><div className="login-stat-val">{s.val}</div><div className="login-stat-lbl">{s.lbl}</div></div>
            ))}
          </div>
          <div className="login-stat-row">
            {[{val:"99.97%",lbl:"System Uptime"},{val:"< 4ms",lbl:"Avg Execution Time"}].map((s,i)=>(
              <div key={i}><div className="login-stat-val">{s.val}</div><div className="login-stat-lbl">{s.lbl}</div></div>
            ))}
          </div>
        </div>
        <div className="login-divider"/>
        <div style={{marginTop:24,display:"flex",flexDirection:"column",gap:8}}>
          {TICKER_DATA.slice(0,5).map((t,i)=>(
            <div key={i} style={{display:"flex",alignItems:"center",gap:12,fontFamily:"var(--font-mono)",fontSize:12}}>
              <span style={{color:"var(--bright)",minWidth:50,fontWeight:500}}>{t.sym}</span>
              <span style={{color:"var(--mid)"}}>{t.price}</span>
              <span style={{color:t.pos?"var(--green)":"var(--red)"}}>{t.chg}</span>
              <Sparkline positive={t.pos} w={80} h={18}/>
            </div>
          ))}
        </div>
      </div>
      <div className="login-right">
        <div className="login-head">RESET PASSWORD</div>
        <div className="login-subhead">Enter your account email to receive a reset link</div>
        <div className="login-form">
          {sent ? (
            <div style={{display:"flex",flexDirection:"column",gap:16}}>
              <div style={{
                fontFamily:"var(--font-mono)",fontSize:12,color:"var(--green)",
                border:"1px solid var(--green)",borderRadius:2,padding:"14px 16px",lineHeight:1.6
              }}>
                CHECK YOUR EMAIL<br/>
                <span style={{color:"var(--mid)",fontSize:11}}>A reset link has been sent to <strong style={{color:"var(--bright)"}}>{email}</strong>. It expires in 1 hour.</span>
              </div>
              <div className="login-footer-links">
                <span className="login-link" onClick={onBack}>← Back to sign in</span>
              </div>
            </div>
          ) : (
            <>
              <div className="form-field">
                <label className="form-label">Email Address</label>
                <input className="form-control" type="email" value={email}
                  onChange={e=>setEmail(e.target.value)}
                  onKeyDown={e=>e.key==="Enter"&&handleSubmit()}
                  placeholder="you@example.com"/>
              </div>
              {err && <div style={{fontFamily:"var(--font-mono)",fontSize:11,color:"var(--red)"}}>{err}</div>}
              <button className="btn btn-amber login-btn-full" onClick={handleSubmit} disabled={loading||!backendOk}>
                {loading ? <span className="loading-pulse">SENDING...</span> : "SEND RESET LINK"}
              </button>
              {backendOk===false && (
                <div style={{fontFamily:"var(--font-mono)",fontSize:11,color:"var(--amber)"}}>
                  BACKEND OFFLINE — PASSWORD RESET UNAVAILABLE IN DEMO MODE
                </div>
              )}
              <div className="login-footer-links">
                <span className="login-link" onClick={onBack}>← Back to sign in</span>
              </div>
            </>
          )}
        </div>
        <div className="login-security">
          <div className="security-item"><Ic.lock/> TLS 1.3 Encrypted</div>
          <div className="security-item"><Ic.shield/> SOC 2 Compliant</div>
          <div className="security-item" style={{color:backendOk===false?"var(--amber)":"var(--green)",display:"flex",alignItems:"center",gap:4}}>
            <span style={{width:5,height:5,borderRadius:"50%",background:backendOk===false?"var(--amber)":"var(--green)",display:"inline-block"}}/>
            {backendOk===null?"Checking API...":backendOk?"API Connected":"Demo Mode (API Offline)"}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   PAGE: RESET PASSWORD (token from email link)
───────────────────────────────────────────────────────────────────────────── */
function ResetPasswordPage({ resetToken, onBack, onSuccess }) {
  const [pwd, setPwd]   = useState("");
  const [pwd2, setPwd2] = useState("");
  const [show, setShow] = useState(false);
  const [loading, setLoading] = useState(false);
  const [done, setDone]   = useState(false);
  const [err, setErr]     = useState("");

  const handleSubmit = async () => {
    if (!pwd)             { setErr("PASSWORD REQUIRED"); return; }
    if (pwd.length < 8)   { setErr("PASSWORD MIN 8 CHARACTERS"); return; }
    if (pwd !== pwd2)     { setErr("PASSWORDS DO NOT MATCH"); return; }
    setErr(""); setLoading(true);
    try {
      await api.resetPassword(resetToken, pwd);
      setDone(true);
      setTimeout(onSuccess, 2500);
    } catch(e) {
      setErr(e.message || "RESET FAILED — LINK MAY HAVE EXPIRED");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-wrap">
      <div className="login-grid-bg"/>
      <div className="login-glow"/>
      <div className="login-left">
        <div className="login-brand">
          <div className="login-brand-mark">TICKER-TAP</div>
          <div className="login-brand-sub">Professional Investment Terminal · v4.2</div>
        </div>
        <div className="login-stats stagger">
          <div className="login-stat-row">
            {[{val:"$2.4B",lbl:"Assets Under Management"},{val:"147K",lbl:"Active Accounts"}].map((s,i)=>(
              <div key={i}><div className="login-stat-val">{s.val}</div><div className="login-stat-lbl">{s.lbl}</div></div>
            ))}
          </div>
          <div className="login-stat-row">
            {[{val:"99.97%",lbl:"System Uptime"},{val:"< 4ms",lbl:"Avg Execution Time"}].map((s,i)=>(
              <div key={i}><div className="login-stat-val">{s.val}</div><div className="login-stat-lbl">{s.lbl}</div></div>
            ))}
          </div>
        </div>
        <div className="login-divider"/>
        <div style={{marginTop:24,display:"flex",flexDirection:"column",gap:8}}>
          {TICKER_DATA.slice(0,5).map((t,i)=>(
            <div key={i} style={{display:"flex",alignItems:"center",gap:12,fontFamily:"var(--font-mono)",fontSize:12}}>
              <span style={{color:"var(--bright)",minWidth:50,fontWeight:500}}>{t.sym}</span>
              <span style={{color:"var(--mid)"}}>{t.price}</span>
              <span style={{color:t.pos?"var(--green)":"var(--red)"}}>{t.chg}</span>
              <Sparkline positive={t.pos} w={80} h={18}/>
            </div>
          ))}
        </div>
      </div>
      <div className="login-right">
        <div className="login-head">SET NEW PASSWORD</div>
        <div className="login-subhead">Choose a new password for your account</div>
        <div className="login-form">
          {done ? (
            <div style={{
              fontFamily:"var(--font-mono)",fontSize:12,color:"var(--green)",
              border:"1px solid var(--green)",borderRadius:2,padding:"14px 16px",lineHeight:1.6
            }}>
              PASSWORD UPDATED<br/>
              <span style={{color:"var(--mid)",fontSize:11}}>Redirecting to sign in...</span>
            </div>
          ) : (
            <>
              <div className="form-field">
                <label className="form-label">New Password</label>
                <div className="pw-wrap">
                  <input className="form-control" type={show?"text":"password"} value={pwd}
                    onChange={e=>setPwd(e.target.value)}
                    onKeyDown={e=>e.key==="Enter"&&handleSubmit()}
                    placeholder="Min 8 characters" style={{paddingRight:36}}/>
                  <button className="pw-eye" onClick={()=>setShow(v=>!v)}>{show?<Ic.eyeOff/>:<Ic.eye/>}</button>
                </div>
              </div>
              <div className="form-field">
                <label className="form-label">Confirm Password</label>
                <input className="form-control" type={show?"text":"password"} value={pwd2}
                  onChange={e=>setPwd2(e.target.value)}
                  onKeyDown={e=>e.key==="Enter"&&handleSubmit()}
                  placeholder="Repeat password"/>
              </div>
              {err && <div style={{fontFamily:"var(--font-mono)",fontSize:11,color:"var(--red)"}}>{err}</div>}
              <button className="btn btn-amber login-btn-full" onClick={handleSubmit} disabled={loading}>
                {loading ? <span className="loading-pulse">UPDATING...</span> : "SET NEW PASSWORD"}
              </button>
              <div className="login-footer-links">
                <span className="login-link" onClick={onBack}>← Back to sign in</span>
              </div>
            </>
          )}
        </div>
        <div className="login-security">
          <div className="security-item"><Ic.lock/> TLS 1.3 Encrypted</div>
          <div className="security-item"><Ic.shield/> SOC 2 Compliant</div>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   PAGE: LOGIN
───────────────────────────────────────────────────────────────────────────── */
const DEMO_EMAIL = "demo@fticker-tap.com";
const DEMO_PWD   = "Demo1234!";

function LoginPage({ onLogin, onRegister, onForgotPassword, backendOk }) {
  const [email, setEmail] = useState(DEMO_EMAIL);
  const [pwd, setPwd] = useState(DEMO_PWD);
  const [show, setShow] = useState(false);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  const handleLogin = async () => {
    if (!email) { setErr("EMAIL REQUIRED"); return; }
    if (!pwd)   { setErr("PASSWORD REQUIRED"); return; }
    setErr(""); setLoading(true);
    try {
      await onLogin(email, pwd);
    } catch(e) {
      setErr(e.message || "LOGIN FAILED");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-wrap">
      <div className="login-grid-bg"/>
      <div className="login-glow"/>

      {/* Left panel — brand + market snapshot */}
      <div className="login-left">
        <div className="login-brand">
          <div className="login-brand-mark">TICKER-TAP</div>
          <div className="login-brand-sub">Professional Investment Terminal · v4.2</div>
        </div>
        <div className="login-stats stagger">
          <div className="login-stat-row">
            {[
              {val:"$2.4B",lbl:"Assets Under Management"},
              {val:"147K",lbl:"Active Accounts"},
            ].map((s,i)=>(
              <div key={i}>
                <div className="login-stat-val">{s.val}</div>
                <div className="login-stat-lbl">{s.lbl}</div>
              </div>
            ))}
          </div>
          <div className="login-stat-row">
            {[
              {val:"99.97%",lbl:"System Uptime"},
              {val:"< 4ms",lbl:"Avg Execution Time"},
            ].map((s,i)=>(
              <div key={i}>
                <div className="login-stat-val">{s.val}</div>
                <div className="login-stat-lbl">{s.lbl}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="login-divider"/>
        <div style={{marginTop:24,display:"flex",flexDirection:"column",gap:8}}>
          {TICKER_DATA.slice(0,5).map((t,i)=>(
            <div key={i} style={{display:"flex",alignItems:"center",gap:12,fontFamily:"var(--font-mono)",fontSize:12}}>
              <span style={{color:"var(--bright)",minWidth:50,fontWeight:500}}>{t.sym}</span>
              <span style={{color:"var(--mid)"}}>{t.price}</span>
              <span style={{color:t.pos?"var(--green)":"var(--red)"}}>{t.chg}</span>
              <Sparkline positive={t.pos} w={80} h={18}/>
            </div>
          ))}
        </div>
      </div>

      {/* Right panel — login form */}
      <div className="login-right">
        <div className="login-head">SIGN IN</div>
        <div className="login-subhead">Access your trading terminal</div>
        <div className="login-form">
          <div className="form-field">
            <label className="form-label">Email Address</label>
            <input className="form-control" type="email" value={email}
              onChange={e=>setEmail(e.target.value)}
              onFocus={()=>{ if (email===DEMO_EMAIL) setEmail(""); }}
              onKeyDown={e=>e.key==="Enter"&&handleLogin()}/>
          </div>
          <div className="form-field">
            <label className="form-label">Password</label>
            <div className="pw-wrap">
              <input className="form-control" type={show?"text":"password"}
                value={pwd} onChange={e=>setPwd(e.target.value)}
                onFocus={()=>{ if (pwd===DEMO_PWD) setPwd(""); }}
                onKeyDown={e=>e.key==="Enter"&&handleLogin()}
                style={{paddingRight:36}}/>
              <button className="pw-eye" onClick={()=>setShow(v=>!v)}>
                {show ? <Ic.eyeOff/> : <Ic.eye/>}
              </button>
            </div>
          </div>
          {err && <div style={{fontFamily:"var(--font-mono)",fontSize:11,color:"var(--red)"}}>{err}</div>}
          <button className="btn btn-amber login-btn-full" onClick={handleLogin} disabled={loading}>
            {loading ? <span className="loading-pulse">AUTHENTICATING...</span> : "SIGN IN TO TERMINAL"}
          </button>
          <div className="login-footer-links">
            <span className="login-link" onClick={onForgotPassword}>Reset password</span>
            <span className="login-link" onClick={onRegister}>Create account →</span>
          </div>
        </div>
        <div className="login-security">
          <div className="security-item"><Ic.lock/> TLS 1.3 Encrypted</div>
          <div className="security-item"><Ic.shield/> SOC 2 Compliant</div>
          <div className="security-item" style={{
            color: backendOk===false ? "var(--amber)" : "var(--green)",
            display:"flex",alignItems:"center",gap:4
          }}>
            <span style={{
              width:5, height:5, borderRadius:"50%",
              background: backendOk===false ? "var(--amber)" : "var(--green)",
              display:"inline-block",
              animation: backendOk===null ? "lpulse 1s infinite" : "none",
            }}/>
            {backendOk===null ? "Checking API..." : backendOk ? "API Connected" : "Demo Mode (API Offline)"}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   PAGE: REGISTER
───────────────────────────────────────────────────────────────────────────── */
function RegisterPage({ onLogin, onBack, backendOk }) {
  const [firstName, setFirstName] = useState("");
  const [lastName,  setLastName]  = useState("");
  const [email,     setEmail]     = useState("");
  const [pwd,       setPwd]       = useState("");
  const [pwd2,      setPwd2]      = useState("");
  const [show,      setShow]      = useState(false);
  const [loading,   setLoading]   = useState(false);
  const [err,       setErr]       = useState("");

  const handleRegister = async () => {
    if (!firstName)       { setErr("FIRST NAME REQUIRED"); return; }
    if (!email)           { setErr("EMAIL REQUIRED"); return; }
    if (!pwd)             { setErr("PASSWORD REQUIRED"); return; }
    if (pwd.length < 8)   { setErr("PASSWORD MIN 8 CHARACTERS"); return; }
    if (pwd !== pwd2)     { setErr("PASSWORDS DO NOT MATCH"); return; }
    setErr(""); setLoading(true);
    try {
      await api.register({ email, password: pwd, first_name: firstName, last_name: lastName });
      await onLogin(email, pwd);
    } catch(e) {
      setErr(e.message || "REGISTRATION FAILED");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-wrap">
      <div className="login-grid-bg"/>
      <div className="login-glow"/>
      <div className="login-left">
        <div className="login-brand">
          <div className="login-brand-mark">TICKER-TAP</div>
          <div className="login-brand-sub">Professional Investment Terminal · v4.2</div>
        </div>
        <div className="login-stats stagger">
          <div className="login-stat-row">
            {[{val:"$2.4B",lbl:"Assets Under Management"},{val:"147K",lbl:"Active Accounts"}].map((s,i)=>(
              <div key={i}><div className="login-stat-val">{s.val}</div><div className="login-stat-lbl">{s.lbl}</div></div>
            ))}
          </div>
          <div className="login-stat-row">
            {[{val:"99.97%",lbl:"System Uptime"},{val:"< 4ms",lbl:"Avg Execution Time"}].map((s,i)=>(
              <div key={i}><div className="login-stat-val">{s.val}</div><div className="login-stat-lbl">{s.lbl}</div></div>
            ))}
          </div>
        </div>
        <div className="login-divider"/>
        <div style={{marginTop:24,display:"flex",flexDirection:"column",gap:8}}>
          {TICKER_DATA.slice(0,5).map((t,i)=>(
            <div key={i} style={{display:"flex",alignItems:"center",gap:12,fontFamily:"var(--font-mono)",fontSize:12}}>
              <span style={{color:"var(--bright)",minWidth:50,fontWeight:500}}>{t.sym}</span>
              <span style={{color:"var(--mid)"}}>{t.price}</span>
              <span style={{color:t.pos?"var(--green)":"var(--red)"}}>{t.chg}</span>
              <Sparkline positive={t.pos} w={80} h={18}/>
            </div>
          ))}
        </div>
      </div>
      <div className="login-right">
        <div className="login-head">CREATE ACCOUNT</div>
        <div className="login-subhead">Open your trading terminal account</div>
        <div className="login-form">
          <div style={{display:"flex",gap:12}}>
            <div className="form-field" style={{flex:1}}>
              <label className="form-label">First Name</label>
              <input className="form-control" type="text" value={firstName}
                onChange={e=>setFirstName(e.target.value)} onKeyDown={e=>e.key==="Enter"&&handleRegister()} placeholder="First"/>
            </div>
            <div className="form-field" style={{flex:1}}>
              <label className="form-label">Last Name</label>
              <input className="form-control" type="text" value={lastName}
                onChange={e=>setLastName(e.target.value)} onKeyDown={e=>e.key==="Enter"&&handleRegister()} placeholder="Last"/>
            </div>
          </div>
          <div className="form-field">
            <label className="form-label">Email Address</label>
            <input className="form-control" type="email" value={email}
              onChange={e=>setEmail(e.target.value)} onKeyDown={e=>e.key==="Enter"&&handleRegister()} placeholder="you@example.com"/>
          </div>
          <div className="form-field">
            <label className="form-label">Password</label>
            <div className="pw-wrap">
              <input className="form-control" type={show?"text":"password"} value={pwd}
                onChange={e=>setPwd(e.target.value)} onKeyDown={e=>e.key==="Enter"&&handleRegister()}
                placeholder="Min 8 characters" style={{paddingRight:36}}/>
              <button className="pw-eye" onClick={()=>setShow(v=>!v)}>{show?<Ic.eyeOff/>:<Ic.eye/>}</button>
            </div>
          </div>
          <div className="form-field">
            <label className="form-label">Confirm Password</label>
            <input className="form-control" type={show?"text":"password"} value={pwd2}
              onChange={e=>setPwd2(e.target.value)} onKeyDown={e=>e.key==="Enter"&&handleRegister()} placeholder="Repeat password"/>
          </div>
          {err && <div style={{fontFamily:"var(--font-mono)",fontSize:11,color:"var(--red)"}}>{err}</div>}
          <button className="btn btn-amber login-btn-full" onClick={handleRegister} disabled={loading}>
            {loading ? <span className="loading-pulse">CREATING ACCOUNT...</span> : "CREATE ACCOUNT"}
          </button>
          <div className="login-footer-links">
            <span className="login-link" onClick={onBack}>← Back to sign in</span>
          </div>
        </div>
        <div className="login-security">
          <div className="security-item"><Ic.lock/> TLS 1.3 Encrypted</div>
          <div className="security-item"><Ic.shield/> SOC 2 Compliant</div>
          <div className="security-item" style={{color:backendOk===false?"var(--amber)":"var(--green)",display:"flex",alignItems:"center",gap:4}}>
            <span style={{width:5,height:5,borderRadius:"50%",background:backendOk===false?"var(--amber)":"var(--green)",display:"inline-block"}}/>
            {backendOk===null?"Checking API...":backendOk?"API Connected":"Demo Mode (API Offline)"}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   PAGE: DASHBOARD
───────────────────────────────────────────────────────────────────────────── */
function DashboardPage({ onNewTx, token, accountId, setPage }) {
  const mktStatus = useMarketStatus();
  const [chartPeriod, setChartPeriod] = useState("3M");
  const [showFilter, setShowFilter] = useState(false);
  const [dashFilter, setDashFilter] = useState("all");
  const [quotesMap, setQuotesMap] = useState({});

  // Fetch portfolio positions (includes symbol + name)
  const { data: apiPositions, loading: hLoading } =
    useApi(() => token ? api.getPositions(token) : Promise.resolve(null), [token]);
  const { data: apiTxns, loading: tLoading } =
    useApi(() => (token && accountId) ? api.listTransactions(accountId, token) : Promise.resolve(null), [token, accountId]);
  const { data: apiSummary } =
    useApi(() => token ? api.getPortfolioSummary(token) : Promise.resolve(null), [token]);
  const { data: apiOrders } =
    useApi(() => (token && accountId) ? api.listOrders(accountId, token) : Promise.resolve(null), [token, accountId]);

  // Fetch live quotes for each held symbol
  const dashPollMs = mktStatus.isOpen ? 3000 : 300000;
  useEffect(() => {
    if (!token || !apiPositions || apiPositions.length === 0) return;
    let cancelled = false;
    const symbols = [...new Set(apiPositions.map(p => p.symbol))];
    const fetchQuotes = () => {
      Promise.allSettled(symbols.map(s => api.getQuote(s, token)))
        .then(results => {
          if (cancelled) return;
          const map = {};
          results.forEach((r, i) => {
            if (r.status === "fulfilled") {
              map[symbols[i]] = { price: Number(r.value.price), change: Number(r.value.change), change_pct: Number(r.value.change_pct) };
            }
          });
          setQuotesMap(map);
        });
    };
    fetchQuotes();
    const id = setInterval(fetchQuotes, dashPollMs);
    return () => { cancelled = true; clearInterval(id); };
  }, [token, apiPositions, dashPollMs]);

  // Merge API data — no mock fallback
  const holdings = (apiPositions || []).map(p => {
      const q = quotesMap[p.symbol];
      return {
        symbol: p.symbol, name: p.name,
        quantity: +p.quantity, average_cost: +(p.average_cost||0),
        current_price: q ? q.price : +(p.current_price||0),
        market_value: +(p.market_value||0),
        chg: q ? q.change : 0, chgPct: q ? q.change_pct : 0,
      };
  });
  // Unify transactions + orders into one activity feed
  const txItems = (apiTxns || []).map(t => ({
    id: t.transaction_id, transaction_type: t.transaction_type,
    symbol: null, amount: +t.amount, status: t.status,
    created_at: t.created_at, reference_number: t.reference_number,
  }));
  const orderItems = (apiOrders || []).map(o => ({
    id: o.order_id, transaction_type: o.side,
    symbol: o.symbol || null, amount: +(o.quantity||0) * +(o.price||0),
    status: o.status, created_at: o.placed_at || null,
    reference_number: null,
  }));
  const txns = [...txItems, ...orderItems]
    .sort((a,b) => (b.created_at||"").localeCompare(a.created_at||""));

  const total   = holdings.reduce((s,h)=>s+(h.quantity||0)*(h.current_price||0),0);
  const cost    = holdings.reduce((s,h)=>s+(h.quantity||0)*(h.average_cost||0),0);
  const pnl     = total - cost;
  const pnlPct  = cost > 0 ? (pnl/cost)*100 : 0;
  const dayChg  = holdings.reduce((s,h)=>s+(h.chg||0)*(h.quantity||0),0);

  const cashBalance = apiSummary && apiSummary.accounts && apiSummary.accounts.length > 0
    ? apiSummary.accounts.reduce((s,a) => s + Number(a.cash_balance||0), 0) : null;
  const pendingOrders = apiOrders ? apiOrders.filter(o => o.status === "pending").length : null;

  const filteredTxns = dashFilter === "all" ? txns : txns.filter(t => (t.transaction_type||t.type) === dashFilter);

  return (
    <div className="page-scroll">
      <div className="page-header">
        <div>
          <div className="page-title">DASHBOARD</div>
          <div className="page-sub">{mktStatus.dateStr} · {mktStatus.isOpen ? "MARKET OPEN" : "MARKET CLOSED"} · NYSE · NASDAQ</div>
        </div>
        <div className="page-actions">
          <div style={{position:"relative"}}>
            <button className="btn btn-outline" onClick={()=>setShowFilter(f=>!f)}>
              <Ic.filter/> FILTER{dashFilter !== "all" ? ` (${dashFilter.toUpperCase()})` : ""}
            </button>
            {showFilter && (
              <div style={{
                position:"absolute",top:"100%",right:0,marginTop:4,zIndex:10,
                background:"var(--panel)",border:"1px solid var(--border)",
                padding:8,display:"flex",flexDirection:"column",gap:4,
                minWidth:160,boxShadow:"0 4px 12px rgba(0,0,0,0.4)",
              }}>
                {["all","buy","sell","deposit","withdrawal"].map(f=>(
                  <button key={f} className={`filter-btn${dashFilter===f?" active":""}`}
                    style={{textAlign:"left",width:"100%"}}
                    onClick={()=>{setDashFilter(f);setShowFilter(false);}}
                  >{f.toUpperCase()}</button>
                ))}
              </div>
            )}
          </div>
          <button className="btn btn-amber" onClick={onNewTx}><Ic.plus/> NEW TRANSACTION</button>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid-stats stagger">
        {[
          {lbl:"Portfolio Value",   val:`$${(total/1000).toFixed(2)}K`, cls:"amber"},
          {lbl:"Unrealized P&L",    val:`${pnl>=0?"+":""}$${(Math.abs(pnl)/1000).toFixed(2)}K`, cls:pnl>=0?"green":"red"},
          {lbl:"Day Change",        val:`${dayChg>=0?"+":""}$${Math.abs(dayChg).toFixed(2)}`,    cls:dayChg>=0?"green":"red"},
          {lbl:"Cash Balance",      val: cashBalance !== null ? `$${cashBalance.toLocaleString("en-US",{minimumFractionDigits:2})}` : "$14,320.50", cls:""},
          {lbl:"Open Orders",       val: pendingOrders !== null ? String(pendingOrders) : "—", cls:""},
        ].map((s,i)=>(
          <div key={i} className="stat-block">
            <div className="stat-lbl">{s.lbl}</div>
            <div className={`stat-val${s.cls?" "+s.cls:""}`}>{s.val}</div>
            {i===1&&<div className={`stat-badge ${pnl>=0?"badge-green":"badge-red"}`}>
              {pnl>=0?<Ic.up/>:<Ic.down/>} {Math.abs(pnlPct).toFixed(2)}% ALL TIME
            </div>}
            {i===2&&<div className={`stat-badge ${dayChg>=0?"badge-green":"badge-red"}`}>
              {dayChg>=0?<Ic.up/>:<Ic.down/>} {total>0?Math.abs(dayChg/total*100).toFixed(2):"0.00"}% TODAY
            </div>}
            {i===3&&<div className="stat-badge badge-mid">AVAILABLE MARGIN</div>}
            {i===4&&pendingOrders>0&&<div className="stat-badge badge-amber">{pendingOrders} PENDING</div>}
          </div>
        ))}
      </div>

      <div className="page-inner stagger">
        {/* Main chart + allocation */}
        <div className="grid-main">
          <div className="panel">
            <div className="panel-header">
              <span className="panel-title">PORTFOLIO PERFORMANCE · {chartPeriod}</span>
              <div style={{display:"flex",gap:1}}>
                {["1W","1M","3M","YTD","1Y","ALL"].map(p=>(
                  <button key={p} className={`filter-btn${p===chartPeriod?" active":""}`}
                    style={{padding:"4px 10px",fontSize:9}}
                    onClick={()=>setChartPeriod(p)}
                  >{p}</button>
                ))}
              </div>
            </div>
            <div className="panel-body" style={{paddingBottom:8}}>
              <PortfolioChart height={160} period={chartPeriod}/>
            </div>
          </div>
          <div className="panel">
            <div className="panel-header">
              <span className="panel-title">ALLOCATION</span>
              <span style={{fontFamily:"var(--font-mono)",fontSize:10,color:"var(--muted)"}}>{holdings.length} POSITIONS</span>
            </div>
            <div className="panel-body">
              <AllocationDonut holdings={holdings}/>
            </div>
          </div>
        </div>

        {/* Holdings snapshot */}
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">TOP POSITIONS</span>
            <button className="btn btn-ghost" style={{fontSize:9,padding:"3px 10px"}} onClick={()=>setPage("holdings")}>VIEW ALL →</button>
          </div>
          <div style={{overflowX:"auto"}}>
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
                {hLoading ? (
                  Array.from({length:3}).map((_,i)=><SkeletonRow key={i} cols={8}/>)
                ) : holdings.length === 0 ? (
                  <tr><td colSpan={8} style={{textAlign:"center",padding:"32px 0",fontFamily:"var(--font-mono)",fontSize:12,color:"var(--muted)"}}>
                    No assets in portfolio
                  </td></tr>
                ) : holdings.slice(0,5).map(h=>{
                  const qty = h.quantity||0, price = h.current_price||0, avg = h.average_cost||0;
                  const val=qty*price, pl=(price-avg)*qty, ret=avg>0?((price-avg)/avg)*100:0;
                  return (
                    <tr key={h.symbol}>
                      <td>
                        <div className="cell-symbol">
                          <div className="sym-badge">{(h.symbol||"?").slice(0,3)}</div>
                          <div><div className="cell-main">{h.symbol}</div><div className="sym-name">{h.name}</div></div>
                        </div>
                      </td>
                      <td className="right">${price.toFixed(2)}</td>
                      <td className={`right ${(h.chgPct||0)>=0?"pnl-pos":"pnl-neg"}`}>
                        {(h.chgPct||0)>=0?"+":""}{(h.chgPct||0).toFixed(2)}%
                      </td>
                      <td className="right">{qty}</td>
                      <td className="right cell-main">${val.toFixed(2)}</td>
                      <td className={`right ${pl>=0?"pnl-pos":"pnl-neg"}`}>
                        {pl>=0?"+":""}${pl.toFixed(2)}
                      </td>
                      <td className={`right ${ret>=0?"pnl-pos":"pnl-neg"}`}>{ret>=0?"+":""}{ret.toFixed(2)}%</td>
                      <td><Sparkline positive={(h.chgPct||0)>=0} w={72} h={22}/></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Recent transactions */}
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">RECENT TRANSACTIONS</span>
            <button className="btn btn-ghost" style={{fontSize:9,padding:"3px 10px"}} onClick={()=>setPage("transactions")}>VIEW ALL →</button>
          </div>
          <div style={{overflowX:"auto"}}>
            <table className="data-table">
              <thead>
                <tr><th>TXN ID</th><th>TYPE</th><th>SYMBOL</th><th className="right">AMOUNT</th><th>STATUS</th><th>DATE</th></tr>
              </thead>
              <tbody>
                {tLoading ? (
                  Array.from({length:3}).map((_,i)=><SkeletonRow key={i} cols={6}/>)
                ) : filteredTxns.length === 0 ? (
                  <tr><td colSpan={6} style={{textAlign:"center",padding:"32px 0",fontFamily:"var(--font-mono)",fontSize:12,color:"var(--muted)"}}>
                    No transactions
                  </td></tr>
                ) : filteredTxns.slice(0,5).map(tx=>(
                  <tr key={tx.transaction_id||tx.id}>
                    <td style={{color:"var(--muted)",fontSize:11}}>{tx.reference_number||tx.id||String(tx.transaction_id||"").slice(0,8)}</td>
                    <td><span className={`type-chip tc-${tx.transaction_type||tx.type}`}>{tx.transaction_type||tx.type}</span></td>
                    <td>{tx.symbol ? <span style={{color:"var(--bright)"}}>{tx.symbol}</span> : <span style={{color:"var(--muted)"}}>—</span>}</td>
                    <td className="right cell-main">${(+tx.amount||0).toLocaleString("en-US",{minimumFractionDigits:2})}</td>
                    <td><span className={`status-pill sp-${tx.status}`}>{tx.status}</span></td>
                    <td style={{color:"var(--muted)"}}>{tx.created_at?tx.created_at.slice(0,10):tx.date||""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   PAGE: TRANSACTIONS
───────────────────────────────────────────────────────────────────────────── */
function TransactionsPage({ onNewTx, token, accountId, goBack }) {
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");

  const { data: apiTxns, loading, error, refetch } =
    useApi(() => (token && accountId) ? api.listTransactions(accountId, token) : Promise.resolve(null), [token, accountId]);

  const allTxns = apiTxns || [];

  const filtered = useMemo(()=>{
    let r = allTxns;
    const type = t => t.transaction_type || t.type;
    if (filter!=="all") r = r.filter(t => type(t) === filter);
    if (search) r = r.filter(t => {
      const id = t.reference_number || t.id || String(t.transaction_id||"");
      return id.toLowerCase().includes(search.toLowerCase());
    });
    return r;
  },[filter, search, allTxns]);

  const totals = {
    total:    allTxns.reduce((s,t)=>s+(+t.amount||0),0),
    deposits: allTxns.filter(t=>(t.transaction_type||t.type)==="deposit").reduce((s,t)=>s+(+t.amount||0),0),
    buys:     allTxns.filter(t=>(t.transaction_type||t.type)==="buy").reduce((s,t)=>s+(+t.amount||0),0),
  };

  return (
    <div className="page-scroll">
      <div className="page-header">
        <div>
          <div className="page-title"><button className="btn btn-ghost" onClick={goBack} style={{padding:"4px 6px",marginRight:8,verticalAlign:"middle"}}><Ic.back/></button>TRANSACTIONS</div>
          <div className="page-sub">{allTxns.length} RECORDS · {accountId ? accountId.toString().slice(0,18) : "ACC-4821"}</div>
        </div>
        <div className="page-actions">
          <button className="btn btn-outline"><Ic.filter/> EXPORT CSV</button>
          <button className="btn btn-amber" onClick={onNewTx}><Ic.plus/> NEW TRANSACTION</button>
        </div>
      </div>

      {/* Summary stats */}
      <div className="grid-stats stagger">
        {[
          {lbl:"Total Volume",    val:`$${(totals.total/1000).toFixed(2)}K`,    cls:"amber"},
          {lbl:"Total Deposits",  val:`$${(totals.deposits/1000).toFixed(2)}K`, cls:""},
          {lbl:"Total Buys",      val:`$${(totals.buys/1000).toFixed(2)}K`,     cls:""},
          {lbl:"Completed",       val:allTxns.filter(t=>t.status==="completed").length, cls:"green"},
          {lbl:"Pending",         val:allTxns.filter(t=>t.status==="pending").length,   cls:"amber"},
        ].map((s,i)=>(
          <div key={i} className="stat-block">
            <div className="stat-lbl">{s.lbl}</div>
            <div className={`stat-val${s.cls?" "+s.cls:""}`}>{s.val}</div>
          </div>
        ))}
      </div>

      <div className="page-inner stagger">
        {error && <ApiError message={error} onRetry={refetch}/>}
        {/* Filter + search bar */}
        <div style={{display:"flex",gap:12,alignItems:"center"}}>
          <div className="filter-bar">
            {["all","deposit","withdrawal","buy","sell"].map(f=>(
              <button key={f} className={`filter-btn${filter===f?" active":""}`} onClick={()=>setFilter(f)}>
                {f}
              </button>
            ))}
          </div>
          <div style={{marginLeft:"auto",display:"flex",alignItems:"center",gap:8}}>
            <Ic.search/>
            <input className="search-input" placeholder="Search by ID or symbol..." value={search} onChange={e=>setSearch(e.target.value)}/>
          </div>
        </div>

        {/* Table */}
        <div className="panel">
          <div style={{overflowX:"auto"}}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>TXN ID</th>
                  <th>TYPE</th>
                  <th>SYMBOL</th>
                  <th className="right">AMOUNT</th>
                  <th>CURRENCY</th>
                  <th>ACCOUNT</th>
                  <th>STATUS</th>
                  <th>DATE</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  Array.from({length:5}).map((_,i)=><SkeletonRow key={i} cols={8}/>)
                ) : filtered.length === 0 ? (
                  <tr><td colSpan={8} style={{textAlign:"center",color:"var(--muted)",padding:"32px"}}>
                    NO TRANSACTIONS FOUND
                  </td></tr>
                ) : filtered.map(tx=>(
                  <tr key={tx.transaction_id||tx.id}>
                    <td style={{fontWeight:500,color:"var(--amber)",fontSize:11}}>{tx.reference_number||tx.id||String(tx.transaction_id||"").slice(0,8)}</td>
                    <td><span className={`type-chip tc-${tx.transaction_type||tx.type}`}>{tx.transaction_type||tx.type}</span></td>
                    <td><span style={{color:"var(--muted)"}}>—</span></td>
                    <td className="right">
                      <span style={{color:"var(--bright)",fontWeight:500}}>
                        ${(+tx.amount||0).toLocaleString("en-US",{minimumFractionDigits:2})}
                      </span>
                    </td>
                    <td style={{color:"var(--muted)"}}>{tx.currency||"USD"}</td>
                    <td style={{color:"var(--muted)",fontSize:11}}>{tx.acct||String(tx.account_id||"").slice(0,8)}</td>
                    <td><span className={`status-pill sp-${tx.status}`}>{tx.status}</span></td>
                    <td style={{color:"var(--muted)"}}>{tx.created_at?tx.created_at.slice(0,10):tx.date||""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   PAGE: HOLDINGS
───────────────────────────────────────────────────────────────────────────── */
function HoldingsPage({ onNewTx, onViewChart, token, accountId, goBack }) {
  const { data: apiHoldings, loading, error, refetch } =
    useApi(() => token ? api.getPositions(token) : Promise.resolve(null), [token]);

  const rawHoldings = apiHoldings || [];
  // Normalise field names — API uses snake_case, mock uses short names
  const holdings = rawHoldings.map(h => ({
    ...h,
    qty:   parseFloat(h.quantity  ?? h.qty),
    avg:   parseFloat(h.average_cost  ?? h.avg),
    price: parseFloat(h.current_price ?? h.price),
    symbol: h.symbol ?? h.security_id,
    name:   h.name   ?? h.symbol ?? "",
    chgPct: h.chgPct ?? 0,
    chg:    h.chg    ?? 0,
  }));
  const total = holdings.reduce((s,h)=>s+h.qty*h.price,0);
  const cost  = holdings.reduce((s,h)=>s+h.qty*h.avg,0);

  return (
    <div className="page-scroll">
      <div className="page-header">
        <div>
          <div className="page-title"><button className="btn btn-ghost" onClick={goBack} style={{padding:"4px 6px",marginRight:8,verticalAlign:"middle"}}><Ic.back/></button>HOLDINGS</div>
          <div className="page-sub">{holdings.length} POSITIONS · {accountId ? `ACCOUNT ${String(accountId).slice(0,8).toUpperCase()}` : "DEMO"}</div>
        </div>
        <div className="page-actions">
          <button className="btn btn-outline" onClick={()=>setSubpage && setSubpage("statements")}><Ic.file/> STATEMENTS</button>
          <button className="btn btn-amber" onClick={onNewTx}><Ic.plus/> NEW TRANSACTION</button>
        </div>
      </div>

      <div className="grid-stats stagger">
        {[
          {lbl:"Total Market Value", val:`$${(total/1000).toFixed(3)}K`,                    cls:"amber"},
          {lbl:"Total Cost Basis",   val:`$${(cost/1000).toFixed(3)}K`,                     cls:""},
          {lbl:"Unrealized Gain",    val:`${total>=cost?"+":""}$${((total-cost)/1000).toFixed(3)}K`,             cls:total>=cost?"green":"red"},
          {lbl:"Total Return",       val:`${total>=cost?"+":""}${cost>0?(((total-cost)/cost)*100).toFixed(2):"0.00"}%`,        cls:total>=cost?"green":"red"},
          {lbl:"Positions",          val:holdings.length,                                    cls:""},
        ].map((s,i)=>(
          <div key={i} className="stat-block">
            <div className="stat-lbl">{s.lbl}</div>
            <div className={`stat-val${s.cls?" "+s.cls:""}`}>{s.val}</div>
          </div>
        ))}
      </div>

      <div className="page-inner stagger">
        <div className="grid-main">
          {/* Holdings table */}
          <div className="panel">
            <div className="panel-header"><span className="panel-title">POSITIONS</span></div>
            <div style={{overflowX:"auto"}}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>SYMBOL</th>
                    <th className="right">QTY</th>
                    <th className="right">AVG COST</th>
                    <th className="right">LAST PRICE</th>
                    <th className="right">MKT VALUE</th>
                    <th className="right">UNRLZD P&L</th>
                    <th className="right">RETURN</th>
                    <th className="right">DAY CHG</th>
                    <th>TREND</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {loading && [0,1,2,3].map(i=><SkeletonRow key={i} cols={10}/>)}
                  {error   && <tr><td colSpan={10}><ApiError message={error} onRetry={refetch}/></td></tr>}
                  {!loading && !error && holdings.length === 0 && (
                    <tr><td colSpan={10} style={{textAlign:"center",padding:"32px 0",fontFamily:"var(--font-mono)",fontSize:12,color:"var(--muted)"}}>
                      No assets in portfolio
                    </td></tr>
                  )}
                  {holdings.map(h=>{
                    const val=(h.qty*h.price), pl=(h.price-h.avg)*h.qty, ret=((h.price-h.avg)/h.avg)*100;
                    const weight=(val/total)*100;
                    return (
                      <tr key={h.symbol} style={{cursor:"pointer"}} onClick={()=>onViewChart&&onViewChart(h.symbol)} title={`Open ${h.symbol} chart`}>
                        <td>
                          <div className="cell-symbol">
                            <div className="sym-badge">{h.symbol.slice(0,3)}</div>
                            <div>
                              <div className="cell-main">{h.symbol}</div>
                              <div className="sym-name">{h.name}</div>
                            </div>
                          </div>
                        </td>
                        <td className="right">{h.qty}</td>
                        <td className="right">${h.avg.toFixed(2)}</td>
                        <td className="right cell-main">${h.price.toFixed(2)}</td>
                        <td className="right">
                          <div>${val.toFixed(2)}</div>
                          <div style={{fontSize:9,color:"var(--muted)",marginTop:1}}>{weight.toFixed(1)}% PORTFOLIO</div>
                        </td>
                        <td className={`right ${pl>=0?"pnl-pos":"pnl-neg"}`}>
                          <div>{pl>=0?"+":""}${Math.abs(pl).toFixed(2)}</div>
                        </td>
                        <td className={`right ${ret>=0?"pnl-pos":"pnl-neg"}`}>{ret>=0?"+":""}{ret.toFixed(2)}%</td>
                        <td className={`right ${h.chgPct>=0?"pnl-pos":"pnl-neg"}`}>
                          {h.chgPct>=0?"+":""}{h.chgPct.toFixed(2)}%
                        </td>
                        <td><Sparkline positive={h.chgPct>=0} w={64} h={20}/></td>
                        <td>
                          <button onClick={e=>{e.stopPropagation();onViewChart&&onViewChart(h.symbol);}}
                            style={{background:"none",border:"1px solid #1e2535",cursor:"pointer",color:"#4a5568",padding:"3px 7px",fontFamily:"IBM Plex Mono",fontSize:9,letterSpacing:"0.5px",display:"flex",alignItems:"center",gap:4,transition:"all 0.1s",borderRadius:2}}
                            onMouseEnter={e=>{e.currentTarget.style.color="#0f7d40";e.currentTarget.style.borderColor="#0f7d40";}}
                            onMouseLeave={e=>{e.currentTarget.style.color="#4a5568";e.currentTarget.style.borderColor="#1e2535";}}>
                            <Ic.externalLink/> CHART
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Donut sidebar */}
          <div style={{display:"flex",flexDirection:"column",gap:16}}>
            <div className="panel">
              <div className="panel-header"><span className="panel-title">ALLOCATION</span></div>
              <div className="panel-body"><AllocationDonut holdings={holdings}/></div>
            </div>
            <div className="panel">
              <div className="panel-header"><span className="panel-title">PERFORMANCE</span></div>
              <div className="panel-body">
                {[
                  {lbl:"Best Performer",  sym:"NVDA",  val:"+50.26%", pos:true},
                  {lbl:"Worst Performer", sym:"TSLA",  val:"-15.00%", pos:false},
                  {lbl:"Largest Position",sym:"MSFT",  val:"$3,031",  pos:null},
                  {lbl:"Smallest Position",sym:"AMZN", val:"$1,178",  pos:null},
                ].map((r,i)=>(
                  <div key={i} style={{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"8px 0",borderBottom:"1px solid var(--border)"}}>
                    <div>
                      <div style={{fontFamily:"var(--font-mono)",fontSize:10,color:"var(--muted)",marginBottom:2}}>{r.lbl}</div>
                      <div style={{fontFamily:"var(--font-mono)",fontSize:12,fontWeight:500,color:"var(--bright)"}}>{r.sym}</div>
                    </div>
                    <div style={{fontFamily:"var(--font-mono)",fontSize:12,fontWeight:500,color:r.pos===null?"var(--text)":r.pos?"var(--green)":"var(--red)"}}>
                      {r.val}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   PAGE: ORDERS
───────────────────────────────────────────────────────────────────────────── */
function OrdersPage({ onNewTx, token, accountId, goBack }) {
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
function generateOHLCV(basePrice, years = 5) {
  const days = years * 365;
  const data = [];
  // Start from 5 years back so "today" is the last candle
  const today = new Date("2026-02-23");
  const startDate = new Date(today);
  startDate.setDate(startDate.getDate() - days);

  // Start price lower so it "grows" to basePrice over the period
  let price = basePrice * (0.30 + Math.random() * 0.15);

  // Build macro regime phases (multi-week trends)
  const phases = [];
  let d = 0;
  while (d < days) {
    const len = 15 + Math.floor(Math.random() * 80);
    const r = Math.random();
    const type = r < 0.50 ? "bull" : r < 0.75 ? "bear" : "range";
    const strength = 0.5 + Math.random();
    phases.push({ start: d, len, type, strength });
    d += len;
  }

  // Intraday vol cycle (higher vol at open/close)
  const getVol = (i) => 0.012 + Math.random() * 0.010 + (i % 252 < 10 || i % 252 > 242 ? 0.006 : 0);

  let earningsOffset = 0; // periodic earnings beats/misses
  for (let i = 0; i < days; i++) {
    const date = new Date(startDate);
    date.setDate(date.getDate() + i);
    if (date.getDay() === 0 || date.getDay() === 6) continue;

    const phase = phases.find(p => i >= p.start && i < p.start + p.len) || phases[phases.length - 1];
    const drift = phase.type === "bull" ? 0.0010 * phase.strength
                : phase.type === "bear" ? -0.0008 * phase.strength
                : 0.0001;

    const dayVol = getVol(i);

    // Quarterly earnings shock every ~63 trading days
    let shock = 0;
    if (i - earningsOffset > 62 && Math.random() < 0.03) {
      shock = (Math.random() < 0.6 ? 1 : -1) * (0.03 + Math.random() * 0.06);
      earningsOffset = i;
    }

    const change = drift + (Math.random() - 0.5) * dayVol * 2 + shock;
    price = Math.max(1, price * (1 + change));

    const spread = price * (0.006 + Math.random() * 0.018);
    const open = price * (1 + (Math.random() - 0.5) * 0.005);
    const close = price;
    const high = Math.max(open, close) + Math.random() * spread * 0.7;
    const low = Math.min(open, close) - Math.random() * spread * 0.7;

    // Volume: base + surge on big moves + earnings days
    const baseVol = basePrice > 400 ? 1.5e7 : basePrice > 100 ? 4e7 : 8e7;
    const volMult = 1 + Math.abs(change) / dayVol * 2 + (Math.abs(shock) > 0 ? 3 : 0);
    const volume = Math.floor(baseVol * (0.4 + Math.random() * 1.2) * volMult);

    data.push({
      date: date.toISOString().slice(0, 10),
      open: +open.toFixed(2),
      high: +high.toFixed(2),
      low: +low.toFixed(2),
      close: +close.toFixed(2),
      volume,
      isEarnings: Math.abs(shock) > 0,
    });
  }

  // Scale final price toward the target basePrice (so it looks "right" today)
  const finalPrice = data[data.length - 1]?.close || 1;
  const scale = basePrice / finalPrice;
  return data.map(d => ({
    ...d,
    open:  +(d.open  * scale).toFixed(2),
    high:  +(d.high  * scale).toFixed(2),
    low:   +(d.low   * scale).toFixed(2),
    close: +(d.close * scale).toFixed(2),
  }));
}

/* ─── SMA CALCULATION ───────────────────────────────────────────────────────── */
function calcSMA(data, period) {
  return data.map((d, i) => {
    if (i < period - 1) return { date: d.date, value: null };
    const slice = data.slice(i - period + 1, i + 1);
    const avg = slice.reduce((s, x) => s + x.close, 0) / period;
    return { date: d.date, value: +avg.toFixed(2) };
  });
}

/* ─── BREAKOUT DETECTION ────────────────────────────────────────────────────── */
function detectBreakouts(data, sma50) {
  const breakouts = [];
  const lookback = 5;
  for (let i = lookback + 1; i < data.length; i++) {
    const curr = data[i];
    const prev = data[i - 1];
    const smaVal = sma50[i]?.value;
    const smaPrev = sma50[i - 1]?.value;
    if (!smaVal || !smaPrev) continue;

    // Bullish: price crosses above 50-SMA with volume surge
    const prevBelow = prev.close < smaPrev;
    const currAbove = curr.close > smaVal;
    const volAvg = data.slice(i - lookback, i).reduce((s, x) => s + x.volume, 0) / lookback;
    const volSurge = curr.volume > volAvg * 1.6;

    if (prevBelow && currAbove && volSurge) {
      breakouts.push({ index: i, type: "bull", date: curr.date, price: curr.close });
    }

    // Bearish: price crosses below 50-SMA with volume surge
    const prevAbove = prev.close > smaPrev;
    const currBelow = curr.close < smaVal;
    if (prevAbove && currBelow && volSurge) {
      breakouts.push({ index: i, type: "bear", date: curr.date, price: curr.close });
    }

    // Consolidation breakout: tight range then expansion
    if (i >= lookback + 10) {
      const window = data.slice(i - 10, i);
      const windowHigh = Math.max(...window.map(x => x.high));
      const windowLow = Math.min(...window.map(x => x.low));
      const rangeRatio = (windowHigh - windowLow) / windowLow;
      if (rangeRatio < 0.04 && curr.close > windowHigh * 1.008 && volSurge) {
        breakouts.push({ index: i, type: "bull", date: curr.date, price: curr.close, label: "CONSOL+" });
      }
      if (rangeRatio < 0.04 && curr.close < windowLow * 0.992 && volSurge) {
        breakouts.push({ index: i, type: "bear", date: curr.date, price: curr.close, label: "CONSOL-" });
      }
    }
  }
  // Deduplicate nearby
  const out = [];
  for (const b of breakouts) {
    const last = out[out.length - 1];
    if (!last || b.index - last.index > 8) out.push(b);
  }
  return out;
}

/* ─── CHART COMPONENT ───────────────────────────────────────────────────────── */
function StockChart({ symbol, stockInfo, onClose, token }) {
  const svgRef = useRef(null);
  const containerRef = useRef(null);
  const wrapRef = useRef(null);
  const dragRef = useRef(null);

  const [dims, setDims] = useState({ w: 900, h: 420 });
  const [crosshair, setCrosshair] = useState(null);
  const [tooltip, setTooltip] = useState(null);
  const [period, setPeriod] = useState("1Y");
  const [overlays, setOverlays] = useState({ sma50: true, sma150: true, smaCustom: true, volume: true, breakouts: true });
  const [customPeriod, setCustomPeriod] = useState(20);
  const [chartType, setChartType] = useState("candle");
  // Zoom/pan state: offset = index offset from right, zoom = candles visible
  const [zoom, setZoom] = useState(null); // null = use period preset

  // Fetch OHLCV from backend; fall back to local generation if backend offline
  const [allData, setAllData] = useState(() => generateOHLCV(stockInfo.price, 5));
  const [dataLoading, setDataLoading] = useState(false);
  const [volumeSource, setVolumeSource] = useState(null); // e.g. "GLD" when ETF volume is used

  useEffect(() => {
    let cancelled = false;
    setDataLoading(true);
    setVolumeSource(null);
    if (!token) {
      setAllData(generateOHLCV(stockInfo.price, 5));
      setDataLoading(false);
      return;
    }
    api.getOhlcv(symbol, token)
      .then(resp => {
        if (!cancelled) {
          // New response format: { bars: [...], volume_source: "GLD" | null }
          const bars = resp.bars || resp;
          setVolumeSource(resp.volume_source || null);
          setAllData(bars.map(b => ({
            date: b.date, open: b.open, high: b.high, low: b.low,
            close: b.close, volume: b.volume, isEarnings: b.is_earnings,
          })));
        }
      })
      .catch(() => {
        if (!cancelled) setAllData(generateOHLCV(stockInfo.price, 5));
      })
      .finally(() => { if (!cancelled) setDataLoading(false); });
    return () => { cancelled = true; };
  }, [symbol, token]);

  const PERIODS = { "1M": 21, "3M": 63, "6M": 126, "1Y": 252, "2Y": 504, "5Y": 1260, "ALL": 9999 };

  // Visible slice — respects period preset OR manual zoom
  const { visibleData, visibleStart } = useMemo(() => {
    let start, count;
    if (zoom) {
      start = Math.max(0, Math.min(allData.length - 1, zoom.start));
      count = Math.max(10, Math.min(allData.length, zoom.count));
    } else {
      count = Math.min(PERIODS[period] || 252, allData.length);
      start = allData.length - count;
    }
    return { visibleData: allData.slice(start, start + count), visibleStart: start };
  }, [allData, period, zoom]);

  // When period changes, clear manual zoom
  const handlePeriod = (p) => { setPeriod(p); setZoom(null); };

  // SMAs computed ONCE on full history — zoom/pan only changes which slice is displayed
  const allSma50     = useMemo(() => calcSMA(allData, 50),                        [allData]);
  const allSma150    = useMemo(() => calcSMA(allData, 150),                       [allData]);
  const allSmaCustom = useMemo(() => calcSMA(allData, Math.max(2, customPeriod)), [allData, customPeriod]);

  // Slice just the visible window from the pre-computed full SMAs
  const sma50     = useMemo(() => allSma50.slice(visibleStart, visibleStart + visibleData.length),     [allSma50,     visibleStart, visibleData.length]);
  const sma150    = useMemo(() => allSma150.slice(visibleStart, visibleStart + visibleData.length),    [allSma150,    visibleStart, visibleData.length]);
  const smaCustom = useMemo(() => allSmaCustom.slice(visibleStart, visibleStart + visibleData.length), [allSmaCustom, visibleStart, visibleData.length]);

  // Breakouts computed on full history using full SMA50
  const breakouts = useMemo(() => {
    const allBo = detectBreakouts(allData, allSma50);
    // Return only those whose index falls within the visible window
    return allBo
      .filter(b => b.index >= visibleStart && b.index < visibleStart + visibleData.length)
      .map(b => ({ ...b, index: b.index - visibleStart }));
  }, [allData, allSma50, visibleStart, visibleData.length]);

  // Measure the chart container div (containerRef)
  useEffect(() => {
    const obs = new ResizeObserver(entries => {
      for (const e of entries) {
        const { width, height } = e.contentRect;
        if (width > 0 && height > 0) setDims({ w: Math.floor(width), h: Math.floor(height) });
      }
    });
    const target = containerRef.current;
    if (target) obs.observe(target);
    return () => obs.disconnect();
  }, []);

  // Chart geometry — price uses top portion, volume in bottom 15% of same SVG
  const PAD    = { top: 20, right: 72, bottom: 22, left: 8 };
  const totalH = Math.max(50, dims.h - PAD.top - PAD.bottom);
  const VOL_H  = overlays.volume ? Math.max(40, Math.round(totalH * 0.15)) : 0;
  const VOL_GAP = overlays.volume ? 8 : 0;
  const H      = totalH - VOL_H - VOL_GAP; // price chart height
  const W      = Math.max(10, dims.w - PAD.left - PAD.right);
  const volTop = PAD.top + H + VOL_GAP; // y position where volume section starts

  const n = visibleData.length;
  const candleGap = n > 0 ? W / n : 1;
  const candleW   = Math.max(1, Math.min(14, candleGap * 0.72));

  const priceMin = n > 0 ? Math.min(...visibleData.map(d => d.low))  : 0;
  const priceMax = n > 0 ? Math.max(...visibleData.map(d => d.high)) : 1;
  const pricePad = (priceMax - priceMin) * 0.07;
  const pLo = priceMin - pricePad;
  const pHi = priceMax + pricePad;
  const volMax = n > 0 ? Math.max(...visibleData.map(d => d.volume)) : 1;

  const xOf  = i => PAD.left + (i + 0.5) * candleGap;
  const yOf  = p => PAD.top + H - ((p - pLo) / (pHi - pLo)) * H;

  // Y-axis ticks
  const yTicks = useMemo(() => {
    if (pHi === pLo) return [];
    const range = pHi - pLo;
    const raw   = range / 6;
    const mag   = Math.pow(10, Math.floor(Math.log10(Math.max(raw, 0.01))));
    const step  = Math.ceil(raw / mag) * mag;
    const ticks = [];
    let t = Math.ceil(pLo / step) * step;
    while (t <= pHi) { ticks.push(t); t = +(t + step).toFixed(10); }
    return ticks;
  }, [pLo, pHi]);

  // X-axis labels
  const xLabels = useMemo(() => {
    const labels = [];
    let lastYear = null;
    const maxLabels = Math.floor(W / 70);
    const step = Math.max(1, Math.floor(n / maxLabels));
    for (let i = 0; i < n; i += step) {
      const d   = new Date(visibleData[i].date);
      const mo  = d.toLocaleString("en-US", { month: "short" });
      const yr  = d.getFullYear();
      const lbl = yr !== lastYear ? `${mo} '${String(yr).slice(2)}` : mo;
      labels.push({ x: xOf(i), label: lbl });
      lastYear = yr;
    }
    return labels;
  }, [visibleData, n, W]);

  // SMA path builder
  const smaPath = (smaData) => {
    let path = "";
    for (let i = 0; i < smaData.length; i++) {
      if (!smaData[i].value) continue;
      const x = xOf(i), y = yOf(smaData[i].value);
      path += `${!path || !smaData[i - 1]?.value ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    }
    return path;
  };

  // Line path
  const linePath = useMemo(() => {
    let p = "";
    for (let i = 0; i < n; i++) {
      const x = xOf(i), y = yOf(visibleData[i].close);
      p += `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    }
    return p;
  }, [visibleData, W, H, pLo, pHi]);

  // ── Mouse handlers ────────────────────────────────────────────────────────
  const handleMouseMove = useCallback((e) => {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    // Drag-to-pan
    if (dragRef.current) {
      const dx = mx - dragRef.current.startX;
      const candleShift = Math.round(-dx / candleGap);
      const base = dragRef.current.baseStart;
      const baseCount = dragRef.current.baseCount;
      const newStart = Math.max(0, Math.min(allData.length - baseCount, base + candleShift));
      setZoom({ start: newStart, count: baseCount });
      return;
    }

    const idx     = Math.round((mx - PAD.left - candleGap / 2) / candleGap);
    const clamped = Math.max(0, Math.min(n - 1, idx));
    const d       = visibleData[clamped];
    if (!d) return;

    const priceCross = pLo + ((PAD.top + H - my) / H) * (pHi - pLo);
    const tRight  = rect.width  - mx < 210;
    const tBottom = my > rect.height * 0.55;

    setCrosshair({ x: xOf(clamped), y: my, idx: clamped, priceCross });
    setTooltip({
      d, idx: clamped,
      s50: sma50[clamped]?.value,
      s150: sma150[clamped]?.value,
      sCx: smaCustom[clamped]?.value,
      screen: { x: mx, y: my, tRight, tBottom },
    });
  }, [visibleData, sma50, sma150, smaCustom, n, W, H, pLo, pHi, candleGap, allData.length]);

  const handleMouseDown = useCallback((e) => {
    if (e.button !== 0) return;
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const cur = zoom || { start: visibleStart, count: visibleData.length };
    dragRef.current = { startX: mx, baseStart: cur.start, baseCount: cur.count };
    e.preventDefault();
  }, [zoom, visibleStart, visibleData.length]);

  const handleMouseUp   = () => { dragRef.current = null; };
  const handleMouseLeave = () => { dragRef.current = null; setCrosshair(null); setTooltip(null); };

  // Mouse-wheel zoom
  const handleWheel = useCallback((e) => {
    e.preventDefault();
    const factor   = e.deltaY > 0 ? 1.15 : 0.87;
    const curCount = zoom ? zoom.count : (PERIODS[period] || 252);
    const curStart = zoom ? zoom.start : (allData.length - Math.min(curCount, allData.length));
    const newCount = Math.max(10, Math.min(allData.length, Math.round(curCount * factor)));

    // Keep center candle in place
    const svg  = svgRef.current;
    const rect = svg?.getBoundingClientRect();
    const ratio = rect ? (e.clientX - rect.left - PAD.left) / W : 0.5;
    const pivot = curStart + Math.round(curCount * ratio);
    const newStart = Math.max(0, Math.min(allData.length - newCount, Math.round(pivot - newCount * ratio)));

    setZoom({ start: newStart, count: newCount });
  }, [zoom, period, allData.length, W, PAD]);

  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    wrap.addEventListener("wheel", handleWheel, { passive: false });
    return () => wrap.removeEventListener("wheel", handleWheel);
  }, [handleWheel]);

  // ── Stats ─────────────────────────────────────────────────────────────────
  const last     = visibleData[visibleData.length - 1] || {};
  const prev     = visibleData[visibleData.length - 2] || {};
  const dayGain  = (last.close || 0) - (prev.close || 0);
  const dayGainPct = prev.close ? (dayGain / prev.close) * 100 : 0;
  const fmtVol   = v => v >= 1e9 ? (v / 1e9).toFixed(2) + "B" : v >= 1e6 ? (v / 1e6).toFixed(2) + "M" : v >= 1e3 ? (v / 1e3).toFixed(0) + "K" : String(v);

  const toggleOverlay = k => setOverlays(o => ({ ...o, [k]: !o[k] }));

  const OVERLAY_DEFS = [
    { key: "sma50",     label: "SMA 50",              color: "#3d7ef5" },
    { key: "sma150",    label: "SMA 150",              color: "#0fc0d0" },
    { key: "smaCustom", label: `SMA ${customPeriod}`,  color: "#a78bfa" },
    { key: "breakouts", label: "BREAKOUTS",            color: "#0f7d40" },
    { key: "volume",    label: "VOLUME",               color: "#4a5568" },
  ];

  // Breakout tooltip hover state
  const [hoveredBreakout, setHoveredBreakout] = useState(null);

  return (
    <div style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0, display: "flex", flexDirection: "column", overflow: "hidden" }}>

      {/* ── STATS BAR ── */}
      <div className="stock-stats-bar" style={{ padding: "10px 20px" }}>
        {/* Symbol + name */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginRight: 18 }}>
          <div style={{ fontFamily: "'Bebas Neue',sans-serif", fontSize: 30, color: "#0f7d40", letterSpacing: 2, lineHeight: 1 }}>{symbol}</div>
          <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: 10, color: "#718096", maxWidth: 160, lineHeight: 1.4 }}>{stockInfo.name}</div>
          {onClose && (
            <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: "#4a5568", padding: 4 }}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M18 6L6 18M6 6l12 12"/></svg>
            </button>
          )}
        </div>

        <div className="stat-sep" />

        {/* OPEN */}
        <div className="stock-stat">
          <div className="ss-label">OPEN</div>
          <div className="ss-value">${last.open?.toFixed(2) ?? "—"}</div>
          <div className="ss-sub">TODAY</div>
        </div>

        <div className="stat-sep" />

        {/* CLOSE */}
        <div className="stock-stat">
          <div className="ss-label">CLOSE</div>
          <div className="ss-value amber">${last.close?.toFixed(2) ?? "—"}</div>
          <div className="ss-sub">LAST PRICE</div>
        </div>

        <div className="stat-sep" />

        {/* VOLUME TODAY */}
        <div className="stock-stat">
          <div className="ss-label">VOLUME TODAY</div>
          <div className="ss-value" style={{ fontSize: 16 }}>{fmtVol(last.volume ?? 0)}</div>
          <div className="ss-sub">AVG: {fmtVol(Math.round(visibleData.slice(-20).reduce((s, d) => s + d.volume, 0) / Math.max(1, visibleData.slice(-20).length)))}</div>
        </div>

        <div className="stat-sep" />

        {/* GAIN TODAY */}
        <div className="stock-stat">
          <div className="ss-label">GAIN TODAY</div>
          <div className={`ss-value ${dayGain >= 0 ? "pos" : "neg"}`} style={{ fontSize: 20 }}>
            {dayGain >= 0 ? "+" : ""}{dayGain.toFixed(2)}
          </div>
          <div className={`ss-badge ${dayGain >= 0 ? "pos" : "neg"}`} style={{ marginTop: 3 }}>
            {dayGainPct >= 0 ? "▲" : "▼"} {Math.abs(dayGainPct).toFixed(2)}%
          </div>
        </div>

        <div className="stat-sep" />

        {/* HIGH / LOW */}
        <div className="stock-stat">
          <div className="ss-label">HIGH · LOW</div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span className="ss-value" style={{ color: "#00d97e", fontSize: 15 }}>${last.high?.toFixed(2) ?? "—"}</span>
            <span style={{ color: "#1e2535", fontFamily: "var(--font-mono)", fontSize: 11 }}>·</span>
            <span className="ss-value" style={{ color: "#f04438", fontSize: 15 }}>${last.low?.toFixed(2)  ?? "—"}</span>
          </div>
          <div className="ss-sub">INTRADAY RANGE</div>
        </div>

        <div className="stat-sep" />

        {/* 52-WEEK range */}
        {(() => {
          const yr = allData.slice(-252);
          const hi52 = yr.length ? Math.max(...yr.map(d => d.high)) : 0;
          const lo52 = yr.length ? Math.min(...yr.map(d => d.low))  : 0;
          const pos52 = hi52 > lo52 ? ((last.close - lo52) / (hi52 - lo52)) * 100 : 50;
          return (
            <div className="stock-stat" style={{ minWidth: 160 }}>
              <div className="ss-label">52-WEEK RANGE</div>
              <div style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 4 }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "#718096" }}>${lo52.toFixed(0)}</span>
                <div style={{ flex: 1, height: 4, background: "#1e2535", borderRadius: 2, position: "relative" }}>
                  <div style={{ position: "absolute", left: 0, top: 0, height: "100%", width: `${Math.min(100, Math.max(0, pos52))}%`, background: "var(--amber)", borderRadius: 2 }} />
                </div>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "#718096" }}>${hi52.toFixed(0)}</span>
              </div>
              <div className="ss-sub">{pos52.toFixed(0)}% FROM 52W LOW</div>
            </div>
          );
        })()}

        {/* Spacer */}
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "#4a5568", textAlign: "right" }}>
            <div style={{ letterSpacing: "0.5px" }}>SCROLL TO ZOOM</div>
            <div style={{ color: "#263045" }}>DRAG TO PAN</div>
          </div>
        </div>
      </div>

      {/* ── CONTROLS ── */}
      <div className="chart-controls">
        <span className="ctrl-label">RANGE:</span>
        <div className="ctrl-group">
          {["1M","3M","6M","1Y","2Y","5Y","ALL"].map(p => (
            <button key={p} className={`ctrl-btn${!zoom && period===p ? " active" : ""}`} onClick={() => handlePeriod(p)}>{p}</button>
          ))}
        </div>
        <div className="ctrl-sep" />
        <span className="ctrl-label">TYPE:</span>
        <div className="ctrl-group">
          {[["candle","CANDLE"],["line","LINE"]].map(([v,l]) => (
            <button key={v} className={`ctrl-btn${chartType===v ? " active" : ""}`} onClick={() => setChartType(v)}>{l}</button>
          ))}
        </div>
        <div className="ctrl-sep" />
        <span className="ctrl-label">OVERLAYS:</span>
        <div className="overlay-toggles">
          {OVERLAY_DEFS.map(od => (
            <div key={od.key} className={`overlay-toggle${overlays[od.key] ? " on" : ""}`}
              onClick={() => toggleOverlay(od.key)}
              style={overlays[od.key] ? { borderColor: od.color + "44", color: od.color } : {}}>
              <div className="overlay-dot" style={{ background: overlays[od.key] ? od.color : "#1e2535" }} />
              {od.key === "smaCustom" ? (
                <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  SMA
                  <input className="sma-custom-input" value={customPeriod}
                    onChange={e => setCustomPeriod(Math.max(2, Math.min(500, parseInt(e.target.value) || 2)))}
                    onClick={e => e.stopPropagation()}
                    style={{ width: 44, color: overlays.smaCustom ? "#a78bfa" : "#4a5568" }}
                  />
                </span>
              ) : od.label}
            </div>
          ))}
        </div>
        {zoom && (
          <button className="ctrl-btn active" style={{ marginLeft: "auto", borderLeft: "1px solid #1e2535" }}
            onClick={() => setZoom(null)}>✕ RESET</button>
        )}
      </div>

      {/* ── CHART BODY — single SVG with price + volume ── */}
      <div ref={wrapRef} style={{ flex: 1, overflow: "hidden", minHeight: 0, position: "relative" }}
        onMouseMove={handleMouseMove}
        onMouseDown={handleMouseDown}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseLeave}
      >
        {/* ── CHART SVG (price + volume) ── */}
        <div ref={containerRef} style={{ width: "100%", height: "100%", position: "relative", background: "#090b0f", cursor: "crosshair" }}>
          {/* Legend overlay */}
          <div className="chart-legend">
            {overlays.sma50     && <div className="legend-item"><div className="legend-line" style={{ background: "#3d7ef5" }}/>SMA50</div>}
            {overlays.sma150    && <div className="legend-item"><div className="legend-line" style={{ background: "#0fc0d0" }}/>SMA150</div>}
            {overlays.smaCustom && <div className="legend-item"><div className="legend-line" style={{ background: "#a78bfa" }}/>SMA{customPeriod}</div>}
            {overlays.breakouts && <div className="legend-item"><div style={{ width: 8, height: 8, background: "#00d97e", clipPath: "polygon(50% 0,100% 100%,0 100%)", flexShrink: 0 }}/>BREAKOUT</div>}
          </div>

          {/* Date range info */}
          <div style={{ position: "absolute", bottom: 18, left: 12, fontFamily: "var(--font-mono)", fontSize: 9, color: "#263045", pointerEvents: "none", zIndex: 2 }}>
            {visibleData[0]?.date && visibleData[n-1]?.date ? `${visibleData[0].date} → ${visibleData[n-1].date}  ·  ${n} SESSIONS` : ""}
          </div>

          <svg ref={svgRef} style={{ display: "block", width: "100%", height: "100%", userSelect: "none" }}>
            <defs>
              <linearGradient id="lgbull" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%"   stopColor="#0f7d40" stopOpacity="0.18" />
                <stop offset="100%" stopColor="#0f7d40" stopOpacity="0" />
              </linearGradient>
              <clipPath id="chartClip">
                <rect x={PAD.left} y={0} width={W + 2} height={dims.h + 10} />
              </clipPath>
            </defs>

            {/* Grid lines */}
            {yTicks.map((t, i) => {
              const y = yOf(t);
              if (y < PAD.top || y > PAD.top + H) return null;
              return (
                <g key={i}>
                  <line x1={PAD.left} y1={y} x2={dims.w - PAD.right} y2={y}
                    stroke="#1a2030" strokeWidth="1" strokeDasharray="2,5" />
                  <text x={dims.w - PAD.right + 5} y={y + 3.5}
                    fontFamily="IBM Plex Mono" fontSize="10" fill="#4a5568">
                    {t >= 1000 ? `$${(t/1000).toFixed(1)}K` : t >= 100 ? `$${t.toFixed(0)}` : `$${t.toFixed(2)}`}
                  </text>
                </g>
              );
            })}

            {/* X-axis labels */}
            {xLabels.map((l, i) => (
              <text key={i} x={l.x} y={dims.h - 4} textAnchor="middle"
                fontFamily="IBM Plex Mono" fontSize="9" fill="#4a5568">{l.label}</text>
            ))}

            {/* ── LINE MODE ── */}
            {chartType === "line" && (
              <g clipPath="url(#chartClip)">
                <path d={linePath + ` L${xOf(n-1)},${PAD.top+H} L${xOf(0)},${PAD.top+H} Z`} fill="url(#lgbull)" />
                <path d={linePath} fill="none" stroke="#0f7d40" strokeWidth="1.6" strokeLinejoin="round" />
              </g>
            )}

            {/* ── CANDLE MODE ── */}
            {chartType === "candle" && (
              <g clipPath="url(#chartClip)">
                {visibleData.map((d, i) => {
                  const bull    = d.close >= d.open;
                  const col     = bull ? "#00d97e" : "#f04438";
                  const x       = xOf(i);
                  const bodyTop = yOf(Math.max(d.open, d.close));
                  const bodyBot = yOf(Math.min(d.open, d.close));
                  const bodyH   = Math.max(1, bodyBot - bodyTop);
                  const cw      = Math.max(1, candleW);
                  const isHov   = crosshair?.idx === i;
                  return (
                    <g key={i} opacity={isHov ? 1 : 0.88}>
                      <line x1={x} y1={yOf(d.high)} x2={x} y2={yOf(d.low)} stroke={col} strokeWidth={cw < 3 ? 1 : 1.2} />
                      <rect x={x - cw/2} y={bodyTop} width={cw} height={bodyH}
                        fillOpacity={bull ? 0.85 : 0.7} fill={col}
                        stroke={isHov ? "#fff" : col} strokeWidth={isHov ? 0.6 : 0.3}
                      />
                      {d.isEarnings && <circle cx={x} cy={bodyTop - 5} r={3} fill="#0f7d40" opacity="0.9" />}
                    </g>
                  );
                })}
              </g>
            )}

            {/* ── SMA OVERLAYS ── */}
            <g clipPath="url(#chartClip)">
              {overlays.sma50     && <path d={smaPath(sma50)}     fill="none" stroke="#3d7ef5" strokeWidth="1.3" opacity="0.9" />}
              {overlays.sma150    && <path d={smaPath(sma150)}    fill="none" stroke="#0fc0d0" strokeWidth="1.3" opacity="0.9" />}
              {overlays.smaCustom && <path d={smaPath(smaCustom)} fill="none" stroke="#a78bfa" strokeWidth="1.2" strokeDasharray="5,4" opacity="0.9" />}
            </g>

            {/* ── BREAKOUTS ── */}
            {overlays.breakouts && breakouts.map((b, i) => {
              const x   = xOf(b.index);
              const py  = yOf(b.price);
              const col = b.type === "bull" ? "#00d97e" : "#f04438";
              const isHov = hoveredBreakout === i;
              return (
                <g key={i} clipPath="url(#chartClip)"
                  onMouseEnter={() => setHoveredBreakout(i)}
                  onMouseLeave={() => setHoveredBreakout(null)}
                  style={{ cursor: "pointer" }}>
                  <line x1={x} y1={PAD.top} x2={x} y2={PAD.top + H}
                    stroke={col} strokeWidth="0.6" strokeDasharray="3,5" opacity={isHov ? 0.6 : 0.2} />
                  <polygon
                    points={b.type === "bull"
                      ? `${x},${py-6} ${x-6},${py-15} ${x+6},${py-15}`
                      : `${x},${py+6} ${x-6},${py+15} ${x+6},${py+15}`}
                    fill={col} opacity={isHov ? 1 : 0.8}
                  />
                  {(isHov || b.label) && (() => {
                    const lbl = b.label || (b.type === "bull" ? "BREAKOUT ▲" : "BREAKDOWN ▼");
                    const bx = x - 36;
                    const by = b.type === "bull" ? py - 30 : py + 18;
                    return (
                      <g>
                        <rect x={bx} y={by} width={74} height={16} rx={1} fill={col} opacity="0.9" />
                        <text x={bx + 4} y={by + 11} fontFamily="IBM Plex Mono" fontSize="8.5" fontWeight="700"
                          fill={b.type === "bull" ? "#060f08" : "#fff"}>{lbl}</text>
                      </g>
                    );
                  })()}
                </g>
              );
            })}

            {/* ── VOLUME BARS (inside same SVG) ── */}
            {overlays.volume && (
              <g>
                <line x1={PAD.left} y1={volTop - VOL_GAP / 2} x2={dims.w - PAD.right} y2={volTop - VOL_GAP / 2}
                  stroke="#1e2535" strokeWidth="1" />
                <text x={PAD.left + 4} y={volTop + 10}
                  fontFamily="IBM Plex Mono" fontSize="9" fontWeight="600" fill="#4a5568" letterSpacing="1">
                  {volumeSource ? `VOLUME (via ${volumeSource})` : "VOLUME"}
                </text>
                <text x={dims.w - PAD.right + 5} y={volTop + 12}
                  fontFamily="IBM Plex Mono" fontSize="9" fill="#4a5568">{fmtVol(volMax)}</text>
                {visibleData.map((d, i) => {
                  const bull  = d.close >= d.open;
                  const x     = xOf(i);
                  const bw    = Math.max(1, candleW);
                  const barH  = Math.max(1, (d.volume / volMax) * (VOL_H - 14));
                  const isHov = crosshair?.idx === i;
                  return (
                    <rect key={`v${i}`}
                      x={x - bw/2} y={volTop + VOL_H - barH} width={bw} height={barH}
                      fill={bull ? "#00d97e" : "#f04438"}
                      opacity={isHov ? 0.9 : 0.35}
                    />
                  );
                })}
              </g>
            )}

            {/* ── CROSSHAIR ── */}
            {crosshair && (
              <g>
                <line x1={crosshair.x} y1={PAD.top} x2={crosshair.x} y2={PAD.top + H + (overlays.volume ? VOL_GAP + VOL_H : 0)} stroke="#263045" strokeWidth="1" />
                <line x1={PAD.left} y1={crosshair.y} x2={dims.w - PAD.right} y2={crosshair.y} stroke="#263045" strokeWidth="1" />
                {crosshair.y >= PAD.top && crosshair.y <= PAD.top + H && (
                  <>
                    <rect x={dims.w - PAD.right} y={crosshair.y - 9} width={PAD.right - 1} height={18} fill="#0f7d40" />
                    <text x={dims.w - PAD.right + 4} y={crosshair.y + 4}
                      fontFamily="IBM Plex Mono" fontSize="10" fontWeight="700" fill="#e8f0fa">
                      ${crosshair.priceCross?.toFixed(2)}
                    </text>
                  </>
                )}
              </g>
            )}

            {/* ── CURRENT PRICE LINE ── */}
            {last.close && (() => {
              const y = yOf(last.close);
              const col = dayGain >= 0 ? "#00d97e" : "#f04438";
              if (y < PAD.top || y > PAD.top + H) return null;
              return (
                <g>
                  <line x1={PAD.left} y1={y} x2={dims.w - PAD.right} y2={y}
                    stroke={col} strokeWidth="0.9" strokeDasharray="5,4" opacity="0.55" />
                  <rect x={dims.w - PAD.right} y={y - 9} width={PAD.right - 1} height={18} fill={col} />
                  <text x={dims.w - PAD.right + 4} y={y + 4}
                    fontFamily="IBM Plex Mono" fontSize="10" fontWeight="700" fill="#060f08">
                    {last.close.toFixed(2)}
                  </text>
                </g>
              );
            })()}
          </svg>
        </div>

        {/* ── TOOLTIP ── */}
        {tooltip && !dragRef.current && (
          <div className="crosshair-tooltip" style={{
            position: "absolute",
            left: tooltip.screen.tRight ? tooltip.screen.x - 210 : tooltip.screen.x + 16,
            top:  tooltip.screen.tBottom ? tooltip.screen.y - 210 : tooltip.screen.y + 16,
            minWidth: 200,
            zIndex: 50,
          }}>
            <div className="tt-date">
              {new Date(tooltip.d.date).toLocaleDateString("en-US", { weekday: "short", year: "numeric", month: "short", day: "numeric" })}
              {tooltip.d.isEarnings && <span style={{ marginLeft: 8, color: "#0f7d40", fontSize: 9, background: "rgba(15,125,64,0.1)", padding: "1px 5px", border: "1px solid rgba(15,125,64,0.2)" }}>EARNINGS</span>}
            </div>
            <div className="tt-row"><span className="tt-key">OPEN</span>  <span className="tt-val">${tooltip.d.open.toFixed(2)}</span></div>
            <div className="tt-row"><span className="tt-key">HIGH</span>  <span className="tt-val" style={{ color: "#00d97e" }}>${tooltip.d.high.toFixed(2)}</span></div>
            <div className="tt-row"><span className="tt-key">LOW</span>   <span className="tt-val" style={{ color: "#f04438" }}>${tooltip.d.low.toFixed(2)}</span></div>
            <div className="tt-row">
              <span className="tt-key">CLOSE</span>
              <span className={`tt-val ${tooltip.d.close >= tooltip.d.open ? "pos" : "neg"}`}>${tooltip.d.close.toFixed(2)}</span>
            </div>
            <div className="tt-row">
              <span className="tt-key">CHANGE</span>
              <span className={`tt-val ${tooltip.d.close >= tooltip.d.open ? "pos" : "neg"}`}>
                {((tooltip.d.close - tooltip.d.open) / tooltip.d.open * 100).toFixed(2)}%
              </span>
            </div>
            <div className="tt-row"><span className="tt-key">VOLUME</span><span className="tt-val">{fmtVol(tooltip.d.volume)}</span></div>
            {(tooltip.s50 || tooltip.s150 || tooltip.sCx) && (
              <>
                <div className="tt-divider" />
                {overlays.sma50     && tooltip.s50  && <div className="tt-sma"><div className="tt-sma-dot" style={{ background: "#3d7ef5" }}/><span className="tt-sma-key">SMA 50</span><span className="tt-sma-val">${tooltip.s50.toFixed(2)}</span></div>}
                {overlays.sma150    && tooltip.s150 && <div className="tt-sma"><div className="tt-sma-dot" style={{ background: "#0fc0d0" }}/><span className="tt-sma-key">SMA 150</span><span className="tt-sma-val">${tooltip.s150.toFixed(2)}</span></div>}
                {overlays.smaCustom && tooltip.sCx  && <div className="tt-sma"><div className="tt-sma-dot" style={{ background: "#a78bfa" }}/><span className="tt-sma-key">SMA {customPeriod}</span><span className="tt-sma-val">${tooltip.sCx.toFixed(2)}</span></div>}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── SEARCH BAR ────────────────────────────────────────────────────────────── */
function ChartSearchBar({ watchlist, onAdd, onSelect, onRemove, activeSymbol, token }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [searching, setSearching] = useState(false);
  const ref = useRef(null);
  const debounceRef = useRef(null);

  // Live search via /market/search API with debounce
  useEffect(() => {
    if (!token || query.length < 1) { setSuggestions([]); return; }
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setSearching(true);
      api.searchSymbols(query, token)
        .then(results => {
          setSuggestions(results.map(r => ({
            sym: r.symbol, name: r.name, exchange: r.exchange || "", type: r.type || ""
          })).slice(0, 8));
        })
        .catch(() => setSuggestions([]))
        .finally(() => setSearching(false));
    }, 250);
    return () => clearTimeout(debounceRef.current);
  }, [query, token]);

  // Fetch live quotes for watchlist chips
  const [chipQuotes, setChipQuotes] = useState({});
  useEffect(() => {
    if (!token) return;
    watchlist.forEach(sym => {
      if (!chipQuotes[sym]) {
        api.getQuote(sym, token).then(q => {
          setChipQuotes(prev => ({ ...prev, [sym]: q }));
        }).catch(() => {});
      }
    });
  }, [watchlist, token]);

  useEffect(() => {
    const fn = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", fn);
    return () => document.removeEventListener("mousedown", fn);
  }, []);

  const handleSelect = (s) => {
    onAdd(s.sym);
    onSelect(s.sym);
    setQuery("");
    setOpen(false);
  };

  return (
    <div className="chart-search-bar">
      {/* Search */}
      <div className="chart-search-wrap" ref={ref}>
        <span className="chart-search-icon">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
        </span>
        <input className="chart-search-input" placeholder="Search any ticker or company name..."
          value={query}
          onChange={e => { setQuery(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={e => { if (e.key === "Escape") { setQuery(""); setOpen(false); } if (e.key === "Enter" && suggestions[0]) handleSelect(suggestions[0]); }}
        />
        {open && (suggestions.length > 0 || searching) && (
          <div className="search-suggestions">
            {searching && suggestions.length === 0 && (
              <div className="suggestion-item" style={{color:"#4a5568",justifyContent:"center"}}>Searching...</div>
            )}
            {suggestions.map(s => (
              <div key={s.sym} className="suggestion-item" onClick={() => handleSelect(s)}>
                <span className="sug-sym">{s.sym}</span>
                <span className="sug-name">{s.name}</span>
                <span style={{ marginLeft: "auto", fontFamily: "'IBM Plex Mono'", fontSize: 10, color: "#4a5568" }}>
                  {s.exchange}{s.type ? ` · ${s.type}` : ""}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Watchlist chips */}
      <div className="watchlist">
        {watchlist.map(sym => {
          const info = chipQuotes[sym];
          return (
            <div key={sym} className={`watch-chip${activeSymbol === sym ? " active" : ""}`}
              onClick={() => onSelect(sym)}>
              {sym}
              {info && (
                <span className={`chip-chg ${info.change_pct >= 0 ? "pos" : "neg"}`}>
                  {info.change_pct >= 0 ? "▲" : "▼"}{Math.abs(info.change_pct).toFixed(2)}%
                </span>
              )}
              <button className="watch-chip-close" onClick={e => { e.stopPropagation(); onRemove(sym); }}>×</button>
            </div>
          );
        })}
        {watchlist.length === 0 && (
          <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 11, color: "#4a5568" }}>
            Search and add symbols to your watchlist →
          </span>
        )}
      </div>
    </div>
  );
}

/* ─── MAIN CHARTS PAGE ──────────────────────────────────────────────────────── */
function ChartsPage({ initialSymbol, goBack, token }) {
  const [watchlist, setWatchlist] = useState(["AAPL", "NVDA", "TSLA"]);
  const [activeSymbol, setActiveSymbol] = useState(initialSymbol || "AAPL");
  const mktStatus = useMarketStatus();

  // When initialSymbol changes (nav from holdings), add and select it
  useEffect(() => {
    if (initialSymbol && !watchlist.includes(initialSymbol)) {
      setWatchlist(w => [...w, initialSymbol]);
    }
    if (initialSymbol) setActiveSymbol(initialSymbol);
  }, [initialSymbol]);

  // Fetch live quote for the active symbol
  const [quoteData, setQuoteData] = useState(null);
  const chartPollMs = mktStatus.isOpen ? 3000 : 300000;
  useEffect(() => {
    if (!token || !activeSymbol) return;
    let cancelled = false;
    const fetchQuote = () => {
      api.getQuote(activeSymbol, token)
        .then(q => { if (!cancelled) setQuoteData(q); })
        .catch(() => {});
    };
    fetchQuote();
    const id = setInterval(fetchQuote, chartPollMs);
    return () => { cancelled = true; clearInterval(id); };
  }, [activeSymbol, token, chartPollMs]);
  const stockInfo = quoteData
    ? { sym: quoteData.symbol, name: quoteData.name, price: quoteData.price,
        chg: quoteData.change, chgPct: quoteData.change_pct, open: quoteData.open,
        close: quoteData.price, vol: quoteData.volume, high: quoteData.high, low: quoteData.low }
    : { sym: activeSymbol, name: activeSymbol, price: 100, chg: 0, chgPct: 0,
        open: 100, close: 100, vol: 0, high: 100, low: 100 };

  const addSymbol = sym => {
    if (!watchlist.includes(sym)) setWatchlist(w => [...w, sym]);
  };
  const removeSymbol = sym => {
    setWatchlist(w => w.filter(s => s !== sym));
    if (activeSymbol === sym) setActiveSymbol(watchlist.find(s => s !== sym) || "");
  };

  return (
    <div className="charts-page" style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <style>{CHART_CSS}</style>

      {/* Page header */}
      <div style={{
        background: "#0e1117", borderBottom: "1px solid #1e2535",
        padding: "14px 24px", display: "flex", alignItems: "flex-end", justifyContent: "space-between",
        flexShrink: 0
      }}>
        <div>
          <div style={{ fontFamily: "'Bebas Neue', sans-serif", fontSize: 28, color: "#e8f0fa", letterSpacing: 1, lineHeight: 1, display:"flex", alignItems:"center" }}>
            <button className="btn btn-ghost" onClick={goBack} style={{padding:"4px 6px",marginRight:8}}><Ic.back/></button>
            CHARTS
          </div>
          <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 11, color: "#4a5568", marginTop: 4 }}>
            INTERACTIVE ANALYSIS · SMA OVERLAYS · BREAKOUT DETECTION
          </div>
        </div>
        <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 10, color: "#4a5568", textAlign: "right" }}>
          <div style={{ color: mktStatus.isOpen ? "#00d97e" : "var(--red)", display: "flex", alignItems: "center", gap: 5, justifyContent: "flex-end" }}>
            <span style={{ width: 5, height: 5, borderRadius: "50%", background: mktStatus.isOpen ? "#00d97e" : "var(--red)", display: "inline-block", animation: "blink 2s infinite" }} />
            {mktStatus.isOpen ? "NYSE OPEN" : `CLOSED · OPENS IN ${mktStatus.countdown}`}
          </div>
          <div style={{ marginTop: 2 }}>{mktStatus.dateStr} · {mktStatus.timeStr}</div>
        </div>
      </div>

      {/* Search + watchlist */}
      <ChartSearchBar
        watchlist={watchlist}
        onAdd={addSymbol}
        onSelect={setActiveSymbol}
        onRemove={removeSymbol}
        activeSymbol={activeSymbol}
        token={token}
      />

      {/* Chart */}
      <div style={{ flex: 1, overflow: "hidden", minHeight: 0, position: "relative" }}>
        {activeSymbol ? (
          <StockChart
            key={activeSymbol}
            symbol={activeSymbol}
            stockInfo={stockInfo}
            token={token}
          />
        ) : (
          <div className="chart-empty">
            <div className="chart-empty-title">NO SYMBOL SELECTED</div>
            <div className="chart-empty-sub">Search for a symbol above to load chart</div>
          </div>
        )}
      </div>
    </div>
  );
}


/* ═══════════════════════════════════════════════════════════════════════════
   IMPORT PAGE — Broker statement download + Manual portfolio entry
   Subpages: Broker Downloads | Manual Import | Portfolio Review
═══════════════════════════════════════════════════════════════════════════ */

const IMPORT_CSS = `
/* ── Import page layout ── */
.import-page { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.import-subnav {
  background: var(--bg2); border-bottom: 1px solid var(--border);
  padding: 0 24px; display: flex; gap: 0;
}
.import-tab {
  padding: 12px 20px; font-family: var(--font-mono); font-size: 11px;
  font-weight: 500; color: var(--muted); cursor: pointer; border: none;
  background: none; letter-spacing: 0.8px; text-transform: uppercase;
  border-bottom: 2px solid transparent; margin-bottom: -1px;
  transition: all 0.12s;
}
.import-tab:hover { color: var(--text); }
.import-tab.active { color: var(--amber); border-bottom-color: var(--amber); }

/* ── Broker cards ── */
.broker-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px; padding: 24px;
}
.broker-card {
  background: var(--panel); border: 1px solid var(--border);
  padding: 20px; cursor: pointer;
  transition: all 0.15s; position: relative; overflow: hidden;
}
.broker-card::before {
  content: ''; position: absolute; left: 0; top: 0; bottom: 0;
  width: 2px; background: var(--border); transition: background 0.15s;
}
.broker-card:hover { border-color: var(--border2); }
.broker-card:hover::before { background: var(--amber); }
.broker-card.selected { border-color: var(--amber); background: rgba(15,125,64,0.04); }
.broker-card.selected::before { background: var(--amber); }
.broker-logo-row { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.broker-logo {
  width: 40px; height: 40px; border-radius: 2px;
  display: flex; align-items: center; justify-content: center;
  font-family: var(--font-disp); font-size: 14px; font-weight: 700;
  flex-shrink: 0; letter-spacing: 0.5px;
}
.broker-name { font-family: var(--font-sans); font-size: 15px; font-weight: 600; color: var(--bright); }
.broker-type { font-family: var(--font-mono); font-size: 10px; color: var(--muted); margin-top: 2px; letter-spacing: 0.5px; }
.broker-desc { font-family: var(--font-mono); font-size: 11px; color: var(--mid); line-height: 1.5; margin-bottom: 12px; }
.broker-formats { display: flex; gap: 6px; flex-wrap: wrap; }
.format-chip {
  font-family: var(--font-mono); font-size: 9px; font-weight: 600;
  padding: 2px 7px; letter-spacing: 0.8px; text-transform: uppercase;
  border: 1px solid var(--border2); color: var(--mid); border-radius: 1px;
}
.broker-download-area {
  background: var(--bg2); border: 1px solid var(--border);
  margin: 0 24px 24px;
}
.broker-dl-header {
  padding: 14px 18px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; justify-content: space-between;
}
.broker-dl-title { font-family: var(--font-disp); font-size: 20px; color: var(--amber); letter-spacing: 1px; }
.broker-dl-body { padding: 20px 18px; display: flex; flex-direction: column; gap: 16px; }
.dl-step {
  display: flex; gap: 14px; align-items: flex-start;
}
.dl-step-num {
  width: 24px; height: 24px; border-radius: 1px;
  background: rgba(15,125,64,0.1); border: 1px solid rgba(15,125,64,0.25);
  display: flex; align-items: center; justify-content: center;
  font-family: var(--font-mono); font-size: 11px; font-weight: 600; color: var(--amber);
  flex-shrink: 0; margin-top: 1px;
}
.dl-step-text { font-family: var(--font-mono); font-size: 12px; color: var(--text); line-height: 1.6; }
.dl-step-text a { color: var(--amber); text-decoration: none; }
.dl-step-text code {
  background: var(--bg3); border: 1px solid var(--border);
  padding: 1px 5px; font-size: 11px; color: var(--cyan);
}
.drop-zone {
  border: 1px dashed var(--border2); padding: 28px;
  text-align: center; cursor: pointer; transition: all 0.15s;
  background: var(--bg3);
}
.drop-zone:hover, .drop-zone.drag-over {
  border-color: var(--amber); background: rgba(15,125,64,0.04);
}
.drop-zone-icon { font-family: var(--font-mono); font-size: 11px; color: var(--muted); margin-top: 8px; }
.drop-zone-sub { font-family: var(--font-mono); font-size: 10px; color: var(--muted); margin-top: 4px; }
.upload-progress { height: 2px; background: var(--border); margin-top: 8px; overflow: hidden; }
.upload-progress-bar { height: 100%; background: var(--amber); transition: width 0.3s; }
.file-row {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px; background: var(--bg3); border: 1px solid var(--border);
  font-family: var(--font-mono); font-size: 11px;
}
.file-name { flex: 1; color: var(--text); }
.file-size { color: var(--muted); }
.file-status-ok { color: var(--green); display: flex; align-items: center; gap: 4px; }
.file-status-err { color: var(--red); }

/* ── Manual import form ── */
.manual-form-wrap { padding: 24px; display: flex; flex-direction: column; gap: 20px; max-width: 900px; }
.manual-entries-table {
  background: var(--panel); border: 1px solid var(--border);
}
.manual-entries-header {
  padding: 10px 16px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; justify-content: space-between;
}
.entry-row-form {
  display: grid;
  grid-template-columns: 140px 1fr 80px 120px 120px 140px 40px;
  gap: 8px; padding: 10px 12px; border-bottom: 1px solid var(--border);
  align-items: center;
}
.entry-row-form:last-child { border-bottom: none; }
.entry-data-row {
  display: grid;
  grid-template-columns: 140px 1fr 80px 120px 120px 140px 40px;
  gap: 8px; padding: 10px 12px; border-bottom: 1px solid var(--border);
  align-items: center; font-family: var(--font-mono); font-size: 12px;
  transition: background 0.08s;
}
.entry-data-row:hover { background: rgba(255,255,255,0.02); }
.entry-data-row:last-child { border-bottom: none; }
.entry-th {
  font-family: var(--font-mono); font-size: 9px; font-weight: 500;
  color: var(--muted); letter-spacing: 1px; text-transform: uppercase;
}
.entry-form-input {
  background: var(--bg3); border: 1px solid var(--border);
  padding: 6px 8px; font-family: var(--font-mono); font-size: 11px;
  color: var(--bright); outline: none; width: 100%; border-radius: 2px;
  transition: border-color 0.1s;
}
.entry-form-input:focus { border-color: var(--amber); }
.entry-form-input::placeholder { color: var(--muted); }
select.entry-form-input {
  appearance: none; cursor: pointer;
  background-image: url("data:image/svg+xml,%3Csvg width='8' height='5' viewBox='0 0 8 5' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1l3 3 3-3' stroke='%234a5568' strokeWidth='1.2'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: right 7px center;
  padding-right: 20px;
}
select.entry-form-input option { background: var(--bg3); }
.asset-type-badge {
  display: inline-flex; align-items: center; gap: 4px;
  font-family: var(--font-mono); font-size: 10px; font-weight: 600;
  padding: 2px 7px; border-radius: 1px; text-transform: uppercase; letter-spacing: 0.5px;
}
.at-stock   { color: #3d7ef5; background: rgba(61,126,245,0.08); border: 1px solid rgba(61,126,245,0.2); }
.at-crypto  { color: #0f7d40; background: rgba(15,125,64,0.08); border: 1px solid rgba(15,125,64,0.2); }
.at-metalsphisical  { color: #fbbf24; background: rgba(251,191,36,0.08); border: 1px solid rgba(251,191,36,0.2); }
.at-metalsetf { color: #0fc0d0; background: rgba(15,192,208,0.08); border: 1px solid rgba(15,192,208,0.2); }
.delete-row-btn {
  background: none; border: none; cursor: pointer; color: var(--muted);
  display: flex; align-items: center; justify-content: center;
  transition: color 0.1s; width: 28px; height: 28px;
  border-radius: 2px;
}
.delete-row-btn:hover { color: var(--red); background: rgba(240,68,56,0.08); }
.import-summary-bar {
  background: var(--bg2); border: 1px solid var(--border);
  padding: 16px 18px; display: flex; gap: 24px; align-items: center;
}
.summary-stat { display: flex; flex-direction: column; gap: 3px; }
.summary-lbl { font-family: var(--font-mono); font-size: 9px; color: var(--muted); letter-spacing: 1px; text-transform: uppercase; }
.summary-val { font-family: var(--font-mono); font-size: 16px; font-weight: 600; color: var(--bright); }
.confirm-actions { display: flex; gap: 10px; margin-left: auto; align-items: center; }

/* ── Portfolio review ── */
.review-wrap { padding: 24px; display: flex; flex-direction: column; gap: 16px; }
.review-section-title {
  font-family: var(--font-mono); font-size: 10px; font-weight: 500;
  color: var(--muted); letter-spacing: 1.5px; text-transform: uppercase;
  padding-bottom: 8px; border-bottom: 1px solid var(--border);
}
.review-empty {
  text-align: center; padding: 48px; color: var(--muted);
  font-family: var(--font-mono); font-size: 12px; letter-spacing: 0.5px;
}
.review-empty-title {
  font-family: var(--font-disp); font-size: 28px; color: var(--muted);
  letter-spacing: 2px; margin-bottom: 8px;
}
`;

const BROKER_LIST = [
  {
    id: "robinhood", name: "Robinhood", short: "RH", color: "#00c805", bg: "#003d01",
    type: "US Equities & Crypto", formats: ["CSV"],
    desc: "Export account history from Settings → Account → History & Statements",
    steps: [
      { text: 'Log into <a href="#" onClick="return false">Robinhood Web</a>' },
      { text: 'Go to <code>Account → Statements & History</code>' },
      { text: 'Select date range and click <code>Download CSV</code>' },
      { text: 'Upload the downloaded file below' },
    ],
    cols: "Date, Type, Symbol, Shares, Price, Amount",
  },
  {
    id: "ibkr", name: "IBKR", short: "IB", color: "#c8282a", bg: "#3d0a0b",
    type: "Multi-asset Global Broker", formats: ["CSV", "XML", "PDF"],
    desc: "Interactive Brokers Flex Query exports detailed trade history",
    steps: [
      { text: 'Log into <a href="#" onClick="return false">IBKR Client Portal</a>' },
      { text: 'Go to <code>Reports → Statements → Flex Queries</code>' },
      { text: 'Create a new Flex Query or use the default <code>Activity Statement</code>' },
      { text: 'Run query, select CSV format, and download' },
    ],
    cols: "TradeDate, Symbol, Quantity, TradePrice, IBCommission, AssetClass",
  },
  {
    id: "etrade", name: "E*TRADE", short: "ET", color: "#6633cc", bg: "#1a0d33",
    type: "US Equities & Options", formats: ["CSV", "OFX"],
    desc: "E*TRADE provides full trade history exports from the Brokerage account section",
    steps: [
      { text: 'Log into <a href="#" onClick="return false">E*TRADE</a> and go to <code>Accounts</code>' },
      { text: 'Select <code>Documents → Brokerage Tax Documents</code>' },
      { text: 'Choose <code>Trade Confirmations</code> and date range' },
      { text: 'Click <code>Export to CSV</code> and upload below' },
    ],
    cols: "TransactionDate, SecurityType, Symbol, Quantity, Price, Amount",
  },
  {
    id: "td", name: "TD Ameritrade", short: "TD", color: "#00a651", bg: "#003118",
    type: "US Full-Service Broker", formats: ["CSV", "OFX", "QFX"],
    desc: "Schwab (formerly TD Ameritrade) exports trade history with full OHLCV data",
    steps: [
      { text: 'Log into <a href="#" onClick="return false">Schwab/TDA</a>' },
      { text: 'Navigate to <code>History & Statements → Transactions</code>' },
      { text: 'Set date range and select <code>Export to Spreadsheet (.csv)</code>' },
      { text: 'Upload the downloaded CSV file below' },
    ],
    cols: "DATE, TRANSACTION TYPE, SECURITY, QUANTITY, PRICE, AMOUNT",
  },
  {
    id: "coinbase", name: "Coinbase", short: "CB", color: "#0052ff", bg: "#000f3d",
    type: "Cryptocurrency Exchange", formats: ["CSV"],
    desc: "Full transaction history including buys, sells, transfers, staking rewards",
    steps: [
      { text: 'Log into <a href="#" onClick="return false">Coinbase</a>' },
      { text: 'Go to <code>Profile → Statements</code>' },
      { text: 'Under <code>Transaction History</code>, select date range' },
      { text: 'Click <code>Generate Report</code> then download CSV' },
    ],
    cols: "Timestamp, Transaction Type, Asset, Quantity Transacted, Spot Price, Subtotal",
  },
  {
    id: "binance", name: "Binance", short: "BN", color: "#f0b90b", bg: "#2d2200",
    type: "Global Crypto Exchange", formats: ["CSV", "XLSX"],
    desc: "Export full order history, P&L reports, and tax statements from Binance",
    steps: [
      { text: 'Log into <a href="#" onClick="return false">Binance</a>' },
      { text: 'Go to <code>Orders → Trade History</code>' },
      { text: 'Select date range (max 3 months per export)' },
      { text: 'Click <code>Export Complete Trade History</code> → CSV' },
    ],
    cols: "Date, Pair, Side, Price, Executed, Amount, Fee",
  },
  {
    id: "schwab", name: "Charles Schwab", short: "CS", color: "#1b7ee0", bg: "#051d35",
    type: "US Full-Service Broker", formats: ["CSV", "OFX", "QFX"],
    desc: "Download detailed position history and trade confirmations from Schwab",
    steps: [
      { text: 'Log into <a href="#" onClick="return false">Schwab</a>' },
      { text: 'Go to <code>Accounts → History</code>' },
      { text: 'Filter transactions by date range and type' },
      { text: 'Click <code>Export</code> and choose CSV format' },
    ],
    cols: "Date, Action, Symbol, Description, Quantity, Price, Amount",
  },
  {
    id: "fidelity", name: "Fidelity", short: "FD", color: "#009b49", bg: "#002d15",
    type: "US Full-Service Broker", formats: ["CSV", "OFX"],
    desc: "Download account history and tax documents directly from Fidelity NetBenefits",
    steps: [
      { text: 'Log into <a href="#" onClick="return false">Fidelity</a>' },
      { text: 'Go to <code>Accounts & Trade → Portfolio</code>' },
      { text: 'Select <code>Activity & Orders → History</code>' },
      { text: 'Click <code>Download</code> and select CSV format' },
    ],
    cols: "Run Date, Action, Symbol, Description, Type, Quantity, Price, Amount",
  },
];

const ASSET_TYPES = [
  { value: "Stock",           label: "STOCK",            cls: "at-stock" },
  { value: "Crypto",          label: "CRYPTO",           cls: "at-crypto" },
  { value: "MetalsPhisical",  label: "METALS PHYSICAL",  cls: "at-metalsphisical" },
  { value: "MetalsETF",       label: "METALS ETF",       cls: "at-metalsetf" },
];

const EMPTY_ENTRY = () => ({
  id: Date.now() + Math.random(),
  type: "Stock",
  identifier: "",
  qty: "",
  purchasePrice: "",
  datePurchased: "",
});

function AssetTypeBadge({ type }) {
  const def = ASSET_TYPES.find(t => t.value === type) || ASSET_TYPES[0];
  return <span className={`asset-type-badge ${def.cls}`}>{def.label}</span>;
}

function ImportPage({ addToast, goBack }) {
  const [subpage, setSubpage] = useState("brokers");
  const [selectedBroker, setSelectedBroker] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [entries, setEntries] = useState([EMPTY_ENTRY()]);
  const [savedEntries, setSavedEntries] = useState([]);
  const [importedFromBroker, setImportedFromBroker] = useState([]);
  const fileRef = useRef(null);

  // ── File upload simulation ──────────────────────────────────────────────
  const simulateUpload = (fileName, fileSize) => {
    setUploading(true);
    setUploadProgress(0);
    const interval = setInterval(() => {
      setUploadProgress(p => {
        if (p >= 100) {
          clearInterval(interval);
          setUploading(false);
          const rows = Math.floor(Math.random() * 200) + 40;
          setUploadedFiles(prev => [...prev, {
            name: fileName, size: fileSize,
            rows, broker: selectedBroker?.name || "Unknown", ok: true,
          }]);
          addToast && addToast(`FILE PARSED · ${rows} TRANSACTIONS IMPORTED FROM ${fileName.toUpperCase()}`);
          // Simulate broker-imported portfolio entries
          const mockImported = [
            { id: Date.now()+1, type:"Stock", identifier:"AAPL", qty:"10", purchasePrice:"142.30", datePurchased:"2024-03-15", source: selectedBroker?.name },
            { id: Date.now()+2, type:"Stock", identifier:"NVDA", qty:"5",  purchasePrice:"480.00", datePurchased:"2024-06-20", source: selectedBroker?.name },
            { id: Date.now()+3, type:"Crypto", identifier:"BTC",  qty:"0.25",purchasePrice:"42000", datePurchased:"2024-01-10", source: selectedBroker?.name },
          ];
          setImportedFromBroker(prev => [...prev, ...mockImported]);
          return 100;
        }
        return p + 12;
      });
    }, 150);
  };

  const handleDrop = e => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) simulateUpload(file.name, `${(file.size / 1024).toFixed(1)} KB`);
  };

  const handleFileInput = e => {
    const file = e.target.files[0];
    if (file) simulateUpload(file.name, `${(file.size / 1024).toFixed(1)} KB`);
  };

  // ── Manual entries management ───────────────────────────────────────────
  const updateEntry = (id, field, value) => {
    setEntries(es => es.map(e => e.id === id ? { ...e, [field]: value } : e));
  };
  const addEntry = () => setEntries(es => [...es, EMPTY_ENTRY()]);
  const deleteEntry = id => setEntries(es => es.filter(e => e.id !== id));

  const isEntryValid = e => e.identifier.trim() && e.qty && e.purchasePrice && e.datePurchased;
  const validEntries = entries.filter(isEntryValid);

  const saveEntries = () => {
    if (validEntries.length === 0) return;
    setSavedEntries(prev => [...prev, ...validEntries.map(e => ({...e, source:"Manual"}))]);
    setEntries([EMPTY_ENTRY()]);
    addToast && addToast(`${validEntries.length} POSITION${validEntries.length > 1 ? "S" : ""} ADDED TO PORTFOLIO`);
    setSubpage("review");
  };

  const totalSaved = savedEntries.length + importedFromBroker.length;
  const totalValue = [...savedEntries, ...importedFromBroker].reduce((s, e) => {
    return s + (parseFloat(e.qty) || 0) * (parseFloat(e.purchasePrice) || 0);
  }, 0);

  const fmtCurrency = v => "$" + v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  return (
    <div className="page-scroll">
      <style>{IMPORT_CSS}</style>

      {/* Page header */}
      <div className="page-header">
        <div>
          <div className="page-title"><button className="btn btn-ghost" onClick={goBack} style={{padding:"4px 6px",marginRight:8,verticalAlign:"middle"}}><Ic.back/></button>IMPORT PORTFOLIO</div>
          <div className="page-sub">DOWNLOAD BROKER STATEMENTS · MANUAL ENTRY · PORTFOLIO REVIEW</div>
        </div>
        <div className="page-actions">
          {totalSaved > 0 && (
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--amber)", display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--amber)", display: "inline-block" }} />
              {totalSaved} POSITIONS STAGED
            </div>
          )}
          <button className="btn btn-outline" onClick={() => setSubpage("manual")}>
            <Ic.file /> MANUAL ENTRY
          </button>
          <button className="btn btn-amber" onClick={() => setSubpage("review")}>
            <Ic.import /> REVIEW & COMMIT
          </button>
        </div>
      </div>

      {/* Sub-navigation */}
      <div className="import-subnav">
        {[
          { id: "brokers", label: "Broker Statements" },
          { id: "manual",  label: "Manual Import" },
          { id: "review",  label: `Portfolio Review${totalSaved > 0 ? ` (${totalSaved})` : ""}` },
        ].map(t => (
          <button key={t.id} className={`import-tab${subpage === t.id ? " active" : ""}`}
            onClick={() => setSubpage(t.id)}>{t.label}</button>
        ))}
      </div>

      {/* ── BROKERS SUBPAGE ── */}
      {subpage === "brokers" && (
        <div style={{ flex: 1, overflow: "auto" }}>
          <div style={{ padding: "16px 24px 0", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--muted)" }}>
            SELECT YOUR BROKER TO SEE EXPORT INSTRUCTIONS AND UPLOAD YOUR STATEMENT FILE
          </div>

          {/* Broker grid */}
          <div className="broker-grid">
            {BROKER_LIST.map(b => (
              <div key={b.id}
                className={`broker-card${selectedBroker?.id === b.id ? " selected" : ""}`}
                onClick={() => setSelectedBroker(b)}>
                <div className="broker-logo-row">
                  <div className="broker-logo" style={{ background: b.bg, color: b.color }}>
                    {b.short}
                  </div>
                  <div>
                    <div className="broker-name">{b.name}</div>
                    <div className="broker-type">{b.type}</div>
                  </div>
                  {selectedBroker?.id === b.id && (
                    <div style={{ marginLeft: "auto", color: "var(--amber)", display: "flex" }}>
                      <Ic.check />
                    </div>
                  )}
                </div>
                <div className="broker-desc">{b.desc}</div>
                <div className="broker-formats">
                  {b.formats.map(f => <div key={f} className="format-chip">{f}</div>)}
                </div>
              </div>
            ))}
          </div>

          {/* Selected broker instructions + upload */}
          {selectedBroker && (
            <div className="broker-download-area">
              <div className="broker-dl-header">
                <div>
                  <div className="broker-dl-title">{selectedBroker.name.toUpperCase()} · EXPORT GUIDE</div>
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)", marginTop: 3 }}>
                    SUPPORTED COLUMNS: {selectedBroker.cols}
                  </div>
                </div>
                <button className="btn btn-ghost" onClick={() => setSelectedBroker(null)}
                  style={{ fontSize: 9, padding: "4px 10px" }}>CLOSE</button>
              </div>
              <div className="broker-dl-body">
                {/* Steps */}
                {selectedBroker.steps.map((step, i) => (
                  <div key={i} className="dl-step">
                    <div className="dl-step-num">{i + 1}</div>
                    <div className="dl-step-text" dangerouslySetInnerHTML={{ __html: step.text }} />
                  </div>
                ))}

                {/* Drop zone */}
                <div className="drop-zone"
                  onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={handleDrop}
                  onClick={() => fileRef.current?.click()}
                  style={{ borderColor: dragOver ? "var(--amber)" : undefined }}>
                  <div style={{ fontSize: 28 }}>
                    <Ic.upload />
                  </div>
                  <div className="drop-zone-icon">
                    DROP {selectedBroker.formats.join(" / ")} FILE HERE OR CLICK TO BROWSE
                  </div>
                  <div className="drop-zone-sub">Max 50MB · {selectedBroker.formats.join(", ")} formats accepted</div>
                  {uploading && (
                    <div className="upload-progress">
                      <div className="upload-progress-bar" style={{ width: `${uploadProgress}%` }} />
                    </div>
                  )}
                </div>
                <input ref={fileRef} type="file" accept=".csv,.xlsx,.xml,.ofx,.qfx"
                  style={{ display: "none" }} onChange={handleFileInput} />

                {/* Uploaded files */}
                {uploadedFiles.map((f, i) => (
                  <div key={i} className="file-row">
                    <div style={{ color: "var(--amber)", display: "flex" }}><Ic.file /></div>
                    <div className="file-name">{f.name}</div>
                    <div className="file-size">{f.size}</div>
                    <div className="file-status-ok"><Ic.check /> {f.rows} transactions</div>
                    <button
                      style={{ background: "none", border: "none", cursor: "pointer", color: "var(--muted)", marginLeft: "auto", display: "flex" }}
                      onClick={() => setUploadedFiles(p => p.filter((_, j) => j !== i))}>
                      <Ic.trash />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── MANUAL IMPORT SUBPAGE ── */}
      {subpage === "manual" && (
        <div style={{ flex: 1, overflow: "auto" }}>
          <div className="manual-form-wrap">
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--muted)" }}>
              MANUALLY ENTER POSITIONS. REQUIRED FIELDS: TYPE · IDENTIFIER · QTY · PURCHASE PRICE · DATE PURCHASED
            </div>

            {/* Entries table */}
            <div className="manual-entries-table">
              <div className="manual-entries-header">
                <span className="panel-title">POSITION ENTRIES</span>
                <button className="btn btn-ghost" style={{ fontSize: 9, padding: "4px 10px" }} onClick={addEntry}>
                  <Ic.plus /> ADD ROW
                </button>
              </div>

              {/* Header row */}
              <div className="entry-row-form" style={{ background: "var(--bg2)", paddingTop: 8, paddingBottom: 8 }}>
                {["ASSET TYPE", "IDENTIFIER / SYMBOL", "QUANTITY", "PURCHASE PRICE", "DATE PURCHASED", "NOTES", ""].map((h, i) => (
                  <div key={i} className="entry-th">{h}</div>
                ))}
              </div>

              {/* Entry rows */}
              {entries.map((entry) => (
                <div key={entry.id} className="entry-row-form">
                  {/* Type */}
                  <select className="entry-form-input" value={entry.type}
                    onChange={e => updateEntry(entry.id, "type", e.target.value)}>
                    {ASSET_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                  </select>

                  {/* Identifier */}
                  <input className="entry-form-input" placeholder={
                    entry.type === "Crypto" ? "BTC, ETH, SOL…" :
                    entry.type === "MetalsPhisical" ? "Gold 1oz Bar, Silver Coin…" :
                    entry.type === "MetalsETF" ? "GLD, SLV, GOLD…" :
                    "AAPL, MSFT, TSLA…"
                  }
                    value={entry.identifier}
                    onChange={e => updateEntry(entry.id, "identifier", e.target.value.toUpperCase())} />

                  {/* Quantity */}
                  <input className="entry-form-input" type="number" placeholder="0.00"
                    min="0" step="any" value={entry.qty}
                    onChange={e => updateEntry(entry.id, "qty", e.target.value)} />

                  {/* Purchase price */}
                  <div style={{ position: "relative" }}>
                    <span style={{ position: "absolute", left: 8, top: "50%", transform: "translateY(-50%)", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--muted)", pointerEvents: "none" }}>$</span>
                    <input className="entry-form-input" type="number" placeholder="0.00"
                      style={{ paddingLeft: 18 }} min="0" step="any"
                      value={entry.purchasePrice}
                      onChange={e => updateEntry(entry.id, "purchasePrice", e.target.value)} />
                  </div>

                  {/* Date */}
                  <input className="entry-form-input" type="date"
                    value={entry.datePurchased}
                    max={new Date().toISOString().split("T")[0]}
                    onChange={e => updateEntry(entry.id, "datePurchased", e.target.value)} />

                  {/* Notes (optional) */}
                  <input className="entry-form-input" placeholder="Optional notes…"
                    value={entry.notes || ""}
                    onChange={e => updateEntry(entry.id, "notes", e.target.value)} />

                  {/* Delete */}
                  <button className="delete-row-btn" onClick={() => deleteEntry(entry.id)}>
                    <Ic.trash />
                  </button>
                </div>
              ))}
            </div>

            {/* Summary + save */}
            <div className="import-summary-bar">
              <div className="summary-stat">
                <div className="summary-lbl">TOTAL ROWS</div>
                <div className="summary-val">{entries.length}</div>
              </div>
              <div className="summary-stat">
                <div className="summary-lbl">VALID ROWS</div>
                <div className="summary-val" style={{ color: validEntries.length > 0 ? "var(--green)" : "var(--muted)" }}>
                  {validEntries.length}
                </div>
              </div>
              <div className="summary-stat">
                <div className="summary-lbl">STAGED COST BASIS</div>
                <div className="summary-val" style={{ color: "var(--amber)" }}>
                  {fmtCurrency(validEntries.reduce((s, e) =>
                    s + (parseFloat(e.qty) || 0) * (parseFloat(e.purchasePrice) || 0), 0))}
                </div>
              </div>
              <div className="confirm-actions">
                <button className="btn btn-ghost" onClick={addEntry}><Ic.plus /> ADD ROW</button>
                <button className="btn btn-outline" onClick={() => setEntries([EMPTY_ENTRY()])}>
                  CLEAR ALL
                </button>
                <button className="btn btn-amber"
                  disabled={validEntries.length === 0}
                  onClick={saveEntries}
                  style={{ opacity: validEntries.length === 0 ? 0.4 : 1, cursor: validEntries.length === 0 ? "not-allowed" : "pointer" }}>
                  <Ic.check /> SAVE {validEntries.length > 0 ? `${validEntries.length} ` : ""}POSITIONS
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── REVIEW SUBPAGE ── */}
      {subpage === "review" && (
        <div style={{ flex: 1, overflow: "auto" }}>
          <div className="review-wrap">
            {/* Summary stats */}
            <div className="grid-stats stagger" style={{ margin: 0 }}>
              {[
                { lbl: "Total Positions",  val: totalSaved,               cls: totalSaved > 0 ? "amber" : "" },
                { lbl: "Cost Basis",       val: fmtCurrency(totalValue),  cls: "" },
                { lbl: "Stocks",           val: [...savedEntries, ...importedFromBroker].filter(e => e.type === "Stock").length, cls: "" },
                { lbl: "Crypto",           val: [...savedEntries, ...importedFromBroker].filter(e => e.type === "Crypto").length, cls: "" },
                { lbl: "Metals",           val: [...savedEntries, ...importedFromBroker].filter(e => e.type === "MetalsPhisical" || e.type === "MetalsETF").length, cls: "" },
              ].map((s, i) => (
                <div key={i} className="stat-block">
                  <div className="stat-lbl">{s.lbl}</div>
                  <div className={`stat-val${s.cls ? " " + s.cls : ""}`}>{s.val}</div>
                </div>
              ))}
            </div>

            {totalSaved === 0 ? (
              <div className="review-empty">
                <div className="review-empty-title">NO POSITIONS STAGED</div>
                Import from a broker or add positions manually
              </div>
            ) : (
              <>
                {/* Broker imported */}
                {importedFromBroker.length > 0 && (
                  <div className="panel">
                    <div className="panel-header">
                      <span className="panel-title">IMPORTED FROM BROKER STATEMENTS</span>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>
                        {importedFromBroker.length} POSITIONS
                      </span>
                    </div>
                    <ReviewTable
                      entries={importedFromBroker}
                      onDelete={id => setImportedFromBroker(p => p.filter(e => e.id !== id))}
                    />
                  </div>
                )}

                {/* Manually entered */}
                {savedEntries.length > 0 && (
                  <div className="panel">
                    <div className="panel-header">
                      <span className="panel-title">MANUALLY ENTERED POSITIONS</span>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>
                        {savedEntries.length} POSITIONS
                      </span>
                    </div>
                    <ReviewTable
                      entries={savedEntries}
                      onDelete={id => setSavedEntries(p => p.filter(e => e.id !== id))}
                    />
                  </div>
                )}

                {/* Commit button */}
                <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, paddingBottom: 24 }}>
                  <button className="btn btn-outline" onClick={() => {
                    setSavedEntries([]); setImportedFromBroker([]);
                    addToast && addToast("PORTFOLIO CLEARED");
                  }}>CLEAR ALL</button>
                  <button className="btn btn-amber" onClick={() => {
                    addToast && addToast(`${totalSaved} POSITIONS COMMITTED TO PORTFOLIO · SYNC COMPLETE`);
                  }}>
                    <Ic.check /> COMMIT {totalSaved} POSITIONS TO PORTFOLIO
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ReviewTable({ entries, onDelete }) {
  const fmtCurrency = v => "$" + parseFloat(v || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  return (
    <div style={{ overflowX: "auto" }}>
      <table className="data-table">
        <thead>
          <tr>
            <th>TYPE</th>
            <th>IDENTIFIER</th>
            <th className="right">QUANTITY</th>
            <th className="right">PURCHASE PRICE</th>
            <th className="right">COST BASIS</th>
            <th>DATE</th>
            <th>SOURCE</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {entries.map(e => {
            const cost = (parseFloat(e.qty) || 0) * (parseFloat(e.purchasePrice) || 0);
            return (
              <tr key={e.id}>
                <td><AssetTypeBadge type={e.type} /></td>
                <td>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div className="sym-badge">{(e.identifier || "?").slice(0, 3)}</div>
                    <span style={{ fontWeight: 600, color: "var(--bright)" }}>{e.identifier || "—"}</span>
                  </div>
                </td>
                <td className="right">{parseFloat(e.qty || 0).toLocaleString()}</td>
                <td className="right">{fmtCurrency(e.purchasePrice)}</td>
                <td className="right" style={{ color: "var(--amber)", fontWeight: 600 }}>{fmtCurrency(cost)}</td>
                <td style={{ color: "var(--muted)" }}>{e.datePurchased || "—"}</td>
                <td>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--mid)" }}>
                    {e.source || "Manual"}
                  </span>
                </td>
                <td>
                  <button className="delete-row-btn" onClick={() => onDelete(e.id)}><Ic.trash /></button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}


export default function App() {
  const [page, setPageRaw] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("reset_token")) return "reset-password";
    return sessionStorage.getItem("fb_token") ? "dashboard" : "login";
  });
  const [pageHistory, setPageHistory] = useState([]);
  const setPage = useCallback((next) => {
    setPageRaw(prev => { setPageHistory(h => [...h.slice(-9), prev]); return next; });
  }, []);
  const goBack = useCallback(() => {
    setPageHistory(h => {
      const copy = [...h];
      const prev = copy.pop() || "dashboard";
      setPageRaw(prev);
      return copy;
    });
  }, []);
  const [resetToken, setResetToken] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("reset_token") || null;
  });
  const [showTxModal, setShowTxModal] = useState(false);
  const [toasts, setToasts] = useState([]);
  const [chartSymbol, setChartSymbol] = useState(null);

  const addToast = (msg, err=false) => {
    const id = Date.now();
    setToasts(t=>[...t,{id,msg,err}]);
    setTimeout(()=>setToasts(t=>t.filter(x=>x.id!==id)),3200);
  };

  // ── Auth state ──────────────────────────────────────────────────────────
  const [authToken,   setAuthToken]   = useState(() => sessionStorage.getItem("fb_token") || null);
  const [authUser,    setAuthUser]    = useState(() => {
    try { return JSON.parse(sessionStorage.getItem("fb_user") || "null"); } catch { return null; }
  });
  const [accountId,   setAccountId]   = useState(() => sessionStorage.getItem("fb_account") || null);
  const [backendOk,   setBackendOk]   = useState(null);   // null=unknown, true, false
  const marketStatus = useMarketStatus();

  // Probe backend health once on mount
  useEffect(() => {
    api.health().then(() => setBackendOk(true)).catch(() => setBackendOk(false));
  }, []);

  const handleLogin = async (email, password) => {
    if (!backendOk) {
      // Offline / demo mode — skip real auth, use demo credentials
      const demoUser = { email, first_name: "Alex", last_name: "Morgan", user_id: "demo" };
      setAuthUser(demoUser);
      setAccountId("ACC-4821");
      setPage("dashboard");
      addToast("DEMO MODE · BACKEND OFFLINE — SHOWING MOCK DATA");
      return;
    }
    try {
      const res = await api.login(email, password);
      setAuthToken(res.access_token);
      setAuthUser({ email: res.email, first_name: res.first_name, last_name: res.last_name, user_id: res.user_id });
      sessionStorage.setItem("fb_token", res.access_token);
      sessionStorage.setItem("fb_user", JSON.stringify({ email: res.email, first_name: res.first_name, last_name: res.last_name, user_id: res.user_id }));

      // Fetch first account
      try {
        const accounts = await api.listAccounts(res.user_id, res.access_token);
        if (accounts.length > 0) {
          setAccountId(accounts[0].account_id);
          sessionStorage.setItem("fb_account", accounts[0].account_id);
        }
      } catch (_) { /* account fetch optional */ }

      setPage("dashboard");
      addToast(`AUTHENTICATION SUCCESSFUL · WELCOME BACK, ${(res.first_name || "").toUpperCase()}`);
    } catch (err) {
      throw err; // re-throw so LoginPage can display it
    }
  };

  const handleLogout = () => {
    setAuthToken(null); setAuthUser(null); setAccountId(null);
    sessionStorage.removeItem("fb_token");
    sessionStorage.removeItem("fb_user");
    sessionStorage.removeItem("fb_account");
    setPage("login");
    addToast("SESSION TERMINATED");
  };

  // ── Listen for expired-token events from apiFetch ──────────────────────
  useEffect(() => {
    const onExpired = () => handleLogout();
    window.addEventListener("session-expired", onExpired);
    return () => window.removeEventListener("session-expired", onExpired);
  });

  // ── Inactivity auto-logout (5 minutes) ─────────────────────────────────
  useEffect(() => {
    if (!authToken) return;
    const IDLE_MS = 5 * 60 * 1000;
    const KEY = "fb_last_activity";
    const touch = () => localStorage.setItem(KEY, Date.now().toString());
    const check = () => {
      const last = parseInt(localStorage.getItem(KEY) || "0", 10);
      if (Date.now() - last >= IDLE_MS) handleLogout();
    };
    // Seed on mount so a fresh login / reload doesn't start stale
    touch();
    const interval = setInterval(check, 10000);
    const reset = () => touch();
    const events = ["mousemove", "mousedown", "keydown", "touchstart", "scroll"];
    events.forEach(e => window.addEventListener(e, reset, { passive: true }));
    return () => { clearInterval(interval); events.forEach(e => window.removeEventListener(e, reset)); };
  }, [authToken]);

  const handleTxSubmit = async (form) => {
    if (!backendOk || !authToken) {
      addToast(`TRANSACTION QUEUED (DEMO) · ${form.transaction_type.toUpperCase()} $${parseFloat(form.amount).toFixed(2)}`);
      return;
    }
    try {
      const payload = {
        account_id: accountId || form.account_id,
        transaction_type: form.transaction_type,
        amount: parseFloat(form.amount),
        currency: form.currency,
      };
      const result = await api.createTransaction(payload, authToken);
      addToast(`TRANSACTION CREATED · ${result.transaction_type.toUpperCase()} $${result.amount.toFixed ? result.amount.toFixed(2) : result.amount}`);
    } catch (err) {
      addToast(`TRANSACTION FAILED · ${err.message}`, true);
    }
  };

  const navigateToChart = (symbol) => {
    setChartSymbol(symbol);
    setPage("charts");
  };

  const NAV = [
    { id:"dashboard",    label:"DASHBOARD",    Icon:Ic.dashboard },
    { id:"transactions", label:"TRANSACTIONS", Icon:Ic.transactions },
    { id:"holdings",     label:"HOLDINGS",     Icon:Ic.holdings },
    { id:"orders",       label:"ORDERS",       Icon:Ic.orders },
    { id:"charts",       label:"CHARTS",       Icon:Ic.charts },
    { id:"import",       label:"IMPORT",       Icon:Ic.import },
  ];

  if (page === "forgot-password") return (
    <>
      <style>{GLOBAL_CSS}</style>
      <ForgotPasswordPage onBack={()=>setPage("login")} backendOk={backendOk}/>
      <ToastContainer toasts={toasts}/>
    </>
  );

  if (page === "reset-password") return (
    <>
      <style>{GLOBAL_CSS}</style>
      <ResetPasswordPage
        resetToken={resetToken}
        onBack={()=>{ window.history.replaceState({}, "", "/"); setPage("login"); }}
        onSuccess={()=>{ window.history.replaceState({}, "", "/"); setPage("login"); addToast("PASSWORD UPDATED · PLEASE SIGN IN"); }}
      />
      <ToastContainer toasts={toasts}/>
    </>
  );

  if (page === "register") return (
    <>
      <style>{GLOBAL_CSS}</style>
      <RegisterPage onLogin={handleLogin} onBack={()=>setPage("login")} backendOk={backendOk}/>
      <ToastContainer toasts={toasts}/>
    </>
  );

  if (page === "login") return (
    <>
      <style>{GLOBAL_CSS}</style>
      <LoginPage onLogin={handleLogin} onRegister={()=>setPage("register")} onForgotPassword={()=>setPage("forgot-password")} backendOk={backendOk}/>
      <ToastContainer toasts={toasts}/>
    </>
  );

  return (
    <>
      <style>{GLOBAL_CSS}</style>
      <div className="app-shell">
        {/* Icon sidebar */}
        <aside className="sidebar">
          <div className="sidebar-logo" onClick={()=>setPage("dashboard")}>
            <div className="logo-glyph">TT</div>
            <div className="logo-name">TICKER-TAP</div>
          </div>
          <nav className="sidebar-nav">
            {NAV.map(n=>(
              <button key={n.id} className={`nav-btn${page===n.id?" active":""}`} onClick={()=>setPage(n.id)}>
                <n.Icon/>
                <span className="nav-label">{n.label}</span>
              </button>
            ))}
          </nav>
          <div className="sidebar-bottom">
            <div className="avatar-btn" style={{width:"100%",borderRadius:4,padding:"0 10px",gap:10,display:"flex",alignItems:"center",height:36}}>
              <span>{authUser ? (authUser.first_name?.[0]||"") + (authUser.last_name?.[0]||"") : "??"}</span>
              <span style={{fontFamily:"var(--font-mono)",fontSize:11,color:"var(--amber)",letterSpacing:"0.5px"}}>{authUser ? `${(authUser.first_name||"").toUpperCase()} ${(authUser.last_name?.[0]||"").toUpperCase()}.` : "USER"}</span>
            </div>
            <button className="nav-btn" onClick={handleLogout}>
              <Ic.logout/>
              <span className="nav-label">SIGN OUT</span>
            </button>
          </div>
        </aside>

        {/* Main */}
        <div className="main-area">
          {/* Topbar */}
          <div className="topbar">
            <div className="topbar-breadcrumb">
              <span>TICKER-TAP</span>
              <span className="topbar-sep">/</span>
              <span className="current">{page.toUpperCase()}</span>
            </div>
            <TickerStrip token={authToken}/>
            <div className="topbar-right">
              <div className="market-status" style={marketStatus.isOpen ? {} : {color:"var(--red)"}}>
                <div className="market-dot" style={marketStatus.isOpen ? {} : {background:"var(--red)"}}/> {marketStatus.isOpen ? "NYSE OPEN" : `CLOSED \u00B7 OPENS IN ${marketStatus.countdown}`}
              </div>
              <Clock/>
            </div>
          </div>

          {/* Pages */}
          {page==="dashboard"    && <DashboardPage    onNewTx={()=>setShowTxModal(true)} token={authToken} accountId={accountId} setPage={setPage}/>}
          {page==="transactions" && <TransactionsPage onNewTx={()=>setShowTxModal(true)} token={authToken} accountId={accountId} goBack={goBack}/>}
          {page==="holdings"     && <HoldingsPage     onNewTx={()=>setShowTxModal(true)} onViewChart={navigateToChart} token={authToken} accountId={accountId} goBack={goBack}/>}
          {page==="orders"       && <OrdersPage       onNewTx={()=>setShowTxModal(true)} token={authToken} accountId={accountId} goBack={goBack}/>}
          {page==="charts"       && <ChartsPage initialSymbol={chartSymbol} token={authToken} goBack={goBack}/>}
          {page==="import"       && <ImportPage addToast={addToast} token={authToken} accountId={accountId} goBack={goBack}/>}
          <Footer/>
        </div>
      </div>

      {/* Transaction modal */}
      {showTxModal && (
        <TxModal
          onClose={()=>setShowTxModal(false)}
          onSubmit={handleTxSubmit}
        />
      )}

      <ToastContainer toasts={toasts}/>
    </>
  );
}
