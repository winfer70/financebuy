# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TickerTap is a Bloomberg-terminal-inspired stock trading platform. FastAPI async backend + React 19 SPA frontend, backed by PostgreSQL 15 and Redis 7, orchestrated via Docker Compose on a private bridge network.

### Request Flow
```
React SPA → apiFetch() → nginx (prod) or Vite proxy (dev) → FastAPI /api/v1/* → SQLAlchemy async → PostgreSQL
```

## Development Commands

### Full stack (Docker — canonical workflow)
```bash
docker compose up --build
docker compose exec backend alembic upgrade head
docker compose down
```

### Backend (local dev)
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export JWT_SECRET="dev-secret-at-least-32-chars-long-xxxxxx"
export DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/tickerTap"
uvicorn app.main:app --reload --port 8000
# API docs: http://localhost:8000/docs
```

### Frontend (local dev)
```bash
cd frontend
npm install
npm run dev          # http://localhost:5173, proxies /api to :8000
npm run build        # Production build to dist/
```

## Testing

### Backend (pytest)
Tests use `AsyncMock` — no live Postgres required.
```bash
cd backend
pytest tests/ -v                                    # all tests
pytest tests/test_auth.py -v                        # single file
pytest tests/ --cov=app --cov-report=term-missing   # coverage
```
In Docker: `docker compose exec backend pytest tests/ -v`

### Frontend (Vitest with jsdom)
```bash
cd frontend
npm test                 # single run
npm run test:watch       # watch mode
npm run test:coverage    # coverage (thresholds: 70% lines/functions/statements, 60% branches)
```

## Linting & Formatting

### Backend (Python)
Configured in `pyproject.toml`. Ruff extends: E, F, W, C90, I (isort), B (bugbear), UP (pyupgrade). Line length 88.
```bash
ruff check .             # lint
ruff check . --fix       # auto-fix
black --check .          # format check
black .                  # format
```
Pre-commit hooks (Ruff + Black) configured in `.pre-commit-config.yaml`.

### Frontend (JavaScript)
```bash
cd frontend
npm run lint
```

## Database Migrations (Alembic)
```bash
cd backend
alembic upgrade head                                # apply all pending
alembic revision --autogenerate -m "description"    # new migration after models.py changes
alembic downgrade -1                                # rollback last
alembic current                                     # show current revision
```
In Docker: `docker compose exec backend alembic upgrade head`

## Architecture

```
nginx (reverse proxy)
  ├── Frontend (React 19 SPA, Vite) — port 3000/5173
  └── Backend (FastAPI) — port 8000, binds 127.0.0.1 only
        ├── PostgreSQL 15 — port 5432 (private network only)
        └── Redis 7 — port 6379 (private network only)
```

All business API routes live under `/api/v1`. The `/health` endpoint is unversioned.

### Backend layering (`backend/app/`)
- **`main.py`** — FastAPI app creation, middleware stack (rate limit → CORS → security headers → body size → request logging), startup validation (JWT_SECRET check, DB connection)
- **`routes/`** — 11 route modules mounted under `/api/v1`. Each uses `Depends()` for DB sessions and auth. Key routes: `auth_routes.py` (register/login/refresh/password-reset), `orders.py` (buy/sell with position tracking), `market.py` (yfinance price lookups)
- **`models.py`** — SQLAlchemy ORM models. UUIDs as PKs. Decimal precision for financial amounts. CHECK constraints on balance/amount/quantity
- **`schemas.py`** — Pydantic v1 request/response validation (`orm_mode = True`, `condecimal`). EmailStr for emails, field limits enforce business rules
- **`auth.py`** — JWT creation/verification (python-jose), Argon2id password hashing, `get_current_user`/`get_current_admin` dependencies
- **`db.py`** — Async engine + session factory (asyncpg), `get_db()` FastAPI dependency

### Frontend structure (`frontend/src/`)
- **`api/client.js`** — Centralized HTTP layer. `apiFetch()` handles token injection, 401 refresh, error normalization. `useApi()` hook for components
- **`context/AuthContext.jsx`** — Single auth state source. Token storage, login/logout, 5-minute inactivity auto-logout, session expiry tracking
- **`styles/globals.js`** — Design system as JS objects (Bloomberg terminal aesthetic, IBM Plex Mono). Injected as `<style>` in `main.jsx`
- **`pages/`** — One component per route. No client-side router library; `App.jsx` manages page state directly
- **`components/common/index.jsx`** — Shared UI: SkeletonRow, ApiError, ToastContainer, Clock, Footer, TickerStrip

### Database schema (11 tables)
Core entities: `users` → `accounts` → `transactions`, `holdings`, `orders`. Supporting: `securities`, `audit_log`, `password_reset_tokens`, `refresh_tokens`, `portfolio_managers`, `chart_templates`. Foreign keys use CASCADE on user deletion for owned data, SET NULL on audit_log to preserve trails.

### Middleware stack (order matters)
SlowAPI rate limiter → CORSMiddleware → SecurityHeadersMiddleware (HSTS, X-Frame-Options DENY) → RequestBodySizeMiddleware (10MB) → RequestLoggingMiddleware (redacts passwords/tokens)

## Key Conventions

- **Async DB everywhere** — use `AsyncSession` via `get_db()` dependency. Wrap multi-step operations in `async with db.begin():` for atomic transactions. Canonical example: `backend/app/routes/transactions.py`
- **Financial precision** — `decimal.Decimal` in Python, `condecimal` in Pydantic, `Numeric(18,2)` in models. Never use `float` for money. DB enforces `CHECK(balance >= 0)` on accounts
- **Auth dependencies** — inject via `Depends(get_current_user)` or `Depends(get_current_admin)`. Admin role determined by `ADMIN_EMAILS` env var
- **Market data** — `yfinance` library with TTL caching (3s during market hours, 5 min when closed) in `backend/app/routes/market.py`
- **Rate limiting** — SlowAPI middleware: 5 login attempts/min, 3 registrations/min
- **Frontend styling** — inline style objects from `globals.js`, no CSS files
- **Test isolation** — backend tests mock DB with `AsyncMock`, frontend tests use jsdom + @testing-library/react
- **Pydantic v1** — the project uses Pydantic v1 (`orm_mode = True`, `condecimal`, etc.), not v2
- **Two-stage Dockerfile** — `backend/Dockerfile` builds wheels in a builder stage, installs from `/wheels` in runtime stage. Do not change this pattern without coordination
- **Environment gating** — production disables Swagger docs, rejects `LOG_LEVEL=DEBUG`, requires real JWT_SECRET

## Environment Variables

Required: `JWT_SECRET` (>=32 chars, app refuses to start with default placeholder), `DATABASE_URL` (async connection string).

Optional: `ALLOWED_ORIGINS` (CORS), `ADMIN_EMAILS`, `SMTP_*` (email), `APP_URL`, `LOG_LEVEL`, `VITE_API_URL`.

## CI

GitHub Actions (`.github/workflows/ci.yml`): lint job (ruff + black), test job (Postgres + Redis service containers, pytest), matrix tests (Python 3.10 & 3.11), Docker image build, and in-container test run.

## When Making Changes

- **New endpoints**: Add route module in `backend/app/routes/`, register in `main.py`, add tests in `backend/tests/`
- **Model changes**: Update `models.py`, create Alembic migration, run `alembic upgrade head`
- **New dependencies**: Update `backend/requirements.txt`, rebuild Docker image, run in-container tests
- **PR checklist**: Tests pass (`pytest -q`), lint clean (`ruff check . && black --check .`), migrations apply cleanly
