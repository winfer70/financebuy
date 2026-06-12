# TickerTap — Full Project Summary

Generated: 2026-05-13  
Branch: `tradingAI0.1`  
Root: `/home/REDACTED420/projects/finance/tickerTap`

---

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI 0.95.2, Python 3.11 |
| ORM | SQLAlchemy 1.4.49 async (asyncpg driver) |
| Validation | Pydantic v1 (1.10.11) — `orm_mode=True`, `condecimal` |
| Auth | JWT (python-jose) + Argon2id hashing + httpOnly refresh cookie |
| Database | TimescaleDB (PostgreSQL 15) |
| Cache / Queue | Redis 7 |
| Background Jobs | arq (async Redis queue) |
| Frontend | React 19, Vite 7.x |
| Reverse Proxy | Host nginx (serves `frontend/dist` directly, proxies `/api/v1/` to :8000) |
| Market Data | yfinance (prices, OHLCV, fundamentals, events) |
| LLM (Guide) | Ollama (llama3:8b-instruct-q4_K_M) on REDACTED_HOST/Server B |
| LLM (News) | Ollama news-scoring worker on REDACTED_HOST/Server B |

---

## Docker Services (prod: `docker-compose.prod.yml`)

| Service | Image | Role |
|---|---|---|
| `db` | `timescale/timescaledb:latest-pg15` | PostgreSQL 15 + TimescaleDB; private network only |
| `redis` | `redis:7-alpine` | Cache + arq job queue; private network only |
| `app` | Built `backend/Dockerfile` | FastAPI on :8000; 0.0.0.0 bind (LAN access for Server B) |
| `alert-worker` | Built `backend/Dockerfile` | arq worker for price alerts |
| `trading-worker` | Built `backend/Dockerfile` | arq worker for backtests + volume flow scanner |
| `paper-worker` | Built `backend/Dockerfile` | arq worker for paper trading sessions |
| `trading-ml` | Built `backend/Dockerfile` | ML strategy worker |

**Deploy cmd:**
```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d
```

**CRITICAL:** App container has NO bind mounts — code is COPY'd at build time.  
New files require: `docker compose --env-file .env.prod -f docker-compose.prod.yml build --no-cache <service>` then `--force-recreate`.

---

## Architecture — Request Flow

```
Browser → nginx (host, :443) → FastAPI /api/v1/* → SQLAlchemy async → PostgreSQL
                                                  → Redis (arq jobs)
                              ← static files from frontend/dist
```

### Middleware stack (order matters):
1. SlowAPI rate limiter
2. CORSMiddleware
3. SecurityHeadersMiddleware (HSTS, CSP, X-Frame-Options: DENY)
4. RequestBodySizeMiddleware (10 MB max)
5. RequestLoggingMiddleware (redacts passwords/tokens)
6. CorrelationIDMiddleware (UUID per request)

---

## Database Schema — 34 ORM Models (22 migrations)

### Core Auth & Users
| Model | Table | Key Columns |
|---|---|---|
| User | `users` | user_id, email, password_hash, is_active, preferences_json |
| Account | `accounts` | account_id, user_id, balance, status |
| RefreshToken | `refresh_tokens` | token, user_id, expires_at |
| PasswordResetToken | `password_reset_tokens` | token, user_id, expires_at |
| EmailVerificationToken | `email_verification_tokens` | token, user_id, token_type |

### Trading & Orders
| Model | Table | Key Columns |
|---|---|---|
| Security | `securities` | symbol, name, security_type |
| Holding | `holdings` | account_id, security_id, quantity |
| Order | `orders` | account_id, security_id, quantity, status, order_type |
| Transaction | `transactions` | account_id, amount, type, status |

### Portfolio Manager
| Model | Table | Key Columns |
|---|---|---|
| Portfolio | `portfolios` | user_id, name, cash_balance |
| PortfolioPosition | `portfolio_positions` | portfolio_id, ticker, quantity, purchase_price, purchase_date, stop_loss, profit_taking, group_tag, asset_type, is_excluded |
| PortfolioTrade | `portfolio_trades` | portfolio_id, ticker, trade_type, quantity, price, cost_basis |

### Watchlists
| Model | Table | Key Columns |
|---|---|---|
| Watchlist | `watchlists` | user_id, name |
| WatchlistItem | `watchlist_items` | watchlist_id, symbol, asset_type, notes, price_when_added |

### Charts
| Model | Table | Key Columns |
|---|---|---|
| ChartTemplate | `chart_templates` | user_id, name, symbol, drawings_json, overlays_json |

### News & Scoring
| Model | Table | Key Columns |
|---|---|---|
| NewsArticle | `news_articles` | url, title, source, general_score (-5..+5), published_at |
| NewsArticleTicker | `news_article_tickers` | article_id, ticker, score, impact_summary |
| ScoreOutcome | `score_outcomes` | article_id, ticker, accuracy_grade |
| ScoringRule | `scoring_rules` | rule_version, rules_text, is_active |

### Trading AI
| Model | Table | Key Columns |
|---|---|---|
| Strategy | `strategies` | user_id, name, strategy_type (builtin/pinescript/composed/ml), definition_json, is_public |
| StrategyVersion | `strategy_versions` | strategy_id, version_number, definition_json |
| BacktestResult | `backtest_results` | user_id, strategy_id, symbol, interval, status, results_json, metrics_json, benchmark_json |
| TradingSignal | `trading_signals` | strategy_id, user_id, symbol, signal_type, direction |
| StrategyRating | `strategy_ratings` | strategy_id, user_id, stars |
| StrategyUsage | `strategy_usage` | strategy_id, user_id |
| PaperTrade | `paper_trades` | user_id, strategy_id, symbol, status, equity, initial_capital |
| PaperTradePosition | `paper_trade_positions` | paper_trade_id, side, entry_price, quantity |
| PaperTradeEquitySnapshot | `paper_trade_equity_snapshots` | paper_trade_id, equity, recorded_at |

### Alerts & Notifications
| Model | Table | Key Columns |
|---|---|---|
| PriceAlert | `price_alerts` | user_id, symbol, condition (above/below/crosses), target_price, is_active |
| Notification | `notifications` | user_id, event_type, title, body, is_read |
| UserWebhook | `user_webhooks` | user_id, url, is_active |

### Admin & Reporting
| Model | Table | Key Columns |
|---|---|---|
| AuditLog | `audit_log` | user_id, action, table_name, record_id, old_values, new_values |
| UserReport | `user_reports` | user_id (nullable), reporter_email, report_type, subject, body, status |

### Volume Flow Scanner
| Model | Table | Key Columns |
|---|---|---|
| ScanResult | `scan_results` | user_id, status (pending/running/complete/error), parameters_json, results_json, phase_reached |

---

## Backend Routes — 20 Route Modules (~70+ endpoints)

### Auth (`/api/v1/auth`)
- POST `/register` — email + password, sends verification email (rate: 3/min)
- POST `/login` — returns JWT + sets httpOnly refresh cookie (rate: 5/min)
- POST `/refresh` — silent token refresh via cookie
- POST `/logout`
- POST `/forgot-password` / `/reset-password`
- GET `/me` / PATCH `/profile`
- PATCH `/preferences` — language, display currency
- POST `/verify-email` / `/resend-verification`
- POST `/change-email` / `/confirm-email-change`
- POST `/deactivate` / `/request-reactivation` / `/reactivate`
- POST `/delete-account` (soft 30-day or permanent) / `/cancel-deletion`

### Accounts (`/api/v1/accounts`)
- POST `/` — create brokerage account
- GET `/me` — list my accounts

### Transactions (`/api/v1/transactions`)
- POST `/create` — deposit / withdrawal
- GET `/?account_id=` — transaction history

### Portfolio (legacy, `/api/v1/portfolio`)
- GET `/positions` / `/summary`

### Portfolio Manager (`/api/v1/portfolio-manager`)
- GET/POST `/portfolios`
- DELETE `/portfolios/{id}`
- GET/POST `/portfolios/{id}/positions`
- PATCH `/positions/{id}` — modify position (qty, stop, profit target, group tag)
- POST `/positions/{id}/sell`
- DELETE `/positions/{id}`
- POST `/portfolios/{id}/import` — bulk import positions
- GET `/portfolios/{id}/trades` — trade history
- DELETE `/trades/{id}` — delete trade record
- GET `/portfolios/{id}/score` — portfolio score + concentration analysis
- POST `/portfolios/{id}/cash` — adjust cash balance
- GET `/portfolios/{id}/analyst-targets` — analyst price targets per position

### Holdings (`/api/v1/holdings`)
- GET `/?account_id=` — paginated holdings list

### Orders (`/api/v1/orders`)
- POST `/` — place order (market/limit, buy/sell)
- GET `/?account_id=` — order blotter
- POST `/{id}/cancel`
- POST `/cancel-all`

### Market Data (`/api/v1/market`)
- GET `/quote/{symbol}` — live price quote (TTL: 3s open / 5m closed)
- GET `/quotes/bulk` — batch quotes
- GET `/ohlcv/{symbol}` — daily OHLCV (years)
- GET `/ohlcv_interval/{symbol}` — intraday/interval OHLCV
- GET `/symbols` — symbol search
- GET `/sectors` — 11 GICS sector ETF performance (TTL: 5m)
- GET `/screener` — stock screener with filters (~100 tickers)
- GET `/fundamentals/{symbol}` — full fundamentals (TTL: 1h)
- GET `/events/{symbol}` — earnings/dividends/splits
- GET `/search` — symbol autocomplete

### Watchlists (`/api/v1/watchlists`)
- GET/POST `/` — list / create watchlist
- GET/PATCH/DELETE `/{id}` — get / rename / delete
- GET/POST `/{id}/items` — list items / add symbol
- PATCH/DELETE `/{id}/items/{item_id}` — edit notes / remove
- POST `/{id}/items/{item_id}/buy` — buy into portfolio from watchlist

### Alerts (`/api/v1/alerts`)
- GET/POST `/` — list / create price alert (max 50 active per user)
- PATCH/DELETE `/{id}` — update / delete alert
- Alert evaluation: every 60s market hours, 5m closed (alert_worker arq)

### News (`/api/v1/news`)
- GET `/feed` — paginated feed; filters: portfolio, sentiment, ticker, source; 25/50/75/100 per page
- GET `/tickers/{ticker}` — articles by ticker
- POST `/internal/news` — news ingestion (X-Internal-Key auth)

### Charts (`/api/v1/chart-templates`)
- GET/POST `/` — list / create template
- GET/PATCH/DELETE `/{id}`

### Trading AI (`/api/v1/trading`)
- GET/POST `/strategies` — list / create strategy
- GET/PATCH/DELETE `/strategies/{id}`
- POST `/strategies/{id}/versions` — save version
- GET `/strategies/{id}/versions` — list versions
- POST `/strategies/{id}/revert/{version_id}` — revert to version
- POST `/backtests` — queue backtest (arq job)
- GET `/backtests/{id}` — poll backtest result
- GET `/backtests/latest` — latest backtest for user
- POST `/validate-pinescript` — AST-validate PineScript
- POST `/transpile-pinescript` — transpile PineScript → signals (LLM fallback)
- GET `/regime/{symbol}` — market regime detection
- POST `/strategies/{id}/publish` — publish to marketplace
- POST `/strategies/{id}/unpublish`
- POST `/strategies/{id}/clone` — clone public strategy
- POST `/strategies/{id}/rate` — star rating
- GET `/marketplace` — public strategy list with filters
- GET `/signals/{id}` — trading signals for strategy
- GET `/notifications` — trading notifications
- GET/POST `/webhooks` — user webhook management
- POST `/paper-trades` — start paper trading session
- GET `/paper-trades/{id}` — get paper trade status
- POST `/paper-trades/{id}/pause` / `/resume` / `/stop`
- POST `/exit-analysis` — ATR/Fibonacci/Bollinger exit point analysis
- GET `/batch-backtest` — batch backtest across watchlist symbols
- POST `/strategies/compare` — side-by-side strategy comparison

### Scanner (`/api/v1/scanner`)
- POST `/run` — queue volume flow scan (arq)
- GET `/latest` — latest scan result for user
- GET `/{result_id}` — poll specific scan

### Admin (`/api/v1/admin`) — admin-only
- GET `/check` / `/users` / `/audit-logs`
- POST `/users/{id}/lock` / `/unlock`
- POST `/accounts/{id}/lock` / `/unlock`

### Reports (`/api/v1/reports`)
- POST `/` — submit bug/suggestion (rate: 5/min; no auth for activation_bug type)
- GET/PATCH/DELETE `/` — admin report management

### Guide (`/api/v1/guide`)
- POST `/ask` — AI Q&A proxied to Ollama with full TickerTap context (60s timeout)

### Import (`/api/v1/import`)
- POST `/degiro/csv` — import DeGiro CSV statement

### Unversioned
- GET `/health` — deep health check (DB + Redis)
- GET `/metrics` — worker heartbeat status (admin)

---

## Background Workers

### trading-worker (arq: `app.trading.worker.WorkerSettings`)
- `run_backtest` — full backtest pipeline: load strategy → fetch OHLCV → run engine → compute metrics (Sharpe, Sortino, drawdown, win rate, profit factor) → benchmark vs buy-and-hold → store results + audit log
- `run_scanner` — 5-phase volume flow scan (see Scanner section below)
- max_jobs: 10 | job_timeout: 300s

### paper-worker (arq: `app.trading.paper_worker.WorkerSettings`)
- `run_paper_evaluation` — evaluates active paper trade sessions every ~60s
- Fetches live price, runs strategy signal function, manages position entry/exit
- Circuit breaker: auto-stops if drawdown > 15% from peak
- Self-re-enqueues after each run

### alert-worker (arq: `app.trading.alert_worker.WorkerSettings`)
- Polls all active `PriceAlert` rows
- Fetches prices via yfinance
- Evaluates: above / below / crosses conditions
- Fires in-app `Notification` on trigger; deactivates alert
- Re-enqueues: 60s market hours, 300s closed
- Max 50 active alerts per user

---

## Volume Flow Scanner (5-Phase System)

**Entry point:** `POST /api/v1/scanner/run` → arq job → `scanner_worker.run_scanner`

### Phase 1 — Sector ETF Volume Surge
11 GICS sector ETFs (XLK, XLC, XLY, XLF, XLV, XLE, XLI, XLB, XLRE, XLU, XLP).  
Filter: volume ≥ 2× 50-day avg AND price up.

### Phase 2 — Industry Drill-Down
For each active sector, check industry ETFs (e.g. Technology → SOXX/SMH/IGV/CLOU/HACK).  
Same 2× volume + up-day filter.

### Phase 3 — Stock Screening
Per active industry: check representative stocks (e.g. Semiconductors → NVDA, AMD, AVGO…).  
Auto-disqualifiers: price > analyst target × 1.05 | rev growth < 15% YoY | earnings within 5 days | market cap < $500M.

### Phase 4 — Auto Scoring (3/7 factors)
- Revenue momentum: 1-5 based on YoY growth tiers (≥40%=5, ≥25%=4, ≥15%=3…)
- Volume confirm: 1-5 (≥4×=5, ≥3×=4, ≥2.5×=3…)
- Analyst consensus: 1-5 (strong buy=5, buy=4, hold=3…)
- Manual factors (not auto-computed): thesis clarity, risk/reward, sector tailwind, entry zone quality
- Threshold: ≥25/35 proceed full size; 18-24 half size; <18 skip

### Phase 5 — Position Sizing
- Risk model: 1.5% of portfolio per trade
- Stop distance: entry − stop_loss
- Shares = risk_usd / stop_dist
- Max position: 8% of portfolio (hard cap)

**Results stored in:** `scan_results.results_json` → `{active_sectors, active_industries, candidates, phase1_count, phase2_count, phase3_count, scan_duration_s}`

**Frontend:** VOLUME FLOW tab in ResearchPage — shows phase progress tracker, sector chips, industry chips, candidates table with scores + position sizing. Polls every 3s until complete.

---

## Trading AI Features

### Built-in Strategies (10)
SMA Crossover, EMA Crossover, RSI Mean Reversion, MACD Crossover, Bollinger Squeeze, Stochastic, ADX Trend, VWAP Bounce, Breakout, Ichimoku Cloud

### Strategy Types
- **builtin** — 10 pre-built strategies
- **pinescript** — Custom PineScript; AST-validated, LLM fallback transpilation
- **composed** — Visual boolean composition of indicators (Strategy Composer)
- **ml** / **learned** — ML-based strategies

### Backtest Engine
Full OHLCV backtest: equity curve, per-trade log (entry/exit, direction, P&L, bars held), Sharpe, Sortino, max drawdown, win rate, profit factor, overfit warning.  
Benchmark: buy-and-hold comparison.

### Paper Trading
- Virtual capital (default $10k), live strategy evaluation every 60s
- Position tracking, equity curve snapshots
- Circuit breaker: auto-stop at 15% drawdown from peak
- States: running / paused / stopped

### Marketplace
Browse/search/filter public strategies. Clone, rate (1-5 stars), view stats (clone count, avg rating, backtest count).

### Batch Backtest
Run one strategy across all watchlist symbols (up to 20) simultaneously.

### Strategy Comparison
Side-by-side backtest of 2-3 strategies on same symbol/period. Overlaid equity curves + metrics table.

---

## Frontend — 26 Pages

### Authenticated Pages
| Page | Key Features |
|---|---|
| **DashboardPage** | Portfolio selector, performance chart (1W/1M/3M/YTD/1Y/ALL), heatmap, KPI cards, asset ribbon, concentration chips, QuickSell drawer, Top Gainers/Losers panels, allocation donut |
| **PortfolioManagerPage** | Multiple portfolios, 4 asset types (stocks/crypto/ETFs/physical), positions table, stop-loss + profit-taking tracking, CHG column ($/%), Trade History tab, cash balance modal, portfolio score, CSV import/export, analyst targets in modify modal |
| **ChartsPage** | Symbol search, candlestick/line/bar charts, 14 drawing tools, intervals 1m–1mo, SMA overlays, breakout detection, event indicators (E/D/S), purchase point markers, chart templates, ruler tool |
| **WatchlistPage** | Named watchlists, live prices, day range, performance since added, notes, sortable columns, stale data banner (>5 min), buy from watchlist |
| **AlertsPage** | Create/edit/delete price alerts, ACTIVE/TRIGGERED/ALL tabs, live price enrichment |
| **ResearchPage** | SECTORS heat-map, SCREENER (~100 tickers, filters), VOLUME FLOW scanner tab |
| **NewsPage** | LLM-scored articles (-5..+5), sentiment badges, per-ticker impact, source badges, pagination (25/50/75/100), portfolio/watchlist/sentiment filters |
| **TradingPage** | Strategy picker, backtest config (symbol, interval, dates, commission, slippage), PAPER tab for paper trading, strategy comparison, batch backtest, marketplace |
| **OrdersPage** | Order blotter, cancel individual/all, place order modal |
| **TransactionsPage** | Deposit/withdrawal history, CSV export |
| **SettingsPage** | Profile edit, display currency (8), language (9), deactivate/delete account |
| **MarketplacePage** | Browse/search/clone public strategies |
| **ImportPage** | CSV import for 8 brokers (Robinhood, IBKR, E*TRADE, TD Ameritrade, Coinbase, Binance, Schwab, Fidelity) |
| **ExitPointsPage** | ATR stops (1.5×/2×/3×), take-profit targets (1:2/1:3), Fibonacci, Bollinger, SMA 50/200, EMA 21 |
| **UserGuidePage** | FEATURES + FAQ + AI assistant tabs |
| **LearningPage** | 20 topics across Beginner/Intermediate/Advanced, progress tracking |
| **AdminPage** | USERS / REPORTS / AUDIT LOG tabs (admin-only) |
| **FeedbackPage** | Bug reports + feature suggestions |

### Auth Pages
LoginPage, RegisterPage, ForgotPasswordPage, ResetPasswordPage, VerifyEmailPage, DeactivatedAccountPage, TokenActionPage

### Shared Components (24)
Common: SkeletonRow, ApiError, ToastContainer, Clock, Footer, TickerStrip, Pagination, FilterBar, StatBlock, NotificationBell, AlertModal, AssetDetailPanel, StaleDataBanner, KeyboardShortcutsModal, QuickSellDrawer  
Charts: OHLCVChart, DrawingTools, chartStyles  
Trading: PineScriptEditor, ParameterEditor, CompositionEditor, StrategyComparison, PaperTradingPanel

---

## UI / Design System

- Bloomberg terminal aesthetic — dark theme, IBM Plex Mono
- Inline style objects from `frontend/src/styles/globals.js` — no CSS files
- Collapsible sidebar (icons-only mode, persisted)
- Keyboard shortcuts: `?` opens modal; `g+d/w/p/t/n/c` navigate pages (1500ms window)
- Full browser back/forward navigation (pushState/popstate)
- Breadcrumb in topbar with translated page names
- Ticker strip: live scrolling quotes, 3s open / 5m closed polling
- 5-minute inactivity auto-logout
- Silent JWT refresh (httpOnly cookie)
- Display currency with real-time ECB rate conversion (USD/EUR/GBP/PLN/CHF/JPY/CAD/AUD)
- Language: English/Polish/German/Chinese/Spanish/Portuguese/French/Japanese/Italian

---

## Security

- Argon2id password hashing
- JWT access tokens + httpOnly refresh cookie
- HSTS + Content Security Policy headers
- X-Frame-Options: DENY
- Redis-backed rate limiting (SlowAPI)
- Account lockout: 10 failed attempts → 15-min cooldown
- Email verification required before first login
- Strong password validation (upper + lower + digit + special, min 8)
- TLS 1.3 via nginx (Let's Encrypt)
- Soft delete: 30-day grace period before permanent deletion
- Admin role via `ADMIN_EMAILS` env var

---

## Key Conventions

- **Async DB everywhere**: `AsyncSession` via `get_db()`. Multi-step ops wrap in `async with db.begin()`
- **Financial precision**: `decimal.Decimal` in Python, `condecimal` in Pydantic, `Numeric(18,2)` in models. Never `float` for money
- **Auth dependencies**: `Depends(get_current_user)` or `Depends(get_current_admin)`. `get_current_user` returns User ORM — access `.user_id`
- **Market data caching**: 3s during market hours, 5m when closed
- **Strategy slugs**: stored in `definition_json.strategy_slug` (no dedicated slug column)
- **Pydantic v1**: `orm_mode = True` (not `model_config`), `condecimal` (not v2 style)
- **Two-stage Dockerfile**: wheels pre-built in builder stage, installed from `/wheels` in runtime
- **yfinance in async**: always `asyncio.get_event_loop().run_in_executor(None, lambda: ...)`

---

## Environment Variables

| Var | Required | Description |
|---|---|---|
| `JWT_SECRET` | Yes (≥32 chars) | App refuses to start with placeholder |
| `DATABASE_URL` | Yes | async: `postgresql+asyncpg://...` |
| `REDIS_URL` | No | Default: `redis://redis:6379/0` |
| `ALLOWED_ORIGINS` | No | CORS whitelist |
| `ADMIN_EMAILS` | No | Comma-separated admin email list |
| `SMTP_*` | No | Email sending (verification, reset) |
| `APP_URL` | No | Base URL for email links |
| `LOG_LEVEL` | No | DEBUG rejected in production |
| `OLLAMA_URL` | No | Default: `http://localhost:11434` |
| `OLLAMA_MODEL` | No | Default: `llama3:8b-instruct-q4_K_M` |
| `VITE_API_URL` | No | Frontend API base (build-time) |

---

## Alembic Migration History (22 migrations)

```
0001 initial — users, accounts, transactions, holdings, orders, securities
0002 password_reset_tokens
0003 integrity_fixes
0004 refresh_tokens
0005 portfolio_manager — portfolios, portfolio_positions
0006 asset_types — add asset_type to positions
0007 stop_loss — add stop_loss to positions
0008 chart_templates
0009 news_articles — news_articles, news_article_tickers
0010 score_feedback — score_outcomes, scoring_rules
0011 user_preferences — add preferences_json to users
0012 reports_email_verify_account_mgmt — user_reports, email_verification_tokens
0013 watchlists_account_lockout — watchlists, watchlist_items
0014 profit_taking — add profit_taking to positions
0015 trading_strategies — strategies, strategy_versions, backtest_results, trading_signals, strategy_ratings, strategy_usage
0016 intraday_bars
0017 notifications — notifications, user_webhooks, price_alerts
0018 social_strategies — marketplace + paper trading tables
0019 paper_trading — paper_trades, paper_trade_positions, paper_trade_equity_snapshots
0020 portfolio_cash_tracking — add cash_balance to portfolios
0021 portfolio_trade_cost_basis — add cost_basis to portfolio_trades
0022 add_scan_results — scan_results table
```

---

## Pending / In-Progress Work

- **Rate limits on trading endpoints**: 19 `@limiter.limit` decorators commented out in `trading.py` — deferred intentionally
- **Volume Flow Scanner enhancements**: configurable volume threshold, portfolio rules analyzer, watchlist add from scanner results (in INNOVATE/PLAN phase)
- **PortfolioTracker integration**: portfolio_manager.py rules engine (stop proximity, house money, analyst target, time stop) to be adapted as arq job reading TickerTap portfolio positions

---

## Dependencies (requirements.txt)

```
fastapi==0.95.2          uvicorn[standard]==0.22.0   SQLAlchemy==1.4.49
asyncpg==0.27.0          pydantic[email]==1.10.11     python-dotenv==1.0.0
argon2-cffi==21.3.0      alembic>=1.10                pytest==7.4.0
httpx==0.24.1            python-jose==3.3.0            psycopg2-binary>=2.9
aiosmtplib>=2.0          yfinance>=0.2.36              pytz>=2023.3
slowapi>=0.1.9           redis>=4.0                    arq>=0.25
numpy>=1.24              pandas>=2.0                   lark>=1.1
pytest-cov>=4.1          pytest-asyncio>=0.23          structlog>=23.1
python-multipart>=0.0.6
```
