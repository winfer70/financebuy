# Agent Actions — tickerTap

This document lists the edits and CI/agent work performed by the AI assistant. Use it to reproduce, verify, or roll back changes.

---

## Session: 2026-03-04 — Self-Improving Feedback Loop, News Pipeline, Dashboard & Chart Enhancements

### Summary of changes

#### 1. Server B Worker — News Scoring Pipeline (new)

Created the `server-b-worker/` directory with a complete Ollama-based news scoring worker that runs on Server B (REDACTED_HOST, REDACTED):

- **`sources.py`** — RSS/Atom feed aggregator. Fetches articles from configurable financial news sources (Reuters, Bloomberg, MarketWatch, etc.), deduplicates by URL, and returns normalized article dicts.
- **`article_queue.py`** — Local SQLite queue for retry resilience. Articles that fail to POST to Server A are stored locally and retried on subsequent cycles.
- **`worker.py`** — Main scoring worker. Runs on a configurable cycle (default 15 min). Fetches articles via `sources.py`, scores each with Ollama/Llama 3 8B using a structured prompt, POSTs scored articles to Server A's `/api/v1/news/internal/articles` endpoint. Supports dynamic scoring rules fetched from Server A's feedback API.
- **`learner.py`** — Weekly analysis script. Fetches outcome data from Server A, uses Ollama to analyze scoring accuracy patterns, and POSTs new calibration rules back to Server A.
- **`requirements.txt`** — Python dependencies for the worker environment.
- **`tickertap-worker.service`** — systemd unit (Type=simple) for the worker daemon.
- **`tickertap-learner.service`** — systemd unit (Type=oneshot) for the learner script.
- **`tickertap-learner.timer`** — systemd timer triggering the learner weekly (Sunday 02:00).

#### 2. Self-Improving Scoring Feedback Loop (backend)

- **`backend/alembic/versions/0010_score_feedback.py`** — Migration adding `score_outcomes` and `scoring_rules` tables.
- **`backend/app/models.py`** — Added `ScoreOutcome` and `ScoringRule` ORM models.
- **`backend/app/schemas.py`** — Added Pydantic schemas for feedback endpoints.
- **`backend/app/routes/feedback.py`** — New route module with endpoints:
  - `POST /api/v1/feedback/internal/outcomes` — Bulk upsert outcomes from the outcome checker.
  - `GET /api/v1/feedback/internal/outcomes` — Fetch outcomes for learner analysis.
  - `POST /api/v1/feedback/internal/rules` — Create/update scoring rules from learner.
  - `GET /api/v1/feedback/internal/rules/active` — Fetch active rules for worker prompt injection.
  - Background task: outcome checker runs every 6 hours, fetches stock prices via yfinance, compares to scored predictions.
- **`backend/app/main.py`** — Registered the feedback router.

#### 3. News Article Ingestion (backend)

- **`backend/alembic/versions/0009_news_articles.py`** — Migration adding `news_articles` table.
- **`backend/app/routes/news.py`** — Internal article ingestion endpoint (`POST /api/v1/news/internal/articles`) authenticated via `INTERNAL_NEWS_KEY`. Public endpoints for fetching scored articles.
- **`backend/app/models.py`** — Added `NewsArticle` ORM model.
- **`backend/app/schemas.py`** — Added `NewsArticleCreate`, `NewsArticleOut` schemas.
- Removed obsolete `backend/app/news_sources.py` and `backend/app/sentiment.py` (replaced by Server B worker).

#### 4. Docker / Deployment Configuration

- **`docker-compose.prod.yml`**:
  - Added `INTERNAL_NEWS_KEY` environment variable to the `app` service (required for news ingestion and feedback API authentication).
  - Changed port binding from `127.0.0.1:8000:8000` to `0.0.0.0:8000:8000` so the API is accessible from both localhost (nginx reverse proxy) and the LAN (REDACTED_HOST worker/learner).
- **`.env.prod.example`** — Added `INTERNAL_NEWS_KEY` placeholder.
- **`backend/.env.example`** — Updated with news key example.
- **`backend/requirements.txt`** — Added `yfinance` dependency for outcome checker.

#### 5. Dashboard Layout Restructure (frontend)

- **`frontend/src/pages/DashboardPage.jsx`**:
  - Restructured `.grid-main` layout: Portfolio Performance and Top Positions stacked in the left column; Allocation donut in the right 320px sidebar.
  - Top Positions table compacted from 8 columns to 4 (SYMBOL, LAST, CHG, P&L). Removed sparkline, sym-badge, QTY, MKT VALUE, RETURN columns.
- **`frontend/src/styles/globals.js`**:
  - `.grid-main`: Added `align-items: start` to prevent empty space under shorter panels.
  - `.donut-legend`: Changed from flex column to `display: grid; grid-template-columns: 1fr 1fr` for two-column legend layout.
  - `.donut-row`: Compacted gap (8 → 5px) and font-size (11 → 10px).
  - `.donut-sym`: Reduced min-width (40 → 32px).

#### 6. Allocation Donut — Position Consolidation (frontend)

- **`frontend/src/components/charts/index.jsx`** (`AllocationDonut`):
  - Added symbol-grouping logic: duplicate holdings with the same symbol are consolidated (quantities and values summed) before creating donut slices.
  - Removed dollar-value (`$X.XXK`) from legend rows; percentage and symbol only. Dollar values remain visible on hover in the donut center.

#### 7. Portfolio Chart — Future Space & Tooltip Fix (frontend)

- **`frontend/src/components/charts/index.jsx`** (`PortfolioChart`):
  - Data points now map to 80% of chart width (`DATA_W`). The rightmost 20% is empty future space with grid lines continuing through it.
  - Subtle dashed separator line marks where data ends and future zone begins.
  - Hovering in the future zone shows only the crosshair line (no tooltip/circle).
  - Leftmost data point tooltip now anchors to the right of the cursor (`translateX(0)`) instead of centering (`translateX(-50%)`), preventing clipping off the left edge.

#### 8. Stock Chart — Future Space Panning (frontend)

- **`frontend/src/pages/ChartsPage.jsx`** (`StockChart`):
  - Introduced `totalSlots` concept: visible window slots = `zoom.count`, which may exceed actual data bars when panned into the future.
  - `candleGap` uses `totalSlots` instead of `n` (actual data count) for consistent candle-width spacing in the future zone.
  - Drag-to-pan max start extended by 25% of visible count (min 10 bars) past data end, allowing users to pan into empty future space for technical analysis.
  - Wheel zoom respects the same future allowance.
  - Crosshair in the future zone shows the vertical line and price label but suppresses the OHLCV tooltip.

#### 9. News Page Updates (frontend)

- **`frontend/src/pages/NewsPage.jsx`** — Updated to consume articles from the backend API (served by Server B worker) instead of the previous client-side sentiment appREDACTED.
- **`frontend/src/api/client.js`** — Added API methods for news article fetching, feedback endpoints, and chart template CRUD.

---

### Files added

| File | Purpose |
|------|---------|
| `server-b-worker/sources.py` | RSS/Atom feed aggregator for financial news |
| `server-b-worker/article_queue.py` | Local SQLite retry queue for article POST failures |
| `server-b-worker/worker.py` | Ollama scoring worker daemon (15-min cycle) |
| `server-b-worker/learner.py` | Weekly scoring accuracy analyzer + rule generator |
| `server-b-worker/requirements.txt` | Python deps for worker environment |
| `server-b-worker/tickertap-worker.service` | systemd unit for worker daemon |
| `server-b-worker/tickertap-learner.service` | systemd oneshot unit for learner |
| `server-b-worker/tickertap-learner.timer` | systemd weekly timer for learner |
| `backend/alembic/versions/0009_news_articles.py` | Migration: news_articles table |
| `backend/alembic/versions/0010_score_feedback.py` | Migration: score_outcomes + scoring_rules tables |
| `backend/app/routes/feedback.py` | Feedback loop API endpoints + outcome checker |

### Files modified

| File | Changes |
|------|---------|
| `docker-compose.prod.yml` | Added INTERNAL_NEWS_KEY env var; port binding → 0.0.0.0:8000 |
| `.env.prod.example` | Added INTERNAL_NEWS_KEY placeholder |
| `backend/.env.example` | Added INTERNAL_NEWS_KEY placeholder |
| `backend/requirements.txt` | Added yfinance |
| `backend/app/main.py` | Registered feedback router |
| `backend/app/models.py` | Added ScoreOutcome, ScoringRule, NewsArticle models |
| `backend/app/schemas.py` | Added feedback + news schemas |
| `backend/app/routes/news.py` | Internal article ingestion endpoint |
| `frontend/src/api/client.js` | News, feedback, template API methods |
| `frontend/src/pages/DashboardPage.jsx` | Layout restructure (Top Positions under Portfolio Performance) |
| `frontend/src/pages/ChartsPage.jsx` | Future space panning in StockChart |
| `frontend/src/pages/NewsPage.jsx` | Backend-driven article display |
| `frontend/src/components/charts/index.jsx` | Donut consolidation, future space, tooltip fix |
| `frontend/src/styles/globals.js` | Grid alignment, donut legend 2-col, compact rows |

### Files removed

| File | Reason |
|------|--------|
| `backend/app/news_sources.py` | Replaced by server-b-worker/sources.py |
| `backend/app/sentiment.py` | Replaced by Ollama LLM scoring on Server B |

---

### Architecture — Two-Server Setup

```
Server A (REDACTED_HOST, REDACTED)        Server B (REDACTED_HOST, REDACTED)
┌─────────────────────────────┐              ┌──────────────────────────────┐
│  Docker Compose             │              │  systemd services            │
│  ├── FastAPI (port 8000)    │◄── HTTP ────►│  ├── tickertap-worker        │
│  ├── PostgreSQL 15          │              │  │   (15-min scoring cycle)   │
│  └── Redis 7                │              │  ├── tickertap-learner       │
│                             │              │  │   (weekly Sun 02:00)       │
│  nginx (80/443) ──► :8000   │              │  └── Ollama + Llama 3 8B Q4  │
└─────────────────────────────┘              └──────────────────────────────┘
```

### Deployment commands

**Server A — Apply migrations and rebuild:**

```bash
cd /home/REDACTED420/projects/finance/tickerTap
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose -f docker-compose.prod.yml --env-file .env.prod exec app alembic upgrade head
```

**Server B — Deploy worker and learner:**

```bash
# Copy files to REDACTED_HOST
scp -r server-b-worker/ reduser@REDACTED:~/ticker-tap/tickertap-worker/

# On REDACTED_HOST: install deps, enable services
cd ~/ticker-tap/tickertap-worker
pip install -r requirements.txt
sudo cp tickertap-worker.service /etc/systemd/system/
sudo cp tickertap-learner.service /etc/systemd/system/
sudo cp tickertap-learner.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tickertap-worker
sudo systemctl enable --now tickertap-learner.timer
```

**Verify:**

```bash
# Check worker status on REDACTED_HOST
sudo systemctl status tickertap-worker
sudo journalctl -u tickertap-worker --since "10 min ago"

# Check learner timer
sudo systemctl list-timers tickertap-learner.timer

# Check migrations on Server A
docker compose -f docker-compose.prod.yml --env-file .env.prod exec app alembic current
```

---

## Session: 2026-01-09 — CI, Linting, Agent Guidance

### Summary of changes

- Added repository guidance for AI agents: `.github/copilot-instructions.md` — explains architecture, key files, run/test/build commands, and repo-specific patterns.
- Added CI and lint configuration:
  - `.github/workflows/ci.yml` — GitHub Actions workflow with jobs: `lint`, `tests`, `build`, `tests-in-image`.
  - `pyproject.toml` — `black` and `ruff` basic settings.
- Implemented test support:
  - Added `/docker-compose` endpoint to `backend/app/main.py` to satisfy `backend/tests/test_health.py`.
  - Verified `docker compose exec app bash -lc "pytest -q"` runs locally in this environment.
- Created branch and PR work:
  - Branch: `ci/add-workflows-copilot-instructions` (pushed to `origin`).
  - The user merged changes; a tag `v0.1.0` was created and pushed.

### Files added / modified

- `.github/copilot-instructions.md` — guidance for AI coding agents (architecture, patterns, commands).
- `.github/workflows/ci.yml` — CI pipeline for linting, tests (service containers) and image build + tests-in-image job.
- `pyproject.toml` — lint/format config for `ruff` and `black`.
- `backend/app/main.py` — added `/docker-compose` endpoint used by tests.

### Commands to reproduce or verify locally

- Run the app (dev):

```bash
cd backend
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/tickerTap \
  uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- Run services and tests inside container (matches CI `tests-in-image` job):

```bash
docker compose up --build -d
docker compose exec app bash -lc "pytest -q"
docker compose down
```

- Run linters locally:

```bash
pip install ruff black
ruff check .
black --check .
```

- Apply migrations (if models change):

```bash
alembic -c backend/alembic.ini revision --autogenerate -m "describe change"
alembic -c backend/alembic.ini upgrade head
```

### CI notes and troubleshooting

- `pyproject.toml` must be valid TOML for `ruff` to parse. If CI reports a parse error, validate the file formatting locally with `python -m tomllib` or re-open it for corrections.
- The `tests` job in CI uses service containers (Postgres + Redis). The `tests-in-image` job uses `docker compose` to build/run services and execute `pytest` inside the `app` container — this validates the Docker wheel-build path.
- The `gh` CLI was not available in the environment when attempting to open a PR; branch pushes were performed and a PR was created/merged manually by the user.
