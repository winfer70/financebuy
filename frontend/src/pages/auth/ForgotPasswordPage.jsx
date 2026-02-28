/**
 * Forgot Password Page
 *
 * Allows users to request a password reset link via email.
 * Shows confirmation message after successful submission.
 */

import { useState } from "react";
import api from "../../api/client";
import { Ic } from "../../components/common/Icons";
import { Sparkline } from "../../components/charts";
import { TICKER_DATA } from "../../styles/globals";

export function ForgotPasswordPage({ onBack, backendOk }) {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [err, setErr] = useState("");

  const handleSubmit = async () => {
    if (!email) { setErr("EMAIL REQUIRED"); return; }
    setErr(""); setLoading(true);
    try {
      await api.forgotPassword(email);
      setSent(true);
    } catch(e) {
      setErr(e.message || "REQUEST FAILED");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-wrap">
      <div className="login-grid-bg"/>
      <div className="login-glow"/>
      <div className="login-left">
        <div className="login-brand">
          <div className="login-brand-mark">TICKER-TAP</div>
          <div className="login-brand-sub">Professional Investment Terminal · v4.2</div>
        </div>
        <div className="login-stats stagger">
          <div className="login-stat-row">
            {[{val:"$2.4B",lbl:"Assets Under Management"},{val:"147K",lbl:"Active Accounts"}].map((s,i)=>(
              <div key={i}><div className="login-stat-val">{s.val}</div><div className="login-stat-lbl">{s.lbl}</div></div>
            ))}
          </div>
          <div className="login-stat-row">
            {[{val:"99.97%",lbl:"System Uptime"},{val:"< 4ms",lbl:"Avg Execution Time"}].map((s,i)=>(
              <div key={i}><div className="login-stat-val">{s.val}</div><div className="login-stat-lbl">{s.lbl}</div></div>
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
      <div className="login-right">
        <div className="login-head">RESET PASSWORD</div>
        <div className="login-subhead">Enter your account email to receive a reset link</div>
        <div className="login-form">
          {sent ? (
            <div style={{display:"flex",flexDirection:"column",gap:16}}>
              <div style={{
                fontFamily:"var(--font-mono)",fontSize:12,color:"var(--green)",
                border:"1px solid var(--green)",borderRadius:2,padding:"14px 16px",lineHeight:1.6
              }}>
                CHECK YOUR EMAIL<br/>
                <span style={{color:"var(--mid)",fontSize:11}}>A reset link has been sent to <strong style={{color:"var(--bright)"}}>{email}</strong>. It expires in 1 hour.</span>
              </div>
              <div className="login-footer-links">
                <span className="login-link" onClick={onBack}>← Back to sign in</span>
              </div>
            </div>
          ) : (
            <>
              <div className="form-field">
                <label className="form-label">Email Address</label>
                <input className="form-control" type="email" value={email}
                  onChange={e=>setEmail(e.target.value)}
                  onKeyDown={e=>e.key==="Enter"&&handleSubmit()}
                  placeholder="you@example.com"/>
              </div>
              {err && <div style={{fontFamily:"var(--font-mono)",fontSize:11,color:"var(--red)"}}>{err}</div>}
              <button className="btn btn-amber login-btn-full" onClick={handleSubmit} disabled={loading||!backendOk}>
                {loading ? <span className="loading-pulse">SENDING...</span> : "SEND RESET LINK"}
              </button>
              {backendOk===false && (
                <div style={{fontFamily:"var(--font-mono)",fontSize:11,color:"var(--amber)"}}>
                  BACKEND OFFLINE — PASSWORD RESET UNAVAILABLE IN DEMO MODE
                </div>
              )}
              <div className="login-footer-links">
                <span className="login-link" onClick={onBack}>← Back to sign in</span>
              </div>
            </>
          )}
        </div>
        <div className="login-security">
          <div className="security-item"><Ic.lock/> TLS 1.3 Encrypted</div>
          <div className="security-item"><Ic.shield/> SOC 2 Compliant</div>
          <div className="security-item" style={{color:backendOk===false?"var(--amber)":"var(--green)",display:"flex",alignItems:"center",gap:4}}>
            <span style={{width:5,height:5,borderRadius:"50%",background:backendOk===false?"var(--amber)":"var(--green)",display:"inline-block"}}/>
            {backendOk===null?"Checking API...":backendOk?"API Connected":"Demo Mode (API Offline)"}
          </div>
        </div>
      </div>
    </div>
  );
}
