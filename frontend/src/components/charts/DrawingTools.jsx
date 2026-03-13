/**
 * DrawingTools.js — Drawing tools configuration, coordinate helpers,
 * hit-testing, and SVG renderers for the OHLCVChart component.
 *
 * Extracted from ChartsPage.jsx StockChart to enable drawing tools on any
 * chart that uses OHLCVChart. All functions are pure (no React hooks) except
 * renderDrawing and renderPreview which return JSX.
 *
 * Used by: OHLCVChart.jsx (when enableDrawingTools=true)
 */

import React from "react";

/* ── Tool Configuration ──────────────────────────────────────────────────── */

/** 9 drawing tool types with anchor count, icon key, and UI label. */
export const DRAWING_TOOLS = {
  trendLine:      { anchors: 2, icon: "trendLine",   label: "TREND LINE" },
  horizontalLine: { anchors: 1, icon: "hLine",       label: "H-LINE" },
  ray:            { anchors: 2, icon: "ray",          label: "RAY" },
  rectangle:      { anchors: 2, icon: "rectangle",    label: "RECTANGLE" },
  fibonacci:      { anchors: 2, icon: "fibonacci",    label: "FIBONACCI" },
  pitchfork:      { anchors: 3, icon: "pitchfork",    label: "PITCHFORK" },
  text:           { anchors: 1, icon: "textTool",     label: "TEXT" },
  arrow:          { anchors: 2, icon: "arrowTool",    label: "ARROW" },
  ruler:          { anchors: 2, icon: "ruler",         label: "RULER" },
};

/** Default style for new drawing objects. */
export const DEFAULT_DRAW_STYLE = {
  color: "#f59e0b",
  lineWidth: 1.5,
  lineStyle: "solid",
  fontSize: 12,
  text: "",
};

/* ── ID Generator ────────────────────────────────────────────────────────── */

let _drawingIdCounter = 0;

/** Generate a unique drawing ID using timestamp + monotonic counter. */
export function genDrawingId() {
  return `d_${Date.now()}_${++_drawingIdCounter}`;
}

/* ── Coordinate Translation ──────────────────────────────────────────────── */

/**
 * Binary search: find fractional index of a timestamp within data array.
 * @param {string} timestamp - ISO date string to locate
 * @param {Array}  data      - OHLCV bar array with .date fields
 * @returns {number} Fractional index (e.g. 42.3)
 */
export function timeToIndex(timestamp, data) {
  if (!data.length) return 0;
  const t = new Date(timestamp).getTime();
  let lo = 0, hi = data.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (new Date(data[mid].date).getTime() < t) lo = mid + 1;
    else hi = mid;
  }
  // Fractional interpolation between lo-1 and lo
  if (lo > 0 && lo < data.length) {
    const tLo = new Date(data[lo - 1].date).getTime();
    const tHi = new Date(data[lo].date).getTime();
    if (tHi !== tLo) {
      const frac = (t - tLo) / (tHi - tLo);
      return lo - 1 + Math.max(0, Math.min(1, frac));
    }
  }
  return lo;
}

/**
 * Convert a drawing anchor's time to pixel X within the visible data window.
 * @param {Object} anchor       - {time, price} drawing anchor
 * @param {Array}  visibleData  - currently visible OHLCV bar slice
 * @param {number} visibleStart - global index offset of the visible slice
 * @param {Array}  allData      - full OHLCV bar array
 * @param {Function} xOf        - index-to-pixel X function
 * @returns {number} Pixel X coordinate
 */
export function resolveAnchorX(anchor, visibleData, visibleStart, allData, xOf) {
  const globalIdx = timeToIndex(anchor.time, allData);
  const localIdx = globalIdx - visibleStart;
  return xOf(localIdx);
}

/**
 * Convert a drawing anchor's price to pixel Y.
 * @param {number} price - price value
 * @param {Object} PAD   - chart padding {top, right, bottom, left}
 * @param {number} H     - chart price area height in pixels
 * @param {number} pLo   - price range low bound
 * @param {number} pHi   - price range high bound
 * @returns {number} Pixel Y coordinate
 */
export function resolveAnchorY(price, PAD, H, pLo, pHi) {
  return PAD.top + H - ((price - pLo) / (pHi - pLo)) * H;
}

/**
 * Perpendicular distance from point (px,py) to line segment (x1,y1)-(x2,y2).
 * @returns {number} Pixel distance
 */
export function pointToSegmentDist(px, py, x1, y1, x2, y2) {
  const dx = x2 - x1, dy = y2 - y1;
  const lenSq = dx * dx + dy * dy;
  if (lenSq === 0) return Math.hypot(px - x1, py - y1);
  let t = ((px - x1) * dx + (py - y1) * dy) / lenSq;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
}

/**
 * Convert pixel coordinates to a drawing anchor {time, price}.
 * @param {number} mx          - mouse X pixel
 * @param {number} my          - mouse Y pixel
 * @param {Array}  visibleData - currently visible OHLCV bar slice
 * @param {number} n           - visibleData.length
 * @param {Object} PAD         - chart padding
 * @param {number} candleGap   - pixels per candle slot
 * @param {number} H           - chart price area height
 * @param {number} pLo         - price range low
 * @param {number} pHi         - price range high
 * @returns {Object|null} {time, price} or null if out of range
 */
export function pixelToAnchor(mx, my, visibleData, n, PAD, candleGap, H, pLo, pHi) {
  const idx = Math.round((mx - PAD.left - candleGap / 2) / candleGap);
  const clamped = Math.max(0, Math.min(n - 1, idx));
  const d = visibleData[clamped];
  if (!d) return null;
  const price = pLo + ((PAD.top + H - my) / H) * (pHi - pLo);
  return { time: d.date, price };
}

/* ── Hit Testing ─────────────────────────────────────────────────────────── */

/**
 * Find the topmost drawing near the given pixel coordinates.
 * @param {Array}    drawings     - committed drawing objects
 * @param {number}   mx           - mouse X pixel
 * @param {number}   my           - mouse Y pixel
 * @param {Array}    visibleData  - visible bar slice
 * @param {number}   visibleStart - global index offset
 * @param {Array}    allData      - full bar array
 * @param {Function} xOf          - index-to-X function
 * @param {Object}   PAD          - chart padding
 * @param {number}   H            - price area height
 * @param {number}   W            - chart width
 * @param {number}   pLo          - price low bound
 * @param {number}   pHi          - price high bound
 * @returns {string|null} Drawing ID or null
 */
export function hitTestDrawing(drawings, mx, my, visibleData, visibleStart, allData, xOf, PAD, H, W, pLo, pHi) {
  const threshold = 10;
  for (let di = drawings.length - 1; di >= 0; di--) {
    const dr = drawings[di];
    const { type, anchors } = dr;
    if (!anchors || !anchors.length) continue;

    const ax = (a) => resolveAnchorX(a, visibleData, visibleStart, allData, xOf);
    const ay = (a) => resolveAnchorY(a.price, PAD, H, pLo, pHi);

    switch (type) {
      case "trendLine":
      case "arrow":
      case "ruler":
        if (anchors.length >= 2) {
          const dist = pointToSegmentDist(mx, my, ax(anchors[0]), ay(anchors[0]), ax(anchors[1]), ay(anchors[1]));
          if (dist < threshold) return dr.id;
        }
        break;
      case "horizontalLine":
        if (anchors.length >= 1) {
          const y = ay(anchors[0]);
          if (Math.abs(my - y) < threshold) return dr.id;
        }
        break;
      case "ray":
        if (anchors.length >= 2) {
          const x1 = ax(anchors[0]), y1 = ay(anchors[0]);
          const x2 = ax(anchors[1]), y2 = ay(anchors[1]);
          const dx = x2 - x1, dy = y2 - y1;
          const len = Math.hypot(dx, dy) || 1;
          const scale = Math.max(W, H) * 2 / len;
          const dist = pointToSegmentDist(mx, my, x1, y1, x1 + dx * scale, y1 + dy * scale);
          if (dist < threshold) return dr.id;
        }
        break;
      case "rectangle":
      case "fibonacci":
        if (anchors.length >= 2) {
          const x1 = ax(anchors[0]), y1 = ay(anchors[0]);
          const x2 = ax(anchors[1]), y2 = ay(anchors[1]);
          const rx = Math.min(x1, x2), ry = Math.min(y1, y2);
          const rw = Math.abs(x2 - x1), rh = Math.abs(y2 - y1);
          if (mx >= rx - threshold && mx <= rx + rw + threshold &&
              my >= ry - threshold && my <= ry + rh + threshold) return dr.id;
        }
        break;
      case "text":
        if (anchors.length >= 1) {
          const x = ax(anchors[0]), y = ay(anchors[0]);
          const fs = dr.style.fontSize || 12;
          const tw = (dr.style.text || "Text").length * fs * 0.65;
          if (mx >= x - 4 && mx <= x + tw + 4 && my >= y - fs - 4 && my <= y + 4) return dr.id;
        }
        break;
      case "pitchfork":
        if (anchors.length >= 3) {
          for (let ai = 0; ai < 2; ai++) {
            const dist = pointToSegmentDist(mx, my, ax(anchors[ai]), ay(anchors[ai]), ax(anchors[ai + 1]), ay(anchors[ai + 1]));
            if (dist < threshold) return dr.id;
          }
        }
        break;
      default: break;
    }
  }
  return null;
}

/* ── SVG Renderers ───────────────────────────────────────────────────────── */

/**
 * Render a committed drawing as SVG elements.
 * @param {Object}   drawing      - drawing object {id, type, anchors, style, visible}
 * @param {Array}    visibleData  - visible bar slice
 * @param {number}   visibleStart - global index offset
 * @param {Array}    allData      - full bar array
 * @param {Function} xOf          - index-to-X function
 * @param {Function} yOf          - price-to-Y function
 * @param {Object}   PAD          - chart padding
 * @param {number}   H            - price area height
 * @param {number}   W            - chart width
 * @param {number}   pLo          - price low bound
 * @param {number}   pHi          - price high bound
 * @param {Object}   dims         - {w, h} container dimensions
 * @param {boolean}  isSelected   - whether this drawing is currently selected
 * @param {string}   currSym      - currency symbol (e.g. "$")
 * @returns {JSX.Element|null}
 */
export function renderDrawing(drawing, visibleData, visibleStart, allData, xOf, yOf, PAD, H, W, pLo, pHi, dims, isSelected, currSym) {
  const { type, anchors, style } = drawing;
  const col = style.color || "#f59e0b";
  const lw = style.lineWidth || 1.5;
  const dash = style.lineStyle === "dashed" ? "6,4" : style.lineStyle === "dotted" ? "2,3" : "none";

  const ax = (i) => resolveAnchorX(anchors[i], visibleData, visibleStart, allData, xOf);
  const ay = (i) => resolveAnchorY(anchors[i].price, PAD, H, pLo, pHi);

  switch (type) {
    case "trendLine": {
      if (anchors.length < 2) return null;
      return (
        <g key={drawing.id}>
          {isSelected && <line x1={ax(0)} y1={ay(0)} x2={ax(1)} y2={ay(1)} stroke="#fff" strokeWidth={lw + 2} opacity="0.3" />}
          <line x1={ax(0)} y1={ay(0)} x2={ax(1)} y2={ay(1)} stroke={col} strokeWidth={lw} strokeDasharray={dash} />
          <circle cx={ax(0)} cy={ay(0)} r={3} fill={col} opacity="0.7" />
          <circle cx={ax(1)} cy={ay(1)} r={3} fill={col} opacity="0.7" />
        </g>
      );
    }
    case "horizontalLine": {
      if (anchors.length < 1) return null;
      const y = ay(0);
      const price = anchors[0].price;
      return (
        <g key={drawing.id}>
          {isSelected && <line x1={PAD.left} y1={y} x2={dims.w - PAD.right} y2={y} stroke="#fff" strokeWidth={lw + 2} opacity="0.3" />}
          <line x1={PAD.left} y1={y} x2={dims.w - PAD.right} y2={y} stroke={col} strokeWidth={lw} strokeDasharray={dash} />
          <rect x={PAD.left} y={y - 8} width={60} height={16} rx={1} fill={col} opacity="0.85" />
          <text x={PAD.left + 4} y={y + 4} fontFamily="IBM Plex Mono" fontSize="9" fontWeight="600" fill="#060f08">
            {currSym}{price.toFixed(2)}
          </text>
        </g>
      );
    }
    case "ray": {
      if (anchors.length < 2) return null;
      const x1 = ax(0), y1 = ay(0), x2 = ax(1), y2 = ay(1);
      const dx = x2 - x1, dy = y2 - y1;
      const len = Math.hypot(dx, dy) || 1;
      const scale = Math.max(W, H) * 2 / len;
      const ex = x1 + dx * scale, ey = y1 + dy * scale;
      return (
        <g key={drawing.id}>
          {isSelected && <line x1={x1} y1={y1} x2={ex} y2={ey} stroke="#fff" strokeWidth={lw + 2} opacity="0.3" />}
          <line x1={x1} y1={y1} x2={ex} y2={ey} stroke={col} strokeWidth={lw} strokeDasharray={dash} />
          <circle cx={x1} cy={y1} r={3} fill={col} opacity="0.7" />
        </g>
      );
    }
    case "rectangle": {
      if (anchors.length < 2) return null;
      const x1 = ax(0), y1 = ay(0), x2 = ax(1), y2 = ay(1);
      const rx = Math.min(x1, x2), ry = Math.min(y1, y2);
      const rw = Math.abs(x2 - x1), rh = Math.abs(y2 - y1);
      return (
        <g key={drawing.id}>
          <rect x={rx} y={ry} width={rw} height={rh} fill={col} fillOpacity="0.08" stroke={col} strokeWidth={lw} strokeDasharray={dash} />
          {isSelected && <rect x={rx} y={ry} width={rw} height={rh} fill="none" stroke="#fff" strokeWidth={lw + 1} opacity="0.3" />}
        </g>
      );
    }
    case "arrow": {
      if (anchors.length < 2) return null;
      const x1 = ax(0), y1 = ay(0), x2 = ax(1), y2 = ay(1);
      const angle = Math.atan2(y2 - y1, x2 - x1);
      const hs = 10;
      const p1x = x2 - hs * Math.cos(angle - 0.4), p1y = y2 - hs * Math.sin(angle - 0.4);
      const p2x = x2 - hs * Math.cos(angle + 0.4), p2y = y2 - hs * Math.sin(angle + 0.4);
      return (
        <g key={drawing.id}>
          {isSelected && <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#fff" strokeWidth={lw + 2} opacity="0.3" />}
          <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={col} strokeWidth={lw} strokeDasharray={dash} />
          <polygon points={`${x2},${y2} ${p1x},${p1y} ${p2x},${p2y}`} fill={col} />
        </g>
      );
    }
    case "ruler": {
      if (anchors.length < 2) return null;
      const x1 = ax(0), y1 = ay(0), x2 = ax(1), y2 = ay(1);
      const price1 = anchors[0].price, price2 = anchors[1].price;
      const diff = price2 - price1;
      const pct = price1 !== 0 ? (diff / price1) * 100 : 0;
      const midX = (x1 + x2) / 2, midY = (y1 + y2) / 2;
      const labelText = `${diff >= 0 ? "+" : ""}${diff.toFixed(2)} (${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%)`;
      const labelColor = diff >= 0 ? "#00d97e" : "#f04438";
      return (
        <g key={drawing.id}>
          {isSelected && <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#fff" strokeWidth={lw + 2} opacity="0.3" />}
          <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={col} strokeWidth={lw} strokeDasharray="6,3" />
          <circle cx={x1} cy={y1} r={3} fill={col} opacity="0.7" />
          <circle cx={x2} cy={y2} r={3} fill={col} opacity="0.7" />
          <line x1={x1} y1={y1} x2={x1} y2={y2} stroke={col} strokeWidth={0.5} strokeDasharray="3,3" opacity="0.4" />
          <line x1={x1} y1={y2} x2={x2} y2={y2} stroke={col} strokeWidth={0.5} strokeDasharray="3,3" opacity="0.4" />
          <rect x={midX - 60} y={midY - 10} width={120} height={16} rx={2} fill="var(--bg2, #1a1a2e)" fillOpacity="0.9" stroke={labelColor} strokeWidth="0.5" />
          <text x={midX} y={midY + 3} textAnchor="middle" fontFamily="IBM Plex Mono" fontSize="9" fontWeight="600" fill={labelColor}>
            {labelText}
          </text>
        </g>
      );
    }
    case "fibonacci": {
      if (anchors.length < 2) return null;
      const p1 = anchors[0].price, p2 = anchors[1].price;
      const high = Math.max(p1, p2), low = Math.min(p1, p2);
      const levels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];
      const x1 = ax(0), x2 = ax(1);
      const left = Math.min(x1, x2), right = Math.max(x1, x2);
      return (
        <g key={drawing.id}>
          {levels.map((lv, i) => {
            const price = high - (high - low) * lv;
            const y = resolveAnchorY(price, PAD, H, pLo, pHi);
            const pctLabel = `${(lv * 100).toFixed(1)}%`;
            return (
              <g key={i}>
                <line x1={left} y1={y} x2={right} y2={y}
                  stroke={col} strokeWidth={lv === 0 || lv === 1 ? lw : lw * 0.7}
                  strokeDasharray={lv === 0.5 ? "4,3" : "none"} opacity={0.7} />
                <text x={right + 4} y={y + 3} fontFamily="IBM Plex Mono" fontSize="8" fill={col} opacity="0.8">
                  {pctLabel} {currSym}{price.toFixed(2)}
                </text>
              </g>
            );
          })}
          {/* Shaded 38.2-61.8 golden zone */}
          {(() => {
            const y382 = resolveAnchorY(high - (high - low) * 0.382, PAD, H, pLo, pHi);
            const y618 = resolveAnchorY(high - (high - low) * 0.618, PAD, H, pLo, pHi);
            return <rect x={left} y={Math.min(y382, y618)} width={right - left} height={Math.abs(y618 - y382)} fill={col} fillOpacity="0.06" />;
          })()}
          {isSelected && <rect x={left} y={resolveAnchorY(high, PAD, H, pLo, pHi)} width={right - left}
            height={Math.abs(resolveAnchorY(low, PAD, H, pLo, pHi) - resolveAnchorY(high, PAD, H, pLo, pHi))}
            fill="none" stroke="#fff" strokeWidth="1" opacity="0.3" />}
        </g>
      );
    }
    case "pitchfork": {
      if (anchors.length < 3) return null;
      const x0 = ax(0), y0 = ay(0);
      const x1 = ax(1), y1 = ay(1);
      const x2 = ax(2), y2 = ay(2);
      const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
      const extendLine = (sx, sy, ex, ey) => {
        const dx = ex - sx, dy = ey - sy;
        const len = Math.hypot(dx, dy) || 1;
        const s = Math.max(W, H) * 2 / len;
        return { ex: sx + dx * s, ey: sy + dy * s };
      };
      const med = extendLine(x0, y0, mx, my);
      const prong1 = extendLine(x1, y1, x1 + (mx - x0), y1 + (my - y0));
      const prong2 = extendLine(x2, y2, x2 + (mx - x0), y2 + (my - y0));
      return (
        <g key={drawing.id}>
          {isSelected && <line x1={x0} y1={y0} x2={med.ex} y2={med.ey} stroke="#fff" strokeWidth={lw + 2} opacity="0.3" />}
          <line x1={x0} y1={y0} x2={med.ex} y2={med.ey} stroke={col} strokeWidth={lw} />
          <line x1={x1} y1={y1} x2={prong1.ex} y2={prong1.ey} stroke={col} strokeWidth={lw * 0.7} strokeDasharray="4,3" />
          <line x1={x2} y1={y2} x2={prong2.ex} y2={prong2.ey} stroke={col} strokeWidth={lw * 0.7} strokeDasharray="4,3" />
          <circle cx={x0} cy={y0} r={3} fill={col} />
          <circle cx={x1} cy={y1} r={3} fill={col} opacity="0.7" />
          <circle cx={x2} cy={y2} r={3} fill={col} opacity="0.7" />
        </g>
      );
    }
    case "text": {
      if (anchors.length < 1) return null;
      const x = ax(0), y = ay(0);
      const txt = style.text || "Text";
      const fs = style.fontSize || 12;
      return (
        <g key={drawing.id}>
          {isSelected && <rect x={x - 2} y={y - fs - 2} width={txt.length * fs * 0.65 + 4} height={fs + 6} fill="#fff" fillOpacity="0.1" stroke="#fff" strokeWidth="1" rx="1" />}
          <text x={x} y={y} fontFamily="IBM Plex Mono" fontSize={fs} fill={col} fontWeight="500">{txt}</text>
        </g>
      );
    }
    default:
      return null;
  }
}

/**
 * Render a rubber-band preview while placing drawing anchors.
 * @param {string}   toolType     - active tool key
 * @param {Array}    anchors      - already-placed anchors
 * @param {Object}   previewPoint - current mouse position as {time, price}
 * @param {Array}    visibleData  - visible bar slice
 * @param {number}   visibleStart - global index offset
 * @param {Array}    allData      - full bar array
 * @param {Function} xOf          - index-to-X function
 * @param {Function} yOf          - price-to-Y function
 * @param {Object}   PAD          - chart padding
 * @param {number}   H            - price area height
 * @param {number}   W            - chart width
 * @param {number}   pLo          - price low bound
 * @param {number}   pHi          - price high bound
 * @param {Object}   dims         - {w, h} container dimensions
 * @param {Object}   style        - current drawing style
 * @returns {JSX.Element|null}
 */
export function renderPreview(toolType, anchors, previewPoint, visibleData, visibleStart, allData, xOf, yOf, PAD, H, W, pLo, pHi, dims, style) {
  if (!previewPoint) return null;
  const col = style.color || "#f59e0b";
  const lw = style.lineWidth || 1.5;
  const ax = (a) => resolveAnchorX(a, visibleData, visibleStart, allData, xOf);
  const ay = (a) => resolveAnchorY(a.price, PAD, H, pLo, pHi);
  const px = resolveAnchorX(previewPoint, visibleData, visibleStart, allData, xOf);
  const py = resolveAnchorY(previewPoint.price, PAD, H, pLo, pHi);

  switch (toolType) {
    case "trendLine":
    case "arrow":
    case "ruler":
      if (anchors.length === 1) {
        return <line x1={ax(anchors[0])} y1={ay(anchors[0])} x2={px} y2={py} stroke={col} strokeWidth={lw} strokeDasharray="4,4" opacity="0.7" />;
      }
      return null;
    case "horizontalLine":
      return <line x1={PAD.left} y1={py} x2={dims.w - PAD.right} y2={py} stroke={col} strokeWidth={lw} strokeDasharray="4,4" opacity="0.7" />;
    case "ray":
      if (anchors.length === 1) {
        const x1 = ax(anchors[0]), y1 = ay(anchors[0]);
        const dx = px - x1, dy = py - y1;
        const len = Math.hypot(dx, dy) || 1;
        const scale = Math.max(W, H) * 2 / len;
        return <line x1={x1} y1={y1} x2={x1 + dx * scale} y2={y1 + dy * scale} stroke={col} strokeWidth={lw} strokeDasharray="4,4" opacity="0.7" />;
      }
      return null;
    case "rectangle":
      if (anchors.length === 1) {
        const x1 = ax(anchors[0]), y1 = ay(anchors[0]);
        return <rect x={Math.min(x1, px)} y={Math.min(y1, py)} width={Math.abs(px - x1)} height={Math.abs(py - y1)} fill={col} fillOpacity="0.06" stroke={col} strokeWidth={lw} strokeDasharray="4,4" opacity="0.7" />;
      }
      return null;
    case "fibonacci":
      if (anchors.length === 1) {
        const p1 = anchors[0].price, p2 = previewPoint.price;
        const high = Math.max(p1, p2), low = Math.min(p1, p2);
        const levels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];
        const x1 = ax(anchors[0]);
        const left = Math.min(x1, px), right = Math.max(x1, px);
        return (
          <g opacity="0.5">
            {levels.map((lv, i) => {
              const price = high - (high - low) * lv;
              const y = resolveAnchorY(price, PAD, H, pLo, pHi);
              return <line key={i} x1={left} y1={y} x2={right} y2={y} stroke={col} strokeWidth={lw * 0.7} strokeDasharray="4,3" />;
            })}
          </g>
        );
      }
      return null;
    case "pitchfork":
      if (anchors.length >= 1) {
        const pts = [...anchors.map(a => ({ x: ax(a), y: ay(a) })), { x: px, y: py }];
        return (
          <g opacity="0.5">
            {pts.map((p, i) => i > 0 && <line key={i} x1={pts[i-1].x} y1={pts[i-1].y} x2={p.x} y2={p.y} stroke={col} strokeWidth={lw} strokeDasharray="4,4" />)}
            {pts.map((p, i) => <circle key={`c${i}`} cx={p.x} cy={p.y} r={3} fill={col} opacity="0.7" />)}
          </g>
        );
      }
      return null;
    case "text":
      return <text x={px} y={py} fontFamily="IBM Plex Mono" fontSize={style.fontSize || 12} fill={col} opacity="0.5">{style.text || "Text"}</text>;
    default:
      return null;
  }
}
