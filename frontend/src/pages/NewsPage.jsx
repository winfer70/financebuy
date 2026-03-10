/**
 * NewsPage.jsx — Financial news page for TickerTap.
 *
 * Displays pre-scored news articles served from PostgreSQL with server-side
 * pagination AND server-side filtering.  Articles are scored by a background
 * LLM worker (Llama 3 on Server B) and carry both a general market impact
 * score (-5 to +5) and per-ticker impact scores.
 *
 * Filtering (portfolio toggle, sentiment, ticker search) is handled on the
 * backend so that pagination totals and page offsets stay consistent
 * regardless of the active filter combination.  The client only sorts
 * the returned page (portfolio articles to the top).
 *
 * Features:
 *  - Server-side pagination with configurable page size (25/50/75/100)
 *  - Server-side ticker search (matches ticker symbols and article titles)
 *  - Server-side sentiment filter: ALL | BULLISH | BEARISH
 *  - Server-side portfolio toggle to show only portfolio-relevant articles
 *  - Automatic page reset to 1 when any filter changes
 *  - Score badge with colour gradient (-5 red → 0 neutral → +5 green)
 *  - LLM reasoning text below each headline
 *  - Per-ticker score drill-down badges
 *  - Portfolio articles sorted to the top within each page
 *  - Staleness indicator when newest article is older than 30 minutes
 *  - Page navigation with PREV / NEXT and page indicator
 *
 * Props:
 *  @param {string}   token          - JWT access token
 *  @param {string}   [initialTicker] - Pre-populate ticker search (from portfolio action)
 *  @param {Function} [onViewChart]   - Callback to open a chart for a ticker
 */

import { useState, useEffect, useMemo, useCallback } from "react";
import api from "../api/client";
import { Ic } from "../components/common/Icons";
import { useI18n } from "../context/I18nContext";

/* -- Page size options ---------------------------------------------------- */

/** Available per-page options for the pagination selector. */
const PAGE_SIZE_OPTIONS = [25, 50, 75, 100];

/* -- Score colour helpers ------------------------------------------------- */

/**
 * Map a score (-5 to +5) to a colour string for the score badge.
 *
 * @param {number} score - Impact score from -5 to +5.
 * @returns {{ color: string, bg: string, border: string }} CSS values.
 */
function scoreStyle(score) {
  if (score >= 3) return { color: "var(--green)", bg: "rgba(0,217,126,0.10)", border: "rgba(0,217,126,0.20)" };
  if (score >= 1) return { color: "var(--green)", bg: "rgba(0,217,126,0.06)", border: "rgba(0,217,126,0.12)" };
  if (score <= -3) return { color: "var(--red)", bg: "rgba(240,68,56,0.10)", border: "rgba(240,68,56,0.20)" };
  if (score <= -1) return { color: "var(--red)", bg: "rgba(240,68,56,0.06)", border: "rgba(240,68,56,0.12)" };
  return { color: "var(--mid)", bg: "var(--bg3)", border: "var(--border)" };
}

/**
 * Map a score (-5 to +5) to a human-readable label.
 *
 * @param {number} score - Impact score.
 * @returns {string} Label like "VERY BULLISH", "BEARISH", "NEUTRAL", etc.
 */
function scoreLabel(score) {
  if (score >= 4) return "VERY BULLISH";
  if (score >= 2) return "BULLISH";
  if (score >= 1) return "LEAN BULL";
  if (score <= -4) return "VERY BEARISH";
  if (score <= -2) return "BEARISH";
  if (score <= -1) return "LEAN BEAR";
  return "NEUTRAL";
}

/* -- Source badge labels -------------------------------------------------- */
const SOURCE_LABELS = {
  yahoo:       "YAHOO",
  google:      "GOOGLE",
  finviz:      "FINVIZ",
  marketwatch: "MKTWATCH",
};

/* -- Filter categories ---------------------------------------------------- */
const SENTIMENT_FILTERS = [
  { id: "all",     label: "ALL" },
  { id: "bullish", label: "BULLISH" },
  { id: "bearish", label: "BEARISH" },
];

/**
 * Format a UTC datetime string as a relative or absolute time label.
 *
 * @param {string|null} dt - ISO datetime string or null.
 * @returns {string} Human-readable time label.
 */
function timeAgo(dt) {
  if (!dt) return "";
  try {
    const diff = (Date.now() - new Date(dt).getTime()) / 1000;
    if (diff < 60)   return "just now";
    if (diff < 3600)  return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return new Date(dt).toLocaleDateString("en-US", { month: "short", day: "numeric" });
  } catch {
    return "";
  }
}

/**
 * Check if the newest article in the list is older than 30 minutes.
 *
 * @param {Array} articles - List of article objects.
 * @returns {boolean} True if news may be stale.
 */
function isStale(articles) {
  if (!articles.length) return false;
  const newest = articles.reduce((best, a) => {
    if (!a.published_at) return best;
    const t = new Date(a.published_at).getTime();
    return t > best ? t : best;
  }, 0);
  if (!newest) return false;
  return (Date.now() - newest) > 30 * 60 * 1000;
}

export function NewsPage({ token, initialTicker, onViewChart }) {
  /* -- State -------------------------------------------------------------- */
  const { t } = useI18n();
  const [articles,       setArticles]       = useState([]);
  const [totalArticles,  setTotalArticles]  = useState(0);
  const [loading,        setLoading]        = useState(true);
  const [error,          setError]          = useState(null);
  const [sentimentFilter, setSentimentFilter] = useState("all");
  const [portfolioOnly,  setPortfolioOnly]  = useState(false);
  const [watchlistOnly,  setWatchlistOnly]  = useState(false);
  const [watchlistTickers, setWatchlistTickers] = useState([]);
  const [searchTicker,   setSearchTicker]   = useState(initialTicker || "");
  const [tickerPopup,    setTickerPopup]    = useState(null); /* { ticker, x, y } */

  /* -- Pagination state --------------------------------------------------- */
  const [perPage,     setPerPage]     = useState(25);
  const [currentPage, setCurrentPage] = useState(1);

  /** Total number of pages based on total articles from the backend. */
  const totalPages = Math.max(1, Math.ceil(totalArticles / perPage));

  /* -- Fetch watchlist tickers on mount ----------------------------------- */
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        // Fetch all watchlists, then collect unique ticker symbols from items
        const watchlists = await api.getWatchlists(token);
        if (cancelled || !watchlists?.length) return;
        const allItems = await Promise.all(
          watchlists.map(wl => api.getWatchlist(wl.watchlist_id, token).catch(() => ({ items: [] })))
        );
        const tickers = [...new Set(allItems.flatMap(wl => (wl.items || []).map(it => it.symbol)))];
        if (!cancelled) setWatchlistTickers(tickers);
      } catch { /* Keep empty on error */ }
    })();
    return () => { cancelled = true; };
  }, [token]);

  /* -- Feed fetch --------------------------------------------------------- */

  /**
   * Fetch a page of articles from the backend with server-side filters.
   * Reads perPage, currentPage, and filter state to compute query params.
   * Filters are applied on the server so pagination totals stay consistent.
   * Updates articles, totalArticles, loading, and error state.
   */
  const loadFeed = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      /* Calculate offset from 1-indexed currentPage. */
      const offset = (currentPage - 1) * perPage;

      /* Build server-side filter params. */
      const params = {
        limit: perPage,
        offset,
        portfolio_only: portfolioOnly,
        sentiment: sentimentFilter !== "all" ? sentimentFilter : null,
        ticker_search: searchTicker.trim() || null,
        // When watchlist toggle is active, pass watchlist tickers to the
        // backend's portfolio_tickers param for server-side filtering.
        portfolio_tickers: watchlistOnly && watchlistTickers.length
          ? watchlistTickers.join(",")
          : null,
      };

      /* api.getNews returns { articles, total, limit, offset }. */
      const data = await api.getNews(token, params);
      setArticles(data.articles || []);
      setTotalArticles(data.total || 0);
    } catch (e) {
      setError(e.message || "Failed to load news feed.");
    } finally {
      setLoading(false);
    }
  }, [token, perPage, currentPage, portfolioOnly, watchlistOnly, watchlistTickers, sentimentFilter, searchTicker]);

  /* Re-fetch whenever token, pagination, or filter state changes. */
  useEffect(() => { loadFeed(); }, [loadFeed]);

  /* -- Pagination handlers ------------------------------------------------ */

  /**
   * Reset to page 1 whenever any filter changes, so the user never lands
   * on an empty page after narrowing results.
   */
  useEffect(() => {
    setCurrentPage(1);
  }, [sentimentFilter, portfolioOnly, watchlistOnly, searchTicker]);

  /**
   * Change the per-page size and reset to page 1.
   * @param {number} size - New page size (25, 50, 75, or 100).
   */
  const handlePerPageChange = useCallback((size) => {
    setPerPage(size);
    setCurrentPage(1);
  }, []);

  /**
   * Navigate to the previous page (clamped at 1).
   */
  const handlePrev = useCallback(() => {
    setCurrentPage(p => Math.max(1, p - 1));
  }, []);

  /**
   * Navigate to the next page (clamped at totalPages).
   */
  const handleNext = useCallback(() => {
    setCurrentPage(p => Math.min(totalPages, p + 1));
  }, [totalPages]);

  /* -- Dismiss ticker popup on outside click ------------------------------- */
  useEffect(() => {
    if (!tickerPopup) return;
    const dismiss = () => setTickerPopup(null);
    window.addEventListener("click", dismiss);
    return () => window.removeEventListener("click", dismiss);
  }, [tickerPopup]);

  /* -- Client-side sorting (within the current server-filtered page) ------- */
  /**
   * Sort the server-filtered articles for display.  All filtering (portfolio,
   * sentiment, ticker search) is now handled server-side so pagination totals
   * stay consistent.  The client only sorts: portfolio articles bubble to
   * the top, then sort by published_at descending.
   */
  const filteredArticles = useMemo(() => {
    const list = [...articles];

    /* Portfolio articles bubble to the top, then sort by date descending. */
    list.sort((a, b) => {
      if (a.in_portfolio !== b.in_portfolio) return a.in_portfolio ? -1 : 1;
      const da = a.published_at ? new Date(a.published_at).getTime() : 0;
      const db = b.published_at ? new Date(b.published_at).getTime() : 0;
      return db - da;
    });

    return list;
  }, [articles]);

  /* -- Render ------------------------------------------------------------- */
  const stale = isStale(articles);

  /** Shared mono style for pagination controls. */
  const paginationBtnStyle = (disabled) => ({
    fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 600,
    letterSpacing: "0.5px", padding: "4px 12px",
    background: disabled ? "transparent" : "var(--bg3)",
    border: `1px solid ${disabled ? "var(--bg3)" : "var(--border)"}`,
    color: disabled ? "var(--bg3)" : "var(--muted)",
    cursor: disabled ? "default" : "pointer",
    borderRadius: 2,
  });

  return (
    <div className="page-scroll">
      {/* Page header */}
      <div className="page-header">
        <div>
          <div className="page-title">NEWS</div>
          <div className="page-sub">
            LLM-SCORED FINANCIAL NEWS · {totalArticles} ARTICLE{totalArticles !== 1 ? "S" : ""} · PAGE {currentPage} OF {totalPages}
          </div>
        </div>
        <div className="page-actions">
          <button className="btn btn-outline" onClick={loadFeed} disabled={loading}>
            {loading ? <span className="loading-pulse">REFRESHING...</span> : "REFRESH"}
          </button>
        </div>
      </div>

      <div className="page-inner">
        {/* Staleness indicator */}
        {stale && !loading && (
          <div style={{
            fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)",
            padding: "6px 12px", background: "var(--bg3)", border: "1px solid var(--border)",
            borderRadius: 2, marginBottom: 8,
          }}>
            NEWS MAY BE DELAYED — newest article is older than 30 minutes
          </div>
        )}

        {/* Toolbar: search + filter + per-page selector */}
        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          {/* Ticker search */}
          <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
            <div style={{ position: "relative" }}>
              <input
                className="search-input"
                placeholder="Search ticker..."
                value={searchTicker}
                onChange={e => setSearchTicker(e.target.value.toUpperCase())}
                onKeyDown={e => { if (e.key === "Enter") e.target.blur(); }}
                style={{ width: 180, paddingRight: 28 }}
              />
              <span style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", color: "var(--muted)" }}>
                <Ic.search />
              </span>
            </div>
            {searchTicker && (
              <button
                className="btn btn-ghost"
                style={{ padding: "5px 8px", fontSize: 10 }}
                onClick={() => setSearchTicker("")}
              >
                CLEAR
              </button>
            )}
          </div>

          {/* Sentiment filter */}
          <div className="filter-bar">
            {SENTIMENT_FILTERS.map(f => (
              <button
                key={f.id}
                className={`filter-btn${sentimentFilter === f.id ? " active" : ""}`}
                onClick={() => setSentimentFilter(f.id)}
              >
                {f.label}
              </button>
            ))}
          </div>

          {/* Portfolio toggle — combines with sentiment filter */}
          <button
            className={`filter-btn${portfolioOnly ? " active" : ""}`}
            onClick={() => { setPortfolioOnly(p => !p); if (!portfolioOnly) setWatchlistOnly(false); }}
            style={{
              fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.5px",
              border: portfolioOnly ? "1px solid var(--amber)" : "1px solid var(--border)",
              color: portfolioOnly ? "var(--amber)" : "var(--muted)",
              background: portfolioOnly ? "rgba(255,178,56,0.08)" : "transparent",
              padding: "4px 10px", cursor: "pointer", borderRadius: 2,
            }}
          >
            {t("news.portfolioOnly")}
          </button>

          {/* Watchlist toggle — filters to watchlist tickers (mutually exclusive with portfolio) */}
          <button
            className={`filter-btn${watchlistOnly ? " active" : ""}`}
            onClick={() => { setWatchlistOnly(w => !w); if (!watchlistOnly) setPortfolioOnly(false); }}
            style={{
              fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.5px",
              border: watchlistOnly ? "1px solid var(--amber)" : "1px solid var(--border)",
              color: watchlistOnly ? "var(--amber)" : "var(--muted)",
              background: watchlistOnly ? "rgba(255,178,56,0.08)" : "transparent",
              padding: "4px 10px", cursor: "pointer", borderRadius: 2,
              opacity: watchlistTickers.length ? 1 : 0.4,
            }}
            disabled={!watchlistTickers.length}
            title={watchlistTickers.length ? `Filter to ${watchlistTickers.length} watchlist tickers` : "No watchlist tickers"}
          >
            {t("news.watchlistOnly")}
          </button>

          {/* Per-page selector */}
          <div style={{ display: "flex", gap: 4, alignItems: "center", marginLeft: "auto" }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--muted)", letterSpacing: "0.5px" }}>
              PER PAGE
            </span>
            {PAGE_SIZE_OPTIONS.map(size => (
              <button
                key={size}
                onClick={() => handlePerPageChange(size)}
                style={{
                  fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 600,
                  padding: "3px 8px", cursor: "pointer", borderRadius: 2,
                  letterSpacing: "0.3px",
                  background: perPage === size ? "var(--amber)" : "transparent",
                  color: perPage === size ? "var(--bg1)" : "var(--muted)",
                  border: perPage === size ? "1px solid var(--amber)" : "1px solid var(--border)",
                }}
              >
                {size}
              </button>
            ))}
          </div>
        </div>

        {/* Results count */}
        <div style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          marginTop: 4,
        }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>
            {filteredArticles.length} RESULT{filteredArticles.length !== 1 ? "S" : ""} ON THIS PAGE
          </span>
        </div>

        {/* Error state */}
        {error && (
          <div style={{
            padding: "12px 16px", background: "rgba(240,68,56,0.06)",
            border: "1px solid rgba(240,68,56,0.2)", borderRadius: 2,
            fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--red)",
          }}>
            {error}
          </div>
        )}

        {/* Loading state */}
        {loading && articles.length === 0 && (
          <div style={{ textAlign: "center", padding: "48px 0" }}>
            <span className="loading-pulse" style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--muted)" }}>
              LOADING NEWS...
            </span>
          </div>
        )}

        {/* Empty state */}
        {!loading && filteredArticles.length === 0 && !error && (
          <div style={{
            textAlign: "center", padding: "48px 0",
            fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--muted)",
          }}>
            {articles.length === 0 && totalArticles === 0
              ? "No news articles available. Articles will appear once the news worker begins scoring."
              : "No articles match the current filter."}
          </div>
        )}

        {/* Article list */}
        {filteredArticles.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
            {filteredArticles.map((article, idx) => {
              const sStyle = scoreStyle(article.score);
              return (
                <div
                  key={article.url + idx}
                  className="panel"
                  style={{
                    padding: "12px 16px",
                    display: "flex", gap: 14, alignItems: "flex-start",
                    borderLeft: article.in_portfolio ? "2px solid var(--amber)" : "2px solid transparent",
                  }}
                >
                  {/* Left: source badge */}
                  <div style={{
                    flexShrink: 0, width: 64, textAlign: "center",
                    fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 600,
                    letterSpacing: "0.5px", color: "var(--muted)",
                    padding: "3px 0", background: "var(--bg3)",
                    border: "1px solid var(--border)", borderRadius: 2,
                  }}>
                    {SOURCE_LABELS[article.source] || article.source.toUpperCase()}
                  </div>

                  {/* Middle: headline + reasoning + metadata */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    {/* Headline */}
                    <a
                      href={article.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        fontFamily: "var(--font-sans)", fontSize: 13, fontWeight: 500,
                        color: "var(--bright)", textDecoration: "none",
                        lineHeight: 1.4, display: "block",
                      }}
                      onMouseOver={e => e.currentTarget.style.color = "var(--amber)"}
                      onMouseOut={e => e.currentTarget.style.color = "var(--bright)"}
                    >
                      {article.title}
                      <span style={{ marginLeft: 6, opacity: 0.5 }}>
                        <Ic.externalLink />
                      </span>
                    </a>

                    {/* LLM reasoning */}
                    {article.reasoning && (
                      <div style={{
                        fontFamily: "var(--font-mono)", fontSize: 11,
                        color: "var(--muted)", marginTop: 4, lineHeight: 1.4,
                        fontStyle: "italic",
                      }}>
                        {article.reasoning}
                      </div>
                    )}

                    {/* Summary (fallback when no reasoning available) */}
                    {!article.reasoning && article.summary && (
                      <div style={{
                        fontFamily: "var(--font-mono)", fontSize: 11,
                        color: "var(--muted)", marginTop: 4, lineHeight: 1.4,
                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                      }}>
                        {article.summary}
                      </div>
                    )}

                    {/* Ticker score badges + time */}
                    <div style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 6, flexWrap: "wrap" }}>
                      {(article.ticker_scores || []).map(ts => {
                        const tStyle = scoreStyle(ts.score);
                        return (
                          <span
                            key={ts.ticker}
                            onClick={(e) => {
                              e.stopPropagation();
                              setTickerPopup({ ticker: ts.ticker, x: e.clientX, y: e.clientY });
                            }}
                            title={ts.reasoning || `${ts.ticker}: ${ts.score > 0 ? "+" : ""}${ts.score}`}
                            style={{
                              fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 600,
                              letterSpacing: "0.5px", padding: "1px 6px",
                              background: tStyle.bg, border: `1px solid ${tStyle.border}`,
                              color: tStyle.color, borderRadius: 1, cursor: "pointer",
                            }}
                          >
                            {ts.ticker} {ts.score > 0 ? "+" : ""}{ts.score}
                          </span>
                        );
                      })}
                      {article.published_at && (
                        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>
                          {timeAgo(article.published_at)}
                        </span>
                      )}
                      {article.in_portfolio && (
                        <span style={{
                          fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 600,
                          color: "var(--amber)", letterSpacing: "0.5px",
                        }}>
                          IN PORTFOLIO
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Right: score badge */}
                  <div style={{
                    flexShrink: 0, textAlign: "center",
                    fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 600,
                    letterSpacing: "0.5px", textTransform: "uppercase",
                    padding: "3px 8px", borderRadius: 1, minWidth: 56,
                    color: sStyle.color,
                    background: sStyle.bg,
                    border: `1px solid ${sStyle.border}`,
                  }}>
                    {scoreLabel(article.score)}
                    <div style={{ fontSize: 12, fontWeight: 700, marginTop: 1 }}>
                      {article.score > 0 ? "+" : ""}{article.score}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* ── Pagination controls ─────────────────────────────────────────── */}
        {totalArticles > 0 && (
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "center",
            gap: 16, padding: "16px 0 8px",
          }}>
            {/* PREV button */}
            <button
              onClick={handlePrev}
              disabled={currentPage <= 1}
              style={paginationBtnStyle(currentPage <= 1)}
            >
              ◀ PREV
            </button>

            {/* Page indicator */}
            <span style={{
              fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 600,
              color: "var(--bright)", letterSpacing: "0.5px",
            }}>
              PAGE {currentPage} OF {totalPages}
            </span>

            {/* NEXT button */}
            <button
              onClick={handleNext}
              disabled={currentPage >= totalPages}
              style={paginationBtnStyle(currentPage >= totalPages)}
            >
              NEXT ▶
            </button>
          </div>
        )}
      </div>

      {/* ── Ticker popup (click on ticker badge) ─────────────────────────── */}
      {tickerPopup && (
        <div
          onClick={e => e.stopPropagation()}
          style={{
            position: "fixed",
            top: tickerPopup.y,
            left: tickerPopup.x,
            zIndex: 1000,
            background: "var(--bg2)",
            border: "1px solid var(--border)",
            borderRadius: 3,
            padding: "6px 0",
            boxShadow: "0 4px 16px rgba(0,0,0,0.5)",
            fontFamily: "var(--font-mono)",
            fontSize: 10,
            minWidth: 140,
          }}
        >
          <div style={{
            padding: "4px 12px", color: "var(--amber)",
            fontWeight: 600, letterSpacing: "0.5px", borderBottom: "1px solid var(--border)",
            marginBottom: 2,
          }}>
            {tickerPopup.ticker}
          </div>
          {onViewChart && (
            <button
              onClick={() => { onViewChart(tickerPopup.ticker); setTickerPopup(null); }}
              style={{
                display: "block", width: "100%", textAlign: "left",
                background: "none", border: "none", cursor: "pointer",
                color: "var(--bright)", padding: "5px 12px",
                fontFamily: "var(--font-mono)", fontSize: 10,
                letterSpacing: "0.3px",
              }}
              onMouseOver={e => e.currentTarget.style.background = "var(--bg3)"}
              onMouseOut={e => e.currentTarget.style.background = "none"}
            >
              VIEW CHART →
            </button>
          )}
          <button
            onClick={() => { setSearchTicker(tickerPopup.ticker); setTickerPopup(null); }}
            style={{
              display: "block", width: "100%", textAlign: "left",
              background: "none", border: "none", cursor: "pointer",
              color: "var(--bright)", padding: "5px 12px",
              fontFamily: "var(--font-mono)", fontSize: 10,
              letterSpacing: "0.3px",
            }}
            onMouseOver={e => e.currentTarget.style.background = "var(--bg3)"}
            onMouseOut={e => e.currentTarget.style.background = "none"}
          >
            FILTER NEWS
          </button>
        </div>
      )}
    </div>
  );
}
