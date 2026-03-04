/**
 * NewsPage.jsx — Financial news page for TickerTap.
 *
 * Displays pre-scored news articles served from PostgreSQL.  Articles are
 * scored by a background LLM worker (Llama 3 on Server B) and carry both
 * a general market impact score (-5 to +5) and per-ticker impact scores.
 *
 * Features:
 *  - Ticker search bar to filter articles by symbol
 *  - Category filter: ALL | PORTFOLIO | BULLISH | BEARISH
 *  - Score badge with colour gradient (-5 red → 0 neutral → +5 green)
 *  - LLM reasoning text below each headline
 *  - Per-ticker score drill-down badges
 *  - Portfolio articles sorted to the top
 *  - Staleness indicator when newest article is older than 30 minutes
 *
 * Props:
 *  @param {string}   token          - JWT access token
 *  @param {string}   [initialTicker] - Pre-populate ticker search (from portfolio action)
 */

import { useState, useEffect, useMemo, useCallback } from "react";
import api from "../api/client";
import { Ic } from "../components/common/Icons";

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
const FILTERS = [
  { id: "all",       label: "ALL" },
  { id: "portfolio", label: "PORTFOLIO" },
  { id: "bullish",   label: "BULLISH" },
  { id: "bearish",   label: "BEARISH" },
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

export function NewsPage({ token, initialTicker }) {
  /* -- State -------------------------------------------------------------- */
  const [articles,       setArticles]       = useState([]);
  const [loading,        setLoading]        = useState(true);
  const [error,          setError]          = useState(null);
  const [filter,         setFilter]         = useState("all");
  const [searchTicker,   setSearchTicker]   = useState(initialTicker || "");

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

  /* -- Filtering + sorting ------------------------------------------------ */
  const filteredArticles = useMemo(() => {
    let list = [...articles];

    /* Apply category filter. */
    if (filter === "portfolio") list = list.filter(a => a.in_portfolio);
    if (filter === "bullish")   list = list.filter(a => a.score > 0);
    if (filter === "bearish")   list = list.filter(a => a.score < 0);

    /* Apply ticker search filter — matches against per-ticker scores. */
    const q = searchTicker.trim().toUpperCase();
    if (q) {
      list = list.filter(a =>
        (a.ticker_scores || []).some(ts => ts.ticker.toUpperCase().includes(q)) ||
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
  const stale = isStale(articles);

  return (
    <div className="page-scroll">
      {/* Page header */}
      <div className="page-header">
        <div>
          <div className="page-title">NEWS</div>
          <div className="page-sub">
            LLM-SCORED FINANCIAL NEWS · {articles.length} ARTICLE{articles.length !== 1 ? "S" : ""}
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
            {articles.length === 0
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
                            onClick={() => setSearchTicker(ts.ticker)}
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
      </div>
    </div>
  );
}
