# TickerTap AI Architecture

_Last updated: 2026-09-02_

Node names below are **placeholders**. Real hostnames, LAN IPs, and credentials live only in gitignored env files — never commit them.

## Node Map

```
dev-workstation (<YOUR_DEV_MACHINE_IP>)     ← dev machine, all code
app-host (<YOUR_APP_SERVER_IP>)             ← prod: tickerTap app + workers (Docker)
ollama-gpu-host (<YOUR_OLLAMA_GPU_IP>)      ← GPU inference: Ollama, RTX 3060 12GB (PRIMARY)
vector-store-host (<YOUR_VECTOR_STORE_IP>)  ← ChromaDB :8000, Redis :6379, Ollama CPU (FALLBACK)
monitoring-host (<YOUR_MONITORING_IP>)      ← Prometheus :9090, Grafana :3000, tickertap-worker
advisor-host (<YOUR_ADVISOR_IP>)            ← swarmAI :8010 (Logician/Devil/Aggregator)
```

---

## Ollama Models

| Node | Role | Models |
|------|------|--------|
| ollama-gpu-host | PRIMARY — RTX 3060 12GB GPU | qwen3:14b (9.3GB), hermes3:8b, deepseek-r1:8b, gemma4, qwen2.5-coder:7b |
| vector-store-host | FALLBACK — CPU only | qwen3:4b, qwen3:8b, deepseek-r1:8b, codestral:22b, hermes3:8b |

All tickerTap + swarmAI AI calls route to **ollama-gpu-host** (`OLLAMA_URL=http://<YOUR_OLLAMA_GPU_IP>:11434`).
Model: **qwen3:14b** for analysis and critique (switched from hermes3:8b 2026-06-18).

---

## tickerTap AI Stack

### 1. Stock Analysis Flow

```
User → Telegram /analyze TICKER
         ↓
bot.py → GET /api/v1/analysis/stock?ticker=XX (X-Bot-Api-Key)
         ↓
analysis_routes.py:
  1. yfinance — price, RSI14, SMA50/200, ATR14, P/E, 52w H/L, sector, analyst target
  2. load investment_rules.json (hot-reload, no restart)
  3. _check_rules() — flags: AVOID_LIST, VOLATILE, ANALYST_TARGET_BAKED_IN, RSI bands, SMA trend, tier S/A/B
  4. query_similar() → ChromaDB :8000 — 3 similar past trades with outcomes (RAG context)
  5. _build_prompt() — rules + market data + RAG + structured output format
  6. POST ollama-gpu-host:11434/api/generate — model: qwen3:14b, temp: 0.2, num_predict: 1024, timeout: 300s
  7. _parse_ollama_response() — extract: RECOMMENDATION / ENTRY / STOP / TARGET / RISK_REWARD / ANALYSIS
  8. INSERT trade_analyses row (outcome=OPEN)
  9. store_analysis() → ChromaDB upsert embedding
         ↓
bot.py → send formatted reply to Telegram chat
```

### 2. Paper Trade Flow

```
/buy TICKER QTY PRICE
  → POST /api/v1/portfolios/{AI_PAPER_PORTFOLIO_ID}/positions
  → PortfolioPosition: group_tag=AI_PAPER, linked to TradeAnalysis.position_id

/sell TICKER QTY PRICE
  → PUT /sell endpoint
  → full sell: queries TradeAnalysis (position_id, outcome=OPEN) BEFORE delete
  → enqueues evaluate_closed_trade(analysis_id) to arq:trading queue
  → position deleted, PortfolioTrade SELL record saved
```

### 3. Learning Loop — evaluate_closed_trade (arq job)

```
evaluate_closed_trade(analysis_id):
  1. Fetch TradeAnalysis + PortfolioPosition
  2. Find sell price from PortfolioTrade SELL record (latest by ticker+portfolio_id)
  3. Compute outcome: WIN (>+1%), LOSS (<-1%), BREAK_EVEN
  4. Ollama critique prompt → qwen3:14b
     - was the recommendation correct?
     - what rule would have improved the call?
  5. Update TradeAnalysis: outcome, actual_entry, actual_exit, actual_pnl_pct, evaluation_json
  6. store_analysis() → update ChromaDB embedding with outcome
  7. _telegram_notify() → send result to user
```

### 4. Shadow Mode Rule Refinement — weekly_meta_analysis (arq cron)

```
Every Monday 03:00:
  1. Fetch 90 days of closed AI_PAPER trades + evaluation_json
  2. Requires min 5 trades (skip if insufficient data)
  3. Ollama pattern analysis → suggested rule changes
  4. INSERT RuleRefinement (status=pending, pattern_summary, suggested_rules)
  5. Telegram notify: "New refinement pending — /refinements to review"

User flow:
  /refinements         → list pending RuleRefinement rows
  /approve_refinement ID → appends suggested rules to investment_rules.json
  Rules NEVER auto-update — user is always the gate
```

---

## ChromaDB (vector-store-host :8000)

- Collection: `trade_analyses`
- Embedding: `{ticker} {sector} {recommendation} price={price} rsi={rsi} sma50={sma50} sma200={sma200} {analysis_text}`
- Used for RAG: inject 3 most similar past trades (with outcomes) into every new analysis prompt
- Updated on: initial store (OPEN), post-evaluation (WIN/LOSS/BREAK_EVEN)
- Client: raw httpx REST — NO chromadb Python package (pydantic v2 conflict)

---

## swarmAI (advisor-host :8010)

```
User → POST /advisor
         ↓
Logician (agent) → ollama-gpu-host:11434 qwen3:14b — frames question
         ↓
Devil (agent) → ollama-gpu-host:11434 qwen3:14b — adversarial critique
         ↓
Aggregator (agent) → ollama-gpu-host:11434 qwen3:14b — synthesises final answer
         ↓
Response ~27.9s (was 7-10min on vector-store-host CPU before ollama-gpu-host GPU)
```

---

## Config Files

| File | Purpose |
|------|---------|
| `backend/app/config/investment_rules.json` | Trading rules — hot-reload. Rules text, avoid list, volatile/stable tickers, tier S/A/B watchlists, R:R thresholds, ATR multiplier |
| `backend/.env` (app-host) | All secrets + `OLLAMA_URL`, `CHROMADB_URL`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |

---

## Workers (app-host Docker)

| Container | Queue | Jobs |
|-----------|-------|------|
| tickertap-alert-worker-1 | arq:alert | `evaluate_price_alerts` (also runs two-stage soft-stop loop), `evaluate_one_soft_stop`, DeGiro sync cron 02:00 |
| tickertap-trading-worker-1 | arq:trading | `run_backtest`, `run_scanner`, `run_portfolio_rules`, `sync_degiro_portfolio`, `evaluate_closed_trade`; cron `weekly_meta_analysis` Mon 03:00 |

Soft-stop delivery: Telegram + ntfy (`NTFY_URL` / `NTFY_TOPIC` / `NTFY_TOKEN`) with per-channel retry. Price alerts remain in-app only.

News scoring is **not** this stack. See `NEWS_RESEARCH.md` + `server-b-worker/` (Ollama on the news-worker host → `POST /api/v1/news/internal/news`).

---

## Key Constraints

- Pydantic v1 only throughout — `orm_mode=True`, never v2 validators
- Never `float` for money — `Decimal` / `Numeric(18,2)` everywhere
- App container has NO bind mounts — code COPY'd; new code needs `--no-cache` rebuild
- chromadb Python package cannot be used (pydantic v2 conflict) — raw httpx only
- Telegram bot polling runs inside FastAPI process (startup event), not a separate container
