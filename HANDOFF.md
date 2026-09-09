# tickerTap HANDOFF — 2026-09-09

## Branch
`feature/insider-monitor-briefings` (off `main`, pushed to origin). PR open into `tradingAI0.1`. Do not `release.sh` / do not `docker compose down` (network-subnet mismatch in `docker-compose.labserver.yml` breaks a full `up`/`build` — see Known Issues).

## Infra
Prod is **labserver** (192.168.0.241), Docker Compose + Cloudflare Tunnel as sole ingress (no host nginx, no published ports). Checkout at `/home/kamilo/tickerTap/`.

## Shipped this session (all live on labserver, all tested)
- **News fix**: targeted per-ticker search + 2h cooldown rotation in `server-b-worker/worker.py`, ordered-by-recency watch list in `feedback.py::get_watch_tickers()` — fixes the "0 articles scored" bug.
- **6 new SEC filing types** ingested via SEC EDGAR (beyond the existing Form 4 pipeline): Form 144 (planned sales), Form 3 (initial ownership), Schedule 13D/13G (>5% beneficial ownership), Form 8-K (material events), Form 13F-HR (institutional holdings via OpenFIGI CUSIP resolution). Plus FINRA biweekly short interest (flat-file CDN, not the paid Query API). All pollers run in `trading-worker` (arq `arq:trading`, has bind mounts) — see `TICKERTAP_SUMMARY.md` for cron schedule and module list.
- **Watchlist parity**: watchlist tickers now get full gating parity with portfolio positions everywhere in the insider pipeline (`book_loader.py` extracted from `insider_monitor.py` to break a circular import; `BookSnapshot.watchlist_tickers` OR'd into every held-ticker check).
- **Form 144 promoted to a standalone "planned sell" alert** — previously context-only, now fires `notify_soft_stop(event_type="planned_sell")` to anyone holding or watching the ticker.
- **New unified API**: `GET /insider/filings-all` normalizes all 6 non-Form-4-transaction sources into one sortable/filterable/paginated response (`source`, `ticker`, `days`, `sort`, `order`, `limit`, `offset` params).
- **New frontend**: `InsiderPage.jsx` gained a FORM 4 / ALL FILINGS tab switcher with source-colored pills, and the person-breakdown panel gained SHORT INTEREST and PENDING FORM 144 boxes.
- **Docs**: `HANDOFF.md` (this file), `TICKERTAP_SUMMARY.md` (rewritten as the low-level architecture reference, Alembic head corrected 0032→0041), `NEWS_RESEARCH.md` (shipped-fix note added), `README.md` Features section, `OnboardingTutorial.jsx` FORM 4 step — all updated to reflect the above.

## Tests
458 passed, 1 skipped (full backend suite). All new filing-type parsers verified against real live EDGAR/OpenFIGI/FINRA data before coding, not just fixture-derived.

## Known Issues (unchanged, not touched this session)
- `docker-compose.labserver.yml` declares network subnet `10.51.0.0/16`; the live network is actually `172.29.0.0/16`. Breaks `docker compose up`/`build` directly — use the manual `docker run --network tickertap_tickertap_net --network-alias <service>` + `docker cp` workaround (see `TICKERTAP_SUMMARY.md` Deployment section).
- `TELEGRAM_BOT_USERNAME` env var still unset on labserver — register page's clickable bot link is inert until set.
- Stale duplicate checkout at `Desktop/Finances and shit/tickerTap` with 26 never-pushed local commits — not investigated, left alone.

## Next
- Review/merge the open PR into `tradingAI0.1` (31 commits, all live in prod already but not merged).
- No compose-up of the whole stack — labserver's subnet mismatch will break it.
