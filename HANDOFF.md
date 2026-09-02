# tickerTap HANDOFF — 2026-09-02

## Branch
`feature/insider-monitor-briefings` off `main` @ `3c8f937`. Not merged. Do not `release.sh` / do not `docker compose down`.

## Shipped (code, tests green)
- News worker: `hermes3:8b`, `INTERNAL_NEWS_KEY` fallback, `NEWS_QUEUE_DIR`. Live on labserver as `tickertap_news_worker` (docker run, not compose-up).
- Soft-stop Telegram: last price + % vs stop + 2× volume-leaving + sector ETF + 48h scored news. `market_context.py`.
- Insider monitor: Form 4 atom→XML parse, Alembic **0033** `insider_filings`, GICS sector/integrity gate, Telegram via `notify_soft_stop`. Cron every 5 min on **trading-worker**.

## Tests
`backend\.venv` (not system 3.14): 112 passed (`test_soft_stops`, `test_insider_*`, rules engine, heartbeats) with `--noconftest`. FastAPI conftest still broken on this venv (Pydantic v1 ForwardRef).

## Next
1. Commit/push this branch when asked (if not already).
2. Deploy without stack recreate: copy `backend/app` + `0033` to labserver; `docker exec tickertap_app alembic upgrade head`; restart `tickertap_trading_worker` only.
3. Set `SEC_USER_AGENT` (name + contact email) in gitignored `backend/.env` on labserver or the poller no-ops.
4. Do **not** `compose up` news-worker — it recreates `tickertap_tickertap_net`.
