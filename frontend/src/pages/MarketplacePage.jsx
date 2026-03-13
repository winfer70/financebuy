/**
 * MarketplacePage.jsx — Public strategy marketplace for TickerTap.
 *
 * Bloomberg terminal–style layout for browsing, rating, and cloning
 * publicly shared trading strategies. Features:
 *   - Featured strategies carousel (top-rated)
 *   - Searchable, filterable strategy table with pagination
 *   - Expandable detail panel with ratings, stats, clone button
 *   - Inline star-rating widget for rating public strategies
 *
 * Props:
 *   @param {string}   token   — JWT access token
 *   @param {Function} setPage — Navigate to another page (e.g. "trading")
 */

import { useState, useEffect, useCallback } from "react";
import api from "../api/client";
import Pagination from "../components/common/Pagination";
import EmptyState from "../components/common/EmptyState";
import StatBlock from "../components/common/StatBlock";

/* ── Constants ─────────────────────────────────────────────────────────────── */

const CATEGORIES = [
  { id: "", label: "ALL" },
  { id: "trend_following", label: "TREND" },
  { id: "mean_reversion", label: "MEAN REVERT" },
  { id: "momentum", label: "MOMENTUM" },
  { id: "volatility", label: "VOLATILITY" },
  { id: "ml_based", label: "ML-BASED" },
  { id: "pinescript", label: "PINESCRIPT" },
  { id: "composed", label: "COMPOSED" },
];

const TIMEFRAMES = [
  { id: "", label: "ALL" },
  { id: "1d", label: "DAILY" },
  { id: "1h", label: "HOURLY" },
  { id: "15m", label: "15MIN" },
  { id: "5m", label: "5MIN" },
];

const SORT_OPTIONS = [
  { id: "newest", label: "NEWEST" },
  { id: "top_rated", label: "TOP RATED" },
  { id: "most_cloned", label: "MOST CLONED" },
  { id: "name_asc", label: "NAME A-Z" },
];

const PER_PAGE = 25;

/* ── Star Component ────────────────────────────────────────────────────────── */

/**
 * StarRating — Displays 1–5 stars, optionally interactive.
 *
 * @param {number}   value      — Current star value (0 = unrated)
 * @param {Function} [onChange] — If provided, stars become clickable
 * @param {number}   [size=14]  — Star size in px
 */
function StarRating({ value = 0, onChange, size = 14 }) {
  const [hover, setHover] = useState(0);
  const interactive = !!onChange;

  return (
    <span style={{ display: "inline-flex", gap: 1, cursor: interactive ? "pointer" : "default" }}>
      {[1, 2, 3, 4, 5].map((star) => (
        <svg
          key={star}
          width={size}
          height={size}
          viewBox="0 0 24 24"
          fill={(hover || value) >= star ? "var(--amber)" : "none"}
          stroke={(hover || value) >= star ? "var(--amber)" : "var(--muted)"}
          strokeWidth={2}
          onMouseEnter={() => interactive && setHover(star)}
          onMouseLeave={() => interactive && setHover(0)}
          onClick={() => interactive && onChange(star)}
        >
          <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
        </svg>
      ))}
    </span>
  );
}

/* ── Rating Modal ──────────────────────────────────────────────────────────── */

/**
 * RatingModal — Overlay dialog for submitting a strategy rating.
 *
 * @param {object}   strategy   — The strategy being rated
 * @param {Function} onSubmit   — Callback: ({ stars, review }) => void
 * @param {Function} onClose    — Close the modal
 */
function RatingModal({ strategy, onSubmit, onClose }) {
  const [stars, setStars] = useState(0);
  const [review, setReview] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (stars < 1) return;
    setSubmitting(true);
    await onSubmit({ stars, review: review.trim() || null });
    setSubmitting(false);
  };

  return (
    <div style={modalOverlay} onClick={onClose}>
      <div style={modalBox} onClick={(e) => e.stopPropagation()}>
        <div style={{ fontSize: 13, fontWeight: 700, color: "var(--amber)", marginBottom: 12 }}>
          RATE STRATEGY
        </div>
        <div style={{ color: "var(--text)", fontSize: 12, marginBottom: 12 }}>
          {strategy.name}
        </div>
        <div style={{ marginBottom: 12 }}>
          <StarRating value={stars} onChange={setStars} size={22} />
        </div>
        <textarea
          style={textareaStyle}
          rows={3}
          placeholder="Write a review (optional)..."
          value={review}
          onChange={(e) => setReview(e.target.value)}
          maxLength={500}
        />
        <div style={{ display: "flex", gap: 8, marginTop: 12, justifyContent: "flex-end" }}>
          <button className="btn btn-outline" onClick={onClose}>CANCEL</button>
          <button
            className="btn btn-primary"
            disabled={stars < 1 || submitting}
            onClick={handleSubmit}
          >
            {submitting ? "SUBMITTING..." : "SUBMIT"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Main Page ─────────────────────────────────────────────────────────────── */

export function MarketplacePage({ token, setPage }) {
  /* -- State: filters & pagination ---------------------------------------- */
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [timeframe, setTimeframe] = useState("");
  const [sortBy, setSortBy] = useState("newest");
  const [page, setCurrentPage] = useState(1);

  /* -- State: data -------------------------------------------------------- */
  const [strategies, setStrategies] = useState([]);
  const [featured, setFeatured] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [totalCount, setTotalCount] = useState(0);

  /* -- State: detail & rating --------------------------------------------- */
  const [selected, setSelected] = useState(null);
  const [selectedStats, setSelectedStats] = useState(null);
  const [selectedRatings, setSelectedRatings] = useState([]);
  const [ratingModal, setRatingModal] = useState(null);
  const [cloning, setCloning] = useState(false);

  /* -- Fetch featured strategies ------------------------------------------ */
  const fetchFeatured = useCallback(async () => {
    try {
      const data = await api.getFeaturedStrategies(token);
      setFeatured(data || []);
    } catch { /* silent — featured is nonessential */ }
  }, [token]);

  /* -- Fetch marketplace listing ------------------------------------------ */
  const fetchStrategies = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {
        limit: PER_PAGE,
        offset: (page - 1) * PER_PAGE,
        sort_by: sortBy,
      };
      if (search) params.search = search;
      if (category) params.category = category;
      if (timeframe) params.timeframe = timeframe;

      const data = await api.browseMarketplace(params, token);
      setStrategies(data || []);
      // Estimate total: if we got a full page, there could be more
      setTotalCount(data.length === PER_PAGE ? page * PER_PAGE + 1 : (page - 1) * PER_PAGE + data.length);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [token, page, search, category, timeframe, sortBy]);

  useEffect(() => { fetchFeatured(); }, [fetchFeatured]);
  useEffect(() => { fetchStrategies(); }, [fetchStrategies]);

  /* -- Fetch detail when a strategy is selected --------------------------- */
  const selectStrategy = useCallback(async (strat) => {
    if (selected?.strategy_id === strat.strategy_id) {
      setSelected(null);
      return;
    }
    setSelected(strat);
    setSelectedStats(null);
    setSelectedRatings([]);
    try {
      const [stats, ratings] = await Promise.all([
        api.getStrategyStats(strat.strategy_id, token),
        api.getStrategyRatings(strat.strategy_id, {}, token),
      ]);
      setSelectedStats(stats);
      setSelectedRatings(ratings || []);
    } catch { /* non-fatal */ }
  }, [token, selected]);

  /* -- Clone strategy ----------------------------------------------------- */
  const handleClone = useCallback(async (strategyId) => {
    setCloning(true);
    try {
      await api.cloneStrategy(strategyId, token);
      // Refresh stats to update clone count
      const stats = await api.getStrategyStats(strategyId, token);
      setSelectedStats(stats);
    } catch (err) {
      setError(err.message);
    } finally {
      setCloning(false);
    }
  }, [token]);

  /* -- Submit rating ------------------------------------------------------ */
  const handleRateSubmit = useCallback(async ({ stars, review }) => {
    if (!ratingModal) return;
    try {
      await api.rateStrategy(ratingModal.strategy_id, { stars, review }, token);
      // Refresh ratings and stats
      const [stats, ratings] = await Promise.all([
        api.getStrategyStats(ratingModal.strategy_id, token),
        api.getStrategyRatings(ratingModal.strategy_id, {}, token),
      ]);
      setSelectedStats(stats);
      setSelectedRatings(ratings || []);
      // Refresh listing to show updated rating
      fetchStrategies();
    } catch (err) {
      setError(err.message);
    }
    setRatingModal(null);
  }, [token, ratingModal, fetchStrategies]);

  /* -- Pagination helpers ------------------------------------------------- */
  const totalPages = Math.max(1, Math.ceil(totalCount / PER_PAGE));

  /* -- Search with debounce (reset page on search change) ----------------- */
  const handleSearch = (val) => {
    setSearch(val);
    setCurrentPage(1);
  };

  const handleFilterChange = (setter) => (val) => {
    setter(val);
    setCurrentPage(1);
  };

  /* ── Render ─────────────────────────────────────────────────────────────── */
  return (
    <div className="page-scroll">
      <div className="page-body" style={{ maxWidth: 1200, margin: "0 auto" }}>
        {/* Header */}
        <div className="page-header">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%" }}>
            <div className="page-title">STRATEGY MARKETPLACE</div>
            <input
              className="form-control"
              style={{ width: 260, fontSize: 11 }}
              placeholder="Search strategies..."
              value={search}
              onChange={(e) => handleSearch(e.target.value)}
            />
          </div>
        </div>

        {/* Filters Bar */}
        <div className="panel" style={{ padding: "8px 12px", marginBottom: 12, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          {/* Category */}
          <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
            <span style={labelStyle}>CATEGORY</span>
            <select className="form-control" style={selectStyle} value={category} onChange={(e) => handleFilterChange(setCategory)(e.target.value)}>
              {CATEGORIES.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
            </select>
          </div>
          {/* Timeframe */}
          <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
            <span style={labelStyle}>TIMEFRAME</span>
            <select className="form-control" style={selectStyle} value={timeframe} onChange={(e) => handleFilterChange(setTimeframe)(e.target.value)}>
              {TIMEFRAMES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
            </select>
          </div>
          {/* Sort */}
          <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
            <span style={labelStyle}>SORT</span>
            <select className="form-control" style={selectStyle} value={sortBy} onChange={(e) => handleFilterChange(setSortBy)(e.target.value)}>
              {SORT_OPTIONS.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select>
          </div>
        </div>

        {/* Featured Section */}
        {featured.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <div style={sectionTitle}>FEATURED STRATEGIES</div>
            <div style={{ display: "flex", gap: 10, overflowX: "auto", paddingBottom: 6 }}>
              {featured.map((s) => (
                <div
                  key={s.strategy_id}
                  className="panel"
                  style={featuredCard}
                  onClick={() => selectStrategy(s)}
                >
                  <div style={{ fontSize: 11, fontWeight: 700, color: "var(--amber)", marginBottom: 4, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {s.name}
                  </div>
                  <div style={{ fontSize: 9, color: "var(--muted)", marginBottom: 6 }}>
                    by {s.author_name}
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <StarRating value={Math.round(s.avg_rating || 0)} size={10} />
                    <span style={{ fontSize: 9, color: "var(--muted)" }}>
                      ({s.rating_count})
                    </span>
                  </div>
                  <div style={{ fontSize: 9, color: "var(--muted)", marginTop: 4 }}>
                    {s.clone_count} clones
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Strategy Table */}
        <div className="panel" style={{ padding: 0 }}>
          <div style={sectionTitle}>ALL STRATEGIES</div>
          {error && (
            <div style={{ padding: 12, color: "var(--red)", fontSize: 11 }}>
              Error: {error}
            </div>
          )}
          <table className="data-table" style={{ width: "100%", fontSize: 11 }}>
            <thead>
              <tr>
                <th style={thStyle}>NAME</th>
                <th style={thStyle}>AUTHOR</th>
                <th style={thStyle}>CATEGORY</th>
                <th style={thStyle}>TIMEFRAME</th>
                <th style={thStyle}>RATING</th>
                <th style={thStyle}>CLONES</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={6} style={{ padding: 24, textAlign: "center", color: "var(--muted)", fontSize: 11 }}>Loading...</td></tr>
              ) : strategies.length === 0 ? (
                <EmptyState asRow colSpan={6} message="No strategies found. Try different filters." />
              ) : (
                strategies.map((s) => (
                  <tr
                    key={s.strategy_id}
                    style={{
                      cursor: "pointer",
                      background: selected?.strategy_id === s.strategy_id ? "rgba(255,191,0,0.06)" : undefined,
                    }}
                    onClick={() => selectStrategy(s)}
                  >
                    <td style={tdStyle}>
                      <span style={{ color: "var(--amber)", fontWeight: 600 }}>{s.name}</span>
                    </td>
                    <td style={tdStyle}>{s.author_name}</td>
                    <td style={tdStyle}>{(s.category || "—").replace(/_/g, " ").toUpperCase()}</td>
                    <td style={tdStyle}>{(s.timeframe || "—").toUpperCase()}</td>
                    <td style={tdStyle}>
                      <StarRating value={Math.round(s.avg_rating || 0)} size={10} />
                      <span style={{ marginLeft: 4, color: "var(--muted)", fontSize: 9 }}>
                        {s.avg_rating ? s.avg_rating.toFixed(1) : "—"} ({s.rating_count})
                      </span>
                    </td>
                    <td style={tdStyle}>{s.clone_count}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>

          {/* Pagination */}
          {!loading && strategies.length > 0 && (
            <div style={{ padding: "8px 12px", borderTop: "1px solid var(--border)" }}>
              <Pagination
                currentPage={page}
                totalPages={totalPages}
                onPrev={() => setCurrentPage((p) => Math.max(1, p - 1))}
                onNext={() => setCurrentPage((p) => p + 1)}
              />
            </div>
          )}
        </div>

        {/* Expanded Detail Panel */}
        {selected && (
          <div className="panel" style={{ marginTop: 12, padding: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <div style={{ fontSize: 14, fontWeight: 700, color: "var(--amber)", marginBottom: 4 }}>
                  {selected.name}
                </div>
                <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 8 }}>
                  by {selected.author_name} &middot; {(selected.category || "").replace(/_/g, " ")} &middot; {(selected.timeframe || "").toUpperCase()}
                </div>
                <div style={{ fontSize: 11, color: "var(--text)", marginBottom: 12, maxWidth: 600, lineHeight: 1.5 }}>
                  {selected.description || "No description provided."}
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
                <button
                  className="btn btn-primary"
                  disabled={cloning}
                  onClick={() => handleClone(selected.strategy_id)}
                >
                  {cloning ? "CLONING..." : "CLONE"}
                </button>
                <button
                  className="btn btn-outline"
                  onClick={() => setRatingModal(selected)}
                >
                  RATE
                </button>
              </div>
            </div>

            {/* Stats Row */}
            {selectedStats && (
              <div style={{ display: "flex", gap: 12, marginBottom: 12 }}>
                <StatBlock label="AVG RATING" value={selectedStats.avg_rating ? selectedStats.avg_rating.toFixed(1) : "—"} cls="amber" />
                <StatBlock label="RATINGS" value={String(selectedStats.rating_count)} />
                <StatBlock label="CLONES" value={String(selectedStats.clone_count)} cls="cyan" />
                <StatBlock label="BACKTESTS" value={String(selectedStats.backtest_count)} />
              </div>
            )}

            {/* Ratings List */}
            {selectedRatings.length > 0 && (
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text)", marginBottom: 8 }}>
                  REVIEWS
                </div>
                {selectedRatings.map((r) => (
                  <div
                    key={r.rating_id}
                    style={{
                      padding: "8px 0",
                      borderBottom: "1px solid var(--border)",
                      fontSize: 11,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                      <span style={{ fontWeight: 600, color: "var(--text)" }}>{r.author_name}</span>
                      <StarRating value={r.stars} size={10} />
                      <span style={{ color: "var(--muted)", fontSize: 9 }}>
                        {new Date(r.created_at).toLocaleDateString()}
                      </span>
                    </div>
                    {r.review && (
                      <div style={{ color: "var(--muted)", lineHeight: 1.4 }}>{r.review}</div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Rating Modal */}
        {ratingModal && (
          <RatingModal
            strategy={ratingModal}
            onSubmit={handleRateSubmit}
            onClose={() => setRatingModal(null)}
          />
        )}
      </div>
    </div>
  );
}

/* ── Inline Styles ─────────────────────────────────────────────────────────── */

const labelStyle = {
  fontSize: 9,
  fontWeight: 700,
  color: "var(--muted)",
  letterSpacing: "0.05em",
};

const selectStyle = {
  fontSize: 10,
  padding: "3px 6px",
  minWidth: 90,
};

const sectionTitle = {
  fontSize: 11,
  fontWeight: 700,
  color: "var(--text)",
  padding: "10px 12px",
  borderBottom: "1px solid var(--border)",
  letterSpacing: "0.05em",
};

const thStyle = {
  textAlign: "left",
  padding: "8px 10px",
  fontSize: 9,
  fontWeight: 700,
  color: "var(--muted)",
  letterSpacing: "0.05em",
};

const tdStyle = {
  padding: "8px 10px",
  borderTop: "1px solid var(--border)",
};

const featuredCard = {
  minWidth: 160,
  maxWidth: 180,
  padding: "10px 12px",
  cursor: "pointer",
  flexShrink: 0,
};

const modalOverlay = {
  position: "fixed",
  inset: 0,
  background: "rgba(0,0,0,0.6)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 9999,
};

const modalBox = {
  background: "var(--bg-panel, #1a1a2e)",
  border: "1px solid var(--border)",
  borderRadius: 6,
  padding: 20,
  minWidth: 320,
  maxWidth: 400,
};

const textareaStyle = {
  width: "100%",
  background: "var(--bg-input, #0f0f1a)",
  border: "1px solid var(--border)",
  borderRadius: 4,
  color: "var(--text)",
  fontSize: 11,
  padding: 8,
  resize: "vertical",
  fontFamily: "inherit",
};
