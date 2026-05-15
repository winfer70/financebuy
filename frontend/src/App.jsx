/**
 * App.jsx — TickerTap root component.
 *
 * Responsibilities:
 *  - Inject global CSS
 *  - Provide AuthContext to the tree via <AuthProvider>
 *  - Manage page routing state
 *  - Manage toast notifications
 *  - Render the authenticated shell (sidebar, topbar, page outlet)
 *    or the appropriate auth page
 *
 * This file is intentionally thin — all business logic lives in context,
 * hooks, and page-level components.
 */

import { useState, useCallback, useEffect } from "react";

/* ── Context ─────────────────────────────────────────────────────────────── */
import { AuthProvider, useAuth } from "./context/AuthContext";
import { CurrencyProvider } from "./context/CurrencyContext";
import { I18nProvider, useI18n } from "./context/I18nContext";
import { QuotesProvider } from "./context/QuotesContext";

/* ── Styles & data ────────────────────────────────────────────────────────── */
import { GLOBAL_CSS } from "./styles/globals";

/* ── Common components ────────────────────────────────────────────────────── */
import { Ic } from "./components/common/Icons";
import { NotificationBell } from "./components/common/NotificationBell";
import {
  ToastContainer,
  Clock,
  Footer,
  TickerStrip,
  useMarketStatus,
} from "./components/common";
import KeyboardShortcutsModal from "./components/common/KeyboardShortcutsModal";
import useKeyboardShortcuts from "./hooks/useKeyboardShortcuts";

/* ── Modal ────────────────────────────────────────────────────────────────── */
import { TxModal } from "./components/modals/TxModal";

/* ── Auth pages ───────────────────────────────────────────────────────────── */
import { LoginPage }          from "./pages/auth/LoginPage";
import { RegisterPage }       from "./pages/auth/RegisterPage";
import { ForgotPasswordPage } from "./pages/auth/ForgotPasswordPage";
import { ResetPasswordPage }  from "./pages/auth/ResetPasswordPage";
import { VerifyEmailPage }          from "./pages/auth/VerifyEmailPage";
import { DeactivatedAccountPage }   from "./pages/auth/DeactivatedAccountPage";
import { TokenActionPage }          from "./pages/auth/TokenActionPage";

/* ── App pages ────────────────────────────────────────────────────────────── */
import { DashboardPage }          from "./pages/DashboardPage";
import { TransactionsPage }       from "./pages/TransactionsPage";
import { OrdersPage }             from "./pages/OrdersPage";
import { ChartsPage }             from "./pages/ChartsPage";
import { ImportPage }             from "./pages/ImportPage";
import { PortfolioManagerPage }   from "./pages/PortfolioManagerPage";
import { NewsPage }               from "./pages/NewsPage";
import { WatchlistPage }          from "./pages/WatchlistPage";
import { LegalPage }              from "./pages/LegalPage";
import { UserGuidePage }          from "./pages/UserGuidePage";
import { SettingsPage }           from "./pages/SettingsPage";
import { FeedbackPage }             from "./pages/FeedbackPage";
import { TradingPage }              from "./pages/TradingPage";
import { MarketplacePage }          from "./pages/MarketplacePage";
import AlertsPage                    from "./pages/AlertsPage";
import LearningPage                  from "./pages/LearningPage";
import ExitPointsPage                from "./pages/ExitPointsPage";
import ResearchPage                  from "./pages/ResearchPage";
import AdminPage                     from "./pages/AdminPage";

/* ── API ─────────────────────────────────────────────────────────────────── */
import api from "./api/client";

/* ═══════════════════════════════════════════════════════════════════════════
   INNER APP — rendered inside AuthProvider so it can call useAuth()
═══════════════════════════════════════════════════════════════════════════ */

/**
 * AppShell — the authenticated application shell.
 * Handles page routing, transaction modal, and toast notifications.
 *
 * Rendered only when the user is authenticated.
 */
function AppShell({ page, setPage, goBack, toasts, addToast, pageParams }) {
  const { authToken, authUser, accountId, handleLogout } = useAuth();
  const { t } = useI18n();
  const [showTxModal,  setShowTxModal]  = useState(false);
  // Read ?symbol= from the URL so /charts?symbol=NVDA works in a new tab
  const [chartSymbol,  setChartSymbol]  = useState(() => {
    const sp = new URLSearchParams(window.location.search);
    return sp.get("symbol")?.toUpperCase() || null;
  });
  const [newsSymbol,   setNewsSymbol]   = useState(null);
  const marketStatus = useMarketStatus();

  /* ── Admin visibility — checked against backend on every token change ── */
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    if (!authToken) {
      /* No token — definitely not an admin */
      setIsAdmin(false);
      return;
    }
    /* Verify admin status; silently treat any error/403 as non-admin */
    api.checkAdmin(authToken)
      .then(() => setIsAdmin(true))
      .catch(() => setIsAdmin(false));
  }, [authToken]);

  /* ── Sidebar collapsed state (persisted to preferences) ──────────── */
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try {
      const prefs = JSON.parse(sessionStorage.getItem("tickertap_preferences") || "null");
      return prefs?.sidebar_collapsed || false;
    } catch { return false; }
  });

  /* ── Keyboard shortcuts modal ─────────────────────────────────────── */
  const [showShortcuts, setShowShortcuts] = useState(false);

  /* Shortcut definitions — "g <key>" navigates to a page; "?" opens help */
  const shortcuts = [
    { key: ["g", "d"], description: "Go to Dashboard",         action: () => setPage("dashboard") },
    { key: ["g", "w"], description: "Go to Watchlist",         action: () => setPage("watchlist") },
    { key: ["g", "p"], description: "Go to Portfolio Manager", action: () => setPage("portfolio-manager") },
    { key: ["g", "t"], description: "Go to Trading AI",        action: () => setPage("trading") },
    { key: ["g", "n"], description: "Go to News",              action: () => setPage("news") },
    { key: ["g", "c"], description: "Go to Charts",            action: () => setPage("charts") },
    { key: "?",        description: "Show keyboard shortcuts", action: () => setShowShortcuts(true) },
  ];
  useKeyboardShortcuts(shortcuts);

  const toggleSidebar = useCallback(() => {
    setSidebarCollapsed(prev => {
      const next = !prev;
      /* Persist to preferences (fire-and-forget) */
      try {
        const prefs = JSON.parse(sessionStorage.getItem("tickertap_preferences") || "{}");
        prefs.sidebar_collapsed = next;
        sessionStorage.setItem("tickertap_preferences", JSON.stringify(prefs));
        api.updatePreferences({ sidebar_collapsed: next }, authToken).catch(() => {});
      } catch { /* non-fatal */ }
      return next;
    });
  }, [authToken]);

  /* ── Transaction submit (creates a real transaction or queues in demo) ── */
  const handleTxSubmit = async (form) => {
    if (!authToken) {
      addToast(
        `TRANSACTION QUEUED (DEMO) · ${form.transaction_type.toUpperCase()} $${parseFloat(form.amount).toFixed(2)}`
      );
      return;
    }
    try {
      const payload = {
        account_id:       accountId || form.account_id,
        transaction_type: form.transaction_type,
        amount:           parseFloat(form.amount),
        currency:         form.currency,
      };
      const result = await api.createTransaction(payload, authToken);
      addToast(
        `TRANSACTION CREATED · ${result.transaction_type.toUpperCase()} $${
          result.amount.toFixed ? result.amount.toFixed(2) : result.amount
        }`
      );
    } catch (err) {
      addToast(`TRANSACTION FAILED · ${err.message}`, true);
    }
  };

  /* ── Navigate to a chart for a specific symbol ─────────────────────── */
  /* Opens in a new browser tab so the user doesn't lose their current
     context in Portfolio Manager or Watchlist. */
  const navigateToChart = (symbol) => {
    window.open(`/charts?symbol=${encodeURIComponent(symbol)}`, "_blank");
  };

  /* ── Navigate to news filtered for a specific ticker ─────────────── */
  const navigateToNews = (symbol) => {
    setNewsSymbol(symbol || null);
    setPage("news");
  };

  /* ── Navigate to Trading AI with a pre-filled symbol ───────────── */
  const navigateToTradeAI = (symbol) => {
    setPage("trading", { symbol: symbol || null });
  };

  /* ── Sidebar navigation items ───────────────────────────────────────── */
  const NAV = [
    { id: "dashboard",        label: t("nav.dashboard"),    Icon: Ic.dashboard    },
    { id: "transactions",     label: t("nav.transactions"), Icon: Ic.transactions },
    { id: "orders",           label: t("nav.orders"),       Icon: Ic.orders       },
    { id: "charts",           label: t("nav.charts"),       Icon: Ic.charts       },
    { id: "news",             label: t("nav.news"),         Icon: Ic.news         },
    { id: "watchlist",         label: t("nav.watchlist"),    Icon: Ic.watchlist    },
    { id: "portfolio-manager",label: t("nav.portfolio"),    Icon: Ic.portfolio    },
    { id: "trading",          label: "TRADING AI",           Icon: Ic.trading      },
    { id: "research",          label: "RESEARCH",             Icon: Ic.charts       },
    { id: "marketplace",       label: "MARKETPLACE",          Icon: Ic.marketplace  },
    { id: "alerts",            label: "ALERTS",               Icon: Ic.bell         },
    { id: "learning",          label: "LEARNING",             Icon: Ic.charts       },
    { id: "exit-points",       label: "EXIT POINTS",          Icon: Ic.orders       },
    { id: "feedback",          label: t("nav.feedback"),     Icon: Ic.feedback     },
    ...(isAdmin ? [{ id: "admin", label: "ADMIN", Icon: Ic.admin }] : []),
  ];

  return (
    <div className="app-shell">
      {/* ── Sidebar ─────────────────────────────────────────────────────── */}
      <aside className={`sidebar${sidebarCollapsed ? " sidebar-collapsed" : ""}`}>
        <div className="sidebar-logo">
          <img src="/logo.png" alt="TickerTap" style={{ width: 32, height: 32, borderRadius: 4, cursor: "pointer" }} onClick={() => setPage("dashboard")} />
          {!sidebarCollapsed && <div className="logo-name" onClick={() => setPage("dashboard")} style={{ cursor: "pointer" }}>TICKER-TAP</div>}
          <button
            className="sidebar-toggle"
            onClick={toggleSidebar}
            title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            style={{
              marginLeft: "auto", background: "none", border: "none",
              color: "var(--muted)", cursor: "pointer", padding: 4,
              display: "flex", alignItems: "center", transition: "color 0.1s",
            }}
            onMouseOver={e => e.currentTarget.style.color = "var(--amber)"}
            onMouseOut={e => e.currentTarget.style.color = "var(--muted)"}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              {sidebarCollapsed
                ? <path d="M13 17l5-5-5-5M6 17l5-5-5-5"/>
                : <path d="M11 17l-5-5 5-5M18 17l-5-5 5-5"/>}
            </svg>
          </button>
        </div>

        <nav className="sidebar-nav">
          {NAV.map((n) => (
            <button
              key={n.id}
              className={`nav-btn${page === n.id ? " active" : ""}`}
              onClick={() => setPage(n.id)}
              title={n.label}
            >
              <n.Icon />
              <span className="nav-label">{n.label}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-bottom">
          {/* User avatar / name */}
          <div
            className="avatar-btn"
            style={{
              width: "100%", borderRadius: 4, padding: "0 10px",
              gap: 10, display: "flex", alignItems: "center", height: 36,
            }}
          >
            <span>
              {authUser
                ? (authUser.first_name?.[0] || "") + (authUser.last_name?.[0] || "")
                : "??"}
            </span>
            <span style={{
              fontFamily: "var(--font-mono)", fontSize: 11,
              color: "var(--amber)", letterSpacing: "0.5px",
            }}>
              {authUser
                ? `${(authUser.first_name || "").toUpperCase()} ${(authUser.last_name?.[0] || "").toUpperCase()}.`
                : "USER"}
            </span>
          </div>

          <button className="nav-btn" onClick={() => setPage("settings")}
            style={page === "settings" ? { color: "var(--amber)" } : {}}
            title={t("nav.settings")}>
            <Ic.gear />
            <span className="nav-label">{t("nav.settings")}</span>
          </button>

          <button className="nav-btn" onClick={handleLogout} title={t("nav.signOut")}>
            <Ic.logout />
            <span className="nav-label">{t("nav.signOut")}</span>
          </button>
        </div>
      </aside>

      {/* Mobile bottom navigation — hidden on desktop via CSS, shown on mobile */}
      <nav className="mobile-bottom-nav">
        {[
          { id: "dashboard",         label: "HOME",   Icon: Ic.dashboard },
          { id: "charts",            label: "CHARTS", Icon: Ic.charts },
          { id: "portfolio-manager", label: "PORT",   Icon: Ic.portfolio },
          { id: "trading",           label: "TRADE",  Icon: Ic.trading },
          { id: "watchlist",         label: "WATCH",  Icon: Ic.watchlist },
          { id: "news",              label: "NEWS",   Icon: Ic.news },
        ].map(({ id, label, Icon }) => (
          <button
            key={id}
            className={`mob-nav-btn${page === id ? " active" : ""}`}
            onClick={() => setPage(id)}
          >
            <Icon />
            <span>{label}</span>
          </button>
        ))}
      </nav>

      {/* ── Main area ───────────────────────────────────────────────────── */}
      <div className="main-area">
        {/* Top bar */}
        <div className="topbar">
          <div className="topbar-breadcrumb">
            <span>TICKER-TAP</span>
            <span className="topbar-sep">/</span>
            <span className="current">{(() => {
                const breadcrumbMap = {
                  dashboard: t("nav.dashboard"),
                  transactions: t("nav.transactions"),
                  orders: t("nav.orders"),
                  charts: t("nav.charts"),
                  news: t("nav.news"),
                  watchlist: t("nav.watchlist"),
                  "portfolio-manager": t("nav.portfolio"),
                  settings: t("nav.settings"),
                  feedback: t("nav.feedback"),
                  guide: t("nav.guide"),
                  import: t("nav.import"),
                  marketplace: "MARKETPLACE",
                  alerts: "ALERTS",
                  learning: "LEARNING",
                  "exit-points": "EXIT POINTS",
                  research: "RESEARCH",
                  admin: "ADMIN",
                };
                if (page.startsWith("legal")) return t("nav.legal");
                return breadcrumbMap[page] || page.toUpperCase();
              })()}</span>
          </div>

          <TickerStrip token={authToken} />

          <div className="topbar-right">
            <div
              className="market-status"
              style={marketStatus.isOpen ? {} : { color: "var(--red)" }}
            >
              <div
                className="market-dot"
                style={marketStatus.isOpen ? {} : { background: "var(--red)" }}
              />
              {marketStatus.isOpen
                ? t("topbar.nyseOpen")
                : `${t("topbar.closed")} · ${t("topbar.opensIn")} ${marketStatus.countdown}`}
            </div>
            <NotificationBell token={authToken} />
            <Clock />
            {/* Keyboard shortcuts help button */}
            <button
              onClick={() => setShowShortcuts(true)}
              title="Keyboard shortcuts (?)"
              style={{
                background: "none", border: "1px solid var(--c-border)", borderRadius: 3,
                color: "var(--c-muted)", cursor: "pointer", fontFamily: "var(--font-mono)",
                fontSize: 11, padding: "2px 7px", lineHeight: 1.4, letterSpacing: ".05em",
              }}
            >?</button>
          </div>
        </div>

        {/* Page outlet — only the active page is rendered */}
        {page === "dashboard"    && (
          <DashboardPage
            onNewTx={() => setShowTxModal(true)}
            token={authToken}
            setPage={setPage}
            onViewChart={navigateToChart}
          />
        )}
        {page === "transactions" && (
          <TransactionsPage
            onNewTx={() => setShowTxModal(true)}
            token={authToken}
            accountId={accountId}
            goBack={goBack}
          />
        )}
        {page === "orders"       && (
          <OrdersPage
            onNewTx={() => setShowTxModal(true)}
            token={authToken}
            accountId={accountId}
            goBack={goBack}
          />
        )}
        {page === "charts"       && (
          <ChartsPage
            initialSymbol={chartSymbol}
            token={authToken}
            goBack={goBack}
          />
        )}
        {page === "news"         && (
          <NewsPage
            token={authToken}
            initialTicker={newsSymbol}
            onViewChart={navigateToChart}
          />
        )}
        {page === "watchlist"    && (
          <WatchlistPage
            token={authToken}
            onViewChart={navigateToChart}
            onViewNews={navigateToNews}
            onTradeAI={navigateToTradeAI}
          />
        )}
        {page === "import"       && (
          <ImportPage
            addToast={addToast}
            token={authToken}
            accountId={accountId}
            goBack={goBack}
          />
        )}
        {page === "portfolio-manager" && (
          <PortfolioManagerPage
            token={authToken}
            onViewChart={navigateToChart}
            onViewNews={navigateToNews}
            onTradeAI={navigateToTradeAI}
            pageParams={pageParams}
          />
        )}
        {page === "trading" && (
          <TradingPage
            token={authToken}
            onViewChart={navigateToChart}
            initialSymbol={pageParams?.symbol}
          />
        )}
        {page === "marketplace" && (
          <MarketplacePage
            token={authToken}
            setPage={setPage}
          />
        )}
        {page === "alerts" && (
          <AlertsPage token={authToken} />
        )}
        {page === "learning" && (
          <LearningPage token={authToken} setPage={setPage} />
        )}
        {page === "exit-points" && (
          <ExitPointsPage token={authToken} />
        )}
        {page === "research" && (
          <ResearchPage token={authToken} onViewChart={navigateToChart} />
        )}
        {page.startsWith("legal") && (
          <LegalPage
            initialTab={
              page === "legal-privacy" ? "privacy"
              : page === "legal-terms" ? "terms"
              : "disclaimer"
            }
            onBack={goBack}
          />
        )}
        {page === "guide" && (
          <UserGuidePage token={authToken} goBack={goBack} />
        )}
        {page === "settings" && (
          <SettingsPage token={authToken} goBack={goBack} onLogout={handleLogout} />
        )}
        {page === "feedback" && (
          <FeedbackPage token={authToken} goBack={goBack} />
        )}
        {page === "admin" && (
          <AdminPage token={authToken} />
        )}

        <Footer onNavigate={setPage} showGuide />
      </div>

      {/* Transaction modal */}
      {showTxModal && (
        <TxModal
          onClose={() => setShowTxModal(false)}
          onSubmit={handleTxSubmit}
        />
      )}

      {/* Keyboard shortcuts modal */}
      <KeyboardShortcutsModal
        isOpen={showShortcuts}
        shortcuts={shortcuts}
        onClose={() => setShowShortcuts(false)}
      />
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   ROOT APP — manages page routing and provides AuthProvider
═══════════════════════════════════════════════════════════════════════════ */

/**
 * App — root component.
 *
 * Injects global styles, manages toast state (so AuthProvider can surface
 * auth toasts), and owns the page-routing state machine.
 */
export default function App() {
  /* ── Toast notifications ──────────────────────────────────────────────── */
  const [toasts, setToasts] = useState([]);

  /**
   * addToast — surface a notification.
   * @param {string}  msg    - message text
   * @param {boolean} [err]  - true for error styling
   */
  const addToast = useCallback((msg, err = false) => {
    const id = Date.now();
    setToasts((t) => [...t, { id, msg, err }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3200);
  }, []);

  /* ── Page routing ─────────────────────────────────────────────────────── */
  const [page, setPageRaw] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("reset_token")) return "reset-password";
    if (params.get("action") && params.get("token")) return "token-action";

    /* Derive initial page from URL pathname when no special query params */
    const KNOWN_PAGES = new Set([
      "dashboard", "transactions", "orders", "charts", "news", "watchlist",
      "portfolio-manager", "trading", "marketplace", "alerts", "learning", "exit-points", "research", "feedback", "import", "settings", "guide", "admin",
      "legal", "legal-privacy", "legal-terms", "legal-disclaimer",
      "login", "register", "forgot-password", "reset-password",
      "verify-email", "token-action", "deactivated",
    ]);
    const slug = window.location.pathname.replace(/^\//, "").replace(/\/$/, "");
    if (slug && KNOWN_PAGES.has(slug)) return slug;

    return sessionStorage.getItem("tickertap_token") ? "dashboard" : "login";
  });
  const [pageParams,  setPageParams]  = useState(null);

  /**
   * setPage — navigate to a new page, pushing the current page onto history.
   * Auth-gated pages use replaceState to avoid polluting browser history.
   * @param {string}      next   - target page id
   * @param {Object|null} params - optional parameters to pass to the target page
   */
  const AUTH_GATED_PAGES = new Set(["token-action", "verify-email", "deactivated"]);
  const setPage = useCallback((next, params = null) => {
    setPageParams(params);
    setPageRaw(next);
    /* Sync the browser URL bar so back/forward buttons work */
    if (AUTH_GATED_PAGES.has(next)) {
      window.history.replaceState({ page: next }, "", `/${next}`);
    } else {
      window.history.pushState({ page: next }, "", `/${next}`);
    }
  }, []);

  /**
   * goBack — navigate to the previous page using the browser history stack.
   */
  const goBack = useCallback(() => {
    window.history.back();
  }, []);

  /* ── Sync React page state with browser back/forward buttons ────────── */
  useEffect(() => {
    /**
     * handlePopState — fired when the user clicks back/forward in the browser.
     * Reads the page id from the history state and updates React state directly
     * (bypassing setPage to avoid pushing another history entry).
     * @param {PopStateEvent} e - browser popstate event
     */
    const handlePopState = (e) => {
      const pg = e.state?.page || "dashboard";
      setPageRaw(pg);
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  /* ── Password-reset token from URL ───────────────────────────────────── */
  const [resetToken] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("reset_token") || null;
  });

  return (
    <>
      {/* Inject global Bloomberg-inspired design system CSS */}
      <style>{GLOBAL_CSS}</style>

      {/*
        AuthProvider owns all auth state (token, user, accountId, login,
        logout, session-expiry, inactivity timer).
        onToast wires auth events (login success, logout) into the toast stack.
      */}
      <AuthProvider onToast={addToast}>
        <PageRouter
          page={page}
          setPage={setPage}
          goBack={goBack}
          resetToken={resetToken}
          toasts={toasts}
          addToast={addToast}
          pageParams={pageParams}
        />
      </AuthProvider>

      <ToastContainer toasts={toasts} />
    </>
  );
}

/* ── Page router (consumes AuthContext) ───────────────────────────────────── */
/**
 * PageRouter — decides which top-level page/screen to render.
 * Lives inside <AuthProvider> so it can read auth state.
 */
function PageRouter({ page, setPage, goBack, resetToken, toasts, addToast, pageParams }) {
  const { authToken, authUser, backendOk, handleLogin, handleLogout, emailNotVerified, unverifiedEmail, accountDeactivated, deactivatedEmail, deletionScheduledAt } = useAuth();

  /* ── Derive initial currency from the authenticated user's preferences ── */
  const initialCurrency = authUser?.preferences?.currency || "USD";
  const [initialLanguage] = useState(() => {
    try {
      const prefs = JSON.parse(sessionStorage.getItem("tickertap_preferences") || "null");
      return prefs?.language || "en";
    } catch { return "en"; }
  });

  /* ── Wrap handleLogin to navigate on success ── */
  const onLogin = useCallback(async (email, password) => {
    try {
      const result = await handleLogin(email, password);
      setPage(result?.page || "dashboard");
    } catch (err) {
      /* If email not verified, redirect to verify page */
      if (err.message === "email_not_verified" || err.detail === "email_not_verified") {
        setPage("verify-email");
        return;
      }
      throw err; /* re-throw for LoginPage to display */
    }
  }, [handleLogin, setPage]);

  /* ── Auth / public pages ─────────────────────────────────────────────── */
  if (page === "forgot-password") {
    return (
      <ForgotPasswordPage
        onBack={() => setPage("login")}
        backendOk={backendOk}
        onNavigate={setPage}
      />
    );
  }

  if (page === "reset-password") {
    return (
      <ResetPasswordPage
        resetToken={resetToken}
        onBack={() => {
          window.history.replaceState({}, "", "/");
          setPage("login");
        }}
        onSuccess={() => {
          window.history.replaceState({}, "", "/");
          setPage("login");
          addToast("PASSWORD UPDATED · PLEASE SIGN IN");
        }}
        onNavigate={setPage}
      />
    );
  }

  if (page === "register") {
    return (
      <RegisterPage
        onLogin={onLogin}
        onBack={() => setPage("login")}
        backendOk={backendOk}
        onNavigate={setPage}
      />
    );
  }

  /* Legal pages — accessible without authentication */
  if (page.startsWith("legal") && !authToken) {
    const tab = page === "legal-privacy" ? "privacy"
              : page === "legal-terms"   ? "terms"
              : "disclaimer";
    return (
      <LegalPage
        initialTab={tab}
        onBack={() => setPage("login")}
        standalone
      />
    );
  }

  /* Token action pages (email links with ?token=xxx&action=xxx) */
  if (page === "token-action") {
    return (
      <TokenActionPage
        onComplete={() => setPage("login")}
        onNavigate={setPage}
      />
    );
  }

  /* Email verification page (shown after registration) */
  if (page === "verify-email" || (emailNotVerified && page !== "login")) {
    return (
      <VerifyEmailPage
        email={unverifiedEmail || ""}
        onBack={() => setPage("login")}
        backendOk={backendOk}
        onNavigate={setPage}
      />
    );
  }

  /* Deactivated account page */
  if (page === "deactivated" || (accountDeactivated && authToken)) {
    return (
      <DeactivatedAccountPage
        email={deactivatedEmail || ""}
        deletionDate={deletionScheduledAt}
        onLogout={() => { handleLogout(); setPage("login"); }}
        backendOk={backendOk}
        onNavigate={setPage}
      />
    );
  }

  if (page === "login" || !authToken) {
    return (
      <LoginPage
        onLogin={onLogin}
        onRegister={() => setPage("register")}
        onForgotPassword={() => setPage("forgot-password")}
        backendOk={backendOk}
        onNavigate={setPage}
      />
    );
  }

  /* ── Authenticated shell ─────────────────────────────────────────────── */
  return (
    <I18nProvider initialLanguage={initialLanguage}>
      <CurrencyProvider token={authToken} initialCurrency={initialCurrency}>
        <QuotesProvider token={authToken}>
          <AppShell
            page={page}
            setPage={setPage}
            goBack={goBack}
            toasts={toasts}
            addToast={addToast}
            pageParams={pageParams}
          />
        </QuotesProvider>
      </CurrencyProvider>
    </I18nProvider>
  );
}
