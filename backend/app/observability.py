"""
observability.py — Health check and worker metrics utilities for TickerTap.

Provides:
  - check_db()           — async DB connectivity probe
  - check_redis()        — async Redis connectivity probe
  - get_worker_metrics() — reads heartbeat + counters from Redis for all workers
  - get_redis_client()   — singleton aioredis client for the FastAPI process

Used by /health and /metrics endpoints (registered in main.py).

Worker heartbeat keys (written by app/trading/heartbeat.py):
  tickertap:worker:heartbeat:<name>   → Unix timestamp float, with TTL
  tickertap:worker:metrics:<name>     → hash: jobs_processed, last_run, last_error
"""

import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis
from sqlalchemy import text

# Set at process startup by main.py _startup_checks()
APP_START_TIME: float = time.monotonic()
APP_START_WALL: Optional[datetime] = None

HEARTBEAT_KEY_PREFIX = "tickertap:worker:heartbeat:"
METRICS_KEY_PREFIX = "tickertap:worker:metrics:"

_redis_client: Optional[aioredis.Redis] = None


def get_redis_client() -> aioredis.Redis:
    """Return or create the module-level Redis client singleton.

    Lazily initialised on first call. Uses REDIS_URL env var.

    Returns:
        aioredis.Redis: Shared async Redis client with short connect/op timeouts.
    """
    global _redis_client
    if _redis_client is None:
        url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        _redis_client = aioredis.Redis.from_url(
            url, socket_connect_timeout=2, socket_timeout=2, decode_responses=True
        )
    return _redis_client


async def check_db() -> dict:
    """Probe database connectivity with a SELECT 1 query.

    Imports app.db.engine lazily to avoid circular imports at module load.
    Times out after 2 seconds.

    Returns:
        dict: {ok: bool, latency_ms: float, error: str|None}
    """
    start = time.monotonic()
    try:
        # Lazy import to avoid circular dependency — observability.py must not
        # import db.py at module level because db.py may import observability.py.
        from app.db import engine  # noqa: PLC0415
        async with engine.connect() as conn:
            await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=2.0)
        return {
            "ok": True,
            "latency_ms": round((time.monotonic() - start) * 1000, 1),
            "error": None,
        }
    except Exception as e:
        return {
            "ok": False,
            "latency_ms": round((time.monotonic() - start) * 1000, 1),
            "error": str(e)[:200],
        }


async def check_redis() -> dict:
    """Probe Redis connectivity with a PING command.

    Times out after 2 seconds.

    Returns:
        dict: {ok: bool, latency_ms: float, error: str|None}
    """
    start = time.monotonic()
    try:
        client = get_redis_client()
        await asyncio.wait_for(client.ping(), timeout=2.0)
        return {
            "ok": True,
            "latency_ms": round((time.monotonic() - start) * 1000, 1),
            "error": None,
        }
    except Exception as e:
        return {
            "ok": False,
            "latency_ms": round((time.monotonic() - start) * 1000, 1),
            "error": str(e)[:200],
        }


async def get_worker_metrics() -> dict:
    """Read heartbeat timestamp and job counters for all three arq workers.

    Reads two Redis keys per worker:
      - heartbeat key (plain string, Unix timestamp, has TTL)
      - metrics hash  (jobs_processed, last_run, last_error)

    Returns:
        dict keyed by worker name, each value:
            {last_seen, last_seen_seconds_ago, jobs_processed, last_run, last_error}
        On any Redis error, all workers report None/0/"Redis unavailable".
    """
    workers = ["trading-worker", "paper-worker", "alert-worker"]
    result = {}
    try:
        client = get_redis_client()
        for name in workers:
            hb_key = f"{HEARTBEAT_KEY_PREFIX}{name}"
            metrics_key = f"{METRICS_KEY_PREFIX}{name}"

            try:
                # Fetch heartbeat and metrics hash concurrently
                hb_val, metrics = await asyncio.gather(
                    client.get(hb_key),
                    client.hgetall(metrics_key),
                    return_exceptions=True,
                )
                last_seen = None
                last_seen_seconds_ago = None
                if isinstance(hb_val, str):
                    try:
                        ts = float(hb_val)
                        last_seen_seconds_ago = int(time.time() - ts)
                        last_seen = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                    except (ValueError, OSError):
                        pass

                result[name] = {
                    "last_seen": last_seen,
                    "last_seen_seconds_ago": last_seen_seconds_ago,
                    "jobs_processed": int(metrics.get("jobs_processed", 0)) if isinstance(metrics, dict) else 0,
                    "last_run": metrics.get("last_run") if isinstance(metrics, dict) else None,
                    "last_error": metrics.get("last_error", "") if isinstance(metrics, dict) else "",
                }
            except Exception as e:
                result[name] = {
                    "last_seen": None,
                    "last_seen_seconds_ago": None,
                    "jobs_processed": 0,
                    "last_run": None,
                    "last_error": str(e),
                }
    except Exception:
        # Redis entirely unavailable — fill all workers with safe defaults
        for name in workers:
            result[name] = {
                "last_seen": None,
                "last_seen_seconds_ago": None,
                "jobs_processed": 0,
                "last_run": None,
                "last_error": "Redis unavailable",
            }
    return result
