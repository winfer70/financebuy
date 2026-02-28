/**
 * Charts Page
 * 
 * Advanced charting page with OHLCV data, technical analysis, and symbol search.
 */

import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import api from "../api/client";
import { Ic } from "../components/common/Icons";
import { useMarketStatus } from "../components/common";

export function generateOHLCV(basePrice, years = 5) {
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
export function ChartsPage({ initialSymbol, goBack, token }) {
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

