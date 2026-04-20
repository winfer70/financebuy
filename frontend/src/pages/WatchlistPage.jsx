/**
 * WatchlistPage.jsx
 *
 * Full-featured watchlist manager: create named watchlists, track symbols
 * with live prices, day range, and performance since added. Buy directly
 * into portfolios from the watchlist.
 *
 * Asset sections: ALL | STOCKS | CRYPTO | ETFs | PHYSICAL
 * Each section filters items by asset_type.
 *
 * Data flow:
 *   1. Load watchlists on mount -> auto-select first
 *   2. Load items when active watchlist changes
 *   3. Load live quotes from bulkQuotes after items load
 *   4. Poll quotes every 30s when market is open (via useMarketStatus)
 *   5. All mutations reload items + quotes
 */

import { useState, useEffect, useMemo, useCallback } from "react";
import api from "../api/client";
import { Ic } from "../components/common/Icons";
import { useCurrency } from "../context/CurrencyContext";
import { useI18n } from "../context/I18nContext";
import { useMarketStatus } from "../components/common";
import { fmtPct } from "../utils/formatters";
import { MODAL_BACKDROP as BDK } from "../styles/shared";
import AssetDetailPanel from "../components/common/AssetDetailPanel";
import AlertModal from "../components/common/AlertModal";

/* ── Asset section IDs (labels resolved via t() inside each component) ── */

/* ── Quote polling interval (ms) ────────────────────────────────────────── */
const POLL_OPEN_MS   = 30_000;  // 30 seconds when market is open
const POLL_CLOSED_MS = 300_000; // 5 minutes when market is closed

/* =========================================================================
   MODAL: Create Watchlist
   Simple name input modal to create a new watchlist.
========================================================================= */

/**
 * CreateWatchlistModal — renders a modal for creating a new watchlist.
 *
 * @param {object}   props
 * @param {Function} props.onClose   - callback to close the modal
 * @param {Function} props.onCreated - callback with the created watchlist object
 * @param {string}   props.token     - JWT access token
 */
function CreateWatchlistModal({ onClose, onCreated, token }) {
  const { t } = useI18n();
  const [name,    setName]    = useState("");
  const [loading, setLoading] = useState(false);
  const [err,     setErr]     = useState("");

  /**
   * submit — validates the name and calls the create watchlist API.
   */
  const submit = async () => {
    if (!name.trim()) { setErr(t("watchlist.nameRequired")); return; }
    setLoading(true); setErr("");
    try {
      // api.createWatchlist — POST /watchlists, returns the new watchlist object
      const wl = await api.createWatchlist({ name: name.trim() }, token);
      onCreated(wl);
    } catch (e) { setErr(e.message || "Failed to create watchlist."); }
    finally { setLoading(false); }
  };

  return (
    <div className="modal-overlay" style={BDK} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-box">
        <div className="modal-top">
          <div className="modal-title">{t("watchlist.newWatchlist")}</div>
          <button className="modal-close" onClick={onClose}><Ic.close /></button>
        </div>
        <div className="modal-body">
          <div className="form-field">
            <label className="form-label">{t("watchlist.watchlistName")} *</label>
            <input
              className="form-control"
              placeholder="e.g. Tech Watchlist"
              value={name}
              onChange={e => setName(e.target.value)}
              maxLength={128}
              onKeyDown={e => { if (e.key === "Enter") submit(); }}
            />
          </div>
        </div>
        {err && (
          <div style={{ padding: "8px 20px", fontSize: 11, color: "var(--red)", background: "rgba(239,68,68,.06)", borderTop: "1px solid rgba(239,68,68,.2)" }}>
            {err}
          </div>
        )}
        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose}>{t("common.cancel")}</button>
          <button className="btn btn-amber" onClick={submit} disabled={loading}>
            {loading ? <span className="loading-pulse">{t("watchlist.creating")}</span> : t("watchlist.create")}
          </button>
        </div>
      </div>
    </div>
  );
}

/* =========================================================================
   MODAL: Add Watchlist Item
   Symbol input with auto-set asset_type from current section, optional notes.
========================================================================= */

/**
 * AddItemModal — renders a modal for adding a symbol to the watchlist.
 *
 * When `assetType` is null (user is on the ALL tab), the modal shows a
 * dropdown at the top so the user can select an asset type before entering
 * a symbol. When `assetType` is provided (a specific section tab), the
 * dropdown is hidden and the provided type is used directly.
 *
 * @param {object}      props
 * @param {string}      props.watchlistId  - ID of the active watchlist
 * @param {string|null} props.assetType    - asset type from the active section
 *                                           ("stock", "crypto", "etf", "physical"),
 *                                           or null when opened from the ALL tab
 * @param {Function}    props.onClose      - callback to close the modal
 * @param {Function}    props.onAdded      - callback with the created item object
 * @param {string}      props.token        - JWT access token
 */
function AddItemModal({ watchlistId, assetType, onClose, onAdded, token }) {
  const { t } = useI18n();
  const [symbol,            setSymbol]            = useState("");
  /* selectedAssetType is only used when assetType prop is null (ALL tab) */
  const [selectedAssetType, setSelectedAssetType] = useState("");
  const [notes,             setNotes]             = useState("");
  const [loading,           setLoading]           = useState(false);
  const [err,               setErr]               = useState("");

  /* Effective asset type: use the prop if provided, otherwise use local selection */
  const effectiveType = assetType || selectedAssetType;

  /**
   * submit — validates symbol (and asset type when on ALL tab) and calls
   * the addWatchlistItem API.
   */
  const submit = async () => {
    if (!assetType && !selectedAssetType) { setErr(t("watchlist.assetTypeRequired") || "Select an asset type."); return; }
    if (!symbol.trim()) { setErr(t("watchlist.symbolRequired")); return; }
    setLoading(true); setErr("");
    try {
      const payload = {
        symbol: symbol.trim().toUpperCase(),
        asset_type: effectiveType,
        notes: notes.trim() || null,
      };
      // api.addWatchlistItem — POST /watchlists/:id/items, returns the new item
      const item = await api.addWatchlistItem(watchlistId, payload, token);
      onAdded(item);
    } catch (e) { setErr(e.message || "Failed to add item."); }
    finally { setLoading(false); }
  };

  // Derive placeholder based on effective asset type for better UX
  const placeholders = {
    stock:    "e.g. AAPL",
    crypto:   "e.g. BTC-USD",
    etf:      "e.g. SPY",
    physical: "e.g. GC=F",
  };

  return (
    <div className="modal-overlay" style={BDK} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-box">
        <div className="modal-top">
          <div className="modal-title">{t("watchlist.addToWatchlist")}</div>
          <button className="modal-close" onClick={onClose}><Ic.close /></button>
        </div>
        <div className="modal-body">
          {/* Asset type selector — only shown when opened from the ALL tab (assetType is null) */}
          {!assetType && (
            <div className="form-field">
              <label className="form-label">{t("watchlist.assetType") || "Asset Type"} *</label>
              <select
                className="form-control"
                value={selectedAssetType}
                onChange={e => setSelectedAssetType(e.target.value)}
                style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}
              >
                <option value="">{t("watchlist.selectAssetType") || "Select asset type..."}</option>
                <option value="stock">{t("watchlist.stocks") || "Stocks"}</option>
                <option value="crypto">{t("watchlist.crypto") || "Crypto"}</option>
                <option value="etf">{t("watchlist.etfs") || "ETFs"}</option>
                <option value="physical">{t("watchlist.physical") || "Physical"}</option>
              </select>
            </div>
          )}
          <div className="form-field">
            <label className="form-label">{t("watchlist.symbol")} *</label>
            <input
              className="form-control"
              placeholder={placeholders[effectiveType] || "e.g. AAPL"}
              value={symbol}
              onChange={e => setSymbol(e.target.value.toUpperCase())}
              maxLength={20}
              onKeyDown={e => { if (e.key === "Enter") submit(); }}
            />
          </div>
          <div className="form-field">
            <label className="form-label">{t("watchlist.notesOptional")}</label>
            <textarea
              className="form-control"
              placeholder={t("watchlist.whyWatching")}
              value={notes}
              onChange={e => setNotes(e.target.value)}
              rows={3}
              maxLength={500}
              style={{ resize: "vertical", minHeight: 60, fontFamily: "var(--font-mono)", fontSize: 12 }}
            />
          </div>
        </div>
        {err && (
          <div style={{ padding: "8px 20px", fontSize: 11, color: "var(--red)", background: "rgba(239,68,68,.06)", borderTop: "1px solid rgba(239,68,68,.2)" }}>
            {err}
          </div>
        )}
        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose}>{t("common.cancel")}</button>
          <button className="btn btn-amber" onClick={submit} disabled={loading}>
            {loading ? <span className="loading-pulse">{t("watchlist.adding")}</span> : t("watchlist.addItem")}
          </button>
        </div>
      </div>
    </div>
  );
}

/* =========================================================================
   MODAL: Edit Watchlist Item Notes
   Inline notes editor for an existing watchlist item.
========================================================================= */

/**
 * EditNotesModal — renders a modal to edit the notes on a watchlist item.
 *
 * @param {object}   props
 * @param {object}   props.item        - the watchlist item being edited
 * @param {string}   props.watchlistId - ID of the parent watchlist
 * @param {Function} props.onClose     - callback to close the modal
 * @param {Function} props.onUpdated   - callback with the updated item object
 * @param {string}   props.token       - JWT access token
 */
function EditNotesModal({ item, watchlistId, onClose, onUpdated, token }) {
  const { t } = useI18n();
  const [notes,   setNotes]   = useState(item.notes || "");
  const [loading, setLoading] = useState(false);
  const [err,     setErr]     = useState("");

  /**
   * submit — calls updateWatchlistItem API to save the new notes.
   */
  const submit = async () => {
    setLoading(true); setErr("");
    try {
      // api.updateWatchlistItem — PATCH /watchlists/:wlId/items/:itemId
      const updated = await api.updateWatchlistItem(watchlistId, item.item_id, { notes: notes.trim() || null }, token);
      onUpdated(updated);
    } catch (e) { setErr(e.message || "Failed to update notes."); }
    finally { setLoading(false); }
  };

  return (
    <div className="modal-overlay" style={BDK} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-box">
        <div className="modal-top">
          <div className="modal-title">{t("watchlist.editNotes")} {"\u2014"} {item.symbol}</div>
          <button className="modal-close" onClick={onClose}><Ic.close /></button>
        </div>
        <div className="modal-body">
          <div className="form-field">
            <label className="form-label">{t("watchlist.notes")}</label>
            <textarea
              className="form-control"
              placeholder={t("watchlist.whyWatching")}
              value={notes}
              onChange={e => setNotes(e.target.value)}
              rows={4}
              maxLength={500}
              style={{ resize: "vertical", minHeight: 80, fontFamily: "var(--font-mono)", fontSize: 12 }}
            />
          </div>
        </div>
        {err && (
          <div style={{ padding: "8px 20px", fontSize: 11, color: "var(--red)", background: "rgba(239,68,68,.06)", borderTop: "1px solid rgba(239,68,68,.2)" }}>
            {err}
          </div>
        )}
        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose}>{t("common.cancel")}</button>
          <button className="btn btn-amber" onClick={submit} disabled={loading}>
            {loading ? <span className="loading-pulse">{t("watchlist.saving")}</span> : t("watchlist.saveNotes")}
          </button>
        </div>
      </div>
    </div>
  );
}

/* =========================================================================
   MODAL: Buy From Watchlist
   Buy a watchlist symbol directly into a portfolio.
   Fetches user portfolios, lets user pick portfolio, quantity, price, date.
========================================================================= */

/**
 * BuyFromWatchlistModal — renders a modal to purchase a watched symbol
 * directly into one of the user's portfolios.
 *
 * @param {object}   props
 * @param {object}   props.item        - the watchlist item being bought
 * @param {string}   props.watchlistId - ID of the parent watchlist
 * @param {number}   props.livePrice   - current live price from quotes
 * @param {Function} props.onClose     - callback to close the modal
 * @param {Function} props.onBought    - callback after successful buy
 * @param {string}   props.token       - JWT access token
 */
function BuyFromWatchlistModal({ item, watchlistId, livePrice, onClose, onBought, token }) {
  const { t } = useI18n();
  const [portfolios, setPortfolios] = useState([]);
  const [portfolioId, setPortfolioId] = useState("");
  const [quantity,    setQuantity]    = useState("");
  const [price,       setPrice]       = useState(livePrice != null ? String(livePrice) : "");
  const [date,        setDate]        = useState(() => new Date().toISOString().slice(0, 10));
  const [loading,     setLoading]     = useState(false);
  const [err,         setErr]         = useState("");

  /* Fetch user's portfolios on mount */
  useEffect(() => {
    let cancelled = false;
    /**
     * fetchPortfolios — loads the user's portfolio list for the dropdown.
     * Uses api.listPortfolios (GET /portfolio-manager/portfolios).
     */
    async function fetchPortfolios() {
      try {
        const list = await api.listPortfolios(token);
        if (!cancelled) {
          setPortfolios(list);
          // Auto-select first portfolio if available
          if (list.length > 0) setPortfolioId(list[0].portfolio_id);
        }
      } catch { /* non-fatal — user will see empty dropdown */ }
    }
    fetchPortfolios();
    return () => { cancelled = true; };
  }, [token]);

  /**
   * submit — validates inputs and calls the buyFromWatchlist API.
   */
  const submit = async () => {
    if (!portfolioId) { setErr("Select a portfolio."); return; }
    if (!quantity || isNaN(+quantity) || +quantity <= 0) { setErr("Quantity must be a positive number."); return; }
    if (!price || isNaN(+price) || +price <= 0) { setErr("Price must be a positive number."); return; }
    if (!date) { setErr("Date is required."); return; }
    setLoading(true); setErr("");
    try {
      const payload = {
        portfolio_id: portfolioId,
        quantity: parseFloat(quantity),
        purchase_price: parseFloat(price),
        purchase_date: new Date(date).toISOString(),
      };
      // api.buyFromWatchlist — POST /watchlists/:wlId/items/:itemId/buy
      await api.buyFromWatchlist(watchlistId, item.item_id, payload, token);
      onBought();
    } catch (e) { setErr(e.message || "Buy failed."); }
    finally { setLoading(false); }
  };

  return (
    <div className="modal-overlay" style={BDK} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-box">
        <div className="modal-top">
          <div className="modal-title">{t("watchlist.buy")} {"\u2014"} {item.symbol}</div>
          <button className="modal-close" onClick={onClose}><Ic.close /></button>
        </div>
        <div className="modal-body">
          <div className="form-field">
            <label className="form-label">{t("charts.portfolio")} *</label>
            <select
              className="form-control"
              value={portfolioId}
              onChange={e => setPortfolioId(e.target.value)}
              style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}
            >
              {portfolios.length === 0 && <option value="">{t("watchlist.noPortfoliosBuy")}</option>}
              {portfolios.map(p => (
                <option key={p.portfolio_id} value={p.portfolio_id}>{p.name}</option>
              ))}
            </select>
          </div>
          <div className="form-row">
            <div className="form-field">
              <label className="form-label">Date *</label>
              <input
                className="form-control"
                type="date"
                value={date}
                onChange={e => setDate(e.target.value)}
              />
            </div>
            <div className="form-field">
              <label className="form-label">{t("portfolioManager.quantity")} *</label>
              <input
                className="form-control"
                type="number"
                min="0.000001"
                step="any"
                placeholder="10"
                value={quantity}
                onChange={e => setQuantity(e.target.value)}
              />
            </div>
          </div>
          <div className="form-field">
            <label className="form-label">{t("watchlist.price")} *</label>
            <input
              className="form-control"
              type="number"
              min="0.01"
              step="any"
              placeholder="155.00"
              value={price}
              onChange={e => setPrice(e.target.value)}
            />
            <span className="form-hint">{t("watchlist.preFilled")}</span>
          </div>
        </div>
        {err && (
          <div style={{ padding: "8px 20px", fontSize: 11, color: "var(--red)", background: "rgba(239,68,68,.06)", borderTop: "1px solid rgba(239,68,68,.2)" }}>
            {err}
          </div>
        )}
        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose}>{t("common.cancel")}</button>
          <button className="btn btn-amber" onClick={submit} disabled={loading}>
            {loading ? <span className="loading-pulse">{t("watchlist.buying")}</span> : t("watchlist.confirmBuy")}
          </button>
        </div>
      </div>
    </div>
  );
}

/* =========================================================================
   MODAL: Rename Watchlist
   Simple modal to rename a watchlist.
========================================================================= */

/**
 * RenameWatchlistModal — renders a modal to rename an existing watchlist.
 *
 * @param {object}   props
 * @param {object}   props.watchlist  - the watchlist being renamed
 * @param {Function} props.onClose    - callback to close the modal
 * @param {Function} props.onRenamed  - callback with the updated watchlist object
 * @param {string}   props.token      - JWT access token
 */
function RenameWatchlistModal({ watchlist, onClose, onRenamed, token }) {
  const { t } = useI18n();
  const [name,    setName]    = useState(watchlist.name || "");
  const [loading, setLoading] = useState(false);
  const [err,     setErr]     = useState("");

  /**
   * submit — validates and calls the renameWatchlist API.
   */
  const submit = async () => {
    if (!name.trim()) { setErr(t("watchlist.nameRequired")); return; }
    if (name.trim() === watchlist.name) { onClose(); return; } // No change
    setLoading(true); setErr("");
    try {
      // api.renameWatchlist — PATCH /watchlists/:id, returns updated watchlist
      const updated = await api.renameWatchlist(watchlist.watchlist_id, { name: name.trim() }, token);
      onRenamed(updated);
    } catch (e) { setErr(e.message || "Failed to rename watchlist."); }
    finally { setLoading(false); }
  };

  return (
    <div className="modal-overlay" style={BDK} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-box">
        <div className="modal-top">
          <div className="modal-title">{t("watchlist.rename")}</div>
          <button className="modal-close" onClick={onClose}><Ic.close /></button>
        </div>
        <div className="modal-body">
          <div className="form-field">
            <label className="form-label">{t("watchlist.newName")} *</label>
            <input
              className="form-control"
              value={name}
              onChange={e => setName(e.target.value)}
              maxLength={128}
              onKeyDown={e => { if (e.key === "Enter") submit(); }}
              autoFocus
            />
          </div>
        </div>
        {err && (
          <div style={{ padding: "8px 20px", fontSize: 11, color: "var(--red)", background: "rgba(239,68,68,.06)", borderTop: "1px solid rgba(239,68,68,.2)" }}>
            {err}
          </div>
        )}
        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose}>{t("common.cancel")}</button>
          <button className="btn btn-amber" onClick={submit} disabled={loading}>
            {loading ? <span className="loading-pulse">{t("watchlist.renaming")}</span> : t("watchlist.rename")}
          </button>
        </div>
      </div>
    </div>
  );
}

/* =========================================================================
   SORT HEADER — reusable sortable column header
========================================================================= */

/**
 * SortTh — renders a sortable table header cell.
 *
 * @param {object}   props
 * @param {string}   props.label   - display label
 * @param {string}   props.col     - column key for sorting
 * @param {string}   props.sortCol - currently active sort column
 * @param {string}   props.sortDir - current sort direction ("asc" | "desc")
 * @param {Function} props.onSort  - callback when header is clicked
 * @param {boolean}  [props.right] - whether to right-align the header
 */
function SortTh({ label, col, sortCol, sortDir, onSort, right }) {
  const active = sortCol === col;
  return (
    <th
      className={right ? "right" : ""}
      onClick={() => onSort(col)}
      style={{ cursor: "pointer", userSelect: "none", whiteSpace: "nowrap" }}
    >
      {label}
      {active
        ? <span style={{ marginLeft: 4, opacity: .8 }}>{sortDir === "asc" ? "\u25B2" : "\u25BC"}</span>
        : <span style={{ marginLeft: 4, opacity: .25 }}>{"\u21C5"}</span>}
    </th>
  );
}

/* =========================================================================
   MAIN PAGE
========================================================================= */

/**
 * WatchlistPage — the main watchlist page component.
 *
 * Features:
 *   - Watchlist tab bar with create/rename/delete controls
 *   - Asset section tabs (ALL / STOCKS / CRYPTO / ETFs / PHYSICAL)
 *   - Summary strip showing total value, day change, and item count
 *   - Live price table with sort, day range, and since-added performance
 *   - Action buttons: buy, chart, edit notes, remove
 *   - 30-second quote polling when market is open
 *
 * @param {object}   props
 * @param {string}   props.token       - JWT access token
 * @param {Function} props.onViewChart - callback to navigate to chart view
 * @param {Function} props.onViewNews  - callback to navigate to news view
 * @param {Function} props.onTradeAI   - callback to navigate to Trading AI with symbol pre-filled
 */
export function WatchlistPage({ token, onViewChart, onViewNews, onTradeAI }) {
  /* ── State ─────────────────────────────────────────────────────────────── */
  const { formatValue } = useCurrency();
  const { t } = useI18n();
  const mktStatus = useMarketStatus();

  /* ── Asset section configuration (i18n-aware) ───────────────────────── */
  const SECTIONS = useMemo(() => [
    { id: "all",      label: t("watchlist.all") },
    { id: "stock",    label: t("watchlist.stocks") },
    { id: "crypto",   label: t("watchlist.crypto") },
    { id: "etf",      label: t("watchlist.etfs") },
    { id: "physical", label: t("watchlist.physical") },
  ], [t]);

  const [watchlists,        setWatchlists]        = useState([]);
  const [activeWatchlistId, setActiveWatchlistId] = useState(null);
  const [items,             setItems]             = useState([]);
  const [quotes,            setQuotes]            = useState({});
  const [sortCol,           setSortCol]           = useState(null);
  const [sortDir,           setSortDir]           = useState("asc");
  const [loadingWatchlists, setLoadingWatchlists] = useState(false);
  const [loadingItems,      setLoadingItems]      = useState(false);
  const [globalErr,         setGlobalErr]         = useState("");
  const [activeSection,     setActiveSection]     = useState("all");

  // Modals
  const [showCreate,   setShowCreate]   = useState(false);
  const [showAddItem,  setShowAddItem]  = useState(false);
  const [editItem,     setEditItem]     = useState(null);   // item for EditNotesModal
  const [buyItem,      setBuyItem]      = useState(null);   // item for BuyFromWatchlistModal
  const [renameWl,     setRenameWl]     = useState(null);   // watchlist for RenameWatchlistModal
  const [detailSymbol, setDetailSymbol] = useState(null);   // symbol for AssetDetailPanel modal
  const [alertSymbol,  setAlertSymbol]  = useState(null);   // symbol for AlertModal
  const [alertPrice,   setAlertPrice]   = useState(null);   // current price for AlertModal

  /* ── Data loading ──────────────────────────────────────────────────────── */

  /**
   * loadWatchlists — fetches all watchlists for the user.
   * Auto-selects the first watchlist if none is active.
   */
  const loadWatchlists = useCallback(async () => {
    if (!token) return;
    setLoadingWatchlists(true); setGlobalErr("");
    try {
      // api.getWatchlists — GET /watchlists, returns array of watchlist objects
      const list = await api.getWatchlists(token);
      setWatchlists(list);
      if (list.length && !activeWatchlistId) setActiveWatchlistId(list[0].watchlist_id);
    } catch (e) { setGlobalErr(e.message || "Failed to load watchlists."); }
    finally { setLoadingWatchlists(false); }
  }, [token]); // eslint-disable-line

  /**
   * loadItems — fetches items for the given watchlist.
   * @param {string} watchlistId - ID of the watchlist to load items for
   */
  const loadItems = useCallback(async (watchlistId) => {
    if (!token || !watchlistId) { setItems([]); return; }
    setLoadingItems(true); setGlobalErr("");
    try {
      // api.getWatchlist — GET /watchlists/:id, returns watchlist with items array
      const wl = await api.getWatchlist(watchlistId, token);
      setItems(wl.items || []);
    } catch (e) { setGlobalErr(e.message || "Failed to load watchlist items."); }
    finally { setLoadingItems(false); }
  }, [token]);

  /**
   * loadQuotes — fetches bulk live quotes for the given items.
   * @param {Array} itemList - array of watchlist items with .symbol field
   */
  const loadQuotes = useCallback(async (itemList) => {
    if (!token || !itemList.length) { setQuotes({}); return; }
    // Deduplicate symbols before fetching
    const symbols = [...new Set(itemList.map(i => i.symbol))];
    try {
      // api.bulkQuotes — GET /market/bulk_quotes, returns array of quote objects
      const quoteList = await api.bulkQuotes(symbols, token);
      const map = {};
      quoteList.forEach(q => { map[q.symbol] = q; });
      setQuotes(map);
    } catch { /* non-fatal — table will show loading dots */ }
  }, [token]);

  /* ── Effects ───────────────────────────────────────────────────────────── */

  // Load watchlists on mount
  useEffect(() => { loadWatchlists(); }, [loadWatchlists]);

  // Load items when active watchlist changes
  useEffect(() => {
    setItems([]); setQuotes({});
    if (activeWatchlistId) loadItems(activeWatchlistId);
  }, [activeWatchlistId, loadItems]);

  // Load quotes when items change
  useEffect(() => {
    if (items.length) loadQuotes(items);
  }, [items]); // eslint-disable-line

  // Poll quotes periodically — 30s when market open, 5min when closed
  useEffect(() => {
    if (!items.length || !token) return;
    const intervalMs = mktStatus.isOpen ? POLL_OPEN_MS : POLL_CLOSED_MS;
    const interval = setInterval(() => loadQuotes(items), intervalMs);
    return () => clearInterval(interval);
  }, [items, token, mktStatus.isOpen, loadQuotes]);

  /* ── Derived data ──────────────────────────────────────────────────────── */

  /** The currently active watchlist object. */
  const activeWatchlist = useMemo(
    () => watchlists.find(w => w.watchlist_id === activeWatchlistId) || null,
    [watchlists, activeWatchlistId]
  );

  /** Items filtered by the active asset section tab. */
  const sectionItems = useMemo(
    () => activeSection === "all" ? items : items.filter(i => (i.asset_type || "stock") === activeSection),
    [items, activeSection]
  );

  /** Count of items per section for tab badges. */
  const sectionCounts = useMemo(() => {
    const counts = { all: items.length, stock: 0, crypto: 0, etf: 0, physical: 0 };
    items.forEach(i => {
      const aType = i.asset_type || "stock";
      counts[aType] = (counts[aType] || 0) + 1;
    });
    return counts;
  }, [items]);

  /** Sorted items based on current sort column and direction. */
  const sortedItems = useMemo(() => {
    if (!sortCol) return sectionItems;
    const mul = sortDir === "asc" ? 1 : -1;
    return [...sectionItems].sort((a, b) => {
      let av, bv;
      switch (sortCol) {
        case "symbol":
          av = a.symbol; bv = b.symbol;
          break;
        case "price":
          av = quotes[a.symbol]?.price || 0;
          bv = quotes[b.symbol]?.price || 0;
          break;
        case "change":
          // Sort by daily dollar change
          av = (quotes[a.symbol]?.price || 0) - (quotes[a.symbol]?.prev_close || 0);
          bv = (quotes[b.symbol]?.price || 0) - (quotes[b.symbol]?.prev_close || 0);
          break;
        case "sinceAdded": {
          // Sort by % change since added to watchlist
          const aq = quotes[a.symbol];
          const bq = quotes[b.symbol];
          av = aq?.price && a.price_when_added ? ((aq.price - a.price_when_added) / a.price_when_added) * 100 : -Infinity;
          bv = bq?.price && b.price_when_added ? ((bq.price - b.price_when_added) / b.price_when_added) * 100 : -Infinity;
          break;
        }
        default:
          av = 0; bv = 0;
      }
      if (typeof av === "string") return mul * av.localeCompare(bv);
      return mul * (av - bv);
    });
  }, [sectionItems, sortCol, sortDir, quotes]);

  /** Summary strip data — total value, day change, and item count. */
  const summary = useMemo(() => {
    let totalValue = 0;
    let dayChange = 0;
    let counted = 0;
    items.forEach(item => {
      const q = quotes[item.symbol];
      if (q?.price != null) {
        totalValue += q.price;
        counted++;
        // Day change = current price - previous close
        if (q.prev_close != null) {
          dayChange += q.price - q.prev_close;
        }
      }
    });
    return { totalValue, dayChange, count: items.length, quotedCount: counted };
  }, [items, quotes]);

  /* ── Sort handler ──────────────────────────────────────────────────────── */

  /**
   * handleSort — toggles sort direction if column is already active,
   * otherwise sets the new column to ascending.
   * @param {string} col - column key to sort by
   */
  const handleSort = (col) => {
    if (sortCol === col) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortCol(col); setSortDir("asc"); }
  };

  /* ── Action handlers ───────────────────────────────────────────────────── */

  /**
   * handleDeleteWatchlist — deletes a watchlist after user confirmation.
   * @param {string} wlId - watchlist ID to delete
   */
  const handleDeleteWatchlist = async (wlId) => {
    if (!window.confirm(t("watchlist.deleteConfirm"))) return;
    try {
      // api.deleteWatchlist — DELETE /watchlists/:id
      await api.deleteWatchlist(wlId, token);
      const next = watchlists.filter(w => w.watchlist_id !== wlId);
      setWatchlists(next);
      if (activeWatchlistId === wlId) setActiveWatchlistId(next[0]?.watchlist_id || null);
    } catch (e) { setGlobalErr(e.message || "Failed to delete watchlist."); }
  };

  /**
   * handleRemoveItem — removes an item from the watchlist after confirmation.
   * @param {object} item - the watchlist item to remove
   */
  const handleRemoveItem = async (item) => {
    if (!window.confirm(t("watchlist.removeConfirm").replace("{symbol}", item.symbol))) return;
    try {
      // api.removeWatchlistItem — DELETE /watchlists/:wlId/items/:itemId
      await api.removeWatchlistItem(activeWatchlistId, item.item_id, token);
      const next = items.filter(i => i.item_id !== item.item_id);
      setItems(next);
    } catch (e) { setGlobalErr(e.message || "Failed to remove item."); }
  };

  /**
   * handleWatchlistCreated — adds the new watchlist to state and selects it.
   * @param {object} wl - the newly created watchlist
   */
  const handleWatchlistCreated = (wl) => {
    const next = [...watchlists, wl];
    setWatchlists(next);
    setActiveWatchlistId(wl.watchlist_id);
    setShowCreate(false);
  };

  /**
   * handleWatchlistRenamed — updates the watchlist name in local state.
   * @param {object} updated - the updated watchlist object
   */
  const handleWatchlistRenamed = (updated) => {
    setWatchlists(prev => prev.map(w => w.watchlist_id === updated.watchlist_id ? updated : w));
    setRenameWl(null);
  };

  /**
   * handleItemAdded — adds a new item to the list and refreshes quotes.
   * @param {object} item - the newly created watchlist item
   */
  const handleItemAdded = (item) => {
    const next = [...items, item];
    setItems(next);
    setShowAddItem(false);
    loadQuotes(next);
  };

  /**
   * handleItemUpdated — updates an edited item in the local items array.
   * @param {object} updated - the updated watchlist item
   */
  const handleItemUpdated = (updated) => {
    setItems(prev => prev.map(i => i.item_id === updated.item_id ? updated : i));
    setEditItem(null);
  };

  /**
   * handleBought — closes the buy modal after a successful purchase.
   */
  const handleBought = () => {
    setBuyItem(null);
  };

  /* ── Render ────────────────────────────────────────────────────────────── */
  return (
    <div className="page-scroll">
      {/* Page header */}
      <div className="page-header">
        <div>
          <div className="page-title">{t("watchlist.title")}</div>
          <div className="page-sub">
            {watchlists.length} {watchlists.length !== 1 ? t("watchlist.title") + "S" : t("watchlist.title")}
            {activeWatchlist && ` \u00B7 ${items.length} ${items.length !== 1 ? t("watchlist.items") + "S" : t("watchlist.items")}`}
          </div>
        </div>
        <div className="page-actions">
          <button className="btn btn-outline" onClick={() => setShowCreate(true)}>
            <Ic.plus /> {t("watchlist.newWatchlist")}
          </button>
        </div>
      </div>

      {/* Global error */}
      {globalErr && (
        <div style={{
          margin: "0 0 12px", padding: "8px 16px",
          background: "rgba(239,68,68,.08)", border: "1px solid rgba(239,68,68,.25)",
          borderRadius: 4, fontSize: 12, fontFamily: "var(--font-mono)", color: "var(--red)",
        }}>
          {globalErr}
        </div>
      )}

      {/* Empty state — no watchlists */}
      {watchlists.length === 0 && !loadingWatchlists && (
        <div style={{
          textAlign: "center", padding: "60px 20px",
          color: "var(--c-muted)", fontFamily: "var(--font-mono)", fontSize: 13,
        }}>
          {t("watchlist.noWatchlists")} <strong>{t("watchlist.newWatchlist")}</strong> {t("watchlist.createFirst")}
        </div>
      )}

      {watchlists.length > 0 && (
        <>
          {/* Watchlist tab bar */}
          <div style={{ display: "flex", gap: 4, marginBottom: 16, flexWrap: "wrap", alignItems: "center" }}>
            {watchlists.map(w => (
              <button
                key={w.watchlist_id}
                onClick={() => setActiveWatchlistId(w.watchlist_id)}
                onDoubleClick={() => setRenameWl(w)}
                style={{
                  display: "flex", alignItems: "center", gap: 6,
                  padding: "6px 14px", borderRadius: 3, fontSize: 11,
                  fontFamily: "var(--font-mono)", letterSpacing: ".06em", fontWeight: 600,
                  cursor: "pointer", border: "1px solid",
                  borderColor: w.watchlist_id === activeWatchlistId ? "var(--c-accent)" : "var(--c-border)",
                  background: w.watchlist_id === activeWatchlistId ? "rgba(59,130,246,.12)" : "var(--c-surface)",
                  color: w.watchlist_id === activeWatchlistId ? "var(--c-accent)" : "var(--c-muted)",
                  transition: "all .15s",
                }}
              >
                {w.name}
                {/* Rename icon — small edit button on tab */}
                <span
                  onClick={e => { e.stopPropagation(); setRenameWl(w); }}
                  title={t("watchlist.rename")}
                  style={{ opacity: .4, cursor: "pointer", lineHeight: 1, fontSize: 10 }}
                >
                  <Ic.edit />
                </span>
                {/* Delete icon — small x button on tab */}
                <span
                  onClick={e => { e.stopPropagation(); handleDeleteWatchlist(w.watchlist_id); }}
                  title={t("watchlist.delete")}
                  style={{ opacity: .5, marginLeft: 0, lineHeight: 1, cursor: "pointer" }}
                >{"\u00D7"}</span>
              </button>
            ))}
          </div>

          {/* Summary strip */}
          <div className="grid-stats stagger" style={{ marginBottom: 16 }}>
            {[
              { lbl: t("watchlist.totalValue"),  val: formatValue(summary.totalValue),  cls: "" },
              {
                lbl: t("watchlist.dayChangeLabel"),
                val: formatValue(summary.dayChange, { showSign: true }),
                cls: summary.dayChange >= 0 ? "green" : "red",
              },
              { lbl: t("watchlist.items"),        val: summary.count,                    cls: "" },
            ].map((s, i) => (
              <div key={i} className="stat-block">
                <div className="stat-lbl">{s.lbl}</div>
                <div className={`stat-val${s.cls ? " " + s.cls : ""}`}>{s.val}</div>
              </div>
            ))}
          </div>

          {/* Asset section tabs: ALL | STOCKS | CRYPTO | ETFs | PHYSICAL */}
          <div style={{
            display: "flex", gap: 2, marginBottom: 16,
            borderBottom: "1px solid var(--c-border)", paddingBottom: 0,
          }}>
            {SECTIONS.map(s => (
              <button
                key={s.id}
                onClick={() => { setActiveSection(s.id); setSortCol(null); }}
                style={{
                  padding: "8px 16px", fontSize: 11,
                  fontFamily: "var(--font-mono)", letterSpacing: ".06em", fontWeight: 600,
                  cursor: "pointer", border: "none", borderBottom: "2px solid",
                  borderBottomColor: activeSection === s.id ? "var(--c-accent)" : "transparent",
                  background: "transparent",
                  color: activeSection === s.id ? "var(--c-accent)" : "var(--c-muted)",
                  transition: "all .15s",
                  marginBottom: -1,
                }}
              >
                {s.label}
                {sectionCounts[s.id] > 0 && (
                  <span style={{ marginLeft: 6, fontSize: 10, opacity: .7 }}>({sectionCounts[s.id]})</span>
                )}
              </button>
            ))}
          </div>

          {/* Section action bar — add item button (always visible) */}
          <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
            <button className="btn btn-amber" onClick={() => setShowAddItem(true)}>
              <Ic.plus /> {t("watchlist.addItem")}
            </button>
          </div>

          {/* Watchlist items table */}
          <div className="panel page-inner stagger">
            <div className="panel-header">
              <span className="panel-title">
                {SECTIONS.find(s => s.id === activeSection)?.label || t("watchlist.items")}
              </span>
              {loadingItems && (
                <span style={{ fontSize: 11, color: "var(--c-muted)", marginLeft: 10 }} className="loading-pulse">
                  {t("common.loading")}
                </span>
              )}
            </div>
            <div style={{ overflowX: "auto" }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <SortTh label={t("watchlist.symbol")}     col="symbol"     sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                    <th>{t("watchlist.name")}</th>
                    <SortTh label={t("watchlist.price")}      col="price"      sortCol={sortCol} sortDir={sortDir} onSort={handleSort} right />
                    <SortTh label={t("watchlist.change")}     col="change"     sortCol={sortCol} sortDir={sortDir} onSort={handleSort} right />
                    <th className="right">{t("watchlist.dayRange")}</th>
                    <SortTh label={t("watchlist.sinceAdded")} col="sinceAdded" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} right />
                    <th>{t("watchlist.notes")}</th>
                    <th>{t("watchlist.actions")}</th>
                  </tr>
                </thead>
                <tbody>
                  {/* Empty state row */}
                  {sortedItems.length === 0 && !loadingItems && (
                    <tr>
                      <td
                        colSpan={99}
                        style={{
                          textAlign: "center", padding: "32px 0",
                          color: "var(--c-muted)", fontFamily: "var(--font-mono)", fontSize: 12,
                        }}
                      >
                        {activeSection === "all"
                          ? t("watchlist.noItemsYet")
                          : `${t("watchlist.noItemsInCategory").replace("{category}", SECTIONS.find(s => s.id === activeSection)?.label.toLowerCase() || "")} ${t("watchlist.addItem")}`}
                      </td>
                    </tr>
                  )}

                  {/* Data rows */}
                  {sortedItems.map(item => {
                    const q     = quotes[item.symbol];
                    const price = q?.price;
                    const prevClose = q?.prev_close;

                    // Daily change: dollar and percent
                    const dayChg    = price != null && prevClose != null ? price - prevClose : null;
                    const dayChgPct = dayChg != null && prevClose > 0 ? (dayChg / prevClose) * 100 : null;

                    // Day range from quote data
                    const dayLow  = q?.low;
                    const dayHigh = q?.high;

                    // Since added: dollar change and % change from price_when_added
                    const sinceAdded = price != null && item.price_when_added
                      ? ((price - item.price_when_added) / item.price_when_added) * 100
                      : null;
                    const sinceAddedDollar = price != null && item.price_when_added
                      ? price - item.price_when_added
                      : null;

                    return (
                      <tr key={item.item_id}>
                        {/* SYMBOL */}
                        <td>
                          <span className="amber" style={{ fontWeight: 700 }}>{item.symbol}</span>
                        </td>

                        {/* NAME — from quotes */}
                        <td style={{ maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {q?.name || <span style={{ color: "var(--c-muted)" }}>{"\u2014"}</span>}
                        </td>

                        {/* PRICE — live price */}
                        <td className="right" style={{ fontVariantNumeric: "tabular-nums" }}>
                          {price != null
                            ? formatValue(price)
                            : <span className="loading-pulse" style={{ color: "var(--c-muted)", fontSize: 11 }}>...</span>}
                        </td>

                        {/* CHG — daily $ change + % */}
                        <td className="right" style={{ fontVariantNumeric: "tabular-nums" }}>
                          {dayChg != null
                            ? (
                              <span className={dayChg >= 0 ? "green" : "red"}>
                                {formatValue(dayChg, { showSign: true })}
                                <span style={{ marginLeft: 4, fontSize: 10, opacity: .75 }}>
                                  ({fmtPct(dayChgPct)})
                                </span>
                              </span>
                            )
                            : <span style={{ color: "var(--c-muted)", fontSize: 11 }}>...</span>}
                        </td>

                        {/* DAY RANGE — low-high */}
                        <td className="right" style={{ fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap", fontSize: 11 }}>
                          {dayLow != null && dayHigh != null
                            ? <span style={{ color: "var(--c-muted)" }}>{formatValue(dayLow)} {"\u2013"} {formatValue(dayHigh)}</span>
                            : <span style={{ color: "var(--c-muted)" }}>{"\u2014"}</span>}
                        </td>

                        {/* SINCE ADDED — dollar change with % in brackets */}
                        <td className="right" style={{ fontVariantNumeric: "tabular-nums" }}>
                          {sinceAdded != null
                            ? <span className={sinceAdded >= 0 ? "green" : "red"}>
                                {formatValue(sinceAddedDollar, { showSign: true })} ({fmtPct(sinceAdded)})
                              </span>
                            : <span style={{ color: "var(--c-muted)" }}>{"\u2014"}</span>}
                        </td>

                        {/* NOTES — truncated */}
                        <td style={{
                          maxWidth: 140, overflow: "hidden",
                          textOverflow: "ellipsis", whiteSpace: "nowrap",
                          fontSize: 11, color: "var(--c-muted)",
                        }}>
                          {item.notes || "\u2014"}
                        </td>

                        {/* ACTIONS — info, buy, chart, edit, remove */}
                        <td>
                          <div style={{ display: "flex", gap: 6 }}>
                            {/* Asset detail info button */}
                            <button
                              className="btn btn-ghost"
                              title="Asset details"
                              onClick={() => setDetailSymbol(item.symbol)}
                              style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontSize: 15, padding: "3px 7px" }}
                            >
                              {"\u24D8"}
                            </button>
                            {/* Price alert button */}
                            <button
                              className="btn btn-ghost"
                              title="Set price alert"
                              onClick={() => { setAlertSymbol(item.symbol); setAlertPrice(quotes[item.symbol]?.price ?? null); }}
                              style={{ padding: "3px 7px", color: "#f59e0b" }}
                            >
                              <Ic.bell />
                            </button>
                            {/* Buy button */}
                            <button
                              className="btn btn-ghost"
                              title={t("watchlist.buy")}
                              onClick={() => setBuyItem(item)}
                              style={{ padding: "3px 7px", color: "var(--green)" }}
                            >
                              <Ic.buy />
                            </button>
                            {/* Chart button */}
                            {onViewChart && (
                              <button
                                className="btn btn-ghost"
                                title={t("dashboard.viewChart")}
                                onClick={() => onViewChart(item.symbol)}
                                style={{ padding: "3px 7px" }}
                              >
                                <Ic.charts />
                              </button>
                            )}
                            {/* Trade AI button */}
                            {onTradeAI && (
                              <button
                                className="btn btn-ghost"
                                title="Trade AI"
                                onClick={() => onTradeAI(item.symbol)}
                                style={{ padding: "3px 7px", color: "var(--amber)" }}
                              >
                                <Ic.trading />
                              </button>
                            )}
                            {/* Edit notes button */}
                            <button
                              className="btn btn-ghost"
                              title={t("watchlist.editNotes")}
                              onClick={() => setEditItem(item)}
                              style={{ padding: "3px 7px" }}
                            >
                              <Ic.edit />
                            </button>
                            {/* Remove button */}
                            <button
                              className="btn btn-ghost"
                              title={t("watchlist.remove")}
                              onClick={() => handleRemoveItem(item)}
                              style={{ padding: "3px 7px", color: "var(--red)" }}
                            >
                              <Ic.trash />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* ── Modals ───────────────────────────────────────────────────────── */}

      {showCreate && (
        <CreateWatchlistModal
          onClose={() => setShowCreate(false)}
          onCreated={handleWatchlistCreated}
          token={token}
        />
      )}

      {showAddItem && activeWatchlistId && (
        <AddItemModal
          watchlistId={activeWatchlistId}
          assetType={activeSection === "all" ? null : activeSection}
          onClose={() => setShowAddItem(false)}
          onAdded={handleItemAdded}
          token={token}
        />
      )}

      {editItem && activeWatchlistId && (
        <EditNotesModal
          item={editItem}
          watchlistId={activeWatchlistId}
          onClose={() => setEditItem(null)}
          onUpdated={handleItemUpdated}
          token={token}
        />
      )}

      {buyItem && activeWatchlistId && (
        <BuyFromWatchlistModal
          item={buyItem}
          watchlistId={activeWatchlistId}
          livePrice={quotes[buyItem.symbol]?.price ?? null}
          onClose={() => setBuyItem(null)}
          onBought={handleBought}
          token={token}
        />
      )}

      {renameWl && (
        <RenameWatchlistModal
          watchlist={renameWl}
          onClose={() => setRenameWl(null)}
          onRenamed={handleWatchlistRenamed}
          token={token}
        />
      )}
      {detailSymbol && (
        <AssetDetailPanel symbol={detailSymbol} token={token} onClose={() => setDetailSymbol(null)} />
      )}
      {alertSymbol && (
        <AlertModal
          symbol={alertSymbol}
          currentPrice={alertPrice}
          token={token}
          onClose={() => { setAlertSymbol(null); setAlertPrice(null); }}
          onCreated={() => {}}
        />
      )}
    </div>
  );
}
