/**
 * chartStyles.js — CSS classes for the interactive OHLCVChart features:
 * controls bar, stats bar, drawing toolbar, and overlay toggles.
 *
 * All classes are prefixed with `ohlcv-` to avoid collisions with
 * ChartsPage.jsx's own CHART_CSS. Injected conditionally via a <style>
 * tag when any interactive feature is enabled on OHLCVChart.
 *
 * Used by: OHLCVChart.jsx
 */

export const OHLCV_INTERACTIVE_CSS = `
/* ── Controls row ── */
.ohlcv-controls {
  background: #0e1117; border-bottom: 1px solid #1e2535;
  padding: 6px 16px; display: flex; align-items: center; gap: 12px;
  flex-shrink: 0; flex-wrap: wrap;
}
.ohlcv-ctrl-group { display: flex; gap: 1px; background: #1e2535; }
.ohlcv-ctrl-btn {
  padding: 4px 10px; background: #0e1117; border: none; cursor: pointer;
  font-family: 'IBM Plex Mono', monospace; font-size: 10px; font-weight: 500;
  color: #4a5568; letter-spacing: 0.8px; text-transform: uppercase;
  transition: all 0.1s;
}
.ohlcv-ctrl-btn:hover { background: #141820; color: #c8d3e0; }
.ohlcv-ctrl-btn.active { background: #141820; color: #0f7d40; }

.ohlcv-overlay-toggles { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.ohlcv-overlay-toggle {
  display: flex; align-items: center; gap: 4px; cursor: pointer;
  font-family: 'IBM Plex Mono', monospace; font-size: 10px;
  padding: 3px 8px; border: 1px solid #1e2535; background: #0e1117;
  border-radius: 2px; transition: all 0.1s; user-select: none;
  color: #4a5568;
}
.ohlcv-overlay-toggle:hover { border-color: #263045; color: #718096; }
.ohlcv-overlay-toggle.on { border-color: transparent; }
.ohlcv-overlay-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }

.ohlcv-ctrl-sep { width: 1px; height: 18px; background: #1e2535; }
.ohlcv-ctrl-label {
  font-family: 'IBM Plex Mono', monospace; font-size: 10px;
  color: #4a5568; letter-spacing: 0.5px;
}

/* ── Stats bar ── */
.ohlcv-stats-bar {
  background: #0e1117; border-bottom: 1px solid #1e2535;
  padding: 10px 16px; display: flex; gap: 0; align-items: stretch;
  flex-shrink: 0; overflow-x: auto;
}
.ohlcv-stat-sep { width: 1px; background: #1e2535; margin: 0 14px; flex-shrink: 0; }
.ohlcv-stock-stat { display: flex; flex-direction: column; gap: 2px; min-width: 80px; }
.ohlcv-ss-label {
  font-family: 'IBM Plex Mono', monospace; font-size: 9px;
  color: #4a5568; letter-spacing: 1px; text-transform: uppercase;
}
.ohlcv-ss-value {
  font-family: 'IBM Plex Mono', monospace; font-size: 16px; font-weight: 600;
  color: #e8f0fa; line-height: 1; letter-spacing: -0.5px;
}
.ohlcv-ss-value.pos { color: #00d97e; }
.ohlcv-ss-value.neg { color: #f04438; }
.ohlcv-ss-value.amber { color: #0f7d40; }
.ohlcv-ss-sub {
  font-family: 'IBM Plex Mono', monospace; font-size: 9px; color: #4a5568;
}
.ohlcv-ss-badge {
  display: inline-flex; align-items: center; gap: 3px;
  font-family: 'IBM Plex Mono', monospace; font-size: 9px; font-weight: 500;
  padding: 2px 6px; border-radius: 1px; align-self: flex-start; margin-top: 1px;
}
.ohlcv-ss-badge.pos { color: #00d97e; background: rgba(0,217,126,0.08); border: 1px solid rgba(0,217,126,0.15); }
.ohlcv-ss-badge.neg { color: #f04438; background: rgba(240,68,56,0.08); border: 1px solid rgba(240,68,56,0.15); }

/* ── Drawing Toolbar ── */
.ohlcv-draw-toolbar {
  position: absolute; top: 0; left: 0; bottom: 0; width: 36px;
  background: rgba(14,17,23,0.92); border-right: 1px solid #1e2535;
  display: flex; flex-direction: column; align-items: center;
  padding: 8px 0; gap: 2px; z-index: 10;
  backdrop-filter: blur(6px);
}
.ohlcv-draw-tool-btn {
  width: 28px; height: 28px; display: flex; align-items: center; justify-content: center;
  background: none; border: 1px solid transparent; border-radius: 2px;
  cursor: pointer; color: #4a5568; transition: all 0.1s; flex-shrink: 0;
  padding: 0;
}
.ohlcv-draw-tool-btn:hover { color: #c8d3e0; background: rgba(255,255,255,0.04); border-color: #263045; }
.ohlcv-draw-tool-btn.active { color: #f59e0b; background: rgba(245,158,11,0.08); border-color: rgba(245,158,11,0.3); }
.ohlcv-draw-tool-btn.mini { width: 28px; height: 18px; }
.ohlcv-draw-tool-btn.danger { color: #4a5568; }
.ohlcv-draw-tool-btn.danger:hover { color: #f04438; background: rgba(240,68,56,0.08); border-color: rgba(240,68,56,0.3); }
.ohlcv-draw-toolbar-sep {
  width: 18px; height: 1px; background: #1e2535; margin: 4px 0; flex-shrink: 0;
}
.ohlcv-draw-color-wrap {
  width: 28px; height: 28px; position: relative; cursor: pointer;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.ohlcv-draw-color-swatch {
  width: 14px; height: 14px; border-radius: 2px; border: 1px solid #263045;
  pointer-events: none;
}
.ohlcv-draw-color-input {
  position: absolute; inset: 0; opacity: 0; cursor: pointer;
  width: 100%; height: 100%;
}
.ohlcv-draw-text-input {
  width: 28px; background: #141820; border: 1px solid #263045;
  color: #e8f0fa; font-family: 'IBM Plex Mono', monospace; font-size: 8px;
  padding: 3px 2px; text-align: center; outline: none; border-radius: 2px;
  flex-shrink: 0;
}
.ohlcv-draw-text-input:focus { border-color: #f59e0b; }
.ohlcv-draw-count {
  font-family: 'IBM Plex Mono', monospace; font-size: 8px; color: #4a5568;
  text-align: center; line-height: 1; margin-top: 2px; flex-shrink: 0;
}
.ohlcv-draw-active-label {
  writing-mode: vertical-rl; text-orientation: mixed;
  font-family: 'IBM Plex Mono', monospace; font-size: 8px; font-weight: 600;
  color: #f59e0b; letter-spacing: 1px; margin-top: auto; padding-bottom: 8px;
  white-space: nowrap; flex-shrink: 0;
}
.ohlcv-draw-anchor-count {
  font-size: 8px; color: #718096; margin-top: 4px;
}

/* ── Reset zoom button ── */
.ohlcv-reset-zoom {
  padding: 3px 8px; background: none; border: 1px solid #1e2535;
  cursor: pointer; font-family: 'IBM Plex Mono', monospace;
  font-size: 9px; color: #4a5568; letter-spacing: 0.5px;
  border-radius: 2px; transition: all 0.1s;
}
.ohlcv-reset-zoom:hover { border-color: #f59e0b; color: #f59e0b; }
`;
