# TickerTap — Full-Stack Stock Trading Platform

A Bloomberg-terminal-inspired trading platform with a FastAPI backend and a React frontend.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Architecture Overview](#architecture-overview)
3. [Features](#features)
4. [Environment Variables](#environment-variables)
5. [Backend Development](#backend-development)
6. [Frontend Development](#frontend-development)
7. [Running Tests](#running-tests)
8. [Database Migrations](#database-migrations)
9. [Security Notes](#security-notes)
10. [Project Structure](#project-structure)

---

## Quick Start

The fastest way to run the full stack is with Docker Compose:

```bash
# 1. Copy and fill in the required environment variables
cp .env.example .env
# Edit .env — at minimum set JWT_SECRET and SMTP credentials

# 2. Start all services (PostgreSQL, Redis, backend API)
docker compose up --build

# 3. Apply database migrations
docker compose exec app alembic upgrade head

# 4. Build the frontend
cd frontend && npm install && npx vite build

# Frontend available at: https://your-domain (served by nginx)
# Backend API available at: http://localhost:8000
# API docs (Swagger UI): http://localhost:8000/docs
```

---

## Architecture Overview

```
Browser (React 19 SPA)
       │
       │  HTTPS / JSON
       ▼
   nginx (port 443/80)
       │
   ┌───┴─────────────┐
   │                 │
   ▼                 ▼
Frontend          Backend
(Vite build)     (FastAPI)
/dist static     port 8000
                     │
              ┌──────┴──────┐
              │             │
              ▼             ▼
         PostgreSQL       Redis
         (primary DB)  (rate-limit / cache)
```

**Backend** — Python 3.11+ / FastAPI with async SQLAlchemy 1.4 ORM (asyncpg driver), Argon2id password hashing, JWT authentication, and SlowAPI rate limiting. Market data from yfinance.

**Frontend** — React 19 (Vite) single-page application. Bloomberg-terminal aesthetic with IBM Plex Mono typography. Page state managed via `App.jsx` (no client-side router).

**Database** — PostgreSQL 15 (TimescaleDB image) with Alembic migrations **0001–0032**. CHECK constraints, CASCADE deletes, composite indexes. Not “12 tables” — that snapshot is obsolete.

**Infrastructure** — Docker Compose with three services (app, db, redis) on a private bridge network. nginx reverse proxy serves the frontend and proxies `/api/v1/` to the backend. Two-stage Dockerfile for deterministic builds.

---

## Features

### Dashboard
- Portfolio selector dropdown with heatmap visualization
- Treemap layout sized by trading volume, coloured by daily % change
- Adaptive text sizing (ticker labels visible on even the smallest tiles)
- Colour gradient legend (-5% to +5%)
- Crypto positions excluded from the heatmap
- "Create Portfolio" prompt when no portfolios exist
- Market status indicator (NYSE open/closed with countdown timer)

### News Aggregation
- Multi-source ingest on a **remote worker** (`server-b-worker/`): Yahoo Finance RSS, Google News RSS, Finviz HTML, MarketWatch RSS
- Ollama LLM scores each article −5…+5 (general + per-ticker) and POSTs to `POST /api/v1/news/internal/news`
- Portfolio-first sorting, category filters, ticker search
- **Not FinBERT** — that classifier is not in this repo

### Portfolio Manager
- Create, rename, and delete custom portfolios
- Add/edit/remove positions with purchase price, quantity, date, and group tags
- CSV bulk import with validation
- Asset type classification (stock, ETF, crypto, commodity, futures)
- Hard stop (broker) vs soft stop (TickerTap warning: Telegram + ntfy, two-stage RTH then EOD)
- Physical commodity type support
- Section-scoped summary statistics
- News action button per position (opens News page filtered to that ticker)

### Advanced Charting
- Interactive candlestick charts (lightweight-charts)
- Multiple timeframes: 1m, 5m, 15m, 1h, 1d, 1wk, 1mo
- Technical indicators: EMA, SMA with configurable periods
- Drawing tools: trend lines, rectangles
- Chart template persistence (save/load configurations per symbol)
- Earnings event markers on bars
- Symbol search navigation
- Real-time quote header

### Trading
- Market orders (immediate execution)
- Limit orders (pending until manual execution)
- Race-condition protection with SELECT ... FOR UPDATE
- Atomic balance/holding mutations
- Position tracking with average cost calculation

### Authentication & Security
- JWT access tokens (configurable expiry) + httpOnly refresh token cookies
- Argon2id password hashing
- Password reset flow via email (SHA-256 hashed tokens)
- 5-minute frontend inactivity auto-logout
- Rate limiting (SlowAPI middleware)
- Security headers (HSTS, CSP, X-Frame-Options, Referrer-Policy)
- Request body size limits (10 MB)
- Structured access logging with path redaction

### Admin
- User lock/unlock
- Account lock/unlock
- Audit log viewer (filterable by user, action, date range)
- Immutable audit trail for all security-sensitive operations

---

## Environment Variables

Create a `.env` file in the project root (or pass variables to Docker Compose). Required variables are marked **REQUIRED**.

| Variable | Default | Description |
|---|---|---|
| `JWT_SECRET` | — | **REQUIRED.** Must be at least 32 characters. The app refuses to start with the default value. |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | JWT lifetime in minutes. |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/tickerTap` | Full async PostgreSQL connection string. |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection string. |
| `ALLOWED_ORIGINS` | `http://localhost:3000,http://localhost:5173` | Comma-separated list of CORS-allowed origins. |
| `ADMIN_EMAILS` | — | Comma-separated email addresses granted admin access. |
| `APP_URL` | `https://ticker-tap.com` | Base URL used in password-reset email links. |
| `SMTP_HOST` | — | SMTP server hostname for email delivery. |
| `SMTP_PORT` | `587` | SMTP port. |
| `SMTP_USER` | — | SMTP username. |
| `SMTP_PASS` | — | SMTP password. |
| `SMTP_FROM` | — | Sender address for system emails. |
| `LOG_LEVEL` | `INFO` | Application log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `VITE_API_URL` | `https://ticker-tap.com` | API base URL injected into the frontend build. |

Generate a secure JWT secret:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Backend Development

### Setup

```bash
cd backend

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set required environment variable
export JWT_SECRET="dev-secret-at-least-32-chars-long-xxxxxx"
export DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/tickerTap"

# Run the API server (auto-reload on file changes)
uvicorn app.main:app --reload --port 8000
```

Interactive API docs are available at `http://localhost:8000/docs`.

### Directory Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app, middleware stack, startup checks
│   ├── auth.py              # JWT utilities, password hashing
│   ├── db.py                # Async engine, session factory, get_db() dependency
│   ├── models.py            # SQLAlchemy ORM models (see alembic 0001–0032)
│   ├── schemas.py           # Pydantic v1 request/response schemas
│   ├── email.py             # Async SMTP email helpers
│   ├── limiter.py           # SlowAPI rate limiter configuration
│   ├── trading/             # arq workers: alerts, scanner, backtests, DeGiro, paper
│   └── routes/              # /api/v1/* — see main.py include_router list
├── alembic/versions/        # 0001 … 0032 (head: soft-stop alert state)
├── tests/
│   ├── test_health.py
│   ├── test_auth.py
│   └── test_orders.py
├── Dockerfile
├── entrypoint.sh
└── requirements.txt
```

---

## Frontend Development

### Setup

```bash
cd frontend

# Install dependencies (including test packages)
npm install --legacy-peer-deps

# Start the development server
npm run dev
# → http://localhost:5173
# API calls are proxied to http://localhost:8000 automatically
```

### Directory Structure

```
frontend/src/
├── App.jsx                    # Root — page state machine, AuthProvider, toasts
├── api/
│   └── client.js              # apiFetch wrapper, typed api object (all endpoints)
├── context/
│   └── AuthContext.jsx         # Auth state, login/logout, inactivity timer, token refresh
├── styles/
│   └── globals.js              # GLOBAL_CSS Bloomberg design system (injected as <style>)
├── components/
│   ├── common/
│   │   ├── Icons.jsx           # SVG icon library (dashboard, charts, news, portfolio, etc.)
│   │   └── index.jsx           # SkeletonRow, ApiError, ToastContainer, Clock,
│   │                           #   Footer, TickerStrip, useMarketStatus
│   ├── charts/
│   │   └── index.jsx           # Sparkline, PortfolioChart, AllocationDonut, Heatmap
│   └── modals/
│       └── TxModal.jsx         # Transaction creation modal
├── pages/
│   ├── auth/                   # LoginPage, RegisterPage, ForgotPasswordPage, ResetPasswordPage
│   ├── DashboardPage.jsx       # Portfolio overview with heatmap and quote grid
│   ├── TransactionsPage.jsx    # Cash deposit/withdrawal history
│   ├── OrdersPage.jsx          # Buy/sell order management
│   ├── ChartsPage.jsx          # Advanced charting with technical indicators
│   ├── NewsPage.jsx            # LLM-scored news feed (−5…+5)
│   ├── PortfolioManagerPage.jsx# Custom portfolio CRUD; soft/hard stops
│   └── ImportPage.jsx          # CSV portfolio import wizard
└── __tests__/
    ├── setup.js                # @testing-library/jest-dom global setup
    └── api.client.test.js      # apiFetch + api object unit tests (12 tests)
```

---

## Running Tests

### Backend (pytest)

Tests use `AsyncMock` to mock the database — no live PostgreSQL is required.

```bash
cd backend

# Run all tests
pytest tests/ -v

# Run a specific suite
pytest tests/test_auth.py -v
pytest tests/test_orders.py -v

# With coverage report
pytest tests/ --cov=app --cov-report=term-missing
```

Or inside Docker:

```bash
docker compose exec app pytest tests/ -v
```

### Frontend (Vitest)

```bash
cd frontend

# Run all tests once
npm test

# Watch mode for active development
npm run test:watch

# Generate coverage report
npm run test:coverage
```

---

## Database Migrations

Migrations are managed with [Alembic](https://alembic.sqlalchemy.org/). The Docker entrypoint runs `alembic upgrade head` automatically on container start.

```bash
# Apply all pending migrations
alembic upgrade head

# Apply in Docker
docker compose exec app alembic upgrade head

# Show current revision
alembic current

# Create a new migration after editing models.py
alembic revision --autogenerate -m "describe your change"

# Roll back the most recent migration
alembic downgrade -1
```

### Migration History

Alembic revisions **0001–0032**. Head: `0032_soft_stop_alert_state`. See `backend/alembic/versions/` — do not treat the old 0001–0008 table as complete.

---

## Security Notes

**JWT** — The application refuses to start if `JWT_SECRET` equals the default placeholder. Access token lifetime defaults to 60 minutes. Refresh tokens are rotated on each use and stored as SHA-256 hashes.

**CORS** — Restricted to explicit origins in `ALLOWED_ORIGINS`. The wildcard `*` is not used.

**Passwords** — Hashed with Argon2id via `argon2-cffi`. Verification is constant-time.

**Rate Limiting** — SlowAPI enforces per-endpoint rate limits (e.g. 5 login attempts/min, 3 registrations/min). Breaches return HTTP 429.

**Security Headers** — Middleware injects HSTS, X-Frame-Options: DENY, Content-Security-Policy, Referrer-Policy, and Permissions-Policy on all responses.

**Inactivity** — The frontend auto-logs-out after 5 minutes of no mouse/keyboard activity.

**Audit Log** — All auth events (register, login, password reset) and financial operations are recorded. Rows are preserved when a user is deleted (`SET NULL` on `user_id`).

**Request Validation** — Request body size capped at 10 MB. Sensitive paths are redacted in access logs.

---

## Contributing

1. Branch `feature/<name>` from a pulled `main`.
2. Make changes and run the relevant tests (`pytest` for backend, `npm test` for frontend).
3. If `models.py` changes, generate a migration: `alembic revision --autogenerate -m "description"`.
4. Verify the UI works manually: `npm run dev` + `uvicorn app.main:app --reload`.
5. Open a pull request targeting `main`. Do not commit secrets, `.env`, or LAN topology.
