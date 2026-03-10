# PLAN: Trading AI — Algorithmic Trading Engine with ML & PineScript Support

**Date:** 2026-03-10
**Project:** TickerTap
**Status:** Awaiting approval

---

## Overview

Add a full algorithmic trading engine to TickerTap across six phases. Users select a stock, pick a strategy from a dropdown (populated from DB-stored algorithms the AI has learned), and the system generates forward-looking entry/exit/stop-loss signals overlaid on the chart, backed by rigorous backtesting with historical data.

---

## Architecture Decisions (Locked In)

| # | Decision | Choice |
|---|---|---|
| 1 | Execution engine | **Hybrid** — API for CRUD/delivery, arq worker for compute |
| 2 | Task queue | **arq** — async Redis queue (lightweight, Redis-native) |
| 3 | Signal delivery | **Hybrid** — polling for backtests, SSE for live signals (Phase 6) |
| 4 | PineScript | **Hybrid** — lark grammar for core subset, LLM fallback + AST validation |
| 5 | ML containers | **Two containers** — Ollama (LLM) + quant ML (PyTorch/sklearn), same host initially |
| 6 | Chart integration | **Shared chart component** — refactor out of ChartsPage + DashboardPage |
| 7 | Strategy storage | **Hybrid** — relational metadata + JSONB definition |
| 8 | Data source abstraction | **Adapter + normalizer pipeline** |
| 9 | Intraday archiver | **TimescaleDB extension** on existing Postgres |
| 10 | Notifications | **Unified notification service** with user preference routing |
| 11 | Strategy discovery | **Curated marketplace** with categories, ratings, author profiles |
| 12 | Paper trading | **Periodic evaluation** initially, event-driven upgrade later |
| 13 | Security sandbox | **Hybrid** — lark = safe by construction, LLM path = AST + container |
| 14 | Backtest replay | **Frontend-only** — full payload, client-side stepping |
| 15 | Strategy composition | **Indicator-level** — visual wiring of strategy indicator outputs |
| 16 | Market regime | **Hybrid** — rule-based + ML calibration from the start |
| 17 | Risk management | **Multiple models** — Fixed %, Fixed $, Kelly, ATR-based |

---

## PHASE 1 — Core Engine

### 1.1 Data Source Abstraction Layer

**File:** `backend/app/trading/providers/__init__.py`

Define an abstract `MarketDataProvider` interface:

```
class MarketDataProvider(ABC):
    get_ohlcv(symbol, interval, start, end) → List[OHLCVBar]
    get_quote(symbol) → Quote
    search(query) → List[SymbolInfo]
    get_supported_intervals() → List[str]
    get_max_history(interval) → timedelta
```

**File:** `backend/app/trading/providers/yfinance_provider.py`

- Implements `MarketDataProvider` using yfinance
- Wraps existing cache logic from `routes/market.py`
- Returns normalized `OHLCVBar` dataclass: `(timestamp, open, high, low, close, volume)`

**File:** `backend/app/trading/providers/normalizer.py`

- `NormalizedDataService` that accepts a provider instance
- Transforms raw provider data into standardized internal format
- Strategies ONLY talk to the normalizer — never to providers directly
- Future providers (Polygon.io, Alpha Vantage) slot in by implementing the interface

### 1.2 Database Schema — New Tables

**Migration:** `backend/alembic/versions/0015_trading_strategies.py`

#### Table: `strategies`

| Column | Type | Notes |
|--------|------|-------|
| strategy_id | UUID PK | `default=uuid4` |
| user_id | UUID FK → users | ON DELETE CASCADE, nullable for system strategies |
| name | VARCHAR(128) NOT NULL | Strategy display name |
| description | TEXT | User-facing description |
| strategy_type | VARCHAR(30) NOT NULL | `'builtin'`, `'learned'`, `'pinescript'`, `'ml'` |
| category | VARCHAR(30) | `'trend_following'`, `'mean_reversion'`, `'momentum'`, `'breakout'`, `'volatility'`, `'ml_based'`, `'hybrid'` |
| timeframe | VARCHAR(20) | `'scalping'`, `'day_trading'`, `'swing'`, `'position'` |
| asset_class | VARCHAR(20) | `'stocks'`, `'etfs'`, `'futures'`, `'crypto'` |
| definition_json | JSONB NOT NULL | Full strategy definition (parameters, logic, source) |
| is_public | BOOLEAN DEFAULT FALSE | Visibility for social marketplace |
| is_system | BOOLEAN DEFAULT FALSE | Built-in strategies (not user-owned) |
| version | INTEGER DEFAULT 1 | Incremented on edit |
| created_at | TIMESTAMPTZ | server_default=func.now() |
| updated_at | TIMESTAMPTZ | server_default=func.now() |

**Indexes:** `idx_strategies_user_id`, `idx_strategies_type`, `idx_strategies_public` (partial: `WHERE is_public = TRUE`)

#### Table: `strategy_versions`

| Column | Type | Notes |
|--------|------|-------|
| version_id | UUID PK | |
| strategy_id | UUID FK → strategies | ON DELETE CASCADE |
| version_number | INTEGER NOT NULL | |
| definition_json | JSONB NOT NULL | Snapshot of definition at this version |
| created_at | TIMESTAMPTZ | |

**Constraint:** `UNIQUE(strategy_id, version_number)`

#### Table: `backtest_results`

| Column | Type | Notes |
|--------|------|-------|
| result_id | UUID PK | |
| user_id | UUID FK → users | ON DELETE CASCADE |
| strategy_id | UUID FK → strategies | ON DELETE SET NULL |
| symbol | VARCHAR(20) NOT NULL | |
| interval | VARCHAR(10) NOT NULL | e.g. `'1d'`, `'1h'` |
| start_date | TIMESTAMPTZ NOT NULL | |
| end_date | TIMESTAMPTZ NOT NULL | |
| parameters_json | JSONB | Strategy parameters used |
| commission_per_trade | NUMERIC(10,4) | Default 1.00 |
| slippage_pct | NUMERIC(6,4) | Default 0.0005 (0.05%) |
| results_json | JSONB NOT NULL | Full results: trades, equity curve, signals |
| metrics_json | JSONB NOT NULL | Sharpe, drawdown, win rate, profit factor, etc. |
| benchmark_json | JSONB | Buy-and-hold + SPY comparison |
| overfit_warning | BOOLEAN DEFAULT FALSE | |
| status | VARCHAR(20) DEFAULT 'pending' | `'pending'`, `'running'`, `'completed'`, `'failed'` |
| error_message | TEXT | On failure |
| created_at | TIMESTAMPTZ | |
| completed_at | TIMESTAMPTZ | |

**Indexes:** `idx_backtest_results_user_id`, `idx_backtest_results_strategy_id`, `idx_backtest_results_status`

#### Table: `trading_signals`

| Column | Type | Notes |
|--------|------|-------|
| signal_id | UUID PK | |
| strategy_id | UUID FK → strategies | ON DELETE CASCADE |
| user_id | UUID FK → users | ON DELETE CASCADE |
| symbol | VARCHAR(20) NOT NULL | |
| signal_type | VARCHAR(10) NOT NULL | `'entry'`, `'exit'`, `'stop_loss'` |
| direction | VARCHAR(10) NOT NULL | `'long'`, `'short'` |
| price | NUMERIC(18,4) NOT NULL | Suggested price |
| confidence | NUMERIC(5,2) | 0.00–1.00 |
| reasoning | TEXT | LLM or rule explanation |
| is_active | BOOLEAN DEFAULT TRUE | |
| triggered_at | TIMESTAMPTZ | When signal condition was met |
| expires_at | TIMESTAMPTZ | Signal expiry |
| created_at | TIMESTAMPTZ | |

**Indexes:** `idx_trading_signals_user_strategy`, `idx_trading_signals_symbol`, `idx_trading_signals_active` (partial)

### 1.3 ORM Models

**File:** `backend/app/models.py` — Add:

- `Strategy` — maps to `strategies`
- `StrategyVersion` — maps to `strategy_versions`
- `BacktestResult` — maps to `backtest_results`
- `TradingSignal` — maps to `trading_signals`

Follow existing patterns: UUID PKs, `server_default=func.now()`, `CheckConstraint` where applicable.

### 1.4 Pydantic Schemas

**File:** `backend/app/schemas.py` — Add:

```
StrategyCreate(name, description, strategy_type, category, timeframe, asset_class, definition_json, is_public)
StrategyOut(strategy_id, name, description, strategy_type, category, timeframe, asset_class, definition_json, is_public, is_system, version, created_at, updated_at)
    — orm_mode = True
StrategyUpdate(name?, description?, definition_json?, is_public?, category?, timeframe?, asset_class?)

BacktestRequest(strategy_id, symbol, interval, start_date?, end_date?, parameters_json?, commission_per_trade?, slippage_pct?)
BacktestResultOut(result_id, strategy_id, symbol, interval, start_date, end_date, parameters_json, results_json, metrics_json, benchmark_json, overfit_warning, status, error_message, created_at, completed_at)
    — orm_mode = True

TradingSignalOut(signal_id, strategy_id, symbol, signal_type, direction, price, confidence, reasoning, is_active, triggered_at, expires_at, created_at)
    — orm_mode = True

MetricsOut(total_return, annualized_return, sharpe_ratio, sortino_ratio, max_drawdown, max_drawdown_duration, win_rate, profit_factor, total_trades, avg_win, avg_loss, expectancy, calmar_ratio)
```

### 1.5 Built-in Strategy Engine

**File:** `backend/app/trading/engine/__init__.py`

Core backtesting engine:

```
class BacktestEngine:
    run(strategy_definition, ohlcv_data, params) → BacktestResult
```

- Iterates through OHLCV bars chronologically
- Applies strategy conditions to generate signals
- Simulates trade execution with commission and slippage
- Computes equity curve, drawdown, and all performance metrics
- Compares against buy-and-hold and SPY benchmarks

**File:** `backend/app/trading/engine/strategies/`

Built-in strategies as individual modules:

| Strategy | File | Parameters |
|----------|------|------------|
| SMA Crossover | `sma_crossover.py` | fast_period (10), slow_period (50) |
| RSI Mean Reversion | `rsi_mean_reversion.py` | period (14), oversold (30), overbought (70) |
| MACD Crossover | `macd_crossover.py` | fast (12), slow (26), signal (9) |
| Bollinger Band Squeeze | `bollinger_squeeze.py` | period (20), std_dev (2.0) |
| EMA Crossover | `ema_crossover.py` | fast_period (9), slow_period (21) |
| Stochastic Oscillator | `stochastic.py` | k_period (14), d_period (3), oversold (20), overbought (80) |
| ADX Trend | `adx_trend.py` | period (14), threshold (25) |
| VWAP Bounce | `vwap_bounce.py` | deviation (0.02) |
| Breakout | `breakout.py` | lookback (20), volume_factor (1.5) |
| Ichimoku Cloud | `ichimoku.py` | tenkan (9), kijun (26), senkou_b (52) |

Each strategy module:
- Exposes `name`, `description`, `default_params`, `param_schema`
- Implements `generate_signals(ohlcv_data, params) → List[Signal]`
- Returns entry, exit, and stop-loss signals with timestamps and prices

**File:** `backend/app/trading/engine/metrics.py`

Performance metric calculations:

- `total_return`, `annualized_return` (CAGR)
- `sharpe_ratio`, `sortino_ratio`, `calmar_ratio`
- `max_drawdown`, `max_drawdown_duration`
- `win_rate`, `profit_factor`, `expectancy`
- `total_trades`, `avg_win`, `avg_loss`
- `benchmark_comparison(equity_curve, spy_data, buy_hold_data)`
- `overfit_score(num_params, num_trades)` → boolean warning

### 1.6 Strategy Templates

Pre-built, cloneable starting points stored as system strategies (`is_system=True`):

| Template | Based On | Description |
|----------|----------|-------------|
| Conservative SMA | SMA Crossover | 50/200 golden cross, position trading |
| Aggressive RSI | RSI Mean Reversion | 14-period RSI, tight bands (25/75) |
| Momentum Breakout | Breakout | 20-bar high breakout with volume confirmation |
| Trend Rider | ADX + EMA | ADX > 25 + EMA cross for trend entries |
| Bollinger Mean Reversion | Bollinger Squeeze | Fade moves to outer bands |

### 1.7 API Routes

**File:** `backend/app/routes/trading.py`

```
GET    /api/v1/trading/strategies                 — List available strategies (user's + system)
POST   /api/v1/trading/strategies                 — Create a new strategy
GET    /api/v1/trading/strategies/{id}             — Get strategy details
PATCH  /api/v1/trading/strategies/{id}             — Update strategy
DELETE /api/v1/trading/strategies/{id}             — Delete strategy (user-owned only)
POST   /api/v1/trading/strategies/{id}/clone       — Clone a strategy (system or public)

POST   /api/v1/trading/backtest                    — Queue a backtest (returns job_id)
GET    /api/v1/trading/backtest/{id}               — Get backtest result/status (poll)
GET    /api/v1/trading/backtest/history             — List user's backtest history

GET    /api/v1/trading/signals/{strategy_id}       — Get active signals for a strategy
GET    /api/v1/trading/signals/symbol/{symbol}     — Get all active signals for a symbol
```

**Rate limits:**
- Backtest: 10 per hour, 3 concurrent per user
- Strategy CRUD: 30 per minute

**Registration in `main.py`:**
```python
from .routes import trading
app.include_router(trading.router, prefix=_V1)
```

### 1.8 arq Task Worker

**File:** `backend/app/trading/worker.py`

```python
from arq import create_pool
from arq.connections import RedisSettings

async def run_backtest(ctx, backtest_id: str):
    """Execute a backtest job.

    1. Load BacktestResult from DB (status='pending')
    2. Set status='running'
    3. Fetch OHLCV data via NormalizedDataService
    4. Run BacktestEngine
    5. Compute metrics + benchmark comparison
    6. Check overfit score
    7. Store results_json, metrics_json, benchmark_json
    8. Set status='completed' (or 'failed' with error_message)
    9. Write audit log entry
    """
    pass

class WorkerSettings:
    functions = [run_backtest]
    redis_settings = RedisSettings.from_dsn(REDIS_URL)
    max_jobs = 10
    job_timeout = 300  # 5 minutes max per backtest
```

**Deployment:** Run as a separate process: `arq backend.app.trading.worker.WorkerSettings`

Add to `docker-compose.yml`:
```yaml
  trading-worker:
    build:
      context: .
      dockerfile: backend/Dockerfile
    restart: unless-stopped
    command: ["arq", "app.trading.worker.WorkerSettings"]
    env_file:
      - ./backend/.env
    environment:
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-postgres}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB:-tickerTap}
      REDIS_URL: redis://redis:6379/0
    networks:
      - tickertap_net
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 1G
        reservations:
          cpus: "0.5"
          memory: 256M
```

### 1.9 Frontend — TradingPage

**File:** `frontend/src/pages/TradingPage.jsx`

Layout (Bloomberg terminal aesthetic):

```
┌─────────────────────────────────────────────────────────────────┐
│ TRADING AI                                                       │
├─────────────┬───────────────────────────────────────────────────┤
│ Controls    │  Chart Canvas (shared component)                   │
│             │  + signal overlay layer                            │
│ [Symbol ▼]  │  (entry markers = green diamond)                  │
│ [Strategy▼] │  (exit markers = red diamond)                     │
│ [Params]    │  (stop-loss = dashed red line)                    │
│             │                                                    │
│ [BACKTEST]  │                                                    │
│ [FORWARD]   │                                                    │
│             ├───────────────────────────────────────────────────┤
│ Metrics     │  Equity Curve / Drawdown Chart / Trade Log         │
│ Panel       │  (tabs)                                            │
│             │                                                    │
│ Sharpe: 1.4 │  [Replay ▶] [Speed ▼]                            │
│ MaxDD: -8%  │                                                    │
│ WinRate: 62%│                                                    │
│ PF: 1.8     │                                                    │
│             │                                                    │
│ [Rankings]  │  Benchmark: Buy&Hold +42% | SPY +38% | Strategy   │
│             │  +67%                                              │
└─────────────┴───────────────────────────────────────────────────┘
```

**Controls panel:**
- Symbol search (reuse existing `searchSymbols` from api/client.js)
- Strategy dropdown (fetched from `/trading/strategies`)
- Parameter sliders/inputs (dynamically rendered from `param_schema`)
- Interval selector (1m, 5m, 15m, 1h, 4h, 1d, 1w)
- Date range selector (1M, 3M, 6M, 1Y, 2Y, 5Y, ALL)
- Commission / slippage inputs (defaults pre-filled)
- [RUN BACKTEST] button → queues job, polls for result
- [GENERATE SIGNALS] button → forward-looking signals

**Metrics panel:**
- All metrics from `MetricsOut` displayed
- User-selectable ranking dropdown (Sort by: Sharpe, Return, Win Rate, etc.)
- Overfit warning badge (yellow) when triggered
- Benchmark comparison bar

**Equity curve tab:**
- Line chart of portfolio value over time
- Drawdown area chart below

**Trade log tab:**
- Table: Entry date, Exit date, Direction, Entry price, Exit price, P&L, P&L %, Duration

**Replay tab:**
- Slider to step through backtest bar-by-bar
- Play/pause button with speed control (1x, 2x, 5x, 10x)
- Chart redraws progressively, signals appear as they're triggered

### 1.10 Chart Component Refactor

**File:** `frontend/src/components/charts/OHLCVChart.jsx` (NEW — extracted)

Extract the OHLCV canvas rendering logic from `ChartsPage.jsx` into a reusable component:

```jsx
/**
 * OHLCVChart — reusable OHLCV canvas chart component.
 *
 * Props:
 *   data          — Array of {date, open, high, low, close, volume}
 *   mode          — 'candlestick' | 'line'
 *   overlays      — Array of overlay configs ({type:'sma', period:50, color:'#fff'})
 *   signals       — Array of {date, type:'entry'|'exit'|'stop_loss', price, direction}
 *   drawings      — Array of user drawing objects (lines, fibs, etc.)
 *   purchasePoints — Array of {date, price} from portfolio positions
 *   events        — Array of financial events (earnings, dividends)
 *   width, height — canvas dimensions
 *   onHover       — callback({date, o, h, l, c, v})
 *   onClick       — callback({date, price})
 */
```

**Changes to existing pages:**
- `ChartsPage.jsx` — replace inline canvas code with `<OHLCVChart />`, pass drawings/overlays/events as props
- `DashboardPage.jsx` — replace PortfolioChart with `<OHLCVChart />` for portfolio performance (line mode)
- `TradingPage.jsx` — use `<OHLCVChart />` with signals prop for entry/exit/stop-loss overlay

### 1.11 Legal Disclaimers

**File:** `frontend/src/pages/LegalPage.jsx` — Add a 4th tab: "Trading AI Disclaimer"

Content (added to `LEGAL_TABS` array):

```
TRADING AI DISCLAIMER

The algorithmic trading signals, backtesting results, and strategy recommendations
provided by TickerTap's Trading AI feature are for educational and informational
purposes only. They do NOT constitute financial advice, investment advice, trading
advice, or any other form of professional advice.

IMPORTANT:
• Past performance (backtesting results) is NOT indicative of future results.
• All trading involves risk. You may lose some or all of your invested capital.
• Backtesting results are hypothetical and subject to inherent limitations including
  look-ahead bias, survivorship bias, and curve-fitting.
• Forward-looking signals are generated by algorithms and AI models that may produce
  incorrect, incomplete, or misleading results.
• TickerTap is not a registered investment advisor, broker-dealer, or financial
  planner.
• You are solely responsible for your own investment decisions.
• Always consult a qualified financial professional before making investment decisions.

By using the Trading AI feature, you acknowledge that you have read, understood, and
agreed to this disclaimer.
```

**TradingPage.jsx:** Display a persistent disclaimer banner at the top of the page:
```
⚠ DISCLAIMER: Trading AI signals are for educational purposes only and do not
constitute financial advice. Past performance does not guarantee future results. [Read More]
```

### 1.12 Audit Trail Extension

Extend existing `AuditLog` usage to cover trading events:

- `backtest_queued` — user queued a backtest (record strategy_id, symbol, params)
- `backtest_completed` — backtest finished (record result_id, summary metrics)
- `signal_generated` — forward signal created (record signal_id, type, price)
- `strategy_created` / `strategy_updated` / `strategy_deleted`

### 1.13 Nav Integration

**File:** `frontend/src/App.jsx`

Add to NAV array:
```javascript
{ id: "trading", label: t("nav.trading"), Icon: Ic.trading },
```

Add to KNOWN_PAGES set: `"trading"`

Add to page outlet:
```jsx
{page === "trading" && (
  <TradingPage token={authToken} onViewChart={navigateToChart} />
)}
```

**File:** `frontend/src/components/common/Icons.jsx`

Add `trading` icon (chart with signal markers).

### 1.14 New Dependencies

**`backend/requirements.txt` — Add:**
```
arq>=0.25
numpy>=1.24
pandas>=2.0
```

**`frontend/package.json` — No new dependencies** (canvas rendering is vanilla, existing patterns).

---

## PHASE 2 — Data & Validation

### 2.1 TimescaleDB Extension

**Docker:** Add TimescaleDB to the Postgres container.

**File:** `docker-compose.yml` — Change db image:
```yaml
db:
  image: timescale/timescaledb:latest-pg15
```

**Migration:** `backend/alembic/versions/0016_intraday_bars.py`

```sql
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE intraday_bars (
    symbol      VARCHAR(20) NOT NULL,
    timestamp   TIMESTAMPTZ NOT NULL,
    interval    VARCHAR(5)  NOT NULL,   -- '1m', '5m', '15m', '1h'
    open        NUMERIC(18,4) NOT NULL,
    high        NUMERIC(18,4) NOT NULL,
    low         NUMERIC(18,4) NOT NULL,
    close       NUMERIC(18,4) NOT NULL,
    volume      BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (symbol, timestamp, interval)
);

SELECT create_hypertable('intraday_bars', 'timestamp');

-- Compression policy: compress chunks older than 7 days
ALTER TABLE intraday_bars SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol,interval'
);
SELECT add_compression_policy('intraday_bars', INTERVAL '7 days');

-- Retention: drop 1-min data older than 90 days
SELECT add_retention_policy('intraday_bars', INTERVAL '90 days',
    if_not_exists => true);
```

### 2.2 Intraday Data Archiver Worker

**File:** `backend/app/trading/archiver.py`

Background worker that runs during market hours:

```
Loop (every 60 seconds during market hours):
  1. Get list of "active" symbols (symbols with running strategies or active paper trades)
  2. For each symbol, fetch latest 1-min bars from yfinance
  3. Upsert into intraday_bars (deduplicate by symbol+timestamp+interval)
  4. Every 5 minutes, also store 5-min aggregated bars
  5. Sleep during market closed hours (use existing _is_market_open pattern)
```

**Downsampling job** (daily, after market close):
- Aggregate 1-min → 5-min bars for data older than 90 days
- Aggregate 5-min → 1-hour bars for data older than 1 year
- Daily bars kept forever (existing yfinance data)

### 2.3 Multi-Timeframe Data Access

**File:** `backend/app/trading/providers/normalizer.py` — Extend:

```python
def get_multi_timeframe(symbol, timeframes: List[str], start, end):
    """Return aligned OHLCV data at multiple intervals.

    For intraday intervals, pull from intraday_bars hypertable.
    For daily+, pull from yfinance provider.
    Returns dict: { '1h': [bars], '1d': [bars] }
    """
```

### 2.4 Walk-Forward Validation Engine

**File:** `backend/app/trading/engine/walk_forward.py`

```python
def walk_forward_validate(strategy, data, train_window, test_window, step):
    """Rolling walk-forward analysis.

    1. Split data into overlapping train/test windows
    2. For each window: optimize on train, evaluate on test
    3. Aggregate out-of-sample results
    4. Return honest performance metrics vs naive backtest

    Default: train=252 bars (1 year), test=63 bars (3 months), step=63
    Required for all ML-based strategies. Optional for rule-based.
    """
```

### 2.5 Strategy Alerts — Unified Notification Service

**Migration:** `backend/alembic/versions/0017_notifications.py`

#### Table: `notifications`

| Column | Type | Notes |
|--------|------|-------|
| notification_id | UUID PK | |
| user_id | UUID FK → users | ON DELETE CASCADE |
| event_type | VARCHAR(50) NOT NULL | `'signal_entry'`, `'signal_exit'`, `'backtest_complete'`, `'strategy_decay'`, `'regime_change'` |
| title | VARCHAR(200) NOT NULL | |
| body | TEXT | |
| metadata_json | JSONB | Additional context (strategy_id, symbol, etc.) |
| is_read | BOOLEAN DEFAULT FALSE | |
| created_at | TIMESTAMPTZ | |

**Indexes:** `idx_notifications_user_unread` (partial: `WHERE is_read = FALSE`)

#### Table: `user_webhooks`

| Column | Type | Notes |
|--------|------|-------|
| webhook_id | UUID PK | |
| user_id | UUID FK → users | ON DELETE CASCADE |
| url | TEXT NOT NULL | Webhook endpoint URL |
| events | JSONB NOT NULL | Array of event types to receive |
| is_active | BOOLEAN DEFAULT TRUE | |
| created_at | TIMESTAMPTZ | |

**File:** `backend/app/trading/notifications.py`

```python
async def notify(user_id, event_type, title, body, metadata=None):
    """Unified notification dispatcher.

    1. Insert into notifications table (in-app)
    2. If user has email alerts enabled for this event_type → send email
    3. If user has webhook configured for this event_type → POST to webhook URL

    User preferences stored in User.preferences JSONB:
    {
        "notifications": {
            "email": ["signal_entry", "signal_exit", "strategy_decay"],
            "webhook": ["signal_entry", "signal_exit"]
        }
    }
    """
```

**API Routes (added to `trading.py`):**
```
GET  /api/v1/trading/notifications          — List user's notifications (paginated)
POST /api/v1/trading/notifications/read      — Mark notifications as read
POST /api/v1/trading/webhooks                — Create/update webhook config
GET  /api/v1/trading/webhooks                — Get webhook config
```

### 2.6 Event-Aware No-Trade Zones

**File:** `backend/app/trading/engine/events.py`

```python
def get_no_trade_zones(symbol, start_date, end_date):
    """Return date ranges when strategies should pause signals.

    Sources (from yfinance):
    - Earnings dates: ±1 day around earnings
    - Ex-dividend dates: day before + day of

    Hardcoded high-impact events:
    - FOMC meeting dates (8 per year, published schedule)
    - Quarterly options expiration (OpEx)

    Returns List[{start, end, reason}]
    """
```

Strategies optionally respect no-trade zones via a `respect_no_trade_zones` parameter (default: True).

---

## PHASE 3 — AI & ML

### 3.1 LLM Container (Ollama)

Extends existing Server B Ollama setup. New capabilities:

**File:** `server-b-worker/strategy_researcher.py`

```python
def research_strategies(market_data_summary):
    """Use Ollama to research and evaluate trading strategies.

    Prompt: Given recent market conditions (volatility, trend, volume patterns),
    identify the top 5 most promising trading strategies. For each, provide:
    - Strategy name and type
    - Entry/exit rules
    - Expected market conditions for optimal performance
    - Historical context for why this works

    Returns structured JSON parsed from LLM response.
    """

def explain_strategy(strategy_definition, backtest_results):
    """Generate a human-readable explanation of why a strategy works or doesn't.

    Used in the strategy detail view and marketplace listings.
    """

def suggest_improvements(strategy_definition, backtest_results):
    """Suggest parameter tweaks or modifications to improve strategy performance.

    Returns structured suggestions with reasoning.
    """
```

### 3.2 Quant ML Container

**File:** `trading-ml/Dockerfile`

```dockerfile
FROM python:3.11-slim
RUN pip install torch scikit-learn pandas numpy joblib fastapi uvicorn
COPY . /app
WORKDIR /app
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8001"]
```

**File:** `trading-ml/api.py`

Internal API (not exposed to users — called by the trading worker):

```
POST /predict          — Run inference on a trained model
POST /train            — Train/retrain a model on new data
GET  /models           — List available models
GET  /regime           — Get current market regime classification
```

**File:** `trading-ml/models/`

| Model | File | Purpose |
|-------|------|---------|
| LSTM Price Predictor | `lstm_predictor.py` | Short-term price direction prediction |
| Pattern Classifier | `pattern_classifier.py` | Candlestick pattern recognition (CNN) |
| Feature Classifier | `feature_classifier.py` | Multi-feature entry/exit scoring (Random Forest) |
| Regime Detector | `regime_detector.py` | Market regime classification (HMM + rule-based hybrid) |

**Docker Compose addition:**
```yaml
  trading-ml:
    build:
      context: ./trading-ml
      dockerfile: Dockerfile
    restart: unless-stopped
    networks:
      - tickertap_net
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 2G
        reservations:
          cpus: "0.5"
          memory: 512M
```

### 3.3 Market Regime Detection (Hybrid)

**File:** `trading-ml/models/regime_detector.py`

**Rule-based layer (always available):**

| Regime | Conditions |
|--------|-----------|
| Trending Up | ADX > 25 AND SMA(50) slope > 0 AND price > SMA(200) |
| Trending Down | ADX > 25 AND SMA(50) slope < 0 AND price < SMA(200) |
| Ranging | ADX < 20 AND ATR(14) < ATR(14, 50-day avg) |
| Volatile | ATR(14) > 1.5 × ATR(14, 50-day avg) |

**ML calibration layer:**
- Hidden Markov Model trained on [returns, volatility, volume, ADX, ATR]
- Adjusts rule thresholds based on learned regime transitions
- Retrained weekly using the latest 2 years of daily data

**API exposed as:**
```
GET /api/v1/trading/regime/{symbol}  →  { regime: "trending_up", confidence: 0.82, recommended_strategies: [...] }
```

### 3.4 AI Learner — Strategy Research & Ranking

**File:** `server-b-worker/strategy_learner.py`

Background periodic job (runs daily after market close):

```
1. Fetch latest market data for top 100 liquid stocks
2. Run each built-in strategy against all stocks (parallel via ProcessPoolExecutor)
3. Compute performance metrics for each strategy × stock combination
4. Use Ollama to analyze patterns:
   - Which strategies performed best in current regime?
   - Are there parameter combinations that consistently outperform?
   - Are any strategies showing decay?
5. Rank strategies by configurable metric (default: Sharpe ratio)
6. Store rankings in DB (strategies table, update a rankings_json field)
7. Generate new "learned" strategies if LLM identifies novel patterns
8. Publish to notifications: "Strategy X is now top-ranked for {regime}"
```

### 3.5 News Sentiment as Signal Filter

**File:** `backend/app/trading/engine/filters.py`

```python
def sentiment_filter(signal, symbol, min_sentiment=None):
    """Filter strategy signals based on news sentiment scores.

    Uses existing NewsArticleTicker scores.

    If min_sentiment is set (e.g., 2):
    - Long entries only when latest ticker sentiment >= min_sentiment
    - Short entries only when latest ticker sentiment <= -min_sentiment
    - Neutral (no recent news) → pass through

    Returns: signal (if passes) or None (if filtered out)
    """
```

Exposed as an optional parameter in strategy definitions:
```json
{
  "filters": {
    "sentiment": { "enabled": true, "min_score": 2 }
  }
}
```

### 3.6 Strategy Decay Detection

**File:** `backend/app/trading/engine/decay.py`

```python
def detect_decay(strategy_id, symbol, lookback_days=90):
    """Monitor rolling strategy performance vs historical average.

    1. Compute rolling 30-day Sharpe ratio over the lookback window
    2. Compare against the strategy's all-time average Sharpe
    3. If rolling Sharpe < 50% of average for 2+ consecutive periods → decay alert

    Returns: { is_decaying: bool, current_sharpe: float, avg_sharpe: float, decay_pct: float }
    """
```

Runs as part of the daily learner job. Triggers notification to user if decay detected.

### 3.7 Risk Management / Position Sizing

**File:** `backend/app/trading/engine/risk.py`

```python
class PositionSizer:
    """Calculate position sizes using various risk models.

    Models:
    - fixed_percentage(account_size, risk_pct, entry, stop_loss) → shares
    - fixed_dollar(account_size, risk_amount, entry, stop_loss) → shares
    - kelly(win_rate, avg_win, avg_loss) → fraction of account
    - fractional_kelly(win_rate, avg_win, avg_loss, fraction=0.5) → fraction
    - atr_based(account_size, risk_pct, atr, multiplier=2.0) → shares

    Default: fixed_percentage with 2% risk per trade
    """
```

### 3.8 Drawdown Circuit Breaker

**File:** `backend/app/trading/engine/circuit_breaker.py`

```python
def check_circuit_breaker(strategy_id, user_id, max_drawdown_pct=None):
    """Pause strategy if drawdown exceeds threshold.

    Checks paper trading equity curve (Phase 6) or simulated P&L.

    If max_drawdown_pct is set and current drawdown exceeds it:
    1. Set all active signals for this strategy to is_active=False
    2. Notify user: "Strategy X paused — drawdown exceeded {max_drawdown_pct}%"
    3. Log to audit trail

    Default threshold: 15% (configurable per strategy)
    """
```

---

## PHASE 4 — PineScript & Strategy Composition

### 4.1 PineScript Parser (Deterministic — lark)

**File:** `backend/app/trading/pinescript/grammar.py`

EBNF grammar covering the core PineScript subset:

**Supported constructs:**
- Variable declarations: `var float x = 0.0`
- Assignments: `x := close > open ? 1 : 0`
- Conditionals: `if`, `else if`, `else`
- Built-in functions: `ta.sma()`, `ta.ema()`, `ta.rsi()`, `ta.macd()`, `ta.bb()`, `ta.atr()`, `ta.adx()`, `ta.stoch()`, `ta.vwap()`, `ta.highest()`, `ta.lowest()`, `ta.crossover()`, `ta.crossunder()`
- Strategy functions: `strategy.entry()`, `strategy.exit()`, `strategy.close()`
- Input functions: `input.int()`, `input.float()`, `input.bool()`
- Series access: `close[1]`, `high[3]`
- Math: `math.abs()`, `math.max()`, `math.min()`, `math.round()`
- Plotting (parsed but mapped to chart overlays): `plot()`, `hline()`, `bgcolor()`
- Arithmetic: `+`, `-`, `*`, `/`, `%`
- Comparison: `>`, `<`, `>=`, `<=`, `==`, `!=`
- Logical: `and`, `or`, `not`

**File:** `backend/app/trading/pinescript/transpiler.py`

```python
def transpile(pinescript_source: str) -> StrategyDefinition:
    """Parse PineScript source → AST → safe strategy definition.

    1. Lex + parse using lark grammar
    2. Walk AST: map each node to a whitelisted Python primitive
    3. Return a StrategyDefinition that the BacktestEngine can execute

    Safety: The transpiler CANNOT produce arbitrary Python code.
    It maps AST nodes to a fixed set of indicator functions and
    signal generators. If a construct is unsupported, it raises
    PineScriptUnsupportedError with a clear message.
    """
```

**File:** `backend/app/trading/pinescript/llm_fallback.py`

```python
def llm_translate(pinescript_source: str) -> str:
    """LLM fallback for complex PineScript not covered by the grammar.

    1. Send source to Ollama with a translation prompt
    2. Receive Python code
    3. Parse with ast.parse()
    4. Walk AST: reject ANY node not in the whitelist:
       - No imports, no __builtins__, no exec/eval
       - No file I/O, no network, no subprocess
       - Only allowed: arithmetic, comparisons, list/dict ops,
         calls to whitelisted indicator functions
    5. If validation passes: execute in gVisor container with:
       - No network access
       - Read-only filesystem
       - 512MB memory limit
       - 30-second timeout
    6. Return results

    UI: Strategies transpiled via LLM get an "AI-Translated" badge
    vs "Verified" badge for lark-parsed strategies.
    """
```

### 4.2 Strategy CRUD & Version History

**API Routes (added to `trading.py`):**
```
POST /api/v1/trading/pinescript/validate    — Validate PineScript syntax
POST /api/v1/trading/pinescript/transpile   — Transpile PineScript → strategy
GET  /api/v1/trading/strategies/{id}/versions  — List version history
GET  /api/v1/trading/strategies/{id}/versions/{v}  — Get specific version
POST /api/v1/trading/strategies/{id}/revert/{v}    — Revert to a version
```

On every strategy update, auto-create a `StrategyVersion` row with the previous `definition_json` snapshot.

### 4.3 Parameterization UI

**File:** `frontend/src/components/trading/ParameterEditor.jsx`

Dynamically renders parameter controls based on `param_schema` from the strategy definition:

```json
{
  "params": [
    { "name": "fast_period", "type": "int", "default": 10, "min": 2, "max": 200, "step": 1, "label": "Fast SMA Period" },
    { "name": "slow_period", "type": "int", "default": 50, "min": 5, "max": 500, "step": 1, "label": "Slow SMA Period" },
    { "name": "stop_loss_pct", "type": "float", "default": 0.02, "min": 0.005, "max": 0.10, "step": 0.005, "label": "Stop Loss %" }
  ]
}
```

Renders: slider + numeric input for each param. Changes trigger re-backtest.

### 4.4 PineScript Editor

**File:** `frontend/src/components/trading/PineScriptEditor.jsx`

- Syntax-highlighted code editor (use `<textarea>` with custom highlighting — no external dependency like Monaco to keep bundle small)
- Line numbers
- Error highlighting (red underline on parse errors)
- "Validate" button → calls `/pinescript/validate`
- "Transpile & Test" button → calls `/pinescript/transpile`, then auto-runs backtest
- LLM assist buttons: "Explain This" → sends code to Ollama, "Suggest Improvements" → sends code + results

### 4.5 Strategy Composition — Indicator-Level

**File:** `backend/app/trading/engine/composition.py`

```python
class ComposedStrategy:
    """Combine indicators from multiple strategies with custom logic.

    Composition graph:
    {
        "nodes": [
            { "id": "rsi", "strategy": "rsi_mean_reversion", "output": "rsi_value" },
            { "id": "sma", "strategy": "sma_crossover", "output": "trend_direction" },
            { "id": "bb", "strategy": "bollinger_squeeze", "output": "squeeze_detected" }
        ],
        "logic": {
            "entry_long": "rsi.rsi_value < 30 AND sma.trend_direction == 'up' AND bb.squeeze_detected",
            "entry_short": "rsi.rsi_value > 70 AND sma.trend_direction == 'down'",
            "exit": "rsi.rsi_value > 50 OR sma.trend_direction == 'neutral'"
        }
    }
    """
```

**File:** `frontend/src/components/trading/CompositionEditor.jsx`

Visual node-based editor:
- Drag strategy blocks onto a canvas
- Each block exposes output pins (indicators)
- Connect outputs to a logic node with AND/OR/comparison operators
- Generate `composition_json` that the backend executes

---

## PHASE 5 — Social & Integration

### 5.1 Database Schema

**Migration:** `backend/alembic/versions/0018_social_strategies.py`

#### Table: `strategy_ratings`

| Column | Type | Notes |
|--------|------|-------|
| rating_id | UUID PK | |
| strategy_id | UUID FK → strategies | ON DELETE CASCADE |
| user_id | UUID FK → users | ON DELETE CASCADE |
| stars | SMALLINT NOT NULL | 1–5 |
| review | TEXT | Optional review text |
| created_at | TIMESTAMPTZ | |

**Constraint:** `UNIQUE(strategy_id, user_id)` — one rating per user per strategy

#### Table: `strategy_usage`

| Column | Type | Notes |
|--------|------|-------|
| usage_id | UUID PK | |
| strategy_id | UUID FK → strategies | ON DELETE CASCADE |
| user_id | UUID FK → users | ON DELETE CASCADE |
| cloned_at | TIMESTAMPTZ | When user cloned this strategy |

### 5.2 API Routes

```
GET    /api/v1/trading/marketplace              — Browse public strategies (paginated, filtered, sorted)
GET    /api/v1/trading/marketplace/featured      — Featured/trending strategies
POST   /api/v1/trading/strategies/{id}/rate      — Rate a strategy (1-5 stars + review)
GET    /api/v1/trading/strategies/{id}/ratings   — Get ratings for a strategy
GET    /api/v1/trading/strategies/{id}/stats     — Usage stats (clones, avg rating, backtests)
POST   /api/v1/trading/strategies/{id}/publish   — Toggle public visibility
```

**Marketplace query parameters:**
- `category` — filter by strategy category
- `timeframe` — filter by timeframe
- `asset_class` — filter by asset class
- `sort_by` — `rating`, `usage`, `return`, `sharpe`, `newest`
- `search` — text search on name/description
- `limit`, `offset` — pagination

### 5.3 Strategy Browser Page

**File:** `frontend/src/pages/MarketplacePage.jsx`

Layout:
```
┌────────────────────────────────────────────────────────────────┐
│ STRATEGY MARKETPLACE                                            │
├────────────────────────────────────────────────────────────────┤
│ [Search...] [Category ▼] [Timeframe ▼] [Sort: Rating ▼]       │
├────────────────────────────────────────────────────────────────┤
│ ★ FEATURED                                                      │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐                        │
│ │ Strategy │ │ Strategy │ │ Strategy │  ← Horizontal scroll    │
│ │ Card     │ │ Card     │ │ Card     │                        │
│ └──────────┘ └──────────┘ └──────────┘                        │
├────────────────────────────────────────────────────────────────┤
│ ALL STRATEGIES                                                  │
│ ┌─────────────────────────────────────────────────────────┐    │
│ │ Strategy Name | Author | Category | ★ 4.2 | 150 uses   │    │
│ │ Strategy Name | Author | Category | ★ 3.8 | 89 uses    │    │
│ │ ...                                                      │    │
│ └─────────────────────────────────────────────────────────┘    │
│ [1] [2] [3] ... [Next →]                                       │
└────────────────────────────────────────────────────────────────┘
```

### 5.4 Strategy Comparison (Side-by-Side)

**File:** `frontend/src/components/trading/StrategyComparison.jsx`

- Select 2–3 strategies
- Run backtests on the same symbol/period
- Display metrics side-by-side in a comparison table
- Overlay all equity curves on a single chart (different colors)

### 5.5 Portfolio/Watchlist/Orders Integration

- "Run strategy on my watchlist" — batch backtest across all watchlist symbols
- "Apply to portfolio" — generate signals for all portfolio positions
- Strategy signals page: one-click "Create Order" button that pre-fills the order form with signal data (symbol, side, quantity from position sizer, price)

### 5.6 Export

- CSV export of backtest trade log
- PDF report: strategy summary, metrics, equity curve chart, trade log
- API: `GET /api/v1/trading/backtest/{id}/export?format=csv|pdf`

---

## PHASE 6 — Paper Trading

### 6.1 Database Schema

**Migration:** `backend/alembic/versions/0019_paper_trading.py`

#### Table: `paper_trades`

| Column | Type | Notes |
|--------|------|-------|
| paper_trade_id | UUID PK | |
| user_id | UUID FK → users | ON DELETE CASCADE |
| strategy_id | UUID FK → strategies | ON DELETE SET NULL |
| symbol | VARCHAR(20) NOT NULL | |
| initial_capital | NUMERIC(18,2) NOT NULL | Starting virtual balance |
| current_equity | NUMERIC(18,2) NOT NULL | Current virtual balance + positions |
| status | VARCHAR(20) DEFAULT 'active' | `'active'`, `'paused'`, `'stopped'` |
| parameters_json | JSONB | Strategy parameters |
| created_at | TIMESTAMPTZ | |
| stopped_at | TIMESTAMPTZ | |

#### Table: `paper_trade_positions`

| Column | Type | Notes |
|--------|------|-------|
| position_id | UUID PK | |
| paper_trade_id | UUID FK → paper_trades | ON DELETE CASCADE |
| side | VARCHAR(10) NOT NULL | `'long'`, `'short'` |
| entry_price | NUMERIC(18,4) NOT NULL | |
| entry_date | TIMESTAMPTZ NOT NULL | |
| exit_price | NUMERIC(18,4) | |
| exit_date | TIMESTAMPTZ | |
| quantity | NUMERIC(18,6) NOT NULL | |
| pnl | NUMERIC(18,4) | |
| status | VARCHAR(20) DEFAULT 'open' | `'open'`, `'closed'` |

#### Table: `paper_trade_equity_snapshots`

| Column | Type | Notes |
|--------|------|-------|
| snapshot_id | UUID PK | |
| paper_trade_id | UUID FK → paper_trades | ON DELETE CASCADE |
| equity | NUMERIC(18,4) NOT NULL | |
| timestamp | TIMESTAMPTZ NOT NULL | |

### 6.2 Paper Trading Evaluation Worker

**File:** `backend/app/trading/paper_worker.py`

Periodic evaluator (runs every 60 seconds during market hours):

```
1. Load all active paper_trades
2. For each paper trade:
   a. Fetch latest price for the symbol
   b. Evaluate strategy conditions against latest data
   c. If entry signal → create paper_trade_position (virtual buy/sell)
   d. If exit signal → close paper_trade_position, compute P&L
   e. If stop-loss hit → close position
   f. Check circuit breaker (max drawdown)
   g. Update current_equity
   h. Insert equity snapshot
   i. If new signal → notify user (via unified notification service)
3. Sleep 60 seconds, repeat
```

### 6.3 API Routes

```
POST   /api/v1/trading/paper                   — Start a paper trade
GET    /api/v1/trading/paper                   — List user's paper trades
GET    /api/v1/trading/paper/{id}              — Get paper trade details
POST   /api/v1/trading/paper/{id}/pause        — Pause paper trade
POST   /api/v1/trading/paper/{id}/resume       — Resume paper trade
POST   /api/v1/trading/paper/{id}/stop         — Stop paper trade
GET    /api/v1/trading/paper/{id}/equity        — Get equity time series (for chart)
GET    /api/v1/trading/paper/{id}/positions     — Get position history
```

### 6.4 Paper Trading Dashboard

**File:** `frontend/src/components/trading/PaperTradingPanel.jsx`

Embedded within TradingPage as a tab:

```
┌─────────────────────────────────────────────────────┐
│ PAPER TRADING                                        │
├─────────────────────────────────────────────────────┤
│ Active: Strategy X on AAPL                           │
│ Started: 2026-03-10 | Capital: $10,000              │
│ Current Equity: $10,450 (+4.5%)                     │
│ Open Position: LONG 50 shares @ $178.50             │
│                                                      │
│ [Equity Chart — real-time updates via SSE]           │
│                                                      │
│ Trade History:                                       │
│ #1 LONG  AAPL 50@175.20 → 178.50 +$165 (+1.88%)  │
│ #2 SHORT AAPL 30@180.00 → 178.50 +$45  (+0.83%)   │
│                                                      │
│ [PAUSE] [STOP]                                       │
└─────────────────────────────────────────────────────┘
```

### 6.5 SSE for Real-Time Updates

**File:** `backend/app/routes/trading_sse.py`

```python
@router.get("/trading/paper/{paper_trade_id}/stream")
async def paper_trade_stream(paper_trade_id: UUID, user=Depends(get_current_user)):
    """Server-Sent Events stream for real-time paper trade updates.

    Events:
    - equity_update: { equity: 10450.00, timestamp: "..." }
    - position_opened: { side, symbol, price, quantity }
    - position_closed: { side, symbol, entry, exit, pnl }
    - signal: { type, direction, price, confidence }
    - circuit_breaker: { reason, drawdown_pct }
    """
    async def event_generator():
        # Subscribe to Redis pub/sub channel for this paper trade
        ...

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

---

## IMPLEMENTATION CHECKLIST

```markdown
PHASE 1 — Core Engine:
1.  Create data source abstraction layer (providers/, normalizer.py)
2.  Create Alembic migration 0015 (strategies, strategy_versions, backtest_results, trading_signals)
3.  Add Strategy, StrategyVersion, BacktestResult, TradingSignal ORM models to models.py
4.  Add all trading Pydantic schemas to schemas.py
5.  Implement BacktestEngine core (engine/__init__.py)
6.  Implement 10 built-in strategy modules (strategies/*.py)
7.  Implement performance metrics calculator (engine/metrics.py)
8.  Implement benchmark comparison (buy-and-hold + SPY)
9.  Implement overfit detection
10. Create strategy templates (5 pre-built, is_system=True)
11. Create /api/v1/trading/* route module (trading.py)
12. Register trading router in main.py
13. Implement arq task worker for backtesting (trading/worker.py)
14. Add trading-worker service to docker-compose.yml
15. Extract OHLCVChart shared component from ChartsPage.jsx
16. Update ChartsPage.jsx to use <OHLCVChart />
17. Update DashboardPage.jsx to use <OHLCVChart />
18. Build TradingPage.jsx (controls, chart, metrics, equity curve, trade log, replay)
19. Add trading nav item + routing in App.jsx
20. Add trading icon to Icons.jsx
21. Add trading API methods to api/client.js
22. Add Trading AI Disclaimer to LegalPage.jsx
23. Add disclaimer banner to TradingPage.jsx
24. Extend audit trail for trading events
25. Add arq and numpy/pandas to requirements.txt
26. Run Alembic migration 0015
27. Test end-to-end: select strategy → run backtest → view results on chart

PHASE 2 — Data & Validation:
28. Switch Docker Postgres to timescale/timescaledb:latest-pg15
29. Create Alembic migration 0016 (intraday_bars hypertable + compression/retention)
30. Implement intraday data archiver worker (trading/archiver.py)
31. Implement downsampling job (1m→5m→1h tiered)
32. Extend normalizer for multi-timeframe data access
33. Implement walk-forward validation engine (engine/walk_forward.py)
34. Create Alembic migration 0017 (notifications, user_webhooks)
35. Implement unified notification service (trading/notifications.py)
36. Add notification API routes
37. Implement event-aware no-trade zones (engine/events.py)
38. Add webhook management UI to SettingsPage.jsx
39. Add notification bell/panel to App.jsx topbar

PHASE 3 — AI & ML:
40. Create trading-ml container (Dockerfile, api.py)
41. Implement LSTM price predictor model
42. Implement pattern classifier model (CNN)
43. Implement feature classifier model (Random Forest)
44. Implement market regime detector (HMM + rule-based hybrid)
45. Add trading-ml service to docker-compose.yml
46. Implement strategy researcher on Server B (strategy_researcher.py)
47. Implement strategy learner job (strategy_learner.py)
48. Add regime endpoint to trading routes
49. Implement news sentiment signal filter (engine/filters.py)
50. Implement strategy decay detection (engine/decay.py)
51. Implement risk management / position sizing (engine/risk.py)
52. Implement drawdown circuit breaker (engine/circuit_breaker.py)
53. Add regime indicator to TradingPage UI
54. Add position sizing controls to TradingPage

PHASE 4 — PineScript & Composition:
55. Define lark EBNF grammar for PineScript subset (pinescript/grammar.py)
56. Implement deterministic transpiler (pinescript/transpiler.py)
57. Implement LLM fallback with AST validation (pinescript/llm_fallback.py)
58. Add PineScript API routes (validate, transpile)
59. Add strategy version history API routes
60. Build PineScriptEditor component (frontend)
61. Build ParameterEditor component (frontend)
62. Implement indicator-level strategy composition engine (engine/composition.py)
63. Build CompositionEditor visual node editor (frontend)
64. Add "Verified" / "AI-Translated" badges to strategy cards

PHASE 5 — Social & Integration:
65. Create Alembic migration 0018 (strategy_ratings, strategy_usage)
66. Add marketplace API routes (browse, rate, stats, publish)
67. Build MarketplacePage.jsx
68. Build StrategyComparison component
69. Implement portfolio/watchlist batch backtest integration
70. Implement one-click order creation from signals
71. Implement CSV/PDF export for backtest results
72. Add marketplace nav item + routing in App.jsx

PHASE 6 — Paper Trading:
73. Create Alembic migration 0019 (paper_trades, paper_trade_positions, paper_trade_equity_snapshots)
74. Implement paper trading evaluation worker (paper_worker.py)
75. Add paper trading API routes
76. Implement SSE endpoint for real-time updates (trading_sse.py)
77. Build PaperTradingPanel component (frontend)
78. Add SSE client logic to TradingPage
79. Connect circuit breaker to paper trading positions
80. Test end-to-end: start paper trade → receive real-time updates → stop trade
```

---

## File Index (New Files)

```
backend/
  app/
    trading/
      __init__.py
      providers/
        __init__.py                    — MarketDataProvider ABC
        yfinance_provider.py           — yfinance adapter
        normalizer.py                  — Normalized data service
      engine/
        __init__.py                    — BacktestEngine core
        metrics.py                     — Performance calculations
        walk_forward.py                — Walk-forward validation
        events.py                      — No-trade zones
        filters.py                     — News sentiment filter
        decay.py                       — Strategy decay detection
        risk.py                        — Position sizing models
        circuit_breaker.py             — Drawdown circuit breaker
        composition.py                 — Indicator-level composition
        strategies/
          __init__.py                  — Strategy registry
          sma_crossover.py
          rsi_mean_reversion.py
          macd_crossover.py
          bollinger_squeeze.py
          ema_crossover.py
          stochastic.py
          adx_trend.py
          vwap_bounce.py
          breakout.py
          ichimoku.py
      pinescript/
        __init__.py
        grammar.py                     — lark EBNF grammar
        transpiler.py                  — Deterministic transpiler
        llm_fallback.py                — LLM translation + AST validation
      worker.py                        — arq backtest worker
      archiver.py                      — Intraday data archiver
      paper_worker.py                  — Paper trading evaluator
      notifications.py                 — Unified notification service
    routes/
      trading.py                       — Trading API routes
      trading_sse.py                   — SSE for paper trading
  alembic/versions/
    0015_trading_strategies.py
    0016_intraday_bars.py
    0017_notifications.py
    0018_social_strategies.py
    0019_paper_trading.py

trading-ml/
  Dockerfile
  api.py                               — Internal ML API
  models/
    lstm_predictor.py
    pattern_classifier.py
    feature_classifier.py
    regime_detector.py

server-b-worker/
  strategy_researcher.py               — LLM strategy research
  strategy_learner.py                  — Daily learning job

frontend/src/
  components/
    charts/
      OHLCVChart.jsx                   — Shared chart component (extracted)
    trading/
      ParameterEditor.jsx              — Dynamic parameter controls
      PineScriptEditor.jsx             — PineScript code editor
      CompositionEditor.jsx            — Visual strategy composer
      StrategyComparison.jsx           — Side-by-side comparison
      PaperTradingPanel.jsx            — Paper trading dashboard
  pages/
    TradingPage.jsx                    — Main trading AI page
    MarketplacePage.jsx                — Strategy marketplace browser
```

---

## Environment Variables (New)

```bash
# backend/.env
REDIS_URL=redis://redis:6379/0          # Already exists, used by arq
TRADING_ML_URL=http://trading-ml:8001   # Internal ML service URL
MAX_CONCURRENT_BACKTESTS=3              # Per-user limit
BACKTEST_TIMEOUT=300                    # Seconds

# trading-ml container
MODEL_DIR=/app/models/trained           # Persisted model weights
RETRAIN_SCHEDULE=0 22 * * 1-5          # Cron: weekdays at 10 PM ET
```

---

## User Guide Updates Required

Per CLAUDE.md rules, update `frontend/src/pages/UserGuidePage.jsx`:

1. **FEATURES tab** — Add "Trading AI" section covering: backtesting, forward signals, strategy selection, chart overlay, performance dashboard, replay mode, PineScript editor, marketplace, paper trading.

2. **FAQ tab** — Add entries:
   - "How does the backtesting work?"
   - "What are forward-looking signals?"
   - "Can I create my own trading strategy?"
   - "What is paper trading?"
   - "Are the AI trading signals real financial advice?" (→ No, disclaimer)

3. **AI system prompt** (`backend/app/routes/guide.py`) — Update `_SYSTEM_PROMPT` to include Trading AI feature descriptions so the AI assistant can answer questions about it.
