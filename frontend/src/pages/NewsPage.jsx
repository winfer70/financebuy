/**
 * NewsPage.jsx — Financial news aggregation page for TickerTap.
 *
 * Displays news articles fetched from the backend news aggregation API
 * (Yahoo Finance, Google News, Finviz, MarketWatch).  Articles are
 * classified by sentiment (FinBERT) and annotated with portfolio flags.
 *
 * Features:
 *  - Ticker search bar to filter articles by symbol
 *  - Category filter: ALL | PORTFOLIO | POSITIVE | NEGATIVE
 *  - Sentiment pill with colour coding (green/red/neutral)
 *  - Portfolio articles sorted to the top
 *  - "Load more" deep-fetch per ticker via getNewsByTicker
 *
 * Props:
 *  @param {string}   token          - JWT access token
 *  @param {string}   [initialTicker] - Pre-populate ticker search (from portfolio action)
 */

import { useState, useEffect, useMemo, useCallback } from "react";
import api from "../api/client";
import { Ic } from "../components/common/Icons";

/* -- Sentiment colour map ------------------------------------------------- */
const SENTIMENT_STYLE = {
  positive: { color: "var(--green)", bg: "rgba(0,217,126,0.08)", border: "rgba(0,217,126,0.15)" },
  negative: { color: "var(--red)",   bg: "rgba(240,68,56,0.08)",  border: "rgba(240,68,56,0.15)" },
  neutral:  { color: "var(--mid)",   bg: "var(--bg3)",            border: "var(--border)" },
};

/* -- Source badge labels -------------------------------------------------- */
const SOURCE_LABELS = {
  yahoo:       "YAHOO",
  google:      "GOOGLE",
  finviz:      "FINVIZ",
  marketwatch: "MKTWATCH",
};

/* -- Filter categories ---------------------------------------------------- */
const FILTERS = [
  { id: "all",       label: "ALL" },
  { id: "portfolio", label: "PORTFOLIO" },
  { id: "positive",  label: "POSITIVE" },
  { id: "negative",  label: "NEGATIVE" },
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

export function NewsPage({ token, initialTicker }) {
  /* -- State -------------------------------------------------------------- */
  const [articles,       setArticles]       = useState([]);
  const [loading,        setLoading]        = useState(true);
  const [error,          setError]          = useState(null);
  const [filter,         setFilter]         = useState("all");
  const [searchTicker,   setSearchTicker]   = useState(initialTicker || "");
  const [tickerLoading,  setTickerLoading]  = useState(null);

  /* -- Feed fetch --------------------------------------------------------- */
  const loadFeed = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.getNews(token);
      setArticles(data || []);
    } catch (e) {
      setError(e.message || "Failed to load news feed.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { loadFeed(); }, [loadFeed]);

  /* -- Deep fetch for a specific ticker (load more) ----------------------- */
  const loadMoreForTicker = async (ticker) => {
    if (!token || !ticker) return;
    setTickerLoading(ticker);
    try {
      const extra = await api.getNewsByTicker(ticker, token);
      if (extra && extra.length) {
        setArticles(prev => {
          /* Merge: add new articles, deduplicate by URL. */
          const existingUrls = new Set(prev.map(a => a.url));
          const newArticles = extra.filter(a => !existingUrls.has(a.url));
          return [...prev, ...newArticles];
        });
      }
    } catch {
      /* Non-fatal — silently ignore. */
    } finally {
      setTickerLoading(null);
    }
  };

  /* -- Search ticker submit (enter key or button) ------------------------- */
  const handleTickerSearch = () => {
    const sym = searchTicker.trim().toUpperCase();
    if (sym) loadMoreForTicker(sym);
  };

  /* -- Filtering + sorting ------------------------------------------------ */
  const filteredArticles = useMemo(() => {
    let list = [...articles];

    /* Apply category filter. */
    if (filter === "portfolio") list = list.filter(a => a.in_portfolio);
    if (filter === "positive")  list = list.filter(a => a.sentiment === "positive");
    if (filter === "negative")  list = list.filter(a => a.sentiment === "negative");

    /* Apply ticker search filter. */
    const q = searchTicker.trim().toUpperCase();
    if (q) {
      list = list.filter(a =>
        (a.tickers || []).some(t => t.toUpperCase().includes(q)) ||
        a.title.toUpperCase().includes(q)
      );
    }

    /* Portfolio articles bubble to the top, then sort by date descending. */
    list.sort((a, b) => {
      if (a.in_portfolio !== b.in_portfolio) return a.in_portfolio ? -1 : 1;
      const da = a.published_at ? new Date(a.published_at).getTime() : 0;
      const db = b.published_at ? new Date(b.published_at).getTime() : 0;
      return db - da;
    });

    return list;
  }, [articles, filter, searchTicker]);

  /* -- Render ------------------------------------------------------------- */
  return (
    <div className="page-scroll">
      {/* Page header */}
      <div className="page-header">
        <div>
          <div className="page-title">NEWS</div>
          <div className="page-sub">
            MULTI-SOURCE FINANCIAL NEWS · {articles.length} ARTICLE{articles.length !== 1 ? "S" : ""}
          </div>
        </div>
        <div className="page-actions">
          <button className="btn btn-outline" onClick={loadFeed} disabled={loading}>
            {loading ? <span className="loading-pulse">REFRESHING...</span> : "REFRESH"}
          </button>
        </div>
      </div>

      <div className="page-inner">
        {/* Toolbar: search + filter */}
        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          {/* Ticker search */}
          <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
            <div style={{ position: "relative" }}>
              <input
                className="search-input"
                placeholder="Search ticker..."
                value={searchTicker}
                onChange={e => setSearchTicker(e.target.value.toUpperCase())}
                onKeyDown={e => { if (e.key === "Enter") handleTickerSearch(); }}
                style={{ width: 180, paddingRight: 28 }}
              />
              <span style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", color: "var(--muted)" }}>
                <Ic.search />
              </span>
            </div>
            {searchTicker.trim() && (
              <button
                className="btn btn-amber"
                style={{ padding: "5px 10px", fontSize: 10 }}
                onClick={handleTickerSearch}
                disabled={tickerLoading === searchTicker.trim().toUpperCase()}
              >
                {tickerLoading === searchTicker.trim().toUpperCase()
                  ? <span className="loading-pulse">LOADING...</span>
                  : "LOAD MORE"}
              </button>
            )}
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

          {/* Category filter */}
          <div className="filter-bar">
            {FILTERS.map(f => (
              <button
                key={f.id}
                className={`filter-btn${filter === f.id ? " active" : ""}`}
                onClick={() => setFilter(f.id)}
              >
                {f.label}
              </button>
            ))}
          </div>

          {/* Count label */}
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)", marginLeft: "auto" }}>
            {filteredArticles.length} RESULT{filteredArticles.length !== 1 ? "S" : ""}
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
              FETCHING NEWS FROM MULTIPLE SOURCES...
            </span>
          </div>
        )}

        {/* Empty state */}
        {!loading && filteredArticles.length === 0 && !error && (
          <div style={{
            textAlign: "center", padding: "48px 0",
            fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--muted)",
          }}>
            {articles.length === 0
              ? "No news articles available. Add tickers to your portfolio to see related news."
              : "No articles match the current filter."}
          </div>
        )}

        {/* Article list */}
        {filteredArticles.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
            {filteredArticles.map((article, idx) => {
              const sentStyle = SENTIMENT_STYLE[article.sentiment] || SENTIMENT_STYLE.neutral;
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

                  {/* Middle: headline + metadata */}
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

                    {/* Summary */}
                    {article.summary && (
                      <div style={{
                        fontFamily: "var(--font-mono)", fontSize: 11,
                        color: "var(--muted)", marginTop: 4, lineHeight: 1.4,
                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                      }}>
                        {article.summary}
                      </div>
                    )}

                    {/* Ticker badges + time */}
                    <div style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 6, flexWrap: "wrap" }}>
                      {(article.tickers || []).map(t => (
                        <span
                          key={t}
                          onClick={() => setSearchTicker(t)}
                          style={{
                            fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 600,
                            letterSpacing: "0.5px", padding: "1px 6px",
                            background: "var(--bg3)", border: "1px solid var(--border2)",
                            color: "var(--amber)", borderRadius: 1, cursor: "pointer",
                          }}
                        >
                          {t}
                        </span>
                      ))}
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

                  {/* Right: sentiment pill */}
                  <div style={{
                    flexShrink: 0, textAlign: "center",
                    fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 600,
                    letterSpacing: "0.5px", textTransform: "uppercase",
                    padding: "3px 8px", borderRadius: 1,
                    color: sentStyle.color,
                    background: sentStyle.bg,
                    border: `1px solid ${sentStyle.border}`,
                  }}>
                    {article.sentiment}
                    <div style={{ fontSize: 8, opacity: 0.7, marginTop: 1 }}>
                      {(article.sentiment_score * 100).toFixed(0)}%
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
