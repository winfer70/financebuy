"""
article_queue.py — SQLite fallback queue for the TickerTap news worker.

When Server A is unreachable, scored articles are queued locally in a SQLite
database.  On each worker cycle the queue is flushed first — successfully
posted articles are removed, failed ones have their retry count incremented.

After ``MAX_RETRIES`` (5) failed attempts an article is logged as a dead
letter and removed from the queue to prevent infinite retries.

Public interface:
    init_db()                → create the table if it doesn't exist
    enqueue(payload_json)    → store a failed article payload
    get_pending(limit)       → retrieve queued articles for retry
    mark_done(row_id)        → remove a successfully posted article
    increment_retries(row_id)→ bump retry counter; removes dead letters
    pending_count()          → number of articles waiting in the queue
"""

import json
import logging
import os
import sqlite3
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
_DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_DB_DIR, "queue.db")
MAX_RETRIES = 5


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    """Open a connection to the local SQLite queue database.

    Returns:
        sqlite3.Connection with row_factory set to sqlite3.Row.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create the ``pending_articles`` table if it does not already exist.

    Should be called once at worker startup to ensure the schema is present.
    """
    conn = _connect()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pending_articles (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                payload     TEXT    NOT NULL,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                retries     INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.commit()
        logger.info("Queue database initialised at %s", DB_PATH)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------

def enqueue(payload_json: str) -> None:
    """Insert a scored article payload into the local queue.

    Args:
        payload_json: JSON string of the article payload (ready to POST).
    """
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO pending_articles (payload) VALUES (?)",
            (payload_json,),
        )
        conn.commit()
        logger.debug("Queued 1 article for later delivery.")
    finally:
        conn.close()


def enqueue_batch(payloads: List[str]) -> None:
    """Insert multiple scored article payloads into the local queue.

    Args:
        payloads: List of JSON strings, each a single article payload.
    """
    if not payloads:
        return
    conn = _connect()
    try:
        conn.executemany(
            "INSERT INTO pending_articles (payload) VALUES (?)",
            [(p,) for p in payloads],
        )
        conn.commit()
        logger.info("Queued %d articles for later delivery.", len(payloads))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------

def get_pending(limit: int = 50) -> List[Tuple[int, str]]:
    """Retrieve pending articles that have not exceeded the retry limit.

    Args:
        limit: Maximum number of articles to retrieve per flush cycle.

    Returns:
        List of (row_id, payload_json) tuples ordered by creation time.
    """
    conn = _connect()
    try:
        cursor = conn.execute(
            "SELECT id, payload FROM pending_articles "
            "WHERE retries < ? ORDER BY created_at ASC LIMIT ?",
            (MAX_RETRIES, limit),
        )
        return [(row["id"], row["payload"]) for row in cursor.fetchall()]
    finally:
        conn.close()


def pending_count() -> int:
    """Return the number of articles currently waiting in the queue.

    Returns:
        Integer count of pending (retries < MAX_RETRIES) articles.
    """
    conn = _connect()
    try:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM pending_articles WHERE retries < ?",
            (MAX_RETRIES,),
        )
        return cursor.fetchone()[0]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Update / delete operations
# ---------------------------------------------------------------------------

def mark_done(row_id: int) -> None:
    """Remove a successfully posted article from the queue.

    Args:
        row_id: Primary key (id) of the pending_articles row.
    """
    conn = _connect()
    try:
        conn.execute("DELETE FROM pending_articles WHERE id = ?", (row_id,))
        conn.commit()
    finally:
        conn.close()


def increment_retries(row_id: int) -> None:
    """Bump the retry counter for a failed article.

    If the retry count reaches ``MAX_RETRIES``, the article is logged as a
    dead letter and removed from the queue.

    Args:
        row_id: Primary key (id) of the pending_articles row.
    """
    conn = _connect()
    try:
        conn.execute(
            "UPDATE pending_articles SET retries = retries + 1 WHERE id = ?",
            (row_id,),
        )
        conn.commit()

        # Check if the article has exceeded the retry limit.
        cursor = conn.execute(
            "SELECT id, payload, retries FROM pending_articles WHERE id = ?",
            (row_id,),
        )
        row = cursor.fetchone()
        if row and row["retries"] >= MAX_RETRIES:
            logger.warning(
                "Dead letter: article id=%d exceeded %d retries. Removing. "
                "Payload preview: %.120s",
                row_id,
                MAX_RETRIES,
                row["payload"],
            )
            conn.execute("DELETE FROM pending_articles WHERE id = ?", (row_id,))
            conn.commit()
    finally:
        conn.close()


def cleanup_dead_letters() -> int:
    """Remove all articles that have exceeded the retry limit.

    Returns:
        Number of dead letter articles removed.
    """
    conn = _connect()
    try:
        cursor = conn.execute(
            "DELETE FROM pending_articles WHERE retries >= ?",
            (MAX_RETRIES,),
        )
        conn.commit()
        removed = cursor.rowcount
        if removed > 0:
            logger.info("Cleaned up %d dead letter articles.", removed)
        return removed
    finally:
        conn.close()
