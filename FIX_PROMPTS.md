# TickerTap — Fix Prompts for Claude Code

Each section is a self-contained prompt. Paste it into Claude Code (MODE: EXECUTE).
All line numbers are exact; verify they match before applying.

---

## FIX 1 — arq Queue Isolation (CRITICAL)

### Problem
All three arq workers (trading-worker, paper-worker, alert-worker) share the default Redis
queue `arq:default`. Any worker polling Redis can pick up jobs meant for another worker.
When that happens the job is silently dropped with a "function not found" log line.
Observed: paper-worker logs show `function 'run_scanner' not found` and
`function 'evaluate_price_alerts' not found`.

### Fix
Add a dedicated `queue_name` to each `WorkerSettings` class, and a matching `_queue_name`
keyword argument to every `enqueue_job` call.

Apply the following changes **exactly** — do not rename anything, do not add comments:

---

**File: `backend/app/trading/worker.py`**

Line 88 — add `_queue_name` to enqueue_backtest:
```python
# BEFORE
    await redis.enqueue_job("run_backtest", backtest_id)

# AFTER
    await redis.enqueue_job("run_backtest", backtest_id, _queue_name="arq:trading")
```

Lines 325–334 — add `queue_name` to WorkerSettings:
```python
# BEFORE
class WorkerSettings:
    """arq worker configuration.

    Run with: ``arq app.trading.worker.WorkerSettings``
    """
    functions = [run_backtest, run_scanner]
    on_startup = _worker_startup
    redis_settings = RedisSettings.from_dsn(_REDIS_URL)
    max_jobs = 10
    job_timeout = 300  # 5 minutes max per backtest

# AFTER
class WorkerSettings:
    """arq worker configuration.

    Run with: ``arq app.trading.worker.WorkerSettings``
    """
    functions = [run_backtest, run_scanner]
    on_startup = _worker_startup
    redis_settings = RedisSettings.from_dsn(_REDIS_URL)
    queue_name = "arq:trading"
    max_jobs = 10
    job_timeout = 300  # 5 minutes max per backtest
```

---

**File: `backend/app/trading/scanner_worker.py`**

Line 771 — add `_queue_name` to enqueue_scanner:
```python
# BEFORE
        job = await redis.enqueue_job("run_scanner", result_id)

# AFTER
        job = await redis.enqueue_job("run_scanner", result_id, _queue_name="arq:trading")
```

---

**File: `backend/app/trading/paper_worker.py`**

Line 151 — re-enqueue inside finally block:
```python
# BEFORE
            await pool.enqueue_job("evaluate_paper_trades", _defer_by=60)

# AFTER
            await pool.enqueue_job("evaluate_paper_trades", _defer_by=60, _queue_name="arq:paper")
```

Line 521 — startup seed enqueue:
```python
# BEFORE
        await pool.enqueue_job("evaluate_paper_trades", _defer_by=10)

# AFTER
        await pool.enqueue_job("evaluate_paper_trades", _defer_by=10, _queue_name="arq:paper")
```

Lines 530–538 — add `queue_name` to WorkerSettings:
```python
# BEFORE
class WorkerSettings:
    """arq worker configuration for the paper trading evaluator.

    Run with: ``arq app.trading.paper_worker.WorkerSettings``
    """

    functions = [evaluate_paper_trades]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(_REDIS_URL)
    max_jobs = 5

# AFTER
class WorkerSettings:
    """arq worker configuration for the paper trading evaluator.

    Run with: ``arq app.trading.paper_worker.WorkerSettings``
    """

    functions = [evaluate_paper_trades]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(_REDIS_URL)
    queue_name = "arq:paper"
    max_jobs = 5
```

---

**File: `backend/app/trading/alert_worker.py`**

Line 244 — re-enqueue inside finally block:
```python
# BEFORE
            await pool.enqueue_job("evaluate_price_alerts", _defer_by=defer_by)

# AFTER
            await pool.enqueue_job("evaluate_price_alerts", _defer_by=defer_by, _queue_name="arq:alert")
```

Line 270 — startup seed enqueue:
```python
# BEFORE
        await pool.enqueue_job("evaluate_price_alerts", _defer_by=10)

# AFTER
        await pool.enqueue_job("evaluate_price_alerts", _defer_by=10, _queue_name="arq:alert")
```

Lines 279–289 — add `queue_name` to WorkerSettings:
```python
# BEFORE
class WorkerSettings:
    """arq worker configuration for the alert evaluation loop.

    Run with: ``arq app.trading.alert_worker.WorkerSettings``
    """

    functions = [evaluate_price_alerts]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(_REDIS_URL)
    max_jobs = 5
    job_timeout = 120

# AFTER
class WorkerSettings:
    """arq worker configuration for the alert evaluation loop.

    Run with: ``arq app.trading.alert_worker.WorkerSettings``
    """

    functions = [evaluate_price_alerts]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(_REDIS_URL)
    queue_name = "arq:alert"
    max_jobs = 5
    job_timeout = 120
```

---

**File: `backend/app/routes/trading.py`**

Line 2653 — paper trade kickoff from API route:
```python
# BEFORE
        await pool.enqueue_job("evaluate_paper_trades", _defer_by=5)

# AFTER
        await pool.enqueue_job("evaluate_paper_trades", _defer_by=5, _queue_name="arq:paper")
```

---

### Deploy
Backend is bind-mounted (`./backend/app:/app/app:ro`) — changes take effect on container restart:
```bash
cd /path/to/tickerTap
docker compose --env-file .env.prod -f docker-compose.prod.yml restart trading-worker paper-worker alert-worker app
```

### Verify
Watch logs for 2 minutes after restart — you should see NO more
`function 'evaluate_price_alerts' not found` or `function 'run_scanner' not found` in paper-worker logs:
```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f paper-worker
```

---

## FIX 2 — trading-worker Heartbeat Expiry

### Problem
`backend/app/trading/heartbeat.py` sets TTL for `trading-worker` to 1800 seconds.
The health check (`python -m app.trading.worker_healthcheck trading-worker 600`) checks
whether the heartbeat key was written within the last 600 seconds.
The heartbeat is only written on job completion — if no backtests run for 10+ minutes,
the health check fails and the container shows UNHEALTHY, even though the worker is running.
Observed: worker completed a scanner job at 22:09, health check at 23:52 → 103 min gap → UNHEALTHY.

### Fix
Add an arq cron job to `worker.py` that pings the heartbeat every 5 minutes.
This ensures the key is always fresh regardless of job activity.

**File: `backend/app/trading/worker.py`**

At the top of the file, add `cron` to the arq imports. Find the existing arq import line
(it imports `Worker`, `WorkerSettings`, `func` or similar from `arq`) and add `cron`:
```python
# Find the arq import — it will look something like:
from arq import Worker
# or
from arq.connections import RedisSettings, create_pool
# Add cron import alongside existing arq imports:
from arq.cron import cron
```

Add a new function before the `WorkerSettings` class (around line 323):
```python
async def _periodic_heartbeat(ctx: dict) -> None:
    """Periodic no-op heartbeat to keep the health-check key alive.

    Runs every 5 minutes via arq cron so the worker shows healthy even
    when no backtest jobs are queued.
    """
    await write_worker_heartbeat(
        "trading-worker", _REDIS_URL, jobs_processed_delta=0, last_error=""
    )
```

In the `WorkerSettings` class, add a `cron_jobs` list:
```python
# BEFORE
class WorkerSettings:
    functions = [run_backtest, run_scanner]
    on_startup = _worker_startup
    redis_settings = RedisSettings.from_dsn(_REDIS_URL)
    queue_name = "arq:trading"   # added by FIX 1
    max_jobs = 10
    job_timeout = 300

# AFTER
class WorkerSettings:
    functions = [run_backtest, run_scanner]
    cron_jobs = [cron(_periodic_heartbeat, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55})]
    on_startup = _worker_startup
    redis_settings = RedisSettings.from_dsn(_REDIS_URL)
    queue_name = "arq:trading"
    max_jobs = 10
    job_timeout = 300
```

### Deploy
```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml restart trading-worker
```

### Verify
Wait 6 minutes then run:
```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml exec app \
  python -m app.trading.worker_healthcheck trading-worker 600
```
Should print `HEALTHY`.

---

## FIX 3 — Remove Orphan trading-ml Container

### Problem
Container `tickertap-trading-ml-1` is running (`uvicorn api:app --host 0.0.0.0 --port 8001`)
but is NOT defined in `docker-compose.prod.yml`. It is an orphan from a previous dev
iteration. It has been running 11+ days serving only GET /health with 2 GB memory limit
allocated. No TickerTap service depends on port 8001.

### Fix
This is a manual Docker operation — NOT a code change.

**Warning:** Verify nothing calls port 8001 before removing:
```bash
grep -r "8001" /path/to/tickerTap/backend/app/ --include="*.py"
grep -r "8001" /path/to/tickerTap/frontend/src/ --include="*.js" --include="*.jsx"
```
If grep returns no results, proceed:

```bash
docker stop tickertap-trading-ml-1
docker rm tickertap-trading-ml-1
```

Also check for any leftover image to free disk:
```bash
docker images | grep trading-ml
# If found:
docker rmi <image-id>
```

To prevent it from being re-created if there is a stale dev `docker-compose.yml` entry,
search the dev compose file:
```bash
grep -r "trading.ml\|trading-ml\|8001" /path/to/tickerTap/*.yml \
  /path/to/tickerTap/*.yaml 2>/dev/null
```
If found, remove the service block from the dev compose file.

---

## FIX 4 — Secure ai_agent_postgres Port Binding

### Problem
`/path/to/ai-agent-stack/docker-compose.yml` line 13:
```yaml
ports:
  - "5432:5432"
```
No `HostIp` specified → Docker binds to `0.0.0.0` → PostgreSQL is accessible from any
network interface, including the public-facing one. Any device on the LAN (or internet
if router forwards 5432) can attempt to connect.

### Fix
**File: `/path/to/ai-agent-stack/docker-compose.yml`**

Line 13:
```yaml
# BEFORE
    ports:
      - "5432:5432"

# AFTER
    ports:
      - "127.0.0.1:5432:5432"
```

This restricts PostgreSQL to localhost only. n8n, worker, and monitor all connect via the
internal Docker network (`ai_agent_network`) using the service name `postgres` as hostname —
they do NOT go through the host port binding, so this change does not affect any container.

Also apply the same fix to Redis on line 44 for defense-in-depth:
```yaml
# BEFORE
    ports:
      - "6379:6379"

# AFTER
    ports:
      - "127.0.0.1:6379:6379"
```

### Deploy
```bash
cd /path/to/ai-agent-stack
docker compose down postgres redis
docker compose up -d postgres redis
```

### Verify
From the host (not inside a container):
```bash
nc -zv 127.0.0.1 5432   # should connect
nc -zv <YOUR_APP_SERVER_IP> 5432  # should REFUSE
```

---

## FIX 5 — Add Worker Heartbeat Monitoring Endpoint

### Problem
The n8n monitor at `/path/to/ai-agent-stack/monitor/main.py` checks TickerTap
via `GET http://<YOUR_APP_SERVER_IP>:8000/health` but has no visibility into individual arq
worker health (trading-worker, paper-worker, alert-worker). Worker failures are invisible
to n8n alerts.

### Fix (Part A) — Add unauthenticated `/metrics/workers` endpoint to TickerTap backend

**File: `backend/app/routes/trading.py`** (or wherever the observability/metrics route lives)

First check if `backend/app/observability.py` or `backend/app/routes/metrics.py` already
has a workers endpoint. If not, add to the end of the most appropriate existing route file
(check `backend/app/main.py` for where routes are registered).

Add this endpoint — it reads from Redis and requires NO auth (monitoring use):
```python
@router.get("/metrics/workers", response_model=None, include_in_schema=False)
async def get_worker_metrics():
    """Return arq worker heartbeat status for monitoring.

    Unauthenticated — internal monitoring use only. Returns HTTP 200 with
    JSON body containing per-worker health data.
    """
    import time
    import redis.asyncio as aioredis
    from ..trading.heartbeat import HEARTBEAT_KEY_PREFIX, METRICS_KEY_PREFIX, _HEARTBEAT_TTL

    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    workers = ["trading-worker", "paper-worker", "alert-worker"]
    result = {}

    try:
        client = aioredis.Redis.from_url(redis_url, decode_responses=True,
                                          socket_connect_timeout=2, socket_timeout=2)
        try:
            for name in workers:
                hb_val = await client.get(f"{HEARTBEAT_KEY_PREFIX}{name}")
                metrics = await client.hgetall(f"{METRICS_KEY_PREFIX}{name}")
                threshold = _HEARTBEAT_TTL.get(name, 600)
                if hb_val is None:
                    status = "no_heartbeat"
                    age_seconds = None
                else:
                    age_seconds = round(time.time() - float(hb_val), 1)
                    status = "healthy" if age_seconds < threshold else "stale"
                result[name] = {
                    "status": status,
                    "age_seconds": age_seconds,
                    "last_run": metrics.get("last_run"),
                    "last_error": metrics.get("last_error") or "",
                    "jobs_processed": int(metrics.get("jobs_processed", 0)),
                }
        finally:
            await client.aclose()
    except Exception as exc:
        return {"error": str(exc)}

    return result
```

Register the route at `/api/v1/metrics/workers` (or wherever makes sense given `main.py`
route registration).

### Fix (Part B) — Update ai_agent_monitor to check worker heartbeats

**File: `/path/to/ai-agent-stack/monitor/main.py`**

Find the section that checks TickerTap (`http://<YOUR_APP_SERVER_IP>:8000/health`) and add a
second check after it:

```python
# After the existing TickerTap /health check, add:
async def check_tickertap_workers(session: aiohttp.ClientSession) -> dict:
    """Check TickerTap arq worker heartbeat status."""
    url = "http://<YOUR_APP_SERVER_IP>:8000/api/v1/metrics/workers"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            if resp.status == 200:
                data = await resp.json()
                unhealthy = [
                    name for name, info in data.items()
                    if info.get("status") != "healthy"
                ]
                return {
                    "healthy": len(unhealthy) == 0,
                    "unhealthy_workers": unhealthy,
                    "details": data,
                }
            return {"healthy": False, "error": f"HTTP {resp.status}"}
    except Exception as exc:
        return {"healthy": False, "error": str(exc)}
```

Wire this into the main health check loop and include worker status in Telegram alerts
when any worker is not healthy. Follow the existing pattern used for other checks in the
file — do not restructure unrelated code.

### Deploy
After code changes:
1. Rebuild and restart TickerTap app: `docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build app`
2. Rebuild and restart monitor: `cd /path/to/ai-agent-stack && docker compose up -d --build monitor`

### Verify
```bash
curl -s http://<YOUR_APP_SERVER_IP>:8000/api/v1/metrics/workers | python3 -m json.tool
```
Should return JSON with status for all three workers.
