# tickerTap HANDOFF — 2026-09-03

## Branch
`feature/insider-monitor-briefings` (off `main`). Not pushed. Do not `release.sh` / do not `docker compose down`.

## Live
- Alembic **0034** applied (`shares_after`, `stake_pct`, owner-history index).
- Insider Telegram redesigned: 10b5-1 (`aff10b5One`), stake %, 12mo owner pattern from ingested filings, your BEP/stop, LOW/MED/HIGH concern, article-count news digest, consensus best-effort via yfinance.
- News scoring is enough for Telegram (title + score + BULL/BEAR); empty vs query-error distinguished.
- Trading + alert workers healthy after deploy.

## Next
Push when asked. Do not compose-up news-worker.
