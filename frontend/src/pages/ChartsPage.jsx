/**
 * Charts Page
 * 
 * Advanced charting page with OHLCV data, technical analysis, and symbol search.
 */

import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import api from "../api/client";
import { Ic } from "../components/common/Icons";
import { useMarketStatus } from "../components/common";
import { useI18n } from "../context/I18nContext";
import { useCurrency } from "../context/CurrencyContext";
import AssetDetailPanel from "../components/common/AssetDetailPanel";
import AlertModal from "../components/common/AlertModal";
import {
  DRAWING_TOOLS_BASE, DEFAULT_DRAW_STYLE, genDrawingId,
  pixelToAnchor as pixelToAnchorFn, hitTestDrawing as hitTestDrawingFn,
  renderDrawing, renderPreview, DrawingContextToolbar,
  renderAnchorHandles, moveDrawingAnchors, moveOneAnchor,
  resolveAnchorX, resolveAnchorY,
} from "../components/charts/DrawingTools.jsx";

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

/* ─── INTERVAL CONFIG ──────────────────────────────────────────────────────── */
const INTERVAL_DAYS = {
  "1m": 7, "2m": 60, "3m": 7, "5m": 60, "10m": 60,
  "15m": 60, "30m": 60, "45m": 60, "1h": 365, "2h": 365,
  "3h": 365, "4h": 365, "1d": 1825, "1wk": 3650,
  "1mo": 3650, "3mo": 3650, "6mo": 3650, "12mo": 3650,
};
const INTRADAY_INTERVALS = new Set(["1m","2m","3m","5m","10m","15m","30m","45m","1h","2h","3h","4h"]);

/* Drawing tools config, coordinate helpers, renderers, and hit-testing are
   imported from ../components/charts/DrawingTools.jsx (shared with OHLCVChart). */



/* ─── CHART COMPONENT ───────────────────────────────────────────────────────── */
function StockChart({ symbol, stockInfo, onClose, token }) {
  const { t } = useI18n();
  const { formatValue, currencySymbol } = useCurrency();

  /* Build translated DRAWING_TOOLS from the base config */
  const DRAWING_TOOLS = useMemo(() => {
    const tools = {};
    for (const [key, def] of Object.entries(DRAWING_TOOLS_BASE)) {
      tools[key] = { ...def, label: t(def.labelKey) };
    }
    return tools;
  }, [t]);

  const svgRef = useRef(null);
  const containerRef = useRef(null);
  const wrapRef = useRef(null);
  const dragRef = useRef(null);

  const [dims, setDims] = useState({ w: 900, h: 420 });
  const [crosshair, setCrosshair] = useState(null);
  const [tooltip, setTooltip] = useState(null);
  const [period, setPeriod] = useState("1Y");
  const [overlays, setOverlays] = useState({ sma50: true, sma150: true, smaCustom: true, volume: true, breakouts: true, events: true });
  const [customPeriod, setCustomPeriod] = useState(20);
  const [chartType, setChartType] = useState("candle");
  const [interval, setIntervalState] = useState("1d");
  const [dataWarning, setDataWarning] = useState(null);
  const [showIntervalPicker, setShowIntervalPicker] = useState(false);
  const isIntraday = INTRADAY_INTERVALS.has(interval);
  // Zoom/pan state: offset = index offset from right, zoom = candles visible
  const [zoom, setZoom] = useState(null); // null = use period preset

  /* ── Hover data toggle (session-persistent) ────────────────────────────── */
  const [showHoverData, setShowHoverData] = useState(() =>
    sessionStorage.getItem("tt_showHoverData") !== "0"
  );
  const toggleHoverData = useCallback(() => {
    setShowHoverData(prev => {
      const next = !prev;
      sessionStorage.setItem("tt_showHoverData", next ? "1" : "0");
      return next;
    });
  }, []);

  /* ── Purchase points from portfolio positions ──────────────────────────── */
  const [purchasePoints, setPurchasePoints] = useState([]);
  useEffect(() => {
    if (!token || !symbol) return;
    let cancelled = false;
    (async () => {
      try {
        const portfolios = await api.listPortfolios(token);
        if (cancelled || !portfolios?.length) return;
        const allPos = await Promise.all(
          portfolios.map(p => api.listPositions(p.portfolio_id, token).catch(() => []))
        );
        const points = allPos.flat()
          .filter(pos => pos.ticker === symbol && pos.purchase_date)
          .map(pos => ({
            date: pos.purchase_date?.slice(0, 10),
            price: parseFloat(pos.purchase_price),
            qty: parseFloat(pos.quantity),
          }));
        if (!cancelled) setPurchasePoints(points);
      } catch {
        /* silent */
      }
    })();
    return () => { cancelled = true; };
  }, [token, symbol]);

  /* ── Events data (earnings, dividends, splits) from backend ───────────── */
  const [eventsData, setEventsData] = useState([]);
  useEffect(() => {
    if (!token || !symbol) return;
    let cancelled = false;
    api.getEvents(symbol, token)
      .then(resp => {
        if (!cancelled && resp?.events) setEventsData(resp.events);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [token, symbol]);

  /**
   * Build a lookup map of event dates → event arrays for O(1) matching
   * against visible bars.  Key is the date portion "YYYY-MM-DD".
   */
  const eventsByDate = useMemo(() => {
    const map = {};
    for (const ev of eventsData) {
      const key = ev.date?.slice(0, 10);
      if (!key) continue;
      if (!map[key]) map[key] = [];
      map[key].push(ev);
    }
    return map;
  }, [eventsData]);

  // Fetch OHLCV from backend; fall back to local generation if backend offline
  const [allData, setAllData] = useState(() => generateOHLCV(stockInfo.price, 5));
  const [dataLoading, setDataLoading] = useState(false);
  const [volumeSource, setVolumeSource] = useState(null); // e.g. "GLD" when ETF volume is used

  useEffect(() => {
    let cancelled = false;
    setDataLoading(true);
    setVolumeSource(null);
    setDataWarning(null);
    if (!token) {
      setAllData(generateOHLCV(stockInfo.price, 5));
      setDataLoading(false);
      return;
    }
    const days = INTERVAL_DAYS[interval] || 1825;
    api.getOhlcvInterval(symbol, token, interval, days)
      .then(resp => {
        if (!cancelled) {
          const bars = resp.bars || resp;
          setVolumeSource(resp.volume_source || null);
          setDataWarning(resp.warning || null);
          setAllData(bars.map(b => ({
            date: b.date, open: b.open, high: b.high, low: b.low,
            close: b.close, volume: b.volume, isEarnings: b.is_earnings || false,
          })));
        }
      })
      .catch(() => {
        if (!cancelled) setAllData(generateOHLCV(stockInfo.price, 5));
      })
      .finally(() => { if (!cancelled) setDataLoading(false); });
    return () => { cancelled = true; };
  }, [symbol, token, interval]);

  const PERIODS = isIntraday
    ? { "100": 100, "500": 500, "1000": 1000, "ALL": 9999 }
    : { "1M": 21, "3M": 63, "6M": 126, "1Y": 252, "2Y": 504, "5Y": 1260, "ALL": 9999 };

  // Reset period when switching between intraday/daily
  useEffect(() => {
    if (isIntraday && !["100","500","1000","ALL"].includes(period)) {
      setPeriod("ALL");
    } else if (!isIntraday && !["1M","3M","6M","1Y","2Y","5Y","ALL"].includes(period)) {
      setPeriod("1Y");
    }
    setZoom(null);
  }, [isIntraday]); // eslint-disable-line

  // Visible slice — respects period preset OR manual zoom
  // totalSlots includes future empty slots when panned past data end
  const { visibleData, visibleStart, totalSlots } = useMemo(() => {
    let start, count;
    if (zoom) {
      start = Math.max(0, zoom.start);
      count = Math.max(10, zoom.count);
    } else {
      count = Math.min(PERIODS[period] || 252, allData.length);
      start = allData.length - count;
    }
    const data = allData.slice(start, start + count);
    return { visibleData: data, visibleStart: start, totalSlots: count };
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
  /* Use totalSlots (data + future) for spacing so future zone has proper candle-width slots */
  const candleGap = totalSlots > 0 ? W / totalSlots : 1;
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
    let lastDay = null;
    const maxLabels = Math.floor(W / 80);
    const step = Math.max(1, Math.floor(n / maxLabels));
    for (let i = 0; i < n; i += step) {
      const d = new Date(visibleData[i].date);
      if (isIntraday) {
        const dayStr = d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
        const timeStr = d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
        const lbl = dayStr !== lastDay ? `${dayStr} ${timeStr}` : timeStr;
        labels.push({ x: xOf(i), label: lbl });
        lastDay = dayStr;
      } else {
        const mo  = d.toLocaleString("en-US", { month: "short" });
        const yr  = d.getFullYear();
        const lbl = yr !== lastYear ? `${mo} '${String(yr).slice(2)}` : mo;
        labels.push({ x: xOf(i), label: lbl });
        lastYear = yr;
      }
    }
    return labels;
  }, [visibleData, n, W, isIntraday]);

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

  // ── Drawing tools state ──────────────────────────────────────────────────
  const [drawings, setDrawings] = useState([]);
  const [activeTool, setActiveTool] = useState(null);      // null | "trendLine" | "horizontalLine" | ...
  const [pendingAnchors, setPendingAnchors] = useState([]); // anchors placed so far for current drawing
  const [previewPoint, setPreviewPoint] = useState(null);   // mouse position as {time, price} during drawing
  const [selectedDrawingId, setSelectedDrawingId] = useState(null);
  const [drawingStyle, setDrawingStyle] = useState({ ...DEFAULT_DRAW_STYLE });
  const [textInput, setTextInput] = useState("");
  const drawSaveTimerRef = useRef(null);

  /* ── Draw interaction state (move/resize drawings) ──────────────────── */
  const [drawInteraction, setDrawInteraction] = useState("idle"); // "idle" | "moving" | "resizing"
  const drawDragStartRef = useRef(null);   // { x, y, anchors: [...] } — captured at drag start
  const drawDragAnchorRef = useRef(null);  // anchor index being resized, null during move

  // ── Template state ──────────────────────────────────────────────────────
  const [templates, setTemplates] = useState([]);
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [showLoadDropdown, setShowLoadDropdown] = useState(false);
  const [templateName, setTemplateName] = useState("");
  const [templateSaving, setTemplateSaving] = useState(false);

  // Fetch templates from backend on mount
  useEffect(() => {
    if (!token) return;
    api.listChartTemplates(token)
      .then(list => setTemplates(list))
      .catch(() => {});
  }, [token]);

  // Save template handler
  const handleSaveTemplate = async () => {
    if (!templateName.trim() || !token) return;
    setTemplateSaving(true);
    try {
      const payload = {
        name: templateName.trim(),
        symbol: symbol || null,
        interval: interval || null,
        drawings_json: drawings,
        overlays_json: overlays,
      };
      const created = await api.createChartTemplate(payload, token);
      setTemplates(prev => [created, ...prev]);
      setShowSaveModal(false);
      setTemplateName("");
    } catch {}
    setTemplateSaving(false);
  };

  // Load template handler
  const handleLoadTemplate = (tpl) => {
    if (tpl.drawings_json) setDrawings(tpl.drawings_json);
    if (tpl.overlays_json) setOverlays(tpl.overlays_json);
    setShowLoadDropdown(false);
    setSelectedDrawingId(null);
  };

  // Delete template handler
  const handleDeleteTemplate = async (e, templateId) => {
    e.stopPropagation();
    if (!token) return;
    try {
      await api.deleteChartTemplate(templateId, token);
      setTemplates(prev => prev.filter(t => t.template_id !== templateId));
    } catch {}
  };

  // Load drawings from localStorage on mount / symbol change
  useEffect(() => {
    try {
      const stored = localStorage.getItem(`tt_drawings_${symbol}`);
      if (stored) setDrawings(JSON.parse(stored));
      else setDrawings([]);
    } catch { setDrawings([]); }
  }, [symbol]);

  // Save drawings to localStorage (debounced)
  useEffect(() => {
    clearTimeout(drawSaveTimerRef.current);
    drawSaveTimerRef.current = setTimeout(() => {
      try { localStorage.setItem(`tt_drawings_${symbol}`, JSON.stringify(drawings)); } catch {}
    }, 500);
    return () => clearTimeout(drawSaveTimerRef.current);
  }, [drawings, symbol]);

  // Cancel drawing on Escape, delete selected on Delete/Backspace
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") {
        if (activeTool) { setActiveTool(null); setPendingAnchors([]); setPreviewPoint(null); }
        else setSelectedDrawingId(null);
      }
      if ((e.key === "Delete" || e.key === "Backspace") && selectedDrawingId && !activeTool) {
        // Don't delete if user is typing in an input
        if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
        setDrawings(prev => prev.filter(d => d.id !== selectedDrawingId));
        setSelectedDrawingId(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [activeTool, selectedDrawingId]);

  // Convert pixel position to {time, price} anchor (delegates to shared module)
  const pixelToAnchor = useCallback((mx, my) => {
    return pixelToAnchorFn(mx, my, visibleData, n, PAD, candleGap, H, pLo, pHi);
  }, [visibleData, n, PAD, candleGap, H, pLo, pHi]);

  // Hit-test: find drawing near pixel (mx, my) (delegates to shared module)
  const hitTestDrawing = useCallback((mx, my) => {
    return hitTestDrawingFn(drawings, mx, my, visibleData, visibleStart, allData, xOf, PAD, H, W, pLo, pHi);
  }, [drawings, visibleData, visibleStart, allData, xOf, PAD, H, W, pLo, pHi]);

  // ── Mouse handlers ────────────────────────────────────────────────────────
  const handleMouseMove = useCallback((e) => {
    const svg = svgRef.current;
    if (!svg) return;
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

    // Drawing mode: update preview point
    if (activeTool && pendingAnchors.length >= 0) {
      const anchor = pixelToAnchor(mx, my);
      if (anchor) setPreviewPoint(anchor);
    }

    // Drag-to-pan (only when not drawing)
    if (dragRef.current) {
      const dx = mx - dragRef.current.startX;
      const candleShift = Math.round(-dx / candleGap);
      const base = dragRef.current.baseStart;
      const baseCount = dragRef.current.baseCount;
      /* Allow panning up to 25% past data end into future zone */
      const maxFuture = Math.max(10, Math.round(baseCount * 0.25));
      const newStart = Math.max(0, Math.min(allData.length - baseCount + maxFuture, base + candleShift));
      setZoom({ start: newStart, count: baseCount });
      return;
    }

    const idx     = Math.round((mx - PAD.left - candleGap / 2) / candleGap);

    /* Future zone — past last data bar: show crosshair line but no tooltip */
    if (idx >= n) {
      const priceCross = pLo + ((PAD.top + H - my) / H) * (pHi - pLo);
      setCrosshair({ x: xOf(Math.min(idx, totalSlots - 1)), y: my, idx: -1, priceCross });
      setTooltip(null);
      return;
    }

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

    /* ── Cursor hint: show "move" when hovering body of selected drawing ── */
    if (selectedDrawingId && !activeTool && drawInteraction === "idle") {
      const hitId = hitTestDrawing(mx, my);
      if (hitId === selectedDrawingId && containerRef.current) {
        containerRef.current.style.cursor = "move";
      } else if (containerRef.current) {
        containerRef.current.style.cursor = "crosshair";
      }
    }
  }, [visibleData, sma50, sma150, smaCustom, n, totalSlots, W, H, pLo, pHi, candleGap, allData.length,
      activeTool, pendingAnchors, pixelToAnchor, drawInteraction, selectedDrawingId, drawings,
      visibleStart, allData, xOf, PAD, hitTestDrawing]);

  const handleMouseDown = useCallback((e) => {
    if (e.button !== 0) return;
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    // Drawing mode: place anchor
    if (activeTool) {
      const anchor = pixelToAnchor(mx, my);
      if (!anchor) return;
      e.preventDefault();
      e.stopPropagation();

      const toolDef = DRAWING_TOOLS[activeTool];
      const newAnchors = [...pendingAnchors, anchor];

      if (newAnchors.length >= toolDef.anchors) {
        // Drawing is complete — commit it
        const style = { ...drawingStyle };
        if (activeTool === "text") style.text = textInput || "Text";
        setDrawings(prev => [...prev, {
          id: genDrawingId(),
          type: activeTool,
          anchors: newAnchors,
          style,
          visible: true,
          locked: false,
          createdAt: new Date().toISOString(),
        }]);
        setPendingAnchors([]);
        setPreviewPoint(null);
        // Keep tool active for rapid successive drawings (click trendLine multiple times)
      } else {
        setPendingAnchors(newAnchors);
      }
      return;
    }

    /* ── Anchor-handle hit-test: start resizing if click lands on a handle ── */
    if (selectedDrawingId && !activeTool) {
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

    // Hit-test drawings for selection or body-drag
    const hitId = hitTestDrawing(mx, my);

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
    if (hitId) {
      setSelectedDrawingId(hitId);
      e.preventDefault();
      return;
    }
    setSelectedDrawingId(null);

    // Default: drag-to-pan
    const cur = zoom || { start: visibleStart, count: visibleData.length };
    dragRef.current = { startX: mx, baseStart: cur.start, baseCount: cur.count };
    e.preventDefault();
  }, [zoom, visibleStart, visibleData.length, activeTool, pendingAnchors, drawingStyle, textInput,
      pixelToAnchor, hitTestDrawing, selectedDrawingId, drawings, visibleData, allData, xOf, PAD, H, pLo, pHi, W, n, candleGap]);

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
    setCrosshair(null);
    setTooltip(null);
    if (activeTool) setPreviewPoint(null);
    /* Reset cursor override */
    if (containerRef.current) containerRef.current.style.cursor = "crosshair";
  }, [drawInteraction, activeTool]);

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
    /* Allow zooming to preserve position when panned into future zone */
    const maxFuture = Math.max(10, Math.round(newCount * 0.25));
    const newStart = Math.max(0, Math.min(allData.length - newCount + maxFuture, Math.round(pivot - newCount * ratio)));

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
    { key: "events",    label: t("charts.events"),      color: "#e879f9" },
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
          <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: 10, fontWeight: 600, color: "#0f7d40", background: "rgba(15,125,64,0.1)", border: "1px solid rgba(15,125,64,0.2)", padding: "2px 8px", borderRadius: 2, letterSpacing: "0.8px" }}>
            {interval.toUpperCase()}
          </div>
          {dataLoading && <span className="loading-pulse" style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: 10, color: "#4a5568" }}>{t("charts.loading")}</span>}
          {onClose && (
            <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: "#4a5568", padding: 4 }}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M18 6L6 18M6 6l12 12"/></svg>
            </button>
          )}
        </div>

        <div className="stat-sep" />

        {/* OPEN */}
        <div className="stock-stat">
          <div className="ss-label">{t("charts.open")}</div>
          <div className="ss-value">{currencySymbol}{last.open?.toFixed(2) ?? "—"}</div>
          <div className="ss-sub">{t("dashboard.today")}</div>
        </div>

        <div className="stat-sep" />

        {/* CLOSE */}
        <div className="stock-stat">
          <div className="ss-label">{t("charts.close")}</div>
          <div className="ss-value amber">{currencySymbol}{last.close?.toFixed(2) ?? "—"}</div>
          <div className="ss-sub">{t("charts.lastPrice")}</div>
        </div>

        <div className="stat-sep" />

        {/* VOLUME TODAY */}
        <div className="stock-stat">
          <div className="ss-label">{t("charts.volumeToday")}</div>
          <div className="ss-value" style={{ fontSize: 16 }}>{fmtVol(last.volume ?? 0)}</div>
          <div className="ss-sub">AVG: {fmtVol(Math.round(visibleData.slice(-20).reduce((s, d) => s + d.volume, 0) / Math.max(1, visibleData.slice(-20).length)))}</div>
        </div>

        <div className="stat-sep" />

        {/* GAIN TODAY */}
        <div className="stock-stat">
          <div className="ss-label">{t("charts.gainToday")}</div>
          <div className={`ss-value ${dayGain >= 0 ? "pos" : "neg"}`} style={{ fontSize: 20 }}>
            {dayGain >= 0 ? "+" : ""}{currencySymbol}{Math.abs(dayGain).toFixed(2)}
          </div>
          <div className={`ss-badge ${dayGain >= 0 ? "pos" : "neg"}`} style={{ marginTop: 3 }}>
            {dayGainPct >= 0 ? "▲" : "▼"} {Math.abs(dayGainPct).toFixed(2)}%
          </div>
        </div>

        <div className="stat-sep" />

        {/* HIGH / LOW */}
        <div className="stock-stat">
          <div className="ss-label">{t("charts.highLow")}</div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span className="ss-value" style={{ color: "#00d97e", fontSize: 15 }}>{currencySymbol}{last.high?.toFixed(2) ?? "—"}</span>
            <span style={{ color: "#1e2535", fontFamily: "var(--font-mono)", fontSize: 11 }}>·</span>
            <span className="ss-value" style={{ color: "#f04438", fontSize: 15 }}>{currencySymbol}{last.low?.toFixed(2)  ?? "—"}</span>
          </div>
          <div className="ss-sub">{t("charts.intradayRange")}</div>
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
              <div className="ss-label">{t("charts.weekRange")}</div>
              <div style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 4 }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "#718096" }}>{currencySymbol}{lo52.toFixed(0)}</span>
                <div style={{ flex: 1, height: 4, background: "#1e2535", borderRadius: 2, position: "relative" }}>
                  <div style={{ position: "absolute", left: 0, top: 0, height: "100%", width: `${Math.min(100, Math.max(0, pos52))}%`, background: "var(--amber)", borderRadius: 2 }} />
                </div>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "#718096" }}>{currencySymbol}{hi52.toFixed(0)}</span>
              </div>
              <div className="ss-sub">{pos52.toFixed(0)}% {t("charts.from52wLow")}</div>
            </div>
          );
        })()}

        {/* Spacer */}
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "#4a5568", textAlign: "right" }}>
            <div style={{ letterSpacing: "0.5px" }}>{t("charts.scrollZoom")}</div>
            <div style={{ color: "#263045" }}>{t("charts.dragPan")}</div>
          </div>
        </div>
      </div>

      {/* ── CONTROLS ── */}
      <div className="chart-controls">
        <span className="ctrl-label">{t("charts.interval")}</span>
        <div className="ctrl-group">
          {["1m","5m","15m","1h","4h","1d","1wk","1mo"].map(iv => (
            <button key={iv} className={`ctrl-btn${interval===iv ? " active" : ""}`}
              onClick={() => { setIntervalState(iv); setZoom(null); }}>{iv.toUpperCase()}</button>
          ))}
          <button className={`ctrl-btn${showIntervalPicker ? " active" : ""}`}
            onClick={() => setShowIntervalPicker(v => !v)}
            style={{ fontSize: 11, letterSpacing: 0 }}>···</button>
        </div>
        <div className="ctrl-sep" />
        <span className="ctrl-label">{t("charts.range")}</span>
        <div className="ctrl-group">
          {Object.keys(PERIODS).map(p => (
            <button key={p} className={`ctrl-btn${!zoom && period===p ? " active" : ""}`} onClick={() => handlePeriod(p)}>{p}</button>
          ))}
        </div>
        <div className="ctrl-sep" />
        <span className="ctrl-label">{t("charts.type")}</span>
        <div className="ctrl-group">
          {[["candle", t("charts.candle")],["line", t("charts.line")]].map(([v,l]) => (
            <button key={v} className={`ctrl-btn${chartType===v ? " active" : ""}`} onClick={() => setChartType(v)}>{l}</button>
          ))}
        </div>
        <div className="ctrl-sep" />
        <span className="ctrl-label">{t("charts.overlays")}</span>
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
        <div className="ctrl-sep" />
        <div className="overlay-toggle" style={showHoverData ? { borderColor: "rgba(255,178,56,0.3)", color: "var(--amber)" } : {}}
          onClick={toggleHoverData}>
          <Ic.eye /> {t("charts.hoverData")}
        </div>
        {zoom && (
          <button className="ctrl-btn active" style={{ marginLeft: "auto", borderLeft: "1px solid #1e2535" }}
            onClick={() => setZoom(null)}>✕ {t("charts.reset")}</button>
        )}
      </div>

      {/* ── INTERVAL PICKER EXPANDED ── */}
      {showIntervalPicker && (
        <div style={{
          background: "#0e1117", borderBottom: "1px solid #1e2535",
          padding: "10px 24px", display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", flexShrink: 0,
        }}>
          <span className="ctrl-label" style={{ minWidth: 55 }}>{t("charts.minutes")}</span>
          <div className="ctrl-group">
            {["1m","2m","3m","5m","10m","15m","30m","45m"].map(iv => (
              <button key={iv} className={`ctrl-btn${interval===iv ? " active" : ""}`}
                onClick={() => { setIntervalState(iv); setZoom(null); setShowIntervalPicker(false); }}>{iv}</button>
            ))}
          </div>
          <div className="ctrl-sep" />
          <span className="ctrl-label" style={{ minWidth: 40 }}>{t("charts.hours")}</span>
          <div className="ctrl-group">
            {["1h","2h","3h","4h"].map(iv => (
              <button key={iv} className={`ctrl-btn${interval===iv ? " active" : ""}`}
                onClick={() => { setIntervalState(iv); setZoom(null); setShowIntervalPicker(false); }}>{iv}</button>
            ))}
          </div>
          <div className="ctrl-sep" />
          <span className="ctrl-label" style={{ minWidth: 40 }}>{t("charts.dwm")}</span>
          <div className="ctrl-group">
            {["1d","1wk","1mo","3mo","6mo","12mo"].map(iv => (
              <button key={iv} className={`ctrl-btn${interval===iv ? " active" : ""}`}
                onClick={() => { setIntervalState(iv); setZoom(null); setShowIntervalPicker(false); }}>{iv}</button>
            ))}
          </div>
        </div>
      )}

      {/* ── DATA WARNING ── */}
      {dataWarning && (
        <div style={{
          background: "rgba(255,191,0,.06)", borderBottom: "1px solid rgba(255,191,0,.18)",
          padding: "5px 24px", fontFamily: "'IBM Plex Mono',monospace", fontSize: 10,
          color: "#d4a017", letterSpacing: "0.5px", flexShrink: 0,
        }}>
          ⚠ {dataWarning}
        </div>
      )}

      {/* ── CHART BODY — single SVG with price + volume ── */}
      <div ref={wrapRef} style={{ flex: 1, overflow: "hidden", minHeight: 0, position: "relative" }}
        onMouseMove={handleMouseMove}
        onMouseDown={handleMouseDown}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseLeave}
      >
        {/* ── CHART SVG (price + volume) ── */}
        <div ref={containerRef} style={{ width: "100%", height: "100%", position: "relative", background: "#090b0f", cursor: drawInteraction === "moving" ? "move" : "crosshair" }}>
          {/* Legend overlay */}
          <div className="chart-legend">
            {overlays.sma50     && <div className="legend-item"><div className="legend-line" style={{ background: "#3d7ef5" }}/>SMA50</div>}
            {overlays.sma150    && <div className="legend-item"><div className="legend-line" style={{ background: "#0fc0d0" }}/>SMA150</div>}
            {overlays.smaCustom && <div className="legend-item"><div className="legend-line" style={{ background: "#a78bfa" }}/>SMA{customPeriod}</div>}
            {overlays.breakouts && <div className="legend-item"><div style={{ width: 8, height: 8, background: "#00d97e", clipPath: "polygon(50% 0,100% 100%,0 100%)", flexShrink: 0 }}/>{t("charts.breakout")}</div>}
            {overlays.events && <div className="legend-item"><div style={{ width: 8, height: 8, background: "#e879f9", borderRadius: 1, flexShrink: 0 }}/>{t("charts.events")}</div>}
          </div>

          {/* ── DRAWING TOOLBAR ── */}
          <div className="draw-toolbar">
            {/* Select / cursor mode */}
            <button className={`draw-tool-btn${!activeTool ? " active" : ""}`}
              title="Select (ESC)"
              onClick={() => { setActiveTool(null); setPendingAnchors([]); setPreviewPoint(null); }}>
              <Ic.cursor />
            </button>

            <div className="draw-toolbar-sep" />

            {/* Tool buttons */}
            {Object.entries(DRAWING_TOOLS).map(([key, def]) => {
              const IconComp = Ic[def.icon];
              return (
              <button key={key}
                className={`draw-tool-btn${activeTool === key ? " active" : ""}`}
                title={`${def.label} (${def.anchors} click${def.anchors > 1 ? "s" : ""})`}
                onClick={() => {
                  setActiveTool(activeTool === key ? null : key);
                  setPendingAnchors([]);
                  setPreviewPoint(null);
                  setSelectedDrawingId(null);
                }}>
                <IconComp />
              </button>
              );
            })}

            <div className="draw-toolbar-sep" />

            {/* Color picker */}
            <div className="draw-color-wrap" title="Drawing color">
              <div className="draw-color-swatch" style={{ background: drawingStyle.color }} />
              <input type="color" className="draw-color-input"
                value={drawingStyle.color}
                onChange={e => setDrawingStyle(s => ({ ...s, color: e.target.value }))} />
            </div>

            {/* Line style */}
            {["solid", "dashed", "dotted"].map(ls => (
              <button key={ls}
                className={`draw-tool-btn mini${drawingStyle.lineStyle === ls ? " active" : ""}`}
                title={ls}
                onClick={() => setDrawingStyle(s => ({ ...s, lineStyle: ls }))}>
                <svg width="14" height="6" viewBox="0 0 14 6">
                  <line x1="0" y1="3" x2="14" y2="3" stroke="currentColor" strokeWidth="1.5"
                    strokeDasharray={ls === "dashed" ? "4,3" : ls === "dotted" ? "1.5,2" : "none"} />
                </svg>
              </button>
            ))}

            <div className="draw-toolbar-sep" />

            {/* Text input (visible when text tool active) */}
            {activeTool === "text" && (
              <input className="draw-text-input"
                placeholder="Label..."
                value={textInput}
                onChange={e => setTextInput(e.target.value)}
                onClick={e => e.stopPropagation()}
                onMouseDown={e => e.stopPropagation()}
                autoFocus
              />
            )}

            {/* Clear all drawings */}
            <button className="draw-tool-btn danger"
              title="Clear all drawings"
              onClick={() => { setDrawings([]); setSelectedDrawingId(null); }}>
              <Ic.eraser />
            </button>

            <div className="draw-toolbar-sep" />

            {/* Save template */}
            <button className="draw-tool-btn"
              title="Save template"
              onClick={() => { setShowSaveModal(true); setShowLoadDropdown(false); }}>
              <Ic.save />
            </button>

            {/* Load template */}
            <div style={{ position: "relative" }}>
              <button className={`draw-tool-btn${showLoadDropdown ? " active" : ""}`}
                title="Load template"
                onClick={() => { setShowLoadDropdown(v => !v); setShowSaveModal(false); }}>
                <Ic.folder />
              </button>
              {showLoadDropdown && (
                <div className="tpl-dropdown">
                  <div className="tpl-dropdown-header">{t("charts.templates")}</div>
                  {templates.length === 0 && (
                    <div className="tpl-dropdown-empty">{t("charts.noTemplates")}</div>
                  )}
                  {templates.map(tpl => (
                    <div key={tpl.template_id} className="tpl-dropdown-item"
                      onClick={() => handleLoadTemplate(tpl)}>
                      <div className="tpl-item-name">{tpl.name}</div>
                      <div className="tpl-item-meta">
                        {tpl.symbol || "ALL"} · {tpl.drawings_json?.length || 0} drawings
                      </div>
                      <button className="tpl-item-del"
                        onClick={e => handleDeleteTemplate(e, tpl.template_id)}
                        title="Delete template">
                        <Ic.close />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Drawing count */}
            {drawings.length > 0 && (
              <div className="draw-count">{drawings.length}</div>
            )}

            {/* Active tool indicator */}
            {activeTool && (
              <div className="draw-active-label">
                {DRAWING_TOOLS[activeTool].label}
                {pendingAnchors.length > 0 && (
                  <span className="draw-anchor-count">
                    {pendingAnchors.length}/{DRAWING_TOOLS[activeTool].anchors}
                  </span>
                )}
              </div>
            )}
            {selectedDrawingId && !activeTool && (
              <div className="draw-active-label" style={{ color: "#f04438" }}>
                {t("charts.selectedDel")}
              </div>
            )}
          </div>

          {/* Date range info */}
          <div style={{ position: "absolute", bottom: 18, left: 46, fontFamily: "var(--font-mono)", fontSize: 9, color: "#263045", pointerEvents: "none", zIndex: 2 }}>
            {visibleData[0]?.date && visibleData[n-1]?.date ? `${visibleData[0].date} → ${visibleData[n-1].date}  ·  ${n} ${t("charts.sessions")}` : ""}
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
            {yTicks.map((tick, i) => {
              const y = yOf(tick);
              if (y < PAD.top || y > PAD.top + H) return null;
              return (
                <g key={i}>
                  <line x1={PAD.left} y1={y} x2={dims.w - PAD.right} y2={y}
                    stroke="#1a2030" strokeWidth="1" strokeDasharray="2,5" />
                  <text x={dims.w - PAD.right + 5} y={y + 3.5}
                    fontFamily="IBM Plex Mono" fontSize="10" fill="#4a5568">
                    {tick >= 1000 ? `${currencySymbol}${(tick/1000).toFixed(1)}K` : tick >= 100 ? `${currencySymbol}${tick.toFixed(0)}` : `${currencySymbol}${tick.toFixed(2)}`}
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
                      {d.isEarnings && !overlays.events && <circle cx={x} cy={bodyTop - 5} r={3} fill="#0f7d40" opacity="0.9" />}
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
                    const lbl = b.label || (b.type === "bull" ? `${t("charts.breakout")} ▲` : `${t("charts.breakdown")} ▼`);
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

            {/* ── PURCHASE POINT INDICATORS ── */}
            {(() => {
              if (!purchasePoints.length || !visibleData.length) return null;

              /* Pre-compute timestamps for each visible bar for efficient lookup */
              const barTimestamps = visibleData.map(bar => new Date(bar.date).getTime());

              /* Maximum time gap allowed: 7 days in milliseconds */
              const MAX_GAP_MS = 7 * 24 * 60 * 60 * 1000;

              /**
               * For each purchase point, find the closest matching bar index
               * in visibleData based on smallest absolute time difference.
               * Groups purchase points that map to the same bar index.
               *
               * matchMap: { barIndex -> [{ price, qty }] }
               */
              const matchMap = {};
              for (const pp of purchasePoints) {
                const ppTime = new Date(pp.date).getTime();
                let bestIdx = -1;
                let bestDiff = Infinity;
                for (let i = 0; i < barTimestamps.length; i++) {
                  const diff = Math.abs(barTimestamps[i] - ppTime);
                  if (diff < bestDiff) {
                    bestDiff = diff;
                    bestIdx = i;
                  }
                }
                /* Skip if no bar within 7-day range */
                if (bestIdx < 0 || bestDiff > MAX_GAP_MS) continue;

                /* If the purchase date is date-only (no "T"), verify the bar's
                   OHLC range includes the purchase price for better Y alignment */
                const isDateOnly = !pp.date.includes("T");
                if (isDateOnly) {
                  const bar = visibleData[bestIdx];
                  if (bar.low != null && bar.high != null) {
                    if (pp.price < bar.low || pp.price > bar.high) {
                      /* Price outside bar range — still show at nearest bar,
                         the weighted average will adjust the Y position */
                    }
                  }
                }

                if (!matchMap[bestIdx]) matchMap[bestIdx] = [];
                matchMap[bestIdx].push({ price: pp.price, qty: pp.qty });
              }

              /* Render diamond markers for each matched bar index */
              return Object.entries(matchMap).map(([viStr, matches]) => {
                const vi = parseInt(viStr, 10);
                const totalQty = matches.reduce((s, m) => s + m.qty, 0);
                const avgPrice = matches.reduce((s, m) => s + m.price * m.qty, 0) / totalQty;
                const px = xOf(vi);
                const py = yOf(avgPrice);
                return (
                  <g key={`pp-${vi}`} clipPath="url(#chartClip)">
                    {/* Diamond marker */}
                    <polygon
                      points={`${px},${py-7} ${px+5},${py} ${px},${py+7} ${px-5},${py}`}
                      fill="var(--amber)" stroke="#0d0e11" strokeWidth="0.8" opacity="0.9"
                    />
                    {/* Dashed vertical line */}
                    <line x1={px} y1={py+7} x2={px} y2={PAD.top + H}
                      stroke="var(--amber)" strokeWidth="0.5" strokeDasharray="2,4" opacity="0.35" />
                    {/* Label */}
                    <rect x={px - 30} y={py - 22} width={60} height={14} rx={1}
                      fill="var(--amber)" opacity="0.85" />
                    <text x={px - 26} y={py - 12} fontFamily="IBM Plex Mono" fontSize="8" fontWeight="700"
                      fill="#0d0e11">BUY {currencySymbol}{avgPrice.toFixed(2)}</text>
                  </g>
                );
              });
            })()}

            {/* ── EVENT INDICATORS (earnings, dividends, splits) ── */}
            {overlays.events && (() => {
              /** Event color + label config by type */
              const EVENT_CFG = {
                earnings: { color: "#e879f9", label: "E" },
                dividend: { color: "#38bdf8", label: "D" },
                split:    { color: "#fbbf24", label: "S" },
              };
              const markers = [];
              for (let i = 0; i < visibleData.length; i++) {
                const bar = visibleData[i];
                const dateKey = bar.date?.slice(0, 10);
                /** Merge backend events + the is_earnings flag from OHLCV */
                const evts = eventsByDate[dateKey] || [];
                const hasFlag = bar.isEarnings && !evts.some(e => e.type === "earnings");
                const combined = hasFlag ? [...evts, { type: "earnings", date: dateKey }] : evts;
                if (combined.length === 0) continue;

                /** Deduplicate by event type for this bar */
                const seen = new Set();
                const unique = combined.filter(e => {
                  if (seen.has(e.type)) return false;
                  seen.add(e.type);
                  return true;
                });

                const x = xOf(i);
                const baseY = PAD.top + H - 2; // bottom of price area
                unique.forEach((ev, ei) => {
                  const cfg = EVENT_CFG[ev.type];
                  if (!cfg) return;
                  const markerY = baseY - ei * 14; // stack vertically if multiple events
                  markers.push(
                    <g key={`ev-${i}-${ev.type}`}>
                      {/* Subtle vertical line from marker to bottom */}
                      <line x1={x} y1={markerY - 5} x2={x} y2={PAD.top + H}
                        stroke={cfg.color} strokeWidth="0.4" strokeDasharray="2,3" opacity="0.3" />
                      {/* Square marker */}
                      <rect x={x - 6} y={markerY - 6} width={12} height={12} rx={2}
                        fill={cfg.color} fillOpacity="0.15" stroke={cfg.color} strokeWidth="0.6" />
                      {/* Label letter */}
                      <text x={x} y={markerY + 3} textAnchor="middle"
                        fontFamily="IBM Plex Mono" fontSize="8" fontWeight="700" fill={cfg.color}>
                        {cfg.label}
                      </text>
                    </g>
                  );
                });
              }
              return markers.length > 0 ? <g clipPath="url(#chartClip)">{markers}</g> : null;
            })()}

            {/* ── DRAWING LAYER ── */}
            <g clipPath="url(#chartClip)">
              {drawings.filter(d => d.visible).map(d =>
                renderDrawing(d, visibleData, visibleStart, allData, xOf, yOf, PAD, H, W, pLo, pHi, dims, d.id === selectedDrawingId, currencySymbol)
              )}
              {/* Anchor handles for the selected drawing (rendered above drawing lines) */}
              {selectedDrawingId && !activeTool && (() => {
                const selDrawing = drawings.find(d => d.id === selectedDrawingId);
                if (!selDrawing) return null;
                const chartParams = { visibleData, visibleStart, allData, xOf, PAD, H, pLo, pHi };
                return renderAnchorHandles(selDrawing, chartParams);
              })()}
              {activeTool && renderPreview(activeTool, pendingAnchors, previewPoint, visibleData, visibleStart, allData, xOf, yOf, PAD, H, W, pLo, pHi, dims, drawingStyle)}
            </g>

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
                      {currencySymbol}{crosshair.priceCross?.toFixed(2)}
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

          {/* ── Drawing context toolbar (floating delete/deselect) ── */}
          {selectedDrawingId && !activeTool && (
            <DrawingContextToolbar
              onDelete={() => {
                setDrawings(prev => prev.filter(d => d.id !== selectedDrawingId));
                setSelectedDrawingId(null);
              }}
              onDeselect={() => setSelectedDrawingId(null)}
            />
          )}
        </div>

        {/* ── TOOLTIP ── */}
        {showHoverData && tooltip && !dragRef.current && (
          <div className="crosshair-tooltip" style={{
            position: "absolute",
            left: tooltip.screen.tRight ? tooltip.screen.x - 210 : tooltip.screen.x + 16,
            top:  tooltip.screen.tBottom ? tooltip.screen.y - 210 : tooltip.screen.y + 16,
            minWidth: 200,
            zIndex: 50,
          }}>
            <div className="tt-date">
              {new Date(tooltip.d.date).toLocaleDateString("en-US", { weekday: "short", year: "numeric", month: "short", day: "numeric" })}
              {/* Event badges (earnings from OHLCV flag + events API) */}
              {overlays.events && (() => {
                const dateKey = tooltip.d.date?.slice(0, 10);
                const evts = eventsByDate[dateKey] || [];
                const hasFlag = tooltip.d.isEarnings && !evts.some(e => e.type === "earnings");
                const combined = hasFlag ? [...evts, { type: "earnings" }] : evts;
                const seen = new Set();
                const unique = combined.filter(e => { if (seen.has(e.type)) return false; seen.add(e.type); return true; });
                const cfgMap = {
                  earnings: { color: "#e879f9", label: t("charts.earnings") },
                  dividend: { color: "#38bdf8", label: t("charts.dividend") },
                  split:    { color: "#fbbf24", label: t("charts.split") },
                };
                return unique.map(ev => {
                  const c = cfgMap[ev.type];
                  if (!c) return null;
                  return (
                    <span key={ev.type} style={{ marginLeft: 6, color: c.color, fontSize: 9, background: `${c.color}18`, padding: "1px 5px", border: `1px solid ${c.color}33` }}>
                      {c.label}{ev.detail ? ` · ${ev.detail}` : ""}
                    </span>
                  );
                });
              })()}
            </div>
            <div className="tt-row"><span className="tt-key">{t("charts.open")}</span>  <span className="tt-val">{currencySymbol}{tooltip.d.open.toFixed(2)}</span></div>
            <div className="tt-row"><span className="tt-key">HIGH</span>  <span className="tt-val" style={{ color: "#00d97e" }}>{currencySymbol}{tooltip.d.high.toFixed(2)}</span></div>
            <div className="tt-row"><span className="tt-key">LOW</span>   <span className="tt-val" style={{ color: "#f04438" }}>{currencySymbol}{tooltip.d.low.toFixed(2)}</span></div>
            <div className="tt-row">
              <span className="tt-key">{t("charts.close")}</span>
              <span className={`tt-val ${tooltip.d.close >= tooltip.d.open ? "pos" : "neg"}`}>{currencySymbol}{tooltip.d.close.toFixed(2)}</span>
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
                {overlays.sma50     && tooltip.s50  && <div className="tt-sma"><div className="tt-sma-dot" style={{ background: "#3d7ef5" }}/><span className="tt-sma-key">SMA 50</span><span className="tt-sma-val">{currencySymbol}{tooltip.s50.toFixed(2)}</span></div>}
                {overlays.sma150    && tooltip.s150 && <div className="tt-sma"><div className="tt-sma-dot" style={{ background: "#0fc0d0" }}/><span className="tt-sma-key">SMA 150</span><span className="tt-sma-val">{currencySymbol}{tooltip.s150.toFixed(2)}</span></div>}
                {overlays.smaCustom && tooltip.sCx  && <div className="tt-sma"><div className="tt-sma-dot" style={{ background: "#a78bfa" }}/><span className="tt-sma-key">SMA {customPeriod}</span><span className="tt-sma-val">{currencySymbol}{tooltip.sCx.toFixed(2)}</span></div>}
              </>
            )}
          </div>
        )}

        {/* ── SAVE TEMPLATE MODAL ── */}
        {showSaveModal && (
          <div className="tpl-modal-overlay" onClick={() => setShowSaveModal(false)}>
            <div className="tpl-modal" onClick={e => e.stopPropagation()}>
              <div className="tpl-modal-title">SAVE TEMPLATE</div>
              <div className="tpl-modal-desc">
                Save current drawings ({drawings.length}) and overlay settings for {symbol}.
              </div>
              <input className="tpl-modal-input"
                placeholder="Template name..."
                value={templateName}
                onChange={e => setTemplateName(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter") handleSaveTemplate(); if (e.key === "Escape") setShowSaveModal(false); }}
                autoFocus
              />
              <div className="tpl-modal-actions">
                <button className="tpl-modal-btn cancel" onClick={() => setShowSaveModal(false)}>CANCEL</button>
                <button className="tpl-modal-btn save"
                  disabled={!templateName.trim() || templateSaving}
                  onClick={handleSaveTemplate}>
                  {templateSaving ? "SAVING..." : "SAVE"}
                </button>
              </div>
            </div>
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

/* ─── PORTFOLIO SIDE PANEL ──────────────────────────────────────────────────── */
function PortfolioSidePanel({ token, onSelectSymbol, activeSymbol }) {
  const { t } = useI18n();
  const { currencySymbol } = useCurrency();
  const [portfolios, setPortfolios] = useState([]);
  const [activePortfolioId, setActivePortfolioId] = useState(null);
  const [positions, setPositions] = useState([]);
  const [quotes, setQuotes] = useState({});
  const [loading, setLoading] = useState(false);

  // Load portfolios on mount
  useEffect(() => {
    if (!token) return;
    api.listPortfolios(token)
      .then(list => {
        setPortfolios(list);
        if (list.length) setActivePortfolioId(list[0].portfolio_id);
      })
      .catch(() => {});
  }, [token]);

  // Load positions when portfolio changes
  useEffect(() => {
    if (!token || !activePortfolioId) { setPositions([]); return; }
    setLoading(true);
    api.listPositions(activePortfolioId, token)
      .then(list => setPositions(list))
      .catch(() => setPositions([]))
      .finally(() => setLoading(false));
  }, [activePortfolioId, token]);

  // Load quotes for all positions
  useEffect(() => {
    if (!token || !positions.length) { setQuotes({}); return; }
    const tickers = [...new Set(positions.map(p => p.ticker))];
    api.bulkQuotes(tickers, token)
      .then(list => {
        const map = {};
        list.forEach(q => { map[q.symbol] = q; });
        setQuotes(map);
      })
      .catch(() => {});
  }, [positions, token]);

  const activePortfolio = portfolios.find(p => p.portfolio_id === activePortfolioId);

  // Summary
  const summary = useMemo(() => {
    let totalValue = 0, totalCost = 0;
    positions.filter(p => !p.is_excluded).forEach(p => {
      const price = quotes[p.ticker]?.price;
      const qty = parseFloat(p.quantity);
      const bep = parseFloat(p.purchase_price);
      if (price != null) totalValue += price * qty;
      totalCost += bep * qty;
    });
    return { totalValue, totalCost, gainLoss: totalValue - totalCost, gainPct: totalCost > 0 ? ((totalValue - totalCost) / totalCost) * 100 : 0 };
  }, [positions, quotes]);

  const fmtUSD = (n) => `${currencySymbol}${parseFloat(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  const fmtPct = (n) => `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;

  return (
    <div className="portfolio-panel">
      {/* Header */}
      <div className="pp-header">
        <div className="pp-title">{t("charts.portfolio")}</div>
        {portfolios.length > 1 ? (
          <select className="pp-select"
            value={activePortfolioId || ""}
            onChange={e => setActivePortfolioId(e.target.value)}>
            {portfolios.map(p => <option key={p.portfolio_id} value={p.portfolio_id}>{p.name}</option>)}
          </select>
        ) : activePortfolio ? (
          <div className="pp-portfolio-name">{activePortfolio.name}</div>
        ) : null}
      </div>

      {/* Summary */}
      <div className="pp-summary">
        <div className="pp-summary-row">
          <span className="pp-summary-label">VALUE</span>
          <span className="pp-summary-val">{fmtUSD(summary.totalValue)}</span>
        </div>
        <div className="pp-summary-row">
          <span className="pp-summary-label">P&L</span>
          <span className={`pp-summary-val ${summary.gainLoss >= 0 ? "pos" : "neg"}`}>
            {fmtUSD(summary.gainLoss)} ({fmtPct(summary.gainPct)})
          </span>
        </div>
      </div>

      {/* Positions list */}
      <div className="pp-positions">
        {loading && <div className="pp-loading loading-pulse">{t("charts.loading")}</div>}
        {!loading && positions.length === 0 && (
          <div className="pp-empty">No positions</div>
        )}
        {positions.map(pos => {
          const q = quotes[pos.ticker];
          const price = q?.price;
          const qty = parseFloat(pos.quantity);
          const bep = parseFloat(pos.purchase_price);
          const gainPct = price != null ? ((price - bep) / bep) * 100 : null;
          const isActive = activeSymbol === pos.ticker;

          return (
            <div key={pos.position_id}
              className={`pp-position${isActive ? " active" : ""}`}
              onClick={() => onSelectSymbol(pos.ticker)}>
              <div className="pp-pos-top">
                <span className="pp-pos-ticker">{pos.ticker}</span>
                <span className="pp-pos-price">
                  {price != null ? fmtUSD(price) : <span className="loading-pulse">...</span>}
                </span>
              </div>
              <div className="pp-pos-bottom">
                <span className="pp-pos-qty">{qty} shares</span>
                {gainPct != null && (
                  <span className={`pp-pos-gain ${gainPct >= 0 ? "pos" : "neg"}`}>
                    {gainPct >= 0 ? "+" : ""}{gainPct.toFixed(2)}%
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ─── WATCHLIST SIDE PANEL ──────────────────────────────────────────────────── */
/**
 * WatchlistSidePanel — collapsible right-side panel that displays the user's
 * watchlists with live quotes.  Follows the same visual pattern as
 * PortfolioSidePanel so only one panel is visible at a time.
 *
 * @param {string}   token           - JWT access token
 * @param {Function} onSelectSymbol  - callback(symbol) to navigate the chart
 * @param {string}   activeSymbol    - currently-displayed chart symbol
 */
function WatchlistSidePanel({ token, onSelectSymbol, activeSymbol }) {
  const { t } = useI18n();
  const { currencySymbol } = useCurrency();
  const mktStatus = useMarketStatus();

  const [watchlists, setWatchlists] = useState([]);
  const [activeWatchlistId, setActiveWatchlistId] = useState(null);
  const [items, setItems] = useState([]);
  const [quotes, setQuotes] = useState({});
  const [loading, setLoading] = useState(false);

  /* Fetch all user watchlists on mount.
   * Sets the first watchlist as active by default. */
  useEffect(() => {
    if (!token) return;
    api.getWatchlists(token)
      .then(list => {
        setWatchlists(list);
        if (list.length) setActiveWatchlistId(list[0].watchlist_id);
      })
      .catch(() => {});
  }, [token]);

  /* Fetch items whenever the active watchlist changes.
   * api.getWatchlist returns the watchlist object with an `items` array. */
  useEffect(() => {
    if (!token || !activeWatchlistId) { setItems([]); return; }
    setLoading(true);
    api.getWatchlist(activeWatchlistId, token)
      .then(wl => setItems(wl.items || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [activeWatchlistId, token]);

  /* Fetch bulk quotes for all watchlist symbols.
   * Uses api.bulkQuotes for a single network round-trip. */
  useEffect(() => {
    if (!token || !items.length) { setQuotes({}); return; }
    const symbols = [...new Set(items.map(i => i.symbol))];
    api.bulkQuotes(symbols, token)
      .then(list => {
        const map = {};
        list.forEach(q => { map[q.symbol] = q; });
        setQuotes(map);
      })
      .catch(() => {});
  }, [items, token]);

  /* Auto-refresh quotes on a timer.
   * Faster during market hours (10 s), slower when closed (5 min). */
  const pollMs = mktStatus.isOpen ? 10000 : 300000;
  useEffect(() => {
    if (!token || !items.length) return;
    const symbols = [...new Set(items.map(i => i.symbol))];
    const id = setInterval(() => {
      api.bulkQuotes(symbols, token)
        .then(list => {
          const map = {};
          list.forEach(q => { map[q.symbol] = q; });
          setQuotes(map);
        })
        .catch(() => {});
    }, pollMs);
    return () => clearInterval(id);
  }, [items, token, pollMs]);

  const activeWatchlist = watchlists.find(w => w.watchlist_id === activeWatchlistId);

  return (
    <div className="portfolio-panel">
      {/* Header — reuses pp-header / pp-title / pp-select classes */}
      <div className="pp-header">
        <div className="pp-title">WATCHLIST</div>
        {watchlists.length > 1 ? (
          <select className="pp-select"
            value={activeWatchlistId || ""}
            onChange={e => setActiveWatchlistId(e.target.value)}>
            {watchlists.map(w => (
              <option key={w.watchlist_id} value={w.watchlist_id}>{w.name}</option>
            ))}
          </select>
        ) : activeWatchlist ? (
          <div className="pp-portfolio-name">{activeWatchlist.name}</div>
        ) : null}
      </div>

      {/* Compact summary row — symbol count */}
      <div className="pp-summary">
        <div className="pp-summary-row">
          <span className="pp-summary-label">SYMBOLS</span>
          <span className="pp-summary-val">{items.length}</span>
        </div>
      </div>

      {/* Scrollable items list */}
      <div className="pp-positions">
        {loading && <div className="pp-loading loading-pulse">{t("charts.loading")}</div>}
        {!loading && items.length === 0 && (
          <div className="pp-empty">No watchlist items</div>
        )}
        {items.map(item => {
          const q = quotes[item.symbol];
          const price = q?.price;
          const changePct = q?.change_pct;
          const isActive = activeSymbol === item.symbol;

          return (
            <div key={item.item_id || item.symbol}
              className={`pp-position${isActive ? " active" : ""}`}
              onClick={() => onSelectSymbol(item.symbol)}>
              <div className="pp-pos-top">
                {/* Symbol in amber per Bloomberg terminal aesthetic */}
                <span className="pp-pos-ticker" style={{ color: "var(--amber)" }}>{item.symbol}</span>
                <span className="pp-pos-price">
                  {price != null ? `${currencySymbol}${price.toFixed(2)}` : <span className="loading-pulse">...</span>}
                </span>
              </div>
              <div className="pp-pos-bottom">
                <span className="pp-pos-qty">{item.asset_type || "Stock"}</span>
                {changePct != null && (
                  <span className={`pp-pos-gain ${changePct >= 0 ? "pos" : "neg"}`}>
                    {changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ─── MAIN CHARTS PAGE ──────────────────────────────────────────────────────── */
export function ChartsPage({ initialSymbol, goBack, token }) {
  const { t } = useI18n();
  const { formatValue, currencySymbol } = useCurrency();
  const [watchlist, setWatchlist] = useState(["AAPL", "NVDA", "TSLA"]);
  const [activeSymbol, setActiveSymbol] = useState(initialSymbol || "AAPL");
  const [showAssetDetail, setShowAssetDetail] = useState(false);   // toggle AssetDetailPanel modal
  const [showAlertModal, setShowAlertModal] = useState(false);     // toggle AlertModal for price alerts
  /* Panel mode: null (hidden), "portfolio", or "watchlist".
   * Migrates legacy boolean "0"/"1" values from tt_chart_panel. */
  const [panelMode, setPanelMode] = useState(() => {
    const stored = localStorage.getItem("tt_chart_panel");
    if (stored === "portfolio" || stored === "watchlist") return stored;
    if (stored === "1") return "portfolio";          // migrate old boolean format
    return null;                                     // "0" or absent → hidden
  });
  const mktStatus = useMarketStatus();

  /**
   * togglePanel — switch to the given panel mode, or close it if already active.
   * Only one panel (portfolio OR watchlist) is shown at a time.
   *
   * @param {string} mode - "portfolio" | "watchlist"
   */
  const togglePanel = (mode) => {
    setPanelMode(prev => {
      const next = prev === mode ? null : mode;
      localStorage.setItem("tt_chart_panel", next || "0");
      return next;
    });
  };

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

  const handlePanelSelect = (sym) => {
    addSymbol(sym);
    setActiveSymbol(sym);
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
            {t("charts.title")}
          </div>
          <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 11, color: "#4a5568", marginTop: 4 }}>
            {t("charts.subtitle")}
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          {/* Panel toggle: Portfolio */}
          <button className="btn btn-ghost" onClick={() => togglePanel("portfolio")}
            style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: 10, letterSpacing: "0.5px", padding: "4px 10px",
              color: panelMode === "portfolio" ? "var(--amber)" : "var(--muted)",
              border: `1px solid ${panelMode === "portfolio" ? "rgba(255,178,56,0.3)" : "#1e2535"}` }}>
            {panelMode === "portfolio" ? `◁ ${t("charts.portfolio")}` : t("charts.portfolio")}
          </button>
          {/* Panel toggle: Watchlist */}
          <button className="btn btn-ghost" onClick={() => togglePanel("watchlist")}
            style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: 10, letterSpacing: "0.5px", padding: "4px 10px",
              color: panelMode === "watchlist" ? "var(--amber)" : "var(--muted)",
              border: `1px solid ${panelMode === "watchlist" ? "rgba(255,178,56,0.3)" : "#1e2535"}` }}>
            {panelMode === "watchlist" ? "◁ WATCHLIST" : "WATCHLIST"}
          </button>
          {/* Asset detail info button for active symbol */}
          {activeSymbol && (
            <button
              className="btn btn-ghost"
              title="Asset details"
              onClick={() => setShowAssetDetail(true)}
              style={{
                fontFamily: "'IBM Plex Mono',monospace", fontSize: 14,
                padding: "4px 10px", color: "var(--muted)",
                border: "1px solid #1e2535", cursor: "pointer",
              }}
            >
              {"\u24D8"}
            </button>
          )}
          {/* Price alert button — opens AlertModal with current symbol/price */}
          {activeSymbol && (
            <button
              className="btn btn-ghost"
              title="Set price alert"
              onClick={() => setShowAlertModal(true)}
              style={{
                fontFamily: "'IBM Plex Mono',monospace", fontSize: 14,
                padding: "4px 10px", color: "var(--muted)",
                border: "1px solid #1e2535", cursor: "pointer",
              }}
            >
              <Ic.bell />
            </button>
          )}
          <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 10, color: "#4a5568", textAlign: "right" }}>
            <div style={{ color: mktStatus.isOpen ? "#00d97e" : "var(--red)", display: "flex", alignItems: "center", gap: 5, justifyContent: "flex-end" }}>
              <span style={{ width: 5, height: 5, borderRadius: "50%", background: mktStatus.isOpen ? "#00d97e" : "var(--red)", display: "inline-block", animation: "blink 2s infinite" }} />
              {mktStatus.isOpen ? t("charts.nyseOpen") : `${t("charts.closedOpensIn")} ${mktStatus.countdown}`}
            </div>
            <div style={{ marginTop: 2 }}>{mktStatus.dateStr} · {mktStatus.timeStr}</div>
          </div>
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

      {/* Chart + Side Panel */}
      <div style={{ flex: 1, overflow: "hidden", minHeight: 0, display: "flex", position: "relative" }}>
        {/* Chart area */}
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

        {/* Portfolio side panel — visible when panelMode === "portfolio" */}
        {panelMode === "portfolio" && (
          <PortfolioSidePanel
            token={token}
            onSelectSymbol={handlePanelSelect}
            activeSymbol={activeSymbol}
          />
        )}

        {/* Watchlist side panel — visible when panelMode === "watchlist" */}
        {panelMode === "watchlist" && (
          <WatchlistSidePanel
            token={token}
            onSelectSymbol={handlePanelSelect}
            activeSymbol={activeSymbol}
          />
        )}
      </div>
      {showAssetDetail && activeSymbol && (
        <AssetDetailPanel symbol={activeSymbol} token={token} onClose={() => setShowAssetDetail(false)} />
      )}
      {showAlertModal && activeSymbol && (
        <AlertModal
          symbol={activeSymbol}
          currentPrice={quoteData?.price ?? null}
          token={token}
          onClose={() => setShowAlertModal(false)}
          onCreated={() => {}}
        />
      )}
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
  position: absolute; top: 12px; left: 46px;
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

/* ── Portfolio Side Panel ── */
.portfolio-panel {
  width: 280px; flex-shrink: 0;
  background: #0e1117; border-left: 1px solid #1e2535;
  display: flex; flex-direction: column;
  overflow: hidden;
}
.pp-header {
  padding: 14px 16px 10px; border-bottom: 1px solid #1e2535;
  flex-shrink: 0;
}
.pp-title {
  font-family: 'Bebas Neue', sans-serif; font-size: 18px;
  color: #e8f0fa; letter-spacing: 1.5px; margin-bottom: 6px;
}
.pp-select {
  width: 100%; background: #141820; border: 1px solid #1e2535;
  color: #e8f0fa; font-family: 'IBM Plex Mono', monospace; font-size: 11px;
  padding: 5px 8px; border-radius: 2px; outline: none; cursor: pointer;
}
.pp-select:focus { border-color: #0f7d40; }
.pp-portfolio-name {
  font-family: 'IBM Plex Mono', monospace; font-size: 11px;
  color: #0f7d40; font-weight: 600; letter-spacing: 0.5px;
}
.pp-summary {
  padding: 10px 16px; border-bottom: 1px solid #1e2535;
  flex-shrink: 0;
}
.pp-summary-row {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 4px;
}
.pp-summary-label {
  font-family: 'IBM Plex Mono', monospace; font-size: 10px;
  color: #4a5568; letter-spacing: 0.8px;
}
.pp-summary-val {
  font-family: 'IBM Plex Mono', monospace; font-size: 11px;
  color: #e8f0fa; font-weight: 500;
}
.pp-summary-val.pos { color: #00d97e; }
.pp-summary-val.neg { color: #f04438; }
.pp-positions {
  flex: 1; overflow-y: auto; overflow-x: hidden;
}
.pp-loading, .pp-empty {
  padding: 24px 16px; text-align: center;
  font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: #4a5568;
}
.pp-position {
  padding: 8px 16px; cursor: pointer;
  border-bottom: 1px solid #141820;
  transition: background .1s;
}
.pp-position:hover { background: #141820; }
.pp-position.active { background: rgba(15,125,64,.08); border-left: 2px solid #0f7d40; }
.pp-pos-top {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 2px;
}
.pp-pos-ticker {
  font-family: 'IBM Plex Mono', monospace; font-size: 12px;
  font-weight: 700; color: #0f7d40; letter-spacing: 0.5px;
}
.pp-pos-price {
  font-family: 'IBM Plex Mono', monospace; font-size: 11px;
  color: #e8f0fa; font-weight: 500;
}
.pp-pos-bottom {
  display: flex; justify-content: space-between; align-items: center;
}
.pp-pos-qty {
  font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: #4a5568;
}
.pp-pos-gain {
  font-family: 'IBM Plex Mono', monospace; font-size: 10px; font-weight: 600;
}
.pp-pos-gain.pos { color: #00d97e; }
.pp-pos-gain.neg { color: #f04438; }

/* ── Drawing Toolbar ── */
.draw-toolbar {
  position: absolute; top: 0; left: 0; bottom: 0; width: 36px;
  background: rgba(14,17,23,0.92); border-right: 1px solid #1e2535;
  display: flex; flex-direction: column; align-items: center;
  padding: 8px 0; gap: 2px; z-index: 10;
  backdrop-filter: blur(6px);
}
.draw-tool-btn {
  width: 28px; height: 28px; display: flex; align-items: center; justify-content: center;
  background: none; border: 1px solid transparent; border-radius: 2px;
  cursor: pointer; color: #4a5568; transition: all 0.1s; flex-shrink: 0;
  padding: 0;
}
.draw-tool-btn:hover { color: #c8d3e0; background: rgba(255,255,255,0.04); border-color: #263045; }
.draw-tool-btn.active { color: #f59e0b; background: rgba(245,158,11,0.08); border-color: rgba(245,158,11,0.3); }
.draw-tool-btn.mini { width: 28px; height: 18px; }
.draw-tool-btn.danger { color: #4a5568; }
.draw-tool-btn.danger:hover { color: #f04438; background: rgba(240,68,56,0.08); border-color: rgba(240,68,56,0.3); }
.draw-toolbar-sep {
  width: 18px; height: 1px; background: #1e2535; margin: 4px 0; flex-shrink: 0;
}
.draw-color-wrap {
  width: 28px; height: 28px; position: relative; cursor: pointer;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.draw-color-swatch {
  width: 14px; height: 14px; border-radius: 2px; border: 1px solid #263045;
  pointer-events: none;
}
.draw-color-input {
  position: absolute; inset: 0; opacity: 0; cursor: pointer;
  width: 100%; height: 100%;
}
.draw-text-input {
  width: 28px; background: #141820; border: 1px solid #263045;
  color: #e8f0fa; font-family: 'IBM Plex Mono', monospace; font-size: 8px;
  padding: 3px 2px; text-align: center; outline: none; border-radius: 2px;
  flex-shrink: 0;
}
.draw-text-input:focus { border-color: #f59e0b; }
.draw-count {
  font-family: 'IBM Plex Mono', monospace; font-size: 8px; color: #4a5568;
  text-align: center; line-height: 1; margin-top: 2px; flex-shrink: 0;
}
.draw-active-label {
  writing-mode: vertical-rl; text-orientation: mixed;
  font-family: 'IBM Plex Mono', monospace; font-size: 8px; font-weight: 600;
  color: #f59e0b; letter-spacing: 1px; margin-top: auto; padding-bottom: 8px;
  white-space: nowrap; flex-shrink: 0;
}
.draw-anchor-count {
  font-size: 8px; color: #718096; margin-top: 4px;
}

/* ── Template Dropdown & Modal ── */
.tpl-dropdown {
  position: absolute; left: calc(100% + 4px); top: 0;
  width: 220px; background: #141820; border: 1px solid #263045;
  z-index: 20; max-height: 300px; overflow-y: auto;
  box-shadow: 0 8px 32px rgba(0,0,0,0.7);
}
.tpl-dropdown-header {
  padding: 8px 12px; font-family: 'IBM Plex Mono', monospace;
  font-size: 9px; color: #4a5568; letter-spacing: 1px;
  border-bottom: 1px solid #1e2535;
}
.tpl-dropdown-empty {
  padding: 16px 12px; font-family: 'IBM Plex Mono', monospace;
  font-size: 10px; color: #4a5568; text-align: center;
}
.tpl-dropdown-item {
  padding: 8px 12px; cursor: pointer;
  border-bottom: 1px solid #1a1d2e; transition: background 0.08s;
  position: relative;
}
.tpl-dropdown-item:last-child { border-bottom: none; }
.tpl-dropdown-item:hover { background: #1a1d2e; }
.tpl-item-name {
  font-family: 'IBM Plex Mono', monospace; font-size: 11px;
  color: #e8f0fa; font-weight: 500; margin-bottom: 2px;
}
.tpl-item-meta {
  font-family: 'IBM Plex Mono', monospace; font-size: 9px;
  color: #4a5568; letter-spacing: 0.3px;
}
.tpl-item-del {
  position: absolute; top: 6px; right: 6px;
  background: none; border: none; cursor: pointer; color: #4a5568;
  padding: 2px; display: flex; align-items: center;
  transition: color 0.1s;
}
.tpl-item-del:hover { color: #f04438; }

.tpl-modal-overlay {
  position: absolute; inset: 0; z-index: 60;
  background: rgba(0,0,0,0.6); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
}
.tpl-modal {
  background: #141820; border: 1px solid #263045;
  padding: 24px; width: 340px;
  box-shadow: 0 12px 48px rgba(0,0,0,0.8);
}
.tpl-modal-title {
  font-family: 'Bebas Neue', sans-serif; font-size: 22px;
  color: #e8f0fa; letter-spacing: 1.5px; margin-bottom: 8px;
}
.tpl-modal-desc {
  font-family: 'IBM Plex Mono', monospace; font-size: 10px;
  color: #4a5568; margin-bottom: 16px; line-height: 1.5;
}
.tpl-modal-input {
  width: 100%; background: #0e1117; border: 1px solid #1e2535;
  padding: 10px 12px; font-family: 'IBM Plex Mono', monospace;
  font-size: 13px; color: #e8f0fa; outline: none;
  border-radius: 2px; box-sizing: border-box;
  text-transform: uppercase; letter-spacing: 0.5px;
  transition: border-color 0.1s;
}
.tpl-modal-input:focus { border-color: #0f7d40; }
.tpl-modal-input::placeholder { color: #4a5568; text-transform: none; letter-spacing: 0; }
.tpl-modal-actions {
  display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px;
}
.tpl-modal-btn {
  padding: 8px 20px; font-family: 'IBM Plex Mono', monospace;
  font-size: 11px; font-weight: 600; letter-spacing: 0.8px;
  cursor: pointer; border: 1px solid; border-radius: 2px;
  transition: all 0.1s;
}
.tpl-modal-btn.cancel {
  background: none; border-color: #1e2535; color: #4a5568;
}
.tpl-modal-btn.cancel:hover { border-color: #263045; color: #718096; }
.tpl-modal-btn.save {
  background: #0f7d40; border-color: #0f7d40; color: #060f08;
}
.tpl-modal-btn.save:hover { background: #10a050; }
.tpl-modal-btn.save:disabled {
  opacity: 0.4; cursor: not-allowed;
}

@media (max-width: 640px) {
  .chart-search-input { width: 100% !important; }
  .chart-controls { flex-wrap: wrap; gap: 4px; }
  .chart-stats { font-size: 10px; }
  .portfolio-panel {
    position: fixed; top: 42px; right: 0; bottom: 56px;
    width: 85vw; z-index: 90;
    box-shadow: -4px 0 20px rgba(0,0,0,0.5);
  }
}
`;

