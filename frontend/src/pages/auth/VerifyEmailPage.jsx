/**
 * VerifyEmailPage.jsx — Shown after registration before email verification.
 *
 * Displays a "check your email" message with the registered address,
 * a button to resend the verification email (rate-limited to once per 60s),
 * and a link back to login. Also provides a minimal bug report form for
 * activation issues (accessible to unauthenticated users).
 *
 * Props:
 *   @param {string}   email     - The email address used during registration
 *   @param {Function} onBack    - Navigate back to login
 *   @param {boolean}  backendOk - Backend health status for indicator display
 *   @param {Function} onNavigate - Navigation callback for legal links
 */

import { useState, useCallback } from "react";
import api from "../../api/client";
import { Ic } from "../../components/common/Icons";
import { LegalLinks } from "../../components/common";

export function VerifyEmailPage({ email, onBack, backendOk, onNavigate }) {
  /* ── Resend state ─────────────────────────────────────────────────────── */
  const [resending, setResending] = useState(false);
  const [resendMsg, setResendMsg] = useState(null);
  const [cooldown, setCooldown]   = useState(0);

  /* ── Bug report state ───────────────────────────────────────────────── */
  const [showBugForm, setShowBugForm]   = useState(false);
  const [bugSubject, setBugSubject]     = useState("");
  const [bugBody, setBugBody]           = useState("");
  const [bugSubmitting, setBugSubmitting] = useState(false);
  const [bugSubmitted, setBugSubmitted] = useState(false);
  const [bugError, setBugError]         = useState(null);

  /**
   * handleResend — resend the verification email and start a 60-second cooldown.
   * Calls api.resendVerification(email) and manages loading + messages.
   */
  const handleResend = useCallback(async () => {
    if (cooldown > 0 || resending) return;
    setResending(true);
    setResendMsg(null);
    try {
      await api.resendVerification(email);
      setResendMsg("VERIFICATION EMAIL SENT");
      /* Start 60-second cooldown */
      setCooldown(60);
      const interval = setInterval(() => {
        setCooldown(prev => {
          if (prev <= 1) { clearInterval(interval); return 0; }
          return prev - 1;
        });
      }, 1000);
    } catch (err) {
      setResendMsg(err.message || "FAILED TO SEND");
    } finally {
      setResending(false);
    }
  }, [email, cooldown, resending]);

  /**
   * handleBugSubmit — submits an activation bug report as an unauthenticated user.
   * Uses report_type "activation_bug" and includes the reporter_email field.
   */
  const handleBugSubmit = useCallback(async () => {
    if (!bugSubject.trim() || !bugBody.trim()) return;
    setBugSubmitting(true);
    setBugError(null);
    try {
      await api.submitReport({
        report_type: "activation_bug",
        subject: bugSubject.trim(),
        body: bugBody.trim(),
        reporter_email: email,
      });
      setBugSubmitted(true);
    } catch (err) {
      setBugError(err.message || "Failed to submit report.");
    } finally {
      setBugSubmitting(false);
    }
  }, [bugSubject, bugBody, email]);

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
            We sent a verification link to your email address. Please check your inbox
            (and spam folder) and click the link to activate your account.
          </p>
          <p>
            Once verified, you can sign in and start using the platform immediately.
          </p>
        </div>
        <div className="login-divider" />
      </div>

      {/* Right form panel */}
      <div className="login-right">
        <div style={{ textAlign: "center", marginBottom: 32 }}>
          <div style={{
            fontFamily: "var(--font-disp)", fontSize: 32, color: "var(--bright)",
            letterSpacing: 1, marginBottom: 8,
          }}>
            CHECK YOUR EMAIL
          </div>
          <div style={{
            fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--muted)",
            marginBottom: 4,
          }}>
            Verification link sent to:
          </div>
          <div style={{
            fontFamily: "var(--font-mono)", fontSize: 14, color: "var(--amber)",
            fontWeight: 600, letterSpacing: 0.5,
          }}>
            {email}
          </div>
        </div>

        {/* Resend button */}
        <button
          className="btn btn-amber login-btn-full"
          onClick={handleResend}
          disabled={cooldown > 0 || resending}
          style={{
            opacity: (cooldown > 0 || resending) ? 0.4 : 1,
            cursor: (cooldown > 0 || resending) ? "default" : "pointer",
            marginBottom: 12,
          }}
        >
          {resending
            ? <span className="loading-pulse">SENDING...</span>
            : cooldown > 0
              ? `RESEND AVAILABLE IN ${cooldown}s`
              : "RESEND VERIFICATION EMAIL"}
        </button>

        {/* Resend feedback message */}
        {resendMsg && (
          <div style={{
            fontFamily: "var(--font-mono)", fontSize: 11,
            color: resendMsg.includes("FAILED") ? "var(--red)" : "var(--green)",
            textAlign: "center", marginBottom: 12,
          }}>
            {resendMsg}
          </div>
        )}

        {/* Back to login */}
        <div className="login-footer-links" style={{ justifyContent: "center", marginBottom: 24 }}>
          <span className="login-link" onClick={onBack}>← BACK TO SIGN IN</span>
        </div>

        {/* Divider */}
        <div style={{
          height: 1, background: "var(--border)", margin: "0 0 16px",
        }} />

        {/* Bug report section */}
        {!showBugForm && !bugSubmitted && (
          <div style={{ textAlign: "center" }}>
            <span
              className="login-link"
              onClick={() => setShowBugForm(true)}
              style={{ fontSize: 10 }}
            >
              Having trouble? Report an activation issue →
            </span>
          </div>
        )}

        {showBugForm && !bugSubmitted && (
          <div style={{
            background: "var(--bg3)", border: "1px solid var(--border)",
            borderRadius: 4, padding: 16, display: "flex", flexDirection: "column", gap: 12,
          }}>
            <div style={{
              fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 500,
              color: "var(--amber)", letterSpacing: 1,
            }}>
              REPORT ACTIVATION ISSUE
            </div>

            {bugError && (
              <div style={{
                fontFamily: "var(--font-mono)", fontSize: 11,
                color: "var(--red)", padding: "6px 10px",
                background: "rgba(240,68,56,0.06)", border: "1px solid rgba(240,68,56,0.2)",
                borderRadius: 2,
              }}>
                {bugError}
              </div>
            )}

            <div className="form-field">
              <label className="form-label">SUBJECT</label>
              <input
                className="form-control"
                type="text"
                placeholder="Brief description..."
                value={bugSubject}
                onChange={e => setBugSubject(e.target.value)}
                maxLength={200}
              />
            </div>

            <div className="form-field">
              <label className="form-label">DESCRIPTION</label>
              <textarea
                className="form-control"
                placeholder="What happened? What did you expect?"
                value={bugBody}
                onChange={e => setBugBody(e.target.value)}
                maxLength={2000}
                style={{ minHeight: 80, resize: "vertical" }}
              />
            </div>

            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button
                className="btn btn-ghost"
                onClick={() => { setShowBugForm(false); setBugSubject(""); setBugBody(""); setBugError(null); }}
                style={{ fontSize: 10, padding: "5px 12px" }}
              >
                CANCEL
              </button>
              <button
                className="btn btn-amber"
                onClick={handleBugSubmit}
                disabled={!bugSubject.trim() || !bugBody.trim() || bugSubmitting}
                style={{
                  fontSize: 10, padding: "5px 12px",
                  opacity: (!bugSubject.trim() || !bugBody.trim() || bugSubmitting) ? 0.4 : 1,
                }}
              >
                {bugSubmitting ? "SUBMITTING..." : "SUBMIT"}
              </button>
            </div>
          </div>
        )}

        {bugSubmitted && (
          <div style={{
            textAlign: "center", fontFamily: "var(--font-mono)", fontSize: 11,
            color: "var(--green)", padding: "12px 0",
          }}>
            <Ic.check /> Report submitted. We'll look into it.
          </div>
        )}

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
