/**
 * NotificationBell.jsx — Topbar notification bell with dropdown panel.
 *
 * Displays a bell icon with an unread badge. Clicking it opens a
 * dropdown panel showing recent notifications. Polls for new
 * notifications every 30 seconds. Provides "mark all read" and
 * individual "mark read" actions.
 *
 * Props:
 *   @param {string} token - JWT access token for API calls
 */

import { useState, useEffect, useCallback, useRef } from "react";
import api from "../../api/client";
import { Ic } from "./Icons";

/* ── Styles ──────────────────────────────────────────────────────────────── */
const S = {
  wrapper: {
    position: "relative",
    display: "flex",
    alignItems: "center",
  },
  btn: {
    background: "none",
    border: "none",
    color: "var(--muted)",
    cursor: "pointer",
    padding: "4px 6px",
    display: "flex",
    alignItems: "center",
    position: "relative",
  },
  badge: {
    position: "absolute",
    top: 0,
    right: 2,
    background: "var(--red)",
    color: "#fff",
    fontSize: 8,
    fontFamily: "var(--font-mono)",
    fontWeight: 700,
    borderRadius: "50%",
    minWidth: 14,
    height: 14,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    lineHeight: 1,
    padding: "0 3px",
  },
  panel: {
    position: "absolute",
    top: "calc(100% + 8px)",
    right: 0,
    width: 340,
    maxHeight: 420,
    background: "var(--panel)",
    border: "1px solid var(--border)",
    borderRadius: 4,
    boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
    zIndex: 9999,
    display: "flex",
    flexDirection: "column",
    fontFamily: "var(--font-mono)",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "10px 14px",
    borderBottom: "1px solid var(--border)",
    fontSize: 11,
    letterSpacing: 1,
    color: "var(--amber)",
    fontFamily: "var(--font-disp)",
  },
  markAllBtn: {
    background: "none",
    border: "none",
    color: "var(--muted)",
    cursor: "pointer",
    fontSize: 9,
    fontFamily: "var(--font-mono)",
    letterSpacing: 0.5,
    padding: "2px 6px",
  },
  list: {
    flex: 1,
    overflowY: "auto",
    padding: 0,
    margin: 0,
    listStyle: "none",
  },
  item: {
    padding: "10px 14px",
    borderBottom: "1px solid var(--border)",
    cursor: "pointer",
    transition: "background 0.15s",
  },
  itemUnread: {
    background: "rgba(255,191,0,0.04)",
    borderLeft: "2px solid var(--amber)",
  },
  itemRead: {
    opacity: 0.6,
    borderLeft: "2px solid transparent",
  },
  itemTitle: {
    fontSize: 11,
    color: "var(--bright)",
    marginBottom: 3,
    lineHeight: 1.3,
  },
  itemMeta: {
    fontSize: 9,
    color: "var(--muted)",
    display: "flex",
    justifyContent: "space-between",
  },
  empty: {
    padding: 24,
    textAlign: "center",
    color: "var(--muted)",
    fontSize: 11,
  },
};

/**
 * timeAgo — formats a date into a relative time string.
 *
 * @param {string} dateStr - ISO date string
 * @returns {string} Human-readable relative time (e.g. "3m ago", "2h ago")
 */
function timeAgo(dateStr) {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

export function NotificationBell({ token }) {
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const panelRef = useRef(null);

  /* ── Fetch notifications ─────────────────────────────────────────────── */
  const fetchNotifications = useCallback(async () => {
    if (!token) return;
    try {
      const data = await api.listNotifications({ limit: 20 }, token);
      setNotifications(data.notifications || []);
      setUnreadCount(data.unread_count || 0);
    } catch {
      /* silent — bell should never break the app */
    }
  }, [token]);

  /* Poll every 30 seconds */
  useEffect(() => {
    fetchNotifications();
    const id = setInterval(fetchNotifications, 30000);
    return () => clearInterval(id);
  }, [fetchNotifications]);

  /* ── Close on outside click ──────────────────────────────────────────── */
  useEffect(() => {
    if (!open) return;
    /** handleClick — close panel if click is outside the panel ref. */
    function handleClick(e) {
      if (panelRef.current && !panelRef.current.contains(e.target)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  /* ── Mark individual notification as read ─────────────────────────── */
  const markRead = useCallback(async (notifId) => {
    try {
      await api.markNotificationsRead([notifId], token);
      setNotifications(prev =>
        prev.map(n => n.notification_id === notifId ? { ...n, is_read: true } : n)
      );
      setUnreadCount(prev => Math.max(0, prev - 1));
    } catch { /* silent */ }
  }, [token]);

  /* ── Mark all as read ────────────────────────────────────────────── */
  const markAllRead = useCallback(async () => {
    try {
      await api.markAllNotificationsRead(token);
      setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } catch { /* silent */ }
  }, [token]);

  return (
    <div style={S.wrapper} ref={panelRef}>
      {/* Bell button */}
      <button
        style={S.btn}
        onClick={() => setOpen(prev => !prev)}
        title="Notifications"
      >
        <Ic.bell />
        {unreadCount > 0 && (
          <span style={S.badge}>{unreadCount > 99 ? "99+" : unreadCount}</span>
        )}
      </button>

      {/* Dropdown panel */}
      {open && (
        <div style={S.panel}>
          <div style={S.header}>
            <span>NOTIFICATIONS</span>
            {unreadCount > 0 && (
              <button style={S.markAllBtn} onClick={markAllRead}>
                MARK ALL READ
              </button>
            )}
          </div>

          <ul style={S.list}>
            {notifications.length === 0 && (
              <li style={S.empty}>No notifications yet.</li>
            )}
            {notifications.map((n) => (
              <li
                key={n.notification_id}
                style={{
                  ...S.item,
                  ...(n.is_read ? S.itemRead : S.itemUnread),
                }}
                onClick={() => !n.is_read && markRead(n.notification_id)}
              >
                <div style={S.itemTitle}>{n.title}</div>
                {n.body && (
                  <div style={{ fontSize: 10, color: "var(--muted)", marginBottom: 3, lineHeight: 1.3 }}>
                    {n.body.length > 80 ? n.body.slice(0, 80) + "..." : n.body}
                  </div>
                )}
                <div style={S.itemMeta}>
                  <span>{n.event_type.replace(/_/g, " ").toUpperCase()}</span>
                  <span>{timeAgo(n.created_at)}</span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
