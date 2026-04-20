/**
 * ResearchPage.jsx — Sector analysis + stock screener page.
 *
 * Two-tab layout:
 *   SECTORS  — Heat-map grid of GICS sector ETF cards, colour-coded by daily
 *              change%.  Each card includes a sparkline SVG showing a synthetic
 *              performance curve derived from change_pct, ytd_pct, and month_pct.
 *              Clicking a card navigates to the SCREENER tab with that sector
 *              pre-filtered.
 *   SCREENER — Filter bar (price, change%, volume, sector, sort) + sortable
 *              results table over ~100 popular tickers.  Each row includes
 *              action buttons (chart, watchlist, portfolio) for quick actions.
 *
 * Data flow:
 *   1. SECTORS tab:  GET /market/sectors  on mount (cached 5 min backend-side).
 *   2. SCREENER tab: GET /market/screener with query params on "SCAN" click.
 *   3. On mount: GET /watchlists + GET /portfolio-manager/portfolios to resolve
 *      default IDs for the quick-add action buttons.
 *
 * Props:
 *   token       — JWT access token for authenticated API calls.
 *   onViewChart — callback(symbol) to open a chart in a new tab.
 */

import { useState, useEffect, useCallback } from "react";
import api from "../api/client";

/* ── Constants ────────────────────────────────────────────────────────────── */

/** Tab definitions for the top-level tab switcher. */
const TABS = [
  { id: "sectors",  label: "SECTORS" },
  { id: "screener", label: "SCREENER" },
];

/** Colour palette for positive/negative values. */
const GREEN = "#22c55e";
const RED   = "#ef4444";
const AMBER = "#f59e0b";

/** Sort options exposed in the screener filter bar. */
const SORT_OPTIONS = [
  { value: "change_pct", label: "Change %" },
  { value: "volume",     label: "Volume" },
  { value: "price",      label: "Price" },
  { value: "market_cap", label: "Market Cap" },
];

/** Known GICS sector names for the sector dropdown filter. */
const SECTOR_NAMES = [
  "Technology", "Financials", "Health Care", "Consumer Discretionary",
  "Consumer Staples", "Energy", "Industrials", "Materials",
  "Real Estate", "Utilities", "Communication Services",
  "Financial Services",
];


/* ── Formatting helpers ──────────────────────────────────────────────────── */

/**
 * fmtPct — format a percentage value with sign and fixed decimals.
 * @param {number|null} val - Percentage value (e.g. 1.42)
 * @returns {string} Formatted string like "+1.42%" or "--"
 */
function fmtPct(val) {
  if (val == null) return "--";
  const sign = val >= 0 ? "+" : "";
  return `${sign}${val.toFixed(2)}%`;
}

/**
 * fmtPrice — format a dollar price with two decimal places.
 * @param {number} val - Price value
 * @returns {string} Formatted string like "$195.50"
 */
function fmtPrice(val) {
  if (val == null) return "--";
  return `$${val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/**
 * fmtVolume — format a volume with M/B suffix for readability.
 * @param {number} val - Raw volume number
 * @returns {string} Formatted string like "45.0M" or "1.2B"
 */
function fmtVolume(val) {
  if (val == null || val === 0) return "--";
  if (val >= 1e9) return `${(val / 1e9).toFixed(1)}B`;
  if (val >= 1e6) return `${(val / 1e6).toFixed(1)}M`;
  if (val >= 1e3) return `${(val / 1e3).toFixed(1)}K`;
  return val.toLocaleString();
}

/**
 * fmtMarketCap — format market capitalisation with T/B/M suffix.
 * @param {number|null} val - Market cap value
 * @returns {string} Formatted string like "2.1T" or "150.3B"
 */
function fmtMarketCap(val) {
  if (val == null || val === 0) return "--";
  if (val >= 1e12) return `$${(val / 1e12).toFixed(1)}T`;
  if (val >= 1e9)  return `$${(val / 1e9).toFixed(1)}B`;
  if (val >= 1e6)  return `$${(val / 1e6).toFixed(1)}M`;
  return `$${val.toLocaleString()}`;
}

/**
 * pctColor — pick green or red based on a percentage value.
 * @param {number|null} val - Percentage value
 * @returns {string} CSS colour string
 */
function pctColor(val) {
  if (val == null || val === 0) return "var(--muted)";
  return val > 0 ? GREEN : RED;
}

/**
 * cardBg — compute a background colour with opacity proportional to |change%|.
 * Caps at 0.3 opacity so cards remain readable.
 * @param {number} changePct - Daily change percentage
 * @returns {string} CSS rgba colour string
 */
function cardBg(changePct) {
  const abs = Math.min(Math.abs(changePct || 0), 5); // cap at 5%
  const opacity = Math.min(abs / 5 * 0.3, 0.3);      // max 0.3 opacity
  const base = (changePct || 0) >= 0 ? "34,197,94" : "239,68,68";
  return `rgba(${base},${opacity})`;
}


/* ── Sector Sparkline sub-component ────────────────────────────────────── */

/**
 * SectorSparkline — renders a small SVG polyline showing synthetic
 * recent performance for a sector.  Since there is no historical sector
 * data endpoint, we derive five points from the available percentage
 * metrics and normalise them to fit within a 60x24 viewport.
 *
 * Point generation:
 *   [0, month_pct/2, (month_pct + ytd_pct) / 4, change_pct, change_pct]
 *
 * @param {object} props
 * @param {number|null} props.changePct - Daily change %
 * @param {number|null} props.ytdPct    - Year-to-date change %
 * @param {number|null} props.monthPct  - 1-month change %
 * @returns {JSX.Element} 60x24 SVG sparkline
 */
function SectorSparkline({ changePct, ytdPct, monthPct }) {
  const c = changePct || 0;
  const y = ytdPct    || 0;
  const m = monthPct  || 0;

  // Build 5 synthetic data points from available percentage metrics
  const raw = [0, m / 2, (m + y) / 4, c, c];

  // Determine min/max for normalisation into the 24px height
  const min = Math.min(...raw);
  const max = Math.max(...raw);
  const range = max - min || 1; // avoid division by zero

  const W = 60;
  const H = 24;
  const PAD = 2; // vertical padding so stroke isn't clipped

  // Map raw values to SVG y-coordinates (inverted: higher value = lower y)
  const points = raw.map((val, i) => {
    const x = (i / (raw.length - 1)) * W;
    const y = PAD + ((max - val) / range) * (H - PAD * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  // Colour: green when overall direction is positive, red otherwise
  const strokeColour = c >= 0 ? GREEN : RED;

  return (
    <svg
      width={W}
      height={H}
      viewBox={`0 0 ${W} ${H}`}
      style={{ display: "block" }}
      aria-hidden="true"
    >
      <polyline
        points={points.join(" ")}
        fill="none"
        stroke={strokeColour}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}


/* ── Sector Card sub-component ───────────────────────────────────────────── */

/**
 * SectorCard — renders a single sector ETF performance tile with a
 * sparkline indicator in the bottom-right corner.
 *
 * @param {object} props
 * @param {object} props.sector   - SectorItem data
 * @param {Function} props.onClick - Callback when the card is clicked
 */
function SectorCard({ sector, onClick }) {
  return (
    <div
      onClick={onClick}
      style={{
        background: cardBg(sector.change_pct),
        border: "1px solid rgba(255,255,255,0.06)",
        borderRadius: 8,
        padding: 16,
        cursor: "pointer",
        transition: "transform 0.15s, box-shadow 0.15s",
        minWidth: 0,
        position: "relative", // anchor for the sparkline overlay
      }}
      onMouseOver={(e) => {
        e.currentTarget.style.transform = "translateY(-2px)";
        e.currentTarget.style.boxShadow = "0 4px 12px rgba(0,0,0,0.3)";
      }}
      onMouseOut={(e) => {
        e.currentTarget.style.transform = "none";
        e.currentTarget.style.boxShadow = "none";
      }}
    >
      {/* Sector name */}
      <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 2, color: "#e5e5e5" }}>
        {sector.name}
      </div>
      {/* ETF symbol (muted) */}
      <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 10, fontFamily: "var(--font-mono)" }}>
        {sector.symbol}
      </div>
      {/* Daily change % — prominent */}
      <div style={{ fontSize: 22, fontWeight: 700, color: pctColor(sector.change_pct), marginBottom: 6 }}>
        {fmtPct(sector.change_pct)}
      </div>
      {/* Price */}
      <div style={{ fontSize: 13, color: "#ccc", marginBottom: 8 }}>
        {fmtPrice(sector.price)}
      </div>
      {/* YTD and 1M row */}
      <div style={{ display: "flex", gap: 12, fontSize: 11 }}>
        <span style={{ color: "var(--muted)" }}>
          YTD <span style={{ color: pctColor(sector.ytd_pct) }}>{fmtPct(sector.ytd_pct)}</span>
        </span>
        <span style={{ color: "var(--muted)" }}>
          1M <span style={{ color: pctColor(sector.month_pct) }}>{fmtPct(sector.month_pct)}</span>
        </span>
      </div>
      {/* Sparkline — synthetic performance curve, bottom-right of the card */}
      <div style={{ position: "absolute", bottom: 10, right: 10, opacity: 0.7 }}>
        <SectorSparkline
          changePct={sector.change_pct}
          ytdPct={sector.ytd_pct}
          monthPct={sector.month_pct}
        />
      </div>
    </div>
  );
}


/* ── Spinner sub-component ───────────────────────────────────────────────── */

/**
 * Spinner — simple CSS loading indicator.
 * @param {object} props
 * @param {string} [props.text] - Optional text below the spinner
 */
function Spinner({ text }) {
  return (
    <div style={{ textAlign: "center", padding: "48px 0", color: "var(--muted)" }}>
      <div
        style={{
          width: 32, height: 32, border: "3px solid rgba(255,255,255,0.1)",
          borderTopColor: AMBER, borderRadius: "50%",
          animation: "spin 0.8s linear infinite", margin: "0 auto 12px",
        }}
      />
      {text && <div style={{ fontSize: 12, letterSpacing: 1 }}>{text}</div>}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}


/* ── Shared input style ──────────────────────────────────────────────────── */

/** Base style object for filter inputs and selects. */
const INPUT_STYLE = {
  background: "#1a1a2e",
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: 4,
  color: "#e5e5e5",
  padding: "6px 10px",
  fontSize: 12,
  fontFamily: "var(--font-mono)",
  outline: "none",
  transition: "border-color 0.15s",
  width: 100,
};


/* ── Main component ──────────────────────────────────────────────────────── */

/**
 * ResearchPage — top-level Research page with SECTORS and SCREENER tabs.
 *
 * @param {object} props
 * @param {string}   props.token       - JWT access token
 * @param {Function} props.onViewChart - Callback to open a chart for a symbol
 */
export default function ResearchPage({ token, onViewChart }) {
  /* ── Tab state ────────────────────────────────────────────────────────── */
  const [activeTab, setActiveTab] = useState("sectors");

  /* ── Sectors state ────────────────────────────────────────────────────── */
  const [sectors, setSectors]         = useState([]);
  const [sectorsLoading, setSectorsLoading] = useState(true);
  const [sectorsError, setSectorsError]     = useState("");

  /* ── Screener state ───────────────────────────────────────────────────── */
  const [screenerResults, setScreenerResults]   = useState([]);
  const [screenerTotal, setScreenerTotal]       = useState(0);
  const [screenerLoading, setScreenerLoading]   = useState(false);
  const [screenerError, setScreenerError]       = useState("");
  const [screenerRan, setScreenerRan]           = useState(false);

  /* ── Filter state ─────────────────────────────────────────────────────── */
  const [fMinPrice,    setFMinPrice]    = useState("");
  const [fMaxPrice,    setFMaxPrice]    = useState("");
  const [fMinChangePct, setFMinChangePct] = useState("");
  const [fMaxChangePct, setFMaxChangePct] = useState("");
  const [fMinVolume,   setFMinVolume]   = useState("");
  const [fSector,      setFSector]      = useState("");
  const [fSortBy,      setFSortBy]      = useState("change_pct");
  const [fSortDir,     setFSortDir]     = useState("desc");
  const [fAboveSma50,  setFAboveSma50]  = useState(false);

  /* ── Watchlist / portfolio IDs for quick-add action buttons ──────────── */
  const [defaultWatchlistId, setDefaultWatchlistId] = useState(null);
  const [defaultPortfolioId, setDefaultPortfolioId] = useState(null);

  /* ── Action feedback — brief toast-like messages shown inline ─────── */
  const [actionFeedback, setActionFeedback] = useState(null);

  /**
   * showFeedback — display a brief inline notification that auto-clears.
   * @param {string} msg   - Message text
   * @param {boolean} isErr - True for error styling
   */
  const showFeedback = useCallback((msg, isErr = false) => {
    setActionFeedback({ msg, isErr });
    setTimeout(() => setActionFeedback(null), 2500);
  }, []);

  /* ── Fetch default watchlist & portfolio IDs on mount ────────────── */
  useEffect(() => {
    if (!token) return;

    // Resolve the first available watchlist for the "add to watchlist" button
    api.getWatchlists(token)
      .then((lists) => {
        const arr = Array.isArray(lists) ? lists : lists?.watchlists || [];
        if (arr.length > 0) setDefaultWatchlistId(arr[0].id || arr[0].watchlist_id);
      })
      .catch(() => {}); // non-fatal — button will show feedback on failure

    // Resolve the first available portfolio for the "add to portfolio" button
    api.listPortfolios(token)
      .then((res) => {
        const arr = Array.isArray(res) ? res : res?.portfolios || [];
        if (arr.length > 0) setDefaultPortfolioId(arr[0].id || arr[0].portfolio_id);
      })
      .catch(() => {}); // non-fatal
  }, [token]);

  /* ── Fetch sectors on mount ──────────────────────────────────────────── */
  useEffect(() => {
    if (!token) return;
    let cancelled = false;

    /** loadSectors — fetch sector ETF performance from the API. */
    async function loadSectors() {
      setSectorsLoading(true);
      setSectorsError("");
      try {
        // api.getSectors returns { sectors: [...] }
        const data = await api.getSectors(token);
        if (!cancelled) setSectors(data.sectors || []);
      } catch (err) {
        if (!cancelled) setSectorsError(err.message || "Failed to load sectors");
      } finally {
        if (!cancelled) setSectorsLoading(false);
      }
    }

    loadSectors();
    return () => { cancelled = true; };
  }, [token]);

  /* ── Run screener ────────────────────────────────────────────────────── */

  /**
   * handleScan — build filter params and call the screener API endpoint.
   * Sends only non-empty filter values as query parameters.
   */
  const handleScan = useCallback(async () => {
    if (!token) return;
    setScreenerLoading(true);
    setScreenerError("");
    setScreenerRan(true);

    const params = {
      sort_by: fSortBy,
      sort_dir: fSortDir,
      limit: 50,
    };
    if (fMinPrice)     params.min_price = fMinPrice;
    if (fMaxPrice)     params.max_price = fMaxPrice;
    if (fMinChangePct) params.min_change_pct = fMinChangePct;
    if (fMaxChangePct) params.max_change_pct = fMaxChangePct;
    if (fMinVolume)    params.min_volume = fMinVolume;
    if (fSector)       params.sector = fSector;
    if (fAboveSma50)   params.above_sma50 = true;

    try {
      // api.runScreener returns { results, total_matched, filters_applied }
      const data = await api.runScreener(params, token);
      setScreenerResults(data.results || []);
      setScreenerTotal(data.total_matched || 0);
    } catch (err) {
      setScreenerError(err.message || "Screener failed");
    } finally {
      setScreenerLoading(false);
    }
  }, [token, fMinPrice, fMaxPrice, fMinChangePct, fMaxChangePct, fMinVolume, fSector, fAboveSma50, fSortBy, fSortDir]);

  /* ── Sector card click → switch to screener with that sector pre-filled ── */

  /**
   * handleSectorClick — pre-fill the sector filter and run a scan.
   * @param {string} sectorName - Sector name to filter by (e.g. "Technology")
   */
  const handleSectorClick = useCallback((sectorName) => {
    setFSector(sectorName);
    setActiveTab("screener");
    // Trigger a scan with the pre-filled sector after state settles
    setTimeout(() => {
      // Build params directly instead of relying on stale closure
      const params = {
        sort_by: fSortBy,
        sort_dir: fSortDir,
        limit: 50,
        sector: sectorName,
      };
      if (fMinPrice)     params.min_price = fMinPrice;
      if (fMaxPrice)     params.max_price = fMaxPrice;
      if (fMinChangePct) params.min_change_pct = fMinChangePct;
      if (fMaxChangePct) params.max_change_pct = fMaxChangePct;
      if (fMinVolume)    params.min_volume = fMinVolume;
      if (fAboveSma50)   params.above_sma50 = true;

      setScreenerLoading(true);
      setScreenerError("");
      setScreenerRan(true);

      api.runScreener(params, token)
        .then((data) => {
          setScreenerResults(data.results || []);
          setScreenerTotal(data.total_matched || 0);
        })
        .catch((err) => setScreenerError(err.message || "Screener failed"))
        .finally(() => setScreenerLoading(false));
    }, 50);
  }, [token, fSortBy, fSortDir, fMinPrice, fMaxPrice, fMinChangePct, fMaxChangePct, fMinVolume]);

  /* ── Handle Enter key in filter inputs ──────────────────────────────── */

  /**
   * handleFilterKeyDown — run scan when Enter is pressed in any filter input.
   * @param {KeyboardEvent} e
   */
  const handleFilterKeyDown = (e) => {
    if (e.key === "Enter") handleScan();
  };

  /* ── Quick-add: watchlist ─────────────────────────────────────────────── */

  /**
   * handleAddToWatchlist — add a symbol to the user's default watchlist.
   * Shows inline feedback on success or failure.
   * @param {string} symbol - Ticker symbol (e.g. "AAPL")
   */
  const handleAddToWatchlist = useCallback(async (symbol) => {
    if (!defaultWatchlistId) {
      showFeedback("No watchlist found — create one first", true);
      return;
    }
    try {
      // api.addWatchlistItem expects (watchlistId, body, token)
      await api.addWatchlistItem(defaultWatchlistId, { symbol, asset_type: "stock" }, token);
      showFeedback(`${symbol} added to watchlist`);
    } catch (err) {
      showFeedback(err.message || `Failed to add ${symbol}`, true);
    }
  }, [defaultWatchlistId, token, showFeedback]);

  /* ── Quick-add: portfolio ────────────────────────────────────────────── */

  /**
   * handleAddToPortfolio — add a symbol to the user's default portfolio
   * as a tracking position (quantity 0, price 0).
   * Shows inline feedback on success or failure.
   * @param {string} symbol - Ticker symbol (e.g. "AAPL")
   */
  const handleAddToPortfolio = useCallback(async (symbol) => {
    if (!defaultPortfolioId) {
      showFeedback("No portfolio found — create one first", true);
      return;
    }
    try {
      // api.addPosition expects (portfolioId, body, token)
      await api.addPosition(defaultPortfolioId, { symbol, quantity: 0, avg_price: 0 }, token);
      showFeedback(`${symbol} added to portfolio`);
    } catch (err) {
      showFeedback(err.message || `Failed to add ${symbol}`, true);
    }
  }, [defaultPortfolioId, token, showFeedback]);

  /* ── Render ─────────────────────────────────────────────────────────── */
  return (
    <div className="page-scroll">
    <div style={{ padding: "24px 28px", maxWidth: 1400, margin: "0 auto" }}>
      {/* Inline action feedback notification — floats top-right */}
      {actionFeedback && (
        <div
          style={{
            position: "fixed",
            top: 60,
            right: 24,
            zIndex: 9999,
            background: actionFeedback.isErr ? "rgba(239,68,68,0.15)" : "rgba(34,197,94,0.15)",
            border: `1px solid ${actionFeedback.isErr ? RED : GREEN}`,
            color: actionFeedback.isErr ? RED : GREEN,
            borderRadius: 6,
            padding: "8px 16px",
            fontSize: 12,
            fontWeight: 600,
            fontFamily: "var(--font-mono)",
            letterSpacing: 0.5,
            pointerEvents: "none",
          }}
        >
          {actionFeedback.msg}
        </div>
      )}
      {/* Page header */}
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 18, fontWeight: 700, letterSpacing: 1, color: "#e5e5e5", margin: 0 }}>
          RESEARCH
        </h1>
        <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>
          Sector analysis and stock screener
        </div>
      </div>

      {/* ── Tab switcher ─────────────────────────────────────────────────── */}
      <div style={{ display: "flex", gap: 0, marginBottom: 20, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              background: "none",
              border: "none",
              borderBottom: activeTab === tab.id ? `2px solid ${AMBER}` : "2px solid transparent",
              color: activeTab === tab.id ? AMBER : "var(--muted)",
              padding: "10px 20px",
              fontSize: 12,
              fontWeight: 700,
              letterSpacing: 1,
              cursor: "pointer",
              fontFamily: "var(--font-mono)",
              transition: "color 0.15s, border-color 0.15s",
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── SECTORS tab ─────────────────────────────────────────────────── */}
      {activeTab === "sectors" && (
        <div>
          {sectorsLoading && <Spinner text="LOADING SECTOR DATA..." />}

          {sectorsError && (
            <div style={{ padding: 20, color: RED, fontSize: 13, textAlign: "center" }}>
              {sectorsError}
            </div>
          )}

          {!sectorsLoading && !sectorsError && sectors.length === 0 && (
            <div style={{ padding: 40, color: "var(--muted)", textAlign: "center", fontSize: 13 }}>
              No sector data available.
            </div>
          )}

          {!sectorsLoading && !sectorsError && sectors.length > 0 && (
            <div
              style={{
                display: "grid",
                /* Lower minimum from 220→180 so more cards fit per row,
                   filling the full container width with less dead space. */
                gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))",
                gap: 12,
              }}
            >
              {sectors.map((s) => (
                <SectorCard
                  key={s.symbol}
                  sector={s}
                  onClick={() => handleSectorClick(s.name)}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── SCREENER tab ────────────────────────────────────────────────── */}
      {activeTab === "screener" && (
        <div>
          {/* Filter bar */}
          <div
            style={{
              background: "rgba(255,255,255,0.02)",
              border: "1px solid rgba(255,255,255,0.06)",
              borderRadius: 8,
              padding: "14px 18px",
              marginBottom: 16,
              display: "flex",
              flexWrap: "wrap",
              gap: 12,
              alignItems: "flex-end",
            }}
          >
            {/* Min Price */}
            <label style={{ fontSize: 10, color: "var(--muted)", letterSpacing: 0.5 }}>
              MIN PRICE
              <input
                type="number"
                value={fMinPrice}
                onChange={(e) => setFMinPrice(e.target.value)}
                onKeyDown={handleFilterKeyDown}
                placeholder="0"
                style={INPUT_STYLE}
                onFocus={(e) => { e.target.style.borderColor = AMBER; }}
                onBlur={(e) => { e.target.style.borderColor = "rgba(255,255,255,0.1)"; }}
              />
            </label>

            {/* Max Price */}
            <label style={{ fontSize: 10, color: "var(--muted)", letterSpacing: 0.5 }}>
              MAX PRICE
              <input
                type="number"
                value={fMaxPrice}
                onChange={(e) => setFMaxPrice(e.target.value)}
                onKeyDown={handleFilterKeyDown}
                placeholder="9999"
                style={INPUT_STYLE}
                onFocus={(e) => { e.target.style.borderColor = AMBER; }}
                onBlur={(e) => { e.target.style.borderColor = "rgba(255,255,255,0.1)"; }}
              />
            </label>

            {/* Min Change % */}
            <label style={{ fontSize: 10, color: "var(--muted)", letterSpacing: 0.5 }}>
              MIN CHG%
              <input
                type="number"
                step="0.1"
                value={fMinChangePct}
                onChange={(e) => setFMinChangePct(e.target.value)}
                onKeyDown={handleFilterKeyDown}
                placeholder="-99"
                style={INPUT_STYLE}
                onFocus={(e) => { e.target.style.borderColor = AMBER; }}
                onBlur={(e) => { e.target.style.borderColor = "rgba(255,255,255,0.1)"; }}
              />
            </label>

            {/* Max Change % */}
            <label style={{ fontSize: 10, color: "var(--muted)", letterSpacing: 0.5 }}>
              MAX CHG%
              <input
                type="number"
                step="0.1"
                value={fMaxChangePct}
                onChange={(e) => setFMaxChangePct(e.target.value)}
                onKeyDown={handleFilterKeyDown}
                placeholder="99"
                style={INPUT_STYLE}
                onFocus={(e) => { e.target.style.borderColor = AMBER; }}
                onBlur={(e) => { e.target.style.borderColor = "rgba(255,255,255,0.1)"; }}
              />
            </label>

            {/* Min Volume */}
            <label style={{ fontSize: 10, color: "var(--muted)", letterSpacing: 0.5 }}>
              MIN VOLUME
              <input
                type="number"
                value={fMinVolume}
                onChange={(e) => setFMinVolume(e.target.value)}
                onKeyDown={handleFilterKeyDown}
                placeholder="0"
                style={{ ...INPUT_STYLE, width: 110 }}
                onFocus={(e) => { e.target.style.borderColor = AMBER; }}
                onBlur={(e) => { e.target.style.borderColor = "rgba(255,255,255,0.1)"; }}
              />
            </label>

            {/* Sector dropdown */}
            <label style={{ fontSize: 10, color: "var(--muted)", letterSpacing: 0.5 }}>
              SECTOR
              <select
                value={fSector}
                onChange={(e) => setFSector(e.target.value)}
                style={{ ...INPUT_STYLE, width: 160 }}
                onFocus={(e) => { e.target.style.borderColor = AMBER; }}
                onBlur={(e) => { e.target.style.borderColor = "rgba(255,255,255,0.1)"; }}
              >
                <option value="">All Sectors</option>
                {SECTOR_NAMES.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </label>

            {/* Sort by dropdown */}
            <label style={{ fontSize: 10, color: "var(--muted)", letterSpacing: 0.5 }}>
              SORT BY
              <select
                value={fSortBy}
                onChange={(e) => setFSortBy(e.target.value)}
                style={{ ...INPUT_STYLE, width: 120 }}
                onFocus={(e) => { e.target.style.borderColor = AMBER; }}
                onBlur={(e) => { e.target.style.borderColor = "rgba(255,255,255,0.1)"; }}
              >
                {SORT_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </label>

            {/* Sort direction toggle */}
            <label style={{ fontSize: 10, color: "var(--muted)", letterSpacing: 0.5 }}>
              DIR
              <select
                value={fSortDir}
                onChange={(e) => setFSortDir(e.target.value)}
                style={{ ...INPUT_STYLE, width: 70 }}
                onFocus={(e) => { e.target.style.borderColor = AMBER; }}
                onBlur={(e) => { e.target.style.borderColor = "rgba(255,255,255,0.1)"; }}
              >
                <option value="desc">DESC</option>
                <option value="asc">ASC</option>
              </select>
            </label>

            {/* Above SMA50 toggle */}
            <label
              onClick={() => setFAboveSma50((v) => !v)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                cursor: "pointer",
                padding: "6px 14px",
                borderRadius: 4,
                border: `1px solid ${fAboveSma50 ? AMBER : "rgba(255,255,255,0.1)"}`,
                background: fAboveSma50 ? `${AMBER}18` : "rgba(255,255,255,0.03)",
                fontFamily: "var(--font-mono)",
                fontSize: 10,
                fontWeight: 600,
                letterSpacing: 0.5,
                color: fAboveSma50 ? AMBER : "var(--muted)",
                alignSelf: "flex-end",
                marginTop: 6,
                transition: "all 0.15s",
                userSelect: "none",
                whiteSpace: "nowrap",
              }}
            >
              {/* Toggle indicator */}
              <span style={{
                width: 10,
                height: 10,
                borderRadius: 2,
                border: `1.5px solid ${fAboveSma50 ? AMBER : "rgba(255,255,255,0.2)"}`,
                background: fAboveSma50 ? AMBER : "transparent",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}>
                {fAboveSma50 && <span style={{ color: "#000", fontSize: 8, fontWeight: 900 }}>&#x2713;</span>}
              </span>
              ABOVE 50 SMA
            </label>

            {/* SCAN button */}
            <button
              onClick={handleScan}
              disabled={screenerLoading}
              style={{
                background: AMBER,
                color: "#000",
                border: "none",
                borderRadius: 4,
                padding: "8px 20px",
                fontSize: 12,
                fontWeight: 700,
                letterSpacing: 1,
                cursor: screenerLoading ? "not-allowed" : "pointer",
                fontFamily: "var(--font-mono)",
                opacity: screenerLoading ? 0.6 : 1,
                alignSelf: "flex-end",
                marginTop: 6,
              }}
            >
              {screenerLoading ? "SCANNING..." : "SCAN"}
            </button>
          </div>

          {/* Screener error */}
          {screenerError && (
            <div style={{ padding: 16, color: RED, fontSize: 13, textAlign: "center" }}>
              {screenerError}
            </div>
          )}

          {/* Screener loading */}
          {screenerLoading && <Spinner text="SCANNING MARKET..." />}

          {/* Screener prompt (before first scan) */}
          {!screenerLoading && !screenerRan && !screenerError && (
            <div style={{ padding: 48, textAlign: "center", color: "var(--muted)", fontSize: 13 }}>
              Set your filters and click <strong style={{ color: AMBER }}>SCAN</strong> to screen stocks.
            </div>
          )}

          {/* Screener results */}
          {!screenerLoading && screenerRan && !screenerError && (
            <div>
              {/* Results count */}
              <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 10, letterSpacing: 0.5 }}>
                {screenerTotal} MATCH{screenerTotal !== 1 ? "ES" : ""} FOUND
              </div>

              {screenerResults.length === 0 ? (
                <div style={{ padding: 40, textAlign: "center", color: "var(--muted)", fontSize: 13 }}>
                  No stocks match your filters. Try adjusting the criteria.
                </div>
              ) : (
                /* Results table */
                <div style={{ overflowX: "auto" }}>
                  <table className="data-table" style={{ width: "100%", borderCollapse: "collapse" }}>
                    <thead>
                      <tr>
                        <th style={TH_STYLE}>SYMBOL</th>
                        <th style={TH_STYLE}>NAME</th>
                        <th style={{ ...TH_STYLE, textAlign: "right" }}>PRICE</th>
                        <th style={{ ...TH_STYLE, textAlign: "right" }}>CHG</th>
                        <th style={{ ...TH_STYLE, textAlign: "right" }}>CHG%</th>
                        <th style={{ ...TH_STYLE, textAlign: "right" }}>VOLUME</th>
                        <th style={{ ...TH_STYLE, textAlign: "right" }}>MKT CAP</th>
                        <th style={TH_STYLE}>SECTOR</th>
                        <th style={{ ...TH_STYLE, textAlign: "right" }}>SMA50</th>
                        <th style={{ ...TH_STYLE, textAlign: "center" }}>ACTIONS</th>
                      </tr>
                    </thead>
                    <tbody>
                      {screenerResults.map((row) => (
                        <tr
                          key={row.symbol}
                          style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}
                          onMouseOver={(e) => { e.currentTarget.style.background = "rgba(255,255,255,0.03)"; }}
                          onMouseOut={(e) => { e.currentTarget.style.background = "none"; }}
                        >
                          {/* Symbol — clickable amber link to chart */}
                          <td style={TD_STYLE}>
                            <span
                              onClick={() => onViewChart && onViewChart(row.symbol)}
                              style={{
                                color: AMBER,
                                cursor: "pointer",
                                fontWeight: 700,
                                fontFamily: "var(--font-mono)",
                                textDecoration: "none",
                              }}
                              onMouseOver={(e) => { e.currentTarget.style.textDecoration = "underline"; }}
                              onMouseOut={(e) => { e.currentTarget.style.textDecoration = "none"; }}
                            >
                              {row.symbol}
                            </span>
                          </td>
                          {/* Company name (truncated) */}
                          <td style={{ ...TD_STYLE, maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {row.name}
                          </td>
                          {/* Price */}
                          <td style={{ ...TD_STYLE, textAlign: "right", fontFamily: "var(--font-mono)" }}>
                            {fmtPrice(row.price)}
                          </td>
                          {/* Absolute change */}
                          <td style={{ ...TD_STYLE, textAlign: "right", fontFamily: "var(--font-mono)", color: pctColor(row.change) }}>
                            {row.change >= 0 ? "+" : ""}{row.change.toFixed(2)}
                          </td>
                          {/* Change % */}
                          <td style={{ ...TD_STYLE, textAlign: "right", fontFamily: "var(--font-mono)", color: pctColor(row.change_pct), fontWeight: 600 }}>
                            {fmtPct(row.change_pct)}
                          </td>
                          {/* Volume */}
                          <td style={{ ...TD_STYLE, textAlign: "right", fontFamily: "var(--font-mono)" }}>
                            {fmtVolume(row.volume)}
                          </td>
                          {/* Market cap */}
                          <td style={{ ...TD_STYLE, textAlign: "right", fontFamily: "var(--font-mono)" }}>
                            {fmtMarketCap(row.market_cap)}
                          </td>
                          {/* Sector */}
                          <td style={{ ...TD_STYLE, fontSize: 11, color: "var(--muted)" }}>
                            {row.sector || "--"}
                          </td>
                          {/* SMA50 — show value and color-code vs current price */}
                          <td style={{ ...TD_STYLE, textAlign: "right", fontSize: 11 }}>
                            {row.sma50 != null
                              ? <span style={{ color: row.price > row.sma50 ? GREEN : RED }}>
                                  ${row.sma50.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </span>
                              : <span style={{ color: "var(--muted)" }}>--</span>}
                          </td>
                          {/* Action buttons — chart, watchlist, portfolio */}
                          <td style={{ ...TD_STYLE, textAlign: "center", whiteSpace: "nowrap" }}>
                            <div style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
                              {/* Chart icon — opens chart in a new tab */}
                              <button
                                title={`Open chart for ${row.symbol}`}
                                onClick={(e) => { e.stopPropagation(); onViewChart && onViewChart(row.symbol); }}
                                style={ACTION_BTN_STYLE}
                                onMouseOver={(e) => { e.currentTarget.style.color = AMBER; }}
                                onMouseOut={(e) => { e.currentTarget.style.color = "var(--muted)"; }}
                              >
                                {/* Chart SVG icon (simple bar chart) */}
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                  <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
                                </svg>
                              </button>
                              {/* Star icon — add to default watchlist */}
                              <button
                                title={`Add ${row.symbol} to watchlist`}
                                onClick={(e) => { e.stopPropagation(); handleAddToWatchlist(row.symbol); }}
                                style={ACTION_BTN_STYLE}
                                onMouseOver={(e) => { e.currentTarget.style.color = AMBER; }}
                                onMouseOut={(e) => { e.currentTarget.style.color = "var(--muted)"; }}
                              >
                                {/* Star SVG icon */}
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                  <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
                                </svg>
                              </button>
                              {/* Plus icon — add to default portfolio */}
                              <button
                                title={`Add ${row.symbol} to portfolio`}
                                onClick={(e) => { e.stopPropagation(); handleAddToPortfolio(row.symbol); }}
                                style={ACTION_BTN_STYLE}
                                onMouseOver={(e) => { e.currentTarget.style.color = AMBER; }}
                                onMouseOut={(e) => { e.currentTarget.style.color = "var(--muted)"; }}
                              >
                                {/* Plus-circle SVG icon */}
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                  <circle cx="12" cy="12" r="10" />
                                  <line x1="12" y1="8" x2="12" y2="16" />
                                  <line x1="8" y1="12" x2="16" y2="12" />
                                </svg>
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
    </div>
  );
}


/* ── Table cell style constants ──────────────────────────────────────────── */

/** Header cell style for the screener results table. */
const TH_STYLE = {
  padding: "8px 12px",
  fontSize: 10,
  fontWeight: 700,
  letterSpacing: 1,
  color: "var(--muted)",
  textAlign: "left",
  borderBottom: "1px solid rgba(255,255,255,0.08)",
  whiteSpace: "nowrap",
  fontFamily: "var(--font-mono)",
};

/** Body cell style for the screener results table. */
const TD_STYLE = {
  padding: "10px 12px",
  fontSize: 13,
  color: "#e5e5e5",
  whiteSpace: "nowrap",
};

/** Style for the small action icon buttons in each screener row. */
const ACTION_BTN_STYLE = {
  background: "none",
  border: "1px solid rgba(255,255,255,0.08)",
  borderRadius: 4,
  color: "var(--muted)",
  cursor: "pointer",
  padding: 4,
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  transition: "color 0.15s, border-color 0.15s",
  lineHeight: 0,
};
