"""
heartbeat.py — Worker heartbeat writer for TickerTap arq workers.

Each worker calls write_worker_heartbeat() on every evaluation cycle to
record that it is alive and to update job counters. The data is stored in
Redis and consumed by the /metrics endpoint via app/observability.py.

Redis schema (per worker):
  tickertap:worker:heartbeat:<name>  → Unix timestamp (string), TTL per worker
  tickertap:worker:metrics:<name>    → hash:
      last_run         ISO-8601 timestamp of last cycle
      last_error       last error string (max 500 chars), empty if healthy
      jobs_processed   cumulative counter (incremented atomically via HINCRBY)

Design notes:
  - Never raises — heartbeat failure must never crash the calling worker.
  - Opens a fresh Redis connection per call (no long-lived connection state
    in workers that may be idle for minutes).
  - TTLs are generous (3× the longest expected inter-cycle gap) so that
    a single slow cycle does not falsely trigger a "down" alert.
"""

import os
import time
from datetime import datetime, timezone

import redis.asyncio as aioredis

# TTL (seconds) per worker name — set to ~3× the maximum expected cycle gap
_HEARTBEAT_TTL = {
    "trading-worker": 1800,  # backtest jobs can run for many minutes
    "paper-worker": 180,     # 3× its 60s evaluation cycle
    "alert-worker": 900,     # 3× its 300s max cycle (market closed)
}
_DEFAULT_TTL = 600

HEARTBEAT_KEY_PREFIX = "tickertap:worker:heartbeat:"
METRICS_KEY_PREFIX = "tickertap:worker:metrics:"


async def write_worker_heartbeat(
    worker_name: str,
    redis_url: str,
    jobs_processed_delta: int = 1,
    last_error: str = "",
) -> None:
    """Write heartbeat timestamp and metrics to Redis.

    Uses a pipeline to update all keys atomically in a single round-trip.
    Opens a fresh aioredis connection and closes it after the pipeline
    executes — workers may be idle for long periods so persistent
    connections are not warranted.

    Never raises — any exception is silently swallowed so that heartbeat
    failures cannot crash the worker.

    Args:
        worker_name:           Logical name, e.g. "alert-worker".
        redis_url:             Redis DSN, e.g. "redis://redis:6379/0".
        jobs_processed_delta:  Number of jobs completed this cycle (added
                               to the running counter).  Pass 0 for
                               startup pings where no job ran.
        last_error:            Error message from this cycle, or "" if OK.
                               Truncated to 500 chars before storage.
    """
    try:
        ttl = _HEARTBEAT_TTL.get(worker_name, _DEFAULT_TTL)
        now_ts = str(time.time())
        now_iso = datetime.now(tz=timezone.utc).isoformat()

        # Open a short-lived connection with tight timeouts
        client = aioredis.Redis.from_url(
            redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=True,
        )
        try:
            pipe = client.pipeline()

            # Heartbeat key — plain string (Unix float) with expiry
            pipe.set(f"{HEARTBEAT_KEY_PREFIX}{worker_name}", now_ts, ex=ttl)

            # Metrics hash — last_run and last_error are overwritten each cycle
            pipe.hset(
                f"{METRICS_KEY_PREFIX}{worker_name}",
                mapping={
                    "last_run": now_iso,
                    "last_error": last_error[:500] if last_error else "",
                },
            )

            # Increment jobs_processed counter atomically
            if jobs_processed_delta > 0:
                pipe.hincrby(
                    f"{METRICS_KEY_PREFIX}{worker_name}",
                    "jobs_processed",
                    jobs_processed_delta,
                )

            await pipe.execute()
        finally:
            # Always release the connection back to the pool
            await client.aclose()
    except Exception:
        # Heartbeat failure must never crash the worker — swallow silently
        pass
