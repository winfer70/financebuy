# TickerTap Integration Plan — Portfolio Rules Engine + Scanner
**Date: May 14, 2026**
**Scope: Integrating portfolio_manager.py + volume_flow_scanner.py into TickerTap**

---

## Integration Map

### What already exists (zero rebuild needed)

| Our feature | Maps to in TickerTap |
|---|---|
| 5-phase volume flow scanner | `trading-worker.run_scanner` arq job |
| Scan results storage | `scan_results` table |
| Rule alerts delivery | `notifications` table |
| Strategy marketplace | `strategies` + `strategy_ratings` + `strategy_usage` |
| LLM for rule generation | Ollama already wired (`/api/v1/guide/ask`) |
| User config storage | `users.preferences_json` |
| Position data | `portfolio_positions` (partial — see migration 23) |

### What's missing (needs migration + code)

**Columns `PortfolioPosition` lacks vs our positions.json schema:**

| Missing field | Notes |
|---|---|
| `t2_usd` | `profit_taking` = T1 only; second target unrepresented |
| `is_semi` | No equivalent — needed for Rule 12 semiconductor cap |
| `sector` | No equivalent — needed for sector weight calculation |
| `date_entered` | `created_at` exists but is audit, not business logic |
| `bucket` | `group_tag` is freeform string; bucket is 1/2/3 enum |
| `closed` | `is_excluded` is semantically different (scan exclusion vs exit) |

---

## Database Migrations

### Migration 23 — Position fields
```sql
ALTER TABLE portfolio_positions
  ADD COLUMN t2_usd       NUMERIC(18,2),
  ADD COLUMN is_semi      BOOLEAN DEFAULT FALSE,
  ADD COLUMN sector       VARCHAR(64),
  ADD COLUMN date_entered DATE,
  ADD COLUMN bucket       SMALLINT CHECK (bucket IN (1, 2, 3)),
  ADD COLUMN closed_at    TIMESTAMPTZ;
```

### Migration 24 — Rule alerts table
```sql
CREATE TABLE rule_alerts (
    id               BIGSERIAL PRIMARY KEY,
    user_id          UUID REFERENCES users(user_id) ON DELETE CASCADE,
    position_id      BIGINT REFERENCES portfolio_positions(id) ON DELETE CASCADE,
    portfolio_id     BIGINT,
    rule_type        VARCHAR(32) NOT NULL,
    -- Values: house_money | stop_proximity | semi_cap | bucket |
    --         time_stop | fundamentals | pre_earnings | analyst_consensus
    severity         VARCHAR(10) NOT NULL,   -- info | warning | critical
    title            VARCHAR(200),
    body             TEXT,
    triggered_value  NUMERIC(18,4),
    state            VARCHAR(16) DEFAULT 'active',
    -- Values: active | snoozed | actioned | expired
    snoozed_until    TIMESTAMPTZ,
    expires_at       TIMESTAMPTZ,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_rule_alerts_user_active
    ON rule_alerts(user_id, state, created_at DESC);
CREATE INDEX idx_rule_alerts_position
    ON rule_alerts(position_id, rule_type);
```

**Why separate from `notifications`:**
The existing `notifications` table (user_id, event_type, title, body, is_read) is the
delivery layer. `rule_alerts` is the source of truth — it has a position FK for
invalidation on exit, structured severity/state lifecycle (snooze, actioned), and
queryability without JSON parsing. `rule_alerts` inserts generate a `notifications`
row for UI delivery; the notification is ephemeral, the rule alert persists.

### Migration 25 — Scan mode column
```sql
ALTER TABLE scan_results ADD COLUMN mode VARCHAR(16) DEFAULT 'auto';
-- Values: auto | live | prev-day
-- Promoted from parameters_json for queryability.
-- session_state, elapsed_weight remain inside parameters_json.
```

---

## Phase A — Portfolio Rules Engine (portfolio_manager.py → arq)

The rules engine becomes a new arq background job in `trading-worker`.
Reads positions from DB instead of positions.json, writes to `rule_alerts`.

### New arq job
```python
# app/trading/worker.py — add to WorkerSettings.functions
async def run_portfolio_rules(ctx, user_id: str, portfolio_id: int):
    """
    Adapts portfolio_manager.py rule checks to run as an arq background job.

    Steps:
    1. Load portfolio_positions from DB for the given portfolio_id
    2. Fetch live prices via yfinance (reuse existing fetch_prices pattern)
    3. Fetch 80-day daily OHLCV for Rule 16 time-stop (fetch_ohlcv_daily)
    4. Fetch fundamentals for D/E, margin YoY, insider selling
    5. Run all rule checks (see list below)
    6. Write new rule_alerts rows; create notifications for critical/warning
    7. Expire stale rule_alerts for positions with closed_at set
    """
    pass
```

### Rule checks to port (all from portfolio_manager.py)

| Rule | Function | Severity tiers |
|---|---|---|
| Rule 11 — House Money | `check_house_money()` | INFO ≥1.5×, WARNING ≥1.75×, CRITICAL ≥2.0× |
| Stop proximity | `check_stop_proximity()` | WARNING <7% buffer, CRITICAL breached |
| Rule 12 — Semi cap | `check_semi_cap()` | WARNING >35% of portfolio in semis |
| Rule 13 — Bucket allocation | `check_buckets()` | WARNING >±5% from target |
| Rule 16 — Time-Stop | `check_time_stop()` | WARNING ≥10 sessions below 50D SMA, CRITICAL ≥21 |
| Analyst consensus | `check_analyst_consensus()` | WARNING >25% above target, CRITICAL >50% |
| Fundamental health | `check_fundamentals_health()` | D/E stress, margin compression, insider selling |
| Pre-earnings alert | inline in `run_dashboard()` | INFO 2 business days before earnings |

### New API endpoints
```
POST /api/v1/portfolio-manager/portfolios/{id}/run-rules
     → queues run_portfolio_rules arq job, returns job_id

GET  /api/v1/portfolio-manager/portfolios/{id}/rule-alerts
     ?severity=warning,critical&state=active&rule_type=house_money
     → returns paginated rule_alerts

PATCH /api/v1/portfolio-manager/rule-alerts/{alert_id}
      body: {"state": "snoozed", "snoozed_until": "2026-05-15T09:30:00Z"}
      → snooze or mark actioned
```

### Trigger options (user picks in Rules settings tab)
- **On demand** — button in PortfolioManagerPage
- **Market hours** — every 60s, same pattern as `paper-worker` self-re-enqueue
- **On price alert fire** — chain from `alert-worker` after a price alert triggers

---

## Phase B — Scanner Session-Awareness (volume_flow_scanner.py → trading-worker)

The existing `run_scanner` arq job gets the session-aware volume framework
built in `volume_flow_scanner.py v2.0`.

### What changes in `run_scanner`
1. Import `pytz`, `get_market_session()`, `get_elapsed_weight()`, `project_daily_volume()`, `fetch_ohlcv_intraday()` from the ported module
2. Build `ctx` dict before phases run (session, elapsed_weight, intraday_vols, verbose)
3. Pass `ctx` to `phase1_scan(ctx)` and `phase2_scan(active_sectors, ctx)`
4. Store `mode` in `scan_results.mode` column (promoted field)
5. Store `session_state` + `elapsed_weight` inside `parameters_json`

### parameters_json payload (updated)
```json
{
  "mode": "auto",
  "session_state": "mid",
  "elapsed_weight": 0.55,
  "volume_threshold": 2.0,
  "portfolio_id": 42,
  "phase_context": {
    "phase1_session": "mid",
    "phase1_elapsed": 0.55,
    "phase2_session": "mid",
    "phase2_elapsed": 0.61
  }
}
```

### Frontend (ResearchPage — VOLUME FLOW tab)
- Add **Mode** selector before triggering scan: Auto | Prev-Day | Live
- Session banner from our script → status chip in scan progress UI:
  `MID SESSION (12:34 ET) | 55% elapsed | LIVE mode`
- `--verbose` flag maps to a "Show volume details" toggle in scan results

---

## Phase C — User-Configurable Rules

Every numeric threshold in portfolio_manager.py becomes user-editable.
Stored in `users.preferences_json` under a `portfolio_rules` key.

### preferences_json schema (new `portfolio_rules` key)
```json
{
  "portfolio_rules": {
    "house_money_multiple":       2.0,
    "house_money_warn_at":        1.75,
    "house_money_info_at":        1.50,
    "stop_proximity_pct":         0.07,
    "semi_cap":                   0.35,
    "bucket_1_target":            0.35,
    "bucket_2_target":            0.35,
    "bucket_3_target":            0.30,
    "time_stop_warn_sessions":    10,
    "time_stop_critical_sessions": 21,
    "analyst_flag_pct":           0.50,
    "de_ratio_warn":              200,
    "de_ratio_critical":          500,
    "margin_compression_warn_pct": 30,
    "enabled_rules": [
      "house_money", "stop_proximity", "semi_cap",
      "bucket", "time_stop", "analyst_consensus",
      "fundamentals", "pre_earnings"
    ],
    "run_schedule": "market_hours"
  }
}
```

### New API endpoints
```
GET   /api/v1/portfolio-manager/rule-config
PATCH /api/v1/portfolio-manager/rule-config
      body: partial preferences_json.portfolio_rules update
```

### Frontend — new "Rules" tab in PortfolioManagerPage
- Slider / number input for each threshold, defaults pre-populated
- Toggle to enable/disable each rule check individually
- Schedule picker: On Demand | Market Hours (60s) | End of Day
- Rule alerts panel: current `rule_alerts` with severity colour coding,
  snooze button, mark-actioned, filter by rule type

---

## Phase D — LLM Rule Builder + Marketplace

### LLM approach — JSON DSL, NOT executable Python

**Do not generate executable Python.** Even sandboxed `exec` is high attack surface,
diffs poorly in UI, and cannot be validated against a schema.

The LLM outputs a **declarative JSON rule DSL**. The rule engine is a pure
interpreter over this schema — no `eval`, no `exec`. Same model as the
existing PineScript AST validator.

### Rule DSL schema
```json
{
  "name": "High-debt semi filter",
  "description": "Warn when a semiconductor position in bucket 1 has D/E above 150%",
  "version": 1,
  "logic": "AND",
  "conditions": [
    {"field": "is_semi",        "operator": "eq",  "value": true},
    {"field": "bucket",         "operator": "eq",  "value": 1},
    {"field": "debt_to_equity", "operator": "gt",  "value": 150}
  ],
  "action": {
    "type": "alert",
    "severity": "warning",
    "message_template": "{ticker} is a semi in bucket 1 with D/E {debt_to_equity}%"
  }
}
```

**Allowed `field` whitelist** (derived from position + fundamentals):
`ticker, quantity, purchase_price, stop_loss, profit_taking, t2_usd, is_semi,
bucket, sector, debt_to_equity, margin_recent, margin_yoy_delta, insider_net_12m,
price, pnl_pct, stop_buffer_pct, sessions_below_sma50, price_vs_entry_multiple`

**Allowed `operator` whitelist:**
`eq, ne, gt, gte, lt, lte, within_pct, crosses_above, crosses_below`

### Ollama prompt flow
```
1. User types natural language: "Alert me when bucket 1 is over 40% of my portfolio"
2. System prompt:
   - Constrains output to DSL JSON schema
   - Injects field whitelist and operator whitelist
   - Examples of valid rules
3. Ollama responds with DSL JSON
4. Validate against JSON Schema — if fails, re-prompt once with validation error
5. On pass: store as strategy row with strategy_type = 'rule'
6. User can edit the JSON directly or re-generate
```

### New API endpoints
```
POST /api/v1/portfolio-manager/rules/generate
     body: {"prompt": "alert me when a position is within 5% of its stop"}
     → calls Ollama, validates DSL, returns draft rule (NOT saved yet)

POST /api/v1/portfolio-manager/rules/validate
     body: {rule DSL JSON}
     → validates against schema, returns errors or "valid"

POST /api/v1/portfolio-manager/rules
     body: {rule DSL JSON, name, description}
     → saves as strategy with strategy_type = 'rule'

GET  /api/v1/portfolio-manager/rules
     → user's saved rule sets
```

### Rules Marketplace — reuse existing strategy tables

Add `rule` as a new `strategy_type` enum value:
```python
strategy_type = 'rule'  # alongside builtin | pinescript | composed | ml
```

**Everything else works immediately with zero table changes:**
- Publish/unpublish: `POST /api/v1/trading/strategies/{id}/publish` ✓
- Clone: `POST /api/v1/trading/strategies/{id}/clone` ✓
- Star ratings: `POST /api/v1/trading/strategies/{id}/rate` ✓
- Usage tracking: `strategy_usage` table ✓
- Marketplace browse: `GET /api/v1/trading/marketplace?strategy_type=rule` ✓

Add `category` inside `definition_json` for marketplace filtering:
- `conservative` — stop proximity, house money, fundamentals focus
- `aggressive` — high concentration tolerance, growth-first rules
- `sector_focus` — semi cap, bucket rotation
- `risk_management` — time-stop heavy, ATR-based triggers

**Frontend — "Rules" tab in MarketplacePage:**
- Browse community rule sets filtered by category
- Clone → applies to your portfolio_rules config
- Rate with existing star system
- Stats: users running this rule set, average portfolio impact

---

## Build Order

| Phase | Task | Effort | Payoff |
|---|---|---|---|
| 1 | Migration 23 (position fields) | 0.5 days | Unlocks is_semi, bucket, sector per position |
| 2 | Migration 24 (rule_alerts table) | 0.5 days | Enables structured alert storage |
| 3 | Migration 25 (scan mode column) | 0.5 hrs | Scanner mode queryable |
| 4 | **Phase A: run_portfolio_rules arq job** | 2–3 days | Existing users get rule alerts immediately |
| 5 | **Phase A: rule-alerts API + frontend panel** | 1–2 days | Alerts visible in PortfolioManagerPage |
| 6 | **Phase B: Scanner session-awareness** | 1 day | Scanner accurate during market hours |
| 7 | **Phase C: User-configurable thresholds** | 1–2 days | Personalisation + settings UI |
| 8 | **Phase D: LLM rule builder (DSL + Ollama)** | 3–4 days | Unique differentiator |
| 9 | **Phase D: Rules marketplace** | 1 day | Free — reuses strategy tables entirely |

**Total: ~10–12 days to full integration including marketplace.**

---

## The Moat

The LLM rule builder with a JSON DSL is the piece that doesn't exist anywhere
in this space. TradingView has Pine Script — a code editor. No platform lets
a retail investor say "alert me when my semiconductor concentration exceeds 35%
and I have an earnings event in 3 days" in plain English and get a working,
shareable, rated rule set back. That's the actual differentiator.

The JSON DSL approach (not executable Python) is what makes it safe to ship
to users without a sandboxing infrastructure investment. The rule engine
interpreter is written once, is ~100 lines, and handles all rules regardless
of who generated them.

---

## Hardware — Dedicated Ollama Node for Rule Builder

### Current setup
- **Kali laptop (Server B):** runs `llama3:8b-instruct-q4_K_M` for news scoring
  (continuous pipeline, high token volume, open-ended generation — needs the 8B)

### Proposed addition
- **i5 laptop, 8GB RAM:** dedicated Ollama node for rule generation only

### Why smaller model is better here

The rule builder is a **constrained generation task**, not open-ended reasoning.
The model receives a tight system prompt (field whitelist + operator enum + JSON
schema) and outputs ~30–80 tokens of structured JSON. This is pattern completion
against a schema — a 3B model handles it reliably and runs fast enough on CPU
for a background arq job where a user waits 5–10 seconds.

| Model | RAM usage | Speed on old i5 (CPU) | Suitable |
|---|---|---|---|
| `llama3:8b-instruct-q4_K_M` | ~5.5 GB | ~2–5 tok/s (tight on 8GB) | No — overkill, slow |
| `phi3.5:mini` | ~2.3 GB | ~8–15 tok/s | **Yes — best choice** |
| `qwen2.5:3b-instruct` | ~1.9 GB | ~10–18 tok/s | **Yes — good alternative** |
| `qwen2.5:7b-instruct-q4` | ~4.5 GB | ~4–8 tok/s | Upgrade path if needed |

**Recommended: `phi3.5:mini`** — Microsoft model, specifically strong at structured
output and function-calling style tasks. Runs at ~2.3GB leaving comfortable
headroom on 8GB. At 8–15 tok/s on old i5, a 60-token rule DSL response arrives
in ~5 seconds — acceptable for an async arq job.

**Upgrade path:** if rule complexity grows, `ollama pull qwen2.5:7b` fits in 8GB
at q4 and is significantly stronger. Model name change in one env var, no other
code changes.

### Ollama JSON mode — eliminates re-prompt loop

Ollama's `format: "json"` parameter hard-constrains output to valid JSON,
removing the most common failure mode before it reaches schema validation:

```python
response = requests.post(f"{OLLAMA_RULES_URL}/api/generate", json={
    "model": "phi3.5:mini",
    "prompt": system_prompt + user_input,
    "format": "json",    # Ollama enforces valid JSON — no parse failures
    "stream": False,
    "options": {"temperature": 0.1}   # low temp = deterministic, schema-following
})
```

`temperature: 0.1` keeps output close to the schema examples in the system prompt.
Higher temperature produces creative but structurally invalid rules.

### Network configuration

Separate env var so rule builder and news scoring never contend:

```env
# .env.prod
OLLAMA_URL=http://kali-laptop:11434         # existing — llama3:8b news scoring
OLLAMA_RULES_URL=http://i5-laptop:11434    # new — phi3.5:mini rule generation
```

The i5 laptop sits idle ~95% of the time (rule generation is user-triggered,
not a continuous pipeline). A single dedicated machine handles bursts comfortably.
No GPU required — the task is CPU-only inference on small batches.

### arq worker routing

```python
# app/trading/worker.py
OLLAMA_RULES_URL = os.getenv("OLLAMA_RULES_URL", "http://localhost:11434")
OLLAMA_RULES_MODEL = os.getenv("OLLAMA_RULES_MODEL", "phi3.5:mini")

async def run_rule_generation(ctx, user_id: str, prompt: str) -> dict:
    """Generate rule DSL from natural language via dedicated Ollama node."""
    loop = asyncio.get_event_loop()
    raw = await loop.run_in_executor(None, lambda: _call_ollama_rules(prompt))
    validated = validate_rule_dsl(raw)   # JSON Schema validation
    return validated
```

### Fallback behaviour

If the i5 laptop is offline, `run_rule_generation` falls back to `OLLAMA_URL`
(the Kali news laptop) with the same model call. The news pipeline is unaffected
because rule generation jobs are infrequent. Add a 30-second timeout so a
slow/offline node doesn't block the arq queue.

---

*Related files: portfolio_manager.py, volume_flow_scanner.py, SCANNER.md, MANAGER.md, ARCHITECTURE.md*
*TickerTap branch: tradingAI0.1 | Root: /home/kamilo420/projects/finance/tickerTap*
