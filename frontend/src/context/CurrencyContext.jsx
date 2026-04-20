/**
 * context/CurrencyContext.jsx
 *
 * React Context that manages display currency conversion for TickerTap.
 *
 * Provides:
 *   - `currency`       — current display currency code (e.g. "USD", "EUR")
 *   - `rates`          — exchange rate map { USD: 1.0, EUR: 0.92, ... }
 *   - `formatValue`    — (usdAmount) => formatted string in display currency
 *   - `convertValue`   — (usdAmount) => numeric value in display currency
 *   - `currencySymbol` — symbol for current currency (e.g. "$", "\u20AC")
 *   - `setCurrency`    — setter to change display currency (also persists to backend)
 *
 * All monetary values in TickerTap are stored and transmitted in USD.
 * This context performs display-only conversion — no data is altered.
 *
 * Exchange rates are fetched from GET /market/exchange-rates (ECB data,
 * 1h server-side cache) and refreshed every 60 minutes on the client.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import api from "../api/client";

/* ── Context creation ────────────────────────────────────────────────────── */
const CurrencyContext = createContext(null);

/* ── Currency symbol map ─────────────────────────────────────────────────── */
const CURRENCY_SYMBOLS = {
  USD: "$",
  EUR: "\u20AC",
  GBP: "\u00A3",
  PLN: "z\u0142",
  CHF: "CHF",
  JPY: "\u00A5",
  CAD: "C$",
  AUD: "A$",
};

/* ── Client-side refresh interval (ms) ───────────────────────────────────── */
const RATE_REFRESH_MS = 60 * 60 * 1000; // 1 hour

/**
 * CurrencyProvider — wraps the application tree with currency context.
 *
 * @param {object} props
 * @param {string}        props.token         - JWT access token for API calls
 * @param {string}        props.initialCurrency - initial currency code from user profile
 * @param {React.ReactNode} props.children
 */
export function CurrencyProvider({ token, initialCurrency = "USD", children }) {
  const [currency, setCurrencyState] = useState(initialCurrency);
  const [rates, setRates]           = useState({ USD: 1.0 });

  /* ── Sync when initialCurrency changes (e.g. profile loaded) ────────── */
  useEffect(() => {
    if (initialCurrency) setCurrencyState(initialCurrency);
  }, [initialCurrency]);

  /* ── Fetch exchange rates on mount and every RATE_REFRESH_MS ────────── */
  useEffect(() => {
    if (!token) return;
    let cancelled = false;

    /**
     * fetchRates — retrieves exchange rates from the backend.
     * Falls back to { USD: 1.0 } on error to avoid breaking formatting.
     */
    async function fetchRates() {
      try {
        const data = await api.getExchangeRates(token);
        if (!cancelled && data?.rates) {
          setRates(data.rates);
        }
      } catch {
        // Silently fall back to USD-only rates
      }
    }

    fetchRates();
    const interval = setInterval(fetchRates, RATE_REFRESH_MS);
    return () => { cancelled = true; clearInterval(interval); };
  }, [token]);

  /* ── Listen for preferences-updated events (from SettingsPage) ─────── */
  useEffect(() => {
    /**
     * handlePrefsUpdate — updates local currency state when the user
     * saves new preferences via the Settings page.
     * @param {CustomEvent} e - event with detail.currency
     */
    function handlePrefsUpdate(e) {
      if (e.detail?.currency) {
        setCurrencyState(e.detail.currency);
      }
    }
    window.addEventListener("preferences-updated", handlePrefsUpdate);
    return () => window.removeEventListener("preferences-updated", handlePrefsUpdate);
  }, []);

  /* ── Derived helpers ───────────────────────────────────────────────────── */
  const rate = rates[currency] || 1.0;
  const currencySymbol = CURRENCY_SYMBOLS[currency] || currency;

  /**
   * convertValue — convert a USD amount to the display currency.
   * @param {number} usdAmount - value in USD
   * @returns {number} value in the display currency
   */
  const convertValue = useCallback(
    (usdAmount) => {
      if (typeof usdAmount !== "number" || !isFinite(usdAmount)) return 0;
      return usdAmount * rate;
    },
    [rate],
  );

  /**
   * formatValue — convert a USD amount and format it as a string with
   * the appropriate currency symbol.
   *
   * @param {number} usdAmount   - value in USD
   * @param {object} [opts]
   * @param {number} [opts.decimals=2]     - decimal places
   * @param {boolean} [opts.showSign=false] - include +/- prefix
   * @param {boolean} [opts.compact=false]  - use K/M/B suffixes
   * @returns {string} formatted currency string, e.g. "$1,234.56" or "\u20AC1.134,21"
   */
  const formatValue = useCallback(
    (usdAmount, { decimals = 2, showSign = false, compact = false } = {}) => {
      if (typeof usdAmount !== "number" || !isFinite(usdAmount)) return `${currencySymbol}0`;

      let converted = usdAmount * rate;
      let suffix = "";

      // Compact formatting: K / M / B
      if (compact) {
        const abs = Math.abs(converted);
        if (abs >= 1e9)      { converted /= 1e9; suffix = "B"; }
        else if (abs >= 1e6) { converted /= 1e6; suffix = "M"; }
        else if (abs >= 1e3) { converted /= 1e3; suffix = "K"; }
      }

      // JPY traditionally uses 0 decimal places
      const dec = currency === "JPY" && decimals === 2 ? 0 : decimals;

      const sign = showSign && converted > 0 ? "+" : "";
      const negative = converted < 0;
      const abs = Math.abs(converted);
      const formatted = abs.toLocaleString("en-US", {
        minimumFractionDigits: dec,
        maximumFractionDigits: dec,
      });

      return `${sign}${negative ? "-" : ""}${currencySymbol}${formatted}${suffix}`;
    },
    [rate, currency, currencySymbol],
  );

  /* ── Context value (memoised to prevent unnecessary rerenders) ──────── */
  const value = useMemo(
    () => ({
      currency,
      rates,
      formatValue,
      convertValue,
      currencySymbol,
      setCurrency: setCurrencyState,
    }),
    [currency, rates, formatValue, convertValue, currencySymbol],
  );

  return (
    <CurrencyContext.Provider value={value}>
      {children}
    </CurrencyContext.Provider>
  );
}

/**
 * useCurrency — hook to access currency context from any component.
 *
 * @returns {{ currency, rates, formatValue, convertValue, currencySymbol, setCurrency }}
 */
export function useCurrency() {
  const ctx = useContext(CurrencyContext);
  if (!ctx) {
    // Fallback for components rendered outside the provider (e.g. auth pages)
    return {
      currency: "USD",
      rates: { USD: 1.0 },
      formatValue: (v) => `$${(v || 0).toFixed(2)}`,
      convertValue: (v) => v || 0,
      currencySymbol: "$",
      setCurrency: () => {},
    };
  }
  return ctx;
}
