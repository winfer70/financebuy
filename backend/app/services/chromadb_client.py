"""
chromadb_client.py — ChromaDB client for trade analysis embeddings.

Uses raw httpx REST calls (no chromadb Python package — requires pydantic v2).
Collection: trade_analyses
Embedding: ticker + sector + recommendation + market_data summary
Used for RAG injection in analysis_routes.py — finds similar past trades with outcomes.
"""

import os
from typing import Optional

import httpx
import structlog

logger = structlog.get_logger("tickerTap.chromadb")

_CHROMADB_URL = os.getenv("CHROMADB_URL", "http://localhost:8000")
_COLLECTION_NAME = "trade_analyses"
_TIMEOUT = httpx.Timeout(10.0)

_collection_id: Optional[str] = None


async def _get_collection_id() -> Optional[str]:
    global _collection_id
    if _collection_id:
        return _collection_id
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get(f"{_CHROMADB_URL}/api/v1/collections/{_COLLECTION_NAME}")
            if r.status_code == 200:
                _collection_id = r.json()["id"]
                return _collection_id
            # Create if not found
            r2 = await client.post(
                f"{_CHROMADB_URL}/api/v1/collections",
                json={"name": _COLLECTION_NAME, "metadata": {"hnsw:space": "cosine"}},
            )
            if r2.status_code in (200, 201):
                _collection_id = r2.json()["id"]
                return _collection_id
            logger.warning("chromadb_collection_create_failed", status=r2.status_code)
            return None
    except Exception as exc:
        logger.warning("chromadb_init_failed", error=str(exc))
        return None


def _build_doc(
    analysis_id: str,
    ticker: str,
    recommendation: Optional[str],
    market_data: dict,
    analysis_text: str,
    outcome: Optional[str] = None,
    actual_pnl_pct: Optional[float] = None,
) -> str:
    price = market_data.get("price", "?")
    rsi = market_data.get("rsi14", "?")
    sector = market_data.get("sector", "Unknown")
    sma50 = market_data.get("sma50", "?")
    sma200 = market_data.get("sma200", "?")
    outcome_str = f" | Outcome: {outcome}" if outcome else ""
    pnl_str = f" | PnL: {actual_pnl_pct:.2f}%" if actual_pnl_pct is not None else ""
    return (
        f"Ticker: {ticker} | Sector: {sector} | Rec: {recommendation or 'N/A'} | "
        f"Price: {price} | RSI14: {rsi} | SMA50: {sma50} | SMA200: {sma200}{outcome_str}{pnl_str} | "
        f"Analysis: {analysis_text}"
    )


async def store_analysis(
    analysis_id: str,
    ticker: str,
    recommendation: Optional[str],
    market_data: dict,
    analysis_text: str,
    outcome: Optional[str] = None,
    actual_pnl_pct: Optional[float] = None,
) -> Optional[str]:
    """Upsert a trade analysis embedding. Returns chromadb_id or None on failure."""
    col_id = await _get_collection_id()
    if col_id is None:
        return None
    doc_id = f"analysis_{analysis_id}"
    doc = _build_doc(analysis_id, ticker, recommendation, market_data, analysis_text, outcome, actual_pnl_pct)
    metadata = {
        "ticker": ticker,
        "recommendation": recommendation or "",
        "outcome": outcome or "OPEN",
        "sector": market_data.get("sector", ""),
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{_CHROMADB_URL}/api/v1/collections/{col_id}/upsert",
                json={"ids": [doc_id], "documents": [doc], "metadatas": [metadata]},
            )
            if r.status_code in (200, 201):
                return doc_id
            logger.warning("chromadb_upsert_failed", status=r.status_code, body=r.text[:200])
            return None
    except Exception as exc:
        logger.warning("chromadb_upsert_failed", error=str(exc))
        return None


async def query_similar(
    ticker: str,
    sector: str,
    recommendation: Optional[str],
    n_results: int = 3,
) -> list:
    """Find similar past analyses with known outcomes for RAG context."""
    col_id = await _get_collection_id()
    if col_id is None:
        return []
    query = f"Ticker: {ticker} | Sector: {sector} | Rec: {recommendation or 'N/A'}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{_CHROMADB_URL}/api/v1/collections/{col_id}/query",
                json={
                    "query_texts": [query],
                    "n_results": n_results,
                    "where": {"outcome": {"$ne": "OPEN"}},
                },
            )
            if r.status_code != 200:
                logger.warning("chromadb_query_failed", status=r.status_code)
                return []
            data = r.json()
            docs = data.get("documents", [[]])[0]
            metas = data.get("metadatas", [[]])[0]
            return [{"doc": d, "meta": m} for d, m in zip(docs, metas)]
    except Exception as exc:
        logger.warning("chromadb_query_failed", error=str(exc))
        return []
