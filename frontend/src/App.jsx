/**
 * App.jsx — TickerTap root component.
 *
 * Responsibilities:
 *  - Inject global CSS
 *  - Provide AuthContext to the tree via <AuthProvider>
 *  - Manage page routing state and navigation history
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

/* ── Styles & data ────────────────────────────────────────────────────────── */
import { GLOBAL_CSS } from "./styles/globals";

/* ── Common components ────────────────────────────────────────────────────── */
import { Ic } from "./components/common/Icons";
import {
  ToastContainer,
  Clock,
  Footer,
  TickerStrip,
  useMarketStatus,
} from "./components/common";

/* ── Modal ────────────────────────────────────────────────────────────────── */
import { TxModal } from "./components/modals/TxModal";

/* ── Auth pages ───────────────────────────────────────────────────────────── */
import { LoginPage }          from "./pages/auth/LoginPage";
import { RegisterPage }       from "./pages/auth/RegisterPage";
import { ForgotPasswordPage } from "./pages/auth/ForgotPasswordPage";
import { ResetPasswordPage }  from "./pages/auth/ResetPasswordPage";

/* ── App pages ────────────────────────────────────────────────────────────── */
import { DashboardPage }    from "./pages/DashboardPage";
import { TransactionsPage } from "./pages/TransactionsPage";
import { HoldingsPage }     from "./pages/HoldingsPage";
import { OrdersPage }       from "./pages/OrdersPage";
import { ChartsPage }       from "./pages/ChartsPage";
import { ImportPage }       from "./pages/ImportPage";

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
function AppShell({ page, setPage, goBack, toasts, addToast }) {
  const { authToken, authUser, accountId, handleLogout } = useAuth();
  const [showTxModal,  setShowTxModal]  = useState(false);
  const [chartSymbol,  setChartSymbol]  = useState(null);
  const marketStatus = useMarketStatus();

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
  const navigateToChart = (symbol) => {
    setChartSymbol(symbol);
    setPage("charts");
  };

  /* ── Sidebar navigation items ───────────────────────────────────────── */
  const NAV = [
    { id: "dashboard",    label: "DASHBOARD",    Icon: Ic.dashboard    },
    { id: "transactions", label: "TRANSACTIONS", Icon: Ic.transactions },
    { id: "holdings",     label: "HOLDINGS",     Icon: Ic.holdings     },
    { id: "orders",       label: "ORDERS",       Icon: Ic.orders       },
    { id: "charts",       label: "CHARTS",       Icon: Ic.charts       },
    { id: "import",       label: "IMPORT",       Icon: Ic.import       },
  ];

  return (
    <div className="app-shell">
      {/* ── Sidebar ─────────────────────────────────────────────────────── */}
      <aside className="sidebar">
        <div className="sidebar-logo" onClick={() => setPage("dashboard")}>
          <div className="logo-glyph">TT</div>
          <div className="logo-name">TICKER-TAP</div>
        </div>

        <nav className="sidebar-nav">
          {NAV.map((n) => (
            <button
              key={n.id}
              className={`nav-btn${page === n.id ? " active" : ""}`}
              onClick={() => setPage(n.id)}
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

          <button className="nav-btn" onClick={handleLogout}>
            <Ic.logout />
            <span className="nav-label">SIGN OUT</span>
          </button>
        </div>
      </aside>

      {/* ── Main area ───────────────────────────────────────────────────── */}
      <div className="main-area">
        {/* Top bar */}
        <div className="topbar">
          <div className="topbar-breadcrumb">
            <span>TICKER-TAP</span>
            <span className="topbar-sep">/</span>
            <span className="current">{page.toUpperCase()}</span>
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
                ? "NYSE OPEN"
                : `CLOSED · OPENS IN ${marketStatus.countdown}`}
            </div>
            <Clock />
          </div>
        </div>

        {/* Page outlet — only the active page is rendered */}
        {page === "dashboard"    && (
          <DashboardPage
            onNewTx={() => setShowTxModal(true)}
            token={authToken}
            accountId={accountId}
            setPage={setPage}
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
        {page === "holdings"     && (
          <HoldingsPage
            onNewTx={() => setShowTxModal(true)}
            onViewChart={navigateToChart}
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
        {page === "import"       && (
          <ImportPage
            addToast={addToast}
            token={authToken}
            accountId={accountId}
            goBack={goBack}
          />
        )}

        <Footer />
      </div>

      {/* Transaction modal */}
      {showTxModal && (
        <TxModal
          onClose={() => setShowTxModal(false)}
          onSubmit={handleTxSubmit}
        />
      )}
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
    return sessionStorage.getItem("fb_token") ? "dashboard" : "login";
  });
  const [pageHistory, setPageHistory] = useState([]);

  /**
   * setPage — navigate to a new page, pushing the current page onto history.
   * @param {string} next - target page id
   */
  const setPage = useCallback((next) => {
    setPageRaw((prev) => {
      setPageHistory((h) => [...h.slice(-9), prev]);
      return next;
    });
  }, []);

  /**
   * goBack — navigate to the previous page, or dashboard if history is empty.
   */
  const goBack = useCallback(() => {
    setPageHistory((h) => {
      const copy = [...h];
      const prev = copy.pop() || "dashboard";
      setPageRaw(prev);
      return copy;
    });
  }, []);

  /* ── Password-reset token from URL ───────────────────────────────────── */
  const [resetToken] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("reset_token") || null;
  });

  /* ── When auth succeeds, navigate to dashboard ────────────────────────── */
  const handleAuthSuccess = useCallback(() => setPage("dashboard"), [setPage]);

  return (
    <>
      {/* Inject global Bloomberg-inspired design system CSS */}
      <style>{GLOBAL_CSS}</style>

      {/*
        AuthProvider owns all auth state (token, user, accountId, login,
        logout, session-expiry, inactivity timer).
        onToast wires auth events (login success, logout) into the toast stack.
        onNavigate lets AuthProvider redirect to dashboard after a successful login.
      */}
      <AuthProvider onToast={addToast} onNavigate={handleAuthSuccess}>
        <PageRouter
          page={page}
          setPage={setPage}
          goBack={goBack}
          resetToken={resetToken}
          toasts={toasts}
          addToast={addToast}
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
function PageRouter({ page, setPage, goBack, resetToken, toasts, addToast }) {
  const { authToken, backendOk, handleLogin } = useAuth();

  /* ── Wrap handleLogin to navigate on success ── */
  const onLogin = useCallback(async (email, password) => {
    await handleLogin(email, password);
    setPage("dashboard");
  }, [handleLogin, setPage]);

  /* ── Auth / public pages ─────────────────────────────────────────────── */
  if (page === "forgot-password") {
    return (
      <ForgotPasswordPage
        onBack={() => setPage("login")}
        backendOk={backendOk}
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
      />
    );
  }

  if (page === "register") {
    return (
      <RegisterPage
        onLogin={onLogin}
        onBack={() => setPage("login")}
        backendOk={backendOk}
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
      />
    );
  }

  /* ── Authenticated shell ─────────────────────────────────────────────── */
  return (
    <AppShell
      page={page}
      setPage={setPage}
      goBack={goBack}
      toasts={toasts}
      addToast={addToast}
    />
  );
}
