"""
chromadb_client.py — ChromaDB client for trade analysis embeddings.

Collection: trade_analyses
Embedding: ticker + sector + recommendation + market_data summary
Used for RAG injection in analysis_routes.py — finds similar past trades with outcomes.
"""

import os
from typing import Optional

import chromadb
import structlog

logger = structlog.get_logger("tickerTap.chromadb")

_CHROMADB_URL = os.getenv("CHROMADB_URL", "http://REDACTED:8000")
_COLLECTION = "trade_analyses"

_client: Optional[chromadb.HttpClient] = None
_collection = None


def _get_client():
    global _client, _collection
    if _client is None:
        try:
            _client = chromadb.HttpClient(
                host=_CHROMADB_URL.replace("http://", "").split(":")[0],
                port=int(_CHROMADB_URL.rsplit(":", 1)[-1]),
            )
            _collection = _client.get_or_create_collection(
                name=_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as exc:
            logger.warning("chromadb_init_failed", error=str(exc))
            _client = None
            _collection = None
    return _collection


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


def store_analysis(
    analysis_id: str,
    ticker: str,
    recommendation: Optional[str],
    market_data: dict,
    analysis_text: str,
    outcome: Optional[str] = None,
    actual_pnl_pct: Optional[float] = None,
) -> Optional[str]:
    """Upsert a trade analysis embedding. Returns chromadb_id or None on failure."""
    col = _get_client()
    if col is None:
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
        col.upsert(ids=[doc_id], documents=[doc], metadatas=[metadata])
        return doc_id
    except Exception as exc:
        logger.warning("chromadb_upsert_failed", error=str(exc))
        return None


def query_similar(
    ticker: str,
    sector: str,
    recommendation: Optional[str],
    n_results: int = 3,
) -> list:
    """Find similar past analyses with known outcomes for RAG context."""
    col = _get_client()
    if col is None:
        return []
    query = f"Ticker: {ticker} | Sector: {sector} | Rec: {recommendation or 'N/A'}"
    try:
        results = col.query(
            query_texts=[query],
            n_results=n_results,
            where={"outcome": {"$ne": "OPEN"}},
        )
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        return [{"doc": d, "meta": m} for d, m in zip(docs, metas)]
    except Exception as exc:
        logger.warning("chromadb_query_failed", error=str(exc))
        return []
