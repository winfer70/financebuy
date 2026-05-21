# Graph Report - .  (2026-05-21)

## Corpus Check
- 109 files · ~0 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1788 nodes · 7431 edges · 92 communities detected
- Extraction: 26% EXTRACTED · 74% INFERRED · 0% AMBIGUOUS · INFERRED: 5511 edges (avg confidence: 0.5)
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

## Communities

### Community 0 - "Community 0"
Cohesion: 0.03
Nodes (239): _check_condition(), evaluate_price_alerts(), _fetch_price(), _is_market_open(), alert_worker.py — arq background worker for evaluating price alerts.  Polls ac, Main worker job: check all active alerts against current prices.      Groups a, Seed the first evaluation job on worker start.      Called by arq's on_startup, arq worker configuration for the alert evaluation loop.      Run with: ``arq a (+231 more)

### Community 1 - "Community 1"
Cohesion: 0.19
Nodes (191): LLMTranspileError, Raised when LLM translation or validation fails., MarketDataProvider, AuditLog, BacktestResult, Notification, PaperTrade, PaperTradeEquitySnapshot (+183 more)

### Community 2 - "Community 2"
Cohesion: 0.05
Nodes (137): cancel_deletion(), change_email(), confirm_email_change(), _create_refresh_token_record(), deactivate_account(), delete_account(), _deletion_purge_loop(), forgot_password() (+129 more)

### Community 3 - "Community 3"
Cohesion: 0.02
Nodes (118): Exception, _call_indicator(), _check_stop_loss(), _compute_indicators(), _eval_comparison(), _eval_condition(), _eval_logical(), _extract_price_series() (+110 more)

### Community 4 - "Community 4"
Cohesion: 0.05
Nodes (77): admin_check(), list_audit_logs(), list_users(), lock_account(), lock_user(), admin.py — Admin-only routes for TickerTap.  Provides endpoints for user and a, Lock or unlock a brokerage account atomically.      Eliminates duplication bet, List all registered users, ordered newest-first.      Args:         db: Async (+69 more)

### Community 5 - "Community 5"
Cohesion: 0.03
Nodes (80): BaseHTTPMiddleware, limiter.py — Shared SlowAPI rate-limiter instance for TickerTap.  Centralised, health(), main.py — FastAPI application entry point for TickerTap.  Configures middlewar, Validate critical configuration on startup.      Performs the following checks, Injects security headers on every response.      Provides a defence-in-depth l, Reject requests whose Content-Length exceeds MAX_REQUEST_BODY_BYTES.      Prev, Logs every request with method, path, status code, and duration.      Paths co (+72 more)

### Community 6 - "Community 6"
Cohesion: 0.11
Nodes (78): _aggregate_bars(), ExchangeRateResponse, _fetch_earnings_dates_set(), _fetch_events(), _fetch_exchange_rates(), _fetch_fundamentals(), _fetch_ohlcv(), _fetch_ohlcv_interval() (+70 more)

### Community 7 - "Community 7"
Cohesion: 0.04
Nodes (62): cleanup_dead_letters(), _connect(), enqueue(), enqueue_batch(), get_pending(), increment_retries(), init_db(), mark_done() (+54 more)

### Community 8 - "Community 8"
Cohesion: 0.07
Nodes (42): annualized_return(), avg_loss(), avg_win(), benchmark_comparison(), calmar_ratio(), compute_all(), expectancy(), max_drawdown() (+34 more)

### Community 9 - "Community 9"
Cohesion: 0.08
Nodes (31): _adx(), _atr(), _bollinger_pctb(), _build_train_data(), _ema(), _engineer_features(), FeatureClassifier, _get_top_features() (+23 more)

### Community 10 - "Community 10"
Cohesion: 0.07
Nodes (31): adx(), atr(), bollinger_bands(), crossover(), crossunder(), ema(), highest(), lowest() (+23 more)

### Community 11 - "Community 11"
Cohesion: 0.08
Nodes (30): FeatureResponse, health(), _load_models(), LSTMResponse, OHLCVRow, PatternResponse, predict_features(), predict_lstm() (+22 more)

### Community 12 - "Community 12"
Cohesion: 0.1
Nodes (18): _bars_to_ohlc_ratios(), _build_pattern_sequences(), PatternClassifier, _PatternCNN, models/pattern_classifier.py — 1D-CNN candlestick pattern classifier.  Classif, Train / fine-tune the CNN on labelled candle data.          Args:, Persist CNN weights to disk., Load CNN weights if a checkpoint exists. (+10 more)

### Community 13 - "Community 13"
Cohesion: 0.1
Nodes (17): _compute_hmm_features(), _quick_adx(), models/regime_detector.py — Market regime detector (HMM + rule-based).  Classi, Train the HMM on market data.          Args:             symbol: Ticker for l, Run HMM prediction on market features.          Args:             bars: OHLCV, Map HMM state indices to regime labels based on feature means.          After, Create default HMM (will need training before use)., Persist HMM and state mapping to disk. (+9 more)

### Community 14 - "Community 14"
Cohesion: 0.17
Nodes (21): _action_button(), email.py — Email sending utilities for TickerTap.  Provides a generic send_ema, Generate a styled call-to-action button for emails.      Args:         url: T, Send an email via the configured SMTP server.      Args:         to_email: Re, Send a password reset email with a one-time link.      Args:         to_email, Send an email verification link for new account registration.      Args:, Send a verification email to the NEW email address for an email change.      A, Send an account reactivation email with a one-time link.      Args:         t (+13 more)

### Community 15 - "Community 15"
Cohesion: 0.21
Nodes (21): create_template(), delete_template(), get_template(), _get_template_or_404(), list_templates(), routes/chart_templates.py — Chart Template CRUD API endpoints.  Provides CRUD, Partially update a chart template (ownership enforced)., Delete a chart template (ownership enforced). (+13 more)

### Community 16 - "Community 16"
Cohesion: 0.11
Nodes (21): _aggregate_5min(), archive_intraday(), _daily_downsample(), downsample_daily(), _fetch_and_store_bars(), _get_active_symbols(), _is_market_open(), trading/archiver.py — Intraday data archiver worker.  Background worker that: (+13 more)

### Community 17 - "Community 17"
Cohesion: 0.15
Nodes (19): _get_dividend_zones(), _get_earnings_zones(), _get_fomc_zones(), get_no_trade_zones(), _get_opex_dates(), _get_opex_zones(), is_in_no_trade_zone(), NoTradeZone (+11 more)

### Community 18 - "Community 18"
Cohesion: 0.12
Nodes (13): _get_cached(), _is_market_open(), YFinance Provider — MarketDataProvider implementation backed by yfinance.  Wra, Fetch OHLCV bars from yfinance and return normalised OHLCVBars.          Args:, Fetch the latest quote for *symbol* from yfinance.          Args:, Search for symbols matching *query* via yfinance.          Args:, Synchronous OHLCV fetch from yfinance.          Args:             sym:, Synchronous quote fetch from yfinance.          Args:             sym: Upper- (+5 more)

### Community 19 - "Community 19"
Cohesion: 0.15
Nodes (17): _call_indicator(), _compute_composed_indicators(), _eval_expression(), _eval_node(), _generate_composed_signals(), Strategy Composition Engine — evaluates a graph of indicator nodes and boolean, Recursively validate every node in the expression AST.      Args:         nod, Evaluate a pre-validated expression against a variable namespace.      Args: (+9 more)

### Community 20 - "Community 20"
Cohesion: 0.15
Nodes (17): _build_user_prompt(), _call_ollama(), _extract_call_name(), llm_transpile(), _parse_llm_response(), PineScript LLM Fallback — translates unsupported PineScript via Ollama.  When, Parse and whitelist-walk the LLM-generated Python code.      Rejects any const, Recursively validate an AST node and all its children.      Args:         nod (+9 more)

### Community 21 - "Community 21"
Cohesion: 0.14
Nodes (16): AuthOut, create_access_token(), decode_access_token(), hash_password(), login(), LoginIn, auth.py — Core authentication utilities for TickerTap.  Provides password hash, Raise on startup if the JWT secret is still the insecure default.      Called (+8 more)

### Community 22 - "Community 22"
Cohesion: 0.17
Nodes (15): analyse_with_ollama(), build_analysis_prompt(), compute_statistics(), fetch_outcomes(), main(), _parse_analysis_json(), post_rules(), learner.py — TickerTap scoring accuracy analyser for Server B (REDACTED_HOST).  Standal (+7 more)

### Community 23 - "Community 23"
Cohesion: 0.17
Nodes (15): build_learning_prompt(), compute_strategy_stats(), fetch_backtest_history(), learn_with_ollama(), main(), _parse_learning_json(), post_strategy_rules(), strategy_learner.py — Strategy performance learner for Server B (REDACTED_HOST).  Analy (+7 more)

### Community 24 - "Community 24"
Cohesion: 0.17
Nodes (15): build_research_prompt(), fetch_recent_backtests(), fetch_regime_summary(), main(), _parse_research_json(), post_recommendations(), strategy_researcher.py — Strategy research agent for Server B (REDACTED_HOST).  Standal, Fetch current market regime summary from Server A.      Returns:         Dict (+7 more)

### Community 25 - "Community 25"
Cohesion: 0.22
Nodes (11): atr_based(), fixed_dollar(), fixed_percentage(), fractional_kelly(), kelly(), PositionSizer, engine/risk.py — Position sizing and risk management models.  Provides the ``P, Automatically choose and apply the best sizing model.          Prefers ATR-bas (+3 more)

### Community 26 - "Community 26"
Cohesion: 0.29
Nodes (9): BreakerStatus, check_circuit_breaker(), check_drawdown(), engine/circuit_breaker.py — Drawdown circuit breaker for strategy risk control., Check and enforce the circuit breaker for a strategy.      Loads recent backte, Execute circuit breaker trip: deactivate signals, notify, and log.      Args:, Result of a circuit breaker check.      Attributes:         tripped:        T, Check if the equity curve's drawdown exceeds the threshold.      Computes the (+1 more)

### Community 27 - "Community 27"
Cohesion: 0.27
Nodes (9): DecayResult, detect_decay(), detect_decay_for_strategy(), engine/decay.py — Strategy performance decay detection.  Monitors rolling stra, Load recent backtest results for a strategy and check for decay.      Queries, Compute rolling annualised Sharpe ratios.      Args:         returns:       B, Result of a strategy decay check.      Attributes:         is_decaying:    Tr, Detect performance decay from an equity curve.      Computes rolling Sharpe ra (+1 more)

### Community 28 - "Community 28"
Cohesion: 0.22
Nodes (5): _dedupe_and_sort(), Normalized Data Service — single entry point for strategy data consumption.  S, Fetch aligned OHLCV data at multiple intervals.          Intraday intervals ar, Read bars from the intraday_bars TimescaleDB hypertable.          Args:, Fetch normalised OHLCV bars for a single symbol and interval.          For int

### Community 29 - "Community 29"
Cohesion: 0.29
Nodes (7): ask_guide(), GuideAskRequest, GuideAskResponse, routes/guide.py — User Guide AI Q&A endpoint.  Proxies user questions to the O, Schema for a user question submitted to the guide endpoint.      Attributes:, Schema for the guide endpoint response.      Attributes:         answer: The, Submit a question to the TickerTap AI guide.      Proxies the question to the

### Community 30 - "Community 30"
Cohesion: 0.32
Nodes (7): generate_signals(), indicator_outputs(), ADX Trend Strategy — enter on strong trend confirmation via ADX.  Enter long w, Expose indicator series for the composition engine.      Args:         bars:, Wilder's smoothing (used in ADX/DI calculations).      Args:         values:, Generate entry/exit signals based on ADX trend strength.      Args:         b, _wilder_smooth()

### Community 31 - "Community 31"
Cohesion: 0.32
Nodes (7): _ema(), generate_signals(), indicator_outputs(), EMA Crossover Strategy — trend-following using exponential moving averages.  F, Compute exponential moving average series.      Args:         closes: List of, Generate entry/exit signals based on EMA crossover.      Args:         bars:, Expose indicator series for the composition engine.      Args:         bars:

### Community 32 - "Community 32"
Cohesion: 0.32
Nodes (7): generate_signals(), indicator_outputs(), _period_high_low(), Ichimoku Cloud Strategy — trend-following using Ichimoku Kinko Hyo components., Expose indicator series for the composition engine.      Args:         bars:, Compute highest high and lowest low over a lookback window.      Args:, Generate entry/exit signals based on Ichimoku Cloud.      Args:         bars:

### Community 33 - "Community 33"
Cohesion: 0.32
Nodes (7): _ema(), generate_signals(), indicator_outputs(), MACD Crossover Strategy — trend-following using MACD line/signal crossovers., Expose indicator series for the composition engine.      Args:         bars:, Compute EMA series (SMA-seeded)., Generate entry/exit signals based on MACD crossover.      Args:         bars:

### Community 34 - "Community 34"
Cohesion: 0.32
Nodes (7): generate_signals(), indicator_outputs(), RSI Mean Reversion Strategy — fade overbought/oversold RSI readings.  Enter lo, Expose indicator series for the composition engine.      Args:         bars:, Compute RSI series using Wilder's smoothing.      Args:         closes: List, Generate entry/exit signals based on RSI mean reversion.      Args:         b, _rsi()

### Community 35 - "Community 35"
Cohesion: 0.32
Nodes (7): generate_signals(), indicator_outputs(), SMA Crossover Strategy — trend-following using simple moving average crossovers., Compute simple moving average series.      Args:         closes: List of clos, Generate entry/exit signals based on SMA crossover.      Args:         bars:, Expose indicator series for the composition engine.      Args:         bars:, _sma()

### Community 36 - "Community 36"
Cohesion: 0.32
Nodes (7): _compute_vwap(), generate_signals(), indicator_outputs(), VWAP Bounce Strategy — intraday mean reversion around VWAP.  Enter long when p, Compute cumulative VWAP series.      Args:         bars: Chronological OHLCV, Generate entry/exit signals based on VWAP bounce.      Args:         bars:, Expose indicator series for the composition engine.      Args:         bars:

### Community 37 - "Community 37"
Cohesion: 0.33
Nodes (2): apiFetch(), _tryRefreshToken()

### Community 38 - "Community 38"
Cohesion: 0.29
Nodes (0): 

### Community 39 - "Community 39"
Cohesion: 0.33
Nodes (5): env.py — Alembic migration environment for TickerTap.  DATABASE_URL environmen, Run migrations in 'offline' mode (no live DB connection required).      Genera, Run migrations against a live database connection., run_migrations_offline(), run_migrations_online()

### Community 40 - "Community 40"
Cohesion: 0.33
Nodes (5): downgrade(), 0011_user_preferences — Add JSONB preferences column to users table.  Stores u, Add preferences JSONB column to users table., Remove preferences column from users table., upgrade()

### Community 41 - "Community 41"
Cohesion: 0.33
Nodes (5): downgrade(), 0012_reports_email_verify — Add email verification, account management, and use, Remove email_verification_tokens, user_reports, and user account columns., Add email verification columns, user_reports table, and email_verification_token, upgrade()

### Community 42 - "Community 42"
Cohesion: 0.33
Nodes (5): downgrade(), 0013_watchlists_account_lockout — Add account lockout columns and watchlist/wat, Remove watchlist_items, watchlists tables, and lockout columns from users., Add lockout columns to users, create watchlists and watchlist_items tables., upgrade()

### Community 43 - "Community 43"
Cohesion: 0.33
Nodes (5): downgrade(), 0014_profit_taking — Add profit-taking target price column to portfolio positio, Add profit_taking column to portfolio_positions., Remove profit_taking column from portfolio_positions., upgrade()

### Community 44 - "Community 44"
Cohesion: 0.33
Nodes (5): downgrade(), 0015_trading_strategies — Trading AI core tables.  Creates four tables require, Drop trading AI core tables in reverse dependency order., Create trading AI core tables., upgrade()

### Community 45 - "Community 45"
Cohesion: 0.4
Nodes (5): _get_avg_sentiment(), engine/filters.py — Signal filters that gate entry/exit signals.  Provides com, Filter a trading signal based on recent news sentiment scores.      Looks up t, Compute average sentiment score for *symbol* over recent articles.      Querie, sentiment_filter()

### Community 46 - "Community 46"
Cohesion: 0.33
Nodes (5): generate_signals(), indicator_outputs(), Bollinger Band Squeeze Strategy — volatility breakout from Bollinger Band contra, Generate entry/exit signals based on Bollinger Band squeeze breakout.      Arg, Expose indicator series for the composition engine.      Args:         bars:

### Community 47 - "Community 47"
Cohesion: 0.33
Nodes (5): generate_signals(), indicator_outputs(), Breakout Strategy — enter on price breaking above N-bar high with volume confirm, Generate entry/exit signals based on price breakout with volume.      Args:, Expose indicator series for the composition engine.      Args:         bars:

### Community 48 - "Community 48"
Cohesion: 0.33
Nodes (5): generate_signals(), indicator_outputs(), Stochastic Oscillator Strategy — mean reversion using %K/%D crossovers.  Enter, Generate entry/exit signals based on Stochastic Oscillator.      Args:, Expose indicator series for the composition engine.      Args:         bars:

### Community 49 - "Community 49"
Cohesion: 0.5
Nodes (1): initial  Revision ID: 0001_initial Revises: Create Date: 2026-01-09 00:00:00

### Community 50 - "Community 50"
Cohesion: 0.5
Nodes (1): password reset tokens  Revision ID: 0002_password_reset_tokens Revises: 0001_

### Community 51 - "Community 51"
Cohesion: 0.5
Nodes (1): integrity fixes  Fix malformed server_defaults (nested quotes), add CASCADE de

### Community 52 - "Community 52"
Cohesion: 0.5
Nodes (1): add refresh_tokens table  Adds the refresh_tokens table used by the P6.3 JWT r

### Community 53 - "Community 53"
Cohesion: 0.5
Nodes (1): add portfolios and portfolio_positions tables  Adds the portfolios and portfol

### Community 54 - "Community 54"
Cohesion: 0.5
Nodes (1): Add asset_type and physical_type to portfolio_positions.  Revision ID: 0006_as

### Community 55 - "Community 55"
Cohesion: 0.5
Nodes (1): Add stop_loss to portfolio_positions.  Revision ID: 0007_stop_loss Revises: 0

### Community 56 - "Community 56"
Cohesion: 0.5
Nodes (1): Create chart_templates table.  Revision ID: 0008_chart_templates Revises: 000

### Community 57 - "Community 57"
Cohesion: 0.5
Nodes (1): Create news_articles and news_article_tickers tables.  Adds the two tables req

### Community 58 - "Community 58"
Cohesion: 0.5
Nodes (1): Create score_outcomes and scoring_rules tables for the feedback loop.  Adds th

### Community 59 - "Community 59"
Cohesion: 0.5
Nodes (1): 0016_intraday_bars — TimescaleDB hypertable for intraday OHLCV data.  Creates

### Community 60 - "Community 60"
Cohesion: 0.5
Nodes (1): 0017_notifications — Notification and webhook tables.  Creates:   - notificat

### Community 61 - "Community 61"
Cohesion: 0.5
Nodes (1): 0018_social_strategies — Strategy ratings and usage tracking tables.  Creates:

### Community 62 - "Community 62"
Cohesion: 0.5
Nodes (1): 0019_paper_trading — Paper trading simulation tables.  Creates:   - paper_tra

### Community 63 - "Community 63"
Cohesion: 0.67
Nodes (0): 

### Community 64 - "Community 64"
Cohesion: 1.0
Nodes (1): dependencies.py — Shared FastAPI dependencies for TickerTap.  Re-exports the c

### Community 65 - "Community 65"
Cohesion: 1.0
Nodes (1): Fetch the latest quote for *symbol*.          Args:             symbol: Ticke

### Community 66 - "Community 66"
Cohesion: 1.0
Nodes (1): Return the provider's supported interval list.          Returns:

### Community 67 - "Community 67"
Cohesion: 1.0
Nodes (1): Return the list of candle intervals this provider supports.          Returns:

### Community 68 - "Community 68"
Cohesion: 1.0
Nodes (1): Synchronous symbol search via yfinance.          Args:             query: Fre

### Community 69 - "Community 69"
Cohesion: 1.0
Nodes (1): Return maximum lookback for *interval*.          Args:             interval:

### Community 70 - "Community 70"
Cohesion: 1.0
Nodes (1): Strategy Templates — pre-built system strategies seeded into the database.  Th

### Community 71 - "Community 71"
Cohesion: 1.0
Nodes (0): 

### Community 72 - "Community 72"
Cohesion: 1.0
Nodes (0): 

### Community 73 - "Community 73"
Cohesion: 1.0
Nodes (1): Enforce at least 1 uppercase, 1 lowercase, 1 digit, and 1 special character.

### Community 74 - "Community 74"
Cohesion: 1.0
Nodes (1): Enforce at least 1 uppercase, 1 lowercase, 1 digit, and 1 special character.

### Community 75 - "Community 75"
Cohesion: 1.0
Nodes (1): Adjust price for slippage.          Entries slip against you (buy higher, sell

### Community 76 - "Community 76"
Cohesion: 1.0
Nodes (1): Build a TradeRecord from an open position and its exit.          Args:

### Community 77 - "Community 77"
Cohesion: 1.0
Nodes (1): Size a position by risking a fixed percentage of the account.          The num

### Community 78 - "Community 78"
Cohesion: 1.0
Nodes (1): Size a position by risking a fixed dollar amount.          Args:

### Community 79 - "Community 79"
Cohesion: 1.0
Nodes (1): Full Kelly criterion — optimal fraction of account to wager.          Formula:

### Community 80 - "Community 80"
Cohesion: 1.0
Nodes (1): Fractional Kelly — conservative variant.          Multiplies the full Kelly fr

### Community 81 - "Community 81"
Cohesion: 1.0
Nodes (1): ATR-based position sizing.          Uses Average True Range to set a volatilit

### Community 82 - "Community 82"
Cohesion: 1.0
Nodes (1): Fetch the latest quote for *symbol*.          Args:             symbol: Ticke

### Community 83 - "Community 83"
Cohesion: 1.0
Nodes (1): Return the list of bar intervals this provider supports.          Returns:

### Community 84 - "Community 84"
Cohesion: 1.0
Nodes (1): Return the maximum historical lookback for *interval*.          Args:

### Community 85 - "Community 85"
Cohesion: 1.0
Nodes (1): Remove duplicate timestamps and sort chronologically.          Args:

### Community 86 - "Community 86"
Cohesion: 1.0
Nodes (1): Check if NYSE is in regular trading hours.

### Community 87 - "Community 87"
Cohesion: 1.0
Nodes (1): Return a numeric sort key so intervals order from shortest to longest.

### Community 88 - "Community 88"
Cohesion: 1.0
Nodes (0): 

### Community 89 - "Community 89"
Cohesion: 1.0
Nodes (0): 

### Community 90 - "Community 90"
Cohesion: 1.0
Nodes (0): 

### Community 91 - "Community 91"
Cohesion: 1.0
Nodes (0): 

## Knowledge Gaps
- **552 isolated node(s):** `env.py — Alembic migration environment for TickerTap.  DATABASE_URL environmen`, `Run migrations in 'offline' mode (no live DB connection required).      Genera`, `Run migrations against a live database connection.`, `initial  Revision ID: 0001_initial Revises: Create Date: 2026-01-09 00:00:00`, `password reset tokens  Revision ID: 0002_password_reset_tokens Revises: 0001_` (+547 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 64`** (2 nodes): `dependencies.py`, `dependencies.py — Shared FastAPI dependencies for TickerTap.  Re-exports the c`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 65`** (2 nodes): `.get_quote()`, `Fetch the latest quote for *symbol*.          Args:             symbol: Ticke`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 66`** (2 nodes): `.get_supported_intervals()`, `Return the provider's supported interval list.          Returns:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 67`** (2 nodes): `Return the list of candle intervals this provider supports.          Returns:`, `.get_supported_intervals()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 68`** (2 nodes): `Synchronous symbol search via yfinance.          Args:             query: Fre`, `._search_sync()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 69`** (2 nodes): `Return maximum lookback for *interval*.          Args:             interval:`, `.get_max_history()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 70`** (2 nodes): `templates.py`, `Strategy Templates — pre-built system strategies seeded into the database.  Th`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 71`** (2 nodes): `eslint.config.js`, `globals.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 72`** (2 nodes): `useContextPopup.js`, `useContextPopup()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 73`** (1 nodes): `Enforce at least 1 uppercase, 1 lowercase, 1 digit, and 1 special character.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 74`** (1 nodes): `Enforce at least 1 uppercase, 1 lowercase, 1 digit, and 1 special character.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 75`** (1 nodes): `Adjust price for slippage.          Entries slip against you (buy higher, sell`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 76`** (1 nodes): `Build a TradeRecord from an open position and its exit.          Args:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 77`** (1 nodes): `Size a position by risking a fixed percentage of the account.          The num`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 78`** (1 nodes): `Size a position by risking a fixed dollar amount.          Args:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 79`** (1 nodes): `Full Kelly criterion — optimal fraction of account to wager.          Formula:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 80`** (1 nodes): `Fractional Kelly — conservative variant.          Multiplies the full Kelly fr`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 81`** (1 nodes): `ATR-based position sizing.          Uses Average True Range to set a volatilit`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 82`** (1 nodes): `Fetch the latest quote for *symbol*.          Args:             symbol: Ticke`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 83`** (1 nodes): `Return the list of bar intervals this provider supports.          Returns:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 84`** (1 nodes): `Return the maximum historical lookback for *interval*.          Args:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 85`** (1 nodes): `Remove duplicate timestamps and sort chronologically.          Args:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 86`** (1 nodes): `Check if NYSE is in regular trading hours.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 87`** (1 nodes): `Return a numeric sort key so intervals order from shortest to longest.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 88`** (1 nodes): `setup.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 89`** (1 nodes): `chartStyles.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 90`** (1 nodes): `shared.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 91`** (1 nodes): `vite.config.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `LLMTranspileError` connect `Community 1` to `Community 3`, `Community 20`?**
  _High betweenness centrality (0.184) - this node is a cross-community bridge._
- **Why does `models/__init__.py — ML model registry for the trading-ml container.  Re-expor` connect `Community 3` to `Community 1`, `Community 12`, `Community 13`, `Community 9`?**
  _High betweenness centrality (0.128) - this node is a cross-community bridge._
- **Why does `User` connect `Community 2` to `Community 0`, `Community 1`, `Community 4`, `Community 21`?**
  _High betweenness centrality (0.083) - this node is a cross-community bridge._
- **Are the 151 inferred relationships involving `User` (e.g. with `admin.py — Admin-only routes for TickerTap.  Provides endpoints for user and a` and `Return 200 if the caller is an admin, else 403 from the dependency.      The f`) actually correct?**
  _`User` has 151 INFERRED edges - model-reasoned connections that need verification._
- **Are the 111 inferred relationships involving `AuditLog` (e.g. with `admin.py — Admin-only routes for TickerTap.  Provides endpoints for user and a` and `Return 200 if the caller is an admin, else 403 from the dependency.      The f`) actually correct?**
  _`AuditLog` has 111 INFERRED edges - model-reasoned connections that need verification._
- **Are the 92 inferred relationships involving `Strategy` (e.g. with `SecurityHeadersMiddleware` and `RequestBodySizeMiddleware`) actually correct?**
  _`Strategy` has 92 INFERRED edges - model-reasoned connections that need verification._
- **Are the 82 inferred relationships involving `YFinanceProvider` (e.g. with `routes/trading.py — Trading AI API endpoints.  Provides strategy CRUD, backtes` and `Validate the X-Internal-Key header and optional IP restriction.      Uses the`) actually correct?**
  _`YFinanceProvider` has 82 INFERRED edges - model-reasoned connections that need verification._