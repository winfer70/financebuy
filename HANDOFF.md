# tickerTap HANDOFF — 2026-09-03

## Branch
`feature/insider-monitor-briefings` (off `main`). Not pushed. Do not `release.sh` / do not `docker compose down`.

## Live
- Form 4 poller ingesting. `SEC_USER_AGENT` set.
- Telegram briefs now include an **Advice** block from `investment_rules.json` (no LLM): don't chase, watchlist tier, vol class, sector cap room, no averaging down, FOMO checklist. Soft-stop + insider.
- Alert-worker restart crash (alembic 0033 missing in image) fixed by docker-cp of 0033. Compose now has `SKIP_MIGRATIONS=1` on alert-worker (takes effect on next recreate).

## Next
Push when asked. Do not compose-up news-worker.
