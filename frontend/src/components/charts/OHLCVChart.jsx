/**
 * OHLCVChart — reusable candlestick / line chart with optional volume bars,
 * SMA overlays, crosshair, signal markers, zoom/pan, drawing tools,
 * controls bar, and stats bar.
 *
 * All interactive features are opt-in via props and default to off so the
 * component stays backward-compatible with existing callers (TradingPage
 * equity curves, DashboardPage mini-charts, etc.).
 *
 * Rendering: 100% SVG — no canvas dependency.
 *
 * Props (original):
 *   data            — Array<{ date, open, high, low, close, volume }>
 *   chartType       — "candle" | "line"  (default "candle")
 *   showVolume      — render volume bars in bottom 15% (default true)
 *   showCrosshair   — enable crosshair + tooltip on hover (default true)
 *   smaOverlays     — Array<{ period, color, dashed? }> SMA lines to render
 *   signals         — Array<{ index, type, label, color? }> markers
 *   height          — explicit px height (default: fills container)
 *   currencySymbol  — axis label prefix (default "$")
 *   onBarHover      — (bar, index) => void  callback
 *
 * Props (interactive — all default false/null):
 *   enableZoom          — scroll-wheel zoom + drag-to-pan
 *   enableDrawingTools  — left toolbar with 9 drawing tools
 *   enableControls      — top controls bar (chart type + overlay toggles)
 *   showStatsBar        — top stats bar (OHLCV, gain, volume, 52wk range)
 *   symbol              — ticker symbol string, shown in stats bar
 *   chartId             — unique prefix for SVG defs IDs (avoid collisions
 *                         when multiple charts on one page)
 */

import React, { useState, useRef, useEffect, useMemo, useCallback } from "react";
import { Ic } from "../common/Icons.jsx";
import {
  DRAWING_TOOLS, DEFAULT_DRAW_STYLE, genDrawingId,
  pixelToAnchor, hitTestDrawing, renderDrawing, renderPreview,
  DrawingContextToolbar,
  renderAnchorHandles, moveDrawingAnchors, moveOneAnchor,
  resolveAnchorX, resolveAnchorY,
} from "./DrawingTools.jsx";
import { OHLCV_INTERACTIVE_CSS } from "./chartStyles.js";

/* ── Helpers ─────────────────────────────────────────────────────────────── */

/** Compute simple moving average over close prices. */
function calcSMA(data, period) {
  return data.map((d, i) => {
    if (i < period - 1) return { date: d.date, value: null };
    const slice = data.slice(i - period + 1, i + 1);
    const avg = slice.reduce((s, x) => s + x.close, 0) / period;
    return { date: d.date, value: +avg.toFixed(2) };
  });
}

/** Format volume into compact string (e.g. "1.23B", "456M", "12K"). */
const fmtVol = (v) =>
  v >= 1e9  ? (v / 1e9).toFixed(2) + "B"
  : v >= 1e6  ? (v / 1e6).toFixed(2) + "M"
  : v >= 1e3  ? (v / 1e3).toFixed(0) + "K"
  : String(v);

/* ── Component ───────────────────────────────────────────────────────────── */

const BASE_PAD = { top: 20, right: 72, bottom: 22, left: 8 };

export default function OHLCVChart({
  data: allData = [],
  chartType: chartTypeProp = "candle",
  showVolume: showVolumeProp = true,
  showCrosshair = true,
  smaOverlays: smaOverlaysProp = [],
  signals = [],
  height: explicitHeight,
  currencySymbol = "$",
  onBarHover,
  /* Interactive feature flags */
  enableZoom = false,
  enableDrawingTools = false,
  enableControls = false,
  showStatsBar = false,
  symbol = "",
  chartId = "ohlcv",
}) {
  /* ── Refs ─────────────────────────────────────────────────────────────── */
  const containerRef = useRef(null);
  const wrapRef      = useRef(null);
  const svgRef       = useRef(null);
  const dragRef      = useRef(null);
  const drawSaveRef  = useRef(null);

  /* ── Core state ──────────────────────────────────────────────────────── */
  const [dims, setDims]       = useState({ w: 600, h: 400 });
  const [hoverIdx, setHoverIdx] = useState(-1);

  /* ── Control-bar state (only used when enableControls) ───────────────── */
  const [chartType, setChartType]       = useState(chartTypeProp);
  const [showVolume, setShowVolume]     = useState(showVolumeProp);
  const [smaToggles, setSmaToggles]     = useState(() => {
    const map = {};
    smaOverlaysProp.forEach(s => { map[s.period] = true; });
    return map;
  });

  /* Sync chartType with prop when not controlling */
  useEffect(() => { if (!enableControls) setChartType(chartTypeProp); }, [chartTypeProp, enableControls]);
  useEffect(() => { if (!enableControls) setShowVolume(showVolumeProp); }, [showVolumeProp, enableControls]);

  const activeSmaOverlays = useMemo(() => {
    if (!enableControls) return smaOverlaysProp;
    return smaOverlaysProp.filter(s => smaToggles[s.period]);
  }, [enableControls, smaOverlaysProp, smaToggles]);

  /* ── Zoom / Pan state ────────────────────────────────────────────────── */
  const [zoom, setZoom] = useState(null); // null = show all data

  /* ── Drawing state (only used when enableDrawingTools) ────────────────── */
  const [drawings, setDrawings]               = useState([]);
  const [activeTool, setActiveTool]           = useState(null);
  const [pendingAnchors, setPendingAnchors]   = useState([]);
  const [previewPoint, setPreviewPoint]       = useState(null);
  const [selectedDrawingId, setSelectedDrawingId] = useState(null);
  const [drawingStyle, setDrawingStyle]       = useState({ ...DEFAULT_DRAW_STYLE });
  const [textInput, setTextInput]             = useState("");

  /* ── Draw interaction state (move/resize drawings) ──────────────────── */
  const [drawInteraction, setDrawInteraction] = useState("idle"); // "idle" | "moving" | "resizing"
  const drawDragStartRef = useRef(null);   // { x, y, anchors: [...] } — captured at drag start
  const drawDragAnchorRef = useRef(null);  // anchor index being resized, null during move

  /* ── Inject interactive CSS once ─────────────────────────────────────── */
  useEffect(() => {
    const needsCss = enableZoom || enableDrawingTools || enableControls || showStatsBar;
    if (!needsCss) return;
    const id = "ohlcv-interactive-css";
    if (document.getElementById(id)) return;
    const style = document.createElement("style");
    style.id = id;
    style.textContent = OHLCV_INTERACTIVE_CSS;
    document.head.appendChild(style);
  }, [enableZoom, enableDrawingTools, enableControls, showStatsBar]);

  /* ── Resize observer ─────────────────────────────────────────────────── */
  useEffect(() => {
    const obs = new ResizeObserver((entries) => {
      for (const e of entries) {
        const { width, height: h } = e.contentRect;
        setDims({ w: Math.round(width), h: Math.round(explicitHeight || h) });
      }
    });
    const target = containerRef.current;
    if (target) obs.observe(target);
    return () => obs.disconnect();
  }, [explicitHeight]);

  /* ── Data windowing (zoom / pan support) ─────────────────────────────── */
  const { visibleData, visibleStart, totalSlots } = useMemo(() => {
    if (!enableZoom || !zoom) {
      return { visibleData: allData, visibleStart: 0, totalSlots: allData.length };
    }
    const start = Math.max(0, zoom.start);
    const count = Math.max(10, zoom.count);
    const data  = allData.slice(start, start + count);
    return { visibleData: data, visibleStart: start, totalSlots: count };
  }, [allData, zoom, enableZoom]);

  /* ── Padding — shift left when drawing toolbar is visible ────────────── */
  const PAD = useMemo(() => (
    enableDrawingTools ? { ...BASE_PAD, left: BASE_PAD.left + 40 } : BASE_PAD
  ), [enableDrawingTools]);

  /* ── Geometry ─────────────────────────────────────────────────────────── */
  const n      = visibleData.length;
  const totalH = Math.max(50, dims.h - PAD.top - PAD.bottom);
  const VOL_H  = showVolume ? Math.max(40, Math.round(totalH * 0.15)) : 0;
  const VOL_GAP = showVolume ? 8 : 0;
  const H      = totalH - VOL_H - VOL_GAP;
  const W      = Math.max(10, dims.w - PAD.left - PAD.right);
  const volTop = PAD.top + H + VOL_GAP;

  const slots    = enableZoom ? totalSlots : n;
  const candleGap = slots > 0 ? W / slots : 1;
  const candleW   = Math.max(1, Math.min(14, candleGap * 0.72));

  const priceMin = n > 0 ? Math.min(...visibleData.map(d => d.low))  : 0;
  const priceMax = n > 0 ? Math.max(...visibleData.map(d => d.high)) : 1;
  const pricePad = (priceMax - priceMin) * 0.07 || 1;
  const pLo = priceMin - pricePad;
  const pHi = priceMax + pricePad;
  const volMax = n > 0 ? Math.max(...visibleData.map(d => d.volume), 1) : 1;

  const xOf = useCallback((i) => PAD.left + (i + 0.5) * candleGap, [PAD.left, candleGap]);
  const yOf = useCallback((p) => PAD.top + H - ((p - pLo) / (pHi - pLo)) * H, [PAD.top, H, pLo, pHi]);

  /* ── Y-axis ticks ────────────────────────────────────────────────────── */
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

  /* ── X-axis labels ───────────────────────────────────────────────────── */
  const xLabels = useMemo(() => {
    const labels = [];
    let lastYear = null;
    const maxLabels = Math.floor(W / 80);
    const step = Math.max(1, Math.floor(n / maxLabels));
    for (let i = 0; i < n; i += step) {
      const d = new Date(visibleData[i].date);
      const mo = d.toLocaleString("en-US", { month: "short" });
      const yr = d.getFullYear();
      const lbl = yr !== lastYear ? `${mo} '${String(yr).slice(2)}` : mo;
      labels.push({ x: xOf(i), label: lbl });
      lastYear = yr;
    }
    return labels;
  }, [visibleData, n, W, xOf]);

  /* ── SMA computations (full-history then sliced) ─────────────────────── */
  const fullSmaLines = useMemo(
    () => activeSmaOverlays.map(cfg => ({ ...cfg, data: calcSMA(allData, cfg.period) })),
    [allData, activeSmaOverlays],
  );
  const smaLines = useMemo(
    () => fullSmaLines.map(sma => ({
      ...sma,
      data: sma.data.slice(visibleStart, visibleStart + n),
    })),
    [fullSmaLines, visibleStart, n],
  );

  /** Build SVG path string from SMA data. */
  const smaPath = (smaData) => {
    let path = "";
    for (let i = 0; i < smaData.length; i++) {
      if (!smaData[i].value) continue;
      const x = xOf(i);
      const y = yOf(smaData[i].value);
      path += `${!path || !smaData[i - 1]?.value ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    }
    return path;
  };

  /* ── Line path (for line chart mode) ─────────────────────────────────── */
  const linePath = useMemo(() => {
    let p = "";
    for (let i = 0; i < n; i++) {
      const x = xOf(i);
      const y = yOf(visibleData[i].close);
      p += `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    }
    return p;
  }, [visibleData, n, xOf, yOf]);

  /* ── Drawing tools: localStorage persistence ─────────────────────────── */
  useEffect(() => {
    if (!enableDrawingTools || !symbol) return;
    try {
      const stored = localStorage.getItem(`tt_ohlcv_drawings_${symbol}`);
      if (stored) setDrawings(JSON.parse(stored));
      else setDrawings([]);
    } catch { setDrawings([]); }
  }, [enableDrawingTools, symbol]);

  useEffect(() => {
    if (!enableDrawingTools || !symbol) return;
    clearTimeout(drawSaveRef.current);
    drawSaveRef.current = setTimeout(() => {
      try { localStorage.setItem(`tt_ohlcv_drawings_${symbol}`, JSON.stringify(drawings)); } catch {}
    }, 500);
    return () => clearTimeout(drawSaveRef.current);
  }, [drawings, symbol, enableDrawingTools]);

  /* ── Drawing tools: keyboard shortcuts ───────────────────────────────── */
  useEffect(() => {
    if (!enableDrawingTools) return;
    const onKey = (e) => {
      if (e.key === "Escape") {
        if (activeTool) { setActiveTool(null); setPendingAnchors([]); setPreviewPoint(null); }
        else setSelectedDrawingId(null);
      }
      if ((e.key === "Delete" || e.key === "Backspace") && selectedDrawingId && !activeTool) {
        if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
        setDrawings(prev => prev.filter(d => d.id !== selectedDrawingId));
        setSelectedDrawingId(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enableDrawingTools, activeTool, selectedDrawingId]);

  /* ── Mouse interactions ──────────────────────────────────────────────── */
  const handleMouseMove = useCallback((e) => {
    const svg = svgRef.current || e.currentTarget;
    const rect = svg.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    /* ── Moving a drawing: apply pixel delta to all anchors ── */
    if (drawInteraction === "moving" && drawDragStartRef.current && selectedDrawingId) {
      const selDrawing = drawings.find(d => d.id === selectedDrawingId);
      if (selDrawing) {
        const dx = mx - drawDragStartRef.current.x;
        const dy = my - drawDragStartRef.current.y;
        /* Use the original anchors from drag start to avoid accumulation drift */
        const original = { ...selDrawing, anchors: drawDragStartRef.current.anchors };
        const chartParams = { visibleData, visibleStart, allData, xOf, PAD, H, pLo, pHi, n, candleGap };
        const updated = moveDrawingAnchors(original, dx, dy, chartParams);
        setDrawings(prev => prev.map(d => d.id === selectedDrawingId ? updated : d));
      }
      return;
    }

    /* ── Resizing a drawing: move one anchor to mouse position ── */
    if (drawInteraction === "resizing" && drawDragAnchorRef.current != null && selectedDrawingId) {
      const selDrawing = drawings.find(d => d.id === selectedDrawingId);
      if (selDrawing) {
        const chartParams = { visibleData, visibleStart, allData, xOf, PAD, H, pLo, pHi, n, candleGap };
        const updated = moveOneAnchor(selDrawing, drawDragAnchorRef.current, mx, my, chartParams);
        setDrawings(prev => prev.map(d => d.id === selectedDrawingId ? updated : d));
      }
      return;
    }

    /* Drawing preview point update */
    if (enableDrawingTools && activeTool && pendingAnchors.length > 0) {
      const anchor = pixelToAnchor(mx, my, visibleData, n, PAD, candleGap, H, pLo, pHi);
      if (anchor) setPreviewPoint(anchor);
    }

    /* Drag-to-pan */
    if (enableZoom && dragRef.current) {
      const dx = mx - dragRef.current.startX;
      const candleShift = Math.round(-dx / candleGap);
      const base = dragRef.current.baseStart;
      const baseCount = dragRef.current.baseCount;
      const maxFuture = Math.max(10, Math.round(baseCount * 0.25));
      const newStart = Math.max(0, Math.min(allData.length - baseCount + maxFuture, base + candleShift));
      setZoom({ start: newStart, count: baseCount });
      return;
    }

    /* Crosshair */
    if (!showCrosshair || n === 0) return;
    const idx = Math.round((mx - PAD.left) / candleGap - 0.5);
    const clamped = Math.max(0, Math.min(n - 1, idx));
    setHoverIdx(clamped);
    if (onBarHover && visibleData[clamped]) onBarHover(visibleData[clamped], clamped);

    /* ── Cursor hint: show "move" when hovering body of selected drawing ── */
    if (enableDrawingTools && selectedDrawingId && !activeTool && drawInteraction === "idle") {
      const hitId = hitTestDrawing(drawings, mx, my, visibleData, visibleStart, allData, xOf, PAD, H, W, pLo, pHi);
      if (hitId === selectedDrawingId && wrapRef.current) {
        wrapRef.current.style.cursor = "move";
      } else if (wrapRef.current) {
        wrapRef.current.style.cursor = "";
      }
    }
  }, [showCrosshair, n, candleGap, onBarHover, visibleData, PAD, enableZoom, enableDrawingTools, activeTool,
      pendingAnchors, allData, H, pLo, pHi, drawInteraction, selectedDrawingId, drawings,
      visibleStart, xOf, W]);

  const handleMouseDown = useCallback((e) => {
    if (e.button !== 0) return;
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    /* Drawing mode: place anchor */
    if (enableDrawingTools && activeTool) {
      const anchor = pixelToAnchor(mx, my, visibleData, n, PAD, candleGap, H, pLo, pHi);
      if (!anchor) return;
      e.preventDefault();
      e.stopPropagation();
      const toolDef = DRAWING_TOOLS[activeTool];
      const newAnchors = [...pendingAnchors, anchor];
      if (newAnchors.length >= toolDef.anchors) {
        const style = { ...drawingStyle };
        if (activeTool === "text") style.text = textInput || "Text";
        setDrawings(prev => [...prev, {
          id: genDrawingId(), type: activeTool, anchors: newAnchors,
          style, visible: true, locked: false, createdAt: new Date().toISOString(),
        }]);
        setPendingAnchors([]);
        setPreviewPoint(null);
      } else {
        setPendingAnchors(newAnchors);
      }
      return;
    }

    /* ── Anchor-handle hit-test: start resizing if click lands on a handle ── */
    if (enableDrawingTools && selectedDrawingId && !activeTool) {
      const selDrawing = drawings.find(d => d.id === selectedDrawingId);
      if (selDrawing && selDrawing.anchors) {
        for (let i = 0; i < selDrawing.anchors.length; i++) {
          const anchorPx = resolveAnchorX(selDrawing.anchors[i], visibleData, visibleStart, allData, xOf);
          const anchorPy = resolveAnchorY(selDrawing.anchors[i].price, PAD, H, pLo, pHi);
          if (Math.hypot(mx - anchorPx, my - anchorPy) <= 8) {
            /* Enter resize mode for this anchor */
            setDrawInteraction("resizing");
            drawDragAnchorRef.current = i;
            drawDragStartRef.current = { x: mx, y: my, anchors: selDrawing.anchors.map(a => ({ ...a })) };
            e.preventDefault();
            e.stopPropagation();
            return;
          }
        }
      }
    }

    /* Hit-test drawings for selection or body-drag */
    if (enableDrawingTools) {
      const hitId = hitTestDrawing(drawings, mx, my, visibleData, visibleStart, allData, xOf, PAD, H, W, pLo, pHi);

      /* ── Body hit on already-selected drawing: start moving ── */
      if (hitId && hitId === selectedDrawingId && !activeTool) {
        const selDrawing = drawings.find(d => d.id === selectedDrawingId);
        if (selDrawing) {
          setDrawInteraction("moving");
          drawDragAnchorRef.current = null;
          drawDragStartRef.current = { x: mx, y: my, anchors: selDrawing.anchors.map(a => ({ ...a })) };
          e.preventDefault();
          e.stopPropagation();
          return;
        }
      }

      /* ── Hit a different drawing: select it ── */
      if (hitId) { setSelectedDrawingId(hitId); e.preventDefault(); return; }
      setSelectedDrawingId(null);
    }

    /* Drag-to-pan */
    if (enableZoom) {
      const cur = zoom || { start: visibleStart, count: visibleData.length };
      dragRef.current = { startX: mx, baseStart: cur.start, baseCount: cur.count };
      e.preventDefault();
    }
  }, [enableDrawingTools, enableZoom, activeTool, pendingAnchors, drawingStyle, textInput, visibleData, n, PAD,
      candleGap, H, W, pLo, pHi, drawings, visibleStart, allData, xOf, zoom, selectedDrawingId]);

  const handleMouseUp = useCallback(() => {
    /* Commit move/resize: drawings state already updated live, just exit interaction */
    if (drawInteraction !== "idle") {
      setDrawInteraction("idle");
      drawDragStartRef.current = null;
      drawDragAnchorRef.current = null;
      /* localStorage save happens automatically via the debounced useEffect on drawings */
      return;
    }
    dragRef.current = null;
  }, [drawInteraction]);

  const handleMouseLeave = useCallback(() => {
    /* Reset any active drawing drag */
    if (drawInteraction !== "idle") {
      setDrawInteraction("idle");
      drawDragStartRef.current = null;
      drawDragAnchorRef.current = null;
    }
    dragRef.current = null;
    setHoverIdx(-1);
    if (enableDrawingTools && activeTool) setPreviewPoint(null);
    /* Reset cursor override */
    if (wrapRef.current) wrapRef.current.style.cursor = "";
  }, [enableDrawingTools, activeTool, drawInteraction]);

  /* ── Scroll-wheel zoom ───────────────────────────────────────────────── */
  const handleWheel = useCallback((e) => {
    if (!enableZoom) return;
    e.preventDefault();
    const factor   = e.deltaY > 0 ? 1.15 : 0.87;
    const curCount = zoom ? zoom.count : allData.length;
    const curStart = zoom ? zoom.start : 0;
    const newCount = Math.max(10, Math.min(allData.length, Math.round(curCount * factor)));

    const svg  = svgRef.current;
    const rect = svg?.getBoundingClientRect();
    const ratio = rect ? (e.clientX - rect.left - PAD.left) / W : 0.5;
    const pivot = curStart + Math.round(curCount * ratio);
    const maxFuture = Math.max(10, Math.round(newCount * 0.25));
    const newStart = Math.max(0, Math.min(allData.length - newCount + maxFuture, Math.round(pivot - newCount * ratio)));

    setZoom({ start: newStart, count: newCount });
  }, [enableZoom, zoom, allData.length, W, PAD]);

  /* Attach wheel listener with { passive: false } */
  useEffect(() => {
    if (!enableZoom) return;
    const el = wrapRef.current;
    if (!el) return;
    el.addEventListener("wheel", handleWheel, { passive: false });
    return () => el.removeEventListener("wheel", handleWheel);
  }, [enableZoom, handleWheel]);

  /* ── Stats bar computations ──────────────────────────────────────────── */
  const last     = visibleData[n - 1] || {};
  const prev     = visibleData[n - 2] || {};
  const dayGain  = (last.close || 0) - (prev.close || 0);
  const dayGainPct = prev.close ? (dayGain / prev.close) * 100 : 0;

  /* ── Hover bar data ──────────────────────────────────────────────────── */
  const hBar = hoverIdx >= 0 && hoverIdx < n ? visibleData[hoverIdx] : null;

  /* ── Cursor style ────────────────────────────────────────────────────── */
  const cursor = drawInteraction === "moving" ? "move"
    : drawInteraction === "resizing" ? "crosshair"
    : enableDrawingTools && activeTool ? "crosshair"
    : enableZoom && dragRef.current ? "grabbing"
    : enableZoom ? "grab"
    : showCrosshair ? "crosshair"
    : "default";

  /* ── Unique IDs for clipPath (avoids collision with multiple charts) ── */
  const clipId    = `${chartId}Clip`;
  const lineGradId = `${chartId}LineGrad`;

  /* ── Render ──────────────────────────────────────────────────────────── */
  return (
    <div
      ref={containerRef}
      style={{
        position: "relative",
        width: "100%",
        height: explicitHeight || "100%",
        display: "flex",
        flexDirection: "column",
        background: "#090b0f",
        overflow: "hidden",
      }}
    >
      {/* ── STATS BAR ── */}
      {showStatsBar && n > 0 && (
        <div className="ohlcv-stats-bar">
          {/* Symbol */}
          <div className="ohlcv-stock-stat">
            <div className="ohlcv-ss-label">SYMBOL</div>
            <div className="ohlcv-ss-value amber" style={{ fontSize: 20 }}>{symbol || "—"}</div>
          </div>
          <div className="ohlcv-stat-sep" />
          {/* Open */}
          <div className="ohlcv-stock-stat">
            <div className="ohlcv-ss-label">OPEN</div>
            <div className="ohlcv-ss-value">{currencySymbol}{last.open?.toFixed(2) ?? "—"}</div>
          </div>
          <div className="ohlcv-stat-sep" />
          {/* Close */}
          <div className="ohlcv-stock-stat">
            <div className="ohlcv-ss-label">CLOSE</div>
            <div className="ohlcv-ss-value amber">{currencySymbol}{last.close?.toFixed(2) ?? "—"}</div>
          </div>
          <div className="ohlcv-stat-sep" />
          {/* Volume */}
          <div className="ohlcv-stock-stat">
            <div className="ohlcv-ss-label">VOLUME</div>
            <div className="ohlcv-ss-value" style={{ fontSize: 16 }}>{fmtVol(last.volume ?? 0)}</div>
          </div>
          <div className="ohlcv-stat-sep" />
          {/* Gain */}
          <div className="ohlcv-stock-stat">
            <div className="ohlcv-ss-label">GAIN</div>
            <div className={`ohlcv-ss-value ${dayGain >= 0 ? "pos" : "neg"}`} style={{ fontSize: 18 }}>
              {dayGain >= 0 ? "+" : ""}{currencySymbol}{Math.abs(dayGain).toFixed(2)}
            </div>
            <div className={`ohlcv-ss-badge ${dayGain >= 0 ? "pos" : "neg"}`}>
              {dayGainPct >= 0 ? "▲" : "▼"} {Math.abs(dayGainPct).toFixed(2)}%
            </div>
          </div>
          <div className="ohlcv-stat-sep" />
          {/* High / Low */}
          <div className="ohlcv-stock-stat">
            <div className="ohlcv-ss-label">HIGH / LOW</div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span className="ohlcv-ss-value" style={{ color: "#00d97e", fontSize: 15 }}>{currencySymbol}{last.high?.toFixed(2) ?? "—"}</span>
              <span style={{ color: "#1e2535", fontSize: 11 }}>·</span>
              <span className="ohlcv-ss-value" style={{ color: "#f04438", fontSize: 15 }}>{currencySymbol}{last.low?.toFixed(2) ?? "—"}</span>
            </div>
          </div>
          <div className="ohlcv-stat-sep" />
          {/* 52-week range */}
          {(() => {
            const yr   = allData.slice(-252);
            const hi52 = yr.length ? Math.max(...yr.map(d => d.high)) : 0;
            const lo52 = yr.length ? Math.min(...yr.map(d => d.low))  : 0;
            const pos52 = hi52 > lo52 ? ((last.close - lo52) / (hi52 - lo52)) * 100 : 50;
            return (
              <div className="ohlcv-stock-stat" style={{ minWidth: 140 }}>
                <div className="ohlcv-ss-label">52-WK RANGE</div>
                <div style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 4 }}>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "#718096" }}>{currencySymbol}{lo52.toFixed(0)}</span>
                  <div style={{ flex: 1, height: 4, background: "#1e2535", borderRadius: 2, position: "relative" }}>
                    <div style={{ position: "absolute", left: 0, top: 0, height: "100%", width: `${Math.min(100, Math.max(0, pos52))}%`, background: "#0f7d40", borderRadius: 2 }} />
                  </div>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "#718096" }}>{currencySymbol}{hi52.toFixed(0)}</span>
                </div>
                <div className="ohlcv-ss-sub">{pos52.toFixed(0)}% from 52w low</div>
              </div>
            );
          })()}
          {/* Zoom/pan hint */}
          {enableZoom && (
            <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "#4a5568", textAlign: "right" }}>
                <div style={{ letterSpacing: "0.5px" }}>SCROLL TO ZOOM</div>
                <div style={{ color: "#263045" }}>DRAG TO PAN</div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── CONTROLS BAR ── */}
      {enableControls && (
        <div className="ohlcv-controls">
          <span className="ohlcv-ctrl-label">TYPE</span>
          <div className="ohlcv-ctrl-group">
            {[["candle", "CANDLE"], ["line", "LINE"]].map(([v, l]) => (
              <button key={v} className={`ohlcv-ctrl-btn${chartType === v ? " active" : ""}`}
                onClick={() => setChartType(v)}>{l}</button>
            ))}
          </div>

          <div className="ohlcv-ctrl-sep" />

          <span className="ohlcv-ctrl-label">OVERLAYS</span>
          <div className="ohlcv-overlay-toggles">
            {/* Volume toggle */}
            <div className={`ohlcv-overlay-toggle${showVolume ? " on" : ""}`}
              onClick={() => setShowVolume(v => !v)}
              style={showVolume ? { borderColor: "rgba(74,85,104,0.3)", color: "#4a5568" } : {}}>
              <div className="ohlcv-overlay-dot" style={{ background: showVolume ? "#4a5568" : "#1e2535" }} />
              VOLUME
            </div>
            {/* SMA toggles */}
            {smaOverlaysProp.map(sma => (
              <div key={sma.period}
                className={`ohlcv-overlay-toggle${smaToggles[sma.period] ? " on" : ""}`}
                onClick={() => setSmaToggles(t => ({ ...t, [sma.period]: !t[sma.period] }))}
                style={smaToggles[sma.period] ? { borderColor: sma.color + "44", color: sma.color } : {}}>
                <div className="ohlcv-overlay-dot" style={{ background: smaToggles[sma.period] ? sma.color : "#1e2535" }} />
                SMA {sma.period}
              </div>
            ))}
          </div>

          {/* Reset zoom button */}
          {enableZoom && zoom && (
            <>
              <div className="ohlcv-ctrl-sep" />
              <button className="ohlcv-reset-zoom" onClick={() => setZoom(null)}>✕ RESET ZOOM</button>
            </>
          )}
        </div>
      )}

      {/* ── Chart area (SVG + drawing toolbar) ── */}
      <div ref={wrapRef} style={{ position: "relative", flex: 1, minHeight: 0, cursor }}>

        {/* ── Drawing Toolbar ── */}
        {enableDrawingTools && (
          <div className="ohlcv-draw-toolbar">
            {/* Cursor / Select */}
            <button className={`ohlcv-draw-tool-btn${!activeTool ? " active" : ""}`}
              title="Select (ESC)"
              onClick={() => { setActiveTool(null); setPendingAnchors([]); setPreviewPoint(null); }}>
              <Ic.cursor />
            </button>
            <div className="ohlcv-draw-toolbar-sep" />
            {/* Tool buttons */}
            {Object.entries(DRAWING_TOOLS).map(([key, def]) => {
              const IconComp = Ic[def.icon];
              return (
                <button key={key}
                  className={`ohlcv-draw-tool-btn${activeTool === key ? " active" : ""}`}
                  title={`${def.label} (${def.anchors} click${def.anchors > 1 ? "s" : ""})`}
                  onClick={() => {
                    setActiveTool(activeTool === key ? null : key);
                    setPendingAnchors([]); setPreviewPoint(null); setSelectedDrawingId(null);
                  }}>
                  <IconComp />
                </button>
              );
            })}
            <div className="ohlcv-draw-toolbar-sep" />
            {/* Color picker */}
            <div className="ohlcv-draw-color-wrap" title="Drawing color">
              <div className="ohlcv-draw-color-swatch" style={{ background: drawingStyle.color }} />
              <input type="color" className="ohlcv-draw-color-input"
                value={drawingStyle.color}
                onChange={e => setDrawingStyle(s => ({ ...s, color: e.target.value }))} />
            </div>
            {/* Line style */}
            {["solid", "dashed", "dotted"].map(ls => (
              <button key={ls}
                className={`ohlcv-draw-tool-btn mini${drawingStyle.lineStyle === ls ? " active" : ""}`}
                title={ls}
                onClick={() => setDrawingStyle(s => ({ ...s, lineStyle: ls }))}>
                <svg width="14" height="6" viewBox="0 0 14 6">
                  <line x1="0" y1="3" x2="14" y2="3" stroke="currentColor" strokeWidth="1.5"
                    strokeDasharray={ls === "dashed" ? "4,3" : ls === "dotted" ? "1.5,2" : "none"} />
                </svg>
              </button>
            ))}
            <div className="ohlcv-draw-toolbar-sep" />
            {/* Text input */}
            {activeTool === "text" && (
              <input className="ohlcv-draw-text-input"
                placeholder="..."
                value={textInput}
                onChange={e => setTextInput(e.target.value)}
                onClick={e => e.stopPropagation()}
                onMouseDown={e => e.stopPropagation()}
                autoFocus />
            )}
            {/* Clear all */}
            <button className="ohlcv-draw-tool-btn danger"
              title="Clear all drawings"
              onClick={() => { setDrawings([]); setSelectedDrawingId(null); }}>
              <Ic.eraser />
            </button>
            {/* Count */}
            {drawings.length > 0 && (
              <div className="ohlcv-draw-count">{drawings.length}</div>
            )}
            {/* Active tool label */}
            {activeTool && (
              <div className="ohlcv-draw-active-label">{DRAWING_TOOLS[activeTool]?.label}</div>
            )}
          </div>
        )}

        {/* ── SVG ── */}
        <svg
          ref={svgRef}
          style={{ display: "block", width: "100%", height: "100%" }}
          onMouseMove={handleMouseMove}
          onMouseDown={handleMouseDown}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseLeave}
        >
          <defs>
            <clipPath id={clipId}>
              <rect x={PAD.left} y={PAD.top} width={W} height={totalH} />
            </clipPath>
            <linearGradient id={lineGradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#0f7d40" stopOpacity="0.18" />
              <stop offset="100%" stopColor="#0f7d40" stopOpacity="0" />
            </linearGradient>
          </defs>

          {/* Grid lines + Y-axis labels */}
          {yTicks.map((t, i) => {
            const y = yOf(t);
            return (
              <g key={i}>
                <line x1={PAD.left} y1={y} x2={PAD.left + W} y2={y}
                  stroke="var(--border)" strokeWidth="1" strokeDasharray="2,4" />
                <text x={PAD.left + W + 6} y={y + 3}
                  fill="var(--muted)" fontSize="10" fontFamily="var(--font-mono)">
                  {currencySymbol}{t >= 1000 ? t.toFixed(0) : t.toFixed(2)}
                </text>
              </g>
            );
          })}

          {/* X-axis labels */}
          {xLabels.map((l, i) => (
            <text key={i} x={l.x} y={dims.h - 4}
              textAnchor="middle" fill="var(--muted)" fontSize="10" fontFamily="var(--font-mono)">
              {l.label}
            </text>
          ))}

          <g clipPath={`url(#${clipId})`}>
            {/* Line mode */}
            {chartType === "line" && n > 0 && (
              <>
                <path
                  d={`${linePath}L${xOf(n - 1).toFixed(1)},${(PAD.top + H).toFixed(1)}L${xOf(0).toFixed(1)},${(PAD.top + H).toFixed(1)}Z`}
                  fill={`url(#${lineGradId})`} />
                <path d={linePath} fill="none" stroke="var(--amber)" strokeWidth="1.5" />
              </>
            )}

            {/* Candle mode */}
            {chartType === "candle" && visibleData.map((d, i) => {
              const bull = d.close >= d.open;
              const color = bull ? "#00d97e" : "#f04438";
              const x = xOf(i);
              const bodyTop = yOf(Math.max(d.open, d.close));
              const bodyBot = yOf(Math.min(d.open, d.close));
              const bodyH = Math.max(1, bodyBot - bodyTop);
              const isHover = i === hoverIdx;
              return (
                <g key={i}>
                  <line x1={x} y1={yOf(d.high)} x2={x} y2={yOf(d.low)}
                    stroke={color} strokeWidth={candleW > 3 ? 1.2 : 1} opacity={isHover ? 1 : 0.8} />
                  <rect x={x - candleW / 2} y={bodyTop} width={candleW} height={bodyH}
                    fill={color} opacity={isHover ? 1 : bull ? 0.85 : 0.7}
                    stroke={isHover ? "#fff" : "none"} strokeWidth={isHover ? 0.8 : 0} />
                </g>
              );
            })}

            {/* SMA overlays */}
            {smaLines.map((sma, i) => (
              <path key={i} d={smaPath(sma.data)} fill="none"
                stroke={sma.color} strokeWidth="1.2"
                strokeDasharray={sma.dashed ? "4,3" : "none"} opacity="0.85" />
            ))}

            {/* Signal markers */}
            {signals.map((sig, i) => {
              if (sig.index < 0 || sig.index >= n) return null;
              const x = xOf(sig.index);
              const bar = visibleData[sig.index];
              const y = sig.type === "entry" ? yOf(bar.high) - 10 : yOf(bar.low) + 10;
              const color = sig.color || (sig.type === "entry" ? "#00d97e" : sig.type === "exit" ? "#f04438" : "#fbbf24");
              return (
                <g key={i}>
                  <line x1={x} y1={PAD.top} x2={x} y2={PAD.top + H}
                    stroke={color} strokeWidth="0.5" strokeDasharray="3,3" opacity="0.4" />
                  <polygon
                    points={sig.type === "entry"
                      ? `${x},${y + 8} ${x - 4},${y} ${x + 4},${y}`
                      : `${x},${y - 8} ${x - 4},${y} ${x + 4},${y}`}
                    fill={color} opacity="0.9" />
                  {sig.label && (
                    <text x={x} y={sig.type === "entry" ? y - 4 : y + 14}
                      textAnchor="middle" fill={color} fontSize="8"
                      fontFamily="var(--font-mono)" fontWeight="600">
                      {sig.label}
                    </text>
                  )}
                </g>
              );
            })}

            {/* Volume bars */}
            {showVolume && (
              <>
                <line x1={PAD.left} y1={volTop} x2={PAD.left + W} y2={volTop}
                  stroke="var(--border)" strokeWidth="1" />
                <text x={PAD.left + 4} y={volTop + 10}
                  fill="var(--muted)" fontSize="8" fontFamily="var(--font-mono)">VOLUME</text>
                <text x={PAD.left + W + 6} y={volTop + 10}
                  fill="var(--muted)" fontSize="8" fontFamily="var(--font-mono)">{fmtVol(volMax)}</text>
                {visibleData.map((d, i) => {
                  const barH = Math.max(1, (d.volume / volMax) * (VOL_H - 14));
                  const bull = d.close >= d.open;
                  const isHover = i === hoverIdx;
                  return (
                    <rect key={i} x={xOf(i) - candleW / 2} y={volTop + VOL_H - barH}
                      width={candleW} height={barH}
                      fill={bull ? "#00d97e" : "#f04438"} opacity={isHover ? 0.9 : 0.35} />
                  );
                })}
              </>
            )}

            {/* Crosshair */}
            {showCrosshair && hBar && (
              <>
                <line x1={xOf(hoverIdx)} y1={PAD.top} x2={xOf(hoverIdx)} y2={PAD.top + totalH}
                  stroke="var(--muted)" strokeWidth="0.5" strokeDasharray="3,3" />
                <line x1={PAD.left} y1={yOf(hBar.close)} x2={PAD.left + W} y2={yOf(hBar.close)}
                  stroke="var(--muted)" strokeWidth="0.5" strokeDasharray="3,3" />
                <rect x={PAD.left + W + 1} y={yOf(hBar.close) - 8} width={68} height={16}
                  fill="var(--amber)" rx="1" />
                <text x={PAD.left + W + 4} y={yOf(hBar.close) + 4}
                  fill="#fff" fontSize="10" fontFamily="var(--font-mono)" fontWeight="600">
                  {currencySymbol}{hBar.close.toFixed(2)}
                </text>
              </>
            )}

            {/* Current price line */}
            {n > 0 && (
              <line x1={PAD.left} y1={yOf(visibleData[n - 1].close)}
                x2={PAD.left + W} y2={yOf(visibleData[n - 1].close)}
                stroke={visibleData[n - 1].close >= visibleData[0].close ? "#00d97e" : "#f04438"}
                strokeWidth="0.8" strokeDasharray="4,4" opacity="0.6" />
            )}

            {/* ── Drawings ── */}
            {enableDrawingTools && drawings.map(dr =>
              renderDrawing(dr, visibleData, visibleStart, allData, xOf, yOf, PAD, H, W, pLo, pHi, dims, dr.id === selectedDrawingId, currencySymbol)
            )}

            {/* Anchor handles for the selected drawing (rendered above drawing lines) */}
            {enableDrawingTools && selectedDrawingId && !activeTool && (() => {
              const selDrawing = drawings.find(d => d.id === selectedDrawingId);
              if (!selDrawing) return null;
              const chartParams = { visibleData, visibleStart, allData, xOf, PAD, H, pLo, pHi };
              return renderAnchorHandles(selDrawing, chartParams);
            })()}

            {/* ── Drawing preview ── */}
            {enableDrawingTools && activeTool && pendingAnchors.length > 0 &&
              renderPreview(activeTool, pendingAnchors, previewPoint, visibleData, visibleStart, allData, xOf, yOf, PAD, H, W, pLo, pHi, dims, drawingStyle)
            }
          </g>
        </svg>

        {/* ── Drawing context toolbar (floating delete/deselect) ── */}
        {enableDrawingTools && selectedDrawingId && !activeTool && (
          <DrawingContextToolbar
            onDelete={() => {
              setDrawings(prev => prev.filter(d => d.id !== selectedDrawingId));
              setSelectedDrawingId(null);
            }}
            onDeselect={() => setSelectedDrawingId(null)}
          />
        )}

        {/* Hover tooltip */}
        {showCrosshair && hBar && (
          <div style={{
            position: "absolute", top: 8, left: PAD.left + 4,
            background: "rgba(17,21,32,0.92)", border: "1px solid var(--border)",
            borderRadius: 3, padding: "6px 10px",
            fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text)",
            pointerEvents: "none", zIndex: 10, lineHeight: "16px",
          }}>
            <div style={{ color: "var(--muted)", marginBottom: 2 }}>{hBar.date}</div>
            <div>
              O <span style={{ color: "var(--bright)" }}>{currencySymbol}{hBar.open.toFixed(2)}</span>{" "}
              H <span style={{ color: "var(--bright)" }}>{currencySymbol}{hBar.high.toFixed(2)}</span>{" "}
              L <span style={{ color: "var(--bright)" }}>{currencySymbol}{hBar.low.toFixed(2)}</span>{" "}
              C <span style={{ color: hBar.close >= hBar.open ? "var(--green)" : "var(--red)" }}>{currencySymbol}{hBar.close.toFixed(2)}</span>
            </div>
            {showVolume && (
              <div style={{ color: "var(--muted)" }}>Vol {fmtVol(hBar.volume)}</div>
            )}
            {smaLines.map(sma =>
              sma.data[hoverIdx]?.value && (
                <div key={sma.period} style={{ color: sma.color }}>
                  SMA{sma.period} {currencySymbol}{sma.data[hoverIdx].value.toFixed(2)}
                </div>
              )
            )}
          </div>
        )}
      </div>
    </div>
  );
}
