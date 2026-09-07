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

/* ── Token refresh lock ───────────────────────────────────────────────────
 * When a 401 is received, we attempt a silent token refresh via the httpOnly
 * refresh cookie. _refreshLock ensures that if multiple API calls 401 at the
 * same time, only ONE refresh request is made; the others await the same
 * promise. Resets to null after the refresh completes (success or failure).
 */
let _refreshLock = null;

/**
 * _tryRefreshToken — Attempt to obtain a new access token using the
 * httpOnly refresh cookie. Returns the new token on success, null on failure.
 *
 * @returns {Promise<string|null>} New access token or null
 */
async function _tryRefreshToken() {
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",   // Browser sends the httpOnly tickertap_refresh cookie
    });
    if (!res.ok) return null;
    const data = await res.json();
    // Persist the new token so AuthContext and page router stay in sync
    if (data.access_token) {
      sessionStorage.setItem("tickertap_token", data.access_token);
      return data.access_token;
    }
    return null;
  } catch {
    return null;
  }
}

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
    credentials: "include",   // Send httpOnly refresh cookie on /auth/refresh
    body: body ? JSON.stringify(body) : undefined,
  });

  // 401 while authenticated → attempt a silent token refresh before giving up.
  // If the refresh succeeds, retry the original request with the new token.
  // If it fails, dispatch session-expired so AuthContext redirects to login.
  if (res.status === 401 && token) {
    // Coalesce concurrent refresh attempts behind a single promise
    if (!_refreshLock) {
      _refreshLock = _tryRefreshToken().finally(() => { _refreshLock = null; });
    }
    const newToken = await _refreshLock;

    if (newToken) {
      // Retry the original request with the fresh token (non-recursive to
      // avoid infinite loops — if this retry 401s, we fall through below).
      const retryHeaders = { ...headers, Authorization: `Bearer ${newToken}` };
      const retry = await fetch(`${API_BASE}${path}`, {
        method,
        headers: retryHeaders,
        credentials: "include",
        body: body ? JSON.stringify(body) : undefined,
      });
      if (retry.ok) {
        if (retry.status === 204) return null;
        return retry.json();
      }
    }

    // Refresh failed or retried request still 401 — session is truly expired
    window.dispatchEvent(new Event("session-expired"));
    throw new Error("Session expired");
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    let msg = err.detail;
    if (Array.isArray(msg)) msg = msg.map(e => e.msg || JSON.stringify(e)).join("; ");
    throw new Error(msg || `HTTP ${res.status}`);
  }

  // 204 No Content — return null (no body to parse)
  if (res.status === 204) return null;

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

  getOhlcvInterval: (symbol, token, interval = "1d", days = 365) =>
    apiFetch(`/market/ohlcv_interval/${symbol}?interval=${interval}&days=${days}`, { token }),

  /**
   * Fetch comprehensive fundamental data for a symbol (valuation, financials,
   * dividends, analyst targets, trading info, etc.).  Cached on the backend.
   *
   * @param {string} symbol - Ticker symbol (e.g. "AAPL")
   * @param {string} token  - JWT access token
   * @returns {Promise<object>} Fundamental data object
   */
  getFundamentals: (symbol, token) =>
    apiFetch(`/market/fundamentals/${encodeURIComponent(symbol)}`, { token }),

  /**
   * Fetch financial events (earnings, dividends, splits) and analyst
   * target prices for a symbol.  Cached for 1 hour on the backend.
   *
   * @param {string} symbol - Ticker symbol (e.g. "AAPL")
   * @param {string} token  - JWT access token
   * @returns {Promise<{symbol: string, events: Array, target_mean: number|null, target_high: number|null, target_low: number|null}>}
   */
  getEvents: (symbol, token) =>
    apiFetch(`/market/events/${encodeURIComponent(symbol)}`, { token }),

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

  // ── Portfolio Manager ─────────────────────────────────────────────────────
  listPortfolios: (token) =>
    apiFetch("/portfolio-manager/portfolios", { token }),

  createPortfolio: (payload, token) =>
    apiFetch("/portfolio-manager/portfolios", { method: "POST", body: payload, token }),

  deletePortfolio: (portfolioId, token) =>
    apiFetch(`/portfolio-manager/portfolios/${portfolioId}`, { method: "DELETE", token }),

  listPositions: (portfolioId, token) =>
    apiFetch(`/portfolio-manager/portfolios/${portfolioId}/positions`, { token }),

  addPosition: (portfolioId, payload, token) =>
    apiFetch(`/portfolio-manager/portfolios/${portfolioId}/positions`, { method: "POST", body: payload, token }),

  importPositions: (portfolioId, positions, token) =>
    apiFetch(`/portfolio-manager/portfolios/${portfolioId}/import`, { method: "POST", body: positions, token }),

  modifyPosition: (positionId, payload, token) =>
    apiFetch(`/portfolio-manager/positions/${positionId}`, { method: "PATCH", body: payload, token }),

  deletePosition: (positionId, token) =>
    apiFetch(`/portfolio-manager/positions/${positionId}`, { method: "DELETE", token }),

  sellPosition: (positionId, quantity, sellPrice, token, creditCash = true) =>
    apiFetch(`/portfolio-manager/positions/${positionId}/sell`, { method: "POST", body: { quantity, sell_price: sellPrice, credit_cash: creditCash }, token }),

  /**
   * Fetch portfolio performance time series from the backend.
   * The backend computes daily portfolio value with forward-fill for
   * missing dates (weekends/holidays) and dynamic "ALL" range.
   *
   * @param {string} portfolioId - Portfolio UUID
   * @param {string} period      - Time range: 1W, 1M, 3M, YTD, 1Y, ALL
   * @param {string} token       - JWT auth token
   * @returns {Promise<Array<{date: string, value: number}>>} Time series data points
   */
  getPortfolioPerformance: (portfolioId, period, token) =>
    apiFetch(`/portfolio-manager/${portfolioId}/performance?period=${encodeURIComponent(period)}`, { token }),

  bulkQuotes: (symbols, token) =>
    apiFetch(`/market/bulk_quotes?symbols=${symbols.join(",")}`, { token }),

  priceChange: (symbol, period, token) =>
    apiFetch(`/market/price_change?symbol=${encodeURIComponent(symbol)}&period=${period}`, { token }),

  bulkSma: (symbols, period, token) =>
    apiFetch(`/market/bulk_sma?symbols=${symbols.join(",")}&period=${period}`, { token }),

  // ── Chart Templates ────────────────────────────────────────────────────────
  listChartTemplates: (token) =>
    apiFetch("/chart-templates/", { token }),

  createChartTemplate: (payload, token) =>
    apiFetch("/chart-templates/", { method: "POST", body: payload, token }),

  updateChartTemplate: (templateId, payload, token) =>
    apiFetch(`/chart-templates/${templateId}`, { method: "PATCH", body: payload, token }),

  deleteChartTemplate: (templateId, token) =>
    apiFetch(`/chart-templates/${templateId}`, { method: "DELETE", token }),

  // ── News ──────────────────────────────────────────────────────────────────
  /**
   * Fetch a paginated, LLM-scored news feed from the DB with optional
   * server-side filters.  Filters are applied before pagination so that
   * total counts and page offsets stay consistent.
   *
   * Returns { articles, total, limit, offset }.
   *
   * @param {string} token   - JWT access token
   * @param {object} [opts]  - Optional filter / pagination parameters
   * @param {number} [opts.limit=25]             - Articles per page (25, 50, 75, or 100)
   * @param {number} [opts.offset=0]             - Number of articles to skip
   * @param {string|null} [opts.portfolio_tickers=null] - Comma-separated portfolio ticker symbols
   * @param {boolean} [opts.portfolio_only=false] - Filter to user's portfolio tickers (server-derived)
   * @param {string|null} [opts.sentiment=null]   - "bullish" or "bearish"
   * @param {string|null} [opts.ticker_search=null] - Search by ticker or title
   */
  getNews: (token, { limit = 25, offset = 0, portfolio_tickers = null, portfolio_only = false, sentiment = null, ticker_search = null } = {}) => {
    /* Build URL with pagination and optional filter query parameters. */
    let url = `/news/feed?limit=${limit}&offset=${offset}`;
    if (portfolio_tickers) url += `&portfolio_tickers=${encodeURIComponent(portfolio_tickers)}`;
    if (portfolio_only) url += `&portfolio_only=true`;
    if (sentiment) url += `&sentiment=${encodeURIComponent(sentiment)}`;
    if (ticker_search) url += `&ticker_search=${encodeURIComponent(ticker_search)}`;
    return apiFetch(url, { token });
  },

  /**
   * Fetch paginated news articles filtered by a single ticker symbol.
   * Returns { articles, total, limit, offset }.
   * @param {string} ticker - Stock ticker symbol (e.g. "AAPL")
   * @param {string} token  - JWT access token
   * @param {number} limit  - Articles per page (25, 50, 75, or 100)
   * @param {number} offset - Number of articles to skip
   */
  getNewsByTicker: (ticker, token, limit = 25, offset = 0) =>
    apiFetch(`/news/tickers/${encodeURIComponent(ticker)}?limit=${limit}&offset=${offset}`, { token }),

  // ── Insider (Form 4) ───────────────────────────────────────────────────────
  /**
   * Paginated Form 4 filings with sort/filter.
   * @returns {Promise<{total: number, items: Array}>}
   */
  getInsiderFilings: (token, {
    ticker = null, owner_cik = null, code = null, days = 90,
    sort = "transaction_date", order = "desc", limit = 50, offset = 0,
  } = {}) => {
    let url = `/insider/filings?days=${days}&sort=${encodeURIComponent(sort)}&order=${encodeURIComponent(order)}&limit=${limit}&offset=${offset}`;
    if (ticker) url += `&ticker=${encodeURIComponent(ticker)}`;
    if (owner_cik) url += `&owner_cik=${encodeURIComponent(owner_cik)}`;
    if (code) url += `&code=${encodeURIComponent(code)}`;
    return apiFetch(url, { token });
  },

  /**
   * Per-person Form 4 breakdown (buys/sells, cadence, 10b5-1 share).
   */
  getInsiderOwner: (ownerCik, token, { ticker = null, days = 365 } = {}) => {
    let url = `/insider/owners/${encodeURIComponent(ownerCik)}?days=${days}`;
    if (ticker) url += `&ticker=${encodeURIComponent(ticker)}`;
    return apiFetch(url, { token });
  },

  // ── Guide ──────────────────────────────────────────────────────────────────
  /**
   * Submit a question to the AI guide (Ollama proxy).
   * @param {string} question - User question text (1-500 chars)
   * @param {string} token    - JWT access token
   * @returns {Promise<{answer: string, model: string}>}
   */
  askGuide: (question, token) =>
    apiFetch("/guide/ask", { method: "POST", body: { question }, token }),

  // ── User Profile & Preferences ────────────────────────────────────────────
  /**
   * Fetch the authenticated user's profile including preferences.
   * @param {string} token - JWT access token
   * @returns {Promise<{email, first_name, last_name, phone, user_id, kyc_status, is_active, preferences}>}
   */
  getProfile: (token) =>
    apiFetch("/auth/me", { token }),

  /**
   * Update the authenticated user's display preferences (currency, language).
   * Only provided fields are merged into the existing preferences.
   * @param {object} payload  - { currency?: string, language?: string }
   * @param {string} token    - JWT access token
   * @returns {Promise<{currency: string, language: string}>}
   */
  updatePreferences: (payload, token) =>
    apiFetch("/auth/preferences", { method: "PATCH", body: payload, token }),

  // ── Exchange Rates ────────────────────────────────────────────────────────
  /**
   * Fetch current exchange rates from the backend (ECB data, 1h cache).
   * Base currency is always USD, returns rates for all supported currencies.
   * @param {string} token - JWT access token
   * @returns {Promise<{base: string, rates: object, timestamp: string}>}
   */
  getExchangeRates: (token) =>
    apiFetch("/market/exchange-rates", { token }),

  // ── Reports ──────────────────────────────────────────────────────────────
  /**
   * Submit a new report. Authentication is optional.
   * @param {object}      payload      - Report data
   * @param {string|null} [token=null] - JWT access token (optional)
   * @returns {Promise<object>} Created report
   */
  submitReport: (payload, token = null) =>
    apiFetch("/reports", { method: "POST", body: payload, token }),

  // ── Email Verification ─────────────────────────────────────────────────
  /**
   * Verify a user's email address using the token from the verification link.
   * @param {string} token - Email verification token
   * @returns {Promise<object>}
   */
  verifyEmail: (token) =>
    apiFetch("/auth/verify-email", { method: "POST", body: { token } }),

  /**
   * Resend the email verification link to the given address.
   * @param {string} email - User's email address
   * @returns {Promise<object>}
   */
  resendVerification: (email) =>
    apiFetch("/auth/resend-verification", { method: "POST", body: { email } }),

  // ── Account Lifecycle ──────────────────────────────────────────────────
  /**
   * Deactivate the authenticated user's account.
   * @param {string} password - Current password for confirmation
   * @param {string} token    - JWT access token
   * @returns {Promise<object>}
   */
  deactivateAccount: (password, token) =>
    apiFetch("/auth/deactivate", { method: "POST", body: { password }, token }),

  /**
   * Request a reactivation link for a deactivated account.
   * @param {string} email - Email of the deactivated account
   * @returns {Promise<object>}
   */
  requestReactivation: (email) =>
    apiFetch("/auth/request-reactivation", { method: "POST", body: { email } }),

  /**
   * Reactivate a deactivated account using the token from the reactivation link.
   * @param {string} token - Reactivation token
   * @returns {Promise<object>}
   */
  reactivateAccount: (token) =>
    apiFetch("/auth/reactivate", { method: "POST", body: { token } }),

  /**
   * Request permanent deletion of the authenticated user's account.
   * @param {string} mode     - Deletion mode (e.g. "soft", "hard")
   * @param {string} password - Current password for confirmation
   * @param {string} token    - JWT access token
   * @returns {Promise<object>}
   */
  deleteAccount: (mode, password, token) =>
    apiFetch("/auth/delete-account", { method: "POST", body: { mode, password }, token }),

  /**
   * Cancel a pending account deletion using the token from the cancellation link.
   * @param {string} token - Deletion cancellation token
   * @returns {Promise<object>}
   */
  cancelDeletion: (token) =>
    apiFetch("/auth/cancel-deletion", { method: "POST", body: { token } }),

  // ── Watchlists ────────────────────────────────────────────────────────────

  /**
   * Create a new watchlist for the authenticated user.
   * @param {object} body  - Watchlist data (e.g. { name: "Tech Stocks" })
   * @param {string} token - JWT access token
   * @returns {Promise<object>} Created watchlist
   */
  createWatchlist: (body, token) =>
    apiFetch("/watchlists", { method: "POST", body, token }),

  /**
   * List all watchlists belonging to the authenticated user.
   * @param {string} token - JWT access token
   * @returns {Promise<Array<object>>} Array of watchlist objects
   */
  getWatchlists: (token) =>
    apiFetch("/watchlists", { token }),

  /**
   * Get a single watchlist with its items.
   * @param {string} id    - Watchlist ID
   * @param {string} token - JWT access token
   * @returns {Promise<object>} Watchlist with items array
   */
  getWatchlist: (id, token) =>
    apiFetch(`/watchlists/${id}`, { token }),

  /**
   * Rename an existing watchlist.
   * @param {string} id    - Watchlist ID
   * @param {object} body  - Rename data (e.g. { name: "New Name" })
   * @param {string} token - JWT access token
   * @returns {Promise<object>} Updated watchlist
   */
  renameWatchlist: (id, body, token) =>
    apiFetch(`/watchlists/${id}`, { method: "PATCH", body, token }),

  /**
   * Delete a watchlist and all its items.
   * @param {string} id    - Watchlist ID
   * @param {string} token - JWT access token
   * @returns {Promise<null>} Null on success (204)
   */
  deleteWatchlist: (id, token) =>
    apiFetch(`/watchlists/${id}`, { method: "DELETE", token }),

  /**
   * Add an item (symbol) to a watchlist.
   * @param {string} watchlistId - Watchlist ID
   * @param {object} body        - Item data (e.g. { symbol, asset_type, notes })
   * @param {string} token       - JWT access token
   * @returns {Promise<object>} Created watchlist item
   */
  addWatchlistItem: (watchlistId, body, token) =>
    apiFetch(`/watchlists/${watchlistId}/items`, { method: "POST", body, token }),

  /**
   * Update a watchlist item (e.g. edit notes).
   * @param {string} watchlistId - Watchlist ID
   * @param {string} itemId      - Watchlist item ID
   * @param {object} body        - Fields to update (e.g. { notes })
   * @param {string} token       - JWT access token
   * @returns {Promise<object>} Updated watchlist item
   */
  updateWatchlistItem: (watchlistId, itemId, body, token) =>
    apiFetch(`/watchlists/${watchlistId}/items/${itemId}`, { method: "PATCH", body, token }),

  /**
   * Remove an item from a watchlist.
   * @param {string} watchlistId - Watchlist ID
   * @param {string} itemId      - Watchlist item ID
   * @param {string} token       - JWT access token
   * @returns {Promise<null>} Null on success (204)
   */
  removeWatchlistItem: (watchlistId, itemId, token) =>
    apiFetch(`/watchlists/${watchlistId}/items/${itemId}`, { method: "DELETE", token }),

  /**
   * Buy from a watchlist item into a portfolio.
   * Creates a portfolio position from a watched symbol.
   * @param {string} watchlistId - Watchlist ID
   * @param {string} itemId      - Watchlist item ID
   * @param {object} body        - Buy data (e.g. { portfolio_id, quantity, price, date })
   * @param {string} token       - JWT access token
   * @returns {Promise<object>} Created portfolio position
   */
  buyFromWatchlist: (watchlistId, itemId, body, token) =>
    apiFetch(`/watchlists/${watchlistId}/items/${itemId}/buy`, { method: "POST", body, token }),

  // ── Profile Management ─────────────────────────────────────────────────
  /**
   * Update the authenticated user's profile fields.
   * Only provided fields are merged into the existing profile.
   * @param {object} payload - Profile fields to update
   * @param {string} token   - JWT access token
   * @returns {Promise<object>} Updated profile
   */
  updateProfile: (payload, token) =>
    apiFetch("/auth/profile", { method: "PATCH", body: payload, token }),

  /**
   * Initiate an email address change for the authenticated user.
   * A confirmation link is sent to the new address.
   * @param {string} newEmail - Desired new email address
   * @param {string} password - Current password for confirmation
   * @param {string} token    - JWT access token
   * @returns {Promise<object>}
   */
  changeEmail: (newEmail, password, token) =>
    apiFetch("/auth/change-email", { method: "POST", body: { new_email: newEmail, password }, token }),

  /**
   * Confirm an email address change using the token from the confirmation link.
   * @param {string} token - Email change confirmation token
   * @returns {Promise<object>}
   */
  confirmEmailChange: (token) =>
    apiFetch("/auth/confirm-email-change", { method: "POST", body: { token } }),

  // ── Trading AI ────────────────────────────────────────────────────────────

  /** List available strategies (built-in + user-created). */
  listStrategies: (token) =>
    apiFetch("/trading/strategies", { token }),

  /** Create a new custom strategy. */
  createStrategy: (body, token) =>
    apiFetch("/trading/strategies", { method: "POST", body, token }),

  /** Update an existing strategy. */
  updateStrategy: (strategyId, body, token) =>
    apiFetch(`/trading/strategies/${strategyId}`, { method: "PATCH", body, token }),

  /** Delete a strategy. */
  deleteStrategy: (strategyId, token) =>
    apiFetch(`/trading/strategies/${strategyId}`, { method: "DELETE", token }),

  /** Clone a strategy. */
  cloneStrategy: (strategyId, token) =>
    apiFetch(`/trading/strategies/${strategyId}/clone`, { method: "POST", token }),

  /** Queue a backtest job. Returns { backtest_id }. */
  queueBacktest: (body, token) =>
    apiFetch("/trading/backtest", { method: "POST", body, token }),

  /** Poll backtest status/result. */
  getBacktestResult: (backtestId, token) =>
    apiFetch(`/trading/backtest/${backtestId}`, { token }),

  /** Get backtest history for the current user. */
  listBacktests: (token) =>
    apiFetch("/trading/backtest/history", { token }),

  /** Get active signals for a strategy. */
  getSignals: (strategyId, token) =>
    apiFetch(`/trading/signals/${strategyId}`, { token }),

  /** Get signals for a specific symbol across all strategies. */
  getSignalsBySymbol: (symbol, token) =>
    apiFetch(`/trading/signals/symbol/${symbol}`, { token }),

  // ── Price Alerts ────────────────────────────────────────────────────────

  /** Create a new price alert. */
  createAlert: (body, token) =>
    apiFetch("/alerts", { method: "POST", body, token }),

  /** List user's price alerts. */
  listAlerts: (activeOnly, token) =>
    apiFetch(`/alerts?active_only=${activeOnly ? "true" : "false"}`, { token }),

  /** Update an existing price alert. */
  updateAlert: (alertId, body, token) =>
    apiFetch(`/alerts/${alertId}`, { method: "PATCH", body, token }),

  /** Delete a price alert. */
  deleteAlert: (alertId, token) =>
    apiFetch(`/alerts/${alertId}`, { method: "DELETE", token }),

  // ── Notifications ───────────────────────────────────────────────────────

  /** List notifications (paginated). */
  listNotifications: (params = {}, token) => {
    const qs = new URLSearchParams();
    if (params.limit) qs.set("limit", params.limit);
    if (params.offset) qs.set("offset", params.offset);
    if (params.unread_only) qs.set("unread_only", "true");
    return apiFetch(`/trading/notifications?${qs}`, { token });
  },

  /** Mark specific notifications as read. */
  markNotificationsRead: (notificationIds, token) =>
    apiFetch("/trading/notifications/read", { method: "POST", body: { notification_ids: notificationIds }, token }),

  /** Mark all notifications as read. */
  markAllNotificationsRead: (token) =>
    apiFetch("/trading/notifications/read-all", { method: "POST", token }),

  // ── Webhooks ────────────────────────────────────────────────────────────

  /** List user's webhooks. */
  listWebhooks: (token) =>
    apiFetch("/trading/webhooks", { token }),

  /** Create a new webhook. */
  createWebhook: (body, token) =>
    apiFetch("/trading/webhooks", { method: "POST", body, token }),

  /** Update a webhook. */
  updateWebhook: (webhookId, body, token) =>
    apiFetch(`/trading/webhooks/${webhookId}`, { method: "PATCH", body, token }),

  /** Delete a webhook. */
  deleteWebhook: (webhookId, token) =>
    apiFetch(`/trading/webhooks/${webhookId}`, { method: "DELETE", token }),

  // ── Market Regime ─────────────────────────────────────────────────────

  /**
   * Detect the current market regime for a symbol.
   * @param {object} body  - { symbol, interval?, period_days? }
   * @param {string} token - JWT access token
   * @returns {Promise<{symbol, regime, confidence, volatility_percentile, trend_strength}>}
   */
  detectRegime: (body, token) =>
    apiFetch("/trading/regime", { method: "POST", body, token }),

  // ── PineScript ─────────────────────────────────────────────────────

  /** Validate PineScript syntax. */
  validatePinescript: (sourceCode, token) =>
    apiFetch("/trading/pinescript/validate", { method: "POST", body: { source_code: sourceCode }, token }),

  /** Transpile PineScript and create a strategy. */
  transpilePinescript: (body, token) =>
    apiFetch("/trading/pinescript/transpile", { method: "POST", body, token }),

  // ── Strategy Composition ──────────────────────────────────────────

  /** Create a composed strategy from indicator nodes + expressions. */
  createComposedStrategy: (body, token) =>
    apiFetch("/trading/compose", { method: "POST", body, token }),

  // ── Strategy Version History ──────────────────────────────────────

  /** List version history for a strategy. */
  listStrategyVersions: (strategyId, token) =>
    apiFetch(`/trading/strategies/${strategyId}/versions`, { token }),

  /** Get a specific version of a strategy. */
  getStrategyVersion: (strategyId, versionNumber, token) =>
    apiFetch(`/trading/strategies/${strategyId}/versions/${versionNumber}`, { token }),

  /** Revert a strategy to a previous version. */
  revertStrategyVersion: (strategyId, versionNumber, token) =>
    apiFetch(`/trading/strategies/${strategyId}/revert/${versionNumber}`, { method: "POST", token }),

  // ── Marketplace ───────────────────────────────────────────────────────

  /** Browse public strategy marketplace (paginated, filterable). */
  browseMarketplace: (params, token) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch(`/trading/marketplace?${qs}`, { token });
  },

  /** Get top-10 featured public strategies. */
  getFeaturedStrategies: (token) =>
    apiFetch("/trading/marketplace/featured", { token }),

  /** Rate a public strategy (upsert — stars 1-5, optional review). */
  rateStrategy: (strategyId, body, token) =>
    apiFetch(`/trading/strategies/${strategyId}/rate`, { method: "POST", body, token }),

  /** List ratings for a strategy (paginated). */
  getStrategyRatings: (strategyId, params, token) => {
    const qs = params ? new URLSearchParams(params).toString() : "";
    return apiFetch(`/trading/strategies/${strategyId}/ratings${qs ? `?${qs}` : ""}`, { token });
  },

  /** Get aggregate stats for a strategy (clones, rating, backtests). */
  getStrategyStats: (strategyId, token) =>
    apiFetch(`/trading/strategies/${strategyId}/stats`, { token }),

  /** Toggle a strategy's public/private visibility (owner only). */
  publishStrategy: (strategyId, token) =>
    apiFetch(`/trading/strategies/${strategyId}/publish`, { method: "POST", token }),

  // ── Backtest Export & Batch ───────────────────────────────────────────

  /** Export backtest results as CSV (returns blob). */
  exportBacktest: async (resultId, format, token) => {
    const resp = await fetch(`/api/v1/trading/backtest/${resultId}/export?format=${format}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resp.ok) throw new Error("Export failed");
    return resp.blob();
  },

  /** Queue backtests for a strategy across multiple symbols. */
  queueBatchBacktest: (body, token) =>
    apiFetch("/trading/backtest/batch", { method: "POST", body, token }),

  // ── Orders (create) ───────────────────────────────────────────────────

  /** Create a new order. */
  createOrder: (body, token) =>
    apiFetch("/orders/", { method: "POST", body, token }),

  // ── Paper Trading ────────────────────────────────────────────────────

  /**
   * Start a new paper trading session.
   * @param {object} body  - { strategy_slug, symbol, initial_capital }
   * @param {string} token - JWT access token
   * @returns {Promise<object>} Created paper trade
   */
  startPaperTrade: (body, token) =>
    apiFetch("/trading/paper", { method: "POST", body, token }),

  /**
   * List all paper trades for the authenticated user.
   * @param {string} token - JWT access token
   * @returns {Promise<Array<object>>} Array of paper trade objects
   */
  listPaperTrades: (token) =>
    apiFetch("/trading/paper", { token }),

  /**
   * Get details for a single paper trade.
   * @param {string} id    - Paper trade ID
   * @param {string} token - JWT access token
   * @returns {Promise<object>} Paper trade detail
   */
  getPaperTrade: (id, token) =>
    apiFetch(`/trading/paper/${id}`, { token }),

  /**
   * Pause an active paper trade.
   * @param {string} id    - Paper trade ID
   * @param {string} token - JWT access token
   * @returns {Promise<object>} Updated paper trade
   */
  pausePaperTrade: (id, token) =>
    apiFetch(`/trading/paper/${id}/pause`, { method: "POST", token }),

  /**
   * Resume a paused paper trade.
   * @param {string} id    - Paper trade ID
   * @param {string} token - JWT access token
   * @returns {Promise<object>} Updated paper trade
   */
  resumePaperTrade: (id, token) =>
    apiFetch(`/trading/paper/${id}/resume`, { method: "POST", token }),

  /**
   * Stop (terminate) a paper trade permanently.
   * @param {string} id    - Paper trade ID
   * @param {string} token - JWT access token
   * @returns {Promise<object>} Updated paper trade
   */
  stopPaperTrade: (id, token) =>
    apiFetch(`/trading/paper/${id}/stop`, { method: "POST", token }),

  /**
   * Delete a stopped paper trade and all its associated data.
   * @param {string} paperTradeId - Paper trade ID
   * @param {string} token        - JWT access token
   * @returns {Promise<null>} Null on success (204)
   */
  deletePaperTrade: (paperTradeId, token) =>
    apiFetch(`/trading/paper/${paperTradeId}`, { method: "DELETE", token }),

  /**
   * Update an active or paused paper trade's capital and/or parameters.
   * @param {string} paperTradeId - Paper trade ID
   * @param {object} body         - { initial_capital?, parameters? }
   * @param {string} token        - JWT access token
   * @returns {Promise<object>} Updated paper trade
   */
  updatePaperTrade: (paperTradeId, body, token) =>
    apiFetch(`/trading/paper/${paperTradeId}`, { method: "PATCH", body, token }),

  /**
   * Fetch equity snapshots (time series) for a paper trade.
   * @param {string} id    - Paper trade ID
   * @param {string} token - JWT access token
   * @returns {Promise<Array<{timestamp: string, equity: number}>>} Equity curve data
   */
  getPaperEquity: (id, token) =>
    apiFetch(`/trading/paper/${id}/equity`, { token }),

  /**
   * Fetch position history for a paper trade.
   * @param {string} id    - Paper trade ID
   * @param {string} token - JWT access token
   * @returns {Promise<Array<object>>} Position history records
   */
  getPaperPositions: (id, token) =>
    apiFetch(`/trading/paper/${id}/positions`, { token }),

  /**
   * Score a portfolio of symbols with technical analysis.
   * Returns overall score, per-symbol breakdowns with trend, RSI, volatility, signal.
   * @param {object} body  - { symbols: ["AAPL", "MSFT", ...] }
   * @param {string} token - JWT access token
   * @returns {Promise<object>} Portfolio scoring results
   */
  scorePortfolio: (body, token) =>
    apiFetch("/trading/portfolio-score", { method: "POST", body, token }),

  /**
   * Score a portfolio with extended P&L analysis using position details.
   * Passes full position data (ticker, quantity, purchase_price, stop_loss,
   * profit_taking) so the backend can compute unrealised P&L and stop-loss
   * status for each position.
   *
   * @param {Array<{ticker, quantity, purchase_price, stop_loss, profit_taking}>} positions
   * @param {string} token - JWT access token
   * @returns {Promise<object>} Extended portfolio scoring results
   */
  scorePortfolioDetailed: (positions, token) =>
    apiFetch("/trading/portfolio-score", {
      method: "POST",
      body: { symbols: positions.map(p => p.ticker), positions },
      token,
    }),

  /**
   * Fetch trade history for a portfolio.
   * @param {string} portfolioId - Portfolio UUID
   * @param {string} token       - JWT access token
   * @returns {Promise<Array<object>>} Array of trade records
   */
  getPortfolioTrades: (portfolioId, token) =>
    apiFetch(`/portfolio-manager/${portfolioId}/trades`, { token }),

  /**
   * Delete a trade record by ID.
   * Ownership is verified server-side via the parent portfolio.
   * @param {string} tradeId - Trade UUID
   * @param {string} token   - JWT access token
   * @returns {Promise<null>} Null on success (204)
   */
  deleteTrade: (tradeId, token) =>
    apiFetch(`/portfolio-manager/trades/${tradeId}`, { method: "DELETE", token }),

  /**
   * Manually adjust a portfolio's cash balance.
   * @param {string}      portfolioId - Portfolio UUID
   * @param {number}      amount      - Positive to add, negative to subtract
   * @param {string|null} notes       - Optional note
   * @param {string}      token       - JWT access token
   * @returns {Promise<{cash_balance: number}>} Updated cash balance
   */
  adjustPortfolioCash: (portfolioId, amount, notes = null, token) =>
    apiFetch(`/portfolio-manager/${portfolioId}/cash`, {
      method: "POST",
      body: { amount, notes },
      token,
    }),

  /**
   * Trigger portfolio rules evaluation for a portfolio.
   * @param {string} portfolioId - Portfolio UUID
   * @param {string} schedule    - "on_demand" | "market_hours" | "end_of_day"
   * @param {string} token       - JWT access token
   * @returns {Promise<object>} PortfolioRulesRunResponse with task_id
   */
  runPortfolioRules: (portfolioId, schedule, token) =>
    apiFetch(`/portfolio-manager/portfolios/${portfolioId}/run-rules`, {
      method: "POST",
      body: { schedule },
      token,
    }),

  /**
   * List rule alerts for a portfolio with optional filters.
   * @param {string}      portfolioId - Portfolio UUID
   * @param {object}      [filters]   - { severity, state, rule_type }
   * @param {string}      token       - JWT access token
   * @returns {Promise<Array>} List of RuleAlertResponse objects
   */
  getRuleAlerts: (portfolioId, { severity = null, state = null, rule_type = null } = {}, token) => {
    const params = new URLSearchParams();
    if (severity)  params.set("severity",  severity);
    if (state)     params.set("state",     state);
    if (rule_type) params.set("rule_type", rule_type);
    const qs = params.toString();
    return apiFetch(`/portfolio-manager/portfolios/${portfolioId}/rule-alerts${qs ? "?" + qs : ""}`, { token });
  },

  /**
   * Patch a rule alert state.
   * @param {string} alertId - Alert UUID
   * @param {object} payload - { state: "snoozed"|"actioned"|"expired" }
   * @param {string} token   - JWT access token
   * @returns {Promise<object>} Updated RuleAlertResponse
   */
  patchRuleAlert: (alertId, payload, token) =>
    apiFetch(`/portfolio-manager/rule-alerts/${alertId}`, { method: "PATCH", body: payload, token }),

  /**
   * Get user's portfolio rules configuration.
   * @param {string} token - JWT access token
   * @returns {Promise<object>} PortfolioRulesConfig
   */
  getRuleConfig: (token) =>
    apiFetch("/portfolio-manager/rule-config", { token }),

  /**
   * Update user's portfolio rules configuration.
   * @param {object} payload - Config fields to update
   * @param {string} token   - JWT access token
   * @returns {Promise<object>} Updated PortfolioRulesConfig
   */
  patchRuleConfig: (payload, token) =>
    apiFetch("/portfolio-manager/rule-config", { method: "PATCH", body: payload, token }),

  /**
   * Run exit analysis for a symbol — computes ATR stops, Bollinger levels,
   * moving-average support/resistance, Fibonacci retracements, and more.
   *
   * @param {object} body  - { symbol: string, period_days?: number }
   * @param {string} token - JWT access token
   * @returns {Promise<object>} ExitAnalysisResponse
   */
  analyzeExitPoints: (body, token) =>
    apiFetch("/trading/exit-analysis", { method: "POST", body, token }),

  // ── Research / Screener ─────────────────────────────────────────────────

  /**
   * Fetch sector performance overview (all GICS sector ETFs).
   * Returns { sectors: [{ symbol, name, price, change_pct, ytd_pct, month_pct }] }.
   * @param {string} token - JWT access token
   * @returns {Promise<{sectors: Array}>}
   */
  getSectors: (token) =>
    apiFetch("/market/sectors", { token }),

  /**
   * Run the stock screener with optional filter parameters.
   * Sends only non-empty params as query string values.
   * Returns { results, total_matched, filters_applied }.
   * @param {object} params - Filter/sort params (min_price, max_price, sector, etc.)
   * @param {string} token  - JWT access token
   * @returns {Promise<{results: Array, total_matched: number, filters_applied: object}>}
   */
  runScreener: (params, token) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v != null && v !== "") qs.set(k, v);
    });
    return apiFetch(`/market/screener?${qs}`, { token });
  },

  // ── Scanner (Volume Flow) ────────────────────────────────────────────────

  /**
   * Start a volume flow scanner run.
   * Scans sector ETFs → industry ETFs → individual stocks for unusual volume.
   * Returns an initial ScanResultOut (status "pending" or "running").
   * @param {object} data  - { portfolio_value_usd: number }
   * @param {string} token - JWT access token
   * @returns {Promise<object>} ScanResultOut with result_id for polling
   */
  runScanner: (data, token) =>
    apiFetch("/scanner/run", { method: "POST", body: data, token }),

  /**
   * Poll a scan result by ID.  Call every 3s until status is "complete"/"error".
   * @param {string} resultId - Scan result UUID (from runScanner response)
   * @param {string} token    - JWT access token
   * @returns {Promise<object>} ScanResultOut
   */
  getScanResult: (resultId, token) =>
    apiFetch(`/scanner/${resultId}`, { token }),

  /**
   * Fetch the latest scan result for the authenticated user.
   * Used to restore prior scan state when the VOLUME FLOW tab is opened.
   * @param {string} token - JWT access token
   * @returns {Promise<object>} ScanResultOut
   */
  getLatestScan: (token) =>
    apiFetch("/scanner/latest", { token }),

  // ── Admin ───────────────────────────────────────────────────────────────

  /** Check if current user is admin. Returns { is_admin: true } or throws 403. */
  checkAdmin: (token) =>
    apiFetch("/admin/check", { token }),

  /** List all users (admin). */
  adminListUsers: (token) =>
    apiFetch("/admin/users", { token }),

  /** Lock (deactivate) a user. */
  adminLockUser: (userId, token) =>
    apiFetch(`/admin/users/${userId}/lock`, { method: "POST", token }),

  /** Unlock (reactivate) a user. */
  adminUnlockUser: (userId, token) =>
    apiFetch(`/admin/users/${userId}/unlock`, { method: "POST", token }),

  /** List reports with optional filters. */
  adminListReports: (params, token) => {
    const qs = new URLSearchParams();
    if (params.status) qs.set("status", params.status);
    if (params.report_type) qs.set("report_type", params.report_type);
    if (params.limit) qs.set("limit", params.limit);
    if (params.offset) qs.set("offset", params.offset);
    return apiFetch(`/reports?${qs}`, { token });
  },

  /** Update a report (status, admin_notes). */
  adminUpdateReport: (reportId, body, token) =>
    apiFetch(`/reports/${reportId}`, { method: "PATCH", body, token }),

  /** Delete a report. */
  adminDeleteReport: (reportId, token) =>
    apiFetch(`/reports/${reportId}`, { method: "DELETE", token }),

  /** Query audit logs. */
  adminAuditLogs: (params, token) => {
    const qs = new URLSearchParams();
    if (params.user_id) qs.set("user_id", params.user_id);
    if (params.action) qs.set("action", params.action);
    if (params.limit) qs.set("limit", params.limit);
    return apiFetch(`/admin/audit-logs?${qs}`, { token });
  },

  /**
   * subscribePaperTrade — Stream paper trade updates via SSE.
   * Uses fetch + ReadableStream because EventSource does not support
   * custom Authorization headers.
   *
   * @param {string} paperTradeId - Paper trade UUID
   * @param {string} token        - JWT access token
   * @returns {AsyncGenerator<object>} Yields parsed JSON events
   */
  async *subscribePaperTrade(paperTradeId, token) {
    const res = await fetch(`${API_BASE}/trading/paper/${paperTradeId}/stream`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const parts = buf.split("\n\n");
      buf = parts.pop();
      for (const part of parts) {
        const line = part.replace(/^data: /, "");
        if (line) {
          try { yield JSON.parse(line); } catch { /* skip malformed frames */ }
        }
      }
    }
  },
};

export default api;

/* ── uploadFile — multipart/form-data upload ─────────────────────────────── */
/**
 * uploadFile — POST a FormData payload without setting Content-Type.
 *
 * The browser automatically sets Content-Type to multipart/form-data with the
 * correct boundary when Content-Type is absent from the request headers.
 * Setting it manually breaks the boundary and causes a 422 on the backend.
 *
 * @param {string}   path     - Full URL path, e.g. "/api/v1/import/degiro/csv"
 * @param {FormData} formData - FormData instance to send as the request body
 * @param {string}   [token]  - Optional JWT access token
 * @returns {Promise<any>} Parsed JSON response
 * @throws  {Error}       On HTTP errors or network failure
 */
export async function uploadFile(path, formData, token) {
  const headers = {};
  // Inject auth header only when a token is provided.
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(path, {
    method: "POST",
    headers,
    credentials: "include",  // Forward httpOnly cookies in case needed
    body: formData,           // DO NOT set Content-Type — browser sets it with boundary
  });

  if (!res.ok) {
    // Attempt to parse error detail from JSON; fall back to raw text.
    const text = await res.text();
    let detail = text;
    try {
      detail = JSON.parse(text).detail || text;
    } catch {
      /* text is not JSON — use as-is */
    }
    if (Array.isArray(detail)) {
      detail = detail.map(e => e.msg || JSON.stringify(e)).join("; ");
    }
    throw new Error(detail || `HTTP ${res.status}`);
  }

  if (res.status === 204) return null;
  return res.json();
}

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
