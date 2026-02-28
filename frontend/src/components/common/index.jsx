/**
 * Common UI Components
 *
 * Exports:
 * - SkeletonRow: Animated loading placeholder for table rows
 * - ApiError: Error display with retry capability
 * - ToastContainer: Toast notification display system
 * - Clock: Real-time clock with timezone display
 * - Footer: Application footer with copyright and links
 * - TickerStrip: Live market ticker strip with auto-refresh
 * - useMarketStatus: Hook to determine NYSE market open/closed status
 */

import { useState, useEffect, useCallback, useRef } from "react";
import api from "../../api/client";
import { Ic } from "./Icons";
import { TICKER_DATA } from "../../styles/globals";

/**
 * SkeletonRow: Animated loading placeholder for table rows
 * Renders a row of animated skeleton elements to simulate content loading
 */
export function SkeletonRow({ cols = 6 }) {
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

/**
 * ApiError: Error display component with optional retry button
 * Shows API error messages prominently with action to retry
 */
export function ApiError({ message, onRetry }) {
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

/**
 * ToastContainer: Toast notification system
 * Displays a stack of toast messages at bottom-right of screen
 */
export function ToastContainer({ toasts }) {
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

/**
 * Clock: Real-time clock component
 * Displays current time with timezone abbreviation, updates every second
 */
export function Clock() {
  const [time, setTime] = useState(() => new Date());
  useEffect(()=>{ const id = setInterval(()=>setTime(new Date()),1000); return ()=>clearInterval(id); },[]);
  const fmt = t => t.toLocaleTimeString("en-US",{hour:"2-digit",minute:"2-digit",second:"2-digit",hour12:false});
  const tzAbbr = time.toLocaleTimeString("en-US", { timeZoneName: "short" }).split(" ").pop();
  return <span className="clock">{fmt(time)} {tzAbbr}</span>;
}

/**
 * Footer: Application footer
 * Displays copyright and legal information
 */
export function Footer() {
  const year = new Date().getFullYear();
  return (
    <footer className="app-footer">
      <span>&copy; {year} Ticker-Tap. All rights reserved.</span>
      <span>Market data provided by Yahoo Finance. Not financial advice.</span>
    </footer>
  );
}

/**
 * TickerStrip: Live market ticker with auto-refresh
 * Displays scrolling ticker with market quotes
 * Refreshes every 3s during market hours, 5m outside hours
 */
export function TickerStrip({ token }) {
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

/**
 * useMarketStatus: Hook to determine NYSE market status
 * Returns: { isOpen, countdown, dateStr, timeStr }
 * - isOpen: boolean indicating if market is currently open (9:30 AM - 4:00 PM ET, weekdays)
 * - countdown: string showing hours/minutes until next market open (if closed)
 * - dateStr: formatted date string
 * - timeStr: formatted time string
 */
export function useMarketStatus() {
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
