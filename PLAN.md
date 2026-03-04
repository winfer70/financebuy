# PLAN: Background News Pipeline with LLM Scoring

## Overview

Replace the current live-fetch-and-score news system with a two-server architecture:

- **Server A (app server)** — Stores and serves pre-scored articles from PostgreSQL. No LLM, no live RSS fetching on request.
- **Server B (REDACTED, i5/16GB)** — Runs Ollama + Llama 3 8B Q4. A worker script fetches news, scores with the LLM, and posts results to Server A via HTTP API. Falls back to a local SQLite queue when Server A is unreachable.

---

## PHASE 1: Server B Setup (Ollama + Llama 3 8B Q4)

### 1.1 Install Ollama on Server B

SSH into `REDACTED` and run:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Verify:
```bash
ollama --version
```

### 1.2 Pull Llama 3 8B Q4 Model

```bash
ollama pull llama3:8b-instruct-q4_K_M
```

This downloads the Q4_K_M quantization (~4.7GB). Verify:
```bash
ollama list
ollama run llama3:8b-instruct-q4_K_M "Hello, respond with OK"
```

### 1.3 Configure Ollama as a System Service

Ollama installs as a systemd service by default. Ensure it starts on boot:

```bash
sudo systemctl enable ollama
sudo systemctl start ollama
```

Verify the API is listening:
```bash
curl http://localhost:11434/api/tags
```

### 1.4 Create Project Directory on Server B

```bash
mkdir -p ~/tickertap-worker
cd ~/tickertap-worker
python3 -m venv venv
source venv/bin/activate
pip install aiohttp feedparser beautifulsoup4 requests
```

---

## PHASE 2: Database Schema (Server A)

### 2.1 New Table: `news_articles`

File: `backend/alembic/versions/0009_news_articles.py`

```sql
CREATE TABLE news_articles (
    article_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url           TEXT NOT NULL,
    title         TEXT NOT NULL,
    summary       TEXT,                        -- Short description / first ~200 chars
    source        VARCHAR(20) NOT NULL,        -- 'yahoo', 'google', 'finviz', 'marketwatch'
    published_at  TIMESTAMP WITH TIME ZONE,    -- Original publication time
    scored_at     TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- General market impact
    general_score     SMALLINT NOT NULL DEFAULT 0,   -- -5 to +5
    general_reasoning TEXT,                          -- 1-2 sentence LLM explanation

    -- Retention
    created_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Dedup
    CONSTRAINT uq_news_articles_url UNIQUE (url)
);

CREATE INDEX idx_news_articles_published ON news_articles (published_at DESC);
CREATE INDEX idx_news_articles_scored    ON news_articles (scored_at DESC);
```

### 2.2 New Table: `news_article_tickers`

Junction table for per-ticker scores:

```sql
CREATE TABLE news_article_tickers (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id  UUID NOT NULL REFERENCES news_articles(article_id) ON DELETE CASCADE,
    ticker      VARCHAR(20) NOT NULL,
    score       SMALLINT NOT NULL DEFAULT 0,   -- -5 to +5 (ticker-specific impact)
    reasoning   TEXT,                          -- 1-2 sentence LLM explanation for this ticker

    CONSTRAINT uq_article_ticker UNIQUE (article_id, ticker)
);

CREATE INDEX idx_news_article_tickers_ticker   ON news_article_tickers (ticker);
CREATE INDEX idx_news_article_tickers_article  ON news_article_tickers (article_id);
```

### 2.3 SQLAlchemy ORM Models

File: `backend/app/models.py` — Add two new classes:

- `NewsArticle` — maps to `news_articles`
- `NewsArticleTicker` — maps to `news_article_tickers`, with relationship back to `NewsArticle`

### 2.4 Pydantic Schemas

File: `backend/app/schemas.py` — Update `NewsArticleOut` to include:

- `general_score: int` (-5 to +5)
- `general_reasoning: Optional[str]`
- `ticker_scores: List[TickerScoreOut]` (each with `ticker`, `score`, `reasoning`)
- Keep `in_portfolio` (computed at query time, not stored)
- Remove `sentiment` and `sentiment_score` (replaced by the new score system)

New schema: `TickerScoreOut` with fields `ticker`, `score`, `reasoning`.

---

## PHASE 3: Internal Ingestion API (Server A)

### 3.1 New Endpoint: `POST /api/v1/internal/news`

File: `backend/app/routes/news.py` — Add new endpoint.

- **Auth**: Shared secret via `X-Internal-Key` header (stored in `.env` / `.env.prod`)
- **IP restriction**: Only accept from `REDACTED` (checked via `request.client.host`)
- **Request body**: List of articles, each with:
  ```json
  {
    "url": "https://...",
    "title": "Headline text",
    "summary": "Short description",
    "source": "yahoo",
    "published_at": "2026-03-04T12:00:00Z",
    "general_score": 3,
    "general_reasoning": "Strong earnings beat signals sector growth",
    "tickers": [
      {"ticker": "NVDA", "score": 4, "reasoning": "Direct beneficiary of AI demand"},
      {"ticker": "AMD", "score": 2, "reasoning": "Indirect competitor benefit"}
    ]
  }
  ```
- **Behaviour**: Upsert by URL (skip if already exists), insert ticker scores
- **Response**: `{"inserted": N, "skipped": M}`

### 3.2 Environment Variable

Add to `.env` and `.env.prod`:
```
INTERNAL_NEWS_KEY=<generate a random 64-char hex string>
```

---

## PHASE 4: Refactor News Read Endpoints (Server A)

### 4.1 Rewrite `GET /api/v1/news/feed`

Replace the current live-fetch logic with a DB query:

1. Get user's portfolio tickers (existing `_get_user_portfolio_tickers()`)
2. Query `news_articles` joined with `news_article_tickers`
3. Order by `published_at DESC`, limit 100
4. For each article:
   - If any `news_article_tickers.ticker` is in the user's portfolio → `in_portfolio = True`, expose the ticker-specific `score` and `reasoning`
   - Otherwise → `in_portfolio = False`, expose `general_score` and `general_reasoning`
5. Return immediately from DB — no external HTTP calls, no LLM inference

### 4.2 Rewrite `GET /api/v1/news/tickers/{ticker}`

Query `news_articles` joined with `news_article_tickers` WHERE `ticker = :sym`, ordered by `published_at DESC`, limit 50.

### 4.3 Remove In-Memory Cache

The DB is the cache now. Remove `_cache`, `_get_cached`, `_set_cached` from the news routes. PostgreSQL with proper indexes will return results in <10ms.

---

## PHASE 5: Worker Script (Server B)

### 5.1 Script: `~/tickertap-worker/worker.py`

Single Python script that runs in a loop:

```
while True:
    1. Flush any pending articles from local SQLite queue
    2. Fetch RSS/HTML from all 4 sources (reuse logic from news_sources.py)
    3. Dedup against already-posted URLs (keep a local seen-set or query Server A)
    4. For each new article:
       a. Build LLM prompt with headline + summary
       b. Call Ollama API (http://localhost:11434/api/generate)
       c. Parse structured JSON response
       d. POST to Server A (http://192.168.0.x:8000/api/v1/internal/news)
       e. On failure → queue to local SQLite
    5. Sleep (10 min during market hours, 30 min off-hours)
```

### 5.2 LLM Prompt Template

```
You are a financial news analyst. Analyze this news article and return ONLY valid JSON.

Article headline: {title}
Article summary: {summary}

Return this exact JSON structure:
{
  "general_score": <integer -5 to +5, where -5 is extremely bearish and +5 is extremely bullish for the overall market>,
  "general_reasoning": "<one sentence explaining the general market impact>",
  "tickers": [
    {
      "symbol": "<affected stock ticker>",
      "score": <integer -5 to +5 for this specific stock>,
      "reasoning": "<one sentence explaining impact on this stock>"
    }
  ]
}

Rules:
- Only include tickers that are directly or significantly affected
- Score 0 means neutral/no impact
- Keep reasoning concise (one sentence max)
- Return valid JSON only, no markdown or explanation
```

### 5.3 Local SQLite Queue

File: `~/tickertap-worker/queue.db`

```sql
CREATE TABLE pending_articles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    payload     TEXT NOT NULL,          -- JSON string of the article
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    retries     INTEGER NOT NULL DEFAULT 0
);
```

- On POST failure: insert into `pending_articles`
- On each cycle start: SELECT WHERE retries < 5, attempt POST, increment retries on failure
- After 5 retries: log as dead letter, stop retrying

### 5.4 Systemd Service

File: `/etc/systemd/system/tickertap-worker.service`

```ini
[Unit]
Description=TickerTap News Worker
After=network.target ollama.service

[Service]
Type=simple
User=<username>
WorkingDirectory=/home/<username>/tickertap-worker
ExecStart=/home/<username>/tickertap-worker/venv/bin/python worker.py
Restart=always
RestartSec=30
Environment=TICKERTAP_API_URL=http://192.168.0.x:8000
Environment=TICKERTAP_INTERNAL_KEY=<same key as Server A>

[Install]
WantedBy=multi-user.target
```

### 5.5 News Source Logic

Copy the fetching logic from `backend/app/news_sources.py` into the worker as `sources.py`. Adapt from async (aiohttp) to sync (requests) for simplicity, since the worker runs sequentially. Keep the same 4 sources: Yahoo RSS, Google News RSS, Finviz HTML, MarketWatch RSS.

The worker does NOT need to know the user's portfolio tickers — it fetches general market news and all tickers mentioned. The per-ticker scoring is done by the LLM for any ticker it detects. The frontend handles showing the right score (portfolio-specific vs general) based on the user's holdings.

---

## PHASE 6: Frontend Updates

### 6.1 Update `NewsArticleOut` Response Contract

The frontend `NewsPage.jsx` currently displays:
- `sentiment` label ("positive"/"negative"/"neutral")
- `sentiment_score` (0-1 confidence)

Replace with:
- `score` (integer -5 to +5) — the most relevant score (ticker-specific if in portfolio, otherwise general)
- `reasoning` (string) — the LLM's explanation for the score
- `ticker_scores` (array) — all per-ticker scores for drill-down

### 6.2 Update NewsPage.jsx

- Replace sentiment pill with a **score badge** (-5 to +5 scale with color gradient)
- Show `reasoning` text below each article headline
- Update filter categories: replace "POSITIVE"/"NEGATIVE" with "BULLISH" (score > 0) / "BEARISH" (score < 0)
- Remove the "load more per ticker" deep-fetch button (all articles are pre-fetched in DB)
- Add a staleness indicator: if the newest article is older than 30 min, show "News may be delayed" in muted text

### 6.3 Update `api/client.js`

- Remove `getNewsByTicker` (no longer needed — all articles served from `/feed`)
- Or keep it as a filtered view (query param on `/feed?ticker=NVDA`) — simpler API surface

---

## PHASE 7: Cleanup (Server A)

### 7.1 Remove FinBERT / torch Dependencies

From `backend/requirements.txt`, remove:
- `transformers>=4.36`
- `torch>=2.1`

This removes ~4GB from the Docker image.

### 7.2 Delete Unused Files

- `backend/app/sentiment.py` — FinBERT loader, no longer needed
- `backend/app/news_sources.py` — RSS/HTML fetching, moved to Server B worker

### 7.3 Update `backend/app/main.py`

- Remove import of `sentiment` if referenced anywhere at startup
- No changes to route registration (news routes stay, just rewritten internally)

### 7.4 Rebuild Docker Image

Without torch/transformers, the image shrinks from ~4GB to ~500MB. Rebuild:
```bash
docker compose --env-file .env.prod up -d --build app
```

---

## PHASE 8: Network Security

### 8.1 Firewall Rule on Server A

Allow PostgreSQL and the internal API only from Server B:

```bash
# Allow Server B to reach the internal news endpoint (port 8000)
sudo ufw allow from REDACTED to any port 8000 proto tcp
```

### 8.2 IP Check in Internal Endpoint

The `POST /api/v1/internal/news` endpoint validates:
1. `X-Internal-Key` header matches the env var
2. `request.client.host` is `REDACTED`

Both must pass. Reject with 403 otherwise.

---

## PHASE 9: Article Retention Policy

### 9.1 Scheduled Cleanup

Add a lightweight background task in FastAPI's startup event (or the worker script) that runs daily:

```sql
DELETE FROM news_articles WHERE created_at < NOW() - INTERVAL '30 days';
```

Cascade deletes will remove associated `news_article_tickers` rows automatically.

### 9.2 Index Support

The `idx_news_articles_published` index on `published_at DESC` also supports efficient range deletes.

---

## IMPLEMENTATION CHECKLIST

```markdown
IMPLEMENTATION CHECKLIST:

SERVER A (App Server):
1.  Create Alembic migration 0009_news_articles (news_articles + news_article_tickers tables)
2.  Add NewsArticle and NewsArticleTicker ORM models to models.py
3.  Add TickerScoreOut schema and update NewsArticleOut in schemas.py
4.  Add INTERNAL_NEWS_KEY to .env and .env.prod
5.  Implement POST /api/v1/internal/news endpoint with auth + IP check
6.  Rewrite GET /api/v1/news/feed to query DB with portfolio-aware scoring
7.  Rewrite GET /api/v1/news/tickers/{ticker} to query DB filtered by ticker
8.  Remove in-memory news cache from routes/news.py
9.  Add 30-day retention cleanup task
10. Remove transformers and torch from requirements.txt
11. Delete backend/app/sentiment.py
12. Delete backend/app/news_sources.py
13. Update main.py imports if needed
14. Run Alembic migration on the database
15. Rebuild Docker image (now ~500MB without torch)

SERVER B (LLM Server — REDACTED):
16. Install Ollama
17. Pull llama3:8b-instruct-q4_K_M model
18. Create ~/tickertap-worker/ project directory with venv
19. Write sources.py (news fetching, adapted from news_sources.py)
20. Write worker.py (main loop: fetch → score → post → sleep)
21. Write queue.py (SQLite fallback queue logic)
22. Create systemd service for the worker
23. Test end-to-end: worker fetches → Ollama scores → articles appear in Server A DB

FRONTEND:
24. Update NewsPage.jsx: score badge, reasoning text, filter updates
25. Update api/client.js: adjust API calls for new response shape
26. Build frontend (npx vite build)

NETWORK & SECURITY:
27. Configure firewall rule on Server A (allow REDACTED)
28. Verify internal endpoint rejects unauthorized requests

VALIDATION:
29. Verify News page loads instantly from DB
30. Verify worker handles Server A downtime (queues locally, flushes on reconnect)
31. Verify 30-day retention purge works
32. Verify Docker image size reduction (~4GB → ~500MB)
```
