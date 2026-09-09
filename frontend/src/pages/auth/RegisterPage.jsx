/**
 * Register Page
 * 
 * Extracted component from App.jsx
 */

import { useEffect, useState } from "react";
import api from "../../api/client";
import { Ic } from "../../components/common/Icons";
import { Sparkline } from "../../components/charts";
import { TICKER_DATA } from "../../styles/globals";
import { LegalLinks } from "../../components/common";

export function RegisterPage({ onLogin, onBack, backendOk, onNavigate }) {
  const [firstName, setFirstName] = useState("");
  const [lastName,  setLastName]  = useState("");
  const [email,     setEmail]     = useState("");
  const [pwd,       setPwd]       = useState("");
  const [pwd2,      setPwd2]      = useState("");
  const [show,      setShow]      = useState(false);
  const [loading,   setLoading]   = useState(false);
  const [err,       setErr]       = useState("");
  const [registered, setRegistered] = useState(false);

  // Telegram invite gate — only present when this register link was shared
  // with a specific ?invite=<code> query param. Checked against the server
  // (not just "is there a code in the URL") so a stale/used/expired link
  // silently falls back to the normal registration form.
  const [inviteCode, setInviteCode] = useState(null);
  const [telegramGateOpen, setTelegramGateOpen] = useState(false);
  const [telegramLink, setTelegramLink] = useState(null); // {link_code, bot_username} once registered

  useEffect(() => {
    const code = new URLSearchParams(window.location.search).get("invite");
    if (!code) return;
    setInviteCode(code);
    api.checkTelegramInvite(code)
      .then((res) => setTelegramGateOpen(!!res?.valid))
      .catch(() => setTelegramGateOpen(false));
  }, []);

  const handleRegister = async () => {
    if (!firstName)       { setErr("FIRST NAME REQUIRED"); return; }
    if (!email)           { setErr("EMAIL REQUIRED"); return; }
    if (!pwd)             { setErr("PASSWORD REQUIRED"); return; }
    if (pwd.length < 8)   { setErr("PASSWORD MIN 8 CHARACTERS"); return; }
    if (pwd !== pwd2)     { setErr("PASSWORDS DO NOT MATCH"); return; }
    setErr(""); setLoading(true);
    try {
      const payload = { email, password: pwd, first_name: firstName, last_name: lastName };
      if (telegramGateOpen && inviteCode) {
        payload.telegram_invite_code = inviteCode;
      }
      const res = await api.register(payload);
      if (res?.telegram_link_code) {
        setTelegramLink({
          linkCode: res.telegram_link_code,
          botUsername: res.telegram_bot_username,
        });
      }
      setRegistered(true);
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
        {!registered && <div className="login-head">CREATE ACCOUNT</div>}
        {!registered && <div className="login-subhead">Open your trading terminal account</div>}
        {registered ? (
          <div style={{ textAlign: "center" }}>
            <div style={{
              fontFamily: "var(--font-disp)", fontSize: 24, color: "var(--green)",
              letterSpacing: 1, marginBottom: 12,
            }}>
              ACCOUNT CREATED
            </div>
            <div style={{
              fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--muted)",
              lineHeight: 1.6, marginBottom: 8,
            }}>
              A verification link has been sent to:
            </div>
            <div style={{
              fontFamily: "var(--font-mono)", fontSize: 14, color: "var(--amber)",
              fontWeight: 600, letterSpacing: 0.5, marginBottom: 24,
            }}>
              {email}
            </div>
            <div style={{
              fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--muted)",
              lineHeight: 1.6, marginBottom: 24,
            }}>
              Please check your inbox (and spam folder) and click the verification
              link to activate your account.
            </div>
            {telegramLink && (
              <div style={{
                textAlign: "left", background: "rgba(15,125,64,0.08)",
                border: "1px solid var(--green)", borderRadius: 4,
                padding: 16, marginBottom: 24, fontFamily: "var(--font-mono)",
              }}>
                <div style={{ color: "var(--green)", fontSize: 12, fontWeight: 600, letterSpacing: 0.5, marginBottom: 8 }}>
                  CONNECT YOUR TELEGRAM ALERTS
                </div>
                <div style={{ color: "var(--muted)", fontSize: 11, lineHeight: 1.6, marginBottom: 10 }}>
                  Message{" "}
                  {telegramLink.botUsername ? (
                    <a
                      href={`https://t.me/${telegramLink.botUsername.replace(/^@/, "")}`}
                      target="_blank" rel="noreferrer"
                      style={{ color: "var(--amber)", fontWeight: 600 }}
                    >
                      @{telegramLink.botUsername.replace(/^@/, "")}
                    </a>
                  ) : "the tickerTap bot"}{" "}
                  on Telegram and send this command — it links this chat to your
                  account only, nothing else is shared:
                </div>
                <div style={{
                  background: "var(--bg3, #111)", border: "1px solid var(--border, #333)",
                  borderRadius: 3, padding: "8px 12px", color: "var(--text, #eee)",
                  fontSize: 13, fontWeight: 600, letterSpacing: 0.5, userSelect: "all",
                }}>
                  /link {telegramLink.linkCode}
                </div>
                <div style={{ color: "var(--muted)", fontSize: 10, marginTop: 8 }}>
                  This code expires in 30 minutes. You can also do this later — it's
                  optional.
                </div>
              </div>
            )}
            <button className="btn btn-amber login-btn-full" onClick={onBack}>
              BACK TO SIGN IN
            </button>
          </div>
        ) : (
          <form className="login-form" onSubmit={e=>{e.preventDefault();handleRegister();}}>
            {telegramGateOpen && (
              <div style={{
                background: "rgba(15,125,64,0.08)", border: "1px solid var(--green)",
                borderRadius: 4, padding: "10px 12px", fontFamily: "var(--font-mono)",
                fontSize: 11, color: "var(--green)", lineHeight: 1.5,
              }}>
                You're registering via an invite link — after signing up you'll be
                able to connect your own Telegram chat for alerts.
              </div>
            )}
            <div style={{display:"flex",gap:12}}>
              <div className="form-field" style={{flex:1}}>
                <label className="form-label">First Name</label>
                <input className="form-control" type="text" value={firstName}
                  onChange={e=>setFirstName(e.target.value)} placeholder="First"/>
              </div>
              <div className="form-field" style={{flex:1}}>
                <label className="form-label">Last Name</label>
                <input className="form-control" type="text" value={lastName}
                  onChange={e=>setLastName(e.target.value)} placeholder="Last"/>
              </div>
            </div>
            <div className="form-field">
              <label className="form-label">Email Address</label>
              <input className="form-control" type="email" value={email}
                onChange={e=>setEmail(e.target.value)} autoComplete="email" placeholder="you@example.com"/>
            </div>
            <div className="form-field">
              <label className="form-label">Password</label>
              <div className="pw-wrap">
                <input className="form-control" type={show?"text":"password"} value={pwd}
                  onChange={e=>setPwd(e.target.value)}
                  autoComplete="new-password" placeholder="Min 8 characters" style={{paddingRight:36}}/>
                <button type="button" className="pw-eye" onClick={()=>setShow(v=>!v)}>{show?<Ic.eyeOff/>:<Ic.eye/>}</button>
              </div>
            </div>
            <div className="form-field">
              <label className="form-label">Confirm Password</label>
              <input className="form-control" type={show?"text":"password"} value={pwd2}
                onChange={e=>setPwd2(e.target.value)} autoComplete="new-password" placeholder="Repeat password"/>
            </div>
            {err && <div style={{fontFamily:"var(--font-mono)",fontSize:11,color:"var(--red)"}}>{err}</div>}
            <button type="submit" className="btn btn-amber login-btn-full" disabled={loading}>
              {loading ? <span className="loading-pulse">CREATING ACCOUNT...</span> : "CREATE ACCOUNT"}
            </button>
            <div className="login-footer-links">
              <span className="login-link" onClick={onBack}>← Back to sign in</span>
            </div>
          </form>
        )}
        <div className="login-security">
          <div className="security-item"><Ic.lock/> TLS 1.3 Encrypted</div>
          <div className="security-item"><Ic.shield/> SOC 2 Compliant</div>
          <div className="security-item" style={{color:backendOk===false?"var(--amber)":"var(--green)",display:"flex",alignItems:"center",gap:4}}>
            <span style={{width:5,height:5,borderRadius:"50%",background:backendOk===false?"var(--amber)":"var(--green)",display:"inline-block"}}/>
            {backendOk===null?"Checking API...":backendOk?"API Connected":"Demo Mode (API Offline)"}
          </div>
        </div>
        {onNavigate && <LegalLinks onNavigate={onNavigate} />}
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   PAGE: DASHBOARD
───────────────────────────────────────────────────────────────────────────── */

