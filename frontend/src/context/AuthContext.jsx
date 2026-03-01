/**
 * context/AuthContext.jsx
 *
 * React Context that owns ALL authentication state for TickerTap:
 *   - authToken, authUser, accountId
 *   - handleLogin / handleLogout
 *   - Session-expiry listener (401 from API)
 *   - Inactivity auto-logout (5 minutes)
 *   - Backend health flag
 *
 * Wrap <App> with <AuthProvider> so every component can access auth
 * state via the `useAuth()` hook without prop-drilling.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import api from "../api/client";

/* ── Context creation ────────────────────────────────────────────────────── */
const AuthContext = createContext(null);

/* ── Storage keys (P7.13 — renamed from fb_* to tickertap_* prefix) ─────── */
// Old "fb_" prefix suggested Firebase; app doesn't use Firebase.
// Migration: old keys are cleaned up automatically on first load below.
const STORAGE_TOKEN   = "tickertap_token";
const STORAGE_USER    = "tickertap_user";
const STORAGE_ACCOUNT = "tickertap_account";
const IDLE_KEY        = "tickertap_last_activity";
const IDLE_MS         = 5 * 60 * 1000; // 5 minutes

// Migrate old fb_* keys to new tickertap_* keys on first load
const _OLD_KEYS = ["fb_token", "fb_user", "fb_account", "fb_last_activity"];
_OLD_KEYS.forEach((k) => {
  const v = sessionStorage.getItem(k) ?? localStorage.getItem(k);
  if (v) {
    const newKey = k.replace("fb_", "tickertap_");
    sessionStorage.setItem(newKey, v);
  }
  sessionStorage.removeItem(k);
  localStorage.removeItem(k);
});

/**
 * AuthProvider — mount once at the root of the component tree.
 *
 * @param {{ children: React.ReactNode, onToast: Function }} props
 *   onToast(msg: string, isError?: boolean) — surfaces toasts from auth events
 */
export function AuthProvider({ children, onToast }) {
  /* ── Initialise from sessionStorage so a page refresh keeps the session ── */
  const [authToken, setAuthToken] = useState(
    () => sessionStorage.getItem(STORAGE_TOKEN) || null
  );
  const [authUser, setAuthUser] = useState(() => {
    try {
      return JSON.parse(sessionStorage.getItem(STORAGE_USER) || "null");
    } catch {
      return null;
    }
  });
  const [accountId, setAccountId] = useState(
    () => sessionStorage.getItem(STORAGE_ACCOUNT) || null
  );

  // null = probe not complete, true = reachable, false = offline
  const [backendOk, setBackendOk] = useState(null);

  /* ── Probe backend once on mount ─────────────────────────────────────── */
  useEffect(() => {
    api.health()
      .then(() => setBackendOk(true))
      .catch(() => setBackendOk(false));
  }, []);

  /* ── Logout helper (shared by explicit logout + expiry + inactivity) ─── */
  const handleLogout = useCallback(() => {
    setAuthToken(null);
    setAuthUser(null);
    setAccountId(null);
    sessionStorage.removeItem(STORAGE_TOKEN);
    sessionStorage.removeItem(STORAGE_USER);
    sessionStorage.removeItem(STORAGE_ACCOUNT);
    onToast?.("SESSION TERMINATED");
  }, [onToast]);

  /* ── Listen for session-expired events dispatched by apiFetch on 401 ─── */
  useEffect(() => {
    const onExpired = () => handleLogout();
    window.addEventListener("session-expired", onExpired);
    return () => window.removeEventListener("session-expired", onExpired);
  }, [handleLogout]);

  /* ── Inactivity auto-logout ──────────────────────────────────────────── */
  useEffect(() => {
    if (!authToken) return;

    // Seed timestamp so a fresh login doesn't immediately trigger the check
    const touch = () => localStorage.setItem(IDLE_KEY, Date.now().toString());
    const check = () => {
      const last = parseInt(localStorage.getItem(IDLE_KEY) || "0", 10);
      if (Date.now() - last >= IDLE_MS) handleLogout();
    };

    touch();
    const interval = setInterval(check, 10_000);
    const events = ["mousemove", "mousedown", "keydown", "touchstart", "scroll"];
    events.forEach((e) => window.addEventListener(e, touch, { passive: true }));

    return () => {
      clearInterval(interval);
      events.forEach((e) => window.removeEventListener(e, touch));
    };
  }, [authToken, handleLogout]);

  /* ── Login ───────────────────────────────────────────────────────────── */
  /**
   * handleLogin — authenticate the user.
   *
   * In offline/demo mode (backendOk === false) it sets up a local demo
   * session without making any network calls.
   *
   * @param {string} email
   * @param {string} password
   * @throws {Error} Re-throws API errors so LoginPage can display them
   */
  const handleLogin = useCallback(async (email, password) => {
    if (backendOk === false) {
      // Demo mode — backend is offline
      const demoUser = {
        email,
        first_name: "Alex",
        last_name: "Morgan",
        user_id: "demo",
      };
      setAuthToken("demo-token");
      setAuthUser(demoUser);
      setAccountId("ACC-4821");
      sessionStorage.setItem(STORAGE_TOKEN, "demo-token");
      sessionStorage.setItem(STORAGE_USER, JSON.stringify(demoUser));
      sessionStorage.setItem(STORAGE_ACCOUNT, "ACC-4821");
      onToast?.("DEMO MODE · BACKEND OFFLINE — SHOWING MOCK DATA");
      return { page: "dashboard" };
    }

    // Real authentication
    const res = await api.login(email, password); // throws on failure

    const user = {
      email:      res.email,
      first_name: res.first_name,
      last_name:  res.last_name,
      user_id:    res.user_id,
    };

    setAuthToken(res.access_token);
    setAuthUser(user);
    sessionStorage.setItem(STORAGE_TOKEN, res.access_token);
    sessionStorage.setItem(STORAGE_USER, JSON.stringify(user));

    // Fetch first account (best-effort — non-fatal)
    try {
      const accounts = await api.listAccounts(res.user_id, res.access_token);
      if (accounts.length > 0) {
        setAccountId(accounts[0].account_id);
        sessionStorage.setItem(STORAGE_ACCOUNT, accounts[0].account_id);
      }
    } catch (_) { /* account fetch is optional */ }

    onToast?.(
      `AUTHENTICATION SUCCESSFUL · WELCOME BACK, ${(res.first_name || "").toUpperCase()}`
    );
    return { page: "dashboard" };
  }, [backendOk, onToast]);

  /* ── Context value ───────────────────────────────────────────────────── */
  const value = {
    authToken,
    authUser,
    accountId,
    backendOk,
    handleLogin,
    handleLogout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/**
 * useAuth — consume the AuthContext.
 *
 * Must be called inside a component tree wrapped with <AuthProvider>.
 *
 * @returns {{
 *   authToken:    string|null,
 *   authUser:     object|null,
 *   accountId:    string|null,
 *   backendOk:    boolean|null,
 *   handleLogin:  Function,
 *   handleLogout: Function,
 * }}
 */
export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return ctx;
}

export default AuthContext;
