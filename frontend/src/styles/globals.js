/**
 * Global Styles, Design Tokens, and Mock Data
 *
 * This file exports:
 * - GLOBAL_CSS: Bloomberg-inspired theme with CSS variables, layout system, components
 * - HOLDINGS: Mock portfolio holdings data
 * - TRANSACTIONS: Mock transaction history
 * - ORDERS: Mock order book data
 * - TICKER_DATA: Mock market ticker data for demonstration
 */

export const GLOBAL_CSS = `
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
\`;

export const HOLDINGS = [
  { symbol:"AAPL", name:"Apple Inc.",         qty:12.5, avg:142.30, price:189.45, chg:+2.34, chgPct:+1.25 },
  { symbol:"MSFT", name:"Microsoft Corp.",    qty:8,    avg:310.00, price:378.90, chg:+4.22, chgPct:+1.12 },
  { symbol:"NVDA", name:"NVIDIA Corp.",       qty:5,    avg:480.00, price:721.28, chg:+34.6, chgPct:+4.87 },
  { symbol:"TSLA", name:"Tesla Inc.",         qty:15,   avg:251.40, price:213.65, chg:-4.12, chgPct:-1.90 },
  { symbol:"AMZN", name:"Amazon.com Inc.",    qty:6,    avg:180.00, price:196.40, chg:+1.43, chgPct:+0.73 },
  { symbol:"GOOGL", name:"Alphabet Inc.",     qty:4,    avg:155.00, price:172.30, chg:+0.87, chgPct:+0.51 },
  { symbol:"META", name:"Meta Platforms",     qty:10,   avg:320.00, price:492.80, chg:+8.32, chgPct:+1.72 },
];

export const TRANSACTIONS = [
  { id:"TXN-0012", type:"buy",        symbol:"NVDA",  amount:2401.40, status:"completed", date:"2026-02-23", currency:"USD", acct:"ACC-4821" },
  { id:"TXN-0011", type:"deposit",    symbol:null,    amount:10000.0, status:"completed", date:"2026-02-20", currency:"USD", acct:"ACC-4821" },
  { id:"TXN-0010", type:"sell",       symbol:"TSLA",  amount:1282.50, status:"completed", date:"2026-02-18", currency:"USD", acct:"ACC-4821" },
  { id:"TXN-0009", type:"buy",        symbol:"AAPL",  amount:1893.75, status:"pending",   date:"2026-02-23", currency:"USD", acct:"ACC-4821" },
  { id:"TXN-0008", type:"withdrawal", symbol:null,    amount:2500.00, status:"completed", date:"2026-02-15", currency:"USD", acct:"ACC-4821" },
  { id:"TXN-0007", type:"buy",        symbol:"MSFT",  amount:3031.20, status:"completed", date:"2026-02-12", currency:"USD", acct:"ACC-4821" },
  { id:"TXN-0006", type:"sell",       symbol:"GOOGL", amount:688.00,  status:"completed", date:"2026-02-10", currency:"USD", acct:"ACC-4821" },
  { id:"TXN-0005", type:"buy",        symbol:"META",  amount:4928.00, status:"completed", date:"2026-02-06", currency:"USD", acct:"ACC-4821" },
];

export const ORDERS = [
  { id:"ORD-1024", symbol:"GOOGL", side:"buy",  type:"limit",  qty:3,  price:165.00, status:"open",      filled:0,   placed:"2026-02-23 09:31" },
  { id:"ORD-1023", symbol:"META",  side:"buy",  type:"market", qty:5,  price:null,   status:"filled",    filled:5,   placed:"2026-02-22 14:05" },
  { id:"ORD-1022", symbol:"TSLA",  side:"sell", type:"stop",   qty:8,  price:200.00, status:"open",      filled:0,   placed:"2026-02-21 11:22" },
  { id:"ORD-1021", symbol:"AAPL",  side:"buy",  type:"limit",  qty:10, price:185.00, status:"cancelled", filled:0,   placed:"2026-02-19 09:45" },
  { id:"ORD-1020", symbol:"NVDA",  side:"buy",  type:"limit",  qty:2,  price:700.00, status:"open",      filled:0,   placed:"2026-02-18 10:00" },
  { id:"ORD-1019", symbol:"MSFT",  side:"sell", type:"limit",  qty:3,  price:395.00, status:"filled",    filled:3,   placed:"2026-02-17 15:50" },
];

export const TICKER_DATA = [
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
