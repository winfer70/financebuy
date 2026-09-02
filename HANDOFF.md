# tickerTap HANDOFF — 2026-09-02

## Branch
`feature/insider-monitor-briefings` (off `main` `3c8f937`). Not pushed. Not merged. Do not `release.sh` / do not `docker compose down`.

## Live on labserver
- Alembic **0033** applied. Form 4 poller running: first cycle `fetched=40 new=10 telegram=0 errors=0`.
- `SEC_USER_AGENT=TickerTap secedgar@ticker-tap.com` in host `backend/.env`. Worker was **recreated** (restart does not reload env_file).
- News worker still inserting. `/health` 200.

## Tests
Local venv is Python 3.13. Pins: `pydantic==1.10.22` (ForwardRef), `httpx==0.27.2` (Starlette TestClient). Conftest uses `RATE_LIMIT_STORAGE=memory://`. `pytest tests --ignore=tests/trading` green except live `/health` skipped without db/redis.

## Next
1. Push branch / PR when asked.
2. Do **not** `compose up` news-worker (recreates `tickertap_tickertap_net`).
