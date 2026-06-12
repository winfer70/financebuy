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
      "KPI cards strip showing key portfolio metrics at a glance",
      "Asset Ribbon — proportional bar across the top showing portfolio weight by asset type (Stocks, Crypto, ETFs, Physical), colour-coded by day P&L intensity",
      "Concentration chips highlighting over-weight positions as a quick risk summary",
      "QuickSell drawer — click any position tile to open a right-edge slide-in drawer with ticker, quantity, and average cost; place a sell directly from the Dashboard",
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
      "Trade History tab — view the complete buy and sell trade log for the portfolio with entry/exit prices, P&L per trade, and aggregate trade statistics",
      "Delete individual trade records from the Trade History tab",
      "Cash Balance Adjustment — click the cash adjustment button in the Portfolio Manager header to open a modal and manually add or subtract cash from the portfolio's cash balance",
      "Detailed portfolio score with per-position P&L breakdown, concentration analysis, and diversification metrics",
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
      "Drawing tools: trend lines, horizontal lines, extended horizontal lines, vertical lines, rays, rectangles, parallel channels, Fibonacci retracement, pitchfork, arrows, text, ruler, price range, callout",
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
      "Export CSV — generates and downloads a CSV file of the currently displayed transactions",
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
      "Broker statement import — demo/preview only: shows a sample walkthrough for Robinhood, IBKR, E*TRADE, TD Ameritrade, Coinbase, Binance, Schwab, and Fidelity. Full broker CSV parsing coming soon.",
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
      "Broker Statement Import: Currently a demo/preview — displays a sample walkthrough for Robinhood, IBKR, E*TRADE, TD Ameritrade, Coinbase, Binance, Schwab, and Fidelity. Full broker CSV parsing coming soon.",
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
      "Smart polling: 30s during market hours, 5m after close",
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
      "Live price quotes with market-aware polling (30s open / 5m closed)",
      "Detailed table: Symbol, Name, Price, Change ($ + %), Day Range, Since Added %, Notes",
      "Summary strip showing total value, day change, and item count per watchlist",
      "Category filter tabs (ALL / STOCKS / CRYPTO / ETFs / PHYSICAL)",
      "Per-item notes for tracking your thesis or research",
      "Buy directly from watchlist — picks portfolio and enters quantity in a modal",
      "Rename and delete watchlists with confirmation dialogs",
      "Performance since added column tracks asset movement from your watchlist entry price",
      "Sortable columns — click any column header (Symbol, Name, Price, Change, Day Range, Since Added %, Notes) to sort the watchlist table ascending or descending",
      "Stale data banner — a warning banner appears when price quotes are more than 5 minutes old, prompting a manual refresh",
    ],
  },
  {
    title: "PRICE ALERTS",
    icon: "bell",
    items: [
      "Create price alerts from Charts, Watchlist, or Portfolio Manager pages using the bell button",
      "Set conditions: above, below, or crosses a target price",
      "Manage all alerts from the dedicated ALERTS page in the sidebar",
      "Filter alerts by Active, Triggered, or All",
      "Edit target price, condition, and notes inline",
      "Alerts are checked every 60 seconds during market hours (every 5 minutes outside market hours)",
      "Triggered alerts generate in-app notifications and automatically deactivate",
      "Maximum 50 active alerts per user",
    ],
  },
  {
    title: "ASSET DETAILS",
    icon: "holdings",
    items: [
      "Click the ⓘ info button next to any ticker on the Portfolio Manager, Watchlist, or Charts page to open the Asset Details panel",
      "Company overview: name, sector, industry, full-time employees, and business summary",
      "Valuation metrics: P/E ratio, forward P/E, PEG ratio, price-to-book, price-to-sales, and enterprise value",
      "Financial health: profit margin, operating margin, ROE, ROA, revenue growth, current ratio, and debt-to-equity",
      "Dividends: dividend rate, yield, payout ratio, and ex-dividend date",
      "Analyst targets: mean, median, high, and low price targets with a visual bar showing current price relative to the range",
      "Earnings: most recent quarterly EPS, revenue, and earnings dates",
      "Trading info: market cap, 52-week high/low, average volume, beta, and float shares",
      "Fundamental data is cached for 1 hour to balance freshness with performance",
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
      "Keyboard shortcuts system — press '?' anywhere to open the shortcuts modal showing all available keyboard shortcuts",
      "Global navigation shortcuts: 'g' then 'd' (Dashboard), 'g' then 'w' (Watchlist), 'g' then 'p' (Portfolio Manager), 'g' then 't' (Trading), 'g' then 'n' (News), 'g' then 'c' (Charts) — 1500ms window to complete the two-key sequence",
      "Keyboard shortcuts are disabled when focus is inside an input, textarea, or select element",
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
      "Interactive backtest chart with scroll-wheel zoom, click-drag pan, 9 drawing tools, chart type/overlay toggles, and stats bar (same features as the Charts page)",
      "Market regime detection: trending, mean reverting, or high volatility",
      "PineScript editor: write TradingView-compatible code, syntax validation, and automatic transpilation to executable strategies",
      "LLM fallback: complex PineScript is translated via AI with safety validation (AST whitelist)",
      "Strategy Composer: visually combine indicators (SMA, EMA, RSI, MACD, BB, ATR, ADX, Stochastic, VWAP) with boolean entry/exit expressions",
      "Strategy version history: every edit is snapshotted, view or revert to any previous version",
      "Verified/AI-Translated badges distinguish built-in strategies from user-authored ones",
    ],
  },
  {
    title: "PAPER TRADING",
    icon: "📊",
    items: [
      {
        heading: "Overview",
        text: "Paper trading lets you simulate live trading with virtual capital. Your chosen strategy evaluates real market data every 60 seconds, automatically generating buy/sell signals and managing positions — all without risking real money.",
      },
      {
        heading: "Starting a Paper Trade",
        text: "Open the PAPER tab in Trading AI, select a strategy and symbol, set your initial capital (default $10,000), then click START. The system will begin monitoring the market and executing simulated trades based on your strategy's signals.",
      },
      {
        heading: "Managing Sessions",
        text: "Active paper trades can be paused (temporarily halt signal evaluation), resumed, or stopped permanently. Stopping a session closes all open positions and locks in the final equity. Use the detail view to monitor equity curves and position history in real time.",
      },
      {
        heading: "Circuit Breaker",
        text: "A built-in safety mechanism automatically stops a paper trade if the drawdown exceeds 15% from peak equity. This protects your simulated portfolio from runaway losses and teaches risk management discipline.",
      },
      {
        heading: "Equity & Positions",
        text: "Each paper trade tracks an equity curve updated every evaluation cycle. View your position history (entry/exit prices, P&L) and overall performance metrics. Use this data to refine your strategy before considering real trading.",
      },
    ],
  },
  {
    title: "MARKETPLACE",
    icon: "marketplace",
    items: [
      "Strategy Marketplace: browse, search, filter, and sort publicly shared trading strategies by category, timeframe, and rating",
      "Featured strategies: top-rated public strategies highlighted at the top of the marketplace",
      "Rate and review public strategies (1–5 stars with optional text review)",
      "Clone any public strategy to your own account with one click",
      "Strategy stats: view clone count, average rating, rating count, and backtest count for any strategy",
      "Publish/unpublish your strategies to share them on the marketplace",
      "Strategy Comparison: select 2–3 strategies and run side-by-side backtests with overlaid equity curves and metric comparison table",
      "Batch Backtest: run a strategy across all your watchlist symbols at once (up to 20 symbols)",
      "One-click order creation from trade log entries — pre-fills symbol, side, quantity, and price",
      "CSV export of backtest results including summary metrics and full trade log",
    ],
  },
  {
    title: "LEARNING CENTER",
    icon: "charts",
    items: [
      "Educational content page with rich topic material — no account or API required, all content loads instantly",
      "Three difficulty levels: BEGINNER (green), INTERMEDIATE (amber), ADVANCED (red) with colour-coded tab buttons",
      "Beginner topics (7): What Are Stocks, Understanding Price Charts, Basic Order Types, Portfolio Basics, Dividends & Income, Reading Financial News, Risk Management Basics",
      "Intermediate topics (7): Technical Indicators, Chart Patterns, Fundamental Analysis, Sector Analysis, Options Basics, Fair Value Gap (FVG) Trading, Backtesting Strategies",
      "Advanced topics (6): Advanced Technical Analysis, Algorithmic Trading Concepts, Portfolio Optimization, Market Microstructure, Macroeconomic Factors, Psychology & Behavioral Finance",
      "Rich topic content — each topic includes an intro paragraph, detailed bullet points, PRO TIP callout boxes with practical advice, and DID YOU KNOW callout boxes with interesting facts",
      "Accordion-style topic cards with emoji/icon on each card header — click to expand/collapse with smooth animation",
      "Only one card expanded at a time per tab; switching tabs auto-expands the first topic",
      "Progress tracking — mark topics as read with a checkbox, progress bar per difficulty level showing completion percentage, and completion badges when all topics in a level are finished",
      "'Try It in TickerTap' navigation links on each topic — click to jump directly to the relevant page (Charts, Trading, Portfolio, Research, etc.)",
    ],
  },
  {
    title: "RESEARCH",
    icon: "charts",
    items: [
      "SECTORS tab — heat-map grid of 11 GICS sector ETFs (XLK, XLF, XLV, XLE, XLY, XLP, XLI, XLB, XLRE, XLU, XLC) colour-coded by daily change percentage",
      "Each sector card shows current price, daily change %, YTD %, 1-month % performance, and a sparkline chart showing recent performance trend",
      "Improved sector card grid layout with better spacing for visual clarity",
      "Click any sector card to auto-filter the screener to that sector's stocks",
      "SCREENER tab — stock screener with filters for price range, change %, volume, and sector",
      "Sort screener results by symbol, price, change, volume, or market cap in ascending or descending order",
      "Results table displays symbol, company name, price, daily change ($ and %), volume, and market cap for each stock",
      "Action buttons on screener results — view chart, add to watchlist, or add to portfolio directly from the results row",
      "Screener covers a universe of approximately 100 widely traded stocks across all 11 sectors",
      "Clickable ticker symbols in the screener open the Charts page for that stock",
    ],
  },
  {
    title: "EXIT POINTS",
    icon: "orders",
    items: [
      "Enter any ticker symbol, select an analysis period, and click ANALYZE to compute exit levels",
      "Overview panel showing current price, trend badge (bullish/bearish/neutral), RSI, ATR value, and support/resistance zones",
      "ATR-based stop-loss levels at 1.5x, 2x, and 3x ATR below the current price",
      "Take-profit targets calculated at 1:2 and 1:3 reward-to-risk ratios relative to ATR stops",
      "Fibonacci retracement levels (23.6%, 38.2%, 50%, 61.8%, 78.6%) based on the 52-week high/low range",
      "Bollinger Band levels (upper, middle, lower) for volatility-based exit zones",
      "Moving average levels — SMA 50, SMA 200, and EMA 21 — as potential support/resistance points",
      "52-week high and low values displayed as reference boundaries",
      "Visual price ladder showing all computed levels arranged vertically relative to the current price",
      "Sortable levels table with colour-coded type badges (stop-loss, take-profit, Fibonacci, indicator, boundary)",
      "Trend analysis and RSI reading help contextualize which exit levels are most relevant",
    ],
  },
  {
    title: "PORTFOLIO RULES",
    icon: "trading",
    items: [
      "Rules engine analyses every position in a portfolio against 8 configurable rules and generates actionable alerts — accessible from the RULES tab inside Portfolio Manager",
      "Run rules manually with the ▶ RUN RULES button, or select a schedule: On demand, Auto — market hours (re-runs every 60s during trading hours), or Auto — end of day",
      {
        heading: "House Money Rule",
        text: "Fires when a position has gained enough that the original capital has been returned and you are now trading with profit only — suggests locking in a portion of gains.",
      },
      {
        heading: "Stop Proximity Rule",
        text: "Triggers a warning when the current price is within 5% of the stop-loss level, and a critical alert when within 2% — prompting you to review the position before an automatic stop is hit.",
      },
      {
        heading: "Semi-Cap Concentration Rule",
        text: "Warns when a semiconductor position exceeds the configured maximum allocation percentage of the total portfolio value — helps manage sector concentration risk.",
      },
      {
        heading: "Bucket Balance Rule",
        text: "Analyses positions grouped by bucket tags (e.g. Core, Growth, Speculative) and alerts when any bucket is overweight or underweight relative to configured target ranges.",
      },
      {
        heading: "Time Stop Rule",
        text: "Warns when a position has been held for longer than expected trading sessions without reaching its profit target — highlights positions that may be consuming capital unproductively.",
      },
      {
        heading: "Analyst Consensus Rule",
        text: "Alerts when the current price is significantly above the analyst consensus price target — a signal to reassess whether the position still has upside potential.",
      },
      {
        heading: "Fundamentals Health Rule",
        text: "Checks debt-to-equity ratio, gross margin trend, and insider trading activity — fires warning or critical alerts when fundamentals deteriorate.",
      },
      {
        heading: "Pre-Earnings Rule",
        text: "Fires an informational alert 1–2 business days before a scheduled earnings date so you can decide whether to reduce size or hedge before the event.",
      },
      "Alerts have severity levels: INFO (informational), WARNING (review recommended), and CRITICAL (immediate attention required)",
      "Filter alerts by severity and state — use the chip filters to show only active, snoozed, or actioned alerts",
      "Mark alerts as ACTIONED once reviewed, or SNOOZE to temporarily hide them — actioned alerts are dimmed and excluded from the active count badge on the RULES tab",
    ],
  },
  {
    title: "ADMIN DASHBOARD",
    icon: "admin",
    items: [
      "Admin-only page accessible from the ADMIN link in the sidebar — restricted to users whose email is listed in the server's ADMIN_EMAILS configuration",
      "Non-admin users see an 'Access Denied' message when attempting to access the page",
      "USERS tab — view all registered users, lock or unlock accounts, and search/filter by email or name",
      "REPORTS tab — filter reports by status and type, expand any report to see full details, update status and admin notes, or delete reports",
      "AUDIT LOG tab — view the 100 most recent system actions with old and new value diffs, filter entries by action type",
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
    a: 'Yes! On the Portfolio Manager page, click the "EXPORT CSV" button to download all positions in the current portfolio as a CSV file. The Transactions page also has an Export CSV button that generates and downloads a CSV file of your current transaction data.',
  },
  {
    q: "How do I import data from my broker?",
    a: 'Go to the Import page (accessible from Portfolio Manager). The broker statement import section is currently a demo/preview — it shows a sample walkthrough for supported brokers (Robinhood, IBKR, E*TRADE, TD Ameritrade, Coinbase, Binance, Schwab, Fidelity), but full CSV parsing is coming soon. In the meantime, use the Manual Import tab to enter positions one by one in an editable grid. Review everything on the Portfolio Review tab before committing.',
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
    a: "Select a drawing tool from the toolbar (trend line, horizontal line, extended horizontal line, vertical line, ray, rectangle, parallel channel, Fibonacci retracement, pitchfork, arrow, text, ruler, price range, or callout), then click on the chart to place anchor points. You can customise colour, line width, and line style (solid/dashed/dotted). Use the cursor tool to select drawings, and Delete/Backspace to remove them.",
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
    a: 'The green/red dot in the top-right shows whether the NYSE is currently open (9:30 AM – 4:00 PM ET, weekdays). When closed, it shows a countdown to the next market open. Polling frequency adjusts automatically: 30-second updates during market hours, 5-minute updates when closed.',
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
    q: "What is the Portfolio Rules engine?",
    a: "The Portfolio Rules engine analyses your positions against 8 configurable rules and generates alerts in the RULES tab of Portfolio Manager. Rules check things like stop proximity, analyst consensus, fundamentals health, earnings timing, sector concentration, and more. Run rules manually or set a schedule to run automatically during market hours.",
  },
  {
    q: "What do the rule alert severity levels mean?",
    a: "INFO alerts are informational reminders (e.g. earnings tomorrow). WARNING alerts suggest reviewing a position (e.g. price near stop loss). CRITICAL alerts flag positions that may need immediate action (e.g. price within 2% of stop). You can SNOOZE an alert to hide it temporarily, or MARK ACTIONED once you have reviewed and acted on it.",
  },
  {
    q: "How do I set up automatic rule scanning?",
    a: "In the RULES tab of Portfolio Manager, open the schedule dropdown next to the ▶ RUN RULES button and select 'Auto — market hours' or 'Auto — end of day', then click ▶ RUN RULES once to register the schedule. The worker will continue re-running the analysis automatically according to the selected schedule.",
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
    q: "How do price alerts work?",
    a: "Create alerts from any page with the bell button or from the ALERTS page. Set a condition (above, below, or crosses) and a target price. The system checks prices every 60 seconds during market hours. When triggered, you receive an in-app notification and the alert is automatically deactivated. You can manage all alerts from the ALERTS page in the sidebar.",
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
  {
    q: "Does the Trading page chart support zoom, pan, and drawing tools?",
    a: "Yes — the backtest chart on the Trading page now has the same interactive features as the Charts page: scroll-wheel zoom, click-drag pan, 9 drawing tools (trend line, horizontal line, ray, rectangle, Fibonacci retracement, pitchfork, arrow, text, ruler), chart type toggle (candle/line), overlay toggles (volume, SMA 50, SMA 200), and a stats bar showing OHLCV values plus a 52-week range indicator. Drawings are persisted per symbol in local storage.",
  },
  {
    q: "How do I share my strategy on the marketplace?",
    a: "Open the Marketplace page and find your strategy, or use the PUBLISH button on the Trading page. Toggling publish makes your strategy visible to all users. Other users can browse, rate, and clone it. You can unpublish at any time.",
  },
  {
    q: "How do I compare strategies?",
    a: "On the Trading page, switch to the COMPARE tab in the bottom panel. Select 2–3 strategies from the dropdown, then click COMPARE. The system runs backtests for each strategy on the same symbol and period, then displays side-by-side metrics (Sharpe, return, drawdown, win rate, etc.) and overlaid equity curves.",
  },
  {
    q: "What is batch backtest?",
    a: "Batch backtest lets you run a single strategy across all your watchlist symbols at once (up to 20). Click 'RUN ON WATCHLIST' on the Trading page, then switch to the BATCH tab to see results for each symbol including return, Sharpe, win rate, and drawdown.",
  },
  {
    q: "How do I export backtest results?",
    a: "After running a backtest, click the 'EXPORT CSV' button next to the RUN BACKTEST button. This downloads a CSV file with a summary of metrics followed by the full trade log.",
  },
  {
    q: "What is paper trading and how does it work?",
    a: "Paper trading simulates live trading using real market data but virtual money. Select a strategy and symbol in the PAPER tab, set your capital, and start. The system evaluates your strategy every 60 seconds, automatically opening and closing positions based on signals. No real money is at risk.",
  },
  {
    q: "Why did my paper trade stop automatically?",
    a: "The circuit breaker trips when drawdown exceeds 15% from peak equity, automatically stopping the trade and closing all positions. This built-in safety mechanism prevents excessive simulated losses. You can start a new paper trade with adjusted parameters.",
  },
  {
    q: "How do I view fundamental data for a stock?",
    a: 'Click the ⓘ info button next to any ticker in the Portfolio Manager, Watchlist, or Charts page. This opens the Asset Details panel showing company info, valuation metrics (P/E, PEG, P/B, etc.), financial health (margins, ROE, debt ratios), dividends, analyst price targets with a visual range bar, earnings, and trading metrics. Data is refreshed every hour.',
  },
  {
    q: "What is the Learning Center?",
    a: "The Learning Center is a static educational page accessible from the LEARNING link in the sidebar. It covers stock trading and investing concepts across three difficulty levels: Beginner (7 topics covering stocks, charts, orders, portfolio basics, dividends, news, and risk management), Intermediate (7 topics on technical indicators, chart patterns, fundamental analysis, sectors, options, FVG trading, and backtesting), and Advanced (6 topics on advanced technicals, algorithmic trading, portfolio optimization, market microstructure, macroeconomics, and behavioral finance).",
  },
  {
    q: "How do I navigate the Learning Center?",
    a: "Use the three colour-coded tab buttons at the top — BEGINNER (green), INTERMEDIATE (amber), ADVANCED (red) — to switch difficulty levels. Within each level, click any topic card header to expand it and read the content. Only one card is expanded at a time; clicking another card closes the previous one. Switching tabs automatically opens the first topic.",
  },
  {
    q: "How do I use the stock screener?",
    a: "Go to the RESEARCH page from the sidebar. The SECTORS tab shows a heat-map grid of 11 sector ETFs colour-coded by daily performance — click any sector card to auto-filter the screener to that sector. Switch to the SCREENER tab to set filters for price range, change %, volume, and sector, then click SCAN. Results show symbol, name, price, change, volume, and market cap. You can sort by any column and click a ticker symbol to open its chart.",
  },
  {
    q: "What are exit points and how do I use them?",
    a: "The EXIT POINTS page computes key price levels to help you plan trade exits. Enter a ticker, select an analysis period, and click ANALYZE. The tool calculates ATR-based stop-loss levels (1.5x, 2x, 3x ATR), take-profit targets (1:2 and 1:3 reward-to-risk), Fibonacci retracement levels, Bollinger Band boundaries, and moving averages (SMA 50, SMA 200, EMA 21). Results include an overview panel with trend, RSI, and support/resistance zones, a visual price ladder showing all levels, and a sortable table with colour-coded type badges.",
  },
  {
    q: "How do I access the admin dashboard?",
    a: "Click ADMIN in the sidebar. Access is restricted to users whose email is listed in the server's ADMIN_EMAILS configuration. Non-admin users will see an 'Access Denied' message. The dashboard provides user management, report review, and audit log viewing.",
  },
  {
    q: "How do I use keyboard shortcuts?",
    a: "Press '?' anywhere on the page (when not typing in a field) to open the keyboard shortcuts modal. Navigation shortcuts use a two-key sequence starting with 'g': g+d for Dashboard, g+w for Watchlist, g+p for Portfolio Manager, g+t for Trading, g+n for News, g+c for Charts. The second key must be pressed within 1500ms of pressing 'g'. Shortcuts are disabled when an input, textarea, or select element has focus.",
  },
  {
    q: "What is the QuickSell drawer on the Dashboard?",
    a: "Clicking a position tile on the Dashboard opens the QuickSell drawer — a slide-in panel from the right edge showing the ticker, your current quantity, and average cost. You can enter a sell quantity and submit a sell order directly without navigating to the Portfolio Manager.",
  },
  {
    q: "How do I view trade history in Portfolio Manager?",
    a: "Switch to the Trade History tab in the Portfolio Manager. It shows a complete log of all buy and sell trades for the selected portfolio, including entry/exit prices, P&L per trade, and aggregate trade statistics. You can also delete individual trade records from this tab.",
  },
  {
    q: "How do I adjust the cash balance in my portfolio?",
    a: "In the Portfolio Manager header, click the cash adjustment button (typically a +/- or wallet icon). A modal opens where you can enter a positive amount to add cash or a negative amount to subtract it. This is useful for reflecting real cash deposits or withdrawals in your tracked portfolio.",
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
                          {/* Support both plain string items and {heading, text} objects */}
                          {typeof item === "string" ? item : (
                            <>
                              <span style={{ color: "var(--bright)", fontWeight: 600 }}>
                                {item.heading}:
                              </span>{" "}
                              {item.text}
                            </>
                          )}
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
