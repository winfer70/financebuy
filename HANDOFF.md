# tickerTap HANDOFF — 2026-09-02

## Date
- 2026-09-02

## What shipped
- Two-stage soft-stop alerts: Telegram + ntfy retry, in-app notification. Never auto-clears `soft_stop_loss`. Immediate check when a newly saved level is already through last price.
- Alembic **0032** (`soft_stop_intraday_on`, `soft_stop_eod_on`, `soft_stop_delivery_json`).
- `POST /positions` persist bug: `add_position` now `db.add` / commit / refresh / return (was falling off the handler → 500).
- Docs pass: FinBERT / 12-table / 8-migration snapshots removed; no hostnames, LAN IPs, or secret values in tracked files.

## Current state
- Canonical branch: **`main`** (kept in sync with `tradingAI0.1` for `release.sh`).
- Alembic head: **0032**.
- News scoring: remote Ollama worker (`server-b-worker/`) POSTs to `POST /api/v1/news/internal/news`. Not FinBERT.
- Volume-flow Phase 4 auto-scores **3/7** factors (max 15). The /35 rubric is a UI checklist, not enforced in code.
- `volume_flow_scanner.py` was never in this repo. Scanner lives in `backend/app/trading/scanner_worker.py`.

## Next
1. New features: `git checkout main && git pull && git checkout -b feature/<name>`.
2. Do **not** run `release.sh` unless you intend a production deploy. It still `docker compose down`s the stack (nginx Docker-DNS 502 unless you reload `tickertap_web` after recreate).
3. Prefer `docker compose --env-file .env.prod -f docker-compose.labserver.yml` recreate of `app` then `web`, then `nginx -s reload` — never a full `down` on prod.

## Do not put in git
Secrets live only in gitignored `.env` / `.env.prod`. Placeholders only in `backend/.env.example` and `.env.prod.example`.
