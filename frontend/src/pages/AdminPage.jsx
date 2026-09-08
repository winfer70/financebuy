/**
 * AdminPage.jsx — Admin dashboard for TickerTap.
 *
 * Provides a three-tab administration interface:
 *   1. USERS     — List all users with lock/unlock actions, client-side search.
 *   2. REPORTS   — List, filter, expand, update, and delete user-submitted reports.
 *   3. AUDIT LOG — Browse recent audit log entries with optional action filter.
 *
 * Access control:
 *   On mount, calls api.checkAdmin(token).  If the backend returns 403 the page
 *   renders an "Access Denied" message instead of the dashboard.
 *
 * Data flow:
 *   - Each tab fetches its data lazily on first activation (and on manual refresh).
 *   - User lock/unlock, report update/delete, etc. mutate via the api client and
 *     refresh the relevant tab data on success.
 *
 * Props:
 *   @param {string} token - JWT access token
 */

import { useState, useEffect, useCallback, Fragment } from "react";
import api from "../api/client";

/* ═══════════════════════════════════════════════════════════════════════════
   CONSTANTS
═══════════════════════════════════════════════════════════════════════════ */

/** Tab identifiers for the admin dashboard. */
const TABS = [
  { id: "users",             label: "USERS"             },
  { id: "reports",           label: "REPORTS"           },
  { id: "audit-log",         label: "AUDIT LOG"         },
  { id: "telegram-invites",  label: "TELEGRAM INVITES"  },
];

/** Report status options for the filter dropdown. */
const REPORT_STATUSES = ["all", "new", "reviewed", "resolved", "dismissed"];

/** Report type options for the filter dropdown. */
const REPORT_TYPES = ["all", "bug", "suggestion", "activation_bug"];

/** Colour map for report status badges. */
const STATUS_COLORS = {
  new:       { bg: "rgba(245,158,11,0.15)", color: "#f59e0b" },
  reviewed:  { bg: "rgba(59,130,246,0.15)",  color: "#3b82f6" },
  resolved:  { bg: "rgba(34,197,94,0.15)",   color: "#22c55e" },
  dismissed: { bg: "rgba(148,163,184,0.15)", color: "#94a3b8" },
};

/** Colour map for report type badges. */
const TYPE_COLORS = {
  bug:            { bg: "rgba(239,68,68,0.15)",   color: "#ef4444" },
  suggestion:     { bg: "rgba(99,102,241,0.15)",  color: "#6366f1" },
  activation_bug: { bg: "rgba(245,158,11,0.15)",  color: "#f59e0b" },
};

/* ═══════════════════════════════════════════════════════════════════════════
   INLINE STYLES (Bloomberg terminal aesthetic)
═══════════════════════════════════════════════════════════════════════════ */

const S = {
  page: {
    padding: "24px 32px",
    fontFamily: "var(--font-mono)",
    color: "var(--fg)",
    minHeight: "100%",
  },
  header: {
    fontSize: 18,
    fontWeight: 700,
    letterSpacing: 1.5,
    color: "var(--amber)",
    marginBottom: 20,
  },
  tabBar: {
    display: "flex",
    gap: 0,
    borderBottom: "1px solid var(--border)",
    marginBottom: 20,
  },
  tab: (active) => ({
    padding: "10px 20px",
    cursor: "pointer",
    background: "none",
    border: "none",
    borderBottom: active ? "2px solid var(--amber)" : "2px solid transparent",
    color: active ? "var(--amber)" : "var(--muted)",
    fontFamily: "var(--font-mono)",
    fontSize: 12,
    fontWeight: 600,
    letterSpacing: 1,
    transition: "color 0.15s, border-color 0.15s",
  }),
  searchInput: {
    background: "var(--surface)",
    border: "1px solid var(--border)",
    borderRadius: 4,
    padding: "6px 10px",
    fontFamily: "var(--font-mono)",
    fontSize: 11,
    color: "var(--fg)",
    outline: "none",
    width: 260,
  },
  select: {
    background: "var(--surface)",
    border: "1px solid var(--border)",
    borderRadius: 4,
    padding: "6px 10px",
    fontFamily: "var(--font-mono)",
    fontSize: 11,
    color: "var(--fg)",
    outline: "none",
    cursor: "pointer",
  },
  toolbar: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    marginBottom: 16,
    flexWrap: "wrap",
  },
  count: {
    fontSize: 11,
    color: "var(--muted)",
    marginLeft: "auto",
  },
  badge: (colors) => ({
    display: "inline-block",
    fontSize: 10,
    fontWeight: 600,
    letterSpacing: 0.5,
    padding: "2px 8px",
    borderRadius: 4,
    background: colors.bg,
    color: colors.color,
    textTransform: "uppercase",
  }),
  ghostBtn: {
    background: "none",
    border: "1px solid var(--border)",
    borderRadius: 4,
    padding: "4px 10px",
    fontFamily: "var(--font-mono)",
    fontSize: 10,
    color: "var(--fg)",
    cursor: "pointer",
    transition: "border-color 0.15s, color 0.15s",
    letterSpacing: 0.5,
  },
  dangerBtn: {
    background: "none",
    border: "1px solid rgba(239,68,68,0.4)",
    borderRadius: 4,
    padding: "4px 10px",
    fontFamily: "var(--font-mono)",
    fontSize: 10,
    color: "#ef4444",
    cursor: "pointer",
    letterSpacing: 0.5,
  },
  primaryBtn: {
    background: "var(--amber)",
    border: "none",
    borderRadius: 4,
    padding: "6px 14px",
    fontFamily: "var(--font-mono)",
    fontSize: 10,
    fontWeight: 600,
    color: "#000",
    cursor: "pointer",
    letterSpacing: 0.5,
  },
  textarea: {
    background: "var(--surface)",
    border: "1px solid var(--border)",
    borderRadius: 4,
    padding: "8px 10px",
    fontFamily: "var(--font-mono)",
    fontSize: 11,
    color: "var(--fg)",
    outline: "none",
    width: "100%",
    minHeight: 60,
    resize: "vertical",
  },
  expandedRow: {
    background: "rgba(255,255,255,0.02)",
    padding: "12px 16px",
    borderBottom: "1px solid var(--border)",
    fontSize: 11,
    lineHeight: 1.6,
  },
  error: {
    color: "var(--red)",
    fontFamily: "var(--font-mono)",
    fontSize: 12,
    padding: "40px 0",
    textAlign: "center",
  },
  loading: {
    color: "var(--muted)",
    fontFamily: "var(--font-mono)",
    fontSize: 12,
    padding: "40px 0",
    textAlign: "center",
    letterSpacing: 0.5,
  },
  denied: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    minHeight: "60vh",
    gap: 12,
  },
  deniedIcon: {
    fontSize: 48,
    color: "var(--red)",
    marginBottom: 8,
  },
  deniedTitle: {
    fontSize: 18,
    fontWeight: 700,
    color: "var(--red)",
    letterSpacing: 1,
  },
  deniedMsg: {
    fontSize: 12,
    color: "var(--muted)",
    maxWidth: 400,
    textAlign: "center",
    lineHeight: 1.6,
  },
  detailLabel: {
    color: "var(--muted)",
    fontSize: 10,
    letterSpacing: 0.5,
    textTransform: "uppercase",
    marginBottom: 4,
  },
};

/* ═══════════════════════════════════════════════════════════════════════════
   HELPER FUNCTIONS
═══════════════════════════════════════════════════════════════════════════ */

/**
 * fmtDate — Format an ISO datetime string into a compact locale display.
 * @param {string|null} iso - ISO 8601 date string
 * @returns {string} Formatted date or "—" if null
 */
function fmtDate(iso) {
  if (!iso) return "\u2014";
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", {
    year: "numeric", month: "short", day: "numeric",
  }) + " " + d.toLocaleTimeString("en-US", {
    hour: "2-digit", minute: "2-digit", hour12: false,
  });
}

/**
 * fmtChanges — Render old/new value changes from audit log as a compact string.
 * @param {object|null} oldVals - Previous values object
 * @param {object|null} newVals - Updated values object
 * @returns {string} Compact diff representation
 */
function fmtChanges(oldVals, newVals) {
  if (!oldVals && !newVals) return "\u2014";
  const parts = [];
  const allKeys = new Set([
    ...Object.keys(oldVals || {}),
    ...Object.keys(newVals || {}),
  ]);
  for (const key of allKeys) {
    const ov = oldVals?.[key];
    const nv = newVals?.[key];
    if (JSON.stringify(ov) !== JSON.stringify(nv)) {
      parts.push(`${key}: ${JSON.stringify(ov)} \u2192 ${JSON.stringify(nv)}`);
    }
  }
  return parts.length > 0 ? parts.join(", ") : "\u2014";
}

/* ═══════════════════════════════════════════════════════════════════════════
   USERS TAB
═══════════════════════════════════════════════════════════════════════════ */

/**
 * UsersTab — Displays all users in a searchable table with lock/unlock actions.
 *
 * @param {string} token - JWT access token
 */
function UsersTab({ token }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const [actionLoading, setActionLoading] = useState(null); // userId being toggled

  /**
   * fetchUsers — Load all users from the admin endpoint.
   * Sets loading/error state accordingly.
   */
  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.adminListUsers(token);
      setUsers(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  /* Fetch on mount */
  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  /**
   * handleToggleLock — Lock or unlock a user account.
   * @param {string}  userId   - UUID of the user
   * @param {boolean} isActive - Current active status (true = will lock, false = will unlock)
   */
  const handleToggleLock = async (userId, isActive) => {
    setActionLoading(userId);
    try {
      if (isActive) {
        await api.adminLockUser(userId, token);
      } else {
        await api.adminUnlockUser(userId, token);
      }
      await fetchUsers(); // Refresh list after toggle
    } catch (e) {
      setError(e.message);
    } finally {
      setActionLoading(null);
    }
  };

  /* Client-side filter by email or name */
  const needle = search.toLowerCase();
  const filtered = users.filter((u) => {
    const haystack = `${u.email} ${u.first_name || ""} ${u.last_name || ""}`.toLowerCase();
    return haystack.includes(needle);
  });

  if (loading) return <div style={S.loading}>LOADING USERS...</div>;
  if (error) return <div style={S.error}>ERROR: {error}</div>;

  return (
    <div>
      {/* Toolbar: search + count */}
      <div style={S.toolbar}>
        <input
          style={S.searchInput}
          placeholder="Search by email or name..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <span style={S.count}>{filtered.length} of {users.length} users</span>
      </div>

      {/* Users table */}
      <table className="data-table" style={{ width: "100%" }}>
        <thead>
          <tr>
            <th>EMAIL</th>
            <th>NAME</th>
            <th>STATUS</th>
            <th>KYC</th>
            <th>EMAIL VERIFIED</th>
            <th>CREATED</th>
            <th>ACTIONS</th>
          </tr>
        </thead>
        <tbody>
          {filtered.map((u) => (
            <tr key={u.user_id}>
              <td style={{ fontSize: 11 }}>{u.email}</td>
              <td style={{ fontSize: 11 }}>
                {u.first_name || ""} {u.last_name || ""}
              </td>
              <td>
                {u.is_active ? (
                  <span style={S.badge({ bg: "rgba(34,197,94,0.15)", color: "#22c55e" })}>
                    ACTIVE
                  </span>
                ) : (
                  <span style={S.badge({ bg: "rgba(239,68,68,0.15)", color: "#ef4444" })}>
                    LOCKED
                  </span>
                )}
              </td>
              <td style={{ fontSize: 11, textTransform: "uppercase" }}>{u.kyc_status}</td>
              <td style={{ fontSize: 11 }}>
                {u.email_verified ? (
                  <span style={{ color: "#22c55e" }}>YES</span>
                ) : (
                  <span style={{ color: "var(--muted)" }}>NO</span>
                )}
              </td>
              <td style={{ fontSize: 11 }}>{fmtDate(u.created_at)}</td>
              <td>
                <button
                  style={u.is_active ? S.dangerBtn : S.ghostBtn}
                  disabled={actionLoading === u.user_id}
                  onClick={() => handleToggleLock(u.user_id, u.is_active)}
                  title={u.is_active ? "Lock user" : "Unlock user"}
                >
                  {actionLoading === u.user_id
                    ? "..."
                    : u.is_active
                      ? "LOCK"
                      : "UNLOCK"}
                </button>
              </td>
            </tr>
          ))}
          {filtered.length === 0 && (
            <tr>
              <td colSpan={7} style={{ textAlign: "center", color: "var(--muted)", padding: 20 }}>
                No users match the search criteria.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   REPORTS TAB
═══════════════════════════════════════════════════════════════════════════ */

/**
 * ReportsTab — Displays, filters, expands, updates, and deletes user reports.
 *
 * @param {string} token - JWT access token
 */
function ReportsTab({ token }) {
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [expandedId, setExpandedId] = useState(null);  // report_id of expanded row
  const [editNotes, setEditNotes] = useState("");       // admin_notes textarea
  const [editStatus, setEditStatus] = useState("");     // status dropdown in detail
  const [actionLoading, setActionLoading] = useState(false);

  /**
   * fetchReports — Load reports with current filters from the admin endpoint.
   */
  const fetchReports = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {};
      if (statusFilter !== "all") params.status = statusFilter;
      if (typeFilter !== "all") params.report_type = typeFilter;
      const data = await api.adminListReports(params, token);
      setReports(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token, statusFilter, typeFilter]);

  /* Fetch on mount and when filters change */
  useEffect(() => { fetchReports(); }, [fetchReports]);

  /**
   * handleExpand — Toggle the expanded detail view for a report row.
   * Pre-populates the edit form with the report's current values.
   * @param {object} report - Report object to expand/collapse
   */
  const handleExpand = (report) => {
    if (expandedId === report.report_id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(report.report_id);
    setEditNotes(report.admin_notes || "");
    setEditStatus(report.status);
  };

  /**
   * handleSave — Persist status and admin_notes changes for the expanded report.
   * @param {string} reportId - UUID of the report to update
   */
  const handleSave = async (reportId) => {
    setActionLoading(true);
    try {
      await api.adminUpdateReport(reportId, {
        status: editStatus,
        admin_notes: editNotes,
      }, token);
      await fetchReports();
      setExpandedId(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setActionLoading(false);
    }
  };

  /**
   * handleDelete — Permanently delete a report after confirmation.
   * @param {string} reportId - UUID of the report to delete
   */
  const handleDelete = async (reportId) => {
    if (!window.confirm("Permanently delete this report?")) return;
    setActionLoading(true);
    try {
      await api.adminDeleteReport(reportId, token);
      await fetchReports();
      setExpandedId(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) return <div style={S.loading}>LOADING REPORTS...</div>;
  if (error) return <div style={S.error}>ERROR: {error}</div>;

  return (
    <div>
      {/* Filter toolbar */}
      <div style={S.toolbar}>
        <select
          style={S.select}
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          {REPORT_STATUSES.map((s) => (
            <option key={s} value={s}>{s.toUpperCase()}</option>
          ))}
        </select>
        <select
          style={S.select}
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
        >
          {REPORT_TYPES.map((t) => (
            <option key={t} value={t}>{t.toUpperCase()}</option>
          ))}
        </select>
        <span style={S.count}>{reports.length} reports</span>
      </div>

      {/* Reports table */}
      <table className="data-table" style={{ width: "100%" }}>
        <thead>
          <tr>
            <th>TYPE</th>
            <th>SUBJECT</th>
            <th>EMAIL</th>
            <th>STATUS</th>
            <th>CREATED</th>
            <th>ACTIONS</th>
          </tr>
        </thead>
        <tbody>
          {reports.map((r) => {
            const isExpanded = expandedId === r.report_id;
            const typeColor = TYPE_COLORS[r.report_type] || TYPE_COLORS.bug;
            const statusColor = STATUS_COLORS[r.status] || STATUS_COLORS.new;
            return (
              <Fragment key={r.report_id}>
                <tr
                  onClick={() => handleExpand(r)}
                  style={{ cursor: "pointer" }}
                >
                  <td>
                    <span style={S.badge(typeColor)}>
                      {r.report_type.replace("_", " ")}
                    </span>
                  </td>
                  <td style={{ fontSize: 11, maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {r.subject}
                  </td>
                  <td style={{ fontSize: 11 }}>{r.reporter_email}</td>
                  <td>
                    <span style={S.badge(statusColor)}>
                      {r.status}
                    </span>
                  </td>
                  <td style={{ fontSize: 11 }}>{fmtDate(r.created_at)}</td>
                  <td>
                    <button
                      style={S.ghostBtn}
                      onClick={(e) => { e.stopPropagation(); handleExpand(r); }}
                    >
                      {isExpanded ? "COLLAPSE" : "EXPAND"}
                    </button>
                  </td>
                </tr>
                {/* Expanded detail row */}
                {isExpanded && (
                  <tr>
                    <td colSpan={6} style={{ padding: 0 }}>
                      <div style={S.expandedRow}>
                        {/* Report body */}
                        <div style={{ marginBottom: 12 }}>
                          <div style={S.detailLabel}>BODY</div>
                          <div style={{ whiteSpace: "pre-wrap", fontSize: 11, lineHeight: 1.6 }}>
                            {r.body}
                          </div>
                        </div>

                        {/* Category (if present) */}
                        {r.category && (
                          <div style={{ marginBottom: 12 }}>
                            <div style={S.detailLabel}>CATEGORY</div>
                            <div style={{ fontSize: 11 }}>{r.category}</div>
                          </div>
                        )}

                        {/* Resolved at (if present) */}
                        {r.resolved_at && (
                          <div style={{ marginBottom: 12 }}>
                            <div style={S.detailLabel}>RESOLVED AT</div>
                            <div style={{ fontSize: 11 }}>{fmtDate(r.resolved_at)}</div>
                          </div>
                        )}

                        {/* Status update dropdown */}
                        <div style={{ marginBottom: 12 }}>
                          <div style={S.detailLabel}>UPDATE STATUS</div>
                          <select
                            style={{ ...S.select, minWidth: 160 }}
                            value={editStatus}
                            onChange={(e) => setEditStatus(e.target.value)}
                          >
                            {REPORT_STATUSES.filter((s) => s !== "all").map((s) => (
                              <option key={s} value={s}>{s.toUpperCase()}</option>
                            ))}
                          </select>
                        </div>

                        {/* Admin notes textarea */}
                        <div style={{ marginBottom: 12 }}>
                          <div style={S.detailLabel}>ADMIN NOTES</div>
                          <textarea
                            style={S.textarea}
                            value={editNotes}
                            onChange={(e) => setEditNotes(e.target.value)}
                            placeholder="Add admin notes..."
                          />
                        </div>

                        {/* Action buttons */}
                        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                          <button
                            style={S.primaryBtn}
                            disabled={actionLoading}
                            onClick={() => handleSave(r.report_id)}
                          >
                            {actionLoading ? "SAVING..." : "SAVE"}
                          </button>
                          <button
                            style={S.dangerBtn}
                            disabled={actionLoading}
                            onClick={() => handleDelete(r.report_id)}
                          >
                            DELETE
                          </button>
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
          {reports.length === 0 && (
            <tr>
              <td colSpan={6} style={{ textAlign: "center", color: "var(--muted)", padding: 20 }}>
                No reports match the current filters.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   AUDIT LOG TAB
═══════════════════════════════════════════════════════════════════════════ */

/**
 * AuditLogTab — Displays recent audit log entries with optional action filter.
 *
 * @param {string} token - JWT access token
 */
function AuditLogTab({ token }) {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionFilter, setActionFilter] = useState("");

  /**
   * fetchLogs — Load audit log entries from the admin endpoint.
   * Applies the action filter if set.
   */
  const fetchLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = { limit: 100 };
      if (actionFilter) params.action = actionFilter;
      const data = await api.adminAuditLogs(params, token);
      setLogs(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token, actionFilter]);

  /* Fetch on mount and when action filter changes */
  useEffect(() => { fetchLogs(); }, [fetchLogs]);

  /* Extract unique action types from loaded logs for the filter dropdown */
  const actionTypes = [...new Set(logs.map((l) => l.action))].sort();

  if (loading) return <div style={S.loading}>LOADING AUDIT LOGS...</div>;
  if (error) return <div style={S.error}>ERROR: {error}</div>;

  return (
    <div>
      {/* Filter toolbar */}
      <div style={S.toolbar}>
        <select
          style={S.select}
          value={actionFilter}
          onChange={(e) => setActionFilter(e.target.value)}
        >
          <option value="">ALL ACTIONS</option>
          {actionTypes.map((a) => (
            <option key={a} value={a}>{a.toUpperCase()}</option>
          ))}
        </select>
        <span style={S.count}>{logs.length} entries</span>
      </div>

      {/* Audit log table */}
      <table className="data-table" style={{ width: "100%" }}>
        <thead>
          <tr>
            <th>TIMESTAMP</th>
            <th>USER</th>
            <th>ACTION</th>
            <th>TABLE</th>
            <th>DETAILS</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((l) => (
            <tr key={l.log_id}>
              <td style={{ fontSize: 11, whiteSpace: "nowrap" }}>{fmtDate(l.created_at)}</td>
              <td style={{ fontSize: 10, maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis" }}>
                {l.user_id || "\u2014"}
              </td>
              <td>
                <span style={{
                  fontSize: 10,
                  fontWeight: 600,
                  letterSpacing: 0.5,
                  color: "var(--amber)",
                  textTransform: "uppercase",
                }}>
                  {l.action}
                </span>
              </td>
              <td style={{ fontSize: 11 }}>{l.table_name || "\u2014"}</td>
              <td style={{ fontSize: 10, maxWidth: 400, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {fmtChanges(l.old_values, l.new_values)}
              </td>
            </tr>
          ))}
          {logs.length === 0 && (
            <tr>
              <td colSpan={5} style={{ textAlign: "center", color: "var(--muted)", padding: 20 }}>
                No audit log entries found.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

/**
 * TelegramInvitesTab — Mint a one-time Telegram-invite registration link.
 *
 * Each generated link works exactly once: it unlocks the Telegram-connect
 * step on /register for whoever opens it, and stops working the moment
 * that registration completes. The bot token is never part of this flow —
 * only the resulting register_url, which is safe to share.
 */
function TelegramInvitesTab({ token }) {
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState(null);
  const [invite, setInvite] = useState(null); // {code, expires_at, register_url}
  const [copied, setCopied] = useState(false);

  const handleGenerate = async () => {
    setGenerating(true);
    setError(null);
    setCopied(false);
    try {
      const data = await api.adminCreateTelegramInvite(token);
      setInvite(data);
    } catch (e) {
      setError(e.message || "Failed to generate invite");
    } finally {
      setGenerating(false);
    }
  };

  const handleCopy = async () => {
    if (!invite?.register_url) return;
    try {
      await navigator.clipboard.writeText(invite.register_url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (_) { /* clipboard permission denied — user can still select-copy */ }
  };

  return (
    <div style={{ fontFamily: "var(--font-mono)", maxWidth: 560 }}>
      <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.6, marginBottom: 16 }}>
        Generate a one-time link that lets a friend register and connect their
        own Telegram chat for their own alerts. Each link works exactly once —
        it stops working the moment that registration completes.
      </div>
      <button
        type="button"
        onClick={handleGenerate}
        disabled={generating}
        className="btn btn-amber"
        style={{ marginBottom: 16 }}
      >
        {generating ? "GENERATING..." : "GENERATE INVITE LINK"}
      </button>
      {error && (
        <div style={{ color: "var(--red, #e5484d)", fontSize: 11, marginBottom: 12 }}>{error}</div>
      )}
      {invite && (
        <div style={{
          border: "1px solid var(--border, #333)", borderRadius: 4, padding: 14,
          background: "var(--bg2, #161616)",
        }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input
              readOnly
              value={invite.register_url}
              onFocus={(e) => e.target.select()}
              style={{
                flex: 1, background: "var(--bg3, #111)", border: "1px solid var(--border, #333)",
                borderRadius: 3, padding: "8px 10px", color: "var(--text, #eee)",
                fontFamily: "inherit", fontSize: 12,
              }}
            />
            <button type="button" onClick={handleCopy} className="btn" style={{ whiteSpace: "nowrap" }}>
              {copied ? "COPIED" : "COPY"}
            </button>
          </div>
          <div style={{ color: "var(--muted)", fontSize: 10, marginTop: 8 }}>
            Expires {new Date(invite.expires_at).toLocaleString()} if unused.
          </div>
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   MAIN ADMIN PAGE
═══════════════════════════════════════════════════════════════════════════ */

/**
 * AdminPage — Top-level admin dashboard component.
 *
 * On mount, verifies admin access via api.checkAdmin(token).
 * If denied, renders an "Access Denied" message.
 * Otherwise, renders a three-tab interface for Users, Reports, and Audit Log.
 *
 * @param {object} props
 * @param {string} props.token - JWT access token
 * @returns {JSX.Element}
 */
export default function AdminPage({ token }) {
  const [isAdmin, setIsAdmin] = useState(null); // null = loading, true = admin, false = denied
  const [activeTab, setActiveTab] = useState("users");

  /**
   * checkAdmin — Verify admin status on mount.
   * Sets isAdmin to true on 200, false on error (403).
   */
  useEffect(() => {
    let cancelled = false;
    api.checkAdmin(token)
      .then(() => { if (!cancelled) setIsAdmin(true); })
      .catch(() => { if (!cancelled) setIsAdmin(false); });
    return () => { cancelled = true; };
  }, [token]);

  /* Loading state while checking admin access */
  if (isAdmin === null) {
    return (
      <div style={S.page}>
        <div style={S.loading}>VERIFYING ADMIN ACCESS...</div>
      </div>
    );
  }

  /* Access denied */
  if (!isAdmin) {
    return (
      <div className="page-scroll">
      <div style={S.page}>
        <div style={S.denied}>
          <div style={S.deniedIcon}>
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <rect x="3" y="11" width="18" height="11" rx="2"/>
              <path d="M7 11V7a5 5 0 0110 0v4"/>
            </svg>
          </div>
          <div style={S.deniedTitle}>ACCESS DENIED</div>
          <div style={S.deniedMsg}>
            Your account does not have administrator privileges.
            Contact a system administrator if you believe this is an error.
          </div>
        </div>
      </div>
      </div>
    );
  }

  /* Admin dashboard */
  return (
    <div className="page-scroll">
    <div style={S.page}>
      <div style={S.header}>ADMIN DASHBOARD</div>

      {/* Tab bar */}
      <div style={S.tabBar}>
        {TABS.map((t) => (
          <button
            key={t.id}
            style={S.tab(activeTab === t.id)}
            onClick={() => setActiveTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "users"             && <UsersTab token={token} />}
      {activeTab === "reports"           && <ReportsTab token={token} />}
      {activeTab === "audit-log"         && <AuditLogTab token={token} />}
      {activeTab === "telegram-invites"  && <TelegramInvitesTab token={token} />}
    </div>
    </div>
  );
}
