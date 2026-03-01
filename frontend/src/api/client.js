/**
 * api/client.js
 *
 * Centralised HTTP layer for the TickerTap frontend.
 * Provides a typed `api` object and a generic `useApi` React hook.
 * All JWT injection, 401 handling, and error normalisation live here
 * so that no component ever touches fetch() directly.
 */

import { useState, useEffect, useCallback } from "react";

/* ── Base URL (P7.12, P7.18) ─────────────────────────────────────────────── */
// Default to the current page origin so local dev works without any .env
// configuration (e.g. http://localhost:5173 in dev, proxied to :8000).
// In production, VITE_API_URL points to the backend host.
const _ORIGIN = import.meta.env.VITE_API_URL || window.location.origin;

// All business API routes are versioned under /api/v1 (P7.18 — API versioning).
const API_BASE = `${_ORIGIN}/api/v1`;

/**
 * apiFetch — low-level fetch wrapper.
 *
 * @param {string} path      - API path, e.g. "/auth/login"
 * @param {object} options
 * @param {string} [options.method="GET"]
 * @param {object} [options.body]   - JSON-serialisable request body
 * @param {string} [options.token]  - JWT access token
 * @returns {Promise<any>}  Parsed JSON response
 * @throws  {Error}         On HTTP errors or network failure
 */
export async function apiFetch(path, { method = "GET", body, token } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  // 401 while authenticated → session expired; surface via custom event so
  // AuthContext can respond without a direct import cycle.
  if (res.status === 401 && token) {
    window.dispatchEvent(new Event("session-expired"));
    throw new Error("Session expired");
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

/* ── Typed API surface ───────────────────────────────────────────────────── */
/**
 * api — namespaced API calls.
 * Every method returns a Promise that resolves to parsed JSON.
 */
const api = {
  // ── Auth ────────────────────────────────────────────────────────────────
  /** @param {string} email @param {string} password */
  login: (email, password) =>
    apiFetch("/auth/login", { method: "POST", body: { email, password } }),

  /** @param {object} payload - registration fields */
  register: (payload) =>
    apiFetch("/auth/register", { method: "POST", body: payload }),

  /** @param {string} email */
  forgotPassword: (email) =>
    apiFetch("/auth/forgot-password", { method: "POST", body: { email } }),

  /**
   * @param {string} token      - password-reset token from email link
   * @param {string} new_password
   */
  resetPassword: (token, new_password) =>
    apiFetch("/auth/reset-password", { method: "POST", body: { token, new_password } }),

  // ── Accounts ─────────────────────────────────────────────────────────────
  /** @param {string} userId @param {string} token */
  listAccounts: (userId, token) =>
    apiFetch(`/accounts/me`, { token }),

  // ── Transactions ─────────────────────────────────────────────────────────
  /** @param {string} accountId @param {string} token */
  listTransactions: (accountId, token) =>
    apiFetch(`/transactions/?account_id=${accountId}`, { token }),

  /** @param {object} payload @param {string} token */
  createTransaction: (payload, token) =>
    apiFetch("/transactions/create", { method: "POST", body: payload, token }),

  // ── Holdings ─────────────────────────────────────────────────────────────
  /** @param {string} accountId @param {string} token */
  listHoldings: (accountId, token) =>
    apiFetch(`/holdings/?account_id=${accountId}`, { token }),

  // ── Orders ───────────────────────────────────────────────────────────────
  /** @param {string} accountId @param {string} token */
  listOrders: (accountId, token) =>
    apiFetch(`/orders/?account_id=${accountId}`, { token }),

  /** @param {string} orderId @param {string} token */
  cancelOrder: (orderId, token) =>
    apiFetch(`/orders/${orderId}/cancel`, { method: "POST", token }),

  // ── Market data ──────────────────────────────────────────────────────────
  /** @param {string} symbol @param {string} token */
  getQuote: (symbol, token) =>
    apiFetch(`/market/quote/${symbol}`, { token }),

  /** @param {string} token */
  getSymbols: (token) =>
    apiFetch("/market/symbols", { token }),

  /**
   * @param {string} symbol
   * @param {string} token
   * @param {number} [years=5]
   */
  getOhlcv: (symbol, token, years = 5) =>
    apiFetch(`/market/ohlcv/${symbol}?years=${years}`, { token }),

  /** @param {string} query @param {string} token */
  searchSymbols: (query, token) =>
    apiFetch(`/market/search?q=${encodeURIComponent(query)}`, { token }),

  // ── Portfolio ────────────────────────────────────────────────────────────
  /** @param {string} token */
  getPositions: (token) => apiFetch("/portfolio/positions", { token }),

  /** @param {string} token */
  getPortfolioSummary: (token) => apiFetch("/portfolio/summary", { token }),

  // ── Auth refresh / logout (P6.3) ─────────────────────────────────────────
  /**
   * Obtain a new access token using the httpOnly refresh cookie.
   * The browser sends the cookie automatically; no token argument needed.
   */
  refreshToken: () =>
    apiFetch("/auth/refresh", { method: "POST" }),

  /** @param {string} token - current access token */
  logout: (token) =>
    apiFetch("/auth/logout", { method: "POST", token }),

  // ── Health (unversioned — stays at /health not /api/v1/health) ──────────
  health: () => fetch(`${_ORIGIN}/health`).then((r) => r.json()),
};

export default api;

/* ── useApi hook ─────────────────────────────────────────────────────────── */
/**
 * useApi — generic data-fetching hook with loading / error / refetch.
 *
 * @param {Function} fetcher   - zero-argument async function returning data
 * @param {Array}    [deps=[]] - dependency array (same semantics as useEffect)
 * @returns {{ data: any, loading: boolean, error: string|null, refetch: Function }}
 *
 * @example
 *   const { data, loading, error, refetch } = useApi(
 *     () => api.listOrders(accountId, token),
 *     [accountId, token]
 *   );
 */
export function useApi(fetcher, deps = []) {
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetcher());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => { refetch(); }, [refetch]);

  return { data, loading, error, refetch };
}
