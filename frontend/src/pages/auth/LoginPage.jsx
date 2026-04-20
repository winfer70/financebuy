/**
 * Login Page
 *
 * Renders the login screen with a two-panel layout:
 *   - Left panel: brand identity and feature highlights for TickerTap.
 *   - Right panel: sign-in form with email/password, password visibility
 *     toggle, error display, and security status indicators.
 *
 * The left panel showcases key platform capabilities (real-time data,
 * portfolio management, watchlists, AI news, security, and i18n) using
 * a clean bullet list instead of mock statistics.
 */

import { useState } from "react";
import { Ic } from "../../components/common/Icons";
import { LegalLinks } from "../../components/common";

// Demo credentials are supplied via build-time env vars (VITE_DEMO_EMAIL /
// VITE_DEMO_PWD).  Both default to empty string so the form starts blank in
// production builds where the vars are not set.  Never hardcode credentials
// in source — they end up in the production bundle and version history.
const DEMO_EMAIL = import.meta.env.VITE_DEMO_EMAIL || "";
const DEMO_PWD   = import.meta.env.VITE_DEMO_PWD   || "";

export function LoginPage({ onLogin, onRegister, onForgotPassword, backendOk, onNavigate }) {
  const [email, setEmail] = useState(DEMO_EMAIL);
  const [pwd, setPwd] = useState(DEMO_PWD);
  const [show, setShow] = useState(false);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  const handleLogin = async () => {
    if (!email) { setErr("EMAIL REQUIRED"); return; }
    if (!pwd)   { setErr("PASSWORD REQUIRED"); return; }
    setErr(""); setLoading(true);
    try {
      await onLogin(email, pwd);
    } catch(e) {
      setErr(e.message || "LOGIN FAILED");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-wrap">
      <div className="login-grid-bg"/>
      <div className="login-glow"/>

      {/* Left panel — brand + feature highlights */}
      <div className="login-left">
        <div className="login-brand">
          <img src="/logo.png" alt="TickerTap" style={{ width: 64, height: 64, borderRadius: 8, marginBottom: 16 }} />
          <div className="login-brand-mark">TICKER-TAP</div>
          <div className="login-brand-sub">Professional Investment Terminal</div>
        </div>
        <div className="login-divider"/>
        <div style={{ marginTop: 24, display: "flex", flexDirection: "column", gap: 20 }}>
          {[
            { title: "Real-Time Market Data", desc: "Live quotes, interactive charts, and news for stocks, crypto, ETFs, and physical assets." },
            { title: "Portfolio Management", desc: "Track multiple portfolios with P&L analysis, allocation breakdowns, and CSV import/export." },
            { title: "Watchlists", desc: "Monitor assets across custom watchlists with live prices, day change, and quick-buy actions." },
            { title: "AI-Powered News", desc: "Sentiment-scored market news filtered by your holdings, with bullish/bearish indicators." },
            { title: "Bank-Grade Security", desc: "End-to-end encryption, argon2 password hashing, account lockout protection, and rate limiting." },
            { title: "Multi-Currency & Multilingual", desc: "8 currencies with live exchange rates and 9 languages including English, Polish, German, and more." },
          ].map((f, i) => (
            <div key={i} style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
              <div style={{
                width: 6, height: 6, borderRadius: "50%",
                background: "var(--amber)", flexShrink: 0, marginTop: 6,
              }} />
              <div>
                <div style={{
                  fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 600,
                  color: "var(--bright)", letterSpacing: "0.5px", marginBottom: 3,
                }}>
                  {f.title}
                </div>
                <div style={{
                  fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--mid)",
                  lineHeight: 1.5,
                }}>
                  {f.desc}
                </div>
              </div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: "auto", paddingTop: 32, fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)", letterSpacing: 1, opacity: 0.5 }}>
          © 2026 TICKERTAP · ALL RIGHTS RESERVED
        </div>
      </div>

      {/* Right panel — login form */}
      <div className="login-right">
        <div className="login-head">SIGN IN</div>
        <div className="login-subhead">Access your trading terminal</div>
        <form className="login-form" onSubmit={e=>{e.preventDefault();handleLogin();}}>
          <div className="form-field">
            <label className="form-label">Email Address</label>
            <input className="form-control" type="email" value={email}
              onChange={e=>setEmail(e.target.value)} autoComplete="email"/>
          </div>
          <div className="form-field">
            <label className="form-label">Password</label>
            <div className="pw-wrap">
              <input className="form-control" type={show?"text":"password"}
                value={pwd} onChange={e=>setPwd(e.target.value)}
                autoComplete="current-password" style={{paddingRight:36}}/>
              <button type="button" className="pw-eye" onClick={()=>setShow(v=>!v)}>
                {show ? <Ic.eyeOff/> : <Ic.eye/>}
              </button>
            </div>
          </div>
          {err && <div style={{fontFamily:"var(--font-mono)",fontSize:11,color:"var(--red)"}}>{err}</div>}
          <button type="submit" className="btn btn-amber login-btn-full" disabled={loading}>
            {loading ? <span className="loading-pulse">AUTHENTICATING...</span> : "SIGN IN TO TERMINAL"}
          </button>
          <div className="login-footer-links">
            <span className="login-link" onClick={onForgotPassword}>Reset password</span>
          </div>
        </form>
        <div className="login-security">
          <div className="security-item"><Ic.lock/> TLS 1.3 Encrypted</div>
          <div className="security-item"><Ic.shield/> SOC 2 Compliant</div>
          <div className="security-item" style={{
            color: backendOk===false ? "var(--amber)" : "var(--green)",
            display:"flex",alignItems:"center",gap:4
          }}>
            <span style={{
              width:5, height:5, borderRadius:"50%",
              background: backendOk===false ? "var(--amber)" : "var(--green)",
              display:"inline-block",
              animation: backendOk===null ? "lpulse 1s infinite" : "none",
            }}/>
            {backendOk===null ? "Checking API..." : backendOk ? "API Connected" : "Demo Mode (API Offline)"}
          </div>
        </div>
        {onNavigate && <LegalLinks onNavigate={onNavigate} />}
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   PAGE: REGISTER
───────────────────────────────────────────────────────────────────────────── */

