# Graph Report - .  (2026-09-08)

## Corpus Check
- 197 files · ~0 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 3097 nodes · 10440 edges · 136 communities detected
- Extraction: 31% EXTRACTED · 69% INFERRED · 0% AMBIGUOUS · INFERRED: 7178 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## God Nodes (most connected - your core abstractions)
1. `User` - 190 edges
2. `PortfolioPosition` - 128 edges
3. `AuditLog` - 120 edges
4. `Portfolio` - 115 edges
5. `Notification` - 115 edges
6. `RuleContext` - 106 edges
7. `RuleAlertData` - 106 edges
8. `Strategy` - 103 edges
9. `YFinanceProvider` - 98 edges
10. `NormalizedDataService` - 95 edges

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
Cohesion: 0.01
Nodes (349): _apply_stage_result(), _build_soft_stop_report(), _check_condition(), _check_soft_stops(), evaluate_one_soft_stop(), evaluate_price_alerts(), _fetch_daily_close(), _fetch_price() (+341 more)

### Community 1 - "Community 1"
Cohesion: 0.02
Nodes (277): admin_check(), list_audit_logs(), list_users(), lock_account(), lock_user(), admin.py — Admin-only routes for TickerTap.  Provides endpoints for user and a, Lock or unlock a brokerage account atomically.      Eliminates duplication bet, List all registered users, ordered newest-first.      Args:         db: Async (+269 more)

### Community 2 - "Community 2"
Cohesion: 0.03
Nodes (118): check_analyst_consensus(), analyst.py — Analyst consensus rule checker.  Fires when current price is sign, Check if price is above analyst consensus target.      Args:         ctx:, check_buckets(), buckets.py — Rule 13: Bucket allocation checker.  Fires when any bucket deviat, Check bucket allocation vs targets.      Args:         ctx: RuleContext with, check_fundamentals_health(), fundamentals.py — Fundamental health rule checker.  Checks debt-to-equity stre (+110 more)

### Community 3 - "Community 3"
Cohesion: 0.2
Nodes (182): LLMTranspileError, Raised when LLM translation or validation fails., MarketDataProvider, BacktestResult, Notification, PaperTrade, PaperTradeEquitySnapshot, PaperTradePosition (+174 more)

### Community 4 - "Community 4"
Cohesion: 0.01
Nodes (126): Exception, _get_parser(), parse(), _preprocess_kwargs(), PineScript Grammar — lark EBNF grammar for the supported PineScript subset.  D, Lazily create and return the lark parser (cached singleton).      Returns:, Result from PineScript validation.      Attributes:         valid:  True if s, Convert keyword arguments into marker-pair positional arguments.      Transfor (+118 more)

### Community 5 - "Community 5"
Cohesion: 0.07
Nodes (94): _aggregate_bars(), ExchangeRateResponse, _fetch_earnings_dates_set(), _fetch_events(), _fetch_exchange_rates(), _fetch_fundamentals(), _fetch_ohlcv(), _fetch_ohlcv_interval() (+86 more)

### Community 6 - "Community 6"
Cohesion: 0.03
Nodes (95): cleanup_dead_letters(), _connect(), enqueue(), enqueue_batch(), get_pending(), increment_retries(), init_db(), mark_done() (+87 more)

### Community 7 - "Community 7"
Cohesion: 0.03
Nodes (93): BaseHTTPMiddleware, limiter.py — Shared SlowAPI rate-limiter instance for TickerTap.  Centralised, CorrelationIDMiddleware, health(), metrics(), main.py — FastAPI application entry point for TickerTap.  Configures middlewar, Validate critical configuration on startup.      Performs the following checks, Injects security headers on every response.      Provides a defence-in-depth l (+85 more)

### Community 8 - "Community 8"
Cohesion: 0.1
Nodes (78): analyse_stock(), AnalysisResponse, approve_refinement(), _build_prompt(), _call_ollama(), _check_rules(), _compute_atr(), _compute_rsi() (+70 more)

### Community 9 - "Community 9"
Cohesion: 0.04
Nodes (59): advice_lines(), format_advice_block(), load_investment_rules(), _news_bias(), _position_phase_note(), briefing_advice.py — Template advice from investment_rules.json + book.  No LLM., Two-level stop line using the position's actual stored levels rather     than a, Squeeze/crowding context from FINRA's biweekly short-interest data —     a fresh (+51 more)

### Community 10 - "Community 10"
Cohesion: 0.06
Nodes (58): AuthOut, create_access_token(), decode_access_token(), hash_password(), login(), LoginIn, auth.py — Core authentication utilities for TickerTap.  Provides password hash, Raise on startup if the JWT secret is still the insecure default.      Called (+50 more)

### Community 11 - "Community 11"
Cohesion: 0.06
Nodes (44): annualized_return(), avg_loss(), avg_win(), benchmark_comparison(), calmar_ratio(), compute_all(), expectancy(), get_worker_metrics() (+36 more)

### Community 12 - "Community 12"
Cohesion: 0.08
Nodes (36): _fetch_map(), cik_ticker_map.py — CIK -> ticker resolution via SEC's free company_tickers.json, Best-effort CIK -> ticker. None if unresolvable (private issuer,     stale cache, resolve_ticker(), _mdy_to_iso(), parse_form144_xml(), form144_edgar.py — Parse SEC Form 144 (Notice of Proposed Sale) atom + XML.  An, One proposed-sale notice per filing (unlike Form 4's multi-row shape).      Retu (+28 more)

### Community 13 - "Community 13"
Cohesion: 0.08
Nodes (31): _adx(), _atr(), _bollinger_pctb(), _build_train_data(), _ema(), _engineer_features(), FeatureClassifier, _get_top_features() (+23 more)

### Community 14 - "Community 14"
Cohesion: 0.09
Nodes (36): Queued or completed Volume Flow Scanner job with full results.      Stores the, ScanResult, get_latest_scan(), get_scan_result(), routes/scanner.py — Volume Flow Scanner endpoints.  Exposes three routes under, Start a Volume Flow Scan in the background.      Creates a pending ScanResult, Return the most recent scan result for the current user.      Args:         d, Return a specific scan result by ID.      Args:         result_id:    UUID st (+28 more)

### Community 15 - "Community 15"
Cohesion: 0.08
Nodes (22): make_mock_item(), make_mock_watchlist(), make_scalar_count_result(), ============================================================================ TE, Tests for watchlist create, list, get, and delete operations., Valid name payload should return 201 with the new watchlist., Omitting the name field should return 422 Unprocessable Entity., User with no watchlists should receive an empty JSON array. (+14 more)

### Community 16 - "Community 16"
Cohesion: 0.17
Nodes (24): _deps(), _deps_multi(), MapFetcher, _mapping(), test_144_notice_note_appended_to_sell_telegram_body(), test_all_new_features_together(), test_cycle_avoid_ticker_no_telegram(), test_cycle_does_not_renotify_same_accession() (+16 more)

### Community 17 - "Community 17"
Cohesion: 0.07
Nodes (31): adx(), atr(), bollinger_bands(), crossover(), crossunder(), ema(), highest(), lowest() (+23 more)

### Community 18 - "Community 18"
Cohesion: 0.07
Nodes (20): make_mock_alert(), ============================================================================ TE, Symbols in lowercase should be stored and returned uppercase., An unrecognised condition value must fail Pydantic validation (422)., User already at the 50-alert cap should receive 400 Bad Request., User with 49 active alerts should be able to create one more., Tests for alert listing endpoint., User with no alerts should receive an empty JSON array. (+12 more)

### Community 19 - "Community 19"
Cohesion: 0.08
Nodes (30): FeatureResponse, health(), _load_models(), LSTMResponse, OHLCVRow, PatternResponse, predict_features(), predict_lstm() (+22 more)

### Community 20 - "Community 20"
Cohesion: 0.09
Nodes (12): ============================================================================ TES, _rows_result(), _session_cm(), test_fetch_failure_returns_gracefully(), test_no_tracked_tickers_skips_fetch(), test_skips_already_stored_ticker_settlement_pair(), test_stores_matched_rows_and_dedupes(), TestFindLatestSettlementDate (+4 more)

### Community 21 - "Community 21"
Cohesion: 0.1
Nodes (27): _call_indicator(), _check_stop_loss(), _compute_indicators(), _eval_comparison(), _eval_condition(), _eval_logical(), _extract_price_series(), _generate_signals() (+19 more)

### Community 22 - "Community 22"
Cohesion: 0.1
Nodes (10): TelegramLinkRequest, ============================================================================ TES, This endpoint must work for a not-yet-registered visitor., A regular user's own JWT must not be able to call this — only         the bot's, TestCheckTelegramInvite, TestCreateTelegramInvite, TestLinkTelegramChat, TestRegisterWithTelegramInvite (+2 more)

### Community 23 - "Community 23"
Cohesion: 0.09
Nodes (17): make_mock_strategy(), ============================================================================ TE, GET /strategies without auth should return 401 or 403., Tests for single-strategy retrieval., Fetching an owned strategy by ID should return 200., Fetching a non-existent strategy should return 404., System strategies should be accessible to any authenticated user., Tests for the backtest queuing endpoint. (+9 more)

### Community 24 - "Community 24"
Cohesion: 0.1
Nodes (25): _et(), TEST SUITE: Scanner Session Detection MODULE UNDER TEST: app.trading.scanner_se, 4:00 PM ET is at/after the regular close; elapsed weight must be 1.0., project_daily_volume must return intraday_vol unchanged when elapsed_weight == 0, At 50% session elapsed, projected volume should be double the intraday volume., Build a timezone-aware datetime in US/Eastern for use in tests.      Args:, Saturday noon ET must yield 'closed' regardless of time., Monday 8:00 AM ET is within pre-market hours (4:00–9:30 AM). (+17 more)

### Community 25 - "Community 25"
Cohesion: 0.16
Nodes (23): _delete_manual_positions(), _extract_cash_balance(), _flatten_position(), _get_account_overview(), _get_int_account(), _get_portfolio(), _get_products_info(), _get_stop_orders() (+15 more)

### Community 26 - "Community 26"
Cohesion: 0.15
Nodes (17): FakePos, TEST SUITE: Two-stage soft-stop alerts MODULE UNDER TEST: app.trading.alert_wor, Mirrors modify_position: any actual soft-stop change clears stage state., Do not hit yfinance / news tables during unit tests., _session_with(), _stub_soft_stop_report(), test_both_channels_fail_does_not_mark_date(), test_changing_soft_stop_value_resets_stage_dates() (+9 more)

### Community 27 - "Community 27"
Cohesion: 0.13
Nodes (17): _api_get(), _api_post(), cmd_alerts(), cmd_analyze(), cmd_approve_refinement(), cmd_buy(), cmd_link(), cmd_pnl() (+9 more)

### Community 28 - "Community 28"
Cohesion: 0.21
Nodes (21): create_template(), delete_template(), get_template(), _get_template_or_404(), list_templates(), routes/chart_templates.py — Chart Template CRUD API endpoints.  Provides CRUD, Partially update a chart template (ownership enforced)., Delete a chart template (ownership enforced). (+13 more)

### Community 29 - "Community 29"
Cohesion: 0.11
Nodes (21): _aggregate_5min(), archive_intraday(), _daily_downsample(), downsample_daily(), _fetch_and_store_bars(), _get_active_symbols(), _is_market_open(), trading/archiver.py — Intraday data archiver worker.  Background worker that: (+13 more)

### Community 30 - "Community 30"
Cohesion: 0.15
Nodes (19): _get_dividend_zones(), _get_earnings_zones(), _get_fomc_zones(), get_no_trade_zones(), _get_opex_dates(), _get_opex_zones(), is_in_no_trade_zone(), NoTradeZone (+11 more)

### Community 31 - "Community 31"
Cohesion: 0.12
Nodes (13): _get_cached(), _is_market_open(), YFinance Provider — MarketDataProvider implementation backed by yfinance.  Wra, Fetch OHLCV bars from yfinance and return normalised OHLCVBars.          Args:, Fetch the latest quote for *symbol* from yfinance.          Args:, Search for symbols matching *query* via yfinance.          Args:, Synchronous OHLCV fetch from yfinance.          Args:             sym:, Synchronous quote fetch from yfinance.          Args:             sym: Upper- (+5 more)

### Community 32 - "Community 32"
Cohesion: 0.15
Nodes (11): _book(), test_gate_blocks_10b5(), test_gate_blocks_avoid_list(), test_gate_blocks_sector_cap(), test_gate_blocks_tiny_notional(), test_gate_critical_de_blocks_buy(), test_gate_officer_buy_passes(), test_gate_sell_held_10b5_small_stake_is_info() (+3 more)

### Community 33 - "Community 33"
Cohesion: 0.15
Nodes (17): _call_indicator(), _compute_composed_indicators(), _eval_expression(), _eval_node(), _generate_composed_signals(), Strategy Composition Engine — evaluates a graph of indicator nodes and boolean, Recursively validate every node in the expression AST.      Args:         nod, Evaluate a pre-validated expression against a variable namespace.      Args: (+9 more)

### Community 34 - "Community 34"
Cohesion: 0.15
Nodes (17): _build_user_prompt(), _call_ollama(), _extract_call_name(), llm_transpile(), _parse_llm_response(), PineScript LLM Fallback — translates unsupported PineScript via Ollama.  When, Parse and whitelist-walk the LLM-generated Python code.      Rejects any const, Recursively validate an AST node and all its children.      Args:         nod (+9 more)

### Community 35 - "Community 35"
Cohesion: 0.11
Nodes (17): auth_client(), make_all_result(), make_scalar_count_result(), make_scalar_result(), make_scalars_result(), mock_db_session(), mock_user(), ============================================================================ Sh (+9 more)

### Community 36 - "Community 36"
Cohesion: 0.11
Nodes (11): ============================================================================ TE, Integration tests for listing the current user's accounts., No accounts for this user should return an empty JSON array., A user with one account should receive a list of length 1., Requests without authentication should be rejected (401 or 403)., Integration tests for account creation endpoint., Valid payload should return 201 with account data., Omitting the required account_type field must return 422. (+3 more)

### Community 37 - "Community 37"
Cohesion: 0.25
Nodes (17): _filed_result(), _held_result(), _mock_request(), ============================================================================ TES, Mock for the open-positions query: result.all() -> [(ticker,), ...]., Mock for the Form 4 filers query: result.all() ->     [(ticker, latest_transacti, test_blank_tickers_skipped(), test_capped_at_watch_ticker_limit() (+9 more)

### Community 38 - "Community 38"
Cohesion: 0.15
Nodes (9): _FakeFetcher, ============================================================================ TE, Serves fixed content per URL — mirrors EdgarFetcher's interface     without any, _SessionLocal() is used as `async with _SessionLocal() as session:`., _session_cm(), test_poll_continues_after_per_entry_error(), test_poll_skips_already_stored_accession(), test_poll_stores_new_notice_with_resolved_ticker() (+1 more)

### Community 39 - "Community 39"
Cohesion: 0.17
Nodes (15): analyse_with_ollama(), build_analysis_prompt(), compute_statistics(), fetch_outcomes(), main(), _parse_analysis_json(), post_rules(), learner.py — TickerTap scoring accuracy analyser for the remote worker host. (+7 more)

### Community 40 - "Community 40"
Cohesion: 0.17
Nodes (15): build_learning_prompt(), compute_strategy_stats(), fetch_backtest_history(), learn_with_ollama(), main(), _parse_learning_json(), post_strategy_rules(), strategy_learner.py — Strategy performance learner for the remote worker host. (+7 more)

### Community 41 - "Community 41"
Cohesion: 0.17
Nodes (15): build_research_prompt(), fetch_recent_backtests(), fetch_regime_summary(), main(), _parse_research_json(), post_recommendations(), strategy_researcher.py — Strategy research agent for the remote worker host., Fetch current market regime summary from Server A.      Returns:         Dict (+7 more)

### Community 42 - "Community 42"
Cohesion: 0.22
Nodes (11): atr_based(), fixed_dollar(), fixed_percentage(), fractional_kelly(), kelly(), PositionSizer, engine/risk.py — Position sizing and risk management models.  Provides the ``P, Automatically choose and apply the best sizing model.          Prefers ATR-bas (+3 more)

### Community 43 - "Community 43"
Cohesion: 0.19
Nodes (13): _make_redis_mock(), TEST SUITE: Worker Metrics Endpoint MODULE UNDER TEST: app.routes.metrics TEST, Workers should report 'no_heartbeat' when the Redis key does not exist.      R, Endpoint should return {error: ...} gracefully when Redis is down.      aiored, Response must contain exactly the three known arq workers as top-level keys., Build a mock aioredis client with pre-configured async methods.      Args:, All workers should report 'healthy' when their heartbeat is recent.      A hea, All workers should report 'stale' when their heartbeat is 2000 s old.      200 (+5 more)

### Community 44 - "Community 44"
Cohesion: 0.14
Nodes (9): ============================================================================ TE, Tests for the positions listing endpoint., User with no accounts should receive an empty positions list., GET /positions without auth should return 401 or 403., Tests for the portfolio summary endpoint., User with no accounts should receive a zero-value summary., GET /summary without auth should return 401 or 403., TestGetPositions (+1 more)

### Community 45 - "Community 45"
Cohesion: 0.2
Nodes (6): _fill_profile_fields(), ============================================================================ TES, auth_client's shared mock_user fixture only sets user_id/email/is_active/     is, Regression: sidebar_collapsed was documented in the schema's         docstring b, TestGetProfileTutorialDefault, TestUpdatePreferencesTutorial

### Community 46 - "Community 46"
Cohesion: 0.27
Nodes (7): _mock_response(), ============================================================================ TES, test_network_error_falls_back_to_stale_cache_instead_of_raising(), test_resolves_ticker_for_known_cik(), test_second_call_within_ttl_does_not_refetch(), test_strips_leading_zeros_from_cik(), test_unknown_cik_returns_none()

### Community 47 - "Community 47"
Cohesion: 0.29
Nodes (9): BreakerStatus, check_circuit_breaker(), check_drawdown(), engine/circuit_breaker.py — Drawdown circuit breaker for strategy risk control., Check and enforce the circuit breaker for a strategy.      Loads recent backte, Execute circuit breaker trip: deactivate signals, notify, and log.      Args:, Result of a circuit breaker check.      Attributes:         tripped:        T, Check if the equity curve's drawdown exceeds the threshold.      Computes the (+1 more)

### Community 48 - "Community 48"
Cohesion: 0.27
Nodes (9): DecayResult, detect_decay(), detect_decay_for_strategy(), engine/decay.py — Strategy performance decay detection.  Monitors rolling stra, Load recent backtest results for a strategy and check for decay.      Queries, Compute rolling annualised Sharpe ratios.      Args:         returns:       B, Result of a strategy decay check.      Attributes:         is_decaying:    Tr, Detect performance decay from an equity curve.      Computes rolling Sharpe ra (+1 more)

### Community 49 - "Community 49"
Cohesion: 0.24
Nodes (9): get_elapsed_weight(), get_market_session(), get_session_context(), project_daily_volume(), scanner_session.py — Market session detection and volume projection for the scan, Return the current market session label for a given Eastern-time datetime., Return the fraction of the regular NYSE session elapsed at the given time., Project a full-day volume estimate from intraday volume and elapsed weight. (+1 more)

### Community 50 - "Community 50"
Cohesion: 0.2
Nodes (2): ============================================================================ TES, TestMdyToIso

### Community 51 - "Community 51"
Cohesion: 0.22
Nodes (5): _dedupe_and_sort(), Normalized Data Service — single entry point for strategy data consumption.  S, Fetch aligned OHLCV data at multiple intervals.          Intraday intervals ar, Read bars from the intraday_bars TimescaleDB hypertable.          Args:, Fetch normalised OHLCV bars for a single symbol and interval.          For int

### Community 52 - "Community 52"
Cohesion: 0.22
Nodes (1): Tests for redesigned insider Telegram briefing (10b5-1, stake %, pattern, concer

### Community 53 - "Community 53"
Cohesion: 0.22
Nodes (3): ============================================================================ TES, Grants/withholding (A/F) shouldn't count toward sample_size or be     scored — o, test_non_ps_codes_are_ignored()

### Community 54 - "Community 54"
Cohesion: 0.29
Nodes (7): ask_guide(), GuideAskRequest, GuideAskResponse, routes/guide.py — User Guide AI Q&A endpoint.  Proxies user questions to the c, Schema for a user question submitted to the guide endpoint.      Attributes:, Schema for the guide endpoint response.      Attributes:         answer: The, Submit a question to the TickerTap AI guide.      Proxies the question to the

### Community 55 - "Community 55"
Cohesion: 0.36
Nodes (7): _build_doc(), _get_collection_id(), query_similar(), chromadb_client.py — ChromaDB client for trade analysis embeddings.  Uses raw, Find similar past analyses with known outcomes for RAG context., Upsert a trade analysis embedding. Returns chromadb_id or None on failure., store_analysis()

### Community 56 - "Community 56"
Cohesion: 0.32
Nodes (7): generate_signals(), indicator_outputs(), ADX Trend Strategy — enter on strong trend confirmation via ADX.  Enter long w, Expose indicator series for the composition engine.      Args:         bars:, Wilder's smoothing (used in ADX/DI calculations).      Args:         values:, Generate entry/exit signals based on ADX trend strength.      Args:         b, _wilder_smooth()

### Community 57 - "Community 57"
Cohesion: 0.32
Nodes (7): _ema(), generate_signals(), indicator_outputs(), EMA Crossover Strategy — trend-following using exponential moving averages.  F, Compute exponential moving average series.      Args:         closes: List of, Generate entry/exit signals based on EMA crossover.      Args:         bars:, Expose indicator series for the composition engine.      Args:         bars:

### Community 58 - "Community 58"
Cohesion: 0.32
Nodes (7): generate_signals(), indicator_outputs(), _period_high_low(), Ichimoku Cloud Strategy — trend-following using Ichimoku Kinko Hyo components., Expose indicator series for the composition engine.      Args:         bars:, Compute highest high and lowest low over a lookback window.      Args:, Generate entry/exit signals based on Ichimoku Cloud.      Args:         bars:

### Community 59 - "Community 59"
Cohesion: 0.32
Nodes (7): _ema(), generate_signals(), indicator_outputs(), MACD Crossover Strategy — trend-following using MACD line/signal crossovers., Expose indicator series for the composition engine.      Args:         bars:, Compute EMA series (SMA-seeded)., Generate entry/exit signals based on MACD crossover.      Args:         bars:

### Community 60 - "Community 60"
Cohesion: 0.32
Nodes (7): generate_signals(), indicator_outputs(), RSI Mean Reversion Strategy — fade overbought/oversold RSI readings.  Enter lo, Expose indicator series for the composition engine.      Args:         bars:, Compute RSI series using Wilder's smoothing.      Args:         closes: List, Generate entry/exit signals based on RSI mean reversion.      Args:         b, _rsi()

### Community 61 - "Community 61"
Cohesion: 0.32
Nodes (7): generate_signals(), indicator_outputs(), SMA Crossover Strategy — trend-following using simple moving average crossovers., Compute simple moving average series.      Args:         closes: List of clos, Generate entry/exit signals based on SMA crossover.      Args:         bars:, Expose indicator series for the composition engine.      Args:         bars:, _sma()

### Community 62 - "Community 62"
Cohesion: 0.32
Nodes (7): _compute_vwap(), generate_signals(), indicator_outputs(), VWAP Bounce Strategy — intraday mean reversion around VWAP.  Enter long when p, Compute cumulative VWAP series.      Args:         bars: Chronological OHLCV, Generate entry/exit signals based on VWAP bounce.      Args:         bars:, Expose indicator series for the composition engine.      Args:         bars:

### Community 63 - "Community 63"
Cohesion: 0.29
Nodes (2): apiFetch(), _tryRefreshToken()

### Community 64 - "Community 64"
Cohesion: 0.29
Nodes (0): 

### Community 65 - "Community 65"
Cohesion: 0.33
Nodes (5): downgrade(), 0011_user_preferences — Add JSONB preferences column to users table.  Stores u, Add preferences JSONB column to users table., Remove preferences column from users table., upgrade()

### Community 66 - "Community 66"
Cohesion: 0.33
Nodes (5): downgrade(), 0012_reports_email_verify — Add email verification, account management, and use, Remove email_verification_tokens, user_reports, and user account columns., Add email verification columns, user_reports table, and email_verification_token, upgrade()

### Community 67 - "Community 67"
Cohesion: 0.33
Nodes (5): downgrade(), 0013_watchlists_account_lockout — Add account lockout columns and watchlist/wat, Remove watchlist_items, watchlists tables, and lockout columns from users., Add lockout columns to users, create watchlists and watchlist_items tables., upgrade()

### Community 68 - "Community 68"
Cohesion: 0.33
Nodes (5): downgrade(), 0014_profit_taking — Add profit-taking target price column to portfolio positio, Add profit_taking column to portfolio_positions., Remove profit_taking column from portfolio_positions., upgrade()

### Community 69 - "Community 69"
Cohesion: 0.33
Nodes (5): downgrade(), 0015_trading_strategies — Trading AI core tables.  Creates four tables require, Drop trading AI core tables in reverse dependency order., Create trading AI core tables., upgrade()

### Community 70 - "Community 70"
Cohesion: 0.4
Nodes (5): _get_avg_sentiment(), engine/filters.py — Signal filters that gate entry/exit signals.  Provides com, Filter a trading signal based on recent news sentiment scores.      Looks up t, Compute average sentiment score for *symbol* over recent articles.      Querie, sentiment_filter()

### Community 71 - "Community 71"
Cohesion: 0.33
Nodes (5): generate_signals(), indicator_outputs(), Bollinger Band Squeeze Strategy — volatility breakout from Bollinger Band contra, Generate entry/exit signals based on Bollinger Band squeeze breakout.      Arg, Expose indicator series for the composition engine.      Args:         bars:

### Community 72 - "Community 72"
Cohesion: 0.33
Nodes (5): generate_signals(), indicator_outputs(), Breakout Strategy — enter on price breaking above N-bar high with volume confirm, Generate entry/exit signals based on price breakout with volume.      Args:, Expose indicator series for the composition engine.      Args:         bars:

### Community 73 - "Community 73"
Cohesion: 0.33
Nodes (5): generate_signals(), indicator_outputs(), Stochastic Oscillator Strategy — mean reversion using %K/%D crossovers.  Enter, Generate entry/exit signals based on Stochastic Oscillator.      Args:, Expose indicator series for the composition engine.      Args:         bars:

### Community 74 - "Community 74"
Cohesion: 0.4
Nodes (4): GET /health should return 200 when DB and Redis are reachable., GET /health response body should contain status, db, redis, and timestamp., test_health_response_shape(), test_health_returns_200()

### Community 75 - "Community 75"
Cohesion: 0.5
Nodes (1): initial  Revision ID: 0001_initial Revises: Create Date: 2026-01-09 00:00:00

### Community 76 - "Community 76"
Cohesion: 0.5
Nodes (1): password reset tokens  Revision ID: 0002_password_reset_tokens Revises: 0001_

### Community 77 - "Community 77"
Cohesion: 0.5
Nodes (1): integrity fixes  Fix malformed server_defaults (nested quotes), add CASCADE de

### Community 78 - "Community 78"
Cohesion: 0.5
Nodes (1): add refresh_tokens table  Adds the refresh_tokens table used by the P6.3 JWT r

### Community 79 - "Community 79"
Cohesion: 0.5
Nodes (1): add portfolios and portfolio_positions tables  Adds the portfolios and portfol

### Community 80 - "Community 80"
Cohesion: 0.5
Nodes (1): Add asset_type and physical_type to portfolio_positions.  Revision ID: 0006_as

### Community 81 - "Community 81"
Cohesion: 0.5
Nodes (1): Add stop_loss to portfolio_positions.  Revision ID: 0007_stop_loss Revises: 0

### Community 82 - "Community 82"
Cohesion: 0.5
Nodes (1): Create chart_templates table.  Revision ID: 0008_chart_templates Revises: 000

### Community 83 - "Community 83"
Cohesion: 0.5
Nodes (1): Create news_articles and news_article_tickers tables.  Adds the two tables req

### Community 84 - "Community 84"
Cohesion: 0.5
Nodes (1): Create score_outcomes and scoring_rules tables for the feedback loop.  Adds th

### Community 85 - "Community 85"
Cohesion: 0.5
Nodes (1): 0016_intraday_bars — TimescaleDB hypertable for intraday OHLCV data.  Creates

### Community 86 - "Community 86"
Cohesion: 0.5
Nodes (1): 0017_notifications — Notification and webhook tables.  Creates:   - notificat

### Community 87 - "Community 87"
Cohesion: 0.5
Nodes (1): 0018_social_strategies — Strategy ratings and usage tracking tables.  Creates:

### Community 88 - "Community 88"
Cohesion: 0.5
Nodes (1): 0019_paper_trading — Paper trading simulation tables.  Creates:   - paper_tra

### Community 89 - "Community 89"
Cohesion: 0.5
Nodes (1): Portfolio cash tracking  Adds a cash_balance column to the portfolios table an

### Community 90 - "Community 90"
Cohesion: 0.5
Nodes (1): Add cost_basis to portfolio_trades for realized P&L tracking  Records the aver

### Community 91 - "Community 91"
Cohesion: 0.5
Nodes (1): add scan_results table  Revision ID: a1b2 Revises: 0021 Create Date: 2026-05

### Community 92 - "Community 92"
Cohesion: 0.5
Nodes (1): Add rule-engine columns to portfolio_positions  Adds six columns that the port

### Community 93 - "Community 93"
Cohesion: 0.5
Nodes (1): Create rule_alerts table  Stores rule-engine alerts triggered by portfolio pos

### Community 94 - "Community 94"
Cohesion: 0.5
Nodes (1): Add mode column to scan_results  Adds a mode column to distinguish how a scan

### Community 95 - "Community 95"
Cohesion: 0.5
Nodes (1): Add isin and degiro_product_id to portfolio_positions  Revision ID: 0026 Revi

### Community 96 - "Community 96"
Cohesion: 0.5
Nodes (1): add sold_reason to portfolio_positions  Revision ID: 0027 Revises: 0026 Crea

### Community 97 - "Community 97"
Cohesion: 0.5
Nodes (1): Add degiro_transactions table.

### Community 98 - "Community 98"
Cohesion: 0.5
Nodes (1): Rename stop_loss to hard_stop_loss; add soft_stop_loss.

### Community 99 - "Community 99"
Cohesion: 0.5
Nodes (1): Add trade_analyses table.

### Community 100 - "Community 100"
Cohesion: 0.5
Nodes (1): Add rule_refinements table for AI-suggested rule changes.

### Community 101 - "Community 101"
Cohesion: 0.5
Nodes (1): Track two-stage soft-stop alert delivery without clearing the stop.

### Community 102 - "Community 102"
Cohesion: 0.5
Nodes (1): Store ingested Form 4 non-derivative transactions.

### Community 103 - "Community 103"
Cohesion: 0.5
Nodes (1): Add shares_after / stake_pct and owner-history index on insider_filings.

### Community 104 - "Community 104"
Cohesion: 0.5
Nodes (1): Per-user Telegram chat linking: telegram_invites table + users columns.

### Community 105 - "Community 105"
Cohesion: 0.5
Nodes (1): Store ingested Form 144 (Notice of Proposed Sale) filings.

### Community 106 - "Community 106"
Cohesion: 0.5
Nodes (1): Store FINRA biweekly short-interest snapshots for tracked tickers.

### Community 107 - "Community 107"
Cohesion: 0.5
Nodes (3): main(), worker_healthcheck.py — Docker HEALTHCHECK script for TickerTap arq workers., Entry point: parse args, query Redis, print status, exit with code.      Reads

### Community 108 - "Community 108"
Cohesion: 1.0
Nodes (1): dependencies.py — Shared FastAPI dependencies for TickerTap.  Re-exports the c

### Community 109 - "Community 109"
Cohesion: 1.0
Nodes (1): Strategy Templates — pre-built system strategies seeded into the database.  Th

### Community 110 - "Community 110"
Cohesion: 1.0
Nodes (0): 

### Community 111 - "Community 111"
Cohesion: 1.0
Nodes (0): 

### Community 112 - "Community 112"
Cohesion: 1.0
Nodes (0): 

### Community 113 - "Community 113"
Cohesion: 1.0
Nodes (1): Enforce at least 1 uppercase, 1 lowercase, 1 digit, and 1 special character.

### Community 114 - "Community 114"
Cohesion: 1.0
Nodes (1): Enforce at least 1 uppercase, 1 lowercase, 1 digit, and 1 special character.

### Community 115 - "Community 115"
Cohesion: 1.0
Nodes (1): Reject non-positive portfolio values.

### Community 116 - "Community 116"
Cohesion: 1.0
Nodes (1): Allow only known mode values.

### Community 117 - "Community 117"
Cohesion: 1.0
Nodes (1): Reject state values outside the allowed set.

### Community 118 - "Community 118"
Cohesion: 1.0
Nodes (1): Reject schedule values outside the allowed set.

### Community 119 - "Community 119"
Cohesion: 1.0
Nodes (1): Adjust price for slippage.          Entries slip against you (buy higher, sell

### Community 120 - "Community 120"
Cohesion: 1.0
Nodes (1): Build a TradeRecord from an open position and its exit.          Args:

### Community 121 - "Community 121"
Cohesion: 1.0
Nodes (1): Size a position by risking a fixed percentage of the account.          The num

### Community 122 - "Community 122"
Cohesion: 1.0
Nodes (1): Size a position by risking a fixed dollar amount.          Args:

### Community 123 - "Community 123"
Cohesion: 1.0
Nodes (1): Full Kelly criterion — optimal fraction of account to wager.          Formula:

### Community 124 - "Community 124"
Cohesion: 1.0
Nodes (1): Fractional Kelly — conservative variant.          Multiplies the full Kelly fr

### Community 125 - "Community 125"
Cohesion: 1.0
Nodes (1): ATR-based position sizing.          Uses Average True Range to set a volatilit

### Community 126 - "Community 126"
Cohesion: 1.0
Nodes (1): Fetch the latest quote for *symbol*.          Args:             symbol: Ticke

### Community 127 - "Community 127"
Cohesion: 1.0
Nodes (1): Return the list of bar intervals this provider supports.          Returns:

### Community 128 - "Community 128"
Cohesion: 1.0
Nodes (1): Return the maximum historical lookback for *interval*.          Args:

### Community 129 - "Community 129"
Cohesion: 1.0
Nodes (1): Remove duplicate timestamps and sort chronologically.          Args:

### Community 130 - "Community 130"
Cohesion: 1.0
Nodes (1): Check if NYSE is in regular trading hours.

### Community 131 - "Community 131"
Cohesion: 1.0
Nodes (1): Return a numeric sort key so intervals order from shortest to longest.

### Community 132 - "Community 132"
Cohesion: 1.0
Nodes (0): 

### Community 133 - "Community 133"
Cohesion: 1.0
Nodes (0): 

### Community 134 - "Community 134"
Cohesion: 1.0
Nodes (0): 

### Community 135 - "Community 135"
Cohesion: 1.0
Nodes (0): 

## Knowledge Gaps
- **778 isolated node(s):** `env.py — Alembic migration environment for TickerTap.  DATABASE_URL environmen`, `Run migrations in 'offline' mode (no live DB connection required).      Genera`, `Run migrations against a live database connection.`, `initial  Revision ID: 0001_initial Revises: Create Date: 2026-01-09 00:00:00`, `password reset tokens  Revision ID: 0002_password_reset_tokens Revises: 0001_` (+773 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 108`** (2 nodes): `dependencies.py`, `dependencies.py — Shared FastAPI dependencies for TickerTap.  Re-exports the c`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 109`** (2 nodes): `templates.py`, `Strategy Templates — pre-built system strategies seeded into the database.  Th`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 110`** (2 nodes): `useContextPopup.js`, `useContextPopup()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 111`** (2 nodes): `useKeyboardShortcuts.js`, `useKeyboardShortcuts()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 112`** (2 nodes): `eslint.config.js`, `globals.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 113`** (1 nodes): `Enforce at least 1 uppercase, 1 lowercase, 1 digit, and 1 special character.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 114`** (1 nodes): `Enforce at least 1 uppercase, 1 lowercase, 1 digit, and 1 special character.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 115`** (1 nodes): `Reject non-positive portfolio values.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 116`** (1 nodes): `Allow only known mode values.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 117`** (1 nodes): `Reject state values outside the allowed set.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 118`** (1 nodes): `Reject schedule values outside the allowed set.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 119`** (1 nodes): `Adjust price for slippage.          Entries slip against you (buy higher, sell`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 120`** (1 nodes): `Build a TradeRecord from an open position and its exit.          Args:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 121`** (1 nodes): `Size a position by risking a fixed percentage of the account.          The num`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 122`** (1 nodes): `Size a position by risking a fixed dollar amount.          Args:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 123`** (1 nodes): `Full Kelly criterion — optimal fraction of account to wager.          Formula:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 124`** (1 nodes): `Fractional Kelly — conservative variant.          Multiplies the full Kelly fr`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 125`** (1 nodes): `ATR-based position sizing.          Uses Average True Range to set a volatilit`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 126`** (1 nodes): `Fetch the latest quote for *symbol*.          Args:             symbol: Ticke`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 127`** (1 nodes): `Return the list of bar intervals this provider supports.          Returns:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 128`** (1 nodes): `Return the maximum historical lookback for *interval*.          Args:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 129`** (1 nodes): `Remove duplicate timestamps and sort chronologically.          Args:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 130`** (1 nodes): `Check if NYSE is in regular trading hours.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 131`** (1 nodes): `Return a numeric sort key so intervals order from shortest to longest.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 132`** (1 nodes): `setup.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 133`** (1 nodes): `chartStyles.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 134`** (1 nodes): `shared.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 135`** (1 nodes): `vite.config.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `User` connect `Community 1` to `Community 0`, `Community 3`, `Community 9`, `Community 10`, `Community 22`?**
  _High betweenness centrality (0.058) - this node is a cross-community bridge._
- **Why does `RuleContext` connect `Community 2` to `Community 1`, `Community 4`?**
  _High betweenness centrality (0.040) - this node is a cross-community bridge._
- **Why does `RuleAlertData` connect `Community 2` to `Community 1`, `Community 4`?**
  _High betweenness centrality (0.040) - this node is a cross-community bridge._
- **Are the 187 inferred relationships involving `User` (e.g. with `admin.py — Admin-only routes for TickerTap.  Provides endpoints for user and a` and `Return 200 if the caller is an admin, else 403 from the dependency.      The f`) actually correct?**
  _`User` has 187 INFERRED edges - model-reasoned connections that need verification._
- **Are the 124 inferred relationships involving `PortfolioPosition` (e.g. with `routes/feedback.py — Scoring feedback loop endpoints and background tasks.  Pr` and `Validate the X-Internal-Key header and optional IP restriction.      Raises HT`) actually correct?**
  _`PortfolioPosition` has 124 INFERRED edges - model-reasoned connections that need verification._
- **Are the 117 inferred relationships involving `AuditLog` (e.g. with `admin.py — Admin-only routes for TickerTap.  Provides endpoints for user and a` and `Return 200 if the caller is an admin, else 403 from the dependency.      The f`) actually correct?**
  _`AuditLog` has 117 INFERRED edges - model-reasoned connections that need verification._
- **Are the 112 inferred relationships involving `Portfolio` (e.g. with `DegiroPreviewRow` and `Config`) actually correct?**
  _`Portfolio` has 112 INFERRED edges - model-reasoned connections that need verification._