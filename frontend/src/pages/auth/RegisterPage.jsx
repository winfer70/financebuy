/**
 * Register Page
 * 
 * Extracted component from App.jsx
 */

import { useState } from "react";
import api from "../../api/client";
import { Ic } from "../../components/common/Icons";
import { Sparkline } from "../../components/charts";
import { TICKER_DATA } from "../../styles/globals";

export function RegisterPage({ onLogin, onBack, backendOk }) {
  const [firstName, setFirstName] = useState("");
  const [lastName,  setLastName]  = useState("");
  const [email,     setEmail]     = useState("");
  const [pwd,       setPwd]       = useState("");
  const [pwd2,      setPwd2]      = useState("");
  const [show,      setShow]      = useState(false);
  const [loading,   setLoading]   = useState(false);
  const [err,       setErr]       = useState("");

  const handleRegister = async () => {
    if (!firstName)       { setErr("FIRST NAME REQUIRED"); return; }
    if (!email)           { setErr("EMAIL REQUIRED"); return; }
    if (!pwd)             { setErr("PASSWORD REQUIRED"); return; }
    if (pwd.length < 8)   { setErr("PASSWORD MIN 8 CHARACTERS"); return; }
    if (pwd !== pwd2)     { setErr("PASSWORDS DO NOT MATCH"); return; }
    setErr(""); setLoading(true);
    try {
      await api.register({ email, password: pwd, first_name: firstName, last_name: lastName });
      await onLogin(email, pwd);
    } catch(e) {
      setErr(e.message || "REGISTRATION FAILED");
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
        <div className="login-head">CREATE ACCOUNT</div>
        <div className="login-subhead">Open your trading terminal account</div>
        <div className="login-form">
          <div style={{display:"flex",gap:12}}>
            <div className="form-field" style={{flex:1}}>
              <label className="form-label">First Name</label>
              <input className="form-control" type="text" value={firstName}
                onChange={e=>setFirstName(e.target.value)} onKeyDown={e=>e.key==="Enter"&&handleRegister()} placeholder="First"/>
            </div>
            <div className="form-field" style={{flex:1}}>
              <label className="form-label">Last Name</label>
              <input className="form-control" type="text" value={lastName}
                onChange={e=>setLastName(e.target.value)} onKeyDown={e=>e.key==="Enter"&&handleRegister()} placeholder="Last"/>
            </div>
          </div>
          <div className="form-field">
            <label className="form-label">Email Address</label>
            <input className="form-control" type="email" value={email}
              onChange={e=>setEmail(e.target.value)} onKeyDown={e=>e.key==="Enter"&&handleRegister()} placeholder="you@example.com"/>
          </div>
          <div className="form-field">
            <label className="form-label">Password</label>
            <div className="pw-wrap">
              <input className="form-control" type={show?"text":"password"} value={pwd}
                onChange={e=>setPwd(e.target.value)} onKeyDown={e=>e.key==="Enter"&&handleRegister()}
                placeholder="Min 8 characters" style={{paddingRight:36}}/>
              <button className="pw-eye" onClick={()=>setShow(v=>!v)}>{show?<Ic.eyeOff/>:<Ic.eye/>}</button>
            </div>
          </div>
          <div className="form-field">
            <label className="form-label">Confirm Password</label>
            <input className="form-control" type={show?"text":"password"} value={pwd2}
              onChange={e=>setPwd2(e.target.value)} onKeyDown={e=>e.key==="Enter"&&handleRegister()} placeholder="Repeat password"/>
          </div>
          {err && <div style={{fontFamily:"var(--font-mono)",fontSize:11,color:"var(--red)"}}>{err}</div>}
          <button className="btn btn-amber login-btn-full" onClick={handleRegister} disabled={loading}>
            {loading ? <span className="loading-pulse">CREATING ACCOUNT...</span> : "CREATE ACCOUNT"}
          </button>
          <div className="login-footer-links">
            <span className="login-link" onClick={onBack}>← Back to sign in</span>
          </div>
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

/* ─────────────────────────────────────────────────────────────────────────────
   PAGE: DASHBOARD
───────────────────────────────────────────────────────────────────────────── */

