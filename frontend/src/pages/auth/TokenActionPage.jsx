/**
 * TokenActionPage.jsx — Handles all email-link token actions.
 *
 * Reads `token` and `action` query parameters from the URL and calls
 * the corresponding API endpoint:
 *   - verify-email    → api.verifyEmail(token)
 *   - reactivate      → api.reactivateAccount(token)
 *   - confirm-email   → api.confirmEmailChange(token)
 *   - cancel-deletion → api.cancelDeletion(token)
 *
 * Displays a processing spinner, then a success or error message with
 * a link to navigate to the login page.
 *
 * Props:
 *   @param {Function} onComplete - Navigate to login or dashboard after action
 *   @param {Function} onNavigate - Navigation callback for legal links
 */

import { useState, useEffect } from "react";
import api from "../../api/client";
import { Ic } from "../../components/common/Icons";
import { LegalLinks } from "../../components/common";

/* ── Action configuration map ──────────────────────────────────────────── */
const ACTIONS = {
  "verify-email": {
    label: "EMAIL VERIFICATION",
    successTitle: "EMAIL VERIFIED",
    successMessage: "Your email has been verified successfully. You can now sign in to your account.",
    call: (token) => api.verifyEmail(token),
  },
  "reactivate": {
    label: "ACCOUNT REACTIVATION",
    successTitle: "ACCOUNT REACTIVATED",
    successMessage: "Your account has been reactivated. You can now sign in and use all features.",
    call: (token) => api.reactivateAccount(token),
  },
  "confirm-email": {
    label: "EMAIL CHANGE",
    successTitle: "EMAIL UPDATED",
    successMessage: "Your email address has been updated successfully. Please sign in with your new email.",
    call: (token) => api.confirmEmailChange(token),
  },
  "cancel-deletion": {
    label: "CANCEL DELETION",
    successTitle: "DELETION CANCELLED",
    successMessage: "Account deletion has been cancelled. Your account has been reactivated and all data is preserved.",
    call: (token) => api.cancelDeletion(token),
  },
};

export function TokenActionPage({ onComplete, onNavigate }) {
  const [status, setStatus]   = useState("processing"); /* processing | success | error */
  const [errMsg, setErrMsg]   = useState(null);
  const [action, setAction]   = useState(null);

  /* ── Parse URL params and execute the token action on mount ──────────── */
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const tokenVal = params.get("token");
    const actionVal = params.get("action");
    const config = ACTIONS[actionVal];

    setAction(config || null);

    if (!tokenVal || !config) {
      setStatus("error");
      setErrMsg("Invalid or missing token link. Please check your email and try again.");
      return;
    }

    let cancelled = false;

    (async () => {
      try {
        await config.call(tokenVal);
        if (!cancelled) setStatus("success");
      } catch (err) {
        if (!cancelled) {
          setStatus("error");
          setErrMsg(err.message || "Token action failed. The link may have expired.");
        }
      }
    })();

    return () => { cancelled = true; };
  }, []);

  /**
   * handleContinue — cleans up URL params and navigates to login.
   */
  const handleContinue = () => {
    window.history.replaceState({}, "", "/");
    onComplete();
  };

  return (
    <div className="login-wrap">
      <div className="login-grid-bg" />
      <div className="login-glow" />

      {/* Left branding panel */}
      <div className="login-left">
        <div className="login-brand">
          <div className="login-brand-mark">TICKER-TAP</div>
          <div className="login-brand-sub">Professional Investment Terminal · v4.2</div>
        </div>
        <div className="login-divider" />
      </div>

      {/* Right content panel */}
      <div className="login-right">
        <div style={{ textAlign: "center" }}>
          {/* Header */}
          <div style={{
            fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 500,
            color: "var(--muted)", letterSpacing: 1.5, marginBottom: 24,
          }}>
            {action?.label || "TOKEN ACTION"}
          </div>

          {/* Processing state */}
          {status === "processing" && (
            <div style={{ padding: "48px 0" }}>
              <div className="loading-pulse" style={{
                fontFamily: "var(--font-mono)", fontSize: 14, color: "var(--amber)",
                letterSpacing: 1,
              }}>
                PROCESSING...
              </div>
              <div style={{
                fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--muted)",
                marginTop: 12,
              }}>
                Please wait while we verify your request.
              </div>
            </div>
          )}

          {/* Success state */}
          {status === "success" && (
            <div style={{ padding: "32px 0" }}>
              <div style={{ color: "var(--green)", marginBottom: 16 }}>
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M8 12l3 3 5-5" />
                </svg>
              </div>
              <div style={{
                fontFamily: "var(--font-disp)", fontSize: 28, color: "var(--bright)",
                letterSpacing: 1, marginBottom: 12,
              }}>
                {action?.successTitle || "SUCCESS"}
              </div>
              <div style={{
                fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--muted)",
                lineHeight: 1.6, maxWidth: 320, margin: "0 auto 24px",
              }}>
                {action?.successMessage || "Action completed successfully."}
              </div>
              <button className="btn btn-amber login-btn-full" onClick={handleContinue}>
                CONTINUE TO SIGN IN
              </button>
            </div>
          )}

          {/* Error state */}
          {status === "error" && (
            <div style={{ padding: "32px 0" }}>
              <div style={{ color: "var(--red)", marginBottom: 16 }}>
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M15 9l-6 6M9 9l6 6" />
                </svg>
              </div>
              <div style={{
                fontFamily: "var(--font-disp)", fontSize: 28, color: "var(--bright)",
                letterSpacing: 1, marginBottom: 12,
              }}>
                ACTION FAILED
              </div>
              <div style={{
                fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--muted)",
                lineHeight: 1.6, maxWidth: 320, margin: "0 auto",
              }}>
                {errMsg}
              </div>
              <button
                className="btn btn-outline login-btn-full"
                onClick={handleContinue}
                style={{ marginTop: 24 }}
              >
                BACK TO SIGN IN
              </button>
            </div>
          )}
        </div>

        {/* Security + legal */}
        <div className="login-security" style={{ marginTop: "auto" }}>
          <div className="security-item"><Ic.lock /> TLS 1.3 Encrypted</div>
          <div className="security-item"><Ic.shield /> SOC 2 Compliant</div>
        </div>
        {onNavigate && <LegalLinks onNavigate={onNavigate} />}
      </div>
    </div>
  );
}
