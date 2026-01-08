# FastAPI Starter — FinanceBuy

Minimal starter demonstrating secure patterns: async DB, explicit transactions, Argon2 password hashing, and container build.

Run locally (requires Docker) via docker-compose, or set `DATABASE_URL` and run Uvicorn.

Quick start (local with PostgreSQL):

1. Copy `.env.example` to `.env` and set `DATABASE_URL`.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run app:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Security notes:
- Secrets are read from environment at runtime.
- Use an external secrets manager in production and grant least-privilege access to instances.
- Tokens are short-lived; refresh token rotation and revocation must be implemented in production.
