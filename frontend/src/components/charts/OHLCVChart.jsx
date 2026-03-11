/**
 * OHLCVChart — reusable candlestick / line chart with optional volume bars,
 * SMA overlays, crosshair, and signal markers.
 *
 * Extracted from the core rendering logic in ChartsPage.jsx's StockChart
 * component.  This version is headless (no stats bar, drawing tools, or
 * template system) so it can be embedded in TradingPage, DashboardPage, or
 * any panel that needs an OHLCV visualisation.
 *
 * Rendering: 100% SVG — no canvas dependency.
 *
 * Props:
 *   data            — Array<{ date, open, high, low, close, volume }>
 *   chartType       — "candle" | "line"  (default "candle")
 *   showVolume      — render volume bars in bottom 15% (default true)
 *   showCrosshair   — enable crosshair + tooltip on hover (default true)
 *   smaOverlays     — Array<{ period, color, dashed? }> SMA lines to render
 *   signals         — Array<{ index, type, label, color? }> markers on the chart
 *   height          — explicit px height (default: fills container)
 *   currencySymbol  — axis label prefix (default "$")
 *   onBarHover      — (bar, index) => void  callback
 */

import React, { useState, useRef, useEffect, useMemo, useCallback } from "react";

/* -- Helpers -------------------------------------------------------------- */

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
  v >= 1e9
    ? (v / 1e9).toFixed(2) + "B"
    : v >= 1e6
      ? (v / 1e6).toFixed(2) + "M"
      : v >= 1e3
        ? (v / 1e3).toFixed(0) + "K"
        : String(v);

/* -- Component ------------------------------------------------------------ */

const PAD = { top: 20, right: 72, bottom: 22, left: 8 };

export default function OHLCVChart({
  data = [],
  chartType = "candle",
  showVolume = true,
  showCrosshair = true,
  smaOverlays = [],
  signals = [],
  height: explicitHeight,
  currencySymbol = "$",
  onBarHover,
}) {
  const containerRef = useRef(null);
  const [dims, setDims] = useState({ w: 600, h: 400 });
  const [hoverIdx, setHoverIdx] = useState(-1);

  /* -- Resize observer ---------------------------------------------------- */
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

  /* -- Geometry ----------------------------------------------------------- */
  const n = data.length;
  const totalH = Math.max(50, dims.h - PAD.top - PAD.bottom);
  const VOL_H = showVolume ? Math.max(40, Math.round(totalH * 0.15)) : 0;
  const VOL_GAP = showVolume ? 8 : 0;
  const H = totalH - VOL_H - VOL_GAP;
  const W = Math.max(10, dims.w - PAD.left - PAD.right);
  const volTop = PAD.top + H + VOL_GAP;

  const candleGap = n > 0 ? W / n : 1;
  const candleW = Math.max(1, Math.min(14, candleGap * 0.72));

  const priceMin = n > 0 ? Math.min(...data.map((d) => d.low)) : 0;
  const priceMax = n > 0 ? Math.max(...data.map((d) => d.high)) : 1;
  const pricePad = (priceMax - priceMin) * 0.07 || 1;
  const pLo = priceMin - pricePad;
  const pHi = priceMax + pricePad;
  const volMax = n > 0 ? Math.max(...data.map((d) => d.volume), 1) : 1;

  const xOf = (i) => PAD.left + (i + 0.5) * candleGap;
  const yOf = (p) => PAD.top + H - ((p - pLo) / (pHi - pLo)) * H;

  /* -- Y-axis ticks ------------------------------------------------------- */
  const yTicks = useMemo(() => {
    if (pHi === pLo) return [];
    const range = pHi - pLo;
    const raw = range / 6;
    const mag = Math.pow(10, Math.floor(Math.log10(Math.max(raw, 0.01))));
    const step = Math.ceil(raw / mag) * mag;
    const ticks = [];
    let t = Math.ceil(pLo / step) * step;
    while (t <= pHi) {
      ticks.push(t);
      t = +(t + step).toFixed(10);
    }
    return ticks;
  }, [pLo, pHi]);

  /* -- X-axis labels ------------------------------------------------------ */
  const xLabels = useMemo(() => {
    const labels = [];
    let lastYear = null;
    const maxLabels = Math.floor(W / 80);
    const step = Math.max(1, Math.floor(n / maxLabels));
    for (let i = 0; i < n; i += step) {
      const d = new Date(data[i].date);
      const mo = d.toLocaleString("en-US", { month: "short" });
      const yr = d.getFullYear();
      const lbl = yr !== lastYear ? `${mo} '${String(yr).slice(2)}` : mo;
      labels.push({ x: xOf(i), label: lbl });
      lastYear = yr;
    }
    return labels;
  }, [data, n, W]);

  /* -- SMA computations --------------------------------------------------- */
  const smaLines = useMemo(
    () =>
      smaOverlays.map((cfg) => ({
        ...cfg,
        data: calcSMA(data, cfg.period),
      })),
    [data, smaOverlays],
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

  /* -- Line path (for line chart mode) ------------------------------------ */
  const linePath = useMemo(() => {
    let p = "";
    for (let i = 0; i < n; i++) {
      const x = xOf(i);
      const y = yOf(data[i].close);
      p += `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    }
    return p;
  }, [data, W, H, pLo, pHi]);

  /* -- Mouse hover -------------------------------------------------------- */
  const handleMouseMove = useCallback(
    (e) => {
      if (!showCrosshair || n === 0) return;
      const svg = e.currentTarget;
      const rect = svg.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const idx = Math.round((mx - PAD.left) / candleGap - 0.5);
      const clamped = Math.max(0, Math.min(n - 1, idx));
      setHoverIdx(clamped);
      if (onBarHover && data[clamped]) onBarHover(data[clamped], clamped);
    },
    [showCrosshair, n, candleGap, onBarHover, data],
  );

  const handleMouseLeave = useCallback(() => setHoverIdx(-1), []);

  /* -- Hover bar data ----------------------------------------------------- */
  const hBar = hoverIdx >= 0 && hoverIdx < n ? data[hoverIdx] : null;

  /* -- Render ------------------------------------------------------------- */
  return (
    <div
      ref={containerRef}
      style={{
        position: "relative",
        width: "100%",
        height: explicitHeight || "100%",
        background: "#090b0f",
        cursor: showCrosshair ? "crosshair" : "default",
      }}
    >
      <svg
        style={{ display: "block", width: "100%", height: "100%" }}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
      >
        <defs>
          <clipPath id="ohlcvClip">
            <rect x={PAD.left} y={PAD.top} width={W} height={totalH} />
          </clipPath>
          {/* Line chart gradient fill */}
          <linearGradient id="lineGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#0f7d40" stopOpacity="0.18" />
            <stop offset="100%" stopColor="#0f7d40" stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* Grid lines + Y-axis labels */}
        {yTicks.map((t, i) => {
          const y = yOf(t);
          return (
            <g key={i}>
              <line
                x1={PAD.left}
                y1={y}
                x2={PAD.left + W}
                y2={y}
                stroke="var(--border)"
                strokeWidth="1"
                strokeDasharray="2,4"
              />
              <text
                x={PAD.left + W + 6}
                y={y + 3}
                fill="var(--muted)"
                fontSize="10"
                fontFamily="var(--font-mono)"
              >
                {currencySymbol}
                {t >= 1000 ? t.toFixed(0) : t.toFixed(2)}
              </text>
            </g>
          );
        })}

        {/* X-axis labels */}
        {xLabels.map((l, i) => (
          <text
            key={i}
            x={l.x}
            y={dims.h - 4}
            textAnchor="middle"
            fill="var(--muted)"
            fontSize="10"
            fontFamily="var(--font-mono)"
          >
            {l.label}
          </text>
        ))}

        <g clipPath="url(#ohlcvClip)">
          {/* Line mode */}
          {chartType === "line" && n > 0 && (
            <>
              <path
                d={`${linePath}L${xOf(n - 1).toFixed(1)},${(PAD.top + H).toFixed(1)}L${xOf(0).toFixed(1)},${(PAD.top + H).toFixed(1)}Z`}
                fill="url(#lineGrad)"
              />
              <path
                d={linePath}
                fill="none"
                stroke="var(--amber)"
                strokeWidth="1.5"
              />
            </>
          )}

          {/* Candle mode */}
          {chartType === "candle" &&
            data.map((d, i) => {
              const bull = d.close >= d.open;
              const color = bull ? "#00d97e" : "#f04438";
              const x = xOf(i);
              const bodyTop = yOf(Math.max(d.open, d.close));
              const bodyBot = yOf(Math.min(d.open, d.close));
              const bodyH = Math.max(1, bodyBot - bodyTop);
              const isHover = i === hoverIdx;
              return (
                <g key={i}>
                  <line
                    x1={x}
                    y1={yOf(d.high)}
                    x2={x}
                    y2={yOf(d.low)}
                    stroke={color}
                    strokeWidth={candleW > 3 ? 1.2 : 1}
                    opacity={isHover ? 1 : 0.8}
                  />
                  <rect
                    x={x - candleW / 2}
                    y={bodyTop}
                    width={candleW}
                    height={bodyH}
                    fill={color}
                    opacity={isHover ? 1 : bull ? 0.85 : 0.7}
                    stroke={isHover ? "#fff" : "none"}
                    strokeWidth={isHover ? 0.8 : 0}
                  />
                </g>
              );
            })}

          {/* SMA overlays */}
          {smaLines.map((sma, i) => (
            <path
              key={i}
              d={smaPath(sma.data)}
              fill="none"
              stroke={sma.color}
              strokeWidth="1.2"
              strokeDasharray={sma.dashed ? "4,3" : "none"}
              opacity="0.85"
            />
          ))}

          {/* Signal markers */}
          {signals.map((sig, i) => {
            if (sig.index < 0 || sig.index >= n) return null;
            const x = xOf(sig.index);
            const bar = data[sig.index];
            const y =
              sig.type === "entry"
                ? yOf(bar.high) - 10
                : yOf(bar.low) + 10;
            const color =
              sig.color ||
              (sig.type === "entry"
                ? "#00d97e"
                : sig.type === "exit"
                  ? "#f04438"
                  : "#fbbf24");
            return (
              <g key={i}>
                {/* Vertical indicator line */}
                <line
                  x1={x}
                  y1={PAD.top}
                  x2={x}
                  y2={PAD.top + H}
                  stroke={color}
                  strokeWidth="0.5"
                  strokeDasharray="3,3"
                  opacity="0.4"
                />
                {/* Triangle marker */}
                <polygon
                  points={
                    sig.type === "entry"
                      ? `${x},${y + 8} ${x - 4},${y} ${x + 4},${y}`
                      : `${x},${y - 8} ${x - 4},${y} ${x + 4},${y}`
                  }
                  fill={color}
                  opacity="0.9"
                />
                {/* Label */}
                {sig.label && (
                  <text
                    x={x}
                    y={sig.type === "entry" ? y - 4 : y + 14}
                    textAnchor="middle"
                    fill={color}
                    fontSize="8"
                    fontFamily="var(--font-mono)"
                    fontWeight="600"
                  >
                    {sig.label}
                  </text>
                )}
              </g>
            );
          })}

          {/* Volume bars */}
          {showVolume && (
            <>
              <line
                x1={PAD.left}
                y1={volTop}
                x2={PAD.left + W}
                y2={volTop}
                stroke="var(--border)"
                strokeWidth="1"
              />
              <text
                x={PAD.left + 4}
                y={volTop + 10}
                fill="var(--muted)"
                fontSize="8"
                fontFamily="var(--font-mono)"
              >
                VOLUME
              </text>
              <text
                x={PAD.left + W + 6}
                y={volTop + 10}
                fill="var(--muted)"
                fontSize="8"
                fontFamily="var(--font-mono)"
              >
                {fmtVol(volMax)}
              </text>
              {data.map((d, i) => {
                const barH = Math.max(
                  1,
                  (d.volume / volMax) * (VOL_H - 14),
                );
                const bull = d.close >= d.open;
                const isHover = i === hoverIdx;
                return (
                  <rect
                    key={i}
                    x={xOf(i) - candleW / 2}
                    y={volTop + VOL_H - barH}
                    width={candleW}
                    height={barH}
                    fill={bull ? "#00d97e" : "#f04438"}
                    opacity={isHover ? 0.9 : 0.35}
                  />
                );
              })}
            </>
          )}

          {/* Crosshair */}
          {showCrosshair && hBar && (
            <>
              {/* Vertical line */}
              <line
                x1={xOf(hoverIdx)}
                y1={PAD.top}
                x2={xOf(hoverIdx)}
                y2={PAD.top + totalH}
                stroke="var(--muted)"
                strokeWidth="0.5"
                strokeDasharray="3,3"
              />
              {/* Horizontal line */}
              <line
                x1={PAD.left}
                y1={yOf(hBar.close)}
                x2={PAD.left + W}
                y2={yOf(hBar.close)}
                stroke="var(--muted)"
                strokeWidth="0.5"
                strokeDasharray="3,3"
              />
              {/* Price tag on right axis */}
              <rect
                x={PAD.left + W + 1}
                y={yOf(hBar.close) - 8}
                width={68}
                height={16}
                fill="var(--amber)"
                rx="1"
              />
              <text
                x={PAD.left + W + 4}
                y={yOf(hBar.close) + 4}
                fill="#fff"
                fontSize="10"
                fontFamily="var(--font-mono)"
                fontWeight="600"
              >
                {currencySymbol}
                {hBar.close.toFixed(2)}
              </text>
            </>
          )}

          {/* Current price line (last bar) */}
          {n > 0 && (
            <>
              <line
                x1={PAD.left}
                y1={yOf(data[n - 1].close)}
                x2={PAD.left + W}
                y2={yOf(data[n - 1].close)}
                stroke={data[n - 1].close >= data[0].close ? "#00d97e" : "#f04438"}
                strokeWidth="0.8"
                strokeDasharray="4,4"
                opacity="0.6"
              />
            </>
          )}
        </g>
      </svg>

      {/* Hover tooltip */}
      {showCrosshair && hBar && (
        <div
          style={{
            position: "absolute",
            top: 8,
            left: PAD.left + 4,
            background: "rgba(17,21,32,0.92)",
            border: "1px solid var(--border)",
            borderRadius: 3,
            padding: "6px 10px",
            fontFamily: "var(--font-mono)",
            fontSize: 10,
            color: "var(--text)",
            pointerEvents: "none",
            zIndex: 10,
            lineHeight: "16px",
          }}
        >
          <div style={{ color: "var(--muted)", marginBottom: 2 }}>
            {hBar.date}
          </div>
          <div>
            O{" "}
            <span style={{ color: "var(--bright)" }}>
              {currencySymbol}
              {hBar.open.toFixed(2)}
            </span>{" "}
            H{" "}
            <span style={{ color: "var(--bright)" }}>
              {currencySymbol}
              {hBar.high.toFixed(2)}
            </span>{" "}
            L{" "}
            <span style={{ color: "var(--bright)" }}>
              {currencySymbol}
              {hBar.low.toFixed(2)}
            </span>{" "}
            C{" "}
            <span
              style={{
                color:
                  hBar.close >= hBar.open ? "var(--green)" : "var(--red)",
              }}
            >
              {currencySymbol}
              {hBar.close.toFixed(2)}
            </span>
          </div>
          {showVolume && (
            <div style={{ color: "var(--muted)" }}>
              Vol {fmtVol(hBar.volume)}
            </div>
          )}
          {smaLines.map(
            (sma) =>
              sma.data[hoverIdx]?.value && (
                <div key={sma.period} style={{ color: sma.color }}>
                  SMA{sma.period} {currencySymbol}
                  {sma.data[hoverIdx].value.toFixed(2)}
                </div>
              ),
          )}
        </div>
      )}
    </div>
  );
}
