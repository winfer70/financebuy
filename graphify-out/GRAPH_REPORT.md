# Graph Report - .  (2026-06-12)

## Corpus Check
- 157 files · ~0 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 2432 nodes · 8890 edges · 115 communities detected
- Extraction: 29% EXTRACTED · 71% INFERRED · 0% AMBIGUOUS · INFERRED: 6308 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## God Nodes (most connected - your core abstractions)
1. `User` - 176 edges
2. `AuditLog` - 118 edges
3. `RuleContext` - 106 edges
4. `RuleAlertData` - 106 edges
5. `Notification` - 103 edges
6. `Strategy` - 102 edges
7. `YFinanceProvider` - 97 edges
8. `NormalizedDataService` - 94 edges
9. `Portfolio` - 85 edges
10. `BacktestResult` - 80 edges

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
Nodes (202): FeatureResponse, health(), _load_models(), LSTMResponse, OHLCVRow, PatternResponse, predict_features(), predict_lstm() (+194 more)

### Community 1 - "Community 1"
Cohesion: 0.02
Nodes (169): AuthOut, create_access_token(), decode_access_token(), hash_password(), login(), LoginIn, auth.py — Core authentication utilities for TickerTap.  Provides password hash, Raise on startup if the JWT secret is still the insecure default.      Called (+161 more)

### Community 2 - "Community 2"
Cohesion: 0.02
Nodes (161): admin_check(), list_audit_logs(), list_users(), lock_account(), lock_user(), admin.py — Admin-only routes for TickerTap.  Provides endpoints for user and a, Lock or unlock a brokerage account atomically.      Eliminates duplication bet, List all registered users, ordered newest-first.      Args:         db: Async (+153 more)

### Community 3 - "Community 3"
Cohesion: 0.03
Nodes (118): check_analyst_consensus(), analyst.py — Analyst consensus rule checker.  Fires when current price is sign, Check if price is above analyst consensus target.      Args:         ctx:, check_buckets(), buckets.py — Rule 13: Bucket allocation checker.  Fires when any bucket deviat, Check bucket allocation vs targets.      Args:         ctx: RuleContext with, check_fundamentals_health(), fundamentals.py — Fundamental health rule checker.  Checks debt-to-equity stre (+110 more)

### Community 4 - "Community 4"
Cohesion: 0.22
Nodes (180): LLMTranspileError, Raised when LLM translation or validation fails., MarketDataProvider, AuditLog, BacktestResult, Notification, PaperTrade, PaperTradeEquitySnapshot (+172 more)

### Community 5 - "Community 5"
Cohesion: 0.02
Nodes (135): Exception, _call_indicator(), _check_stop_loss(), _compute_indicators(), _eval_comparison(), _eval_condition(), _eval_logical(), _extract_price_series() (+127 more)

### Community 6 - "Community 6"
Cohesion: 0.1
Nodes (103): cancel_deletion(), change_email(), confirm_email_change(), _create_refresh_token_record(), deactivate_account(), delete_account(), _deletion_purge_loop(), forgot_password() (+95 more)

### Community 7 - "Community 7"
Cohesion: 0.03
Nodes (75): _check_condition(), evaluate_price_alerts(), _fetch_price(), _is_market_open(), alert_worker.py — arq background worker for evaluating price alerts.  Polls ac, Evaluate whether the alert condition is met.      Args:         condition: "a, Main worker job: check all active alerts against current prices.      Groups a, Seed the first evaluation job on worker start.      Called by arq's on_startup (+67 more)

### Community 8 - "Community 8"
Cohesion: 0.11
Nodes (78): _aggregate_bars(), ExchangeRateResponse, _fetch_earnings_dates_set(), _fetch_events(), _fetch_exchange_rates(), _fetch_fundamentals(), _fetch_ohlcv(), _fetch_ohlcv_interval() (+70 more)

### Community 9 - "Community 9"
Cohesion: 0.04
Nodes (65): _analyze_single_symbol(), _audit(), browse_marketplace(), clone_strategy(), _compute_exit_analysis(), _compute_score(), _compute_trend(), create_composed_strategy() (+57 more)

### Community 10 - "Community 10"
Cohesion: 0.1
Nodes (62): _change_pct_to_score(), _check_article_outcomes(), create_scoring_rules(), export_training_data(), _fetch_outcome_prices(), get_active_rules(), get_outcome_data(), _grade_accuracy() (+54 more)

### Community 11 - "Community 11"
Cohesion: 0.06
Nodes (44): annualized_return(), avg_loss(), avg_win(), benchmark_comparison(), calmar_ratio(), compute_all(), expectancy(), get_worker_metrics() (+36 more)

### Community 12 - "Community 12"
Cohesion: 0.08
Nodes (31): _adx(), _atr(), _bollinger_pctb(), _build_train_data(), _ema(), _engineer_features(), FeatureClassifier, _get_top_features() (+23 more)

### Community 13 - "Community 13"
Cohesion: 0.08
Nodes (22): make_mock_item(), make_mock_watchlist(), make_scalar_count_result(), ============================================================================ TE, Tests for watchlist create, list, get, and delete operations., Valid name payload should return 201 with the new watchlist., Omitting the name field should return 422 Unprocessable Entity., User with no watchlists should receive an empty JSON array. (+14 more)

### Community 14 - "Community 14"
Cohesion: 0.07
Nodes (31): adx(), atr(), bollinger_bands(), crossover(), crossunder(), ema(), highest(), lowest() (+23 more)

### Community 15 - "Community 15"
Cohesion: 0.07
Nodes (20): make_mock_alert(), ============================================================================ TE, Symbols in lowercase should be stored and returned uppercase., An unrecognised condition value must fail Pydantic validation (422)., User already at the 50-alert cap should receive 400 Bad Request., User with 49 active alerts should be able to create one more., Tests for alert listing endpoint., User with no alerts should receive an empty JSON array. (+12 more)

### Community 16 - "Community 16"
Cohesion: 0.09
Nodes (17): make_mock_strategy(), ============================================================================ TE, GET /strategies without auth should return 401 or 403., Tests for single-strategy retrieval., Fetching an owned strategy by ID should return 200., Fetching a non-existent strategy should return 404., System strategies should be accessible to any authenticated user., Tests for the backtest queuing endpoint. (+9 more)

### Community 17 - "Community 17"
Cohesion: 0.1
Nodes (25): _et(), TEST SUITE: Scanner Session Detection MODULE UNDER TEST: app.trading.scanner_se, 4:00 PM ET is at/after the regular close; elapsed weight must be 1.0., project_daily_volume must return intraday_vol unchanged when elapsed_weight == 0, At 50% session elapsed, projected volume should be double the intraday volume., Build a timezone-aware datetime in US/Eastern for use in tests.      Args:, Saturday noon ET must yield 'closed' regardless of time., Monday 8:00 AM ET is within pre-market hours (4:00–9:30 AM). (+17 more)

### Community 18 - "Community 18"
Cohesion: 0.1
Nodes (18): _bars_to_ohlc_ratios(), _build_pattern_sequences(), PatternClassifier, _PatternCNN, models/pattern_classifier.py — 1D-CNN candlestick pattern classifier.  Classif, Train / fine-tune the CNN on labelled candle data.          Args:, Persist CNN weights to disk., Load CNN weights if a checkpoint exists. (+10 more)

### Community 19 - "Community 19"
Cohesion: 0.1
Nodes (17): _compute_hmm_features(), _quick_adx(), models/regime_detector.py — Market regime detector (HMM + rule-based).  Classi, Train the HMM on market data.          Args:             symbol: Ticker for l, Run HMM prediction on market features.          Args:             bars: OHLCV, Map HMM state indices to regime labels based on feature means.          After, Create default HMM (will need training before use)., Persist HMM and state mapping to disk. (+9 more)

### Community 20 - "Community 20"
Cohesion: 0.17
Nodes (21): _action_button(), email.py — Email sending utilities for TickerTap.  Provides a generic send_ema, Generate a styled call-to-action button for emails.      Args:         url: T, Send an email via the configured SMTP server.      Args:         to_email: Re, Send a password reset email with a one-time link.      Args:         to_email, Send an email verification link for new account registration.      Args:, Send a verification email to the NEW email address for an email change.      A, Send an account reactivation email with a one-time link.      Args:         t (+13 more)

### Community 21 - "Community 21"
Cohesion: 0.11
Nodes (21): _aggregate_5min(), archive_intraday(), _daily_downsample(), downsample_daily(), _fetch_and_store_bars(), _get_active_symbols(), _is_market_open(), trading/archiver.py — Intraday data archiver worker.  Background worker that: (+13 more)

### Community 22 - "Community 22"
Cohesion: 0.15
Nodes (19): _get_dividend_zones(), _get_earnings_zones(), _get_fomc_zones(), get_no_trade_zones(), _get_opex_dates(), _get_opex_zones(), is_in_no_trade_zone(), NoTradeZone (+11 more)

### Community 23 - "Community 23"
Cohesion: 0.12
Nodes (13): _get_cached(), _is_market_open(), YFinance Provider — MarketDataProvider implementation backed by yfinance.  Wra, Fetch OHLCV bars from yfinance and return normalised OHLCVBars.          Args:, Fetch the latest quote for *symbol* from yfinance.          Args:, Search for symbols matching *query* via yfinance.          Args:, Synchronous OHLCV fetch from yfinance.          Args:             sym:, Synchronous quote fetch from yfinance.          Args:             sym: Upper- (+5 more)

### Community 24 - "Community 24"
Cohesion: 0.14
Nodes (19): cleanup_dead_letters(), _connect(), enqueue(), enqueue_batch(), get_pending(), increment_retries(), init_db(), mark_done() (+11 more)

### Community 25 - "Community 25"
Cohesion: 0.15
Nodes (17): _call_indicator(), _compute_composed_indicators(), _eval_expression(), _eval_node(), _generate_composed_signals(), Strategy Composition Engine — evaluates a graph of indicator nodes and boolean, Recursively validate every node in the expression AST.      Args:         nod, Evaluate a pre-validated expression against a variable namespace.      Args: (+9 more)

### Community 26 - "Community 26"
Cohesion: 0.11
Nodes (17): auth_client(), make_all_result(), make_scalar_count_result(), make_scalar_result(), make_scalars_result(), mock_db_session(), mock_user(), ============================================================================ Sh (+9 more)

### Community 27 - "Community 27"
Cohesion: 0.11
Nodes (11): ============================================================================ TE, Integration tests for listing the current user's accounts., No accounts for this user should return an empty JSON array., A user with one account should receive a list of length 1., Requests without authentication should be rejected (401 or 403)., Integration tests for account creation endpoint., Valid payload should return 201 with account data., Omitting the required account_type field must return 422. (+3 more)

### Community 28 - "Community 28"
Cohesion: 0.17
Nodes (15): analyse_with_ollama(), build_analysis_prompt(), compute_statistics(), fetch_outcomes(), main(), _parse_analysis_json(), post_rules(), learner.py — TickerTap scoring accuracy analyser for Server B (REDACTED_HOST).  Standal (+7 more)

### Community 29 - "Community 29"
Cohesion: 0.18
Nodes (15): fetch_all_news(), fetch_finviz(), fetch_google(), fetch_marketwatch(), fetch_yahoo(), _make_article(), _parse_rss_date(), sources.py — Synchronous multi-source financial news fetcher for the TickerTap w (+7 more)

### Community 30 - "Community 30"
Cohesion: 0.17
Nodes (15): build_learning_prompt(), compute_strategy_stats(), fetch_backtest_history(), learn_with_ollama(), main(), _parse_learning_json(), post_strategy_rules(), strategy_learner.py — Strategy performance learner for Server B (REDACTED_HOST).  Analy (+7 more)

### Community 31 - "Community 31"
Cohesion: 0.17
Nodes (15): build_research_prompt(), fetch_recent_backtests(), fetch_regime_summary(), main(), _parse_research_json(), post_recommendations(), strategy_researcher.py — Strategy research agent for Server B (REDACTED_HOST).  Standal, Fetch current market regime summary from Server A.      Returns:         Dict (+7 more)

### Community 32 - "Community 32"
Cohesion: 0.22
Nodes (11): atr_based(), fixed_dollar(), fixed_percentage(), fractional_kelly(), kelly(), PositionSizer, engine/risk.py — Position sizing and risk management models.  Provides the ``P, Automatically choose and apply the best sizing model.          Prefers ATR-bas (+3 more)

### Community 33 - "Community 33"
Cohesion: 0.19
Nodes (13): _make_redis_mock(), TEST SUITE: Worker Metrics Endpoint MODULE UNDER TEST: app.routes.metrics TEST, Workers should report 'no_heartbeat' when the Redis key does not exist.      R, Endpoint should return {error: ...} gracefully when Redis is down.      aiored, Response must contain exactly the three known arq workers as top-level keys., Build a mock aioredis client with pre-configured async methods.      Args:, All workers should report 'healthy' when their heartbeat is recent.      A hea, All workers should report 'stale' when their heartbeat is 2000 s old.      200 (+5 more)

### Community 34 - "Community 34"
Cohesion: 0.14
Nodes (9): ============================================================================ TE, Tests for the positions listing endpoint., User with no accounts should receive an empty positions list., GET /positions without auth should return 401 or 403., Tests for the portfolio summary endpoint., User with no accounts should receive a zero-value summary., GET /summary without auth should return 401 or 403., TestGetPositions (+1 more)

### Community 35 - "Community 35"
Cohesion: 0.29
Nodes (9): BreakerStatus, check_circuit_breaker(), check_drawdown(), engine/circuit_breaker.py — Drawdown circuit breaker for strategy risk control., Check and enforce the circuit breaker for a strategy.      Loads recent backte, Execute circuit breaker trip: deactivate signals, notify, and log.      Args:, Result of a circuit breaker check.      Attributes:         tripped:        T, Check if the equity curve's drawdown exceeds the threshold.      Computes the (+1 more)

### Community 36 - "Community 36"
Cohesion: 0.27
Nodes (9): DecayResult, detect_decay(), detect_decay_for_strategy(), engine/decay.py — Strategy performance decay detection.  Monitors rolling stra, Load recent backtest results for a strategy and check for decay.      Queries, Compute rolling annualised Sharpe ratios.      Args:         returns:       B, Result of a strategy decay check.      Attributes:         is_decaying:    Tr, Detect performance decay from an equity curve.      Computes rolling Sharpe ra (+1 more)

### Community 37 - "Community 37"
Cohesion: 0.24
Nodes (9): get_elapsed_weight(), get_market_session(), get_session_context(), project_daily_volume(), scanner_session.py — Market session detection and volume projection for the scan, Return the current market session label for a given Eastern-time datetime., Return the fraction of the regular NYSE session elapsed at the given time., Project a full-day volume estimate from intraday volume and elapsed weight. (+1 more)

### Community 38 - "Community 38"
Cohesion: 0.22
Nodes (5): _dedupe_and_sort(), Normalized Data Service — single entry point for strategy data consumption.  S, Fetch aligned OHLCV data at multiple intervals.          Intraday intervals ar, Read bars from the intraday_bars TimescaleDB hypertable.          Args:, Fetch normalised OHLCV bars for a single symbol and interval.          For int

### Community 39 - "Community 39"
Cohesion: 0.32
Nodes (7): generate_signals(), indicator_outputs(), ADX Trend Strategy — enter on strong trend confirmation via ADX.  Enter long w, Expose indicator series for the composition engine.      Args:         bars:, Wilder's smoothing (used in ADX/DI calculations).      Args:         values:, Generate entry/exit signals based on ADX trend strength.      Args:         b, _wilder_smooth()

### Community 40 - "Community 40"
Cohesion: 0.32
Nodes (7): _ema(), generate_signals(), indicator_outputs(), EMA Crossover Strategy — trend-following using exponential moving averages.  F, Compute exponential moving average series.      Args:         closes: List of, Generate entry/exit signals based on EMA crossover.      Args:         bars:, Expose indicator series for the composition engine.      Args:         bars:

### Community 41 - "Community 41"
Cohesion: 0.32
Nodes (7): generate_signals(), indicator_outputs(), _period_high_low(), Ichimoku Cloud Strategy — trend-following using Ichimoku Kinko Hyo components., Expose indicator series for the composition engine.      Args:         bars:, Compute highest high and lowest low over a lookback window.      Args:, Generate entry/exit signals based on Ichimoku Cloud.      Args:         bars:

### Community 42 - "Community 42"
Cohesion: 0.32
Nodes (7): _ema(), generate_signals(), indicator_outputs(), MACD Crossover Strategy — trend-following using MACD line/signal crossovers., Expose indicator series for the composition engine.      Args:         bars:, Compute EMA series (SMA-seeded)., Generate entry/exit signals based on MACD crossover.      Args:         bars:

### Community 43 - "Community 43"
Cohesion: 0.32
Nodes (7): generate_signals(), indicator_outputs(), RSI Mean Reversion Strategy — fade overbought/oversold RSI readings.  Enter lo, Expose indicator series for the composition engine.      Args:         bars:, Compute RSI series using Wilder's smoothing.      Args:         closes: List, Generate entry/exit signals based on RSI mean reversion.      Args:         b, _rsi()

### Community 44 - "Community 44"
Cohesion: 0.32
Nodes (7): generate_signals(), indicator_outputs(), SMA Crossover Strategy — trend-following using simple moving average crossovers., Compute simple moving average series.      Args:         closes: List of clos, Generate entry/exit signals based on SMA crossover.      Args:         bars:, Expose indicator series for the composition engine.      Args:         bars:, _sma()

### Community 45 - "Community 45"
Cohesion: 0.32
Nodes (7): _compute_vwap(), generate_signals(), indicator_outputs(), VWAP Bounce Strategy — intraday mean reversion around VWAP.  Enter long when p, Compute cumulative VWAP series.      Args:         bars: Chronological OHLCV, Generate entry/exit signals based on VWAP bounce.      Args:         bars:, Expose indicator series for the composition engine.      Args:         bars:

### Community 46 - "Community 46"
Cohesion: 0.29
Nodes (2): apiFetch(), _tryRefreshToken()

### Community 47 - "Community 47"
Cohesion: 0.29
Nodes (0): 

### Community 48 - "Community 48"
Cohesion: 0.33
Nodes (5): downgrade(), 0011_user_preferences — Add JSONB preferences column to users table.  Stores u, Add preferences JSONB column to users table., Remove preferences column from users table., upgrade()

### Community 49 - "Community 49"
Cohesion: 0.33
Nodes (5): downgrade(), 0012_reports_email_verify — Add email verification, account management, and use, Remove email_verification_tokens, user_reports, and user account columns., Add email verification columns, user_reports table, and email_verification_token, upgrade()

### Community 50 - "Community 50"
Cohesion: 0.33
Nodes (5): downgrade(), 0013_watchlists_account_lockout — Add account lockout columns and watchlist/wat, Remove watchlist_items, watchlists tables, and lockout columns from users., Add lockout columns to users, create watchlists and watchlist_items tables., upgrade()

### Community 51 - "Community 51"
Cohesion: 0.33
Nodes (5): downgrade(), 0014_profit_taking — Add profit-taking target price column to portfolio positio, Add profit_taking column to portfolio_positions., Remove profit_taking column from portfolio_positions., upgrade()

### Community 52 - "Community 52"
Cohesion: 0.33
Nodes (5): downgrade(), 0015_trading_strategies — Trading AI core tables.  Creates four tables require, Drop trading AI core tables in reverse dependency order., Create trading AI core tables., upgrade()

### Community 53 - "Community 53"
Cohesion: 0.4
Nodes (5): _get_avg_sentiment(), engine/filters.py — Signal filters that gate entry/exit signals.  Provides com, Filter a trading signal based on recent news sentiment scores.      Looks up t, Compute average sentiment score for *symbol* over recent articles.      Querie, sentiment_filter()

### Community 54 - "Community 54"
Cohesion: 0.33
Nodes (5): generate_signals(), indicator_outputs(), Bollinger Band Squeeze Strategy — volatility breakout from Bollinger Band contra, Generate entry/exit signals based on Bollinger Band squeeze breakout.      Arg, Expose indicator series for the composition engine.      Args:         bars:

### Community 55 - "Community 55"
Cohesion: 0.33
Nodes (5): generate_signals(), indicator_outputs(), Breakout Strategy — enter on price breaking above N-bar high with volume confirm, Generate entry/exit signals based on price breakout with volume.      Args:, Expose indicator series for the composition engine.      Args:         bars:

### Community 56 - "Community 56"
Cohesion: 0.33
Nodes (5): generate_signals(), indicator_outputs(), Stochastic Oscillator Strategy — mean reversion using %K/%D crossovers.  Enter, Generate entry/exit signals based on Stochastic Oscillator.      Args:, Expose indicator series for the composition engine.      Args:         bars:

### Community 57 - "Community 57"
Cohesion: 0.4
Nodes (4): GET /health should return 200 when DB and Redis are reachable., GET /health response body should contain status, db, redis, and timestamp., test_health_response_shape(), test_health_returns_200()

### Community 58 - "Community 58"
Cohesion: 0.5
Nodes (1): initial  Revision ID: 0001_initial Revises: Create Date: 2026-01-09 00:00:00

### Community 59 - "Community 59"
Cohesion: 0.5
Nodes (1): password reset tokens  Revision ID: 0002_password_reset_tokens Revises: 0001_

### Community 60 - "Community 60"
Cohesion: 0.5
Nodes (1): integrity fixes  Fix malformed server_defaults (nested quotes), add CASCADE de

### Community 61 - "Community 61"
Cohesion: 0.5
Nodes (1): add refresh_tokens table  Adds the refresh_tokens table used by the P6.3 JWT r

### Community 62 - "Community 62"
Cohesion: 0.5
Nodes (1): add portfolios and portfolio_positions tables  Adds the portfolios and portfol

### Community 63 - "Community 63"
Cohesion: 0.5
Nodes (1): Add asset_type and physical_type to portfolio_positions.  Revision ID: 0006_as

### Community 64 - "Community 64"
Cohesion: 0.5
Nodes (1): Add stop_loss to portfolio_positions.  Revision ID: 0007_stop_loss Revises: 0

### Community 65 - "Community 65"
Cohesion: 0.5
Nodes (1): Create chart_templates table.  Revision ID: 0008_chart_templates Revises: 000

### Community 66 - "Community 66"
Cohesion: 0.5
Nodes (1): Create news_articles and news_article_tickers tables.  Adds the two tables req

### Community 67 - "Community 67"
Cohesion: 0.5
Nodes (1): Create score_outcomes and scoring_rules tables for the feedback loop.  Adds th

### Community 68 - "Community 68"
Cohesion: 0.5
Nodes (1): 0016_intraday_bars — TimescaleDB hypertable for intraday OHLCV data.  Creates

### Community 69 - "Community 69"
Cohesion: 0.5
Nodes (1): 0017_notifications — Notification and webhook tables.  Creates:   - notificat

### Community 70 - "Community 70"
Cohesion: 0.5
Nodes (1): 0018_social_strategies — Strategy ratings and usage tracking tables.  Creates:

### Community 71 - "Community 71"
Cohesion: 0.5
Nodes (1): 0019_paper_trading — Paper trading simulation tables.  Creates:   - paper_tra

### Community 72 - "Community 72"
Cohesion: 0.5
Nodes (1): Portfolio cash tracking  Adds a cash_balance column to the portfolios table an

### Community 73 - "Community 73"
Cohesion: 0.5
Nodes (1): Add cost_basis to portfolio_trades for realized P&L tracking  Records the aver

### Community 74 - "Community 74"
Cohesion: 0.5
Nodes (1): add scan_results table  Revision ID: a1b2 Revises: 0021 Create Date: 2026-05

### Community 75 - "Community 75"
Cohesion: 0.5
Nodes (1): Add rule-engine columns to portfolio_positions  Adds six columns that the port

### Community 76 - "Community 76"
Cohesion: 0.5
Nodes (1): Create rule_alerts table  Stores rule-engine alerts triggered by portfolio pos

### Community 77 - "Community 77"
Cohesion: 0.5
Nodes (1): Add mode column to scan_results  Adds a mode column to distinguish how a scan

### Community 78 - "Community 78"
Cohesion: 0.5
Nodes (1): Add isin and degiro_product_id to portfolio_positions  Revision ID: 0026 Revi

### Community 79 - "Community 79"
Cohesion: 0.5
Nodes (1): add sold_reason to portfolio_positions  Revision ID: 0027 Revises: 0026 Crea

### Community 80 - "Community 80"
Cohesion: 0.5
Nodes (1): Add degiro_transactions table.

### Community 81 - "Community 81"
Cohesion: 0.5
Nodes (3): main(), worker_healthcheck.py — Docker HEALTHCHECK script for TickerTap arq workers., Entry point: parse args, query Redis, print status, exit with code.      Reads

### Community 82 - "Community 82"
Cohesion: 1.0
Nodes (1): dependencies.py — Shared FastAPI dependencies for TickerTap.  Re-exports the c

### Community 83 - "Community 83"
Cohesion: 1.0
Nodes (1): Fetch the latest quote for *symbol*.          Args:             symbol: Ticke

### Community 84 - "Community 84"
Cohesion: 1.0
Nodes (1): Return the provider's supported interval list.          Returns:

### Community 85 - "Community 85"
Cohesion: 1.0
Nodes (1): Return maximum lookback for *interval*.          Args:             interval:

### Community 86 - "Community 86"
Cohesion: 1.0
Nodes (1): Synchronous symbol search via yfinance.          Args:             query: Fre

### Community 87 - "Community 87"
Cohesion: 1.0
Nodes (1): Return the list of candle intervals this provider supports.          Returns:

### Community 88 - "Community 88"
Cohesion: 1.0
Nodes (1): Strategy Templates — pre-built system strategies seeded into the database.  Th

### Community 89 - "Community 89"
Cohesion: 1.0
Nodes (0): 

### Community 90 - "Community 90"
Cohesion: 1.0
Nodes (0): 

### Community 91 - "Community 91"
Cohesion: 1.0
Nodes (0): 

### Community 92 - "Community 92"
Cohesion: 1.0
Nodes (1): Enforce at least 1 uppercase, 1 lowercase, 1 digit, and 1 special character.

### Community 93 - "Community 93"
Cohesion: 1.0
Nodes (1): Enforce at least 1 uppercase, 1 lowercase, 1 digit, and 1 special character.

### Community 94 - "Community 94"
Cohesion: 1.0
Nodes (1): Reject non-positive portfolio values.

### Community 95 - "Community 95"
Cohesion: 1.0
Nodes (1): Allow only known mode values.

### Community 96 - "Community 96"
Cohesion: 1.0
Nodes (1): Reject state values outside the allowed set.

### Community 97 - "Community 97"
Cohesion: 1.0
Nodes (1): Reject schedule values outside the allowed set.

### Community 98 - "Community 98"
Cohesion: 1.0
Nodes (1): Adjust price for slippage.          Entries slip against you (buy higher, sell

### Community 99 - "Community 99"
Cohesion: 1.0
Nodes (1): Build a TradeRecord from an open position and its exit.          Args:

### Community 100 - "Community 100"
Cohesion: 1.0
Nodes (1): Size a position by risking a fixed percentage of the account.          The num

### Community 101 - "Community 101"
Cohesion: 1.0
Nodes (1): Size a position by risking a fixed dollar amount.          Args:

### Community 102 - "Community 102"
Cohesion: 1.0
Nodes (1): Full Kelly criterion — optimal fraction of account to wager.          Formula:

### Community 103 - "Community 103"
Cohesion: 1.0
Nodes (1): Fractional Kelly — conservative variant.          Multiplies the full Kelly fr

### Community 104 - "Community 104"
Cohesion: 1.0
Nodes (1): ATR-based position sizing.          Uses Average True Range to set a volatilit

### Community 105 - "Community 105"
Cohesion: 1.0
Nodes (1): Fetch the latest quote for *symbol*.          Args:             symbol: Ticke

### Community 106 - "Community 106"
Cohesion: 1.0
Nodes (1): Return the list of bar intervals this provider supports.          Returns:

### Community 107 - "Community 107"
Cohesion: 1.0
Nodes (1): Return the maximum historical lookback for *interval*.          Args:

### Community 108 - "Community 108"
Cohesion: 1.0
Nodes (1): Remove duplicate timestamps and sort chronologically.          Args:

### Community 109 - "Community 109"
Cohesion: 1.0
Nodes (1): Check if NYSE is in regular trading hours.

### Community 110 - "Community 110"
Cohesion: 1.0
Nodes (1): Return a numeric sort key so intervals order from shortest to longest.

### Community 111 - "Community 111"
Cohesion: 1.0
Nodes (0): 

### Community 112 - "Community 112"
Cohesion: 1.0
Nodes (0): 

### Community 113 - "Community 113"
Cohesion: 1.0
Nodes (0): 

### Community 114 - "Community 114"
Cohesion: 1.0
Nodes (0): 

## Knowledge Gaps
- **700 isolated node(s):** `env.py — Alembic migration environment for TickerTap.  DATABASE_URL environmen`, `Run migrations in 'offline' mode (no live DB connection required).      Genera`, `Run migrations against a live database connection.`, `initial  Revision ID: 0001_initial Revises: Create Date: 2026-01-09 00:00:00`, `password reset tokens  Revision ID: 0002_password_reset_tokens Revises: 0001_` (+695 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 82`** (2 nodes): `dependencies.py`, `dependencies.py — Shared FastAPI dependencies for TickerTap.  Re-exports the c`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 83`** (2 nodes): `.get_quote()`, `Fetch the latest quote for *symbol*.          Args:             symbol: Ticke`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 84`** (2 nodes): `.get_supported_intervals()`, `Return the provider's supported interval list.          Returns:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 85`** (2 nodes): `Return maximum lookback for *interval*.          Args:             interval:`, `.get_max_history()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 86`** (2 nodes): `Synchronous symbol search via yfinance.          Args:             query: Fre`, `._search_sync()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 87`** (2 nodes): `Return the list of candle intervals this provider supports.          Returns:`, `.get_supported_intervals()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 88`** (2 nodes): `templates.py`, `Strategy Templates — pre-built system strategies seeded into the database.  Th`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 89`** (2 nodes): `eslint.config.js`, `globals.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 90`** (2 nodes): `useContextPopup.js`, `useContextPopup()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 91`** (2 nodes): `useKeyboardShortcuts.js`, `useKeyboardShortcuts()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 92`** (1 nodes): `Enforce at least 1 uppercase, 1 lowercase, 1 digit, and 1 special character.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 93`** (1 nodes): `Enforce at least 1 uppercase, 1 lowercase, 1 digit, and 1 special character.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 94`** (1 nodes): `Reject non-positive portfolio values.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 95`** (1 nodes): `Allow only known mode values.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 96`** (1 nodes): `Reject state values outside the allowed set.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 97`** (1 nodes): `Reject schedule values outside the allowed set.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 98`** (1 nodes): `Adjust price for slippage.          Entries slip against you (buy higher, sell`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 99`** (1 nodes): `Build a TradeRecord from an open position and its exit.          Args:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 100`** (1 nodes): `Size a position by risking a fixed percentage of the account.          The num`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 101`** (1 nodes): `Size a position by risking a fixed dollar amount.          Args:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 102`** (1 nodes): `Full Kelly criterion — optimal fraction of account to wager.          Formula:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 103`** (1 nodes): `Fractional Kelly — conservative variant.          Multiplies the full Kelly fr`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 104`** (1 nodes): `ATR-based position sizing.          Uses Average True Range to set a volatilit`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 105`** (1 nodes): `Fetch the latest quote for *symbol*.          Args:             symbol: Ticke`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 106`** (1 nodes): `Return the list of bar intervals this provider supports.          Returns:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 107`** (1 nodes): `Return the maximum historical lookback for *interval*.          Args:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 108`** (1 nodes): `Remove duplicate timestamps and sort chronologically.          Args:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 109`** (1 nodes): `Check if NYSE is in regular trading hours.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 110`** (1 nodes): `Return a numeric sort key so intervals order from shortest to longest.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 111`** (1 nodes): `setup.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 112`** (1 nodes): `chartStyles.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 113`** (1 nodes): `shared.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 114`** (1 nodes): `vite.config.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `User` connect `Community 2` to `Community 1`, `Community 4`, `Community 6`?**
  _High betweenness centrality (0.065) - this node is a cross-community bridge._
- **Why does `RuleContext` connect `Community 3` to `Community 1`, `Community 5`?**
  _High betweenness centrality (0.050) - this node is a cross-community bridge._
- **Why does `RuleAlertData` connect `Community 3` to `Community 1`, `Community 5`?**
  _High betweenness centrality (0.050) - this node is a cross-community bridge._
- **Are the 173 inferred relationships involving `User` (e.g. with `admin.py — Admin-only routes for TickerTap.  Provides endpoints for user and a` and `Return 200 if the caller is an admin, else 403 from the dependency.      The f`) actually correct?**
  _`User` has 173 INFERRED edges - model-reasoned connections that need verification._
- **Are the 115 inferred relationships involving `AuditLog` (e.g. with `admin.py — Admin-only routes for TickerTap.  Provides endpoints for user and a` and `Return 200 if the caller is an admin, else 403 from the dependency.      The f`) actually correct?**
  _`AuditLog` has 115 INFERRED edges - model-reasoned connections that need verification._
- **Are the 104 inferred relationships involving `RuleContext` (e.g. with `models/__init__.py — ML model registry for the trading-ml container.  Re-expor` and `analyst.py — Analyst consensus rule checker.  Fires when current price is sign`) actually correct?**
  _`RuleContext` has 104 INFERRED edges - model-reasoned connections that need verification._
- **Are the 104 inferred relationships involving `RuleAlertData` (e.g. with `models/__init__.py — ML model registry for the trading-ml container.  Re-expor` and `analyst.py — Analyst consensus rule checker.  Fires when current price is sign`) actually correct?**
  _`RuleAlertData` has 104 INFERRED edges - model-reasoned connections that need verification._