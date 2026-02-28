# TickerTap — Full-Stack Stock Trading Platform

A Bloomberg-terminal-inspired trading platform with a FastAPI backend and a React frontend.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Architecture Overview](#architecture-overview)
3. [Environment Variables](#environment-variables)
4. [Backend Development](#backend-development)
5. [Frontend Development](#frontend-development)
6. [Running Tests](#running-tests)
7. [Database Migrations](#database-migrations)
8. [Security Notes](#security-notes)
9. [Project Structure](#project-structure)

---

## Quick Start

The fastest way to run the full stack is with Docker Compose:

```bash
# 1. Copy and fill in the required environment variables
cp .env.example .env
# Edit .env — at minimum set JWT_SECRET and SMTP credentials

# 2. Start all services (PostgreSQL, Redis, backend API, frontend)
docker compose up --build

# 3. Apply database migrations
docker compose exec backend alembic upgrade head

# Frontend available at: http://localhost:3000
# Backend API available at: http://localhost:8000
# API docs (Swagger UI): http://localhost:8000/docs
```

---

## Architecture Overview

```
Browser (React SPA)
       │
       │  HTTPS / JSON
       ▼
   nginx (port 443/80)
       │
   ┌───┴─────────────┐
   │                 │
   ▼                 ▼
Frontend          Backend
(Vite SPA)       (FastAPI)
port 3000        port 8000
                     │
              ┌──────┴──────┐
              │             │
              ▼             ▼
         PostgreSQL       Redis
         (primary DB)  (rate-limit / cache)
```

**Backend** — Python 3.11+ / FastAPI with async SQLAlchemy ORM, argon2 password hashing, and JWT authentication.

**Frontend** — React 19 (Vite) single-page application. Bloomberg-terminal aesthetic with IBM Plex Mono typography. Modular component architecture with React Context for auth state.

**Database** — PostgreSQL 15 with Alembic migrations. Schema enforces CHECK constraints, CASCADE deletes, and composite indexes on hot query paths.

---

## Environment Variables

Create a `.env` file in the project root (or pass variables to Docker Compose). Required variables are marked **REQUIRED**.

| Variable | Default | Description |
|---|---|---|
| `JWT_SECRET` | — | **REQUIRED.** Must be at least 32 characters. The app refuses to start with the default value. |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | JWT lifetime in minutes. |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/tickerTap` | Full async PostgreSQL connection string. |
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
│   ├── main.py            # FastAPI app, middleware, startup checks
│   ├── auth.py            # JWT utilities, password hashing, startup validation
│   ├── db.py              # Database engine and session factory
│   ├── models.py          # SQLAlchemy ORM models
│   ├── schemas.py         # Pydantic request/response schemas
│   ├── email.py           # SMTP email helpers
│   ├── dependencies.py    # Re-exports get_current_user, get_current_admin
│   └── routes/
│       ├── auth_routes.py # /auth/* endpoints + get_current_user dependency
│       ├── accounts.py    # /accounts/*
│       ├── transactions.py# /transactions/*
│       ├── holdings.py    # /holdings/*
│       ├── orders.py      # /orders/*
│       ├── portfolio.py   # /portfolio/*
│       ├── market.py      # /market/*
│       └── admin.py       # /admin/*
├── alembic/
│   └── versions/
│       ├── 0001_initial.py
│       ├── 0002_password_reset_tokens.py
│       └── 0003_integrity_fixes.py
├── tests/
│   ├── test_health.py
│   ├── test_auth.py
│   └── test_orders.py
└── requirements.txt
```

---

## Frontend Development

### Setup

```bash
cd frontend

# Install dependencies (including test packages)
npm install

# Start the development server
npm run dev
# → http://localhost:5173
# API calls are proxied to http://localhost:8000 automatically
```

### Directory Structure

```
frontend/src/
├── App.jsx                    # Root — routing, AuthProvider, toasts
├── api/
│   └── client.js              # apiFetch, typed api object, useApi hook
├── context/
│   └── AuthContext.jsx        # Auth state, login/logout, inactivity timer
├── styles/
│   └── globals.js             # GLOBAL_CSS design system + mock data
├── components/
│   ├── common/
│   │   ├── Icons.jsx          # SVG icon library
│   │   └── index.jsx          # SkeletonRow, ApiError, ToastContainer,
│   │                          #   Clock, Footer, TickerStrip, useMarketStatus
│   ├── charts/
│   │   └── index.jsx          # Sparkline, PortfolioChart, AllocationDonut
│   └── modals/
│       └── TxModal.jsx        # Transaction creation modal
├── pages/
│   ├── auth/                  # Login, Register, ForgotPassword, ResetPassword
│   ├── DashboardPage.jsx
│   ├── TransactionsPage.jsx
│   ├── HoldingsPage.jsx
│   ├── OrdersPage.jsx
│   ├── ChartsPage.jsx
│   └── ImportPage.jsx
└── __tests__/
    ├── setup.js               # @testing-library/jest-dom global setup
    └── api.client.test.js     # apiFetch + useApi unit tests
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
docker compose exec backend pytest tests/ -v
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

Migrations are managed with [Alembic](https://alembic.sqlalchemy.org/).

```bash
# Apply all pending migrations
alembic upgrade head

# Apply in Docker
docker compose exec backend alembic upgrade head

# Show current revision
alembic current

# Create a new migration after editing models.py
alembic revision --autogenerate -m "describe your change"

# Roll back the most recent migration
alembic downgrade -1
```

### Migration History

| Revision | Description |
|---|---|
| `0001_initial` | Core schema — users, accounts, transactions, securities, holdings, orders, audit_log |
| `0002_password_reset_tokens` | Password reset token table with CASCADE delete on user_id |
| `0003_integrity_fixes` | Fix malformed server_defaults, add CHECK constraints, CASCADE/RESTRICT deletes, composite indexes |

---

## Security Notes

**JWT** — The application refuses to start if `JWT_SECRET` equals the default placeholder `please-change-me`. Token lifetime defaults to 60 minutes (was previously 24 hours).

**CORS** — Restricted to explicit origins in `ALLOWED_ORIGINS`. The wildcard `*` is not used.

**Passwords** — Hashed with argon2id via `argon2-cffi`. Verification is constant-time.

**Inactivity** — The frontend auto-logs-out after 5 minutes of no mouse/keyboard activity.

**Audit log** — All auth events (register, login, password reset) are recorded. Rows are preserved when a user is deleted (`SET NULL` on `user_id`), ensuring the audit trail is never silently dropped.

**Email** — SMTP failures during password-reset are logged at ERROR level and do not leak error details to the client.

---

## Contributing

1. Branch from `main`.
2. Make changes and run the relevant tests (`pytest` for backend, `npm test` for frontend).
3. If `models.py` changes, generate a migration: `alembic revision --autogenerate -m "description"`.
4. Verify the UI works manually: `npm run dev` + `uvicorn app.main:app --reload`.
5. Open a pull request with a clear description of what changed and why.
