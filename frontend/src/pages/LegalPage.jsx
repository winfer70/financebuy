/**
 * LegalPage.jsx — Legal information page for TickerTap.
 *
 * Renders three tabbed sections: Financial Disclaimer, Privacy Policy,
 * and Terms of Service. Operates in two modes:
 *
 *  - Standalone (prop `standalone`): Full-viewport layout with its own
 *    header and back button, used when accessed from auth pages
 *    (login, register, etc.) before the user is authenticated.
 *
 *  - In-shell (default): Standard page-scroll layout rendered inside
 *    AppShell for authenticated users navigating from the footer.
 *
 * All legal content is defined as internal sub-components
 * (DisclaimerContent, PrivacyContent, TermsContent) to keep the
 * top-level component focused on layout and tab switching.
 */

import { useState, useEffect } from "react";

/* ── Tab definitions ─────────────────────────────────────────────────────── */
const TABS = [
  { id: "disclaimer", label: "FINANCIAL DISCLAIMER" },
  { id: "privacy",    label: "PRIVACY POLICY" },
  { id: "terms",      label: "TERMS OF SERVICE" },
];

/* ═══════════════════════════════════════════════════════════════════════════
   CONTENT COMPONENTS — one per legal section
═══════════════════════════════════════════════════════════════════════════ */

/**
 * DisclaimerContent — Financial disclaimer section.
 * Covers: not financial advice, AI scoring caveats, market data source,
 * past performance, and assumption of risk.
 */
function DisclaimerContent() {
  return (
    <div className="legal-content">
      <div className="legal-effective-date">EFFECTIVE DATE: MARCH 5, 2026</div>

      <section className="legal-section">
        <div className="legal-section-title">NOT FINANCIAL ADVICE</div>
        <p className="legal-text">
          TickerTap is a portfolio tracking and informational tool only. Nothing
          displayed on this platform &mdash; including market data, portfolio
          analytics, charts, and AI-generated scores &mdash; constitutes financial
          advice, investment recommendations, or solicitations to buy, sell, or
          hold any security or financial instrument.
        </p>
        <p className="legal-text">
          TickerTap is not a registered broker-dealer, investment adviser, or
          financial institution. The operator of this platform is not licensed to
          provide financial services or investment guidance.
        </p>
      </section>

      <section className="legal-section">
        <div className="legal-section-title">AI-GENERATED CONTENT</div>
        <p className="legal-text">
          TickerTap uses a local large language model (Llama 3 via Ollama) to
          generate impact scores and analysis for financial news articles. These
          scores are algorithmic outputs, not expert opinions. They are produced
          automatically without human review and may be inaccurate, incomplete,
          or misleading.
        </p>
        <ul className="legal-list">
          <li>AI scores reflect pattern matching, not market expertise or insider knowledge</li>
          <li>Scores may not account for breaking developments, corrections, or context</li>
          <li>Model outputs should never be the sole basis for any investment decision</li>
          <li>
            Scores range from &minus;5 (bearish) to +5 (bullish) and represent the
            model&apos;s interpretation of news sentiment, not a prediction of price movement
          </li>
        </ul>
      </section>

      <section className="legal-section">
        <div className="legal-section-title">MARKET DATA</div>
        <p className="legal-text">
          Market data displayed on TickerTap is sourced from Yahoo Finance and is
          provided on an as-is basis. Data may be delayed, inaccurate, or
          incomplete. TickerTap does not guarantee the timeliness, accuracy, or
          completeness of any market data.
        </p>
        <p className="legal-text">
          Real-time quotes are subject to Yahoo Finance&apos;s data availability
          and may not reflect actual market prices at the time of viewing.
        </p>
      </section>

      <section className="legal-section">
        <div className="legal-section-title">PAST PERFORMANCE</div>
        <p className="legal-text">
          Past performance of any security, portfolio, or strategy displayed on
          TickerTap is not indicative of future results. Historical data and
          portfolio performance metrics are shown for informational purposes only
          and should not be interpreted as a guarantee of future returns.
        </p>
      </section>

      <section className="legal-section">
        <div className="legal-section-title">ASSUMPTION OF RISK</div>
        <p className="legal-text">
          All investment decisions are made at your own risk. You acknowledge that
          investing in securities involves risk of loss, including the potential
          loss of principal. TickerTap shall not be liable for any financial
          losses incurred as a result of using this platform or relying on
          information displayed herein.
        </p>
        <p className="legal-text">
          You are solely responsible for conducting your own due diligence and
          consulting with a qualified financial professional before making any
          investment decisions.
        </p>
      </section>
    </div>
  );
}

/**
 * PrivacyContent — Privacy policy section.
 * Covers: data collected, usage, storage, third-party sharing,
 * retention, user rights, and cookies/local storage.
 */
function PrivacyContent() {
  return (
    <div className="legal-content">
      <div className="legal-effective-date">EFFECTIVE DATE: MARCH 5, 2026</div>

      <section className="legal-section">
        <div className="legal-section-title">OVERVIEW</div>
        <p className="legal-text">
          TickerTap is a self-hosted application. Your data is stored on
          infrastructure controlled by the platform operator. This privacy policy
          describes what data is collected, how it is used, and your rights
          regarding that data.
        </p>
      </section>

      <section className="legal-section">
        <div className="legal-section-title">DATA WE COLLECT</div>

        <div className="legal-subsection-title">Account Information</div>
        <ul className="legal-list">
          <li>Email address (used for authentication and password recovery)</li>
          <li>First and last name (used for display purposes)</li>
          <li>Hashed password (Argon2id &mdash; your plaintext password is never stored)</li>
        </ul>

        <div className="legal-subsection-title">Portfolio Data</div>
        <ul className="legal-list">
          <li>Portfolio names and descriptions you create</li>
          <li>Securities holdings (ticker symbols, quantities, purchase prices, dates)</li>
          <li>Transaction history (buys, sells, deposits, withdrawals)</li>
          <li>Order records (limit orders, market orders, stop orders)</li>
        </ul>

        <div className="legal-subsection-title">Usage Data</div>
        <ul className="legal-list">
          <li>Authentication timestamps and session activity</li>
          <li>Audit log entries for security-relevant actions (login, password changes)</li>
        </ul>
      </section>

      <section className="legal-section">
        <div className="legal-section-title">HOW WE USE YOUR DATA</div>
        <ul className="legal-list">
          <li>To authenticate you and maintain your session</li>
          <li>To display your portfolio, holdings, and transaction history</li>
          <li>To fetch market data for securities in your portfolio</li>
          <li>To generate AI-scored news relevant to your holdings</li>
          <li>To send password reset emails when requested</li>
        </ul>
        <p className="legal-text">
          TickerTap does not use your data for advertising, profiling, or
          marketing purposes.
        </p>
      </section>

      <section className="legal-section">
        <div className="legal-section-title">DATA STORAGE AND SECURITY</div>
        <p className="legal-text">
          All data is stored in a PostgreSQL database on self-hosted
          infrastructure. Data is not transmitted to or stored on third-party
          cloud services beyond what is described in this policy.
        </p>
        <ul className="legal-list">
          <li>Authentication uses JWT tokens stored in your browser&apos;s sessionStorage (cleared when the browser tab closes)</li>
          <li>Passwords are hashed using Argon2id before storage</li>
          <li>All connections use TLS encryption in transit</li>
          <li>Session tokens expire automatically and are refreshed transparently</li>
          <li>An inactivity timer automatically logs you out after 5 minutes of inactivity</li>
        </ul>
      </section>

      <section className="legal-section">
        <div className="legal-section-title">THIRD-PARTY DATA SHARING</div>
        <p className="legal-text">
          TickerTap does not sell, rent, or share your personal data with third
          parties. The only external service interactions are:
        </p>
        <ul className="legal-list">
          <li>
            <strong>Yahoo Finance API:</strong> Ticker symbols from your portfolio are
            sent to Yahoo Finance to retrieve market data. No personal information
            (name, email, account details) is transmitted
          </li>
          <li>
            <strong>SMTP provider (if configured):</strong> Your email address is
            transmitted to the configured email service solely for sending password
            reset links
          </li>
        </ul>
      </section>

      <section className="legal-section">
        <div className="legal-section-title">DATA RETENTION</div>
        <p className="legal-text">
          Your data is retained for as long as your account exists. Transaction
          history and audit logs are retained for the lifetime of your account to
          maintain data integrity and security audit trails.
        </p>
      </section>

      <section className="legal-section">
        <div className="legal-section-title">YOUR RIGHTS</div>
        <ul className="legal-list">
          <li>
            <strong>Access:</strong> You can view all data associated with your
            account through the application interface
          </li>
          <li>
            <strong>Correction:</strong> You can update your profile information
            through account settings
          </li>
          <li>
            <strong>Deletion:</strong> You may request complete deletion of your
            account and all associated data by contacting the platform operator.
            Account deletion cascades to all portfolio data, transactions, holdings,
            and orders
          </li>
          <li>
            <strong>Export:</strong> Portfolio and transaction data can be viewed and
            exported through the application interface
          </li>
        </ul>
      </section>

      <section className="legal-section">
        <div className="legal-section-title">COOKIES AND LOCAL STORAGE</div>
        <p className="legal-text">
          TickerTap does not use cookies. Authentication tokens are stored in
          sessionStorage (not localStorage), meaning they are automatically
          cleared when you close the browser tab. A single localStorage key is
          used solely for inactivity tracking to protect your session. No
          tracking cookies, analytics cookies, or third-party cookies are used.
        </p>
      </section>
    </div>
  );
}

/**
 * TermsContent — Terms of service section.
 * Covers: acceptance, service description, account responsibilities,
 * acceptable use, IP, availability, liability, warranties,
 * termination, changes, governing law, and contact.
 */
function TermsContent() {
  return (
    <div className="legal-content">
      <div className="legal-effective-date">EFFECTIVE DATE: MARCH 5, 2026</div>

      <section className="legal-section">
        <div className="legal-section-title">ACCEPTANCE OF TERMS</div>
        <p className="legal-text">
          By accessing or using TickerTap, you agree to be bound by these Terms of
          Service. If you do not agree to these terms, you must not use the
          platform.
        </p>
      </section>

      <section className="legal-section">
        <div className="legal-section-title">SERVICE DESCRIPTION</div>
        <p className="legal-text">
          TickerTap is a self-hosted portfolio tracking application that provides
          market data visualization, portfolio management, and AI-scored financial
          news. It is not a brokerage, trading platform, or financial advisory
          service. No actual securities transactions are executed through TickerTap.
        </p>
      </section>

      <section className="legal-section">
        <div className="legal-section-title">ACCOUNT RESPONSIBILITIES</div>
        <ul className="legal-list">
          <li>You must provide accurate information when creating an account</li>
          <li>You are responsible for maintaining the security of your login credentials</li>
          <li>You must not share your account with others</li>
          <li>You must notify the platform operator immediately of any unauthorized access</li>
          <li>You must be at least 18 years of age to use this service</li>
        </ul>
      </section>

      <section className="legal-section">
        <div className="legal-section-title">ACCEPTABLE USE</div>
        <p className="legal-text">
          You agree to use TickerTap only for its intended purpose as a portfolio
          tracking tool. You must not:
        </p>
        <ul className="legal-list">
          <li>Attempt to gain unauthorized access to the platform or its infrastructure</li>
          <li>Use automated tools to scrape data or overload the service</li>
          <li>Circumvent rate limits or security measures</li>
          <li>Use the platform for any unlawful purpose</li>
          <li>Interfere with other users&apos; access to the service</li>
          <li>Reverse engineer, decompile, or attempt to extract the source code</li>
        </ul>
      </section>

      <section className="legal-section">
        <div className="legal-section-title">INTELLECTUAL PROPERTY</div>
        <p className="legal-text">
          The TickerTap name, logo, design, and source code are the property of the
          platform operator. The Bloomberg-inspired visual design is an original
          work and does not imply any affiliation with Bloomberg L.P.
        </p>
        <p className="legal-text">
          Market data displayed is sourced from Yahoo Finance and is subject to
          Yahoo Finance&apos;s own terms of service. AI-generated content is
          produced by open-source language models and is not claimed as proprietary
          analysis.
        </p>
      </section>

      <section className="legal-section">
        <div className="legal-section-title">SERVICE AVAILABILITY</div>
        <p className="legal-text">
          TickerTap is provided on an &ldquo;as is&rdquo; and &ldquo;as
          available&rdquo; basis. The platform operator does not guarantee
          uninterrupted, error-free, or secure operation of the service. The
          service may be modified, suspended, or discontinued at any time without
          prior notice.
        </p>
        <ul className="legal-list">
          <li>Market data availability depends on Yahoo Finance API uptime</li>
          <li>AI scoring depends on the availability of the local Ollama instance</li>
          <li>Scheduled or unscheduled maintenance may cause temporary service interruptions</li>
        </ul>
      </section>

      <section className="legal-section">
        <div className="legal-section-title">LIMITATION OF LIABILITY</div>
        <p className="legal-text">
          To the maximum extent permitted by applicable law, the platform operator
          shall not be liable for any indirect, incidental, special, consequential,
          or punitive damages, including but not limited to:
        </p>
        <ul className="legal-list">
          <li>Financial losses resulting from investment decisions influenced by platform data</li>
          <li>Loss of data due to system failures or security incidents</li>
          <li>Service interruptions or unavailability</li>
          <li>Inaccuracies in market data, portfolio calculations, or AI-generated scores</li>
          <li>Unauthorized access to your account due to compromised credentials</li>
        </ul>
        <p className="legal-text">
          The platform operator&apos;s total liability for any claims arising from
          use of the service shall not exceed the amount you have paid for the
          service (which, for a free application, is zero).
        </p>
      </section>

      <section className="legal-section">
        <div className="legal-section-title">DISCLAIMER OF WARRANTIES</div>
        <p className="legal-text">
          TickerTap is provided without warranties of any kind, whether express or
          implied, including but not limited to implied warranties of
          merchantability, fitness for a particular purpose, and non-infringement.
          The platform operator does not warrant that market data is accurate, that
          AI scores are reliable, or that the service will meet your requirements.
        </p>
      </section>

      <section className="legal-section">
        <div className="legal-section-title">ACCOUNT TERMINATION</div>
        <p className="legal-text">
          The platform operator reserves the right to suspend or terminate your
          account at any time for violation of these terms or for any other reason.
          You may delete your account at any time by contacting the platform
          operator.
        </p>
      </section>

      <section className="legal-section">
        <div className="legal-section-title">CHANGES TO TERMS</div>
        <p className="legal-text">
          These terms may be updated at any time. Continued use of the platform
          after changes are posted constitutes acceptance of the modified terms.
          Material changes will be communicated through the platform interface
          where practical.
        </p>
      </section>

      <section className="legal-section">
        <div className="legal-section-title">GOVERNING LAW</div>
        <p className="legal-text">
          These terms shall be governed by and construed in accordance with the
          laws of the jurisdiction in which the platform is operated, without
          regard to conflict of law provisions.
        </p>
      </section>

      <section className="legal-section">
        <div className="legal-section-title">CONTACT</div>
        <p className="legal-text">
          For questions regarding these terms, privacy concerns, or account
          deletion requests, contact the platform operator at the email address
          provided during platform setup.
        </p>
      </section>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   LEGAL PAGE — Main exported component
═══════════════════════════════════════════════════════════════════════════ */

/**
 * LegalPage — Tabbed legal information page.
 *
 * @param {object}   props
 * @param {string}   props.initialTab  - "disclaimer" | "privacy" | "terms"
 * @param {Function} props.onBack      - Navigation callback (returns to previous page)
 * @param {boolean}  [props.standalone] - If true, renders full-viewport layout
 *                                         for unauthenticated users
 * @returns {JSX.Element}
 */
export function LegalPage({ initialTab = "disclaimer", onBack, standalone }) {
  const [activeTab, setActiveTab] = useState(initialTab);

  /* Sync active tab when navigated via footer links while already mounted */
  useEffect(() => { setActiveTab(initialTab); }, [initialTab]);

  /* ── Shared tab bar (used by both render modes) ──────────────────────── */
  const tabBar = (
    <div className="legal-tabs">
      {TABS.map(t => (
        <button
          key={t.id}
          className={`legal-tab${activeTab === t.id ? " active" : ""}`}
          onClick={() => setActiveTab(t.id)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );

  /* ── Shared content area ─────────────────────────────────────────────── */
  const content = (
    <div className="page-inner">
      {activeTab === "disclaimer" && <DisclaimerContent />}
      {activeTab === "privacy"    && <PrivacyContent />}
      {activeTab === "terms"      && <TermsContent />}
    </div>
  );

  /* ── Standalone mode (unauthenticated — full-viewport) ───────────────── */
  if (standalone) {
    return (
      <div className="legal-standalone">
        <div className="legal-standalone-header">
          <span
            style={{
              fontFamily: "var(--font-disp)",
              fontSize: 22,
              color: "var(--amber)",
              letterSpacing: 2,
            }}
          >
            TT
          </span>
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 11,
              color: "var(--muted)",
              letterSpacing: 1,
            }}
          >
            TICKER-TAP
          </span>
          <button className="legal-back-btn" onClick={onBack}>
            &larr; BACK TO SIGN IN
          </button>
        </div>
        {tabBar}
        <div className="legal-standalone-body">
          {content}
        </div>
      </div>
    );
  }

  /* ── In-shell mode (authenticated — standard page layout) ────────────── */
  return (
    <div className="page-scroll">
      <div className="page-header">
        <div>
          <div className="page-title" style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <button
              className="btn btn-ghost"
              onClick={onBack}
              style={{ padding: "4px 8px", fontSize: 14 }}
            >
              &larr;
            </button>
            LEGAL
          </div>
          <div className="page-sub">
            FINANCIAL DISCLAIMER &middot; PRIVACY POLICY &middot; TERMS OF SERVICE
          </div>
        </div>
      </div>
      {tabBar}
      {content}
    </div>
  );
}
