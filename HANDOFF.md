# tickerTap HANDOFF — 2026-09-07

## Branch
`feature/insider-monitor-briefings` (off `main`). Not pushed. Do not `release.sh` / do not `docker compose down`.

## Infra note
labserver SSH = **192.168.0.241** (`Host labserver`), not legacy .102.

## Live
1. **Telegram trade date** — trading-worker (bind mount) restarted with updated `insider_briefing.py`.
2. **Form 4 API** — `insider.py`, `main.py`, `models.py` docker-cp’d into `tickertap_app`; healthy. Routes: `GET /api/v1/insider/filings`, `GET /api/v1/insider/owners/{cik}`.

## Local only (frontend rebuild → `tickertap_web`)
- Nav **FORM 4** → `InsiderPage.jsx`
- Charts **SMA PROJ** (OLS on last 50 closes → 30-bar projected SMA)

## Tests
35 insider tests passed (briefing/gate/monitor). Added `test_insider_routes.py`
(6 tests) covering the `/insider/filings` + `/insider/owners/{cik}` API that
had zero coverage — full suite now 230 passed, 1 skipped.

## Next
- Rebuild/redeploy frontend. Push when asked. No compose-up news-worker.
