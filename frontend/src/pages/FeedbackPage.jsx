/**
 * FeedbackPage.jsx — Bug reporting and improvement suggestions for TickerTap.
 *
 * Two-tab layout:
 *   1. REPORT BUG     — Submit bug reports with subject, category, and description.
 *   2. SUGGEST IMPROVEMENT — Submit feature/improvement suggestions with subject
 *                            and description.
 *
 * On successful submission the page transitions to a confirmation panel with
 * the option to reset and submit another report.
 *
 * Data flow:
 *   - Builds a payload with `report_type` ("bug" | "suggestion"), optional
 *     `category` (bugs only), `subject`, and `body`.
 *   - Sends the payload via `api.submitReport(payload, token)`.
 *
 * Props:
 *   @param {string}   token  - JWT access token
 *   @param {Function} goBack - Navigate back callback
 */

import { useState, useCallback } from "react";
import api from "../api/client";
import { Ic } from "../components/common/Icons";
import { useI18n } from "../context/I18nContext";

/* ── Bug category options ─────────────────────────────────────────────────── */
const BUG_CATEGORIES = [
  { value: "UI",              label: "UI"             },
  { value: "Data",            label: "Data"           },
  { value: "Performance",     label: "Performance"    },
  { value: "Authentication",  label: "Authentication" },
  { value: "Other",           label: "Other"          },
];

/* ── Maximum character count for description fields ───────────────────────── */
const MAX_BODY_LENGTH = 5000;

/* ── Inline style objects (Bloomberg terminal aesthetic) ──────────────────── */
const S = {
  /* Character counter positioned below the textarea */
  charCounter: {
    fontFamily: "var(--font-mono)",
    fontSize: 10,
    color: "var(--muted)",
    textAlign: "right",
    marginTop: 4,
    letterSpacing: 0.5,
  },
  /* Warning colour when approaching limit */
  charCounterWarn: {
    color: "var(--amber)",
  },
  /* Error banner displayed on submission failure */
  errorBanner: {
    marginBottom: 16,
    padding: "10px 14px",
    fontFamily: "var(--font-mono)",
    fontSize: 11,
    color: "var(--red)",
    background: "rgba(240,68,56,0.06)",
    border: "1px solid rgba(240,68,56,0.2)",
    borderRadius: 2,
    letterSpacing: 0.3,
  },
  /* Thank-you confirmation panel after successful submission */
  successPanel: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 16,
    padding: "48px 24px",
    textAlign: "center",
  },
  successIcon: {
    color: "var(--green)",
    marginBottom: 4,
  },
  successTitle: {
    fontFamily: "var(--font-disp)",
    fontSize: 18,
    color: "var(--bright)",
    letterSpacing: 1,
  },
  successSub: {
    fontFamily: "var(--font-mono)",
    fontSize: 11,
    color: "var(--muted)",
    maxWidth: 380,
    lineHeight: 1.5,
  },
  /* Textarea specific overrides */
  textarea: {
    minHeight: 140,
    resize: "vertical",
  },
};

/* ═══════════════════════════════════════════════════════════════════════════
   COMPONENT
═══════════════════════════════════════════════════════════════════════════ */

/**
 * FeedbackPage — renders bug report and improvement suggestion forms.
 *
 * @param {object}   props
 * @param {string}   props.token  - JWT access token for API calls
 * @param {Function} props.goBack - Navigation callback to return to previous page
 * @returns {JSX.Element}
 */
export function FeedbackPage({ token, goBack }) {
  const { t } = useI18n();

  /* ── Tab state ─────────────────────────────────────────────────────────── */
  const [tab, setTab] = useState("bug"); /* "bug" | "suggestion" */

  /* ── Form field state ──────────────────────────────────────────────────── */
  const [subject, setSubject]   = useState("");
  const [category, setCategory] = useState("UI");
  const [body, setBody]         = useState("");

  /* ── Submission lifecycle state ────────────────────────────────────────── */
  const [submitting, setSubmitting] = useState(false);
  const [error, setError]           = useState(null);
  const [submitted, setSubmitted]   = useState(false);

  /* ── Derived helpers ───────────────────────────────────────────────────── */
  const bodyLength    = body.length;
  const isNearLimit   = bodyLength > MAX_BODY_LENGTH * 0.9;
  const canSubmit     = subject.trim().length > 0 && body.trim().length > 0 && !submitting;

  /**
   * resetForm — clears all form fields and resets submission state so the
   * user can file another report without navigating away.
   */
  const resetForm = useCallback(() => {
    setSubject("");
    setCategory("UI");
    setBody("");
    setError(null);
    setSubmitted(false);
  }, []);

  /**
   * handleTabChange — switches between bug and suggestion tabs and resets
   * form state to avoid stale data carrying over between report types.
   *
   * @param {string} newTab - The tab identifier ("bug" | "suggestion")
   */
  const handleTabChange = useCallback((newTab) => {
    if (newTab === tab) return;
    setTab(newTab);
    setSubject("");
    setCategory("UI");
    setBody("");
    setError(null);
    setSubmitted(false);
  }, [tab]);

  /**
   * handleSubmit — assembles the report payload and sends it to the backend
   * via api.submitReport. Manages loading, error, and success states.
   *
   * Payload shape:
   *   { report_type: "bug"|"suggestion", category?: string, subject: string, body: string }
   */
  const handleSubmit = useCallback(async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);

    /* Build payload — category is only included for bug reports */
    const payload = {
      report_type: tab === "bug" ? "bug" : "suggestion",
      subject: subject.trim(),
      body: body.trim(),
    };
    if (tab === "bug") {
      payload.category = category;
    }

    try {
      /* api.submitReport(payload, token) — sends POST to the feedback endpoint,
         returns the created report object on success */
      await api.submitReport(payload, token);
      setSubmitted(true);
    } catch (err) {
      setError(err.message || t("feedback.submitError") || "Failed to submit report. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }, [canSubmit, tab, subject, body, category, token, t]);

  /* ── Render ────────────────────────────────────────────────────────────── */
  return (
    <div className="page-scroll">
      {/* ── Page header ──────────────────────────────────────────────────── */}
      <div className="page-header">
        <div>
          <div className="page-title" style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <button className="btn btn-ghost" onClick={goBack} style={{ padding: "4px 6px" }}>
              <Ic.back />
            </button>
            {t("feedback.title") || "FEEDBACK"}
          </div>
          <div className="page-sub">
            {t("feedback.subtitle") || "REPORT BUGS · SUGGEST IMPROVEMENTS"}
          </div>
        </div>
      </div>

      <div className="page-inner">
        {/* ── Tab bar ──────────────────────────────────────────────────── */}
        <div className="filter-bar" style={{ marginBottom: 16 }}>
          <button
            className={`filter-btn${tab === "bug" ? " active" : ""}`}
            onClick={() => handleTabChange("bug")}
          >
            {t("feedback.reportBug") || "REPORT BUG"}
          </button>
          <button
            className={`filter-btn${tab === "suggestion" ? " active" : ""}`}
            onClick={() => handleTabChange("suggestion")}
          >
            {t("feedback.suggestImprovement") || "SUGGEST IMPROVEMENT"}
          </button>
        </div>

        {/* ── Success confirmation panel ───────────────────────────────── */}
        {submitted && (
          <div className="panel">
            <div className="panel-body" style={S.successPanel}>
              <div style={S.successIcon}>
                <Ic.check />
              </div>
              <div style={S.successTitle}>
                {t("feedback.successTitle") || "Report submitted successfully"}
              </div>
              <div style={S.successSub}>
                {t("feedback.successMessage") || "Thank you for your feedback. Our team will review your submission and take appropriate action."}
              </div>
              <button
                className="btn btn-amber"
                onClick={resetForm}
                style={{ marginTop: 8, padding: "8px 20px" }}
              >
                {t("feedback.submitAnother") || "SUBMIT ANOTHER"}
              </button>
            </div>
          </div>
        )}

        {/* ── Form (hidden when submission succeeded) ──────────────────── */}
        {!submitted && (
          <div className="panel">
            <div className="panel-header">
              <div className="panel-title">
                {tab === "bug"
                  ? (t("feedback.bugFormTitle") || "BUG REPORT")
                  : (t("feedback.suggestionFormTitle") || "IMPROVEMENT SUGGESTION")}
              </div>
            </div>
            <div className="panel-body" style={{ padding: "16px 20px", display: "flex", flexDirection: "column", gap: 16 }}>

              {/* Error banner */}
              {error && (
                <div style={S.errorBanner}>
                  {error}
                </div>
              )}

              {/* Subject field */}
              <div className="form-field">
                <label className="form-label">
                  {t("feedback.subject") || "SUBJECT"}
                </label>
                <input
                  className="form-control search-input"
                  type="text"
                  placeholder={t("feedback.subjectPlaceholder") || "Brief summary of your report..."}
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  maxLength={200}
                />
              </div>

              {/* Category dropdown (bug reports only) */}
              {tab === "bug" && (
                <div className="form-field">
                  <label className="form-label">
                    {t("feedback.category") || "CATEGORY"}
                  </label>
                  <select
                    className="form-control search-input"
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    style={{ cursor: "pointer" }}
                  >
                    {BUG_CATEGORIES.map((cat) => (
                      <option key={cat.value} value={cat.value}>
                        {cat.label}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {/* Description textarea */}
              <div className="form-field">
                <label className="form-label">
                  {t("feedback.description") || "DESCRIPTION"}
                </label>
                <textarea
                  className="form-control search-input"
                  placeholder={
                    tab === "bug"
                      ? (t("feedback.bugDescriptionPlaceholder") || "Describe the bug: what happened, what you expected, and steps to reproduce...")
                      : (t("feedback.suggestionDescriptionPlaceholder") || "Describe your idea: what improvement would you like to see and why...")
                  }
                  value={body}
                  onChange={(e) => {
                    /* Enforce max length on paste/input */
                    if (e.target.value.length <= MAX_BODY_LENGTH) {
                      setBody(e.target.value);
                    }
                  }}
                  maxLength={MAX_BODY_LENGTH}
                  style={S.textarea}
                />
                {/* Character counter */}
                <div style={{
                  ...S.charCounter,
                  ...(isNearLimit ? S.charCounterWarn : {}),
                }}>
                  {bodyLength} / {MAX_BODY_LENGTH}
                </div>
              </div>

              {/* Submit button */}
              <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 4 }}>
                <button
                  className="btn btn-amber"
                  onClick={handleSubmit}
                  disabled={!canSubmit}
                  style={{
                    padding: "8px 24px",
                    opacity: canSubmit ? 1 : 0.4,
                    cursor: canSubmit ? "pointer" : "default",
                  }}
                >
                  {submitting
                    ? (t("feedback.submitting") || "SUBMITTING...")
                    : (t("feedback.submit") || "SUBMIT")}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
