/**
 * Data Visualization Components
 *
 * Exports:
 * - Sparkline: Compact mini chart for trend indication
 * - PortfolioChart: Interactive area chart with hover tooltips
 * - AllocationDonut: Donut chart showing portfolio allocation percentages
 */

import { useState, useMemo, useRef, useCallback } from "react";

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
 * PortfolioChart: Interactive area chart showing portfolio value over time
 * Supports hover interaction for detailed values
 */
export function PortfolioChart({ height=160, data=null, period="3M" }) {
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

/**
 * AllocationDonut: Donut chart showing portfolio allocation percentages
 * Interactive with hover effects, displays total value in center
 */
const PALETTE = ["#0f7d40","#3d7ef5","#00d97e","#f04438","#0fc0d0","#a78bfa","#fb923c"];

export function AllocationDonut({ holdings: holdingsProp = null }) {
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
