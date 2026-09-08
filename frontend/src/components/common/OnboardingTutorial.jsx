/**
 * OnboardingTutorial.jsx — First-run tutorial overlay.
 *
 * Shown once per account: fetches the user's profile on mount, and only
 * renders if `preferences.tutorial_done` is falsy. Completing or skipping
 * either one persists `tutorial_done: true` via PATCH /auth/preferences so
 * it never shows again on any device/session for that account.
 */
import { useEffect, useState } from "react";
import api from "../../api/client";

const STEPS = [
  {
    title: "Welcome to TickerTap",
    body: "A quick 8-step tour of where things live. Skip any time — this only shows once.",
  },
  {
    title: "Dashboard",
    body: "Your portfolio overview: a heatmap sized by volume and colored by daily move, plus market-hours status.",
  },
  {
    title: "Portfolio Manager",
    body: "Create portfolios, add positions, and set a hard stop (from your broker) or a soft stop — TickerTap will alert you by Telegram/ntfy when price crosses it.",
  },
  {
    title: "Charts",
    body: "Candlesticks with SMA overlays, drawing tools, and an SMA PROJ overlay — a linear trend fit on recent closes, projected forward as a dashed line.",
  },
  {
    title: "News",
    body: "Multi-source financial news, scored −5 to +5 by a local LLM, filterable by ticker and sentiment.",
  },
  {
    title: "FORM 4",
    body: "Insider (Form 4) filings from SEC EDGAR — sortable, filterable, and click any row for that person's buy/sell breakdown and historical track record.",
  },
  {
    title: "Orders & Trading",
    body: "Place market or limit orders, and (if enabled) run the AI paper-trading assistant via the Telegram bot.",
  },
  {
    title: "You're set",
    body: "Everything else is discoverable from the nav on the left. You can revisit this anytime you'd like — just ask.",
  },
];

export function OnboardingTutorial({ token }) {
  const [visible, setVisible] = useState(false);
  const [checked, setChecked] = useState(false);
  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!token) return;
    (async () => {
      try {
        const profile = await api.getProfile(token);
        if (!cancelled && !profile?.preferences?.tutorial_done) {
          setVisible(true);
        }
      } catch (_) {
        // Profile fetch failing shouldn't block the app — just skip the tour.
      } finally {
        if (!cancelled) setChecked(true);
      }
    })();
    return () => { cancelled = true; };
  }, [token]);

  const finish = async () => {
    setSaving(true);
    try {
      await api.updatePreferences({ tutorial_done: true }, token);
    } catch (_) {
      // Even if the save fails, don't trap the user in the overlay — it'll
      // just show again next session, which is an acceptable fallback.
    } finally {
      setSaving(false);
      setVisible(false);
    }
  };

  if (!checked || !visible) return null;

  const isLast = step === STEPS.length - 1;
  const s = STEPS[step];

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Onboarding tutorial"
      style={{
        position: "fixed", inset: 0, zIndex: 2000,
        background: "rgba(0,0,0,0.6)",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontFamily: "'IBM Plex Mono',monospace",
      }}
    >
      <div style={{
        width: 460, maxWidth: "90vw", background: "var(--bg2)",
        border: "1px solid var(--border)", borderRadius: 6,
        padding: 24, display: "flex", flexDirection: "column", gap: 16,
        boxShadow: "0 8px 40px rgba(0,0,0,0.5)",
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <span style={{ color: "var(--mid)", fontSize: 10, letterSpacing: 1 }}>
            STEP {step + 1} / {STEPS.length}
          </span>
          <button
            type="button"
            onClick={finish}
            disabled={saving}
            style={{
              background: "none", border: "none", color: "var(--mid)",
              cursor: "pointer", fontSize: 11, fontFamily: "inherit", letterSpacing: 0.5,
            }}
          >
            SKIP TUTORIAL ✕
          </button>
        </div>

        <div>
          <h2 style={{
            margin: "0 0 8px", fontFamily: "'Bebas Neue',sans-serif",
            fontSize: 24, letterSpacing: 1, color: "var(--text)",
          }}>
            {s.title}
          </h2>
          <p style={{ margin: 0, color: "var(--text)", lineHeight: 1.6, fontSize: 13 }}>
            {s.body}
          </p>
        </div>

        <div style={{ display: "flex", gap: 4, justifyContent: "center" }}>
          {STEPS.map((_, i) => (
            <div
              key={i}
              style={{
                width: 6, height: 6, borderRadius: 3,
                background: i === step ? "var(--green)" : "var(--border)",
              }}
            />
          ))}
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
          <button
            type="button"
            onClick={() => setStep((p) => Math.max(0, p - 1))}
            disabled={step === 0}
            style={{
              padding: "8px 14px", borderRadius: 3, cursor: step === 0 ? "default" : "pointer",
              border: "1px solid var(--border)", background: "var(--bg3)",
              color: step === 0 ? "var(--border)" : "var(--mid)",
              fontFamily: "inherit", fontSize: 12,
            }}
          >
            BACK
          </button>
          <button
            type="button"
            onClick={() => (isLast ? finish() : setStep((p) => p + 1))}
            disabled={saving}
            style={{
              padding: "8px 18px", borderRadius: 3, cursor: "pointer",
              border: "1px solid var(--green)", background: "rgba(15,125,64,0.15)",
              color: "var(--green)", fontFamily: "inherit", fontSize: 12, fontWeight: 600,
            }}
          >
            {isLast ? (saving ? "FINISHING…" : "GET STARTED") : "NEXT →"}
          </button>
        </div>
      </div>
    </div>
  );
}
