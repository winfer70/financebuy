/**
 * Reset Password Page
 *
 * Allows users to set a new password using a reset token from email.
 * Validates password strength and confirmation matching.
 */

import { useState } from "react";
import api from "../../api/client";
import { Ic } from "../../components/common/Icons";
import { Sparkline } from "../../components/charts";
import { TICKER_DATA } from "../../styles/globals";

export function ResetPasswordPage({ resetToken, onBack, onSuccess }) {
  const [pwd, setPwd]   = useState("");
  const [pwd2, setPwd2] = useState("");
  const [show, setShow] = useState(false);
  const [loading, setLoading] = useState(false);
  const [done, setDone]   = useState(false);
  const [err, setErr]     = useState("");

  const handleSubmit = async () => {
    if (!pwd)             { setErr("PASSWORD REQUIRED"); return; }
    if (pwd.length < 8)   { setErr("PASSWORD MIN 8 CHARACTERS"); return; }
    if (pwd !== pwd2)     { setErr("PASSWORDS DO NOT MATCH"); return; }
    setErr(""); setLoading(true);
    try {
      await api.resetPassword(resetToken, pwd);
      setDone(true);
      setTimeout(onSuccess, 2500);
    } catch(e) {
      setErr(e.message || "RESET FAILED — LINK MAY HAVE EXPIRED");
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
        <div className="login-head">{done ? "PASSWORD RESET" : "CREATE NEW PASSWORD"}</div>
        <div className="login-subhead">{done ? "Your password has been updated." : "Enter a strong password"}</div>
        <div className="login-form">
          {done ? (
            <div style={{display:"flex",flexDirection:"column",gap:16}}>
              <div style={{fontFamily:"var(--font-mono)",fontSize:11,color:"var(--green)",textAlign:"center",padding:"20px"}}>
                ✓ PASSWORD UPDATED<br/>
                Redirecting to sign in...
              </div>
            </div>
          ) : (
            <>
              <div className="form-field">
                <label className="form-label">New Password</label>
                <div className="pw-wrap">
                  <input className="form-control" type={show?"text":"password"} value={pwd} onChange={e=>setPwd(e.target.value)} placeholder="Min 8 characters"/>
                  <button className="pw-eye" onClick={()=>setShow(!show)}>{show?<Ic.eyeOff/>:<Ic.eye/>}</button>
                </div>
              </div>
              <div className="form-field">
                <label className="form-label">Confirm Password</label>
                <input className="form-control" type={show?"text":"password"} value={pwd2} onChange={e=>setPwd2(e.target.value)} onKeyDown={e=>e.key==="Enter"&&handleSubmit()} placeholder="Re-enter password"/>
              </div>
              {err && <div style={{fontFamily:"var(--font-mono)",fontSize:11,color:"var(--red)"}}>{err}</div>}
              <button className="btn btn-amber login-btn-full" onClick={handleSubmit} disabled={loading}>
                {loading ? <span className="loading-pulse">RESETTING...</span> : "RESET PASSWORD"}
              </button>
              <div className="login-footer-links">
                <span className="login-link" onClick={onBack}>← Back</span>
              </div>
            </>
          )}
        </div>
        <div className="login-security">
          <div className="security-item"><Ic.lock/> TLS 1.3 Encrypted</div>
          <div className="security-item"><Ic.shield/> SOC 2 Compliant</div>
        </div>
      </div>
    </div>
  );
}
