/**
 * AlertsPage.jsx
 *
 * Full-page management view for price alerts. Users can:
 *   - View all alerts with filter tabs (Active / Triggered / All)
 *   - Create new alerts via the AlertModal
 *   - Edit alerts inline (condition, target price, note)
 *   - Toggle active/inactive status via PATCH
 *   - Delete alerts with confirmation
 *   - Re-arm triggered alerts to watch again via PATCH
 *
 * Data flow:
 *   1. Fetch all alerts on mount via api.listAlerts(false, token)
 *   2. Enrich with live prices via api.bulkQuotes (best-effort, non-fatal)
 *   3. Client-side filter by tab (active, triggered, all)
 *   4. Mutations refresh the full list and price map
 *
 * Currency:
 *   All price displays use the user's preferred currency symbol via useCurrency().
 */

import { useState, useEffect, useCallback } from "react";
import api from "../api/client";
import { Ic } from "../components/common/Icons";
import AlertModal from "../components/common/AlertModal";
import { useCurrency } from "../context/CurrencyContext";

/* ── Filter tab definitions ──────────────────────────────────────────────── */
const TABS = [
  { id: "active",    label: "ACTIVE" },
  { id: "triggered", label: "TRIGGERED" },
  { id: "all",       label: "ALL" },
];

/* ── Condition badge colour map ──────────────────────────────────────────── */
const BADGE_COLORS = {
  above:   { bg: "rgba(245,158,11,.15)", color: "#f59e0b" },
  below:   { bg: "rgba(239,68,68,.15)",  color: "#ef4444" },
  crosses: { bg: "rgba(59,130,246,.15)", color: "#3b82f6" },
};

/**
 * fmtDate — format an ISO timestamp to a short human-readable date.
 *
 * @param {string|null} iso - ISO 8601 timestamp
 * @returns {string} Formatted date or em-dash
 */
function fmtDate(iso) {
  if (!iso) return "\u2014";
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

/**
 * AlertsPage — renders the full alerts management page.
 *
 * @param {object} props
 * @param {string} props.token - JWT access token
 */
export default function AlertsPage({ token }) {
  const [alerts,     setAlerts]     = useState([]);
  const [loading,    setLoading]    = useState(true);
  const [error,      setError]      = useState("");
  const [activeTab,  setActiveTab]  = useState("active");
  const [showCreate, setShowCreate] = useState(false);

  /* Live price map populated after alerts load — { SYMBOL: price } */
  const [priceMap, setPriceMap] = useState({});

  /* Inline edit state — only one alert can be edited at a time */
  const [editingId,        setEditingId]        = useState(null);
  const [editCondition,    setEditCondition]    = useState("above");
  const [editTargetPrice,  setEditTargetPrice]  = useState("");
  const [editNote,         setEditNote]         = useState("");
  const [editLoading,      setEditLoading]      = useState(false);
  const [editError,        setEditError]        = useState("");

  /* Delete confirmation state */
  const [deletingId, setDeletingId] = useState(null);

  /* ── Fetch all alerts ───────────────────────────────────────────────── */

  /**
   * fetchAlerts — load all user alerts from the API, then enrich with live
   * prices via bulkQuotes.  Price enrichment is best-effort: a failure will
   * not surface an error to the user.
   * Always fetches all (active_only=false) so we can client-side filter.
   */
  const fetchAlerts = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      // api.listAlerts(false, token) — GET /alerts?active_only=false, returns all alerts
      const data = await api.listAlerts(false, token);
      const alertList = Array.isArray(data) ? data : [];
      setAlerts(alertList);

      // Collect unique symbols from the loaded alerts
      const symbols = [...new Set(alertList.map(a => a.symbol).filter(Boolean))];
      if (symbols.length > 0) {
        try {
          // api.bulkQuotes — GET /market/bulk_quotes, returns [{ symbol, price, ... }]
          const quoteList = await api.bulkQuotes(symbols, token);
          const map = {};
          quoteList.forEach(q => { map[q.symbol] = q.price; });
          setPriceMap(map);
        } catch {
          /* Non-fatal: price enrichment is best-effort; cards still render */
        }
      }
    } catch (e) {
      setError(e.message || "Failed to load alerts.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { fetchAlerts(); }, [fetchAlerts]);

  /* ── Client-side filtering by tab ───────────────────────────────────── */

  /**
   * filteredAlerts — apply the active tab filter.
   *   - "active":    is_active === true AND triggered_at is null
   *   - "triggered": triggered_at is not null
   *   - "all":       no filter
   */
  const filteredAlerts = alerts.filter((a) => {
    if (activeTab === "active")    return a.is_active && !a.triggered_at;
    if (activeTab === "triggered") return !!a.triggered_at;
    return true; // "all"
  });

  /* ── Toggle active/inactive ─────────────────────────────────────────── */

  /**
   * handleToggleActive — flip is_active via PATCH, then refresh.
   * @param {object} alert - alert object with alert_id and is_active
   */
  const handleToggleActive = async (alert) => {
    try {
      // api.updateAlert — PATCH /alerts/:id, toggles the is_active flag
      await api.updateAlert(alert.alert_id, { is_active: !alert.is_active }, token);
      fetchAlerts();
    } catch (e) {
      setError(e.message || "Failed to update alert.");
    }
  };

  /* ── Delete alert ───────────────────────────────────────────────────── */

  /**
   * handleDelete — permanently delete an alert after confirmation.
   * @param {string} alertId - UUID of the alert to delete
   */
  const handleDelete = async (alertId) => {
    try {
      // api.deleteAlert — DELETE /alerts/:id, removes the alert
      await api.deleteAlert(alertId, token);
      setDeletingId(null);
      fetchAlerts();
    } catch (e) {
      setError(e.message || "Failed to delete alert.");
    }
  };

  /* ── Re-arm triggered alert ─────────────────────────────────────────── */

  /**
   * handleRearm — re-activate a triggered alert by clearing triggered_at
   * and setting is_active to true via PATCH, then refresh the list.
   * @param {object} alert - alert object with alert_id
   */
  const handleRearm = async (alert) => {
    try {
      // api.updateAlert — PATCH /alerts/:id, clears triggered_at and reactivates
      await api.updateAlert(alert.alert_id, { is_active: true, triggered_at: null }, token);
      fetchAlerts();
    } catch (e) {
      console.error(e);
    }
  };

  /* ── Inline edit: start ─────────────────────────────────────────────── */

  /**
   * startEdit — populate inline edit fields from the selected alert.
   * @param {object} alert - alert object
   */
  const startEdit = (alert) => {
    setEditingId(alert.alert_id);
    setEditCondition(alert.condition);
    setEditTargetPrice(String(alert.target_price));
    setEditNote(alert.note || "");
    setEditError("");
  };

  /**
   * cancelEdit — discard inline edit state.
   */
  const cancelEdit = () => {
    setEditingId(null);
    setEditError("");
  };

  /* ── Inline edit: save ──────────────────────────────────────────────── */

  /**
   * saveEdit — validate and PATCH the edited alert fields.
   */
  const saveEdit = async () => {
    const price = parseFloat(editTargetPrice);
    if (isNaN(price) || price <= 0) { setEditError("Enter a valid target price."); return; }

    setEditLoading(true);
    setEditError("");
    try {
      // api.updateAlert — PATCH /alerts/:id, updates condition/target_price/note
      await api.updateAlert(editingId, {
        condition: editCondition,
        target_price: price,
        note: editNote.trim() || null,
      }, token);
      setEditingId(null);
      fetchAlerts();
    } catch (e) {
      setEditError(e.message || "Failed to save.");
    } finally {
      setEditLoading(false);
    }
  };

  /* ── Determine left-border colour for an alert card ─────────────────── */

  /**
   * getCardBorderColor — returns the left-border colour based on alert status.
   * @param {object} alert - alert object
   * @returns {string} CSS colour value
   */
  const getCardBorderColor = (alert) => {
    if (alert.triggered_at) return "#22c55e"; // green — triggered
    if (alert.is_active) return "#f59e0b";    // amber — active
    return "#6b7280";                          // muted — inactive/expired
  };

  /* ── Currency symbol for price display ──────────────────────────────── */
  // useCurrency — provides currencySymbol (e.g. "$", "€") for the user's
  // preferred display currency.
  const { currencySymbol } = useCurrency();

  /* ── Render ─────────────────────────────────────────────────────────── */
  return (
    <div style={{ flex: 1, overflow: "auto", padding: "24px 32px" }}>
      <style>{ALERTS_CSS}</style>

      {/* ── Page header ─────────────────────────────────────────────── */}
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        marginBottom: 24,
      }}>
        <div>
          <div style={{
            fontFamily: "'Bebas Neue', sans-serif", fontSize: 28,
            color: "#e8f0fa", letterSpacing: 1, lineHeight: 1,
            display: "flex", alignItems: "center", gap: 10,
          }}>
            <Ic.bell /> PRICE ALERTS
          </div>
          <div style={{
            fontFamily: "var(--font-mono)", fontSize: 11, color: "#4a5568",
            marginTop: 4,
          }}>
            Manage your price alerts and notifications
          </div>
        </div>
        <button
          className="btn btn-amber"
          onClick={() => setShowCreate(true)}
          style={{ display: "flex", alignItems: "center", gap: 6 }}
        >
          <Ic.plus /> NEW ALERT
        </button>
      </div>

      {/* ── Filter tabs ─────────────────────────────────────────────── */}
      <div style={{
        display: "flex", gap: 0, marginBottom: 20,
        borderBottom: "1px solid rgba(255,255,255,0.06)",
      }}>
        {TABS.map((tab) => (
          <button
            key={tab.id}
            className={`alerts-tab${activeTab === tab.id ? " alerts-tab-active" : ""}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
            {/* Badge showing count */}
            <span className="alerts-tab-count">
              {alerts.filter((a) => {
                if (tab.id === "active")    return a.is_active && !a.triggered_at;
                if (tab.id === "triggered") return !!a.triggered_at;
                return true;
              }).length}
            </span>
          </button>
        ))}
      </div>

      {/* ── Error banner ────────────────────────────────────────────── */}
      {error && (
        <div style={{
          padding: "10px 16px", fontSize: 11, color: "var(--red)",
          background: "rgba(239,68,68,.06)", borderRadius: 6,
          border: "1px solid rgba(239,68,68,.2)", marginBottom: 16,
        }}>
          {error}
        </div>
      )}

      {/* ── Loading state ───────────────────────────────────────────── */}
      {loading && (
        <div style={{
          textAlign: "center", padding: "48px 0", color: "var(--c-muted)",
          fontFamily: "var(--font-mono)", fontSize: 12,
        }}>
          <span className="loading-pulse">Loading alerts...</span>
        </div>
      )}

      {/* ── Empty state ─────────────────────────────────────────────── */}
      {!loading && filteredAlerts.length === 0 && (
        <div style={{
          textAlign: "center", padding: "48px 0", color: "var(--c-muted)",
          fontFamily: "var(--font-mono)", fontSize: 12,
        }}>
          <div style={{ fontSize: 32, marginBottom: 12, opacity: 0.3 }}>
            <Ic.bell />
          </div>
          {activeTab === "active"
            ? "No active alerts. Create one to get started."
            : activeTab === "triggered"
              ? "No triggered alerts yet."
              : "No alerts found. Click NEW ALERT to create one."}
        </div>
      )}

      {/* ── Alert cards ─────────────────────────────────────────────── */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {filteredAlerts.map((alert) => {
          const isEditing = editingId === alert.alert_id;
          const isDeleting = deletingId === alert.alert_id;
          const badge = BADGE_COLORS[alert.condition] || BADGE_COLORS.above;

          /* Live price enrichment — resolved from priceMap after bulk fetch */
          const currentPrice = priceMap[alert.symbol] != null
            ? parseFloat(priceMap[alert.symbol])
            : null;
          const distToTarget = currentPrice != null
            ? parseFloat(alert.target_price) - currentPrice
            : null;
          /*
           * distColor — green when price is on the "safe" side of the target
           * (i.e. has not yet crossed it), red when it has already passed it.
           *   "above" alert: safe while currentPrice < target
           *   "below" alert: safe while currentPrice > target
           *   "crosses":     always neutral amber
           */
          const distColor = currentPrice != null
            ? ((alert.condition === "above" && currentPrice < alert.target_price) ||
               (alert.condition === "below" && currentPrice > alert.target_price))
              ? "#22c55e"
              : "#ef4444"
            : "var(--c-muted)";

          return (
            <div
              key={alert.alert_id}
              className="alert-card"
              style={{ borderLeftColor: getCardBorderColor(alert) }}
            >
              {/* ── Card top row ───────────────────────────────────── */}
              <div className="alert-card-top">
                {/* Symbol */}
                <span className="alert-symbol">{alert.symbol}</span>

                {/* Condition badge */}
                {!isEditing && (
                  <span className="alert-badge" style={{ background: badge.bg, color: badge.color }}>
                    {alert.condition.toUpperCase()}
                  </span>
                )}

                {/* Target price */}
                {!isEditing && (
                  <span className="alert-target">
                    {currencySymbol}{parseFloat(alert.target_price).toFixed(2)}
                  </span>
                )}

                {/* Current price and distance to target */}
                {!isEditing && currentPrice != null && (
                  <span style={{
                    fontFamily: "var(--font-mono)", fontSize: 11,
                    color: "var(--c-muted)",
                  }}>
                    {/* Current live price */}
                    {currencySymbol}{currentPrice.toFixed(2)}
                    {/* Signed distance from current price to target */}
                    <span style={{ marginLeft: 5, color: distColor }}>
                      {distToTarget >= 0 ? "+" : "-"}
                      {currencySymbol}{Math.abs(distToTarget).toFixed(2)}
                    </span>
                  </span>
                )}

                {/* Note */}
                {!isEditing && alert.note && (
                  <span className="alert-note">{alert.note}</span>
                )}

                {/* Spacer */}
                <span style={{ flex: 1 }} />

                {/* Action menu (three-dot or direct buttons) */}
                {!isEditing && !isDeleting && (
                  <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    {/* Re-arm: only shown when the alert has been triggered */}
                    {alert.triggered_at && (
                      <button
                        className="btn btn-ghost"
                        title="Re-arm this alert"
                        onClick={() => handleRearm(alert)}
                        style={{ padding: "3px 7px", fontSize: 11, color: "#3b82f6" }}
                      >
                        RE-ARM
                      </button>
                    )}
                    {/* Toggle active/inactive */}
                    <button
                      className="btn btn-ghost"
                      title={alert.is_active ? "Deactivate" : "Activate"}
                      onClick={() => handleToggleActive(alert)}
                      style={{
                        padding: "3px 7px", fontSize: 12,
                        color: alert.is_active ? "var(--green)" : "var(--c-muted)",
                      }}
                    >
                      {alert.is_active ? "\u25CF" : "\u25CB"}
                    </button>
                    {/* Edit */}
                    <button
                      className="btn btn-ghost"
                      title="Edit"
                      onClick={() => startEdit(alert)}
                      style={{ padding: "3px 7px" }}
                    >
                      <Ic.edit />
                    </button>
                    {/* Delete */}
                    <button
                      className="btn btn-ghost"
                      title="Delete"
                      onClick={() => setDeletingId(alert.alert_id)}
                      style={{ padding: "3px 7px", color: "var(--red)" }}
                    >
                      <Ic.trash />
                    </button>
                  </div>
                )}
              </div>

              {/* ── Card bottom row: metadata ──────────────────────── */}
              {!isEditing && (
                <div className="alert-card-meta">
                  <span>Created: {fmtDate(alert.created_at)}</span>
                  <span style={{ marginLeft: 16 }}>
                    Status:{" "}
                    {alert.triggered_at
                      ? <span style={{ color: "#22c55e" }}>Triggered {fmtDate(alert.triggered_at)}</span>
                      : alert.is_active
                        ? <span style={{ color: "#f59e0b" }}>Active</span>
                        : <span style={{ color: "#6b7280" }}>Inactive</span>}
                  </span>
                </div>
              )}

              {/* ── Inline edit form ───────────────────────────────── */}
              {isEditing && (
                <div className="alert-edit-form">
                  <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
                    {/* Condition */}
                    <div className="form-field" style={{ minWidth: 120 }}>
                      <label className="form-label" style={{ fontSize: 10 }}>Condition</label>
                      <select
                        className="form-control"
                        value={editCondition}
                        onChange={(e) => setEditCondition(e.target.value)}
                        style={{
                          background: "var(--c-surface)", border: "1px solid var(--c-border)",
                          color: "var(--c-text)", fontFamily: "var(--font-mono)", fontSize: 11,
                          borderRadius: 3, padding: "6px 8px", cursor: "pointer",
                        }}
                      >
                        <option value="above">Above</option>
                        <option value="below">Below</option>
                        <option value="crosses">Crosses</option>
                      </select>
                    </div>
                    {/* Target Price */}
                    <div className="form-field" style={{ minWidth: 120 }}>
                      <label className="form-label" style={{ fontSize: 10 }}>Target Price</label>
                      <input
                        className="form-control"
                        type="number"
                        min="0"
                        step="any"
                        value={editTargetPrice}
                        onChange={(e) => setEditTargetPrice(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter") saveEdit(); if (e.key === "Escape") cancelEdit(); }}
                        autoFocus
                        style={{ width: 110 }}
                      />
                    </div>
                    {/* Note */}
                    <div className="form-field" style={{ flex: 1, minWidth: 160 }}>
                      <label className="form-label" style={{ fontSize: 10 }}>Note</label>
                      <input
                        className="form-control"
                        type="text"
                        value={editNote}
                        onChange={(e) => setEditNote(e.target.value)}
                        maxLength={256}
                        onKeyDown={(e) => { if (e.key === "Enter") saveEdit(); if (e.key === "Escape") cancelEdit(); }}
                        style={{ width: "100%" }}
                      />
                    </div>
                  </div>
                  {editError && (
                    <div style={{ fontSize: 11, color: "var(--red)", marginTop: 6 }}>
                      {editError}
                    </div>
                  )}
                  <div style={{ display: "flex", gap: 8, marginTop: 10, justifyContent: "flex-end" }}>
                    <button className="btn btn-ghost" onClick={cancelEdit} style={{ fontSize: 11 }}>
                      CANCEL
                    </button>
                    <button
                      className="btn btn-amber"
                      onClick={saveEdit}
                      disabled={editLoading}
                      style={{ fontSize: 11 }}
                    >
                      {editLoading ? <span className="loading-pulse">SAVING...</span> : "SAVE"}
                    </button>
                  </div>
                </div>
              )}

              {/* ── Delete confirmation ────────────────────────────── */}
              {isDeleting && (
                <div style={{
                  display: "flex", gap: 10, alignItems: "center",
                  marginTop: 8, padding: "8px 0",
                }}>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--red)" }}>
                    Delete this alert?
                  </span>
                  <button
                    className="btn btn-ghost"
                    onClick={() => setDeletingId(null)}
                    style={{ fontSize: 11 }}
                  >
                    CANCEL
                  </button>
                  <button
                    className="btn"
                    onClick={() => handleDelete(alert.alert_id)}
                    style={{
                      fontSize: 11, background: "rgba(239,68,68,.15)",
                      color: "var(--red)", border: "1px solid rgba(239,68,68,.3)",
                    }}
                  >
                    CONFIRM DELETE
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* ── Create alert modal ────────────────────────────────────── */}
      {showCreate && (
        <AlertModal
          symbol=""
          currentPrice={null}
          token={token}
          onClose={() => setShowCreate(false)}
          onCreated={() => fetchAlerts()}
        />
      )}
    </div>
  );
}

/* ── Page-scoped CSS ─────────────────────────────────────────────────────── */
const ALERTS_CSS = `
/* Filter tabs */
.alerts-tab {
  background: none; border: none; cursor: pointer;
  font-family: var(--font-mono); font-size: 11px; letter-spacing: 0.5px;
  color: var(--c-muted); padding: 10px 18px;
  border-bottom: 2px solid transparent;
  transition: color 0.15s, border-color 0.15s;
  display: flex; align-items: center; gap: 6;
}
.alerts-tab:hover { color: var(--c-text); }
.alerts-tab-active {
  color: #f59e0b;
  border-bottom-color: #f59e0b;
}
.alerts-tab-count {
  font-size: 10px; background: rgba(255,255,255,0.06);
  padding: 1px 6px; border-radius: 8px;
}
.alerts-tab-active .alerts-tab-count {
  background: rgba(245,158,11,.15); color: #f59e0b;
}

/* Alert card */
.alert-card {
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 8px;
  border-left: 3px solid #f59e0b;
  padding: 14px 18px;
  transition: background 0.15s;
}
.alert-card:hover {
  background: rgba(255,255,255,0.05);
}

/* Card top row */
.alert-card-top {
  display: flex; align-items: center; gap: 12;
  flex-wrap: wrap;
}

/* Symbol label */
.alert-symbol {
  font-family: var(--font-mono); font-size: 14px; font-weight: 700;
  color: #f59e0b; letter-spacing: 0.5px;
}

/* Condition badge */
.alert-badge {
  font-family: var(--font-mono); font-size: 10px; font-weight: 600;
  letter-spacing: 0.5px; padding: 2px 8px; border-radius: 3px;
}

/* Target price */
.alert-target {
  font-family: var(--font-mono); font-size: 13px; font-weight: 600;
  color: var(--c-text);
}

/* Note */
.alert-note {
  font-family: var(--font-mono); font-size: 11px; color: var(--c-muted);
  max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

/* Metadata row */
.alert-card-meta {
  font-family: var(--font-mono); font-size: 10px; color: var(--c-muted);
  margin-top: 8px; letter-spacing: 0.3px;
}

/* Edit form area */
.alert-edit-form {
  margin-top: 10px; padding-top: 10px;
  border-top: 1px solid rgba(255,255,255,0.06);
}
`;
