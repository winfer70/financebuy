# Graph Report - .  (2026-06-02)

## Corpus Check
- 172 files · ~326,249 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 2070 nodes · 7810 edges · 120 communities detected
- Extraction: 29% EXTRACTED · 71% INFERRED · 0% AMBIGUOUS · INFERRED: 5543 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## God Nodes (most connected - your core abstractions)
1. `User` - 154 edges
2. `AuditLog` - 114 edges
3. `Strategy` - 95 edges
4. `YFinanceProvider` - 93 edges
5. `Notification` - 92 edges
6. `NormalizedDataService` - 90 edges
7. `PaperTrade` - 78 edges
8. `PaperTradePosition` - 78 edges
9. `PaperTradeEquitySnapshot` - 78 edges
10. `BacktestResult` - 76 edges

## Surprising Connections (you probably didn't know these)
- `main.py — FastAPI application entry point for TickerTap.  Configures middlewar` --uses--> `Strategy`  [INFERRED]
  backend\app\main.py → backend\app\models.py
- `Insert system strategy templates if the strategies table is empty.      Reads` --uses--> `Strategy`  [INFERRED]
  backend\app\main.py → backend\app\models.py
- `Validate critical configuration on startup.      Performs the following checks` --uses--> `Strategy`  [INFERRED]
  backend\app\main.py → backend\app\models.py
- `Injects security headers on every response.      Provides a defence-in-depth l` --uses--> `Strategy`  [INFERRED]
  backend\app\main.py → backend\app\models.py
- `Reject requests whose Content-Length exceeds MAX_REQUEST_BODY_BYTES.      Prev` --uses--> `Strategy`  [INFERRED]
  backend\app\main.py → backend\app\models.py

## Hyperedges (group relationships)
- **Strategy Creation and Testing Ecosystem** — trading_CompositionEditor, trading_PineScriptEditor, trading_StrategyComparison, trading_PaperTradingPanel, trading_ParameterEditor [INFERRED 0.85]
- **Interactive Chart Drawing System** — charts_OHLCVChart, charts_DrawingTools, common_Icons [EXTRACTED 1.00]
- **Preferences Event Bus** — pages_settingspage, context_currencycontext, context_i18ncontext [EXTRACTED 1.00]
- **Portfolio Data Shared via sessionStorage** — context_authcontext, pages_dashboardpage, pages_portfoliomanagerpage [EXTRACTED 0.95]
- **Live Quotes Consumer Group** — context_quotescontext, pages_dashboardpage, pages_alertspage [EXTRACTED 0.90]
- **Auth Registration Lifecycle Pages** — auth_registerpage, auth_verifyemailpage, auth_loginpage [EXTRACTED 0.95]
- **Trading AI Feature Dependencies** — trading_ai_fullplan, backend_requirements_deps, tradingml_requirements_deps [INFERRED 0.85]
- **Two-Server News Pipeline Context Group** — news_research_feasibilitystudy, serverbworker_requirements_deps, concept_two_server_news_pipeline [INFERRED 0.85]

## Communities

### Community 0 - "Backend Accounts and Auth API"
Cohesion: 0.02
Nodes (264): admin_check(), list_audit_logs(), list_users(), lock_account(), lock_user(), _toggle_account_status(), _toggle_user_status(), unlock_account() (+256 more)

### Community 1 - "React Frontend Pages"
Cohesion: 0.01
Nodes (27): apiFetch(), _tryRefreshToken(), Buy-from-Watchlist Portfolio Integration, ExitPointsPage(), fmtUsd(), PriceLadder(), EMPTY_ENTRY(), handleDrop() (+19 more)

### Community 2 - "Trading ML Models and Strategies"
Cohesion: 0.2
Nodes (183): LLMTranspileError, Raised when LLM translation or validation fails., MarketDataProvider, BacktestResult, Notification, PaperTrade, PaperTradeEquitySnapshot, PaperTradePosition (+175 more)

### Community 3 - "Admin API Endpoints"
Cohesion: 0.05
Nodes (155): admin.py — Admin-only routes for TickerTap.  Provides endpoints for user and a, Lock or unlock a brokerage account atomically.      Eliminates duplication bet, List all registered users, ordered newest-first.      Args:         db: Async, Deactivate a user account, preventing further login.      Existing JWT tokens, Reactivate a previously locked user account.      Args:         user_id: UUID, Set an account's status to 'locked', blocking trading operations.      Args:, Restore an account's status to 'active', re-enabling trading.      Args:, Retrieve audit log entries for admin review.      Args:         user_id: Opti (+147 more)

### Community 4 - "PineScript Grammar and Parser"
Cohesion: 0.02
Nodes (108): Exception, _get_parser(), parse(), _preprocess_kwargs(), PineScript Grammar — lark EBNF grammar for the supported PineScript subset.  D, Lazily create and return the lark parser (cached singleton).      Returns:, Result from PineScript validation.      Attributes:         valid:  True if s, Convert keyword arguments into marker-pair positional arguments.      Transfor (+100 more)

### Community 5 - "FastAPI App and Middleware"
Cohesion: 0.03
Nodes (80): BaseHTTPMiddleware, limiter.py — Shared SlowAPI rate-limiter instance for TickerTap.  Centralised, health(), main.py — FastAPI application entry point for TickerTap.  Configures middlewar, Validate critical configuration on startup.      Performs the following checks, Injects security headers on every response.      Provides a defence-in-depth l, Reject requests whose Content-Length exceeds MAX_REQUEST_BODY_BYTES.      Prev, Logs every request with method, path, status code, and duration.      Paths co (+72 more)

### Community 6 - "Market Data Provider"
Cohesion: 0.11
Nodes (78): _aggregate_bars(), ExchangeRateResponse, _fetch_earnings_dates_set(), _fetch_events(), _fetch_exchange_rates(), _fetch_fundamentals(), _fetch_ohlcv(), _fetch_ohlcv_interval() (+70 more)

### Community 7 - "Portfolio Holdings"
Cohesion: 0.06
Nodes (52): _assert_account_owner(), Config, HoldingOut, list_holdings(), holdings.py — Holdings (portfolio positions) routes for TickerTap.  Exposes a, Output schema for a single holding position.      Attributes:         holding, Verify the account belongs to the given user. Raises HTTP 403 if not.      Use, List holdings for the given account with pagination (P7.3).      Ownership of (+44 more)

### Community 8 - "News Article Queue (NATS)"
Cohesion: 0.04
Nodes (62): cleanup_dead_letters(), _connect(), enqueue(), enqueue_batch(), get_pending(), increment_retries(), init_db(), mark_done() (+54 more)

### Community 9 - "Trading Metrics and Analytics"
Cohesion: 0.07
Nodes (42): annualized_return(), avg_loss(), avg_win(), benchmark_comparison(), calmar_ratio(), compute_all(), expectancy(), max_drawdown() (+34 more)

### Community 10 - "Feature Classifier (ML)"
Cohesion: 0.08
Nodes (31): _adx(), _atr(), _bollinger_pctb(), _build_train_data(), _ema(), _engineer_features(), FeatureClassifier, _get_top_features() (+23 more)

### Community 11 - "Technical Indicators"
Cohesion: 0.07
Nodes (31): adx(), atr(), bollinger_bands(), crossover(), crossunder(), ema(), highest(), lowest() (+23 more)

### Community 12 - "Trading ML API"
Cohesion: 0.08
Nodes (30): FeatureResponse, health(), _load_models(), LSTMResponse, OHLCVRow, PatternResponse, predict_features(), predict_lstm() (+22 more)

### Community 13 - "Strategy Executor"
Cohesion: 0.1
Nodes (27): _call_indicator(), _check_stop_loss(), _compute_indicators(), _eval_comparison(), _eval_condition(), _eval_logical(), _extract_price_series(), _generate_signals() (+19 more)

### Community 14 - "Pattern Classifier (ML)"
Cohesion: 0.1
Nodes (18): _bars_to_ohlc_ratios(), _build_pattern_sequences(), PatternClassifier, _PatternCNN, models/pattern_classifier.py — 1D-CNN candlestick pattern classifier.  Classif, Train / fine-tune the CNN on labelled candle data.          Args:, Persist CNN weights to disk., Load CNN weights if a checkpoint exists. (+10 more)

### Community 15 - "Market Regime Detector (HMM)"
Cohesion: 0.1
Nodes (17): _compute_hmm_features(), _quick_adx(), models/regime_detector.py — Market regime detector (HMM + rule-based).  Classi, Train the HMM on market data.          Args:             symbol: Ticker for l, Run HMM prediction on market features.          Args:             bars: OHLCV, Map HMM state indices to regime labels based on feature means.          After, Create default HMM (will need training before use)., Persist HMM and state mapping to disk. (+9 more)

### Community 16 - "Email Templates"
Cohesion: 0.17
Nodes (21): _action_button(), email.py — Email sending utilities for TickerTap.  Provides a generic send_ema, Generate a styled call-to-action button for emails.      Args:         url: T, Send an email via the configured SMTP server.      Args:         to_email: Re, Send a password reset email with a one-time link.      Args:         to_email, Send an email verification link for new account registration.      Args:, Send a verification email to the NEW email address for an email change.      A, Send an account reactivation email with a one-time link.      Args:         t (+13 more)

### Community 17 - "Chart Templates"
Cohesion: 0.21
Nodes (21): create_template(), delete_template(), get_template(), _get_template_or_404(), list_templates(), routes/chart_templates.py — Chart Template CRUD API endpoints.  Provides CRUD, Partially update a chart template (ownership enforced)., Delete a chart template (ownership enforced). (+13 more)

### Community 18 - "OHLCV Archiver"
Cohesion: 0.11
Nodes (21): _aggregate_5min(), archive_intraday(), _daily_downsample(), downsample_daily(), _fetch_and_store_bars(), _get_active_symbols(), _is_market_open(), trading/archiver.py — Intraday data archiver worker.  Background worker that: (+13 more)

### Community 19 - "Events and Earnings Zones"
Cohesion: 0.15
Nodes (19): _get_dividend_zones(), _get_earnings_zones(), _get_fomc_zones(), get_no_trade_zones(), _get_opex_dates(), _get_opex_zones(), is_in_no_trade_zone(), NoTradeZone (+11 more)

### Community 20 - "Module Group 20"
Cohesion: 0.12
Nodes (13): _get_cached(), _is_market_open(), YFinance Provider — MarketDataProvider implementation backed by yfinance.  Wra, Fetch OHLCV bars from yfinance and return normalised OHLCVBars.          Args:, Fetch the latest quote for *symbol* from yfinance.          Args:, Search for symbols matching *query* via yfinance.          Args:, Synchronous OHLCV fetch from yfinance.          Args:             sym:, Synchronous quote fetch from yfinance.          Args:             sym: Upper- (+5 more)

### Community 21 - "Module Group 21"
Cohesion: 0.15
Nodes (17): _call_indicator(), _compute_composed_indicators(), _eval_expression(), _eval_node(), _generate_composed_signals(), Strategy Composition Engine — evaluates a graph of indicator nodes and boolean, Recursively validate every node in the expression AST.      Args:         nod, Evaluate a pre-validated expression against a variable namespace.      Args: (+9 more)

### Community 22 - "Module Group 22"
Cohesion: 0.18
Nodes (17): API Client, AuthContext, CurrencyContext, I18nContext, QuotesContext, AdminPage, AlertsPage, DashboardPage (+9 more)

### Community 23 - "Module Group 23"
Cohesion: 0.17
Nodes (15): analyse_with_ollama(), build_analysis_prompt(), compute_statistics(), fetch_outcomes(), main(), _parse_analysis_json(), post_rules(), learner.py — TickerTap scoring accuracy analyser for Server B (REDACTED_HOST).  Standal (+7 more)

### Community 24 - "Module Group 24"
Cohesion: 0.17
Nodes (15): build_learning_prompt(), compute_strategy_stats(), fetch_backtest_history(), learn_with_ollama(), main(), _parse_learning_json(), post_strategy_rules(), strategy_learner.py — Strategy performance learner for Server B (REDACTED_HOST).  Analy (+7 more)

### Community 25 - "Module Group 25"
Cohesion: 0.17
Nodes (15): build_research_prompt(), fetch_recent_backtests(), fetch_regime_summary(), main(), _parse_research_json(), post_recommendations(), strategy_researcher.py — Strategy research agent for Server B (REDACTED_HOST).  Standal, Fetch current market regime summary from Server A.      Returns:         Dict (+7 more)

### Community 26 - "Module Group 26"
Cohesion: 0.22
Nodes (11): atr_based(), fixed_dollar(), fixed_percentage(), fractional_kelly(), kelly(), PositionSizer, engine/risk.py — Position sizing and risk management models.  Provides the ``P, Automatically choose and apply the best sizing model.          Prefers ATR-bas (+3 more)

### Community 27 - "Module Group 27"
Cohesion: 0.22
Nodes (9): hitTestDrawing(), moveOneAnchor(), pixelToAnchor(), pointToSegmentDist(), renderDrawing(), renderPreview(), resolveAnchorX(), resolveAnchorY() (+1 more)

### Community 28 - "Module Group 28"
Cohesion: 0.18
Nodes (13): App Root Component, AppShell Authenticated Shell, PageRouter Auth Page Router, Drawing Tools Utilities, OHLCV Candlestick Chart, Price Alert Modal, SVG Icon Library, Notification Bell Dropdown (+5 more)

### Community 29 - "Module Group 29"
Cohesion: 0.29
Nodes (9): BreakerStatus, check_circuit_breaker(), check_drawdown(), engine/circuit_breaker.py — Drawdown circuit breaker for strategy risk control., Check and enforce the circuit breaker for a strategy.      Loads recent backte, Execute circuit breaker trip: deactivate signals, notify, and log.      Args:, Result of a circuit breaker check.      Attributes:         tripped:        T, Check if the equity curve's drawdown exceeds the threshold.      Computes the (+1 more)

### Community 30 - "Module Group 30"
Cohesion: 0.27
Nodes (9): DecayResult, detect_decay(), detect_decay_for_strategy(), engine/decay.py — Strategy performance decay detection.  Monitors rolling stra, Load recent backtest results for a strategy and check for decay.      Queries, Compute rolling annualised Sharpe ratios.      Args:         returns:       B, Result of a strategy decay check.      Attributes:         is_decaying:    Tr, Detect performance decay from an equity curve.      Computes rolling Sharpe ra (+1 more)

### Community 31 - "Module Group 31"
Cohesion: 0.22
Nodes (5): _dedupe_and_sort(), Normalized Data Service — single entry point for strategy data consumption.  S, Fetch aligned OHLCV data at multiple intervals.          Intraday intervals ar, Read bars from the intraday_bars TimescaleDB hypertable.          Args:, Fetch normalised OHLCV bars for a single symbol and interval.          For int

### Community 32 - "Module Group 32"
Cohesion: 0.29
Nodes (7): ask_guide(), GuideAskRequest, GuideAskResponse, routes/guide.py — User Guide AI Q&A endpoint.  Proxies user questions to the O, Schema for a user question submitted to the guide endpoint.      Attributes:, Schema for the guide endpoint response.      Attributes:         answer: The, Submit a question to the TickerTap AI guide.      Proxies the question to the

### Community 33 - "Module Group 33"
Cohesion: 0.32
Nodes (7): generate_signals(), indicator_outputs(), ADX Trend Strategy — enter on strong trend confirmation via ADX.  Enter long w, Expose indicator series for the composition engine.      Args:         bars:, Wilder's smoothing (used in ADX/DI calculations).      Args:         values:, Generate entry/exit signals based on ADX trend strength.      Args:         b, _wilder_smooth()

### Community 34 - "Module Group 34"
Cohesion: 0.32
Nodes (7): _ema(), generate_signals(), indicator_outputs(), EMA Crossover Strategy — trend-following using exponential moving averages.  F, Compute exponential moving average series.      Args:         closes: List of, Generate entry/exit signals based on EMA crossover.      Args:         bars:, Expose indicator series for the composition engine.      Args:         bars:

### Community 35 - "Module Group 35"
Cohesion: 0.32
Nodes (7): generate_signals(), indicator_outputs(), _period_high_low(), Ichimoku Cloud Strategy — trend-following using Ichimoku Kinko Hyo components., Expose indicator series for the composition engine.      Args:         bars:, Compute highest high and lowest low over a lookback window.      Args:, Generate entry/exit signals based on Ichimoku Cloud.      Args:         bars:

### Community 36 - "Module Group 36"
Cohesion: 0.32
Nodes (7): _ema(), generate_signals(), indicator_outputs(), MACD Crossover Strategy — trend-following using MACD line/signal crossovers., Expose indicator series for the composition engine.      Args:         bars:, Compute EMA series (SMA-seeded)., Generate entry/exit signals based on MACD crossover.      Args:         bars:

### Community 37 - "Module Group 37"
Cohesion: 0.32
Nodes (7): generate_signals(), indicator_outputs(), RSI Mean Reversion Strategy — fade overbought/oversold RSI readings.  Enter lo, Expose indicator series for the composition engine.      Args:         bars:, Compute RSI series using Wilder's smoothing.      Args:         closes: List, Generate entry/exit signals based on RSI mean reversion.      Args:         b, _rsi()

### Community 38 - "Module Group 38"
Cohesion: 0.32
Nodes (7): generate_signals(), indicator_outputs(), SMA Crossover Strategy — trend-following using simple moving average crossovers., Compute simple moving average series.      Args:         closes: List of clos, Generate entry/exit signals based on SMA crossover.      Args:         bars:, Expose indicator series for the composition engine.      Args:         bars:, _sma()

### Community 39 - "Module Group 39"
Cohesion: 0.32
Nodes (7): _compute_vwap(), generate_signals(), indicator_outputs(), VWAP Bounce Strategy — intraday mean reversion around VWAP.  Enter long when p, Compute cumulative VWAP series.      Args:         bars: Chronological OHLCV, Generate entry/exit signals based on VWAP bounce.      Args:         bars:, Expose indicator series for the composition engine.      Args:         bars:

### Community 40 - "Module Group 40"
Cohesion: 0.48
Nodes (6): _close_position(), evaluate_paper_trades(), _evaluate_single_trade(), _get_session(), _signal_to_action(), startup()

### Community 41 - "Module Group 41"
Cohesion: 0.33
Nodes (7): DeactivatedAccountPage, LoginPage, RegisterPage, VerifyEmailPage, Auth Registration Lifecycle, Deactivated Account Recovery Flow, Rationale: Demo Credentials via Env Vars

### Community 42 - "Module Group 42"
Cohesion: 0.33
Nodes (5): env.py — Alembic migration environment for TickerTap.  DATABASE_URL environmen, Run migrations in 'offline' mode (no live DB connection required).      Genera, Run migrations against a live database connection., run_migrations_offline(), run_migrations_online()

### Community 43 - "Module Group 43"
Cohesion: 0.33
Nodes (5): downgrade(), 0011_user_preferences — Add JSONB preferences column to users table.  Stores u, Add preferences JSONB column to users table., Remove preferences column from users table., upgrade()

### Community 44 - "Module Group 44"
Cohesion: 0.33
Nodes (5): downgrade(), 0012_reports_email_verify — Add email verification, account management, and use, Remove email_verification_tokens, user_reports, and user account columns., Add email verification columns, user_reports table, and email_verification_token, upgrade()

### Community 45 - "Module Group 45"
Cohesion: 0.33
Nodes (5): downgrade(), 0013_watchlists_account_lockout — Add account lockout columns and watchlist/wat, Remove watchlist_items, watchlists tables, and lockout columns from users., Add lockout columns to users, create watchlists and watchlist_items tables., upgrade()

### Community 46 - "Module Group 46"
Cohesion: 0.33
Nodes (5): downgrade(), 0014_profit_taking — Add profit-taking target price column to portfolio positio, Add profit_taking column to portfolio_positions., Remove profit_taking column from portfolio_positions., upgrade()

### Community 47 - "Module Group 47"
Cohesion: 0.33
Nodes (5): downgrade(), 0015_trading_strategies — Trading AI core tables.  Creates four tables require, Drop trading AI core tables in reverse dependency order., Create trading AI core tables., upgrade()

### Community 48 - "Module Group 48"
Cohesion: 0.4
Nodes (5): _get_avg_sentiment(), engine/filters.py — Signal filters that gate entry/exit signals.  Provides com, Filter a trading signal based on recent news sentiment scores.      Looks up t, Compute average sentiment score for *symbol* over recent articles.      Querie, sentiment_filter()

### Community 49 - "Module Group 49"
Cohesion: 0.33
Nodes (5): generate_signals(), indicator_outputs(), Bollinger Band Squeeze Strategy — volatility breakout from Bollinger Band contra, Generate entry/exit signals based on Bollinger Band squeeze breakout.      Arg, Expose indicator series for the composition engine.      Args:         bars:

### Community 50 - "Module Group 50"
Cohesion: 0.33
Nodes (5): generate_signals(), indicator_outputs(), Breakout Strategy — enter on price breaking above N-bar high with volume confirm, Generate entry/exit signals based on price breakout with volume.      Args:, Expose indicator series for the composition engine.      Args:         bars:

### Community 51 - "Module Group 51"
Cohesion: 0.33
Nodes (5): generate_signals(), indicator_outputs(), Stochastic Oscillator Strategy — mean reversion using %K/%D crossovers.  Enter, Generate entry/exit signals based on Stochastic Oscillator.      Args:, Expose indicator series for the composition engine.      Args:         bars:

### Community 52 - "Module Group 52"
Cohesion: 0.5
Nodes (1): initial  Revision ID: 0001_initial Revises: Create Date: 2026-01-09 00:00:00

### Community 53 - "Module Group 53"
Cohesion: 0.5
Nodes (1): integrity fixes  Fix malformed server_defaults (nested quotes), add CASCADE de

### Community 54 - "Module Group 54"
Cohesion: 0.5
Nodes (1): add portfolios and portfolio_positions tables  Adds the portfolios and portfol

### Community 55 - "Module Group 55"
Cohesion: 0.5
Nodes (1): Add asset_type and physical_type to portfolio_positions.  Revision ID: 0006_as

### Community 56 - "Module Group 56"
Cohesion: 0.5
Nodes (1): Add stop_loss to portfolio_positions.  Revision ID: 0007_stop_loss Revises: 0

### Community 57 - "Module Group 57"
Cohesion: 0.5
Nodes (1): Create chart_templates table.  Revision ID: 0008_chart_templates Revises: 000

### Community 58 - "Module Group 58"
Cohesion: 0.5
Nodes (1): Create news_articles and news_article_tickers tables.  Adds the two tables req

### Community 59 - "Module Group 59"
Cohesion: 0.5
Nodes (1): Create score_outcomes and scoring_rules tables for the feedback loop.  Adds th

### Community 60 - "Module Group 60"
Cohesion: 0.5
Nodes (1): 0016_intraday_bars — TimescaleDB hypertable for intraday OHLCV data.  Creates

### Community 61 - "Module Group 61"
Cohesion: 0.5
Nodes (1): 0017_notifications — Notification and webhook tables.  Creates:   - notificat

### Community 62 - "Module Group 62"
Cohesion: 0.5
Nodes (1): 0018_social_strategies — Strategy ratings and usage tracking tables.  Creates:

### Community 63 - "Module Group 63"
Cohesion: 0.5
Nodes (1): 0019_paper_trading — Paper trading simulation tables.  Creates:   - paper_tra

### Community 64 - "Module Group 64"
Cohesion: 0.67
Nodes (2): fmtVol(), OHLCVChart()

### Community 65 - "Module Group 65"
Cohesion: 0.5
Nodes (4): Backend Python Requirements, Trading AI Architecture Decisions, Trading AI 6-Phase Implementation Plan, Trading ML Container Python Requirements

### Community 66 - "Module Group 66"
Cohesion: 0.67
Nodes (0): 

### Community 67 - "Module Group 67"
Cohesion: 0.67
Nodes (3): Strategy Composition Editor, PineScript Code Editor, Strategy Backtest Comparison

### Community 68 - "Module Group 68"
Cohesion: 0.67
Nodes (3): CLAUDE.md Project Architecture Guide, Rationale: No Client-Side Router, Security Hardening Plan

### Community 69 - "Module Group 69"
Cohesion: 0.67
Nodes (3): Two-Server News Pipeline, News Expansion Feasibility Study, Server B Worker Python Requirements

### Community 70 - "Module Group 70"
Cohesion: 1.0
Nodes (1): dependencies.py — Shared FastAPI dependencies for TickerTap.  Re-exports the c

### Community 71 - "Module Group 71"
Cohesion: 1.0
Nodes (1): Strategy Templates — pre-built system strategies seeded into the database.  Th

### Community 72 - "Module Group 72"
Cohesion: 1.0
Nodes (1): Fetch the latest quote for *symbol*.          Args:             symbol: Ticke

### Community 73 - "Module Group 73"
Cohesion: 1.0
Nodes (1): Return the provider's supported interval list.          Returns:

### Community 74 - "Module Group 74"
Cohesion: 1.0
Nodes (1): Return the list of candle intervals this provider supports.          Returns:

### Community 75 - "Module Group 75"
Cohesion: 1.0
Nodes (1): Return maximum lookback for *interval*.          Args:             interval:

### Community 76 - "Module Group 76"
Cohesion: 1.0
Nodes (1): Synchronous symbol search via yfinance.          Args:             query: Fre

### Community 77 - "Module Group 77"
Cohesion: 1.0
Nodes (2): Paper Trading Session Manager, Strategy Parameter Editor

### Community 78 - "Module Group 78"
Cohesion: 1.0
Nodes (2): LearningPage, UserGuidePage

### Community 79 - "Module Group 79"
Cohesion: 1.0
Nodes (1): Enforce at least 1 uppercase, 1 lowercase, 1 digit, and 1 special character.

### Community 80 - "Module Group 80"
Cohesion: 1.0
Nodes (1): Enforce at least 1 uppercase, 1 lowercase, 1 digit, and 1 special character.

### Community 81 - "Module Group 81"
Cohesion: 1.0
Nodes (1): Size a position by risking a fixed percentage of the account.          The num

### Community 82 - "Module Group 82"
Cohesion: 1.0
Nodes (1): Size a position by risking a fixed dollar amount.          Args:

### Community 83 - "Module Group 83"
Cohesion: 1.0
Nodes (1): Full Kelly criterion — optimal fraction of account to wager.          Formula:

### Community 84 - "Module Group 84"
Cohesion: 1.0
Nodes (1): Fractional Kelly — conservative variant.          Multiplies the full Kelly fr

### Community 85 - "Module Group 85"
Cohesion: 1.0
Nodes (1): ATR-based position sizing.          Uses Average True Range to set a volatilit

### Community 86 - "Module Group 86"
Cohesion: 1.0
Nodes (1): Adjust price for slippage.          Entries slip against you (buy higher, sell

### Community 87 - "Module Group 87"
Cohesion: 1.0
Nodes (1): Build a TradeRecord from an open position and its exit.          Args:

### Community 88 - "Module Group 88"
Cohesion: 1.0
Nodes (1): Remove duplicate timestamps and sort chronologically.          Args:

### Community 89 - "Module Group 89"
Cohesion: 1.0
Nodes (1): Check if NYSE is in regular trading hours.

### Community 90 - "Module Group 90"
Cohesion: 1.0
Nodes (1): Return a numeric sort key so intervals order from shortest to longest.

### Community 91 - "Module Group 91"
Cohesion: 1.0
Nodes (1): Fetch the latest quote for *symbol*.          Args:             symbol: Ticke

### Community 92 - "Module Group 92"
Cohesion: 1.0
Nodes (1): Return the list of bar intervals this provider supports.          Returns:

### Community 93 - "Module Group 93"
Cohesion: 1.0
Nodes (1): Return the maximum historical lookback for *interval*.          Args:

### Community 94 - "Module Group 94"
Cohesion: 1.0
Nodes (0): 

### Community 95 - "Module Group 95"
Cohesion: 1.0
Nodes (0): 

### Community 96 - "Module Group 96"
Cohesion: 1.0
Nodes (0): 

### Community 97 - "Module Group 97"
Cohesion: 1.0
Nodes (1): Chart Components Index

### Community 98 - "Module Group 98"
Cohesion: 1.0
Nodes (1): Portfolio Area Chart

### Community 99 - "Module Group 99"
Cohesion: 1.0
Nodes (1): Allocation Donut Chart

### Community 100 - "Module Group 100"
Cohesion: 1.0
Nodes (1): Holdings Treemap Heatmap

### Community 101 - "Module Group 101"
Cohesion: 1.0
Nodes (1): Sparkline Mini Chart

### Community 102 - "Module Group 102"
Cohesion: 1.0
Nodes (1): Asset Fundamentals Detail Panel

### Community 103 - "Module Group 103"
Cohesion: 1.0
Nodes (1): Context Menu Popup

### Community 104 - "Module Group 104"
Cohesion: 1.0
Nodes (1): Empty State Placeholder

### Community 105 - "Module Group 105"
Cohesion: 1.0
Nodes (1): Filter Button Strip

### Community 106 - "Module Group 106"
Cohesion: 1.0
Nodes (1): Common Components Index

### Community 107 - "Module Group 107"
Cohesion: 1.0
Nodes (1): Page Navigation Controls

### Community 108 - "Module Group 108"
Cohesion: 1.0
Nodes (1): Time Period Selector

### Community 109 - "Module Group 109"
Cohesion: 1.0
Nodes (1): Stat Card Block

### Community 110 - "Module Group 110"
Cohesion: 1.0
Nodes (1): ChartsPage

### Community 111 - "Module Group 111"
Cohesion: 1.0
Nodes (1): ImportPage

### Community 112 - "Module Group 112"
Cohesion: 1.0
Nodes (1): LegalPage

### Community 113 - "Module Group 113"
Cohesion: 1.0
Nodes (1): TradingPage

### Community 114 - "Module Group 114"
Cohesion: 1.0
Nodes (1): TickerTap Platform README

### Community 115 - "Module Group 115"
Cohesion: 1.0
Nodes (1): Backend README

### Community 116 - "Module Group 116"
Cohesion: 1.0
Nodes (1): Agent Actions Changelog

### Community 117 - "Module Group 117"
Cohesion: 1.0
Nodes (1): Backend API Reference

### Community 118 - "Module Group 118"
Cohesion: 1.0
Nodes (1): Graphify Knowledge Graph Report

### Community 119 - "Module Group 119"
Cohesion: 1.0
Nodes (1): Middleware Stack Order

## Knowledge Gaps
- **600 isolated node(s):** `env.py — Alembic migration environment for TickerTap.  DATABASE_URL environmen`, `Run migrations in 'offline' mode (no live DB connection required).      Genera`, `Run migrations against a live database connection.`, `initial  Revision ID: 0001_initial Revises: Create Date: 2026-01-09 00:00:00`, `integrity fixes  Fix malformed server_defaults (nested quotes), add CASCADE de` (+595 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Module Group 70`** (2 nodes): `dependencies.py`, `dependencies.py — Shared FastAPI dependencies for TickerTap.  Re-exports the c`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 71`** (2 nodes): `templates.py`, `Strategy Templates — pre-built system strategies seeded into the database.  Th`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 72`** (2 nodes): `.get_quote()`, `Fetch the latest quote for *symbol*.          Args:             symbol: Ticke`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 73`** (2 nodes): `.get_supported_intervals()`, `Return the provider's supported interval list.          Returns:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 74`** (2 nodes): `Return the list of candle intervals this provider supports.          Returns:`, `.get_supported_intervals()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 75`** (2 nodes): `Return maximum lookback for *interval*.          Args:             interval:`, `.get_max_history()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 76`** (2 nodes): `Synchronous symbol search via yfinance.          Args:             query: Fre`, `._search_sync()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 77`** (2 nodes): `Paper Trading Session Manager`, `Strategy Parameter Editor`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 78`** (2 nodes): `LearningPage`, `UserGuidePage`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 79`** (1 nodes): `Enforce at least 1 uppercase, 1 lowercase, 1 digit, and 1 special character.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 80`** (1 nodes): `Enforce at least 1 uppercase, 1 lowercase, 1 digit, and 1 special character.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 81`** (1 nodes): `Size a position by risking a fixed percentage of the account.          The num`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 82`** (1 nodes): `Size a position by risking a fixed dollar amount.          Args:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 83`** (1 nodes): `Full Kelly criterion — optimal fraction of account to wager.          Formula:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 84`** (1 nodes): `Fractional Kelly — conservative variant.          Multiplies the full Kelly fr`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 85`** (1 nodes): `ATR-based position sizing.          Uses Average True Range to set a volatilit`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 86`** (1 nodes): `Adjust price for slippage.          Entries slip against you (buy higher, sell`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 87`** (1 nodes): `Build a TradeRecord from an open position and its exit.          Args:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 88`** (1 nodes): `Remove duplicate timestamps and sort chronologically.          Args:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 89`** (1 nodes): `Check if NYSE is in regular trading hours.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 90`** (1 nodes): `Return a numeric sort key so intervals order from shortest to longest.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 91`** (1 nodes): `Fetch the latest quote for *symbol*.          Args:             symbol: Ticke`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 92`** (1 nodes): `Return the list of bar intervals this provider supports.          Returns:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 93`** (1 nodes): `Return the maximum historical lookback for *interval*.          Args:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 94`** (1 nodes): `vite.config.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 95`** (1 nodes): `chartStyles.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 96`** (1 nodes): `setup.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 97`** (1 nodes): `Chart Components Index`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 98`** (1 nodes): `Portfolio Area Chart`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 99`** (1 nodes): `Allocation Donut Chart`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 100`** (1 nodes): `Holdings Treemap Heatmap`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 101`** (1 nodes): `Sparkline Mini Chart`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 102`** (1 nodes): `Asset Fundamentals Detail Panel`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 103`** (1 nodes): `Context Menu Popup`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 104`** (1 nodes): `Empty State Placeholder`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 105`** (1 nodes): `Filter Button Strip`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 106`** (1 nodes): `Common Components Index`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 107`** (1 nodes): `Page Navigation Controls`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 108`** (1 nodes): `Time Period Selector`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 109`** (1 nodes): `Stat Card Block`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 110`** (1 nodes): `ChartsPage`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 111`** (1 nodes): `ImportPage`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 112`** (1 nodes): `LegalPage`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 113`** (1 nodes): `TradingPage`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 114`** (1 nodes): `TickerTap Platform README`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 115`** (1 nodes): `Backend README`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 116`** (1 nodes): `Agent Actions Changelog`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 117`** (1 nodes): `Backend API Reference`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 118`** (1 nodes): `Graphify Knowledge Graph Report`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 119`** (1 nodes): `Middleware Stack Order`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `LLMTranspileError` connect `Trading ML Models and Strategies` to `PineScript Grammar and Parser`?**
  _High betweenness centrality (0.164) - this node is a cross-community bridge._
- **Why does `models/__init__.py — ML model registry for the trading-ml container.  Re-expor` connect `PineScript Grammar and Parser` to `Trading ML Models and Strategies`, `Feature Classifier (ML)`, `Pattern Classifier (ML)`, `Market Regime Detector (HMM)`?**
  _High betweenness centrality (0.114) - this node is a cross-community bridge._
- **Why does `Strategy` connect `Trading ML Models and Strategies` to `Backend Accounts and Auth API`, `FastAPI App and Middleware`?**
  _High betweenness centrality (0.076) - this node is a cross-community bridge._
- **Are the 151 inferred relationships involving `User` (e.g. with `admin.py — Admin-only routes for TickerTap.  Provides endpoints for user and a` and `Return 200 if the caller is an admin, else 403 from the dependency.      The f`) actually correct?**
  _`User` has 151 INFERRED edges - model-reasoned connections that need verification._
- **Are the 111 inferred relationships involving `AuditLog` (e.g. with `admin.py — Admin-only routes for TickerTap.  Provides endpoints for user and a` and `Return 200 if the caller is an admin, else 403 from the dependency.      The f`) actually correct?**
  _`AuditLog` has 111 INFERRED edges - model-reasoned connections that need verification._
- **Are the 92 inferred relationships involving `Strategy` (e.g. with `SecurityHeadersMiddleware` and `RequestBodySizeMiddleware`) actually correct?**
  _`Strategy` has 92 INFERRED edges - model-reasoned connections that need verification._
- **Are the 82 inferred relationships involving `YFinanceProvider` (e.g. with `routes/trading.py — Trading AI API endpoints.  Provides strategy CRUD, backtes` and `Validate the X-Internal-Key header and optional IP restriction.      Uses the`) actually correct?**
  _`YFinanceProvider` has 82 INFERRED edges - model-reasoned connections that need verification._