/**
 * Login Page
 * 
 * Extracted component from App.jsx
 */

import { useState } from "react";
import { Ic } from "../../components/common/Icons";
import { Sparkline } from "../../components/charts";
import { TICKER_DATA } from "../../styles/globals";

const DEMO_EMAIL = "demo@example.com";

export const DEMO_EMAIL = "demo@fticker-tap.com";
const DEMO_PWD   = "Demo1234!";

function LoginPage({ onLogin, onRegister, onForgotPassword, backendOk }) {
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

      {/* Left panel — brand + market snapshot */}
      <div className="login-left">
        <div className="login-brand">
          <div className="login-brand-mark">TICKER-TAP</div>
          <div className="login-brand-sub">Professional Investment Terminal · v4.2</div>
        </div>
        <div className="login-stats stagger">
          <div className="login-stat-row">
            {[
              {val:"$2.4B",lbl:"Assets Under Management"},
              {val:"147K",lbl:"Active Accounts"},
            ].map((s,i)=>(
              <div key={i}>
                <div className="login-stat-val">{s.val}</div>
                <div className="login-stat-lbl">{s.lbl}</div>
              </div>
            ))}
          </div>
          <div className="login-stat-row">
            {[
              {val:"99.97%",lbl:"System Uptime"},
              {val:"< 4ms",lbl:"Avg Execution Time"},
            ].map((s,i)=>(
              <div key={i}>
                <div className="login-stat-val">{s.val}</div>
                <div className="login-stat-lbl">{s.lbl}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="login-divider"/>
        <div style={{marginTop:24,display:"flex",flexDirection:"column",gap:8}}>
          {TICKER_DATA.slice(0,5).map((t,i)=>(
            <div key={i} style={{display:"flex",alignItems:"center",gap:12,fontFamily:"var(--font-mono)",fontSize:12}}>
              <span style={{color:"var(--bright)",minWidth:50,fontWeight:500}}>{t.sym}</span>
              <span style={{color:"var(--mid)"}}>{t.price}</span>
              <span style={{color:t.pos?"var(--green)":"var(--red)"}}>{t.chg}</span>
              <Sparkline positive={t.pos} w={80} h={18}/>
            </div>
          ))}
        </div>
      </div>

      {/* Right panel — login form */}
      <div className="login-right">
        <div className="login-head">SIGN IN</div>
        <div className="login-subhead">Access your trading terminal</div>
        <div className="login-form">
          <div className="form-field">
            <label className="form-label">Email Address</label>
            <input className="form-control" type="email" value={email}
              onChange={e=>setEmail(e.target.value)}
              onFocus={()=>{ if (email===DEMO_EMAIL) setEmail(""); }}
              onKeyDown={e=>e.key==="Enter"&&handleLogin()}/>
          </div>
          <div className="form-field">
            <label className="form-label">Password</label>
            <div className="pw-wrap">
              <input className="form-control" type={show?"text":"password"}
                value={pwd} onChange={e=>setPwd(e.target.value)}
                onFocus={()=>{ if (pwd===DEMO_PWD) setPwd(""); }}
                onKeyDown={e=>e.key==="Enter"&&handleLogin()}
                style={{paddingRight:36}}/>
              <button className="pw-eye" onClick={()=>setShow(v=>!v)}>
                {show ? <Ic.eyeOff/> : <Ic.eye/>}
              </button>
            </div>
          </div>
          {err && <div style={{fontFamily:"var(--font-mono)",fontSize:11,color:"var(--red)"}}>{err}</div>}
          <button className="btn btn-amber login-btn-full" onClick={handleLogin} disabled={loading}>
            {loading ? <span className="loading-pulse">AUTHENTICATING...</span> : "SIGN IN TO TERMINAL"}
          </button>
          <div className="login-footer-links">
            <span className="login-link" onClick={onForgotPassword}>Reset password</span>
            <span className="login-link" onClick={onRegister}>Create account →</span>
          </div>
        </div>
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
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   PAGE: REGISTER
───────────────────────────────────────────────────────────────────────────── */

