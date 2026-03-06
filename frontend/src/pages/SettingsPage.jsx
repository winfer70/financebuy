/**
 * SettingsPage.jsx — User account settings, preferences, and account management.
 *
 * Displays the user's profile information (read-only) and provides
 * controls to update display preferences:
 *   - Currency: USD, EUR, GBP, PLN, CHF, JPY, CAD, AUD
 *   - Language: en, pl, de, zh, es, pt, fr, ja
 *
 * Also provides an ACCOUNT section with:
 *   - Edit Name: update first_name / last_name via PATCH /auth/profile
 *   - Change Email: request email change (requires password verification)
 *   - Deactivate Account: disable login while preserving data
 *   - Delete Account: permanent or 30-day soft delete
 *
 * Preferences are persisted to the backend via PATCH /auth/preferences
 * and reflected immediately in the UI via the context providers.
 *
 * Props:
 *   @param {string}   token    - JWT access token
 *   @param {Function} goBack   - Navigate back callback
 *   @param {Function} onLogout - Callback to sign the user out (used after deactivate/delete)
 */

import { useState, useEffect, useCallback } from "react";
import api from "../api/client";
import { Ic } from "../components/common/Icons";
import { useI18n } from "../context/I18nContext";

/* ── Currency and language option labels ──────────────────────────────────── */
const CURRENCY_OPTIONS = [
  { code: "USD", label: "USD — US Dollar",          symbol: "$"  },
  { code: "EUR", label: "EUR — Euro",               symbol: "\u20AC" },
  { code: "GBP", label: "GBP — British Pound",      symbol: "\u00A3" },
  { code: "PLN", label: "PLN — Polish Z\u0142oty",  symbol: "z\u0142"},
  { code: "CHF", label: "CHF — Swiss Franc",         symbol: "CHF"},
  { code: "JPY", label: "JPY — Japanese Yen",        symbol: "\u00A5" },
  { code: "CAD", label: "CAD — Canadian Dollar",     symbol: "C$" },
  { code: "AUD", label: "AUD — Australian Dollar",   symbol: "A$" },
];

const LANGUAGE_OPTIONS = [
  { code: "en", label: "English"                  },
  { code: "pl", label: "Polski"                   },
  { code: "de", label: "Deutsch"                  },
  { code: "zh", label: "\u4E2D\u6587 (Simplified)"},
  { code: "es", label: "Espa\u00F1ol"             },
  { code: "pt", label: "Portugu\u00EAs"           },
  { code: "fr", label: "Fran\u00E7ais"            },
  { code: "ja", label: "\u65E5\u672C\u8A9E"       },
  { code: "it", label: "Italiano"                },
];

/* ── Styles ─────────────────────────────────────────────────────────────── */
const S = {
  container: {
    padding: "32px 40px",
    maxWidth: 680,
    margin: "0 auto",
    fontFamily: "var(--font-mono)",
    overflowY: "auto",
    height: "100%",
  },
  header: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    marginBottom: 32,
  },
  title: {
    fontFamily: "var(--font-disp)",
    fontSize: 28,
    color: "var(--bright)",
    letterSpacing: 1,
  },
  backBtn: {
    background: "none",
    border: "none",
    color: "var(--muted)",
    cursor: "pointer",
    padding: 4,
    display: "flex",
    alignItems: "center",
  },
  section: {
    background: "var(--panel)",
    border: "1px solid var(--border)",
    borderRadius: 4,
    padding: "20px 24px",
    marginBottom: 20,
  },
  sectionTitle: {
    fontFamily: "var(--font-disp)",
    fontSize: 16,
    color: "var(--amber)",
    letterSpacing: 1.5,
    marginBottom: 16,
    borderBottom: "1px solid var(--border)",
    paddingBottom: 8,
  },
  row: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "8px 0",
    borderBottom: "1px solid var(--border)",
    fontSize: 12,
  },
  label: {
    color: "var(--muted)",
    fontSize: 10,
    letterSpacing: 1,
    textTransform: "uppercase",
  },
  value: {
    color: "var(--bright)",
    fontSize: 12,
    fontFamily: "var(--font-mono)",
  },
  select: {
    background: "var(--bg2)",
    border: "1px solid var(--border)",
    color: "var(--bright)",
    fontFamily: "var(--font-mono)",
    fontSize: 12,
    padding: "6px 10px",
    borderRadius: 3,
    cursor: "pointer",
    minWidth: 200,
    outline: "none",
  },
  saveBtn: {
    background: "var(--amber)",
    color: "#fff",
    border: "none",
    fontFamily: "var(--font-mono)",
    fontSize: 11,
    letterSpacing: 1,
    padding: "8px 20px",
    borderRadius: 3,
    cursor: "pointer",
    marginTop: 16,
    opacity: 1,
  },
  saveBtnDisabled: {
    opacity: 0.4,
    cursor: "default",
  },
  status: {
    fontSize: 10,
    letterSpacing: 1,
    marginLeft: 12,
    fontFamily: "var(--font-mono)",
  },
};

/**
 * SettingsPage — renders profile info, preference controls, and account management.
 *
 * @param {object} props
 * @param {string}   props.token    - JWT access token for API calls
 * @param {Function} props.goBack   - Navigation callback to return to previous page
 * @param {Function} props.onLogout - Callback to sign the user out (deactivate / delete flows)
 * @returns {JSX.Element}
 */
export function SettingsPage({ token, goBack, onLogout }) {
  const { t } = useI18n();

  /* ── Profile state ─────────────────────────────────────────────────────── */
  const [profile, setProfile]   = useState(null);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState(null);

  /* ── Preference form state ─────────────────────────────────────────────── */
  const [currency, setCurrency] = useState("USD");
  const [language, setLanguage] = useState("en");
  const [saving, setSaving]     = useState(false);
  const [saveMsg, setSaveMsg]   = useState(null);

  /* ── Track whether preferences have been modified from saved values ─── */
  const [savedCurrency, setSavedCurrency] = useState("USD");
  const [savedLanguage, setSavedLanguage] = useState("en");
  const hasChanges = currency !== savedCurrency || language !== savedLanguage;

  /* ── Account section state ──────────────────────────────────────────── */
  /* Name editing */
  const [editFirstName, setEditFirstName] = useState("");
  const [editLastName, setEditLastName]   = useState("");
  const [savingName, setSavingName]       = useState(false);
  const [nameMsg, setNameMsg]             = useState(null);
  const [nameEdited, setNameEdited]       = useState(false);

  /* Email change */
  const [newEmail, setNewEmail]           = useState("");
  const [emailPwd, setEmailPwd]           = useState("");
  const [savingEmail, setSavingEmail]     = useState(false);
  const [emailMsg, setEmailMsg]           = useState(null);

  /* Deactivate */
  const [showDeactivate, setShowDeactivate] = useState(false);
  const [deactPwd, setDeactPwd]             = useState("");
  const [deactivating, setDeactivating]     = useState(false);
  const [deactErr, setDeactErr]             = useState(null);

  /* Delete */
  const [showDelete, setShowDelete]     = useState(false);
  const [deleteMode, setDeleteMode]     = useState("soft");  /* "soft" | "permanent" */
  const [deletePwd, setDeletePwd]       = useState("");
  const [deleting, setDeleting]         = useState(false);
  const [deleteErr, setDeleteErr]       = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState("");  /* must type "DELETE" for permanent */

  /* ── Load profile on mount ─────────────────────────────────────────────── */
  useEffect(() => {
    if (!token) return;
    let cancelled = false;

    /**
     * fetchProfile — retrieves user profile + preferences from GET /auth/me.
     * Populates both profile display and preference form defaults.
     */
    async function fetchProfile() {
      try {
        const data = await api.getProfile(token);
        if (cancelled) return;
        setProfile(data);
        const prefs = data.preferences || {};
        const cur = prefs.currency || "USD";
        const lang = prefs.language || "en";
        setCurrency(cur);
        setLanguage(lang);
        setSavedCurrency(cur);
        setSavedLanguage(lang);
        setEditFirstName(data.first_name || "");
        setEditLastName(data.last_name || "");
      } catch (err) {
        if (!cancelled) setError(err.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchProfile();
    return () => { cancelled = true; };
  }, [token]);

  /* ── Save preferences ──────────────────────────────────────────────────── */
  /**
   * handleSave — sends PATCH /auth/preferences with changed fields.
   * Updates local saved-state on success so the "unsaved" indicator clears.
   */
  const handleSave = useCallback(async () => {
    if (!hasChanges || saving) return;
    setSaving(true);
    setSaveMsg(null);

    try {
      const payload = {};
      if (currency !== savedCurrency) payload.currency = currency;
      if (language !== savedLanguage) payload.language = language;

      await api.updatePreferences(payload, token);

      setSavedCurrency(currency);
      setSavedLanguage(language);
      setSaveMsg("SAVED");

      // Dispatch custom event so CurrencyContext / I18nContext can react
      window.dispatchEvent(new CustomEvent("preferences-updated", {
        detail: { currency, language },
      }));
    } catch (err) {
      setSaveMsg(`ERROR: ${err.message}`);
    } finally {
      setSaving(false);
      // Clear the status message after 3 seconds
      setTimeout(() => setSaveMsg(null), 3000);
    }
  }, [currency, language, savedCurrency, savedLanguage, hasChanges, saving, token]);

  /* ── Save name ──────────────────────────────────────────────────────── */
  /**
   * handleSaveName — sends updated first_name and last_name to the backend
   * via api.updateProfile(). Clears the "edited" flag and shows a status
   * message on success or error.
   */
  const handleSaveName = useCallback(async () => {
    if (savingName) return;
    setSavingName(true);
    setNameMsg(null);
    try {
      /* api.updateProfile — PATCH /auth/profile with { first_name, last_name }. Returns updated user. */
      await api.updateProfile({ first_name: editFirstName.trim(), last_name: editLastName.trim() }, token);
      setProfile(prev => ({ ...prev, first_name: editFirstName.trim(), last_name: editLastName.trim() }));

      /* Notify other contexts (e.g. AuthContext) so the navbar avatar reflects the new name */
      window.dispatchEvent(new CustomEvent("profile-updated", {
        detail: { first_name: editFirstName.trim(), last_name: editLastName.trim() },
      }));

      setNameMsg("SAVED");
      setNameEdited(false);
    } catch (err) {
      setNameMsg(`ERROR: ${err.message}`);
    } finally {
      setSavingName(false);
      setTimeout(() => setNameMsg(null), 3000);
    }
  }, [editFirstName, editLastName, savingName, token]);

  /* ── Change email ───────────────────────────────────────────────────── */
  /**
   * handleChangeEmail — sends a new email + current password to the backend
   * via api.changeEmail(). The backend sends a verification email to the new
   * address; the email is not updated until the user clicks the link.
   */
  const handleChangeEmail = useCallback(async () => {
    if (savingEmail || !newEmail.trim() || !emailPwd) return;
    setSavingEmail(true);
    setEmailMsg(null);
    try {
      /* api.changeEmail — POST /auth/change-email with { new_email, password }. Sends verification link. */
      await api.changeEmail({ new_email: newEmail.trim(), password: emailPwd }, token);
      setEmailMsg("VERIFICATION EMAIL SENT TO NEW ADDRESS");
      setNewEmail("");
      setEmailPwd("");
    } catch (err) {
      setEmailMsg(`ERROR: ${err.message}`);
    } finally {
      setSavingEmail(false);
      setTimeout(() => setEmailMsg(null), 5000);
    }
  }, [newEmail, emailPwd, savingEmail, token]);

  /* ── Deactivate account ─────────────────────────────────────────────── */
  /**
   * handleDeactivate — disables the user's login by calling
   * api.deactivateAccount(). On success, signs the user out via onLogout().
   * Data is preserved; the user can reactivate via an email link.
   */
  const handleDeactivate = useCallback(async () => {
    if (deactivating || !deactPwd) return;
    setDeactivating(true);
    setDeactErr(null);
    try {
      /* api.deactivateAccount — POST /auth/deactivate with { password }. Disables login. */
      await api.deactivateAccount({ password: deactPwd }, token);
      onLogout?.();
    } catch (err) {
      setDeactErr(err.message || "Failed to deactivate account.");
    } finally {
      setDeactivating(false);
    }
  }, [deactPwd, deactivating, token, onLogout]);

  /* ── Delete account ─────────────────────────────────────────────────── */
  /**
   * handleDelete — permanently or soft-deletes the user's account via
   * api.deleteAccount(). "soft" schedules deletion in 30 days (cancellable);
   * "permanent" deletes immediately. Both require password confirmation.
   * On success, signs the user out via onLogout().
   */
  const handleDelete = useCallback(async () => {
    if (deleting || !deletePwd) return;
    if (deleteMode === "permanent" && deleteConfirm !== "DELETE") return;
    setDeleting(true);
    setDeleteErr(null);
    try {
      /* api.deleteAccount — DELETE /auth/account with { mode, password }. Returns confirmation. */
      await api.deleteAccount({ mode: deleteMode, password: deletePwd }, token);
      onLogout?.();
    } catch (err) {
      setDeleteErr(err.message || "Failed to delete account.");
    } finally {
      setDeleting(false);
    }
  }, [deletePwd, deleteMode, deleteConfirm, deleting, token, onLogout]);

  /* ── Loading / Error states ────────────────────────────────────────────── */
  if (loading) {
    return (
      <div style={S.container}>
        <div style={{ color: "var(--muted)", fontSize: 12, fontFamily: "var(--font-mono)" }}>
          {t("common.loading")}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={S.container}>
        <div style={{ color: "var(--red)", fontSize: 12, fontFamily: "var(--font-mono)" }}>
          {t("common.error") + ": "}{error}
        </div>
      </div>
    );
  }

  return (
    <div style={S.container}>
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div style={S.header}>
        <button style={S.backBtn} onClick={goBack} title="Go back">
          <Ic.back />
        </button>
        <span style={S.title}>{t("settings.title")}</span>
      </div>

      {/* ── Profile Section (read-only) ──────────────────────────────── */}
      <div style={S.section}>
        <div style={S.sectionTitle}>{t("settings.profile")}</div>

        <div style={S.row}>
          <span style={S.label}>{t("settings.email")}</span>
          <span style={S.value}>{profile?.email || "—"}</span>
        </div>
        <div style={S.row}>
          <span style={S.label}>{t("settings.name")}</span>
          <span style={S.value}>
            {profile?.first_name || ""} {profile?.last_name || ""}
          </span>
        </div>
        <div style={S.row}>
          <span style={S.label}>{t("settings.phone")}</span>
          <span style={S.value}>{profile?.phone || "—"}</span>
        </div>
        <div style={S.row}>
          <span style={S.label}>{t("settings.kycStatus")}</span>
          <span style={{
            ...S.value,
            color: profile?.kyc_status === "approved"
              ? "var(--green)"
              : profile?.kyc_status === "pending"
              ? "var(--amber)"
              : "var(--muted)",
          }}>
            {(profile?.kyc_status || "—").toUpperCase()}
          </span>
        </div>
        <div style={{ ...S.row, borderBottom: "none" }}>
          <span style={S.label}>{t("settings.accountStatus")}</span>
          <span style={{
            ...S.value,
            color: profile?.is_active ? "var(--green)" : "var(--red)",
          }}>
            {profile?.is_active ? t("settings.active") : t("settings.inactive")}
          </span>
        </div>
      </div>

      {/* ── Preferences Section ──────────────────────────────────────── */}
      <div style={S.section}>
        <div style={S.sectionTitle}>{t("settings.preferences")}</div>

        {/* Currency selector */}
        <div style={S.row}>
          <span style={S.label}>{t("settings.displayCurrency")}</span>
          <select
            style={S.select}
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
          >
            {CURRENCY_OPTIONS.map((c) => (
              <option key={c.code} value={c.code}>
                {c.label}
              </option>
            ))}
          </select>
        </div>

        {/* Language selector */}
        <div style={{ ...S.row, borderBottom: "none" }}>
          <span style={S.label}>{t("settings.language")}</span>
          <select
            style={S.select}
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
          >
            {LANGUAGE_OPTIONS.map((l) => (
              <option key={l.code} value={l.code}>
                {l.label}
              </option>
            ))}
          </select>
        </div>

        {/* Save button + status */}
        <div style={{ display: "flex", alignItems: "center", marginTop: 16 }}>
          <button
            style={{
              ...S.saveBtn,
              ...((!hasChanges || saving) ? S.saveBtnDisabled : {}),
            }}
            onClick={handleSave}
            disabled={!hasChanges || saving}
          >
            {saving ? t("settings.saving") : t("settings.savePreferences")}
          </button>

          {saveMsg && (
            <span style={{
              ...S.status,
              color: saveMsg.startsWith("ERROR") ? "var(--red)" : "var(--green)",
            }}>
              {saveMsg}
            </span>
          )}

          {hasChanges && !saveMsg && (
            <span style={{ ...S.status, color: "var(--amber)" }}>
              {t("settings.unsavedChanges")}
            </span>
          )}
        </div>
      </div>

      {/* ── Account Section ──────────────────────────────────────────── */}
      <div style={S.section}>
        <div style={S.sectionTitle}>{t("settings.account")}</div>

        {/* Edit name */}
        <div style={{ marginBottom: 16 }}>
          <div style={{ ...S.label, marginBottom: 8 }}>{t("settings.editName")}</div>
          <div style={{ display: "flex", gap: 12 }}>
            <input
              className="form-control"
              placeholder={t("settings.firstName")}
              value={editFirstName}
              onChange={e => { setEditFirstName(e.target.value); setNameEdited(true); }}
              style={{ flex: 1 }}
            />
            <input
              className="form-control"
              placeholder={t("settings.lastName")}
              value={editLastName}
              onChange={e => { setEditLastName(e.target.value); setNameEdited(true); }}
              style={{ flex: 1 }}
            />
          </div>
          <div style={{ display: "flex", alignItems: "center", marginTop: 8 }}>
            <button
              style={{ ...S.saveBtn, ...(!nameEdited || savingName ? S.saveBtnDisabled : {}), marginTop: 0 }}
              onClick={handleSaveName}
              disabled={!nameEdited || savingName}
            >
              {savingName ? t("settings.savingName") : t("settings.saveName")}
            </button>
            {nameMsg && (
              <span style={{ ...S.status, color: nameMsg.startsWith("ERROR") ? "var(--red)" : "var(--green)" }}>
                {nameMsg}
              </span>
            )}
          </div>
        </div>

        <div style={{ height: 1, background: "var(--border)", margin: "16px 0" }} />

        {/* Change email */}
        <div style={{ marginBottom: 16 }}>
          <div style={{ ...S.label, marginBottom: 8 }}>{t("settings.changeEmail")}</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <input
              className="form-control"
              type="email"
              placeholder={t("settings.newEmail")}
              value={newEmail}
              onChange={e => setNewEmail(e.target.value)}
            />
            <input
              className="form-control"
              type="password"
              placeholder={t("settings.currentPassword")}
              value={emailPwd}
              onChange={e => setEmailPwd(e.target.value)}
              autoComplete="current-password"
            />
          </div>
          <div style={{ display: "flex", alignItems: "center", marginTop: 8 }}>
            <button
              style={{ ...S.saveBtn, ...(!newEmail.trim() || !emailPwd || savingEmail ? S.saveBtnDisabled : {}), marginTop: 0 }}
              onClick={handleChangeEmail}
              disabled={!newEmail.trim() || !emailPwd || savingEmail}
            >
              {savingEmail ? t("settings.sending") : t("settings.changeEmail")}
            </button>
            {emailMsg && (
              <span style={{
                ...S.status,
                color: emailMsg.startsWith("ERROR") ? "var(--red)" : "var(--green)",
                maxWidth: 260, display: "inline-block",
              }}>
                {emailMsg}
              </span>
            )}
          </div>
        </div>

        <div style={{ height: 1, background: "var(--border)", margin: "16px 0" }} />

        {/* Deactivate Account */}
        <div style={{ marginBottom: 16 }}>
          <div style={{ ...S.label, marginBottom: 4 }}>{t("settings.deactivateAccount")}</div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--muted)", marginBottom: 8, lineHeight: 1.5 }}>
            {t("settings.deactivateDesc")}
          </div>
          {!showDeactivate ? (
            <button
              className="btn btn-outline"
              onClick={() => setShowDeactivate(true)}
              style={{ fontSize: 10, padding: "6px 14px" }}
            >
              {t("settings.deactivateAccount")}
            </button>
          ) : (
            <div style={{ background: "var(--bg3)", border: "1px solid var(--border)", borderRadius: 4, padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
              <input
                className="form-control"
                type="password"
                placeholder={t("settings.enterPassword")}
                value={deactPwd}
                onChange={e => setDeactPwd(e.target.value)}
                autoComplete="current-password"
              />
              {deactErr && <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--red)" }}>{deactErr}</div>}
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn btn-ghost" onClick={() => { setShowDeactivate(false); setDeactPwd(""); setDeactErr(null); }} style={{ fontSize: 10, padding: "5px 12px" }}>{t("common.cancel")}</button>
                <button className="btn btn-danger" onClick={handleDeactivate} disabled={!deactPwd || deactivating} style={{ fontSize: 10, padding: "5px 12px", opacity: (!deactPwd || deactivating) ? 0.4 : 1 }}>
                  {deactivating ? t("settings.deactivating") : t("settings.confirmDeactivate")}
                </button>
              </div>
            </div>
          )}
        </div>

        <div style={{ height: 1, background: "var(--border)", margin: "16px 0" }} />

        {/* Delete Account */}
        <div>
          <div style={{ ...S.label, marginBottom: 4, color: "var(--red)" }}>{t("settings.deleteAccount")}</div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--muted)", marginBottom: 8, lineHeight: 1.5 }}>
            {t("settings.deleteDesc")}
          </div>
          {!showDelete ? (
            <button
              className="btn btn-danger"
              onClick={() => setShowDelete(true)}
              style={{ fontSize: 10, padding: "6px 14px" }}
            >
              {t("settings.deleteAccount")}
            </button>
          ) : (
            <div style={{ background: "rgba(240,68,56,0.04)", border: "1px solid rgba(240,68,56,0.2)", borderRadius: 4, padding: 12, display: "flex", flexDirection: "column", gap: 10 }}>
              {/* Mode selector */}
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  className={`filter-btn${deleteMode === "soft" ? " active" : ""}`}
                  onClick={() => { setDeleteMode("soft"); setDeleteConfirm(""); }}
                  style={{ padding: "4px 12px", fontSize: 9 }}
                >
                  {t("settings.softDelete")}
                </button>
                <button
                  className={`filter-btn${deleteMode === "permanent" ? " active" : ""}`}
                  onClick={() => setDeleteMode("permanent")}
                  style={{ padding: "4px 12px", fontSize: 9 }}
                >
                  {t("settings.permanentDelete")}
                </button>
              </div>

              {deleteMode === "soft" && (
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)", lineHeight: 1.5 }}>
                  {t("settings.softDeleteDesc")}
                </div>
              )}
              {deleteMode === "permanent" && (
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--red)", lineHeight: 1.5 }}>
                  {t("settings.permanentDeleteDesc")}
                </div>
              )}

              <input
                className="form-control"
                type="password"
                placeholder={t("settings.enterPasswordShort")}
                value={deletePwd}
                onChange={e => setDeletePwd(e.target.value)}
                autoComplete="current-password"
              />

              {deleteMode === "permanent" && (
                <input
                  className="form-control"
                  type="text"
                  placeholder={t("settings.typeDelete")}
                  value={deleteConfirm}
                  onChange={e => setDeleteConfirm(e.target.value)}
                  style={{ borderColor: deleteConfirm === "DELETE" ? "var(--red)" : undefined }}
                />
              )}

              {deleteErr && <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--red)" }}>{deleteErr}</div>}

              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn btn-ghost" onClick={() => { setShowDelete(false); setDeletePwd(""); setDeleteConfirm(""); setDeleteErr(null); }} style={{ fontSize: 10, padding: "5px 12px" }}>{t("common.cancel")}</button>
                <button
                  className="btn btn-danger"
                  onClick={handleDelete}
                  disabled={!deletePwd || deleting || (deleteMode === "permanent" && deleteConfirm !== "DELETE")}
                  style={{ fontSize: 10, padding: "5px 12px", opacity: (!deletePwd || deleting || (deleteMode === "permanent" && deleteConfirm !== "DELETE")) ? 0.4 : 1 }}
                >
                  {deleting ? t("settings.deleting") : deleteMode === "permanent" ? t("settings.deletePermanently") : t("settings.scheduleDeletion")}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
