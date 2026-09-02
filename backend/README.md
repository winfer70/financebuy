# tickerTap Backend

FastAPI backend for the tickerTap stock trading platform. Provides REST API
endpoints for authentication, trading, portfolio management, market data,
news aggregation, and administration.

---

## Quick Start

### With Docker (recommended)

```bash
# From the project root
docker compose up --build -d
docker compose exec app alembic upgrade head
# API available at http://localhost:8000
# Swagger UI at http://localhost:8000/docs
```

### Without Docker

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export JWT_SECRET="dev-secret-at-least-32-chars-long-xxxxxx"
export DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/tickerTap"

uvicorn app.main:app --reload --port 8000
```

---

## Directory Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app, middleware stack, startup checks
│   ├── auth.py              # JWT utilities, Argon2id password hashing
│   ├── db.py                # Async engine, session factory, get_db() dependency
│   ├── models.py            # SQLAlchemy ORM models (alembic 0001–0032)
│   ├── schemas.py           # Pydantic v1 request/response schemas
│   ├── email.py             # Async SMTP email helpers
│   ├── limiter.py           # SlowAPI rate limiter configuration
│   ├── trading/             # arq workers (alerts, scanner, backtests, DeGiro)
│   └── routes/              # /api/v1/* — see main.py
├── alembic/versions/        # 0001 … 0032
├── tests/
│   ├── test_health.py
│   ├── test_auth.py
│   └── test_orders.py
├── Dockerfile               # Two-stage build (wheels → runtime)
├── entrypoint.sh            # Container entrypoint (runs migrations)
└── requirements.txt
```

---

## Tests

Tests use `AsyncMock` to mock the database — no live PostgreSQL required.

```bash
# Run all tests
pytest tests/ -v

# Inside Docker
docker compose exec app pytest tests/ -v

# With coverage
pytest tests/ --cov=app --cov-report=term-missing
```

---

## Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Create a new migration after editing models.py
alembic revision --autogenerate -m "describe your change"

# Roll back the most recent migration
alembic downgrade -1

# Show current revision
alembic current
```

---

## Key Patterns

- **Async DB:** All handlers use `AsyncSession` via `get_db()` dependency. Multi-step operations wrap in `async with db.begin()`.
- **Money:** `Decimal` throughout — `condecimal` in schemas, `Numeric` in models. Positivity validated in endpoints.
- **NaN safety:** yfinance data passes through `_safe_float()` before JSON serialization to handle NaN/Inf values.
- **Pydantic v1:** Uses `orm_mode = True`, `class Config`, and v1 validators. Do not use v2 syntax.
- **Two-stage Docker:** Wheels built in builder stage, installed from `/wheels` for deterministic images.

---

## Security

- **JWT:** App refuses to start if `JWT_SECRET` equals the default placeholder. Access tokens are configurable (default 60 min). Refresh tokens stored as SHA-256 hashes.
- **Passwords:** Argon2id via `argon2-cffi`. Constant-time verification.
- **Rate limiting:** SlowAPI enforces per-endpoint limits (e.g. 5 login attempts/min).
- **Security headers:** HSTS, X-Frame-Options: DENY, CSP, Referrer-Policy, Permissions-Policy.
- **Request limits:** Body size capped at 10 MB. Sensitive paths redacted in access logs.
