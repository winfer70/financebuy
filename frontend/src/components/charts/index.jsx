/**
 * Data Visualization Components
 *
 * Exports:
 * - Sparkline: Compact mini chart for trend indication
 * - PortfolioChart: Interactive area chart with hover tooltips
 * - AllocationDonut: Donut chart showing portfolio allocation percentages
 * - OHLCVChart: Reusable candlestick / line chart with volume, SMA, signals
 */

import { useState, useMemo, useRef, useCallback, useEffect } from "react";

export { default as OHLCVChart } from "./OHLCVChart";

/**
 * Sparkline: Compact inline chart for quick trend visualization
 * Generates random data points and renders as SVG mini-chart
 */
export function Sparkline({ positive, w=80, h=24 }) {
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

/**
 * PortfolioChart: Interactive area chart showing portfolio value over time.
 * Supports hover interaction for detailed values.
 *
 * @param {number}       height         - SVG height in px (default 160)
 * @param {Array|null}   data           - Array of { date, value } objects or plain numbers.
 *                                         Returns empty-state when null / empty.
 * @param {string}       period         - Display period label (e.g. "3M", "1Y")
 * @param {string}       currencySymbol - Currency symbol for formatting (default "$")
 */
export function PortfolioChart({ height=160, data=null, period="3M", currencySymbol="$" }) {
  /* Normalise input: accept [number], [{close}], or [{date, value}] */
  const raw = useMemo(() => {
    if (data && data.length > 0) return data.map(d => typeof d === "number" ? d : d.value ?? d.close ?? d);
    return [];
  }, [data]);

  /* Extract date strings from data (if present) for x-axis labels */
  const dates = useMemo(() => {
    if (data && data.length > 0 && data[0]?.date) return data.map(d => d.date);
    return null;
  }, [data]);

  const [hover, setHover] = useState(null);
  const svgRef = useRef(null);
  const W=600, H=height;
  /* Data occupies 80% of chart width; the remaining 20% is empty future space */
  const DATA_W = W * 0.8;
  const mn=Math.min(...raw), mx=Math.max(...raw), rng=mx-mn||1;
  const pts = raw.map((v,i)=>({
    x:(i/(raw.length-1))*DATA_W,
    y:H-((v-mn)/rng)*(H-16)-8
  }));
  const line = pts.map((p,i)=>`${i===0?"M":"L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  /* Fill area closes down to DATA_W (not full W) so gradient doesn't bleed into future zone */
  const fill = line+` L${DATA_W},${H} L0,${H} Z`;

  /* Y-axis labels — adapt format based on magnitude */
  const fmtY = (v) => {
    if (Math.abs(v) >= 1e6) return currencySymbol + (v / 1e6).toFixed(1) + "M";
    if (Math.abs(v) >= 1e3) return currencySymbol + (v / 1e3).toFixed(1) + "K";
    return currencySymbol + v.toFixed(0);
  };
  const yVals = [mx, (mx+mn)/2, mn].map(fmtY);

  /* X-axis labels — derive from dates or fall-back to period hint */
  const xLabels = useMemo(() => {
    if (dates && dates.length >= 3) {
      const fmt = (d) => {
        try {
          const dt = new Date(d);
          return dt.toLocaleDateString("en-US", { month: "short", year: "2-digit" }).toUpperCase().replace(",", " '");
        } catch { return ""; }
      };
      const first = fmt(dates[0]);
      const mid   = fmt(dates[Math.floor(dates.length / 2)]);
      const last  = fmt(dates[dates.length - 1]);
      return [first, mid, last];
    }
    return ["DEC '25","JAN '26","FEB '26"];
  }, [dates]);

  /**
   * handleMouseMove — resolves cursor position to nearest data point.
   * If cursor is in the future zone (past DATA_W), store raw x for crosshair
   * but mark inFuture=true so tooltip/circle are suppressed.
   */
  const handleMouseMove = useCallback((e) => {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const relX = (e.clientX - rect.left) / rect.width * W;
    if (relX > DATA_W) {
      /* Future zone — show crosshair only, no data tooltip */
      setHover({ idx: -1, x: relX, y: H / 2, value: null, inFuture: true });
    } else {
      const idx = Math.min(Math.max(Math.round((relX / DATA_W) * (raw.length - 1)), 0), raw.length - 1);
      const dateStr = dates && dates[idx] ? dates[idx] : null;
      setHover({ idx, x: pts[idx].x, y: pts[idx].y, value: raw[idx], inFuture: false, date: dateStr });
    }
  }, [raw, pts, DATA_W, dates]);

  /* Determine tooltip anchor: leftmost points anchor right, others center */
  const tooltipLeft = hover && !hover.inFuture ? `${(hover.x / W) * 100}%` : "0";
  const tooltipTransform = hover && hover.idx === 0 ? "translateX(0)" : "translateX(-50%)";

  /* Format tooltip value based on magnitude */
  const fmtTooltip = (v) => {
    if (v >= 1e6) return currencySymbol + (v / 1e6).toFixed(2) + "M";
    if (v >= 1e3) return currencySymbol + (v / 1e3).toFixed(2) + "K";
    return currencySymbol + v.toFixed(2);
  };

  /* Empty-state: when no data is available, show a placeholder instead of the chart canvas */
  if (raw.length === 0) {
    return (
      <div className="chart-area" style={{position:"relative", display:"flex", alignItems:"center", justifyContent:"center", height:H}}>
        <span style={{fontFamily:"var(--font-mono)",fontSize:11,color:"var(--muted)",letterSpacing:"0.5px"}}>
          NO PORTFOLIO DATA AVAILABLE
        </span>
      </div>
    );
  }

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
          {/* Grid lines span the full width including future zone */}
          {[H*0.1,H*0.5,H*0.9].map((y,i)=>(
            <line key={i} x1="0" y1={y} x2={W} y2={y} className="chart-gridline"/>
          ))}
          {/* Subtle separator marking where data ends and future zone begins */}
          <line x1={DATA_W} y1={0} x2={DATA_W} y2={H} stroke="var(--border)" strokeWidth="0.5" strokeDasharray="4,4" opacity="0.5"/>
          <path d={fill} fill="url(#ag)" className="chart-fill"/>
          <path d={line} className="chart-line"/>
          {hover && (
            <line x1={hover.x} y1={0} x2={hover.x} y2={H} stroke="var(--muted)" strokeWidth="0.5" strokeDasharray="2,2"/>
          )}
          {hover && !hover.inFuture && (
            <circle cx={hover.x} cy={hover.y} r="4" fill="#0f7d40" stroke="var(--panel)" strokeWidth="2"/>
          )}
          {!hover && (
            <>
              <circle cx={pts[pts.length-1].x} cy={pts[pts.length-1].y} r="3" fill="#0f7d40"/>
              <circle cx={pts[pts.length-1].x} cy={pts[pts.length-1].y} r="6" fill="#0f7d40" opacity="0.2"/>
            </>
          )}
        </svg>
        {hover && !hover.inFuture && (
          <div style={{
            position:"absolute", left:tooltipLeft, top: hover.y < 50 ? hover.y + 16 : hover.y - 36,
            transform:tooltipTransform, background:"var(--bg2)", border:"1px solid var(--border)",
            padding:"4px 8px", borderRadius:2, pointerEvents:"none",
            fontFamily:"var(--font-mono)", fontSize:10, color:"var(--amber)",
            whiteSpace:"nowrap", zIndex:5,
          }}>
            {hover.date && (
              <span style={{ color: "var(--muted)", marginRight: 6 }}>
                {new Date(hover.date).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
              </span>
            )}
            {fmtTooltip(hover.value)}
          </div>
        )}
      </div>
      <div className="chart-xaxis">
        {xLabels.map((l,i)=><div key={i} className="chart-xlabel">{l}</div>)}
      </div>
    </div>
  );
}

/**
 * AllocationDonut: Donut chart showing portfolio allocation percentages
 * Interactive with hover effects, displays total value in center
 */
const PALETTE = ["#0f7d40","#3d7ef5","#00d97e","#f04438","#0fc0d0","#a78bfa","#fb923c"];

export function AllocationDonut({ holdings: holdingsProp = null, currencySymbol = "$" }) {
  const [hoverIdx, setHoverIdx] = useState(null);
  const data = holdingsProp || [];
  const total = data.reduce((s,h)=>s+(h.quantity||h.qty||0)*(h.current_price||h.price||0),0);
  if (total === 0) return (
    <div style={{fontFamily:"var(--font-mono)",fontSize:11,color:"var(--muted)",padding:"24px 0",textAlign:"center"}}>
      NO ALLOCATION DATA
    </div>
  );
  /* Group holdings by symbol to consolidate duplicate positions */
  const grouped = {};
  data.forEach(h => {
    const sym = h.symbol;
    const qty = h.quantity || h.qty || 0;
    const val = qty * (h.current_price || h.price || 0);
    if (grouped[sym]) {
      grouped[sym].qty += qty;
      grouped[sym].val += val;
    } else {
      grouped[sym] = { symbol: sym, name: h.name || sym, qty, val };
    }
  });
  const slices = Object.values(grouped).map((g, i) => ({
    symbol: g.symbol,
    name: g.name,
    qty: g.qty,
    val: g.val,
    pct: (g.val / total) * 100,
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
              {currencySymbol}{(slices[hoverIdx].val/1000).toFixed(2)}K
            </text>
          </>
        ) : (
          <>
            <text x={cx} y={cy-5} textAnchor="middle" fill="var(--muted)" fontSize="8" fontFamily="IBM Plex Mono" letterSpacing="1">TOTAL</text>
            <text x={cx} y={cy+10} textAnchor="middle" fill="var(--amber)" fontSize="11" fontFamily="IBM Plex Mono" fontWeight="600">
              {currencySymbol}{(total/1000).toFixed(1)}K
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
            <span className="donut-pct">{s.pct.toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Heatmap: Treemap-style heatmap of portfolio holdings
 * Tile size = daily volume, color = daily gain (green pos / red neg)
 */
function heatColor(chgPct) {
  const t = Math.min(Math.abs(chgPct) / 5, 1);
  if (chgPct >= 0) {
    return `rgb(${Math.round(10 - t * 10)},${Math.round(46 + t * 171)},${Math.round(26 + t * 100)})`;
  }
  return `rgb(${Math.round(46 + t * 194)},${Math.round(10 + t * 58)},${Math.round(10 + t * 46)})`;
}

function squarify(items, rect) {
  if (!items.length) return [];
  const totalVal = items.reduce((s, it) => s + it.value, 0);
  if (totalVal <= 0) return [];
  const results = [];
  let remaining = [...items];
  let { x, y, w, h } = rect;

  while (remaining.length > 0) {
    const remVal = remaining.reduce((s, it) => s + it.value, 0);
    const isVert = w >= h;
    const side = isVert ? h : w;

    let row = [remaining[0]];
    let rowVal = remaining[0].value;

    const worstAspect = (rItems, rVal) => {
      const area = (rVal / remVal) * w * h;
      const rowSide = area / side;
      let mx = 0;
      for (const it of rItems) {
        const dim = (it.value / rVal) * area / rowSide;
        const aspect = dim > rowSide ? dim / rowSide : rowSide / dim;
        if (aspect > mx) mx = aspect;
      }
      return mx;
    };

    let bestWorst = worstAspect(row, rowVal);
    let i = 1;
    while (i < remaining.length) {
      row.push(remaining[i]);
      const newVal = rowVal + remaining[i].value;
      const w2 = worstAspect(row, newVal);
      if (w2 > bestWorst) {
        row.pop();
        break;
      }
      rowVal = newVal;
      bestWorst = w2;
      i++;
    }

    const rowFrac = rowVal / remVal;
    const rowThickness = isVert ? w * rowFrac : h * rowFrac;
    let offset = 0;
    for (const it of row) {
      const itemFrac = it.value / rowVal;
      const itemLen = side * itemFrac;
      if (isVert) {
        results.push({ ...it, rx: x, ry: y + offset, rw: rowThickness, rh: itemLen });
      } else {
        results.push({ ...it, rx: x + offset, ry: y, rw: itemLen, rh: rowThickness });
      }
      offset += itemLen;
    }

    if (isVert) { x += rowThickness; w -= rowThickness; }
    else { y += rowThickness; h -= rowThickness; }
    remaining = remaining.slice(row.length);
  }
  return results;
}

export function Heatmap({ holdings = [], onTileAction = null }) {
  const wrapRef = useRef(null);
  /* Taller container (280px) gives small-cap tiles more vertical room */
  const MAP_H = 280;
  const LEGEND_H = 24;
  const [dims, setDims] = useState({ w: 600, h: MAP_H });
  const [hover, setHover] = useState(null);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(entries => {
      const cr = entries[0].contentRect;
      if (cr.width > 0) setDims({ w: cr.width, h: MAP_H });
    });
    ro.observe(el);
    setDims({ w: el.clientWidth || 600, h: MAP_H });
    return () => ro.disconnect();
  }, []);

  const items = useMemo(() => {
    return holdings
      .filter(h => (h.volume || 0) > 0 && !h.symbol.endsWith("-USD"))
      .map(h => ({ symbol: h.symbol, chgPct: h.chgPct || 0, volume: h.volume, value: h.volume }))
      .sort((a, b) => b.value - a.value);
  }, [holdings]);

  const tiles = useMemo(() => {
    if (!items.length || dims.w <= 0) return [];
    const gap = 2;
    return squarify(items, { x: gap, y: gap, w: dims.w - gap * 2, h: dims.h - gap * 2 });
  }, [items, dims]);

  if (!items.length) {
    return (
      <div ref={wrapRef} style={{ width: "100%", height: MAP_H, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--muted)" }}>
        NO VOLUME DATA
      </div>
    );
  }

  const fmtVol = v => v >= 1e9 ? (v / 1e9).toFixed(1) + "B" : v >= 1e6 ? (v / 1e6).toFixed(1) + "M" : v >= 1e3 ? (v / 1e3).toFixed(0) + "K" : String(v);

  /**
   * Adaptive font size for the ticker symbol based on tile dimensions.
   * Ensures even small tiles show at least a compact label.
   *
   * @param {number} w - Tile width in px.
   * @param {number} h - Tile height in px.
   * @returns {number} Font size in px.
   */
  const symbolFontSize = (w, h) => {
    const minDim = Math.min(w, h);
    if (minDim >= 40) return 12;
    if (minDim >= 28) return 10;
    if (minDim >= 18) return 8;
    return 7;
  };

  /**
   * Build legend stops: 11 evenly-spaced values from -5% to +5%.
   * Each stop maps to the heatColor scale for the gradient bar.
   */
  const legendStops = [];
  for (let pct = -5; pct <= 5; pct += 1) {
    const offset = ((pct + 5) / 10) * 100;
    legendStops.push({ offset: `${offset}%`, color: heatColor(pct) });
  }

  return (
    <div ref={wrapRef} style={{ width: "100%", position: "relative" }}>
      {/* ── Treemap SVG ─────────────────────────────────────────────── */}
      <svg width={dims.w} height={dims.h} viewBox={`0 0 ${dims.w} ${dims.h}`} style={{ display: "block", background: "var(--panel)" }}>
        {tiles.map((t, i) => {
          const gap = 1.5;
          const isHovered = hover === i;
          const cellW = Math.max(0, t.rw - gap * 2);
          const cellH = Math.max(0, t.rh - gap * 2);
          /* Show symbol if at least 20×14 px — covers nearly all tiles */
          const showSymbol = cellW >= 20 && cellH >= 14;
          /* Show change % only when there is enough vertical room for two lines */
          const showPct = cellW >= 36 && cellH >= 32;
          const fSize = symbolFontSize(cellW, cellH);
          return (
            <g key={t.symbol} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}
              onClick={(e) => onTileAction && onTileAction(t.symbol, e)}
              style={{ cursor: "pointer" }}>
              <rect
                x={t.rx + gap} y={t.ry + gap}
                width={cellW} height={cellH}
                rx={2}
                fill={heatColor(t.chgPct)}
                opacity={isHovered ? 1 : 0.85}
                stroke={isHovered ? "var(--bright)" : "var(--bg)"}
                strokeWidth={isHovered ? 1.5 : 0.5}
              />
              {showSymbol && (
                <text
                  x={t.rx + t.rw / 2} y={t.ry + t.rh / 2 - (showPct ? fSize * 0.55 : 0)}
                  textAnchor="middle" dominantBaseline="central"
                  fill="#fff" fontSize={fSize} fontFamily="IBM Plex Mono" fontWeight="600"
                  style={{ pointerEvents: "none" }}
                >
                  {t.symbol}
                </text>
              )}
              {showPct && (
                <text
                  x={t.rx + t.rw / 2} y={t.ry + t.rh / 2 + fSize * 0.6}
                  textAnchor="middle" dominantBaseline="central"
                  fill="rgba(255,255,255,0.75)" fontSize={Math.max(7, fSize - 2)} fontFamily="IBM Plex Mono"
                  style={{ pointerEvents: "none" }}
                >
                  {t.chgPct >= 0 ? "+" : ""}{t.chgPct.toFixed(1)}%
                </text>
              )}
            </g>
          );
        })}
      </svg>

      {/* ── Gradient Legend ──────────────────────────────────────────── */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "center",
        gap: 6, height: LEGEND_H, marginTop: 4,
        fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--mid)",
      }}>
        <span>-5%</span>
        <svg width={140} height={10} style={{ display: "block", borderRadius: 2, overflow: "hidden" }}>
          <defs>
            <linearGradient id="heatLegendGrad" x1="0%" y1="0%" x2="100%" y2="0%">
              {legendStops.map((s, idx) => (
                <stop key={idx} offset={s.offset} stopColor={s.color} />
              ))}
            </linearGradient>
          </defs>
          <rect width={140} height={10} fill="url(#heatLegendGrad)" />
        </svg>
        <span>+5%</span>
      </div>

      {/* ── Hover Tooltip ───────────────────────────────────────────── */}
      {hover !== null && tiles[hover] && (
        <div style={{
          position: "absolute", top: 8, right: 8,
          background: "rgba(14,17,23,0.95)", border: "1px solid var(--border)",
          padding: "8px 12px", borderRadius: 3, pointerEvents: "none",
          fontFamily: "var(--font-mono)", fontSize: 11, lineHeight: 1.6, zIndex: 5,
        }}>
          <div style={{ color: "var(--bright)", fontWeight: 600, marginBottom: 2 }}>{tiles[hover].symbol}</div>
          <div style={{ color: tiles[hover].chgPct >= 0 ? "var(--green)" : "var(--red)" }}>
            {tiles[hover].chgPct >= 0 ? "+" : ""}{tiles[hover].chgPct.toFixed(2)}% TODAY
          </div>
          <div style={{ color: "var(--mid)" }}>VOL {fmtVol(tiles[hover].volume)}</div>
        </div>
      )}
    </div>
  );
}
