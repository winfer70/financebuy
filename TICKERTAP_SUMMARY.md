# TickerTap — Full Project Summary

Generated: 2026-09-09
Branch: `feature/insider-monitor-briefings` (not yet merged into `tradingAI0.1`/`main`)
Alembic head: **0041**

> This is the canonical low-level architecture reference for the whole site. Older
> snapshots in this file (table counts, worker lists, pending work) were updated
> 2026-09-09. Prefer `CLAUDE.md` + code if anything still disagrees.

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
| Reverse Proxy | nginx (Docker `web` service; Cloudflare Tunnel terminates TLS in prod) |
| Market Data | yfinance (prices, OHLCV, fundamentals, events) |
| SEC Filings | SEC EDGAR atom/XML feeds (Form 4/144/3/13D/13G/8-K/13F), no API key |
| CUSIP→ticker | OpenFIGI API (`api.openfigi.com`), free, unauthenticated |
| Short interest | FINRA flat-file CDN (`cdn.finra.org`), free, unauthenticated |
| LLM (analysis) | Ollama — model from `OLLAMA_MODEL` / `AI_ARCHITECTURE.md` |
| LLM (news) | Separate Ollama process in `server-b-worker/` |

---

## Docker Services

Two compose files exist: `docker-compose.prod.yml` (generic prod template) and
`docker-compose.labserver.yml` (the **actual live** deployment on labserver,
192.168.0.241, behind a Cloudflare Tunnel with no published host ports). The
service list is the same either way:

| Service | Image | Role |
|---|---|---|
| `db` | `timescale/timescaledb:latest-pg15` | PostgreSQL 15 + TimescaleDB; private network only |
| `redis` | `redis:7-alpine` | Cache + arq job queue; private network only |
| `app` | Built `backend/Dockerfile` | FastAPI on :8000 |
| `alert-worker` | Built `backend/Dockerfile` | arq `arq:alert`: price alerts + two-stage soft stops |
| `trading-worker` | Built `backend/Dockerfile` | arq `arq:trading`: backtests, scanner, portfolio rules, trade eval, DeGiro sync, **all SEC-filing/insider pollers** |
| `paper-worker` | Built `backend/Dockerfile` | arq worker for paper trading sessions |
| `trading-ml` | Built `backend/Dockerfile` | ML strategy worker |
| `news-worker` | `server-b-worker/` | RSS ingest + Ollama scoring → `POST /api/v1/news/internal/news` |
| `web` | Built `web/Dockerfile` (multi-stage: `node:20-alpine` build → `nginx:1.27-alpine`) | Serves the Vite `dist/` build + `nginx.conf` |

**Deploy cmd (when the network mismatch below isn't blocking it):**
```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d
```

---

## Deployment on labserver — bind-mount matrix and gotchas

**Known bug (unfixed):** `docker-compose.labserver.yml` declares network subnet
`10.51.0.0/16`, but the live Docker network is actually `172.29.0.0/16`. This
breaks `docker compose up`/`build` directly for this stack. Until fixed, every
deploy is a manual `docker run --network tickertap_tickertap_net --network-alias
<service>` + file-copy operation. **Never `docker compose down` the whole prod
stack** — there is no clean way back up through compose.

Per-service update mechanism, because bind mounts differ per container:

| Service | Bind mounts? | Update mechanism |
|---|---|---|
| `app`, `alert-worker` | **None** — code is `COPY`'d at image build time | `docker cp` changed files into the running container + `docker restart`. **New Alembic migration files must also be `docker cp`'d in**, or the container crash-loops with `Can't locate revision identified by '<rev>'`. Pre-emptively copy new migrations into every container that runs `alembic upgrade head` on startup, not just `app`. |
| `trading-worker`, `paper-worker` | **Yes** — `./backend/app:/app/app:ro`, `./backend/alembic:/app/alembic:ro` | `scp` changed files to the labserver host checkout at `/home/kamilo/tickerTap/`, then `docker restart <container>`. No rebuild needed. |
| `news-worker` | **None** (only a `news_queue` volume) | `docker cp` of `worker.py`/`sources.py` + `docker restart`. |
| `web` | **None** — full multi-stage image build | See below — requires a real image rebuild, not just a file copy. |

### `web` deploy flow (frontend)

1. `scp` changed frontend files to `/home/kamilo/tickerTap/frontend/...` on labserver.
2. On labserver, from `/home/kamilo/tickerTap`: `docker build -f web/Dockerfile -t tickertap-web:latest .`
3. `docker stop tickertap_web && docker rm tickertap_web` — a plain `docker restart`
   does **not** pick up a newly built image for an already-created container.
4. Recreate with the original flags (confirm via `docker inspect tickertap_web`
   before touching it): `docker run -d --name tickertap_web --network
   tickertap_tickertap_net --network-alias web --restart always tickertap-web:latest`
   (no published ports — Cloudflare Tunnel reaches it over the Docker network alias).

`web/nginx.conf`: `/assets/` gets `Cache-Control: public, immutable` + 1-year
expiry (safe — Vite content-hashes filenames), `/` (SPA fallback) gets
`Cache-Control: no-cache`. Cloudflare's edge does not cache the HTML either
(`cf-cache-status: DYNAMIC` on a direct curl) — a user not seeing a new deploy
is a browser-cache issue, not a server/CDN one; there is no service worker.

`npm install` requires `--legacy-peer-deps` — a documented pre-existing
`eslint-plugin-react-hooks`/`eslint` peer-dependency conflict, unrelated to
any app code.

---

## Architecture — Request Flow

```
Browser → Cloudflare Tunnel → web (nginx) → FastAPI /api/v1/* → SQLAlchemy async → PostgreSQL
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

## Database Schema — ORM models through Alembic 0041

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

Watchlist tickers now have **full gating parity with portfolio positions** in the
insider-monitoring pipeline (see below) — a ticker only on a watchlist, with zero
portfolio positions, gets the same Form 4/144/3/13D/13G/8-K alert coverage as a
held position.

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

### SEC Filings & Insider Monitoring (migrations 0033–0041)
| Model | Table | Key Columns |
|---|---|---|
| InsiderFiling | `insider_filings` | accession, ticker, owner_cik, owner_name, transaction_code, shares, price, shares_after, transaction_date, filed_at |
| Form144Notice | `form144_notices` | accession, ticker, owner_cik, owner_name, broker, shares, approx_sale_value, approx_sale_date, filed_at |
| Form3Statement | `form3_statements` | accession, ticker, owner_cik, owner_name, shares_held (initial position), filed_at |
| BeneficialOwnership | `beneficial_ownership` | accession, person_index (unique w/ accession — a single 13D can name several reporting persons), ticker, filer_cik, filer_name, pct_owned, shares, is_13d, filed_at |
| EightKFiling | `eight_k_filings` | accession, ticker, filer_cik, items (JSONB — item codes + descriptions), filed_at |
| Form13FHolding | `form13f_holdings` | accession, filer_cik, filer_name, cusip, ticker (resolved via OpenFIGI), shares, value_usd, filed_at |
| ShortInterestSnapshot | `short_interest_snapshots` | ticker, settlement_date, short_interest_shares, days_to_cover, pct_change |

See **SEC Filing & Insider Monitoring System** below for how these are populated
and surfaced.

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
| TradeAnalysis | `trade_analyses` | Telegram-bot AI analysis + learning-loop outcome tracking — see `AI_ARCHITECTURE.md` |
| RuleRefinement | `rule_refinements` | shadow-mode weekly rule-change proposals — see `AI_ARCHITECTURE.md` |

### Alerts & Notifications
| Model | Table | Key Columns |
|---|---|---|
| PriceAlert | `price_alerts` | user_id, symbol, condition (above/below/crosses), target_price, is_active |
| Notification | `notifications` | user_id, event_type, title, body, is_read |
| UserWebhook | `user_webhooks` | user_id, url, is_active |
| RuleAlert | `rule_alerts` | user_id, position_id (soft ref), rule_type, severity, state |

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

## Backend Routes — 21 Route Modules (~80+ endpoints)

### Auth (`/api/v1/auth`)
- POST `/register` — email + password, sends verification email (rate: 3/min)
- POST `/login` — returns JWT + sets httpOnly refresh cookie (rate: 5/min)
- POST `/refresh` — silent token refresh via cookie
- POST `/logout`
- POST `/forgot-password` / `/reset-password`
- GET `/me` / PATCH `/profile`
- PATCH `/preferences` — language, display currency, `tutorial_done`
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
- POST `/internal/news` — news ingestion (`X-Internal-Key` / `INTERNAL_NEWS_KEY`)

### Insider / SEC Filings (`/api/v1/insider`)
- GET `/filings` — paginated Form 4 filings (ticker/owner filters)
- GET `/owners/{owner_cik}` — person breakdown: track record, historical Form 4s,
  `pending_144` notices, `short_interest` (when a `ticker` query param is given)
- GET `/filings-all` — **unified** view across all 6 non-Form-4-transaction
  sources (`form144`, `form3`, `13d`, `13g`, `8k`, `13f`); params: `ticker`,
  `source` (comma-separated or `all`), `days`, `sort` (date/ticker/source),
  `order`, `limit`, `offset`. Merges per-source query results and
  sorts/paginates in Python (not a SQL UNION, since the 5 underlying models
  are structurally different) via `AllFilingOut`, a normalized Pydantic shape
  (`source`, `ticker`, `filing_date`, `headline`, `detail`, `person`,
  `owner_cik`, `amount`, `value_usd`, `is_amendment`, `filing_url`).

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

### alert-worker (arq: `app.trading.alert_worker.WorkerSettings`, queue `arq:alert`)
- `evaluate_price_alerts` — active `PriceAlert` rows; in-app notify; also runs `_check_soft_stops`
- `evaluate_one_soft_stop` — immediate check when a newly saved soft stop is already through last price
- Two-stage soft stop: RTH last_price ≤ soft → quiet Telegram+ntfy; after 16:00 ET daily Close still ≤ soft → loud ntfy. Level is **not** auto-cleared
- Re-enqueues: 60s market hours, 300s closed
- Max 50 active price alerts per user

### trading-worker (arq: `app.trading.worker.WorkerSettings`, queue `arq:trading`)
- `run_backtest`, `run_scanner`, `run_portfolio_rules`, `sync_degiro_portfolio`, `evaluate_closed_trade`
- **Insider/SEC-filing pollers** (all cron, all in this worker since they need the same DB session + bind-mount-based deploy path):
  | Job | Module | Cadence |
  |---|---|---|
  | `poll_insider_filings` (Form 4) | `insider_monitor.py` | every 5 min |
  | `poll_form144_filings` | `form144_monitor.py` | :00/:15/:30/:45 |
  | `poll_form3_filings` | `form3_monitor.py` | :05/:20/:35/:50 |
  | `poll_schedule13_filings` (13D+13G) | `schedule13_monitor.py` | :10/:40 |
  | `poll_8k_filings` | `form8k_monitor.py` | every 5 min (offset :02) |
  | `poll_short_interest` | `finra_short_interest.py` | daily 06:00 |
  | `poll_13f_filings` | `form13f_monitor.py` | daily 07:00 |
- Cron: `weekly_meta_analysis` Monday 03:00, `sync_degiro_portfolio` 02:00
- max_jobs: 10 | job_timeout: 300s

### paper-worker (arq: `app.trading.paper_worker.WorkerSettings`, queue `arq:paper`)
- `evaluate_paper_trades` — evaluates active paper trade sessions every ~60s
- Circuit breaker: auto-stops if drawdown > 15% from peak
- Self-re-enqueues after each run

---

## SEC Filing & Insider Monitoring System

**Entry point pattern:** every filing type shares the same EDGAR "current filings"
atom feed (`action=getcurrent&type=<form>&owner=include&count=40&output=atom`),
parsed generically by `parse_atom_accessions()` in `insider_edgar.py`. Only the
per-filing-type document parser differs. This scaffolding (polling cadence, dedup
by accession number, rate-limit courtesy pause between EDGAR requests) is shared
across all 6 filing types — adding a 7th would mean writing one new parser
module, not new plumbing.

### Filing types and what makes each one's parsing different
- **Form 4** (`insider_edgar.py::parse_form4_xml`) — `ownershipDocument` XML,
  `nonDerivativeTransaction` table (buy/sell with transaction code + price).
- **Form 144** (`form144_edgar.py`, via `cik_ticker_map.py`) — a different
  `own:`-namespaced XML schema; the filing has no ticker embedded, only an
  issuer CIK, so CIK→ticker resolution uses SEC's free `company_tickers.json`.
- **Form 3** (`insider_edgar.py::parse_form3_xml`) — same `ownershipDocument`
  family as Form 4, but `nonDerivativeHolding` (a starting position, no
  transaction code/price) instead of `nonDerivativeTransaction`.
- **Schedule 13D/13G** (`schedule13_edgar.py`) — genuinely different XML tag
  names for equivalent concepts between the two (13D wraps per-person data
  under `reportingPersons/reportingPersonInfo` with `issuerCIK`/
  `aggregateAmountOwned`/`percentOfClass`; 13G uses unwrapped sibling
  `coverPageHeaderReportingPersonDetails` blocks with lowercase `issuerCik` and
  no per-person CIK, falling back to the top-level filer CIK). EDGAR's type
  filter needs the exact string `SCHEDULE 13D`/`SCHEDULE 13G` (not `SC 13D`),
  which conveniently prefix-matches `/A` amendments too.
- **Form 8-K** (`form8k_edgar.py`) — the only type parsed **from the atom feed
  alone**; item codes ("Item 5.02: ...") are already in the `<summary>` text,
  no per-filing document fetch needed. Volume is dozens per 5-minute tick
  across every US issuer, so `form8k_monitor.py` filters to tracked tickers
  (open positions + watchlist + known insider filers) **before** storing
  anything, reusing `finra_short_interest.py`'s `_wanted_tickers()` query.
- **Form 13F-HR** (`form13f_edgar.py`, via `cusip_ticker_map.py`) — holdings
  live in a separate `infotable.xml` file from the filing's `primary_doc.xml`
  (a dedicated selector picks the "infotable" file, since a generic
  "first .xml" picker grabs the wrong one). The `<figi>` field present in
  modern filings is share-class-level, not composite/exchange-level, so CUSIP
  is the reliable resolution key via OpenFIGI (batched up to 100/request,
  prefers `exchCode == "US"`). Positioning data, not a timely signal — filed
  up to 45 days after quarter-end.
- **FINRA short interest** (`finra_short_interest.py`) — not an EDGAR filing at
  all. The documented Query API (`api.finra.org`) requires paid/registered
  credentials for current data (frozen at 2020-04-15 on the free tier); the
  real free path is the flat-file CDN
  `cdn.finra.org/equity/otcmarket/biweekly/shrt{YYYYMMDD}.csv` (pipe-delimited
  despite the `.csv` extension). No predictable "latest" URL — a HEAD-request
  backward scan from today finds the most recent published date, cached
  per-day.

### Watchlist/portfolio gating parity
`BookSnapshot.watchlist_tickers` (a `set`, kept separate from `held_tickers` so
sector-exposure/stop/phase math stays scoped to real positions) is OR'd into
every "is this ticker tracked" gate check in `insider_gate.py` and
`insider_monitor.py`. `book_loader.py` (extracted from `insider_monitor.py` to
avoid a circular import once `form144_monitor.py` also needed it) unions
portfolio-holder user IDs with watchlist-holder user IDs, so a user with a
ticker **only** on a watchlist and zero positions still gets a `BookSnapshot`
and full alert coverage — previously impossible.

### Form 144 planned-sell alert
Promoted from passive context (a note appended to Form 4 sell alerts) to a
standalone alert: when a new Form 144 notice is stored, `form144_monitor.py`
loads all books, finds every user holding or watching that ticker, and fires
`notify_soft_stop(event_type="planned_sell", ...)` (Telegram + ntfy + in-app)
per user — independent of whether a matching Form 4 sale ever follows.

### Advice enrichment
`insider_monitor.py`'s Telegram/ntfy advice text (`briefing_advice.py`,
`market_context.py`) is enriched with data from every filing type when
relevant to a Form 4 buy/sell: a matching Form 144 ("pre-announced... not a
surprise"), the person's initial Form 3 stake ("this sale is X% of their
initial N-share position"), 13D/13G market color ("activist stake filed by
X — Y% stake" vs. softer 13G phrasing), 8-K material events on the same
ticker, 13F "which funds hold this" positioning notes, and FINRA short
interest squeeze/crowding warnings (high days-to-cover, fast-rising short
interest). Also includes Phase Framework position-sizing notes and an
analyst-target premium check.

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

### Phase 4 — Auto Scoring (3 of 7 factors in `_score_candidate`)
Implemented in `backend/app/trading/scanner_worker.py` (there is **no** `volume_flow_scanner.py` in this repo):
- Auto (0–5 each, `auto_score_max` 15 or 10 if no analyst data): revenue momentum, volume confirm, analyst consensus
- Stored as `null`: thesis_clarity, risk_reward, sector_tailwind, entry_zone_quality
- **≥25/35 / half-size bands are UI copy only** (`ResearchPage.jsx`). No backend gate, no persistence of the four manual scores.

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

## Frontend — 27 Pages

### Authenticated Pages
| Page | Key Features |
|---|---|
| **DashboardPage** | Portfolio selector, performance chart (1W/1M/3M/YTD/1Y/ALL), heatmap, KPI cards, asset ribbon, concentration chips, QuickSell drawer, Top Gainers/Losers panels, allocation donut |
| **PortfolioManagerPage** | Multiple portfolios, 4 asset types (stocks/crypto/ETFs/physical), positions table, stop-loss + profit-taking tracking, CHG column ($/%), Trade History tab, cash balance modal, portfolio score, CSV import/export, analyst targets in modify modal |
| **ChartsPage** | Symbol search, candlestick/line/bar charts, 14 drawing tools, intervals 1m–1mo, SMA overlays, breakout detection, event indicators (E/D/S), purchase point markers, chart templates, ruler tool, SMA PROJ (OLS trend fit projected forward) |
| **WatchlistPage** | Named watchlists, live prices, day range, performance since added, notes, sortable columns, stale data banner (>5 min), buy from watchlist |
| **AlertsPage** | Create/edit/delete price alerts, ACTIVE/TRIGGERED/ALL tabs, live price enrichment |
| **ResearchPage** | SECTORS heat-map, SCREENER (~100 tickers, filters), VOLUME FLOW scanner tab |
| **NewsPage** | LLM-scored articles (-5..+5), sentiment badges, per-ticker impact, source badges, pagination (25/50/75/100), portfolio/watchlist/sentiment filters |
| **InsiderPage** | FORM 4 / ALL FILINGS tab switcher; FORM 4 tab shows Form 4 buy/sell transactions; ALL FILINGS tab unifies Form 144/3/13D/13G/8-K/13F into one sortable, source-filterable, paginated table with source-colored pills; clicking any owner-linked row opens the person breakdown panel (track record, SHORT INTEREST box, PENDING FORM 144 box) |
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

### First-run
`OnboardingTutorial.jsx` — 8-step modal tour, shown once per account (gated on
`preferences.tutorial_done`, persisted via `PATCH /auth/preferences`).

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
- TLS terminates at Cloudflare edge (Tunnel), not at the app's own nginx
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
- **EDGAR polling**: reuse `insider_edgar.py`'s atom-feed + accession-dedup scaffolding for any new filing type; only the per-filing parser differs
- **Normalizing heterogeneous models for one API response**: build a single Pydantic shape (see `AllFilingOut`) and merge/sort/paginate in Python rather than attempting a SQL UNION across structurally different tables
- **Avoiding circular imports between sibling trading modules**: extract shared loaders (e.g. `book_loader.py`) into their own module rather than importing across two modules that already import from each other

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
| `OLLAMA_URL` | No | Analysis LLM base URL |
| `OLLAMA_MODEL` | No | Analysis model tag (see `AI_ARCHITECTURE.md`) |
| `INTERNAL_NEWS_KEY` | News ingest | Shared secret for `POST /api/v1/news/internal/news` |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Soft-stop + bot | Gitignored `.env` only |
| `TELEGRAM_BOT_USERNAME` | Register page bot link | **Currently unset on labserver** — link is inert until set |
| `NTFY_URL` / `NTFY_TOPIC` / `NTFY_TOKEN` | Soft-stop backup | Gitignored `.env` only |
| `VITE_API_URL` | No | Frontend API base (build-time) |
| `SEC_USER_AGENT` | EDGAR polling | Required by SEC's fair-use policy for all EDGAR requests |

No new env vars were needed for the SEC-filing expansion — OpenFIGI and the
FINRA CDN are both free/unauthenticated.

---

## Alembic Migration History (0001–0041)

See `backend/alembic/versions/`. Notable later revisions:
- **0024** `rule_alerts`
- **0029** `hard_stop_loss` / `soft_stop_loss`
- **0030** `trade_analyses`
- **0031** `rule_refinements`
- **0032** soft-stop stage dates + delivery JSON
- **0033** `insider_filings` (Form 4)
- **0034** `insider_shares_after`
- **0035** `telegram_invites`
- **0036** `form144_notices`
- **0037** `short_interest_snapshots`
- **0038** `form3_statements`
- **0039** `beneficial_ownership` (13D/13G)
- **0040** `eight_k_filings`
- **0041** `form13f_holdings` (current head)

---

## Pending / In-Progress Work

- **Rate limits on trading endpoints**: some `@limiter.limit` decorators remain commented in `trading.py` — deferred intentionally
- **Scanner rubric /35**: four subjective factors are still a manual checklist (see Phase 4)
- **nginx Docker DNS**: recreating `app` without reloading `web` can 502 until `nginx -s reload`. Do not `compose down` the whole prod stack
- Portfolio **rule engine is live** (`run_portfolio_rules` on `arq:trading`, `rule_alerts` table) — not a future integration item
- **`docker-compose.labserver.yml` network subnet mismatch** unfixed (`10.51.0.0/16` declared vs `172.29.0.0/16` actual) — every deploy is manual until this is fixed
- **`TELEGRAM_BOT_USERNAME`** unset on labserver — register page's bot link is inert
- **Form N-PORT** (monthly fund holdings) remains unbuilt — see `FREE_FILINGS_RESEARCH.md`; lowest priority since 13F now covers "who holds this" with far less engineering cost
- **`feature/insider-monitor-briefings`** not yet pushed/merged into `tradingAI0.1`/`main`, despite being fully live in prod

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

SEC EDGAR, OpenFIGI, and FINRA CDN calls all go through the existing `httpx`
dependency — no new HTTP client library was added for the filings expansion.
