<!-- Copilot instructions — FinanceBuy -->

Purpose: concise, repo-specific guidance to help AI coding agents be productive quickly.

Big picture
- FastAPI backend in [backend/app](backend/app) using async SQLAlchemy (AsyncSession). Services: Postgres (`db`) and Redis (`redis`) wired by [docker-compose.yml](docker-compose.yml).

Concrete commands
- Dev run (from backend): set `DATABASE_URL` then: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- Container workflow (canonical):
  - `docker compose up --build -d`
  - `docker compose exec app bash -lc "pytest -q"`
  - `docker compose down`
- Migrations:
  - `alembic -c backend/alembic.ini revision --autogenerate -m "msg"`
  - `alembic -c backend/alembic.ini upgrade head`

Key files & examples
- [backend/app/main.py](backend/app/main.py) — app init, routers, `/health` and `/docker-compose` endpoints used by tests.
- [backend/app/db.py](backend/app/db.py) — async engine, `AsyncSessionLocal`, `get_db()` dependency.
- [backend/app/routes/transactions.py](backend/app/routes/transactions.py) — canonical transaction pattern: `async with db.begin()` and Decimal checks.
- [backend/app/schemas.py](backend/app/schemas.py) & [backend/app/models.py](backend/app/models.py) — Pydantic (orm_mode) ↔ SQLAlchemy mappings.
- [backend/tests/test_health.py](backend/tests/test_health.py) — shows test import and expected smoke endpoint.

Project-specific patterns (follow these)
- Use `AsyncSession` + `async with db.begin()` for multi-step DB transactions; avoid mixing sync DB calls into async handlers.
- Monetary values use `pydantic.condecimal` / `decimal.Decimal` and `Numeric` in models; validate positivity in endpoints (see transactions example).
- Tests expect the repo-root layout; prefer running tests inside the `app` container to match CI.

Docker & build notes
- `backend/Dockerfile` is deliberately two-stage: it builds wheels then installs from `/wheels` for reproducible images. Do not change this pattern without coordination.
- `docker-compose.yml` mounts `./backend/app`; in-container tests reflect CI behavior and are the canonical way to validate changes.

CI / PR checklist (practical)
- Run tests: `docker compose exec app bash -lc "pytest -q"` (or mirror this in CI).
- Lint/format: `ruff check .` and `black --check .` (configured in `pyproject.toml`).
- Model changes: add Alembic migration under `backend/alembic/versions` and validate `alembic -c backend/alembic.ini upgrade head`.

When editing dependencies
- Update `backend/requirements.txt`, build the image, and run in-container tests to validate the dependency surface.

If you'd like, I can also:
- add a compact GitHub Actions workflow that runs the containerized tests and builds the `backend` image, or
- expand the migrations / PR checklist section with concrete examples.
<!-- Guidance for AI coding agents working on FinanceBuy -->
# Copilot instructions — FinanceBuy

Purpose: concise, actionable notes to help an AI code assistant be productive in this repo.

**Big Picture**
- **What:** FastAPI backend (async SQLAlchemy) + Postgres + Redis. App lives in `backend/app`.
- **Service boundaries:** `db` (Postgres), `redis`, `app` (FastAPI). See `docker-compose.yml` for wiring.

**Key files & patterns**
- `backend/app/main.py`: router registration and lightweight health endpoints (`/health`, `/docker-compose`).
- `backend/app/db.py`: async SQLAlchemy engine, `AsyncSessionLocal`, and `get_db()` dependency.
- `backend/app/models.py` and `backend/app/schemas.py`: DB models + Pydantic schemas (`orm_mode = True`).
- `backend/app/routes/transactions.py`: canonical example of monetary logic — uses `async with db.begin()` and decimal checks.
- Migrations: `backend/alembic/` (use `alembic -c backend/alembic.ini`).

**Developer workflows (concrete commands)**
- Run locally (dev):
  - `cd backend`
  - `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/financebuy \
    uvicorn app.main:app --host 0.0.0.0 --port 8000`
- Docker-compose (build + tests):
  - `docker compose up --build -d`
  - `docker compose exec app bash -lc "pytest -q"`
  - `docker compose down`
- Tests: `pytest` inside the container mirrors CI; tests add repo root to `PYTHONPATH` so `app` imports work.
- Lint/format: configured in `pyproject.toml` (`ruff`, `black`). Run `ruff check .` and `black --check .`.

**Project-specific conventions**
- Async DB everywhere: prefer `AsyncSession` and `async with db.begin()` for transactional work.
- Money: use `pydantic.condecimal` and `decimal.Decimal` checks server-side (see `transactions.create_transaction`).
- Tests run against FastAPI `TestClient` and expect `/docker-compose` endpoint for a simple smoke check.
- Keep `backend` package importable in tests — tests manipulate `sys.path` (see `backend/tests/test_health.py`).

**Integration points & secrets**
- Postgres: `DATABASE_URL` uses `postgresql+asyncpg://...` in runtime and `docker-compose.yml` for service name `db`.
- Redis: used for caching/coordination; service name `redis` in compose.
- Secrets: read from env; `JWT_SECRET` present in compose as a placeholder — do not hardcode secrets in code.

**When editing code**
- Update models -> create an Alembic autogenerate revision: `alembic -c backend/alembic.ini revision --autogenerate -m "msg"` then `upgrade head`.
- If adding endpoints, also update `backend/tests` with a minimal TestClient check and, when necessary, update CI.

**Files to inspect for examples**
- [backend/app/main.py](backend/app/main.py)
- [backend/app/routes/transactions.py](backend/app/routes/transactions.py)
- [backend/app/db.py](backend/app/db.py)
- [backend/tests/test_health.py](backend/tests/test_health.py)

If anything above is unclear or you want more examples (CI, migrations, or common PR checklist), tell me which section to expand.
# Copilot instructions — FinanceBuy

This repository is a small FastAPI service (backend) with Postgres + Redis and an opinionated container build. The guidance below highlights project-specific patterns, commands, and files an AI coding agent should use to be productive.

- **Big picture**: the API lives in `backend/app` (FastAPI). Database layer is async SQLAlchemy (`backend/app/db.py`) and migrations live under `backend/alembic`. The service is expected to run in Docker via `docker-compose.yml` (services: `db`, `redis`, `app`).

- **Run / build / test (concrete commands)**:
  - Build & run locally with containers: `docker compose up --build`
  - Run the app directly (dev): `uvicorn app.main:app --host 0.0.0.0 --port 8000` (from `backend` with `DATABASE_URL` set)
  - Run tests inside the container: `docker compose exec app bash -lc "pytest -q"`
  - Apply migrations: `alembic -c backend/alembic.ini upgrade head` (run with appropriate `DATABASE_URL`)

- **Container/build notes**: `backend/Dockerfile` builds wheels in a builder stage and installs from `/wheels` for deterministic images. `docker-compose.yml` mounts `./backend/app` into the container as a read-only volume — prefer changing files on the host and rebuilding when modifying dependencies or container image.

- **Auth and secrets**: `backend/app/auth.py` uses Argon2 for password hashing and `python-jose` for JWTs. Secrets are read from env vars: `DATABASE_URL`, `JWT_SECRET`. Defaults are placeholders — do not rely on them for production.

- **Key patterns to follow (examples)**:
  - Async DB sessions: `backend/app/db.py` exposes `AsyncSessionLocal` and `get_db()` (FastAPI dependency). Use `async with db.begin(): ...` for authoritative multi-step DB operations (see `routes/transactions.py`).
  - Pydantic v1 models: `backend/app/schemas.py` uses `orm_mode = True` in response models; return ORM objects after `await db.refresh(obj)` when needed.
  - Money handling: amounts use `condecimal` / `Decimal` in `schemas.py` and `Numeric` in `models.py`. Enforce positive amounts in endpoints (example implemented in `create_transaction`).

- **Files to inspect for context or edits**:
  - `backend/app/main.py` — app initialization and router registration
  - `backend/app/db.py` — async engine, sessionmaker, `get_db()` dependency
  - `backend/app/models.py` and `backend/app/schemas.py` — DB model / API schema mapping
  - `backend/app/routes/transactions.py` — canonical transaction pattern (explicit DB transaction + refresh)
  - `backend/app/auth.py` — hashing + JWT helpers
  - `backend/Dockerfile`, `docker-compose.yml`, `backend/requirements.txt`

- **Developer expectations / constraints**:
  - Keep changes minimal and focused — the Dockerfile and wheel-build are deliberate for reproducible images.
  - Follow existing async patterns (do not mix sync DB calls into async handlers).
  - Use the `get_db()` dependency rather than creating ad-hoc sessions.

- **When adding features or fixing bugs**:
  - Update `backend/requirements.txt` for new runtime deps and rebuild the image (follow the two-stage Dockerfile flow).
  - If altering DB models, create an Alembic migration under `backend/alembic/versions` and run migrations against the proper `DATABASE_URL`.

---

**CI / PR Guidance (recommended checks)**

- **Quick checklist for PRs**:
  - Run unit tests: `pytest -q` (inside container via `docker compose exec app bash -lc "pytest -q"`).
  - Run linting / formatting (add tooling if needed). Prefer `ruff`/`black` for Python — if not yet present, iterate with the maintainer before adding.
  - Confirm container builds: `docker compose build --no-cache --pull app` and ensure `uvicorn` start succeeds.
  - If DB model changes, include an Alembic migration under `backend/alembic/versions` and demonstrate `alembic -c backend/alembic.ini upgrade head` runs against a test DB.

- **Suggested GitHub Actions snippets**:
  - Job to run tests/build:

    - Checkout + set up Python 3.11
    - Build service containers (optional) or run tests inside an official Python runner
    - Run `pytest -q`
    - Build `backend` image with Docker and fail on build errors

- **Container image validation**:
  - Build with the two-stage `backend/Dockerfile` to validate wheel build step.
  - Prefer `--no-cache` in CI to detect missing wheel dependencies.

**Examples / Recipes**

- **Apply DB migration locally**:

  1. Ensure `DATABASE_URL` points to a dev Postgres instance (or use the docker-compose DB).
  2. Create migration (if changing models):

     ```bash
     alembic -c backend/alembic.ini revision --autogenerate -m "describe change"
     alembic -c backend/alembic.ini upgrade head
     ```

  3. Run the app or tests to validate schema changes.

- **Quick curl example (health & create transaction)**:

  - Health check:

    ```bash
    curl -sS http://localhost:8000/health
    ```

  - Create transaction (replace UUIDs and adjust `DATABASE_URL` / server origin):

    ```bash
    curl -X POST http://localhost:8000/transactions/create \
      -H "Content-Type: application/json" \
      -d '{"account_id":"11111111-1111-1111-1111-111111111111","transaction_type":"deposit","amount":"100.00","currency":"USD"}'
    ```

**Notes and constraints**

- Do not change the two-stage Dockerfile pattern without coordination; it intentionally prebuilds wheels for deterministic images.
- Keep async DB usage consistent; prefer `AsyncSession` + dependency `get_db()` rather than creating new sync sessions.

If you'd like, I can add a ready-to-use GitHub Actions workflow file that runs tests and builds the `backend` image — would you like that created next?

