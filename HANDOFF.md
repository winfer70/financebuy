# tickerTap HANDOFF — 2026-08-15

## Date
- 2026-08-15

## What Was Accomplished
- **Repo public-safety audit**: verified `winfer70/tickerTap` is safe to make public. `main` diverges from `tradingAI0.1` only with benign cleanup/graphify/merge commits; no leaked secrets were found and no remediation is needed.
- **Production incident postmortem**: investigated same-day logged-in production breakage on labserver (`kamilo`; this repo now runs on labserver, not swiss-knife).
- Root cause: `tickertap_web` (nginx) cached Docker DNS resolution for `proxy_pass http://app:8000`; after `tickertap_app` was recreated on 2026-08-13, nginx kept proxying to stale IP `172.29.0.4` even though the app had moved to `172.29.0.6`, producing connection-refused 502s for proxied API routes while static/SPA pages still loaded.
- Fix already applied on production: `docker exec tickertap_web nginx -s reload` (graceful reload, no container restart required).
- Verification already completed: `https://ticker-tap.com/health` returned 200; previously failing API endpoints returned expected 401 instead of 502; nginx logs showed no new `connect() failed` / 502 entries after reload.

## Current State
- Branch: `tradingAI0.1`
- Repo is confirmed safe for public GitHub publication; no audit remediation follow-up is required.
- Production is currently healthy after the nginx reload.
- Known cosmetic-only follow-up: CSP currently blocks Google Fonts (`style-src 'self' 'unsafe-inline'`), so fonts fall back but functionality is unaffected.
- Structural risk remains: future `tickertap_app` redeploys/recreates can cause the same outage again unless nginx is also reloaded/restarted or the upstream config is changed to re-resolve Docker DNS.

## Exact Next Actions
1. Add an nginx reload step to the labserver deploy/release flow whenever `tickertap_app` or other proxied backend containers are recreated.
2. Prefer a durable nginx hardening fix: use a Docker DNS `resolver` plus variable-based `proxy_pass` so nginx periodically re-resolves `app` instead of caching the container IP for the life of the worker process.
3. Optional cosmetic follow-up: either allowlist `https://fonts.googleapis.com` / related font sources in CSP or self-host the fonts.
4. If/when publishing the repo publicly, proceed normally from `tradingAI0.1`; no secret cleanup is required first.

## Blockers
- No structural nginx/Docker DNS hardening has been implemented yet, so the 502 failure mode can recur on the next backend container recreate.
- CSP font issue is unresolved and awaits prioritization.
