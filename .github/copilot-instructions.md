<!-- Copilot instructions — tickerTap -->
# Copilot Instructions — tickerTap

Concise, repo-specific guidance for AI coding agents working in this codebase.

---

## Big Picture

**What:** Full-stack stock trading platform — FastAPI backend, React 19 frontend, PostgreSQL, Redis.

**Architecture:**

```
Browser (React 19 SPA)
       │  HTTPS / JSON
       ▼
   nginx (443/80)
       │
   ┌───┴─────────────┐
   │                 │
   ▼                 ▼
Frontend          Backend
(Vite /dist)     (FastAPI :8000)
                     │
              ┌──────┴──────┐
              │             │
              ▼             ▼
         PostgreSQL       Redis
```

**Services** (via `docker-compose.yml`): `app` (FastAPI), `db` (PostgreSQL 15), `redis`.

---

## Backend

**Stack:** Python 3.11+ / FastAPI / async SQLAlchemy 1.4 (asyncpg) / Pydantic v1 / Alembic / Argon2id / JWT / SlowAPI.

### Key Files

| File | Purpose |
|------|---------|
| `backend/app/main.py` | App init, middleware stack, router registration, `/health` endpoint |
| `backend/app/db.py` | Async engine, `AsyncSessionLocal`, `get_db()` dependency |
| `backend/app/models.py` | 12 SQLAlchemy ORM models |
| `backend/app/schemas.py` | Pydantic v1 schemas (`orm_mode = True`) |
| `backend/app/auth.py` | Argon2 hashing, JWT creation/verification |
| `backend/app/email.py` | Async SMTP helpers for password reset |
| `backend/app/limiter.py` | SlowAPI rate limiter configuration |
| `backend/app/news_sources.py` | Multi-source RSS/HTML news aggregation |
| `backend/app/sentiment.py` | FinBERT sentiment classification singleton |

### Route Modules

| Module | Prefix | Purpose |
|--------|--------|---------|
| `routes/auth_routes.py` | `/auth` | Register, login, refresh, logout, password reset |
| `routes/accounts.py` | `/accounts` | Account CRUD |
| `routes/transactions.py` | `/transactions` | Cash deposits/withdrawals |
| `routes/holdings.py` | `/holdings` | Raw holdings with pagination |
| `routes/orders.py` | `/orders` | Market/limit order placement, execution, cancellation |
| `routes/portfolio.py` | `/portfolio` | Cross-account positions and summary |
| `routes/portfolio_manager.py` | `/portfolio-manager` | Custom portfolio CRUD, CSV import, position sell |
| `routes/market.py` | `/market` | Quotes, OHLCV, SMA, search (yfinance) |
| `routes/news.py` | `/news` | Aggregated feed with FinBERT sentiment |
| `routes/chart_templates.py` | `/chart-templates` | Saved chart configurations |
| `routes/admin.py` | `/admin` | User/account mgmt, audit logs |

### Patterns to Follow

- **Async DB everywhere:** Use `AsyncSession` + `async with db.begin()` for transactional work.
- **Money:** `condecimal` / `Decimal` in schemas, `Numeric` in models. Validate positivity in endpoints.
- **NaN safety:** yfinance data passes through `_safe_float()` (in `market.py`) before JSON serialization.
- **Pydantic v1:** This project uses Pydantic v1 conventions (`orm_mode`, `class Config`, etc.). Do not use v2 syntax.

### Commands

```bash
# Dev run (from backend/)
export JWT_SECRET="dev-secret-at-least-32-chars-long-xxxxxx"
export DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/tickerTap"
uvicorn app.main:app --reload --port 8000

# Docker workflow (canonical)
docker compose up --build -d
docker compose exec app bash -lc "pytest -q"
docker compose down

# Migrations
alembic -c backend/alembic.ini revision --autogenerate -m "msg"
alembic -c backend/alembic.ini upgrade head

# Lint/format
ruff check .
black --check .
```

---

## Frontend

**Stack:** React 19 / Vite / lightweight-charts / IBM Plex Mono / Bloomberg-terminal aesthetic.

### Key Files

| File | Purpose |
|------|---------|
| `frontend/src/App.jsx` | Root component, page state machine, AuthProvider, toasts |
| `frontend/src/api/client.js` | `apiFetch` wrapper, typed `api` object (all endpoints) |
| `frontend/src/context/AuthContext.jsx` | Auth state, login/logout, inactivity timer, token refresh |
| `frontend/src/styles/globals.js` | `GLOBAL_CSS` design system (injected as `<style>`) |
| `frontend/src/components/common/index.jsx` | SkeletonRow, ApiError, ToastContainer, Clock, Footer, TickerStrip |
| `frontend/src/components/common/Icons.jsx` | SVG icon library |
| `frontend/src/components/charts/index.jsx` | Sparkline, PortfolioChart, AllocationDonut, Heatmap |

### Pages

| Page | File |
|------|------|
| Dashboard | `pages/DashboardPage.jsx` |
| Orders | `pages/OrdersPage.jsx` |
| Transactions | `pages/TransactionsPage.jsx` |
| Charts | `pages/ChartsPage.jsx` |
| News | `pages/NewsPage.jsx` |
| Portfolio Manager | `pages/PortfolioManagerPage.jsx` |
| CSV Import | `pages/ImportPage.jsx` |
| Auth | `pages/auth/` (Login, Register, ForgotPassword, ResetPassword) |

### Patterns to Follow

- **No client-side router.** Page state is managed via `App.jsx` (string-based state machine).
- **API calls** go through `api/client.js` — never use raw `fetch` directly.
- **Bloomberg aesthetic:** IBM Plex Mono, dark background (#0a0a0a), green/amber/red accents.
- **Install dependencies** with `npm install --legacy-peer-deps` (peer-dep conflicts with React 19).

### Commands

```bash
cd frontend
npm install --legacy-peer-deps
npm run dev          # → http://localhost:5173 (proxied to :8000)
npm test             # Vitest
npm run test:watch   # Watch mode
npx vite build       # Production build → dist/
```

---

## Database

**Engine:** PostgreSQL 15 with Alembic migrations.

**Schema:** 12 tables — users, accounts, transactions, securities, holdings, orders, audit_log, password_reset_tokens, refresh_tokens, portfolios, portfolio_positions, chart_templates.

**Migration files:** `backend/alembic/versions/0001_initial.py` through `0008_chart_templates.py`.

When editing `models.py`:
1. Create migration: `alembic -c backend/alembic.ini revision --autogenerate -m "describe change"`
2. Apply: `alembic -c backend/alembic.ini upgrade head`
3. Validate with tests.

---

## Docker & Build

- `backend/Dockerfile` is two-stage: builds wheels in a builder stage, installs from `/wheels` for deterministic images. Do not change this pattern.
- `docker-compose.yml` mounts `./backend/app` as read-only into the container. Code changes on the host are picked up after `docker compose restart app` (no rebuild needed for Python changes).
- Frontend is built separately (`npx vite build`) and served by nginx from `frontend/dist/`.

---

## Secrets & Environment

- `JWT_SECRET` — required, min 32 chars. App refuses to start with default.
- `DATABASE_URL` — async PostgreSQL connection string (`postgresql+asyncpg://...`).
- `REDIS_URL` — Redis connection string.
- `ADMIN_EMAILS` — comma-separated admin email addresses.
- `SMTP_*` — SMTP credentials for password reset emails.
- `VITE_API_URL` — API base URL injected into frontend build.

Never hardcode secrets. Read from environment variables only.

---

## PR Checklist

1. Run backend tests: `docker compose exec app bash -lc "pytest -q"`
2. Run frontend tests: `cd frontend && npm test`
3. Lint: `ruff check .` and `black --check .`
4. If models changed: include Alembic migration, verify `alembic upgrade head`
5. If frontend changed: verify `npx vite build` succeeds
6. Container builds: `docker compose build --no-cache app`
