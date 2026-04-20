/**
 * AlertModal.jsx
 *
 * Reusable modal for creating a new price alert. Triggered from Charts,
 * Watchlist, and Portfolio pages when the user clicks the alert/bell button.
 * Pre-fills the symbol and derives a default target price from the current
 * price (+5% for "above", -5% for "below", exact for "crosses").
 *
 * Uses the standard TickerTap modal structure:
 *   .modal-overlay > .modal-box > .modal-top + .modal-body + .modal-footer
 */

import { useState, useEffect, useCallback } from "react";
import api from "../../api/client";
import { Ic } from "./Icons";
import { MODAL_BACKDROP as BDK } from "../../styles/shared";

/* ── Condition options for the dropdown ─────────────────────────────────── */
const CONDITIONS = [
  { value: "above",   label: "Above" },
  { value: "below",   label: "Below" },
  { value: "crosses", label: "Crosses" },
];

/**
 * deriveDefaultTarget — compute a sensible default target price based on
 * the selected condition and current market price.
 *
 * @param {string}      condition    - "above" | "below" | "crosses"
 * @param {number|null} currentPrice - latest quote price (may be null)
 * @returns {string} Default target price as a string for the input field
 */
function deriveDefaultTarget(condition, currentPrice) {
  if (currentPrice == null) return "";
  if (condition === "above")  return (currentPrice * 1.05).toFixed(2);
  if (condition === "below")  return (currentPrice * 0.95).toFixed(2);
  return currentPrice.toFixed(2); // "crosses" defaults to exact current price
}

/**
 * AlertModal — modal dialog for creating a new price alert.
 *
 * @param {object}        props
 * @param {string}        props.symbol       - Pre-filled ticker symbol
 * @param {number|null}   props.currentPrice - Current market price (reference)
 * @param {string}        props.token        - JWT access token
 * @param {Function}      props.onClose      - Close handler
 * @param {Function}      props.onCreated    - Callback after successful creation
 */
export default function AlertModal({ symbol: initialSymbol, currentPrice, token, onClose, onCreated }) {
  const [symbolInput, setSymbolInput] = useState(initialSymbol || "");
  const [searchResults, setSearchResults] = useState([]);
  const [showSearch, setShowSearch] = useState(false);
  const [condition,   setCondition]   = useState("above");
  const [targetPrice, setTargetPrice] = useState(() => deriveDefaultTarget("above", currentPrice));
  const [note,        setNote]        = useState("");
  const [loading,     setLoading]     = useState(false);
  const [error,       setError]       = useState("");
  const [success,     setSuccess]     = useState(false);

  /* Debounced symbol search — fires 300ms after user stops typing */
  useEffect(() => {
    if (!symbolInput || symbolInput.length < 1 || initialSymbol) { setSearchResults([]); return; }
    const timer = setTimeout(async () => {
      try {
        const results = await api.searchSymbols(symbolInput, token);
        setSearchResults((results || []).slice(0, 6));
        setShowSearch(true);
      } catch { setSearchResults([]); }
    }, 300);
    return () => clearTimeout(timer);
  }, [symbolInput, token, initialSymbol]);

  /* Re-derive target when condition or currentPrice change */
  useEffect(() => {
    setTargetPrice(deriveDefaultTarget(condition, currentPrice));
  }, [condition, currentPrice]);

  /* Close on Escape key */
  const handleKeyDown = useCallback((e) => {
    if (e.key === "Escape") onClose();
  }, [onClose]);

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  /**
   * handleSubmit — validate inputs and call the createAlert API.
   * On success, briefly show a success state then invoke callbacks.
   */
  const handleSubmit = async () => {
    /* Validation */
    const price = parseFloat(targetPrice);
    if (!symbolInput) { setError("Symbol is required."); return; }
    if (isNaN(price) || price <= 0) { setError("Enter a valid target price."); return; }

    setLoading(true);
    setError("");
    try {
      // api.createAlert — POST /alerts, returns the created alert object
      await api.createAlert(
        { symbol: symbolInput.toUpperCase(), condition, target_price: price, note: note.trim() || null },
        token,
      );
      setSuccess(true);
      // Brief success flash (600ms), then close
      setTimeout(() => {
        if (onCreated) onCreated();
        onClose();
      }, 600);
    } catch (e) {
      setError(e.message || "Failed to create alert.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="modal-overlay"
      style={BDK}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="modal-box" style={{ maxWidth: 420 }}>
        {/* ── Header ──────────────────────────────────────────────── */}
        <div className="modal-top">
          <div className="modal-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Ic.bell />
            CREATE PRICE ALERT
          </div>
          <button className="modal-close" onClick={onClose}><Ic.close /></button>
        </div>

        {/* ── Body ────────────────────────────────────────────────── */}
        <div className="modal-body">
          {/* Symbol input — editable when no initial symbol; pre-filled otherwise */}
          <div className="form-field" style={{ position: "relative" }}>
            <label className="form-label">Symbol</label>
            <input
              className="form-control"
              type="text"
              placeholder="e.g. AAPL"
              value={symbolInput}
              onChange={(e) => { setSymbolInput(e.target.value.toUpperCase()); setError(""); }}
              onFocus={() => { if (searchResults.length) setShowSearch(true); }}
              onBlur={() => setTimeout(() => setShowSearch(false), 200)}
              style={{
                width: "100%", fontWeight: 700, color: "#f59e0b",
                letterSpacing: "0.5px",
              }}
              autoFocus={!initialSymbol}
            />
            {/* Search results dropdown */}
            {showSearch && searchResults.length > 0 && (
              <div style={{
                position: "absolute", top: "100%", left: 0, right: 0, zIndex: 10,
                background: "var(--bg2)", border: "1px solid var(--border2)",
                borderRadius: 4, maxHeight: 180, overflowY: "auto", marginTop: 2,
              }}>
                {searchResults.map((r) => (
                  <div
                    key={r.symbol}
                    style={{
                      padding: "8px 12px", cursor: "pointer", fontSize: 12,
                      fontFamily: "var(--font-mono)", display: "flex", justifyContent: "space-between",
                      borderBottom: "1px solid var(--border)",
                    }}
                    onMouseDown={() => {
                      setSymbolInput(r.symbol);
                      setSearchResults([]);
                      setShowSearch(false);
                    }}
                  >
                    <span style={{ color: "#f59e0b", fontWeight: 600 }}>{r.symbol}</span>
                    <span style={{ color: "var(--muted)", fontSize: 10, maxWidth: "60%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {r.name || r.shortname || ""}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Current price reference */}
          {currentPrice != null && (
            <div className="form-field" style={{ marginTop: 8 }}>
              <label className="form-label">Current Price</label>
              <div style={{
                fontFamily: "var(--font-mono)", fontSize: 13, color: "var(--c-text)",
              }}>
                ${currentPrice.toFixed(2)}
              </div>
            </div>
          )}

          {/* Condition dropdown */}
          <div className="form-field" style={{ marginTop: 14 }}>
            <label className="form-label">Condition</label>
            <select
              className="form-control"
              value={condition}
              onChange={(e) => setCondition(e.target.value)}
              style={{
                background: "var(--c-surface)", border: "1px solid var(--c-border)",
                color: "var(--c-text)", fontFamily: "var(--font-mono)", fontSize: 12,
                borderRadius: 4, padding: "8px 10px", cursor: "pointer", width: "100%",
              }}
            >
              {CONDITIONS.map((c) => (
                <option key={c.value} value={c.value}>{c.label}</option>
              ))}
            </select>
          </div>

          {/* Target price */}
          <div className="form-field" style={{ marginTop: 14 }}>
            <label className="form-label">Target Price</label>
            <input
              className="form-control"
              type="number"
              min="0"
              step="any"
              placeholder="e.g. 180.00"
              value={targetPrice}
              onChange={(e) => setTargetPrice(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleSubmit(); }}
              style={{ width: "100%" }}
            />
          </div>

          {/* Note (optional) */}
          <div className="form-field" style={{ marginTop: 14 }}>
            <label className="form-label">Note (optional)</label>
            <input
              className="form-control"
              type="text"
              placeholder="e.g. Earnings play"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={256}
              onKeyDown={(e) => { if (e.key === "Enter") handleSubmit(); }}
              style={{ width: "100%" }}
            />
          </div>
        </div>

        {/* ── Error banner ────────────────────────────────────────── */}
        {error && (
          <div style={{
            padding: "8px 20px", fontSize: 11, color: "var(--red)",
            background: "rgba(239,68,68,.06)",
            borderTop: "1px solid rgba(239,68,68,.2)",
          }}>
            {error}
          </div>
        )}

        {/* ── Success banner ──────────────────────────────────────── */}
        {success && (
          <div style={{
            padding: "8px 20px", fontSize: 11, color: "var(--green)",
            background: "rgba(34,197,94,.06)",
            borderTop: "1px solid rgba(34,197,94,.2)",
          }}>
            Alert created successfully!
          </div>
        )}

        {/* ── Footer ──────────────────────────────────────────────── */}
        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose}>CANCEL</button>
          <button
            className="btn btn-amber"
            onClick={handleSubmit}
            disabled={loading || success}
          >
            {loading
              ? <span className="loading-pulse">CREATING...</span>
              : success
                ? "CREATED"
                : "CREATE"}
          </button>
        </div>
      </div>
    </div>
  );
}
