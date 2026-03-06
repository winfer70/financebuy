/**
 * context/QuotesContext.jsx
 *
 * Shared market quote polling context for TickerTap.
 *
 * Provides a single, deduplicated polling loop that serves all components
 * needing live quote data (TickerStrip, DashboardPage, etc.).
 *
 * How it works:
 *   - Components call `registerSymbols(id, symbols)` on mount to declare
 *     which tickers they need.
 *   - The context merges all registered symbol sets, deduplicates them,
 *     and polls `bulkQuotes` on a market-aware interval (3s open / 5min closed).
 *   - Components read from the shared `quotesMap` — a { symbol: QuoteOut } dict.
 *   - Components call `unregisterSymbols(id)` on unmount to release their symbols.
 *
 * This eliminates:
 *   - Redundant polling (TickerStrip + Dashboard were polling independently)
 *   - Per-symbol HTTP requests (TickerStrip was calling getQuote() per ticker)
 *
 * Props:
 *   @param {string}          token    - JWT access token
 *   @param {React.ReactNode} children
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import api from "../api/client";
import { useMarketStatus } from "../components/common";

/* ── Context creation ────────────────────────────────────────────────────── */
const QuotesContext = createContext(null);

/**
 * QuotesProvider — single polling loop for all live quote consumers.
 *
 * @param {object} props
 * @param {string}          props.token    - JWT access token for API calls
 * @param {React.ReactNode} props.children
 */
export function QuotesProvider({ token, children }) {
  const mktStatus = useMarketStatus();
  const pollMs = mktStatus.isOpen ? 3000 : 300000;

  /* ── Symbol registry: { subscriberId: [symbols] } ──────────────────── */
  const registryRef = useRef({});
  const [mergedSymbols, setMergedSymbols] = useState([]);
  const [quotesMap, setQuotesMap] = useState({});

  /**
   * _recalcMerged — recompute the deduplicated symbol list from all
   * registered subscribers and update state.
   */
  const _recalcMerged = useCallback(() => {
    const all = new Set();
    Object.values(registryRef.current).forEach(syms => {
      syms.forEach(s => all.add(s));
    });
    setMergedSymbols(prev => {
      const next = [...all].sort();
      // Only update if the list actually changed (avoid unnecessary re-renders)
      if (prev.length === next.length && prev.every((s, i) => s === next[i])) return prev;
      return next;
    });
  }, []);

  /**
   * registerSymbols — declare which symbols a component needs.
   *
   * @param {string}   id      - unique subscriber ID (e.g. "tickerstrip", "dashboard")
   * @param {string[]} symbols - array of ticker symbols
   */
  const registerSymbols = useCallback((id, symbols) => {
    registryRef.current[id] = symbols;
    _recalcMerged();
  }, [_recalcMerged]);

  /**
   * unregisterSymbols — remove a subscriber's symbol set.
   *
   * @param {string} id - subscriber ID to remove
   */
  const unregisterSymbols = useCallback((id) => {
    delete registryRef.current[id];
    _recalcMerged();
  }, [_recalcMerged]);

  /* ── Single polling loop: bulkQuotes for all merged symbols ────────── */
  useEffect(() => {
    if (!token || mergedSymbols.length === 0) return;
    let cancelled = false;

    /**
     * fetchAll — single bulkQuotes call for all symbols from all subscribers.
     * Results are stored in quotesMap keyed by symbol.
     */
    const fetchAll = async () => {
      try {
        const quoteList = await api.bulkQuotes(mergedSymbols, token);
        if (cancelled) return;
        const map = {};
        quoteList.forEach(q => { map[q.symbol] = q; });
        setQuotesMap(map);
      } catch {
        /* non-fatal — keep stale data */
      }
    };

    fetchAll();
    const id = setInterval(fetchAll, pollMs);
    return () => { cancelled = true; clearInterval(id); };
  }, [token, mergedSymbols, pollMs]);

  /* ── Context value (memoised) ──────────────────────────────────────── */
  const value = useMemo(
    () => ({ quotesMap, registerSymbols, unregisterSymbols }),
    [quotesMap, registerSymbols, unregisterSymbols],
  );

  return (
    <QuotesContext.Provider value={value}>
      {children}
    </QuotesContext.Provider>
  );
}

/**
 * useQuotes — hook to access the shared quotes context.
 *
 * @returns {{ quotesMap: Object, registerSymbols: Function, unregisterSymbols: Function }}
 */
export function useQuotes() {
  const ctx = useContext(QuotesContext);
  if (!ctx) {
    return {
      quotesMap: {},
      registerSymbols: () => {},
      unregisterSymbols: () => {},
    };
  }
  return ctx;
}
