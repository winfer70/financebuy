/**
 * context/I18nContext.jsx
 *
 * React Context for internationalisation (i18n) in TickerTap.
 *
 * Provides:
 *   - `language`     — current language code (e.g. "en", "pl", "de")
 *   - `t`            — translation function: t("nav.dashboard") => "DASHBOARD"
 *   - `setLanguage`  — setter to change UI language (also persists to backend)
 *
 * String tables are loaded lazily from /src/locales/{code}.json.
 * English is always loaded as the fallback so missing keys in other
 * languages gracefully degrade to English text.
 *
 * The language preference is sourced from the user's backend profile
 * (via the `initialLanguage` prop) and kept in sync with SettingsPage
 * through the "preferences-updated" custom event.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

/* ── Static imports for all locale files ─────────────────────────────────── */
// Vite supports JSON imports natively — these are bundled at build time.
import en from "../locales/en.json";
import pl from "../locales/pl.json";
import de from "../locales/de.json";
import zh from "../locales/zh.json";
import es from "../locales/es.json";
import pt from "../locales/pt.json";
import fr from "../locales/fr.json";
import ja from "../locales/ja.json";
import it from "../locales/it.json";

/* ── Locale map ─────────────────────────────────────────────────────────── */
const LOCALES = { en, pl, de, zh, es, pt, fr, ja, it };

/* ── Context creation ────────────────────────────────────────────────────── */
const I18nContext = createContext(null);

/**
 * _resolve — walk a nested object by dot-separated key path.
 *
 * @param {object} obj  - the locale object (e.g. en.json parsed)
 * @param {string} path - dot-separated key (e.g. "nav.dashboard")
 * @returns {string|undefined} the resolved string or undefined
 */
function _resolve(obj, path) {
  const parts = path.split(".");
  let current = obj;
  for (const part of parts) {
    if (current == null || typeof current !== "object") return undefined;
    current = current[part];
  }
  return typeof current === "string" ? current : undefined;
}

/**
 * I18nProvider — wraps the application tree with i18n context.
 *
 * @param {object} props
 * @param {string}          props.initialLanguage - language code from user profile
 * @param {React.ReactNode} props.children
 */
export function I18nProvider({ initialLanguage = "en", children }) {
  const [language, setLanguageState] = useState(initialLanguage);

  /* ── Sync when initialLanguage changes (e.g. profile loaded) ────────── */
  useEffect(() => {
    if (initialLanguage) setLanguageState(initialLanguage);
  }, [initialLanguage]);

  /* ── Listen for preferences-updated events (from SettingsPage) ─────── */
  useEffect(() => {
    /**
     * handlePrefsUpdate — updates local language state when the user
     * saves new preferences via the Settings page.
     * @param {CustomEvent} e - event with detail.language
     */
    function handlePrefsUpdate(e) {
      if (e.detail?.language) {
        setLanguageState(e.detail.language);
      }
    }
    window.addEventListener("preferences-updated", handlePrefsUpdate);
    return () => window.removeEventListener("preferences-updated", handlePrefsUpdate);
  }, []);

  /* ── Translation function ──────────────────────────────────────────── */
  /**
   * t — translate a dot-separated key to the current language string.
   *
   * Falls back to English if the key is missing in the current locale.
   * Falls back to the raw key if missing in both.
   *
   * @param {string} key - dot-separated path, e.g. "nav.dashboard"
   * @returns {string} translated string
   */
  const t = useCallback(
    (key) => {
      const locale = LOCALES[language] || LOCALES.en;
      return _resolve(locale, key) || _resolve(LOCALES.en, key) || key;
    },
    [language],
  );

  /* ── Context value (memoised) ──────────────────────────────────────── */
  const value = useMemo(
    () => ({
      language,
      t,
      setLanguage: setLanguageState,
    }),
    [language, t],
  );

  return (
    <I18nContext.Provider value={value}>
      {children}
    </I18nContext.Provider>
  );
}

/**
 * useI18n — hook to access the i18n context from any component.
 *
 * @returns {{ language: string, t: (key: string) => string, setLanguage: Function }}
 */
export function useI18n() {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    // Fallback for components rendered outside the provider (e.g. auth pages)
    return {
      language: "en",
      t: (key) => _resolve(LOCALES.en, key) || key,
      setLanguage: () => {},
    };
  }
  return ctx;
}
