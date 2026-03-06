/**
 * DeactivatedAccountPage.jsx — Shown when a deactivated user logs in.
 *
 * Displays the account deactivation notice with an option to request
 * reactivation via email link. If deletion is scheduled, shows the
 * countdown date and advises the user to reactivate before that date.
 *
 * Props:
 *   @param {string}      email        - The user's email address
 *   @param {string|null} deletionDate - ISO-8601 date of scheduled permanent deletion
 *   @param {Function}    onLogout     - Sign out and return to login
 *   @param {boolean}     backendOk    - Backend health status
 *   @param {Function}    onNavigate   - Navigation callback for legal links
 */

import { useState, useCallback } from "react";
import api from "../../api/client";
import { Ic } from "../../components/common/Icons";
import { LegalLinks } from "../../components/common";

export function DeactivatedAccountPage({ email, deletionDate, onLogout, backendOk, onNavigate }) {
  /* ── Reactivation request state ───────────────────────────────────────── */
  const [requesting, setRequesting] = useState(false);
  const [requestMsg, setRequestMsg] = useState(null);
  const [cooldown, setCooldown]     = useState(0);

  /**
   * formatDeletionDate — formats the ISO deletion date for display.
   * @param {string} iso - ISO-8601 date string
   * @returns {string} Formatted date like "Mar 15, 2026"
   */
  const formatDeletionDate = (iso) => {
    try {
      return new Date(iso).toLocaleDateString("en-US", {
        year: "numeric", month: "short", day: "numeric",
      });
    } catch { return iso; }
  };

  /**
   * handleRequestReactivation — sends a reactivation email link and starts cooldown.
   * Calls api.requestReactivation(email) and disables the button for 60s.
   */
  const handleRequestReactivation = useCallback(async () => {
    if (cooldown > 0 || requesting) return;
    setRequesting(true);
    setRequestMsg(null);
    try {
      await api.requestReactivation(email);
      setRequestMsg("REACTIVATION LINK SENT — CHECK YOUR EMAIL");
      setCooldown(60);
      const interval = setInterval(() => {
        setCooldown(prev => {
          if (prev <= 1) { clearInterval(interval); return 0; }
          return prev - 1;
        });
      }, 1000);
    } catch (err) {
      setRequestMsg(err.message || "FAILED TO SEND REQUEST");
    } finally {
      setRequesting(false);
    }
  }, [email, cooldown, requesting]);

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
        <div style={{
          fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--muted)",
          maxWidth: 400, lineHeight: 1.7,
        }}>
          <p style={{ marginBottom: 16 }}>
            Your account has been deactivated. All your data is preserved and you
            can reactivate at any time by requesting a reactivation link.
          </p>
          {deletionDate && (
            <p style={{ color: "var(--red)" }}>
              Your account is scheduled for permanent deletion on{" "}
              <strong style={{ color: "var(--bright)" }}>{formatDeletionDate(deletionDate)}</strong>.
              Reactivate before this date to prevent data loss.
            </p>
          )}
        </div>
        <div className="login-divider" />
      </div>

      {/* Right form panel */}
      <div className="login-right">
        <div style={{ textAlign: "center", marginBottom: 32 }}>
          <div style={{
            fontFamily: "var(--font-disp)", fontSize: 32, color: "var(--red)",
            letterSpacing: 1, marginBottom: 8,
          }}>
            ACCOUNT DEACTIVATED
          </div>
          <div style={{
            fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--muted)",
            marginBottom: 4,
          }}>
            Account:
          </div>
          <div style={{
            fontFamily: "var(--font-mono)", fontSize: 14, color: "var(--amber)",
            fontWeight: 600, letterSpacing: 0.5,
          }}>
            {email}
          </div>
        </div>

        {/* Deletion warning banner */}
        {deletionDate && (
          <div style={{
            background: "rgba(240,68,56,0.06)", border: "1px solid rgba(240,68,56,0.2)",
            borderRadius: 4, padding: "12px 16px", marginBottom: 16,
            fontFamily: "var(--font-mono)", fontSize: 11,
          }}>
            <div style={{ color: "var(--red)", fontWeight: 600, marginBottom: 4, letterSpacing: 0.5 }}>
              DELETION SCHEDULED
            </div>
            <div style={{ color: "var(--muted)" }}>
              Permanent deletion on {formatDeletionDate(deletionDate)}.
              Reactivate your account to cancel the deletion and restore full access.
            </div>
          </div>
        )}

        {/* Request reactivation button */}
        <button
          className="btn btn-amber login-btn-full"
          onClick={handleRequestReactivation}
          disabled={cooldown > 0 || requesting}
          style={{
            opacity: (cooldown > 0 || requesting) ? 0.4 : 1,
            cursor: (cooldown > 0 || requesting) ? "default" : "pointer",
            marginBottom: 12,
          }}
        >
          {requesting
            ? <span className="loading-pulse">SENDING...</span>
            : cooldown > 0
              ? `RESEND IN ${cooldown}s`
              : "REQUEST REACTIVATION"}
        </button>

        {/* Feedback message */}
        {requestMsg && (
          <div style={{
            fontFamily: "var(--font-mono)", fontSize: 11,
            color: requestMsg.includes("FAILED") ? "var(--red)" : "var(--green)",
            textAlign: "center", marginBottom: 12,
          }}>
            {requestMsg}
          </div>
        )}

        {/* Sign out */}
        <button
          className="btn btn-outline login-btn-full"
          onClick={onLogout}
          style={{ marginTop: 8 }}
        >
          <Ic.logout /> SIGN OUT
        </button>

        {/* Security indicators */}
        <div className="login-security">
          <div className="security-item"><Ic.lock /> TLS 1.3 Encrypted</div>
          <div className="security-item"><Ic.shield /> SOC 2 Compliant</div>
          <div className="security-item" style={{
            color: backendOk === false ? "var(--amber)" : "var(--green)",
            display: "flex", alignItems: "center", gap: 4,
          }}>
            <span style={{
              width: 5, height: 5, borderRadius: "50%",
              background: backendOk === false ? "var(--amber)" : "var(--green)",
              display: "inline-block",
            }} />
            {backendOk === null ? "Checking API..." : backendOk ? "API Connected" : "Demo Mode (API Offline)"}
          </div>
        </div>
        {onNavigate && <LegalLinks onNavigate={onNavigate} />}
      </div>
    </div>
  );
}
