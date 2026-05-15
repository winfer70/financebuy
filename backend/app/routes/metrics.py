"""
metrics.py — Internal observability endpoints for TickerTap monitoring.

These endpoints are unauthenticated and excluded from API docs.
They are intended for internal monitoring tools (n8n, REDACTED_HOST dashboard).
"""

import os
import time
from fastapi import APIRouter
import redis.asyncio as aioredis

from ..trading.heartbeat import HEARTBEAT_KEY_PREFIX, METRICS_KEY_PREFIX, _HEARTBEAT_TTL

router = APIRouter(tags=["metrics"])

_WORKERS = ["trading-worker", "paper-worker", "alert-worker"]


@router.get("/metrics/workers", include_in_schema=False)
async def get_worker_metrics():
    """Return arq worker heartbeat status.

    Reads from Redis. Returns per-worker status: healthy, stale, or no_heartbeat.
    Health threshold = each worker's heartbeat TTL from heartbeat.py.

    Returns:
        dict mapping worker name to status dict with keys:
            status: "healthy" | "stale" | "no_heartbeat"
            age_seconds: float | None
            last_run: str | None  (ISO-8601)
            last_error: str
            jobs_processed: int
    """
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    result = {}

    try:
        client = aioredis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        try:
            for name in _WORKERS:
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
