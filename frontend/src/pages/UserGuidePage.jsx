/**
 * UserGuidePage.jsx — TickerTap User Guide.
 *
 * Two-tab layout:
 *   1. FEATURES — Accordion-style feature explanations for every major section.
 *   2. FAQ      — Common questions with static answers + AI Q&A powered by
 *                 the Ollama-backed /guide/ask endpoint.
 *
 * Props:
 *   @param {string}   token  - JWT access token
 *   @param {Function} goBack - Navigate back callback
 */

import { useState, useCallback } from "react";
import api from "../api/client";
import { Ic } from "../components/common/Icons";

/* ── Feature descriptions (FEATURES tab) ──────────────────────────────────── */
const FEATURES = [
  {
    title: "DASHBOARD",
    icon: "dashboard",
    items: [
      "Portfolio selector dropdown — switch between multiple portfolios",
      "Portfolio performance chart with real OHLCV data and selectable time ranges (1W / 1M / 3M / YTD / 1Y / ALL) — shows 'NO PORTFOLIO DATA AVAILABLE' when no data exists",
      "Market heatmap showing portfolio holdings with gain/loss colour coding — click any tile to view its chart",
      "Key statistics: total portfolio value, unrealised P&L (with all-time %), gain/loss today (with today %), position count",
      "Top Gainers panel — most profitable positions with BEP, Price, CHG (amount + %), and Gain/Loss (value + %) columns",
      "Biggest Losers panel — worst-performing positions with same detailed columns and VIEW ALL button",
      "Category filter tabs (ALL / STOCKS / CRYPTO / ETFs / PHYSICAL) for gainers and losers",
      "Portfolio performance chart displayed full-width above the gainers/losers grid for maximum visibility",
      "Performance chart uses actual purchase dates for accurate growth tracking — gaps on weekends and holidays are automatically filled for smooth, continuous lines",
      "Same-symbol positions consolidated into single rows in top positions",
      "Category filters on both Top Gainers and Biggest Losers panels",
      "Allocation donut chart showing portfolio composition by position — respects display currency symbol",
      "Instant load via stale-while-revalidate caching — fresh data updates in background",
    ],
  },
  {
    title: "PORTFOLIO MANAGER",
    icon: "portfolio",
    items: [
      "Create and manage multiple named portfolios with strategy labels",
      "Four asset types: Stocks, Crypto, ETFs, and Physical Assets (gold, silver, platinum, palladium, copper)",
      "Add positions with full cost-basis tracking: ticker, quantity, purchase date, purchase price, stop-loss, group/tag",
      "Modify positions: update quantity, price, stop-loss, and group/tag",
      "Sell positions with quantity validation against current holding",
      "Exclude/include toggle to remove positions from P&L calculations without deleting",
      "Price change period selector: 1D, 5D, 1M, 3M, 6M, 1Y",
      "Bulk SMA data with visual alerts when price crosses SMA thresholds",
      "CSV import and export for bulk position management",
      "Sortable table columns with colour-coded gain/loss indicators",
      "Cross-page navigation: VIEW CHART and VIEW NEWS per position",
      "Pre-configured metals futures: Gold (GC=F), Silver (SI=F), Platinum (PL=F), Palladium (PA=F), Copper (HG=F)",
      "CHG column shows dollar amount with percentage: $123.45 (+1.23%)",
      "All monetary values respect your display currency preference",
      "Profit Taking column with inline-editable target price — highlights green when price reaches target, pairs with Stop Loss for bracket management",
      "Allocation % column showing each position's weight as a percentage of total portfolio value",
      "Period Gain/Loss in the summary strip — shows portfolio-level gain/loss for the selected change period (1D through 1Y)",
      "Analyst price targets displayed when modifying a position — shows mean, high, and low consensus targets from market analysts",
    ],
  },
  {
    title: "CHARTS",
    icon: "charts",
    items: [
      "Symbol search with autocomplete suggestions and watchlist chip bar with live price changes",
      "Interactive candlestick and line charts with real OHLCV data",
      "Multiple intervals: 1m, 2m, 3m, 5m, 10m, 15m, 30m, 45m, 1h, 2h, 3h, 4h, 1d, 1wk, 1mo",
      "Time periods: 1M, 3M, 6M, 1Y, 2Y, 5Y, ALL (daily) and 100, 500, 1000, ALL bars (intraday)",
      "SMA overlays: 50-period, 150-period, and custom-period with toggle controls",
      "Automatic breakout detection with visual bullish/bearish badge markers",
      "Volume histogram bars (toggle on/off)",
      "Crosshair with hover tooltip showing Date, OHLCV, Change%, and SMA values",
      "Hover data toggle to show/hide OHLCV tooltip (session-persistent)",
      "Drawing tools: trend lines, horizontal lines, rays, rectangles, Fibonacci retracement, pitchfork, arrows, text",
      "Drawing style options: colour picker, line width, line style (solid/dashed/dotted), font size for text",
      "Chart template save/load system — save drawings and overlay settings as named templates",
      "Purchase point indicators showing where you bought positions — uses nearest-bar matching for accurate placement across all intervals",
      "Mouse wheel zoom and click-drag pan across the time axis",
      "Ruler measurement tool — click two points to measure price difference and percentage change between them",
      "Event indicators overlay showing earnings dates (E), dividend dates (D), and stock splits (S) as colour-coded markers at the bottom of the chart",
    ],
  },
  {
    title: "NEWS",
    icon: "news",
    items: [
      "LLM-scored financial news articles with impact ratings (-5 to +5)",
      "Colour-coded sentiment badges: VERY BULLISH, BULLISH, LEAN BULL, NEUTRAL, LEAN BEAR, BEARISH, VERY BEARISH",
      "LLM reasoning text explaining each article's score",
      "Per-ticker impact badges — click for context popup with VIEW CHART and FILTER NEWS actions",
      "Sentiment filtering: ALL, BULLISH, BEARISH",
      "Portfolio toggle that shows only articles relevant to your holdings (combinable with sentiment)",
      "Source badges (YAHOO, GOOGLE, FINVIZ, MKTWATCH) per article",
      "Ticker search with instant filtering",
      "Staleness indicator when newest article is older than 30 minutes",
      "Portfolio-relevant articles are automatically sorted to the top",
      "Watchlist toggle to filter articles by tickers in your watchlists — mutually exclusive with portfolio filter",
      "Server-side filtering and pagination — portfolio, sentiment, and search filters applied before pagination for consistent page sizes (25, 50, 75, or 100 articles per page) with PREV/NEXT navigation",
    ],
  },
  {
    title: "TRANSACTIONS & ORDERS",
    icon: "transactions",
    items: [
      "Transaction history table with columns: TXN ID, Type, Symbol, Amount, Currency, Account, Status, Date",
      "Transaction type filter: ALL, DEPOSIT, WITHDRAWAL, BUY, SELL",
      "Search by transaction ID or symbol",
      "Summary stats: Total Volume, Total Deposits, Total Buys, Completed count, Pending count",
      "Export CSV for transaction records",
      "Order blotter with columns: Order ID, Symbol, Side, Type, Qty, Limit Price, Filled/Total, Status, Placed At",
      "Order filter: ALL, OPEN, FILLED, CANCELLED",
      "Order stats: Total Orders, Open Orders, Filled Orders, Cancelled, Open Notional",
      "Cancel individual orders or cancel all open orders at once",
      "Quick-create transaction/order modal accessible from any page",
    ],
  },
  {
    title: "IMPORT",
    icon: "holdings",
    items: [
      "Broker statement import — supports 8 brokers: Robinhood, IBKR, E*TRADE, TD Ameritrade, Coinbase, Binance, Schwab, Fidelity",
      "Per-broker step-by-step export guides with supported format badges (CSV, XML, OFX, QFX, XLSX)",
      "Drag-and-drop file upload with progress indicator",
      "Manual import — editable position grid with asset type dropdown, symbol, quantity, price, date, notes",
      "Row validation with valid/total counts and staged cost basis summary",
      "Portfolio review tab — review all imported and manual positions before committing",
      "Commit staged positions to your portfolio in one action",
    ],
  },
  {
    title: "DATA IMPORT & EXPORT",
    icon: "holdings",
    items: [
      "Portfolio CSV Export: Downloads all positions as CSV with columns — Ticker, Name, Quantity, Purchase Date, Purchase Price, Asset Type, Group Tag, Stop Loss",
      "Transaction CSV Export: Downloads transaction history with columns — TXN ID, Type, Symbol, Amount, Currency, Account, Status, Date",
      "CSV Import: Upload positions with required columns (Ticker, Quantity, Purchase Price) and optional columns (Name, Date, Asset Type, Group Tag, Stop Loss, Notes)",
      "Broker Statement Import: Supports 8 brokers — Robinhood, IBKR, E*TRADE, TD Ameritrade, Coinbase, Binance, Schwab, Fidelity",
      "Supported file formats: CSV, XML, OFX, QFX, XLSX depending on broker",
      "Review all imported positions on the Portfolio Review tab before committing to your portfolio",
    ],
  },
  {
    title: "TICKER STRIP",
    icon: "holdings",
    items: [
      "Live scrolling market ticker in the top bar",
      "Automatically shows your portfolio tickers when positions exist",
      "Falls back to market index defaults (SPY, QQQ, major tech) when no portfolio",
      "Smart polling: 3s during market hours, 5m after close",
    ],
  },
  {
    title: "SETTINGS",
    icon: "gear",
    items: [
      "View your profile information (email, name, phone, KYC status, account status)",
      "Display currency preference: USD, EUR, GBP, PLN, CHF, JPY, CAD, AUD",
      "Currency conversion uses real-time ECB exchange rates (updated hourly)",
      "Language selection: English, Polish, German, Chinese, Spanish, Portuguese, French, Japanese, Italian",
      "All monetary values convert to your chosen currency for display (data stored in USD)",
      "Preferences are saved to your account and persist across sessions",
    ],
  },
  {
    title: "ACCOUNT & SECURITY",
    icon: "holdings",
    items: [
      "Secure sign-in with email and password, with backend health indicator and feature highlights",
      "Account registration with name, email, and strong password validation (uppercase, lowercase, digit, special character, min 8 chars)",
      "Account lockout after 10 failed login attempts (15-minute cooldown)",
      "Email verification required on registration before first login",
      "Edit name and email from Settings > Account — name changes reflect instantly in the navbar avatar",
      "Email change requires verification on the new address",
      "Deactivate account (disables login, preserves data, reactivate via email link)",
      "Delete account: 30-day soft delete (cancellable via email) or permanent deletion",
      "Forgot password flow with email-based reset link (1-hour expiry)",
      "5-minute inactivity auto-logout for session security",
      "Automatic silent token refresh — no unexpected sign-outs during active use",
      "TLS 1.3 encrypted connections",
      "HSTS and Content Security Policy headers for defence-in-depth",
      "Rate limiting backed by Redis for distributed protection",
      "Browser back/forward navigation works correctly across all pages",
    ],
  },
  {
    title: "WATCHLISTS",
    icon: "watchlist",
    items: [
      "Create unlimited named watchlists to track assets you're interested in",
      "Add stocks, crypto, ETFs, and physical assets to any watchlist",
      "Live price quotes with market-aware polling (3s open / 5m closed)",
      "Detailed table: Symbol, Name, Price, Change ($ + %), Day Range, Since Added %, Notes",
      "Summary strip showing total value, day change, and item count per watchlist",
      "Category filter tabs (ALL / STOCKS / CRYPTO / ETFs / PHYSICAL)",
      "Per-item notes for tracking your thesis or research",
      "Buy directly from watchlist — picks portfolio and enters quantity in a modal",
      "Rename and delete watchlists with confirmation dialogs",
      "Performance since added column tracks asset movement from your watchlist entry price",
    ],
  },
  {
    title: "FEEDBACK & REPORTING",
    icon: "holdings",
    items: [
      "Submit bug reports with subject, category, and description",
      "Suggest improvements through the dedicated feedback form",
      "Report activation issues without authentication",
      "Access feedback from sidebar navigation",
    ],
  },
  {
    title: "INTERFACE",
    icon: "gear",
    items: [
      "Collapsible sidebar (icons-only mode) — preference saved automatically",
      "Breadcrumb in topbar shows translated page names",
      "Sidebar state persisted across sessions",
    ],
  },
  {
    title: "TRADING AI",
    icon: "chart",
    items: [
      "10 built-in strategies: SMA Crossover, EMA Crossover, RSI Mean Reversion, MACD Crossover, Bollinger Squeeze, Stochastic, ADX Trend, VWAP Bounce, Breakout, Ichimoku Cloud",
      "Backtest any strategy on historical OHLCV data with configurable commission, slippage, and date ranges",
      "Full performance metrics: Sharpe ratio, Sortino, max drawdown, win rate, profit factor, Calmar ratio",
      "Equity curve chart and detailed trade log with entry/exit prices and P&L",
      "Market regime detection: trending, mean reverting, or high volatility",
      "PineScript editor: write TradingView-compatible code, syntax validation, and automatic transpilation to executable strategies",
      "LLM fallback: complex PineScript is translated via AI with safety validation (AST whitelist)",
      "Strategy Composer: visually combine indicators (SMA, EMA, RSI, MACD, BB, ATR, ADX, Stochastic, VWAP) with boolean entry/exit expressions",
      "Strategy version history: every edit is snapshotted, view or revert to any previous version",
      "Verified/AI-Translated badges distinguish built-in strategies from user-authored ones",
    ],
  },
];

/* ── FAQ entries (static answers) ─────────────────────────────────────────── */
const FAQ_ITEMS = [
  {
    q: "How do I add a new position to my portfolio?",
    a: 'Navigate to the Portfolio Manager page, select your portfolio, and click the "+ ADD POSITION" button. Choose the asset type (Stock, Crypto, ETF, or Physical), then enter the ticker symbol, quantity, purchase date, purchase price, and optionally a stop-loss and group tag.',
  },
  {
    q: "What asset types are supported?",
    a: "TickerTap supports four asset types: Stocks (equities), Crypto (e.g. BTC-USD, ETH-USD), ETFs (exchange-traded funds), and Physical Assets (gold, silver, platinum, palladium, copper with linked futures tickers like GC=F).",
  },
  {
    q: "What do the news scores mean?",
    a: "Each article is scored from -5 (very bearish) to +5 (very bullish) by an AI model. Scores reflect the predicted market impact. Per-ticker scores show expected impact on individual stocks. You can click a ticker badge for a popup with VIEW CHART and FILTER NEWS actions.",
  },
  {
    q: "Can I change how many news articles are shown per page?",
    a: 'Yes — use the per-page selector (25 / 50 / 75 / 100) at the top of the News page. Navigate between pages using the PREV and NEXT buttons at the bottom.',
  },
  {
    q: "How do I set a stop loss?",
    a: 'Open the Portfolio Manager, find your position, and click the edit (pencil) icon in the Actions column. The Modify Position modal includes a Stop Loss field where you can set your target exit price.',
  },
  {
    q: "Can I export my portfolio data?",
    a: 'Yes! On the Portfolio Manager page, click the "EXPORT CSV" button to download all positions in the current portfolio as a CSV file. The Transactions page also has an Export CSV button for transaction records.',
  },
  {
    q: "How do I import data from my broker?",
    a: 'Go to the Import page (accessible from Portfolio Manager). You can import broker statements from 8 supported brokers (Robinhood, IBKR, E*TRADE, TD Ameritrade, Coinbase, Binance, Schwab, Fidelity) by dragging and dropping your export file. Alternatively, use the Manual Import tab to enter positions one by one in an editable grid. Review everything on the Portfolio Review tab before committing.',
  },
  {
    q: "What format does the CSV export use?",
    a: "Portfolio CSV exports include: Ticker, Name, Quantity, Purchase Date, Purchase Price, Asset Type, Group Tag, and Stop Loss columns. Transaction exports include: TXN ID, Type, Symbol, Amount, Currency, Account, Status, and Date. For CSV import, the required columns are Ticker, Quantity, and Purchase Price — all other columns are optional.",
  },
  {
    q: "What chart intervals are available?",
    a: "TickerTap supports: 1m, 2m, 3m, 5m, 10m, 15m, 30m, 45m, 1h, 2h, 3h, 4h for intraday, and 1d, 1wk, 1mo for daily/weekly/monthly views. Time periods include 1M, 3M, 6M, 1Y, 2Y, 5Y, ALL for daily charts, and 100, 500, 1000, ALL bars for intraday.",
  },
  {
    q: "How do I use the drawing tools on charts?",
    a: "Select a drawing tool from the toolbar (trend line, horizontal line, ray, rectangle, Fibonacci retracement, pitchfork, arrow, or text), then click on the chart to place anchor points. You can customise colour, line width, and line style (solid/dashed/dotted). Use the cursor tool to select drawings, and Delete/Backspace to remove them.",
  },
  {
    q: "What are chart templates?",
    a: "Chart templates let you save your current drawings and overlay settings (SMA toggles, etc.) as a named configuration. Click the save icon on the chart toolbar to create a template, and use the dropdown to load or delete saved templates. Templates are stored on the server and persist across sessions.",
  },
  {
    q: "Why does the ticker strip show different symbols sometimes?",
    a: "The ticker strip shows your portfolio holdings when you have positions. If you have no portfolios or positions, it falls back to popular market symbols (AAPL, MSFT, NVDA, etc.).",
  },
  {
    q: "What does the market status indicator mean?",
    a: 'The green/red dot in the top-right shows whether the NYSE is currently open (9:30 AM – 4:00 PM ET, weekdays). When closed, it shows a countdown to the next market open. Polling frequency adjusts automatically: 3-second updates during market hours, 5-minute updates when closed.',
  },
  {
    q: "How do I change the display currency?",
    a: 'Click the gear icon (Settings) in the sidebar. Under Preferences, select your preferred currency from the dropdown and click "SAVE PREFERENCES". All monetary values across the app will be converted using real-time ECB exchange rates.',
  },
  {
    q: "How do I change the language?",
    a: 'Go to Settings (gear icon in the sidebar), select your preferred language from the dropdown under Preferences, and click "SAVE PREFERENCES". The interface will switch to your chosen language immediately. Available languages: English, Polish, German, Chinese, Spanish, Portuguese, French, Japanese, and Italian.',
  },
  {
    q: "How do I manage orders?",
    a: 'The Orders page shows all your orders in a blotter table. You can filter by status (ALL, OPEN, FILLED, CANCELLED), view summary stats including open notional value, and cancel individual orders or all open orders at once. Use the "PLACE ORDER" button to create a new order.',
  },
  {
    q: "Will I get logged out if I'm inactive?",
    a: "Yes. For security, TickerTap automatically logs you out after 5 minutes of inactivity. Active use (mouse movement, clicks, key presses) resets the timer. Your session token also refreshes silently in the background so you won't be unexpectedly signed out during active use.",
  },
  {
    q: "What does exclude/include do on a position?",
    a: "The exclude toggle in Portfolio Manager removes a position from all P&L calculations without deleting it. This is useful for tracking positions you don't want factored into your performance metrics. You can re-include the position at any time.",
  },
  {
    q: "How do I change my name or email?",
    a: "Go to Settings > Account section. Name changes are instant and update your avatar throughout the app immediately. Email changes require verification on the new address.",
  },
  {
    q: "How do I deactivate or delete my account?",
    a: "Go to Settings > Account. You can deactivate (preserves data, reactivate via email link) or delete (30-day grace period or permanent).",
  },
  {
    q: "How do I report a bug or suggest an improvement?",
    a: "Click Feedback in the sidebar navigation. Choose Report Bug or Suggest Improvement, fill in the form, and submit.",
  },
  {
    q: "What are watchlists and how do I use them?",
    a: 'Watchlists let you track assets you\'re interested in without buying them. Go to the Watchlist page from the sidebar, create a named watchlist, and add items using the "+ ADD ITEM" button. Each item shows live price, day change, price range, and performance since you added it. You can add notes, filter by asset type, and even buy directly from the watchlist into one of your portfolios.',
  },
  {
    q: "Does browser back/forward navigation work?",
    a: "Yes — TickerTap supports full browser back and forward navigation. Clicking sidebar links pushes entries to browser history, so the back button returns you to the previous page. The URL bar also updates to reflect the current page.",
  },
  {
    q: "Why do I need to verify my email?",
    a: "Email verification is required for security. After registration, check your inbox for a verification link before signing in.",
  },
  {
    q: "What is the Profit Taking column?",
    a: "Profit Taking lets you set a target exit price for a position. When the current price meets or exceeds the target, the cell highlights green. You can set it when adding a position or click the pencil icon inline to edit it. It pairs with Stop Loss for complete bracket management.",
  },
  {
    q: "What does Allocation % show in Portfolio Manager?",
    a: "The ALLOC % column shows each position's weight as a percentage of the total portfolio value. It updates in real-time as prices change and helps you monitor concentration risk across your holdings.",
  },
  {
    q: "How do I use the ruler tool on charts?",
    a: "Select the ruler from the drawing tools panel. Click on the chart to set the start point, then move your mouse and click again to lock the endpoint. The ruler displays the price difference and percentage change between the two points with a colour-coded label (green for gain, red for loss).",
  },
  {
    q: "What are event indicators on charts?",
    a: "When the EVENTS overlay is enabled, charts display colour-coded markers at the bottom: 'E' (purple) for earnings dates, 'D' (blue) for dividend ex-dates, and 'S' (yellow) for stock splits. Hovering over a bar with events shows badges in the tooltip with event details.",
  },
  {
    q: "Can I filter news by my watchlist?",
    a: "Yes — click the WATCHLIST toggle button on the News page to show only articles related to tickers in your watchlists. This is mutually exclusive with the PORTFOLIO filter, so activating one deactivates the other.",
  },
  {
    q: "How do I write a PineScript strategy?",
    a: "Go to the Trading page and select the PINESCRIPT mode tab. A code editor with syntax highlighting appears with a default SMA crossover template. Write your strategy using supported ta.* functions (sma, ema, rsi, macd, atr, adx, stoch, vwap, crossover, crossunder), input.* for parameters, and strategy.entry/exit for signals. Click VALIDATE to check syntax, then TRANSPILE & CREATE to compile it into a backtestable strategy.",
  },
  {
    q: "What is the LLM fallback for PineScript?",
    a: "When the deterministic parser can't handle complex PineScript syntax, you can enable the 'LLM fallback' checkbox. This sends your code to a local AI model which translates it into the strategy format. AI-translated strategies receive an 'AI-Translated' badge. The generated code is safety-validated through an AST whitelist before use.",
  },
  {
    q: "How do I compose a strategy without coding?",
    a: "Select the COMPOSE mode on the Trading page. Click indicators from the palette (SMA, EMA, RSI, MACD, etc.) to add them as nodes. Configure each node's parameters (period, source, etc.). Write entry and exit conditions as simple expressions referencing the indicator output variables (e.g. 'sma_0 > sma_1 and rsi_2 < 30'). Click CREATE COMPOSED STRATEGY.",
  },
  {
    q: "Can I view or revert strategy version history?",
    a: "Yes — every time you update a strategy, a version snapshot is automatically saved. Use the API endpoints GET /strategies/{id}/versions to list versions and POST /strategies/{id}/revert/{version} to revert. Version history UI integration is available in the strategy management section.",
  },
];


/* ═══════════════════════════════════════════════════════════════════════════
   COMPONENT
═══════════════════════════════════════════════════════════════════════════ */
export function UserGuidePage({ token, goBack }) {
  const [tab, setTab]             = useState("features"); /* "features" | "faq" */
  const [openIdx, setOpenIdx]     = useState(0);           /* Active accordion index */
  const [aiQuestion, setAiQuestion] = useState("");
  const [aiAnswer, setAiAnswer]   = useState(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError]     = useState(null);

  /**
   * Submit user question to the AI guide endpoint.
   * Sets loading/error/answer states accordingly.
   */
  const handleAskAI = useCallback(async () => {
    const q = aiQuestion.trim();
    if (!q || aiLoading) return;
    setAiLoading(true);
    setAiError(null);
    setAiAnswer(null);
    try {
      const resp = await api.askGuide(q, token);
      setAiAnswer(resp.answer);
    } catch (err) {
      setAiError(err.message || "Failed to get a response. Please try again.");
    } finally {
      setAiLoading(false);
    }
  }, [aiQuestion, aiLoading, token]);

  /** Toggle an accordion section open/closed. */
  const toggleAccordion = (idx) => setOpenIdx(prev => prev === idx ? -1 : idx);

  return (
    <div className="page-scroll">
      {/* Page header */}
      <div className="page-header">
        <div>
          <div className="page-title" style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <button className="btn btn-ghost" onClick={goBack} style={{ padding: "4px 6px" }}>
              <Ic.back />
            </button>
            USER GUIDE
          </div>
          <div className="page-sub">FEATURES · FAQ · AI ASSISTANT</div>
        </div>
      </div>

      <div className="page-inner">
        {/* Tab bar */}
        <div className="filter-bar" style={{ marginBottom: 16 }}>
          <button
            className={`filter-btn${tab === "features" ? " active" : ""}`}
            onClick={() => setTab("features")}
          >
            FEATURES
          </button>
          <button
            className={`filter-btn${tab === "faq" ? " active" : ""}`}
            onClick={() => setTab("faq")}
          >
            FAQ
          </button>
        </div>

        {/* ═══ FEATURES TAB ═══ */}
        {tab === "features" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {FEATURES.map((section, idx) => {
              const IconComp = Ic[section.icon];
              const isOpen = openIdx === idx;
              return (
                <div key={section.title} className="panel" style={{ overflow: "hidden" }}>
                  {/* Accordion header */}
                  <div
                    onClick={() => toggleAccordion(idx)}
                    style={{
                      padding: "12px 16px",
                      display: "flex", alignItems: "center", gap: 12,
                      cursor: "pointer",
                      background: isOpen ? "var(--bg3)" : "transparent",
                    }}
                  >
                    {IconComp && <span style={{ color: "var(--amber)" }}><IconComp /></span>}
                    <span style={{
                      fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 600,
                      letterSpacing: "0.5px", color: "var(--bright)", flex: 1,
                    }}>
                      {section.title}
                    </span>
                    <span style={{
                      fontFamily: "var(--font-mono)", fontSize: 10,
                      color: "var(--muted)", transition: "transform 0.2s",
                      transform: isOpen ? "rotate(90deg)" : "rotate(0deg)",
                    }}>
                      ▶
                    </span>
                  </div>

                  {/* Accordion body */}
                  {isOpen && (
                    <div style={{ padding: "8px 16px 14px 46px" }}>
                      {section.items.map((item, i) => (
                        <div key={i} style={{
                          fontFamily: "var(--font-mono)", fontSize: 11,
                          color: "var(--mid)", lineHeight: 1.6,
                          paddingLeft: 12, position: "relative",
                        }}>
                          <span style={{
                            position: "absolute", left: 0, color: "var(--amber)",
                          }}>·</span>
                          {item}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* ═══ FAQ TAB ═══ */}
        {tab === "faq" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {/* Static FAQ items */}
            {FAQ_ITEMS.map((item, idx) => (
              <div key={idx} className="panel" style={{ padding: "12px 16px" }}>
                <div style={{
                  fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 600,
                  color: "var(--bright)", marginBottom: 6, letterSpacing: "0.3px",
                }}>
                  Q: {item.q}
                </div>
                <div style={{
                  fontFamily: "var(--font-mono)", fontSize: 11,
                  color: "var(--mid)", lineHeight: 1.5,
                }}>
                  {item.a}
                </div>
              </div>
            ))}

            {/* AI Q&A section */}
            <div className="panel" style={{ padding: "16px" }}>
              <div style={{
                fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 600,
                color: "var(--amber)", marginBottom: 10, letterSpacing: "0.5px",
              }}>
                ASK AI ASSISTANT
              </div>
              <div style={{
                fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)",
                marginBottom: 10,
              }}>
                Have a question not covered above? Ask our AI assistant about any TickerTap feature.
              </div>

              {/* Input row */}
              <div style={{ display: "flex", gap: 8 }}>
                <input
                  className="search-input"
                  placeholder="Type your question..."
                  value={aiQuestion}
                  onChange={e => setAiQuestion(e.target.value)}
                  onKeyDown={e => { if (e.key === "Enter") handleAskAI(); }}
                  style={{ flex: 1 }}
                  maxLength={500}
                />
                <button
                  className="btn btn-primary"
                  onClick={handleAskAI}
                  disabled={!aiQuestion.trim() || aiLoading}
                  style={{ padding: "6px 16px" }}
                >
                  {aiLoading ? "ASKING..." : "ASK"}
                </button>
              </div>

              {/* AI error */}
              {aiError && (
                <div style={{
                  marginTop: 10, padding: "8px 12px",
                  fontFamily: "var(--font-mono)", fontSize: 11,
                  color: "var(--red)", background: "rgba(240,68,56,0.06)",
                  border: "1px solid rgba(240,68,56,0.2)", borderRadius: 2,
                }}>
                  {aiError}
                </div>
              )}

              {/* AI answer */}
              {aiAnswer && (
                <div style={{
                  marginTop: 10, padding: "10px 14px",
                  fontFamily: "var(--font-mono)", fontSize: 11,
                  color: "var(--mid)", lineHeight: 1.6,
                  background: "var(--bg3)", border: "1px solid var(--border)",
                  borderLeft: "2px solid var(--amber)", borderRadius: 2,
                  whiteSpace: "pre-wrap",
                }}>
                  {aiAnswer}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
